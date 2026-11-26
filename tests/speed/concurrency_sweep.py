"""Decode speed with N parallel requests against an OpenAI-compatible server on 127.0.0.1:8080 (run it on the GPU box).

    python3 concurrency_sweep.py [model_id] [max_tokens] [levels]
    python3 concurrency_sweep.py qwen3.8-27b 512 1,2,3,4,6

Same method and prompts as HyperInkling's scripts/quick_bench.py (2026-11-25 Inkling sweep), so the numbers compare:
temperature 0, ignore_eos, fixed max_tokens, streams start together. "total" = all tokens / wall time of the run;
"per stream" = each stream's tokens / its decode time (first token -> end). GPU power and SM clock are sampled
every 0.5 s while each level runs. Works with vLLM (HyperQwen, HyperInkling) and llama.cpp.
"""
import json
import subprocess
import sys
import threading
import time
import urllib.request

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.8-27b"
MAX_TOKENS = int(sys.argv[2]) if len(sys.argv) > 2 else 512
LEVELS = [int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "1,2,3,4,6").split(",")]
URL = "http://127.0.0.1:8080/v1/chat/completions"
PROMPTS = [
    "Spiega in dettaglio come funziona un motore a quattro tempi.",
    "Descrivi la storia dell'Impero romano d'Occidente.",
    "Write a detailed guide to binary search trees in Python.",
    "Elenca e spiega i principi della termodinamica.",
    "Racconta una lunga storia su un faro in Sardegna.",
    "Explain how TCP congestion control works, step by step.",
]


def stream(i, res):
    body = json.dumps({"model": MODEL,
        "messages": [{"role": "user", "content": PROMPTS[i % len(PROMPTS)]}],
        "max_tokens": MAX_TOKENS, "temperature": 0, "stream": True, "ignore_eos": True,
        "stream_options": {"include_usage": True}}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json"})
    t0, first, toks, chunks = time.time(), None, 0, 0
    for line in urllib.request.urlopen(req, timeout=600):
        if not line.startswith(b"data: {"):
            continue
        d = json.loads(line[6:])
        if d.get("usage"):
            toks = d["usage"]["completion_tokens"]
        if d.get("choices"):
            chunks += 1
            if first is None:
                first = time.time()
    res.append((first - t0, toks or chunks, time.time() - first))


def gpu_sampler(stop, samples):
    while not stop.is_set():
        out = subprocess.run(["nvidia-smi", "--query-gpu=power.draw,clocks.sm", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True).stdout.strip().split(",")
        try:
            samples.append((float(out[0]), float(out[1])))
        except (ValueError, IndexError):
            pass
        time.sleep(0.5)


print(f"model {MODEL}, {MAX_TOKENS} tokens per request, levels {LEVELS}")
stream(0, [])  # warm-up, not counted
for n in LEVELS:
    res, samples, stop = [], [], threading.Event()
    g = threading.Thread(target=gpu_sampler, args=(stop, samples)); g.start()
    t0 = time.time()
    ts = [threading.Thread(target=stream, args=(i, res)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    wall = time.time() - t0
    stop.set(); g.join()
    total = sum(r[1] for r in res)
    per = [r[1] / r[2] for r in res]
    pw = [s[0] for s in samples] or [0]
    clk = [s[1] for s in samples] or [0]
    print(f"{n} req: total {total / wall:6.1f} tok/s | per stream {min(per):5.1f}-{max(per):5.1f} "
          f"(sum {sum(per):6.1f}) | TTFT max {max(r[0] for r in res):5.2f}s | GPU avg {sum(pw) / len(pw):.0f} W "
          f"max {max(pw):.0f} W, SM avg {sum(clk) / len(clk):.0f} MHz", flush=True)
