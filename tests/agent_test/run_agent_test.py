#!/usr/bin/env python3
"""Agent test: tool calling (multi-turn, mock tools that really run) + small coding tasks (unit tests).
Stdlib only. Scores itself.

usage: run_agent_test.py LABEL [PORT] [only=tools|code]
env: TASKS=t09_nested_args,c08_extract_json (subset), REPEAT=5 (runs per task), MAX_TOKENS=8000
writes results_<LABEL>.json next to this script and prints a score table.

Tool part: the model gets tools and a task; we execute its calls against a fixed fake world and feed results back
(max 8 rounds). A check function then looks at the calls it made and its final answer.
Code part: the model writes a Python function; we run unit tests in a subprocess (python3 -I, 10 s timeout, temp
dir). If they fail, we send the error back once (= what a small agent loop would do) and test again.
"""
import json, os, re, subprocess, sys, tempfile, time, urllib.request

LABEL = sys.argv[1]
PORT = sys.argv[2] if len(sys.argv) > 2 else "8080"
ONLY = sys.argv[3].split("=")[1] if len(sys.argv) > 3 else ""
TASKS = set(filter(None, os.environ.get("TASKS", "").split(",")))
REPEAT = int(os.environ.get("REPEAT", "1"))
MAXTOK = int(os.environ.get("MAX_TOKENS", "8000"))
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = f"http://127.0.0.1:{PORT}/v1"
MODEL = json.load(urllib.request.urlopen(BASE + "/models", timeout=30))["data"][0]["id"]


def chat(messages, tools=None):
    body = {"model": MODEL, "messages": messages, "max_tokens": MAXTOK, "temperature": 0.6, "top_p": 0.95}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(BASE + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=1200))
    return r["choices"][0], r.get("usage") or {}, time.time() - t


# ---------------------------------------------------------------- fake world for the tool part
LISTINGS = {
    "G-2021": {"id": "G-2021", "title": "Gazelle Ultimate C380 HMB", "brand": "Gazelle", "year": 2021, "price": 1450,
               "battery_wh": 500, "battery_health_pct": 86, "km": 8400, "status": "available"},
    "G-2018": {"id": "G-2018", "title": "Gazelle Arroyo C7", "brand": "Gazelle", "year": 2018, "price": 980,
               "battery_wh": 400, "battery_health_pct": 71, "km": 21000, "status": "available"},
    "G-2022": {"id": "G-2022", "title": "Gazelle Grenoble C5", "brand": "Gazelle", "year": 2022, "price": 1690,
               "battery_wh": 500, "battery_health_pct": 93, "km": 3100, "status": "reserved"},
    "B-2019": {"id": "B-2019", "title": "Batavus Finez E-go", "brand": "Batavus", "year": 2019, "price": 750,
               "battery_wh": 418, "battery_health_pct": None, "km": 15000, "status": "available"},
    "S-2020": {"id": "S-2020", "title": "Sparta M7b", "brand": "Sparta", "year": 2020, "price": 1100,
               "battery_wh": 500, "battery_health_pct": 80, "km": 12500, "status": "sold"},
}
WEATHER = {("Amersfoort", "2026-11-24"): {"temp_c": 7, "rain_mm": 4.5, "wind_bft": 4},
           ("Utrecht", "2026-11-24"): {"temp_c": 8, "rain_mm": 0.5, "wind_bft": 3}}
FILES = {"sales/2026-10.csv": 'date,listing_id,price,payment\n2026-10-03,K-11,640,cash\n2026-10-12,K-14,"1,150",tikkie\n'
                              '2026-10-28,K-19,890,cash\n',
         "sales/2026-11.csv": 'date,listing_id,price,payment\n2026-11-02,K-21,1200,tikkie\n2026-11-15,K-22,720,cash\n',
         "notes.txt": "Remember: battery tests at Fietsenmaker de Wit, Thursdays only."}


def fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


