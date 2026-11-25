# One RTX 3090 + 128 GB RAM: Inkling 2 Mini vs Qwen3.8-27B vs Qwen3.8-Flash-Next 125B

We compared three local LLM setups on one home server, measuring speed, writing quality in Dutch and English, tool
calling and small coding tasks. The tests were run on 24–25 November 2026. All prompts, scripts and raw answers are
in [`tests/`](tests/), so you can rerun them on your own box.

**Short version:** the 125B MoE (Strata) and the dense 27B (llama.cpp) write the best Dutch and English. Inkling 2
Mini (HyperInkling) writes noticeably weaker Dutch. For small agents (tool calls, short Python functions) it is as
capable as the big models on our tasks and **7–10x faster**, with one weakness: it breaks the JSON when a tool
argument is an array of objects.

## The machine

| Part | |
|---|---|
| Workstation | Dell Precision T5810 (bought used) |
| CPU | Xeon E5-2699 v4, 22 cores (Broadwell, 2016) |
| RAM | 128 GB DDR4-2400 ECC RDIMM, 4 channels |
| GPU | RTX 3090 24 GB, PCIe 3.0 x16 |
| PSU | Dell 685 W. This limits the GPU to **250 W** under CPU+GPU load (300 W tripped it). |

## The three setups

| | **Inkling** | **q27** | **Strata** |
|---|---|---|---|
| Model | Inkling 2 Mini, W4A16 GPTQ (~16 GB) | Qwen3.8-27B dense, Unsloth UD-Q5_K_XL | Qwen3.8-Flash-Next 125B MoE, Unsloth UD-Q5_K_XL |
| Engine | [HyperInkling](https://github.com/Pento95/HyperInkling) 0.1.4 (patched vLLM, docker) | llama.cpp b11887 | Strata 0.1.60 (MoE experts in system RAM) |
| Drafting (speculative decoding) | DSpark | MTP draft head, n-max 2 | DFlash2 |
| Context | ~268K | 32K, KV q8_0 | 128K, KV int8 |
| GPU power limit | 250 W | 300 W (GPU-only load) | 250 W |
| Memory used | ~21 GB VRAM + 16 GB RAM prefix cache | 23.4 GB VRAM | most of the VRAM + ~111 GB RAM |

Only one of them runs at a time on the single GPU. All three run with their default thinking/reasoning on.

## Results at a glance

| Test | Inkling | q27 | Strata |
|---|---|---|---|
| **Speed, 1 request** (decode tok/s) | **138** (106 without DSpark) | 54 at 250 W, 64–66 at 300 W | 56 chat, 68 agent |
| **Speed, 6 requests in parallel** (total tok/s) | **~320–340** (~60 per stream) | not measured | not measured |
| **Writing, Dutch** (10 seller replies) | weakest: role mix-ups, unnatural phrasing, no counter-offer | **good**, natural and short | **good**, best scam warning |
| Median reply time, Dutch | **7 s** | 16 s (max 80 s) | 15 s |
| **Writing, English** (same 10, translated) | fluent, but 2 risky judgement errors | **good** | **good** |
| Median reply time, English | **5 s** | 8 s | 8 s |
| **Tool calling**, 10 multi-step tasks | 9/10 and 10/10 (two runs) | **10/10** | **10/10** |
| Nested array arguments (invoice task, all runs) | **3/7** (invalid JSON) | 6/6 | 6/6 |
| Time for the 10 tool tasks | **24 s** | 46 s | 107 s |
| **Coding**, 8 Python tasks, first try | 7/8 | 5/8 (3× no code: out of tokens while thinking) | 7/8, 8/8 after fixing our harness |
| Coding, after one fix round | **8/8** | 6/8 | **8/8** |
| Time for the 8 coding tasks | **~1–1.5 min** | ~20 min | ~10 min |

Speed numbers come from different benchmark runs; see [Speed](#speed) for how each one was measured. The writing
and agent tests used the same client and settings for all three.

## Speed

| | 1 request | 6 parallel requests | How it was measured |
|---|---|---|---|
| Inkling, DSpark on | 138.5 tok/s (145 per stream) | 318–329 total, 56–79 per stream | HyperInkling `scripts/quick_bench.py N 512`: short prompt, 512 tokens out, warm runs, 250 W |
| Inkling, DSpark off | 106 tok/s | 335–340 total, ~60 per stream | same |
| q27 | 53.9 tok/s at 250 W; 63.5–65.6 at 300 W | – | llama.cpp on our own code and prose prompts (MTP acceptance ~69%) |
| Strata | 55.9 chat / 67.9 agent | – | Strata's live tok/s on real chat and coding-agent sessions |

- DSpark speeds up one request by about 30%. With six requests the GPU is already at its 250 W cap, so drafting
  costs about 5%.
- HyperInkling's own README reports ~611 tok/s for 6 streams on a 3090 at 320 W with
  [gpu-unlock](https://github.com/zagitta/gpu-unlock). We used neither, so expect about half of that at 250 W.
- Startup time: Inkling ~70 s (~4 min on the first start, while it compiles kernels); Strata ~2 min.

## Writing test: Marktplaats seller replies

**Setup:** a private seller of used e-bikes on Marktplaats (the Dutch eBay) gets 10 buyer messages. The assistant
drafts replies for a human to approve. The system prompt gives two listings plus hidden rules: a minimum price,
pickup only, cash or Tikkie at pickup, never share the address before an appointment, and never use links or codes
from the buyer. The messages cover a battery question, a low bid (€900 for €1,450), a fair bid (€1,250), a question
with no answer in the listing (warranty), a shipping request, a fake payment-link scam, a "forward me the SMS code"
scam, defects, a buyer writing in the other language, and booking an appointment. One sample per prompt,
temperature 0.7. The answers were compared by hand.

| | Inkling | q27 | Strata |
|---|---|---|---|
| Kept every hidden rule (no address, phone, code or link; floor price never stated as the lowest) | yes | yes | yes |
| Invented facts (warranty, range in km) | no | no | no |
| **Dutch** language quality | stiff; often talks about "de verkoper" in the third person while speaking as the seller; wrong idiom ("dat laat hij na") | natural, short | natural, short |
| Dutch negotiation | turned down €1,250 without a counter-offer | countered €1,250 with €1,300 | offered €1,300 straight away to the €900 bid |
| **English** language quality | fluent, natural | natural, short | natural, short |
| English judgement errors | offered €1,300 to a buyer who had already agreed to €1,450; added "Here's a draft:" and a note revealing the floor price | offered €1,300 straight away to the €900 bid | same as q27 |

Example (Dutch, buyer offers €1,250 for the €1,450 bike and wants to come Saturday morning):

> **Inkling:** Mooie fiets vind ik ook. Ik kan niet op 1.250 ingaan. Zaterdag kan ik alleen ophalen na een vaste
> afspraak; het adres volgt dan. Zou je willen dat ik even kijk of er een tijdslot mogelijk is?
>
> **q27:** Dank je wel! 1.250 kan helaas niet, maar tegen 1.300 kan ik meegaan. Zaterdag 10:00-16:00 is ophalen
> mogelijk. Zou een tijdstip uitkomen?
>
> **Strata:** Bedankt! Voor 1.250 kan het helaas niet, maar ik kan je wel 1.300 aanbieden. Zaterdagochtend schikt,
> laten we via Marktplaats een exact moment afspreken tussen 10:00 en 12:00. Na de vaste afspraak volgt het
> ophaaladres. Betaling is bij ophalen, contant of via Tikkie.

All 60 answers: [`tests/writing_test/results_*.json`](tests/writing_test/). To judge the Dutch round yourself without
knowing which model wrote what, use the blind A/B/C sheet [`blind_nl.md`](tests/writing_test/blind_nl.md), then
check [`key.md`](tests/writing_test/key.md) for the key and our per-answer notes for both rounds.

**Lesson for the prompt itself:** both big models gave the floor price away to a low bid in English. A seller prompt
should say how to negotiate, for example "counter close to the asking price first".

## Tool calling and coding test (small agents)

[`tests/agent_test/run_agent_test.py`](tests/agent_test/run_agent_test.py) is one stdlib-only Python script
that scores itself.

**Tool calling:** 10 tasks against mock tools that really execute: a small listings database, weather, a file store,
a calendar and invoices. The model can take up to 8 rounds of calls. A task passes only with the right calls, valid
JSON arguments and a correct final answer.

| Task | What it tests | Inkling | q27 | Strata |
|---|---|---|---|---|
| t01 | single lookup | ✓ | ✓ | ✓ |
| t02 | enum filter (brand, price) | ✓ | ✓ | ✓ |
| t03 | chain: search, then details | ✓ | ✓ | ✓ |
| t04 | two calls in parallel (weather in 2 cities, "tomorrow") | ✓ | ✓ | ✓ |
| t05 | recover from a not-found error (mistyped id) | ✓ | ✓ | ✓ |
| t06 | knowledge question, no tool needed | ✓ | ✓ | ✓ |
| t07 | list files, read a CSV, sum it | ✓ | ✓ | ✓ |
| t08 | date maths ("Saturday 11:00 for one hour" → 2026-11-28 11:00–12:00) | ✓ | ✓ | ✓ |
| t09 | nested arguments: invoice with an array of 2 line items, 0% VAT | **3/7 runs** | 6/6 | 6/6 |
| t10 | trap: the bike is sold, so the default "available" search finds nothing | ✓ | ✓ | ✓ |

Inkling's t09 failure is systematic: it drops the closing `]` of the array (`"items":[{…},{…,"unit_price":35}}`).
After the error message it usually sends the same broken call again and runs out of rounds. Flat arguments were
always fine. It also tends to make extra read calls it doesn't need, such as reading notes before writing an invoice.

**Coding:** 8 small Python tasks with unit tests: a Dutch price parser, a postcode validator, the next pickup slot
from opening hours, removing duplicate listings, fixing a buggy function, CSV totals, a retry wrapper with backoff,
and extracting JSON from a chatty model reply. If the tests fail, the model gets the error output once and tries
again, as a minimal agent loop would.

| | First try | After one fix | Notes |
|---|---|---|---|
| Inkling | 7/8 (two full runs) | 8/8 every run | small slips, such as `datetime.datetime` after `from datetime import datetime`; ~1–1.5 min in total |
| q27, 8K tokens | 5/8 | 6/8 | all failures produced **no code at all**: it used the whole budget on thinking |
| q27, 32K tokens (3 hard tasks, 2 runs each) | 3/6 | 6/6 | the price parser still ran out of tokens twice, after 17–18 min of thinking |
| Strata | 8/8 | 8/8 | ~10 min in total |

The first harness version cut off code that contained `` ``` `` inside strings, which caused two false failures. The
fixed harness is the one in this repo, and the reruns are in `results_r2_*.json`. Always check your harness with
reference solutions before blaming the model.

## What we take from this

- **For Dutch (or English) text that customers will read:** use q27 or Strata.
- **For small agents and scripts:** Inkling is fast and good, if your tool schemas stay flat (no arrays of objects),
  or your agent loop validates and repairs JSON arguments before running a call.
- **q27 with thinking on** is a poor fit for agent loops: it overthinks easy tasks. Thinking off or a capped
  budget is the next thing to test.
- HyperInkling is young software (version 0.1.4, a handful of contributors), so we run it as an opt-in mode, not as
  the default.

## Caveats

- Small samples: 10 writing prompts with one answer each, 10 tool tasks, and 8 coding tasks with 1–7 runs each.
- The writing quality was judged by hand, by us.
- Speed numbers for q27 and Strata come from earlier runs with their own prompts. The writing and agent test times
  are directly comparable.
- Our system prompt said "say the seller will check it", which may have pushed Inkling towards the third person.

## Rerun it

Start a model on an OpenAI-compatible endpoint (port 8080 here), then:

```bash
python3 tests/writing_test/run_writing_test.py nl_mymodel 8080 "" prompts_nl.json
python3 tests/writing_test/run_writing_test.py en_mymodel 8080 "" prompts_en.json
python3 tests/agent_test/run_agent_test.py mymodel 8080
TASKS=t09_nested_args REPEAT=5 python3 tests/agent_test/run_agent_test.py mymodel_t09 8080 only=tools
```

Both scripts use only the Python standard library. The agent test runs model-written code in a subprocess
(`python3 -I`, 10 s timeout, temporary directory). That code is not sandboxed further, so run it on a machine where
that is acceptable.

## License

MIT, see [LICENSE](LICENSE). Model outputs in `tests/` were generated by the models named above.
