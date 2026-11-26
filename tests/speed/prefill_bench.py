"""Prefill speed (time to first token) on long prompts against an OpenAI-compatible server on 127.0.0.1:8080 (run it on the GPU box).

    python3 prefill_bench.py [model_id] [sizes_in_k_tokens] [repeats]
    python3 prefill_bench.py qwen3.8-27b 8,30 2

Each prompt starts with a random nonce, so no prefix cache can be reused; max_tokens 1. Prompt tokens come from the
server's usage numbers. Made as the "before" measurement for gpu-unlock (prefill is what it speeds up).
"""
import json
import random
import sys
import time
import urllib.request

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.8-27b"
SIZES = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "8,30").split(",")]
REPEATS = int(sys.argv[3]) if len(sys.argv) > 3 else 2
URL = "http://127.0.0.1:8080/v1/chat/completions"
PARA = ("The municipal archive of a mid-sized Dutch town keeps records of bridges, canals, windmills and bicycle "
        "paths, together with council minutes, budgets and letters from residents about drainage and road works. ")


def ttft(k):
    words = int(k * 1000 / 1.25 / len(PARA.split()))  # ~1.25 tokens per word for this English text
    text = f"[{random.random():.12f}] " + PARA * words + "\nSummarise the archive in one word."
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": text}], "max_tokens": 1,
                       "temperature": 0, "stream": True, "stream_options": {"include_usage": True}}).encode()
    t0, first, ptoks = time.time(), None, 0
    for line in urllib.request.urlopen(urllib.request.Request(URL, body, {"Content-Type": "application/json"}),
                                       timeout=900):
        if not line.startswith(b"data: {"):
            continue
        d = json.loads(line[6:])
        if d.get("usage"):
            ptoks = d["usage"].get("prompt_tokens", 0)
        if first is None and d.get("choices"):
            first = time.time()
    end = time.time()
    return (first or end) - t0, end - t0, ptoks


print(f"model {MODEL}")
ttft(1)  # warm-up
for k in SIZES:
    for r in range(REPEATS):
        t, total, p = ttft(k)
        print(f"{k:>3}K: prompt {p:6d} tok | first chunk {t:6.2f}s | done {total:6.2f}s | {p / total:7.0f} tok/s prefill",
              flush=True)