TOOLS = [
    fn("search_listings", "Search our own e-bike listings. Returns id, title, price, status.",
       {"brand": {"type": "string", "enum": ["Gazelle", "Batavus", "Sparta"]},
        "max_price": {"type": "integer", "description": "EUR"},
        "status": {"type": "string", "enum": ["available", "reserved", "sold", "any"]}}, []),
    fn("get_listing", "Full details of one listing by id.", {"listing_id": {"type": "string"}}, ["listing_id"]),
    fn("get_weather", "Weather forecast for a Dutch city on a date.",
       {"city": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"}}, ["city", "date"]),
    fn("list_files", "List files in the workspace.", {"prefix": {"type": "string"}}, []),
    fn("read_file", "Read a text file from the workspace.", {"path": {"type": "string"}}, ["path"]),
    fn("create_event", "Create a calendar event (the owner approves it later).",
       {"title": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"},
        "start": {"type": "string", "description": "HH:MM"}, "end": {"type": "string", "description": "HH:MM"}},
       ["title", "date", "start", "end"]),
    fn("create_invoice", "Create a draft invoice.",
       {"customer": {"type": "string"},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "description": {"type": "string"}, "qty": {"type": "integer"}, "unit_price": {"type": "number"}},
            "required": ["description", "qty", "unit_price"]}},
        "vat_pct": {"type": "number", "enum": [0, 9, 21]}}, ["customer", "items", "vat_pct"]),
]


def run_tool(name, a):
    if name == "search_listings":
        st = a.get("status", "available")
        out = [{k: l[k] for k in ("id", "title", "price", "status")} for l in LISTINGS.values()
               if (not a.get("brand") or l["brand"] == a["brand"]) and (not a.get("max_price") or l["price"] <= a["max_price"])
               and (st == "any" or l["status"] == st)]
        return out
    if name == "get_listing":
        l = LISTINGS.get(str(a.get("listing_id", "")).strip())
        return l or {"error": f"listing '{a.get('listing_id')}' not found. Use search_listings to find ids."}
    if name == "get_weather":
        w = WEATHER.get((a.get("city"), a.get("date")))
        return w or {"error": "no forecast for that city/date"}
    if name == "list_files":
        return [p for p in FILES if p.startswith(a.get("prefix", ""))]
    if name == "read_file":
        return FILES.get(a.get("path"), {"error": "file not found"}) if a.get("path") in FILES else {"error": "file not found"}
    if name in ("create_event", "create_invoice"):
        return {"ok": True, "id": "draft-1", "needs_approval": True}
    return {"error": f"unknown tool {name}"}


SYS_T = ("You are a helpful assistant for a small used e-bike business in Amersfoort, the Netherlands. Use the tools "
         "when they help; don't call tools you don't need. Today is Monday 23 November 2026. Answer in English, briefly.")


def calls(log, name=None):
    return [c for c in log if name is None or c["name"] == name]


def has(text, *needles):
    t = text.lower().replace(",", "").replace(".", "")
    return all(n.lower().replace(",", "").replace(".", "") in t for n in needles)


TOOL_TASKS = [
    ("t01_simple", "What's the battery health of listing G-2021?",
     lambda log, ans: bool(calls(log, "get_listing")) and has(ans, "86")),
    ("t02_enum_filter", "Which Gazelles do we have available under 1500 euro? Just the ids and prices.",
     lambda log, ans: any(c["args"].get("brand") == "Gazelle" for c in calls(log, "search_listings"))
     and has(ans, "G-2021") and has(ans, "G-2018") and "G-2022" not in ans),
    ("t03_chain", "Find our cheapest available Gazelle and tell me how many km it has done.",
     lambda log, ans: bool(calls(log, "search_listings")) and any(c["args"].get("listing_id") == "G-2018"
     for c in calls(log, "get_listing")) and has(ans, "21000")),
    ("t04_parallel", "Tomorrow I deliver a bike either in Amersfoort or Utrecht. Which city will be drier?",
     lambda log, ans: {c["args"].get("city") for c in calls(log, "get_weather")} >= {"Amersfoort", "Utrecht"}
     and all(c["args"].get("date") == "2026-11-24" for c in calls(log, "get_weather")) and "utrecht" in ans.lower()),
    ("t05_error_recovery", "Get me the details of listing G2018 (the Arroyo).",
     lambda log, ans: any(c["args"].get("listing_id") == "G-2018" for c in calls(log, "get_listing")) and has(ans, "980")),
    ("t06_no_tool", "In one sentence: why do e-bike batteries lose capacity in winter?",
     lambda log, ans: len(log) == 0 and len(ans) > 20),
    ("t07_files_sum", "What was our total sales revenue in October 2026? The sales files are in the workspace.",
     lambda log, ans: any(c["args"].get("path") == "sales/2026-10.csv" for c in calls(log, "read_file")) and has(ans, "2680")),
    ("t08_dates", "Put a pickup in the calendar: Saturday at 11:00 for one hour, buyer Sanne, listing B-2019.",
     lambda log, ans: any(c["args"].get("date") == "2026-11-28" and c["args"].get("start") == "11:00"
     and c["args"].get("end") == "12:00" for c in calls(log, "create_event"))),
    ("t09_nested_args", "Make a draft invoice for Jan de Vries: one Batavus Finez E-go at 700 euro and two bike locks at 35 "
     "euro each. Used bikes go under the margin scheme, so use 0% VAT.",
     lambda log, ans: any(c["args"].get("vat_pct") == 0 and len(c["args"].get("items") or []) == 2
     and sorted(int(i.get("qty", 0)) for i in c["args"]["items"]) == [1, 2]
     and sorted(float(i.get("unit_price", 0)) for i in c["args"]["items"]) == [35.0, 700.0] for c in calls(log, "create_invoice"))),
    ("t10_status_trap", "Is the Sparta M7b still for sale? A buyer asks.",
     lambda log, ans: bool(calls(log)) and ("sold" in ans.lower() or "not" in ans.lower() and "available" in ans.lower())),
]


