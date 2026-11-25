#!/usr/bin/env python3
"""Run the writing test (prompts_nl.json or prompts_en.json) against an OpenAI-compatible server. Stdlib only.

usage: run_writing_test.py LABEL [PORT] [MODEL] [PROMPTS_FILE]   (default prompts_nl.json)
writes results_<LABEL>.json (labels used: nl_<model>, en_<model>) next to this script. Server default settings are kept (thinking on if the server
does that by default); reasoning text is stored separately and its length counted.
"""
import json, sys, time, urllib.request, os

label = sys.argv[1]
port = sys.argv[2] if len(sys.argv) > 2 else "8080"
here = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(os.path.join(here, sys.argv[4] if len(sys.argv) > 4 else "prompts_nl.json")))
base = f"http://127.0.0.1:{port}/v1"

def get(path):
    return json.load(urllib.request.urlopen(base + path, timeout=30))

model = (sys.argv[3] if len(sys.argv) > 3 else "") or get("/models")["data"][0]["id"]

def chat(messages, tools=None):
    body = {"model": model, "messages": messages, "max_tokens": 6000, "temperature": 0.7, "top_p": 0.95}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=900))
    dt = time.time() - t
    m = r["choices"][0]["message"]
    reasoning = m.get("reasoning_content") or m.get("reasoning") or ""
    return {"content": m.get("content") or "", "reasoning_chars": len(reasoning), "reasoning": reasoning,
            "tool_calls": m.get("tool_calls") or [], "finish": r["choices"][0].get("finish_reason"),
            "usage": r.get("usage"), "seconds": round(dt, 1)}

out = {"label": label, "model": model, "date": time.strftime("%Y-%m-%d %H:%M"), "writing": {}, "tools": {}}
for p in P["prompts"]:
    res = chat([{"role": "system", "content": P["system"]},
                {"role": "user", "content": ("Message from buyer about listing " if P["version"].endswith("-en")
                                            else "Bericht van koper over advertentie ") + f"{p['ad']}:\n\n{p['buyer']}"}])
    out["writing"][p["id"]] = res
    print(p["id"], res["seconds"], "s", res["finish"], res["usage"] and res["usage"].get("completion_tokens"), flush=True)
T = P["tool_test"]
for c in T["cases"]:
    res = chat([{"role": "system", "content": T["system"]}, {"role": "user", "content": c["buyer"]}], T["tools"])
    out["tools"][c["id"]] = res
    print(c["id"], res["seconds"], "s", [tc["function"]["name"] + tc["function"]["arguments"] for tc in res["tool_calls"]], flush=True)
json.dump(out, open(os.path.join(here, f"results_{label}.json"), "w"), ensure_ascii=False, indent=1)
print("WROTE", f"results_{label}.json")