def run_tool_task(tid, prompt, check):
    msgs = [{"role": "system", "content": SYS_T}, {"role": "user", "content": prompt}]
    log, secs, toks, bad_json, answer = [], 0.0, 0, 0, ""
    for _ in range(8):
        ch, usage, dt = chat(msgs, TOOLS)
        secs += dt; toks += usage.get("completion_tokens", 0)
        m = ch["message"]
        tcs = m.get("tool_calls") or []
        if not tcs:
            answer = m.get("content") or ""
            break
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": tcs})
        for tc in tcs:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except Exception:
                args, res = {"_raw": tc["function"]["arguments"]}, {"error": "arguments were not valid JSON"}
                bad_json += 1
            else:
                req = next((t["function"]["parameters"]["required"] for t in TOOLS
                            if t["function"]["name"] == tc["function"]["name"]), [])
                miss = [k for k in req if k not in args]
                res = {"error": f"missing required arguments: {miss}"} if miss else run_tool(tc["function"]["name"], args)
            log.append({"name": tc["function"]["name"], "args": args})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": json.dumps(res)})
    try:
        ok = bool(check(log, answer)) and bool(answer.strip()) and bad_json == 0
    except Exception:
        ok = False
    return {"ok": ok, "calls": log, "answer": answer, "bad_json": bad_json, "seconds": round(secs, 1), "tokens": toks}


# ---------------------------------------------------------------- coding part
CODE_TASKS = [
    ("c01_parse_price", "Write `parse_price(s: str) -> float | None` for Dutch Marktplaats price strings: "
     "'€ 1.450,-' -> 1450.0, '1.250,50' -> 1250.5, '€750' -> 750.0, 'Bieden' -> None, 'Gratis' -> 0.0, '' -> None.",
     """assert parse_price('€ 1.450,-') == 1450.0
assert parse_price('1.250,50') == 1250.5
assert parse_price('€750') == 750.0
assert parse_price('Bieden') is None
assert parse_price('Gratis') == 0.0
assert parse_price('') is None
assert parse_price('€ 12,95') == 12.95"""),
    ("c02_postcode", "Write `is_valid_postcode(s: str) -> bool` for Dutch postcodes: 4 digits (first not 0), optional "
     "single space, 2 letters (case-insensitive); the letter pairs SA, SD and SS are not used and are invalid.",
     """assert is_valid_postcode('3811 AB')
assert is_valid_postcode('3811ab')
assert not is_valid_postcode('0811 AB')
assert not is_valid_postcode('3811 SS')
assert not is_valid_postcode('3811  AB')
assert not is_valid_postcode('381 AB')
assert not is_valid_postcode('3811 A1')
assert is_valid_postcode('9999 ZZ')"""),
    ("c03_next_slot", "Write `next_pickup_slot(now: datetime.datetime) -> datetime.datetime`. Pickups are possible on "
     "weekdays (Mon-Fri) from 18:00 to 21:00 and on Saturday from 10:00 to 16:00, never on Sunday. Return the earliest "
     "start time on the hour or half hour (minute 0 or 30) that is >= now and inside a window (the slot start must be "
     "before the window's end). Seconds are 0 in the result. Import datetime yourself.",
     """import datetime as d
D=d.datetime
assert next_pickup_slot(D(2026,11,23,12,0)) == D(2026,11,23,18,0)
assert next_pickup_slot(D(2026,11,23,18,10)) == D(2026,11,23,18,30)
assert next_pickup_slot(D(2026,11,23,20,45)) == D(2026,11,24,18,0)
assert next_pickup_slot(D(2026,11,27,21,0)) == D(2026,11,28,10,0)
assert next_pickup_slot(D(2026,11,28,15,40)) == D(2026,11,30,18,0)
assert next_pickup_slot(D(2026,11,29,9,0)) == D(2026,11,30,18,0)
assert next_pickup_slot(D(2026,11,28,10,0)) == D(2026,11,28,10,0)"""),
    ("c04_dedupe", "Write `dedupe(listings: list[dict]) -> list[dict]`. Each dict has 'title', 'price' (int) and 'date' "
     "('YYYY-MM-DD'). Two listings are duplicates if their titles are equal after lowercasing, trimming and collapsing "
     "whitespace, and their prices are equal. Keep only the one with the earliest date. Keep the original order of the "
     "kept items. Don't modify the input.",
     """a=[{'title':'Gazelle  Arroyo','price':980,'date':'2026-11-05'},{'title':'Sparta','price':1100,'date':'2026-11-01'},
{'title':' gazelle arroyo ','price':980,'date':'2026-11-02'},{'title':'Gazelle Arroyo','price':950,'date':'2026-11-03'}]
import copy; b=copy.deepcopy(a)
r=dedupe(a)
assert a==b
assert [x['date'] for x in r]==['2026-11-01','2026-11-02','2026-11-03'], r
assert dedupe([])==[]"""),
    ("c05_fix_bug", "This function has bugs. Return the fixed version (same name and signature):\n```python\n"
     "def add_tag(tag, tags=[]):\n    # add tag once, return a NEW sorted list; tags is not modified\n"
     "    if tag not in tags:\n        tags.append(tag)\n    return sorted(tags)[1:]\n```",
     """x=['b']
assert add_tag('a', x)==['a','b']
assert x==['b']
assert add_tag('c')==['c']
assert add_tag('d')==['d']
assert add_tag('b',['b'])==['b']"""),
    ("c06_csv_totals", "Write `totals_by_payment(csv_text: str) -> dict[str, int]` for a CSV with a header "
     "`date,listing_id,price,payment`. Prices may be quoted and use a comma as thousands separator (\"1,150\"). "
     "Return the sum of price per payment method, lowercased.",
     """t='date,listing_id,price,payment\\n2026-10-03,K-11,640,cash\\n2026-10-12,K-14,"1,150",Tikkie\\n2026-10-28,K-19,890,CASH\\n'
assert totals_by_payment(t)=={'cash':1530,'tikkie':1150}
assert totals_by_payment('date,listing_id,price,payment\\n')=={}"""),
    ("c07_retry", "Write a function `retry(fn, attempts=3, exceptions=(Exception,), sleep=time.sleep, base_delay=1.0)` "
     "that calls fn() and returns its result. On one of `exceptions` it waits base_delay * 2**i seconds (i = 0, 1, ...) "
     "via the given sleep function and tries again, up to `attempts` calls in total; after the last failure it re-raises "
     "the last exception. Other exceptions propagate immediately without retry. Import time yourself.",
     """w=[]
n={'c':0}
def f():
    n['c']+=1
    if n['c']<3: raise ValueError('x')
    return 42
assert retry(f, sleep=w.append)==42 and w==[1.0,2.0]
w.clear(); n['c']=-10
try:
    retry(f, attempts=2, sleep=w.append); assert False
except ValueError: pass
assert w==[1.0]
def g(): raise KeyError('k')
w.clear()
try:
    retry(g, exceptions=(ValueError,), sleep=w.append); assert False
except KeyError: pass
assert w==[]"""),
    ("c08_extract_json", "Write `extract_json(text: str)` that finds the first JSON object in a model's reply and "
     "returns it parsed (dict). The reply may wrap it in ```json fences or plain ``` fences, or have prose before and "
     "after it; braces may appear inside JSON strings. Return None if there is no valid JSON object.",
     """assert extract_json('Sure! ```json\\n{"a": 1}\\n``` done')=={'a':1}
assert extract_json('result: {"t": "x}y", "n": {"m": [1,2]}} thanks')=={'t':'x}y','n':{'m':[1,2]}}
assert extract_json('no json here') is None
assert extract_json('```\\n{"k": true}\\n```')=={'k':True}
assert extract_json('bad {not json} then {"ok": 1}')=={'ok':1}"""),
]
SYS_C = ("You are a careful Python 3.12 programmer. Reply with one ```python code block containing the complete "
         "solution (functions and the imports they need), no tests, no example usage. Standard library only.")


def extract_code(text):
    # Code may itself contain ``` inside strings (c08), so try candidates and keep the first that compiles:
    # from the first ```python line to each later ``` line, longest first.
    m = re.search(r"```(?:python|py)?[ \t]*\n", text)
    if not m:
        return text
    body = text[m.end():]
    ends = [e.start() for e in re.finditer(r"^```[ \t]*$", body, re.M)] or [len(body)]
    for e in sorted(ends, reverse=True):
        try:
            compile(body[:e], "x", "exec"); return body[:e]
        except SyntaxError:
            pass
    return body[:ends[0]]


def run_tests(code, tests):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.py")
        open(p, "w").write(code + "\n\n" + tests + "\nprint('ALL_OK')\n")
        try:
            r = subprocess.run([sys.executable, "-I", p], capture_output=True, text=True, timeout=10, cwd=d)
            out = (r.stdout + r.stderr)[-1500:]
            return "ALL_OK" in r.stdout, out
        except subprocess.TimeoutExpired:
            return False, "timeout after 10 s"


def run_code_task(tid, prompt, tests):
    msgs = [{"role": "system", "content": SYS_C}, {"role": "user", "content": prompt}]
    res = {"attempts": [], "seconds": 0.0, "tokens": 0}
    for attempt in range(2):
        ch, usage, dt = chat(msgs)
        res["seconds"] += dt; res["tokens"] += usage.get("completion_tokens", 0)
        text = ch["message"].get("content") or ""
        code = extract_code(text)
        ok, out = run_tests(code, tests)
        res["attempts"].append({"ok": ok, "code": code, "raw": text, "test_output": out, "finish": ch.get("finish_reason"),
                                "reasoning_chars": len(ch["message"].get("reasoning_content") or ch["message"].get("reasoning") or "")})
        if ok:
            break
        msgs += [{"role": "assistant", "content": text},
                 {"role": "user", "content": "The tests failed:\n```\n" + out + "\n```\nFix it. Reply with the complete corrected code block."}]
    res["pass1"] = res["attempts"][0]["ok"]
    res["pass2"] = res["attempts"][-1]["ok"]
    res["seconds"] = round(res["seconds"], 1)
    return res


out = {"label": LABEL, "model": MODEL, "date": time.strftime("%Y-%m-%d %H:%M"), "tools": {}, "code": {}}
def runs(tasks):
    for t in tasks:
        if TASKS and t[0] not in TASKS:
            continue
        for k in range(REPEAT):
            yield (t[0] if REPEAT == 1 else f"{t[0]}#{k+1}"), t[1], t[2]


if ONLY != "code":
    for tid, prompt, check in runs(TOOL_TASKS):
        r = run_tool_task(tid, prompt, check)
        out["tools"][tid] = r
        print(f"{tid:22s} {'OK  ' if r['ok'] else 'FAIL'} {r['seconds']:6.1f}s bad_json={r['bad_json']} calls={[c['name'] for c in r['calls']]}", flush=True)
if ONLY != "tools":
    for tid, prompt, tests in runs(CODE_TASKS):
        r = run_code_task(tid, prompt, tests)
        out["code"][tid] = r
        print(f"{tid:22s} pass1={'OK  ' if r['pass1'] else 'FAIL'} pass2={'OK  ' if r['pass2'] else 'FAIL'} {r['seconds']:6.1f}s", flush=True)
t = out["tools"].values(); c = out["code"].values()
print(f"SUMMARY {LABEL}: tools {sum(x['ok'] for x in t)}/{len(out['tools'])}, "
      f"code pass@1 {sum(x['pass1'] for x in c)}/{len(out['code'])}, after 1 fix {sum(x['pass2'] for x in c)}/{len(out['code'])}, "
      f"time tools {sum(x['seconds'] for x in out['tools'].values()):.0f}s code {sum(x['seconds'] for x in out['code'].values()):.0f}s")
json.dump(out, open(os.path.join(HERE, f"results_{LABEL}.json"), "w"), ensure_ascii=False, indent=1)
