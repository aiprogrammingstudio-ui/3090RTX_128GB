# One RTX 3090 + 128 GB RAM: six local LLM setups compared

Qwen3.8-Flash-Next 125B MoE (Strata, Q4 and Q5), Qwen3.8-27B (HyperQwen, llama.cpp, ninfer) and Inkling 2 Mini
(HyperInkling), all on one 2016 workstation with one RTX 3090. We measured speed (1–6 parallel requests, long-prompt
prefill), writing quality in Dutch and English, tool calling and small coding tasks. All prompts, scripts and raw answers are
in [`tests/`](tests/), so you can rerun them on your own box.

**What changed on 26 November 2026:** the GPU now has its own **1400 W server PSU** and runs at **370 W** (it was
capped at 250 W). **gpu-unlock** is active. We added **HyperQwen** (the 27B in 4-bit on patched vLLM) and the
**Strata UD-Q4_K_XL** quant next to Q5, then reran every speed test. The first version of this page (24–25 November,
250 W, three setups) is in the git history. Its quality results are still here and are marked "250 W".

**What changed on 27 November 2026:** the kernel option **`iommu=pt`** (prefill +7–15% on Strata and Inkling, decode the
same), a full speed rerun of every setup, first numbers for HyperQwen's **150K and 240K** profiles, and a list of Strata
tuning attempts that did *not* help on this machine, with the RAM bandwidth Strata really uses
([27 November](#iommupt-and-a-full-rerun-27-november), [tuning](#tuning-strata-on-this-machine-what-did-not-help)).

**Short version**

- **Best all-rounder: HyperQwen.** It runs the same Qwen3.8-27B as llama.cpp, at **129 tok/s** with one request and
  **371 tok/s** in total with 6 (2.2x and 3.6x llama.cpp). Its writing and tool-calling scores match the Q5 llama.cpp run.
- **Fastest: Inkling 2 Mini** (HyperInkling): 145 tok/s single, 402 total, and 4.6K tok/s prefill. It is good for
  small agents. Its Dutch is weaker, and it breaks JSON when a tool argument is an array of objects.
- **Biggest model: Strata 125B MoE**, with the experts in system RAM. UD-Q4_K_XL is **+18% faster** than UD-Q5_K_XL
  (80 against 67 tok/s) and uses 20 GB less RAM. It writes as well as the 27B and was the best at coding on our tasks.
- **Best for many users at once: HyperQwen 150K** (MTP drafting): 402 tok/s in total with 6 requests, 98 with one.
- **Software beat hardware:** on the same GPU and the same 27B model, HyperQwen and ninfer are 2–2.5x faster than llama.cpp.

## The machine

| Part | |
|---|---|
| Workstation | Dell Precision T5810 (bought used) |
| CPU | Xeon E5-2699 v4, 22 cores (Broadwell, 2016) |
| RAM | 128 GB DDR4-2400 ECC RDIMM, 4 channels (~77 GB/s) |
| GPU | RTX 3090 24 GB (not Ti), PCIe 3.0 x16, no Resizable BAR, headless |
| GPU power | **370 W limit** (the card's default; it allows 100–390 W) |
| PSU | Dell 685 W for the board, CPU and the 75 W PCIe slot; a **1400 W server PSU with a breakout board** for the card's two 8-pin connectors |
| GPU firmware patch | gpu-unlock 2.0.0 by Zagitta (raises the FP16/BF16 tensor-core rate with fp32 accumulate) |
| OS / driver | Ubuntu 24.04, kernel 6.8, NVIDIA 595.99 / CUDA 13.2; kernel option `iommu=pt` since 27 November |

**About the PSU:** the old 685 W PSU tripped at 300 W of GPU load under CPU load, so the card ran at 250 W with a 1,500 MHz
clock lock. A used server PSU now powers the 8-pins: each 8-pin socket gets its own 6-pin cable from the breakout
board, both PSUs plug into the same power strip, and the server PSU is switched on before the workstation. Two
30-minute load tests (Strata, 4 parallel generations plus CPU load) passed. At 370 W the card averaged 328 W and peaked
at 357 W, at 73–76 °C. At 390 W it gained only ~1.5% clock and began thermal throttling at 80 °C, so 370 W is our default.

## The setups

Only one runs at a time on the single GPU, on port 8080. All run with thinking/reasoning on (the server default).

| | Engine | Model / quant | Drafting (speculative decoding) | Context |
|---|---|---|---|---|
| **HyperQwen** | HyperQwen (patched vLLM 0.33, docker, image `ghcr.io/syv-ai/hyperqwen`) | Qwen3.8-27B W4A16 AutoRound, `-fast` variant (4-bit LM head) | DFlash2 (MTP in the 150K profile) | 64K; also 150K (fp8/int8 KV) and 240K (KVarN 4/2-bit KV, 2 slots) |
| **Inkling** | [HyperInkling](https://github.com/Pento95/HyperInkling) 0.1.4 (patched vLLM, docker) | Inkling 2 Mini, W4A16 GPTQ (~16 GB) | DSpark | ~268K |
| **q27** | llama.cpp b11887 | Qwen3.8-27B dense, Unsloth UD-Q5_K_XL, KV q8_0, 4 slots | MTP draft head, n-max 2 | 32K |
| **ninfer** | ninfer-3090 v0.16 | Qwen3.8-27B, its own 4/6-bit format (17.7 GiB) | DFlash2, K=7 | 237K |
| **Strata Q5** | Strata 0.2.22 / engine 0.1.69 (MoE experts in system RAM) | Qwen3.8-Flash-Next 125B MoE, Unsloth UD-Q5_K_XL | DFlash2 | 256K, int8 KV (32K in VRAM, rest in RAM) |
| **Strata Q4** | same | same model, Unsloth **UD-Q4_K_XL** | DFlash2 | same |

ninfer and HyperInkling are young projects (a few contributors, frequent releases). We run them as opt-in modes, not
as the default. We have since removed ninfer from the machine to free disk space, so its numbers below are not rerun.

## Results at a glance (370 W, gpu-unlock)

| Setup | Decode, 1 request (tok/s) | Total, 4–6 requests | Prefill 8K / 30K (tok/s) | Tool calls (10 tasks) | Coding (8 tasks, 1st try / after fix) | Writing NL / EN |
|---|---|---|---|---|---|---|
| **HyperQwen** | **129** | **371** (6) | 1,880 / 1,720 | 10/10, nested args 5/5 | 3–5/8 / 4–6/8 ¹ | ≈ q27 / good |
| **Inkling** | **145** | **402** (6) | **4,632 / 3,993** | 9–10/10, nested args **3/7** ² | 7/8 / **8/8** ² | weakest / fluent, 2 judgement errors ² |
| **q27** | 58 | 132 (4) | 1,128 / 1,098 | 10/10 ² | 5/8 / 6/8 ¹ ² | **good / good** ² |
| **ninfer** | 102 prose / 147 code ³ | one lane only | 2,818 / 2,557 | not tested | not tested | not tested |
| **Strata Q5** | 67 | 57 (4) ⁴ | 948 / 2,935 | 10/10 | **8/8 / 8/8** ² | **good / good** ² |
| **Strata Q4** | **80** | 69 (4) ⁴ | 1,228 / 3,102 | 10/10 | not tested | not tested |
| **HyperQwen 150K** ⁵ | 98 | **402** (6) | 1,771 / 1,594 | not tested | not tested | not tested |
| **HyperQwen 240K** ⁵ | 117 | 208 (4; 2 slots) | 1,745 / 1,597 | not tested | not tested | not tested |

¹ All failures were **no code at all**: the model used the whole 8,000-token budget for thinking.
² Measured at 250 W (24–25 November). Scores don't depend on power, but times do.
³ Prose at 370 W. Code at 300 W with a clock lock (2026-11-19, other prompts).
⁴ Strata's DFlash2 serves one request at a time, so parallel requests don't add throughput.
⁵ First measured on 27 November, with `iommu=pt`. The other rows are from before `iommu=pt`; the rerun is
[below](#iommupt-and-a-full-rerun-27-november).

## Speed

### Method

[`tests/speed/concurrency_sweep.py`](tests/speed/concurrency_sweep.py) (decode) and
[`tests/speed/prefill_bench.py`](tests/speed/prefill_bench.py) (prefill) run on the GPU box against
`127.0.0.1:8080`, with the same scripts and prompts for every engine.

- **Decode:** temperature 0, `ignore_eos`, 512 tokens per request, N streams started together, one warm-up.
  **Total** = all tokens ÷ wall time of the whole run (including time to first token and the tail when fast streams
  have finished). **Per stream** = what one chat sees. The prompts are free prose in Italian and English, the same as
  HyperInkling's `scripts/quick_bench.py`.
- **Prefill:** English filler text that starts with a random nonce (so no prefix cache), `max_tokens` 1, two runs (second
  shown). tok/s = prompt tokens ÷ time until the reply is done.

### Decode by number of parallel requests (370 W, before gpu-unlock), total tok/s

| Setup | 1 | 2 | 3 | 4 | 5 | 6 | At 250 W (1 / 2 / 3 / 4 / 5 / 6) |
|---|---|---|---|---|---|---|---|
| **HyperQwen** | **128** | **228** | 245 | **289** | 242 | 288 | 110 / 180 / 202 / 238 / 204 / 243 |
| Inkling | 123 | 210 | 281 | 318 | 337 | **368** | 122 / 186 / 252 / 276 / – / 340 |
| q27 | 59 | 80 | 109 | 131 | 100 | 105 | 54 / 71 / 100 / 118 / 95 / 99 (300 W + clock lock) |
| ninfer | 102 | 102 | – | – | – | – | one lane: a second request waits |
| Strata Q5 (128K) | 66 | 57 | 59 | 56 | – | – | one request at a time |

- Per stream at 6 requests: HyperQwen 50–68, Inkling 64–92, q27 28–43 tok/s. With q27, the 5th and 6th requests
  wait ~17 s for one of llama.cpp's 4 slots.
- **What the bigger PSU gave:** HyperQwen +17–21% (it was power-capped at 250 W), q27 +6–11% (the clock lock went away),
  Inkling +0% single and +8–15% at 3–6 requests (single-stream Inkling was not power-limited).
- HyperQwen is slower at 5 requests than at 4, in repeated runs. We think this comes from DFlash2's verify batch
  sizes but have not checked. 4 or 6 parallel requests are the better points.
- GPU during the sweeps: 316–357 W average, SM clock ~1,500–1,900 MHz (at 250 W it was 1,000–1,400 MHz).

### gpu-unlock: before → after (370 W both)

| Setup | Prefill 8K | Prefill 30K | Prefill 60K | Decode 1 / 4 / 6 requests (total) |
|---|---|---|---|---|
| **HyperQwen** | 1,268 → **1,880** (+48%) | 1,151 → **1,720** (+49%) | 1,021 → **1,522** (+49%) | 128 → 129 / 289 → **361** (+25%) / 288 → **371** (+29%) |
| **Inkling** | 3,467 → **4,632** (+34%) | 3,177 → **3,993** (+26%) | 2,671 → **3,590** (+34%) | 123 → 145 / 318 → 314 / 368 → **402** (+9%) |
| Strata Q5 | 949 → 948 | 2,656 → 2,935 (+11%) | 2,636 → 2,854 (+8%) | 66 → 65 |
| q27 | 1,123 → 1,128 | 1,067 → 1,098 | – (32K context) | 59 → 58 / 131 → 132 / 105 → 104 |

- As gpu-unlock's README says, the FP16 paths gain and the int8 paths don't. The vLLM engines (W4A16 Marlin kernels in
  fp16) read long prompts 26–49% faster. llama.cpp's quantized matmuls gain nothing.
- **HyperQwen's multi-request decode also gained +25–29%.** With several streams, the speculative-decoding verify steps
  become real fp16 GEMMs rather than memory-bound work. Single-stream decode stays memory-bound and is unchanged.
- **Waiting for a 30K-token prompt** (a long coding-assistant session): q27 28 s, HyperQwen 18 s, Strata 10 s, Inkling 8.5 s.
- Quality after the unlock: HyperQwen's writing and tool calls were rerun and unchanged, with coherent output in both
  languages and valid JSON. We saw no Xid errors in the kernel log.

### Strata: UD-Q4_K_XL vs UD-Q5_K_XL

Same session and settings: 256K context, int8 KV (32K in VRAM), DFlash2, vision on, the same tuning args
(`--prefill auto:32768 --pcie-frac 0.00 --adapt-every 1 --adapt-swaps 160 --adapt-decay 0.97`), and a fresh start before each set.

| | UD-Q5_K_XL | UD-Q4_K_XL | Change |
|---|---|---|---|
| Decode, 1 request (3 runs) | 66.4 / 69.2 / 66.2, mean 67.3 | 80.3 / 79.5 / 78.6, mean **79.5** | **+18%** |
| 2 / 4 requests, total | 59.0 / 56.6 | 71.3 / 69.0 | +21% / +22% |
| Prefill 8K | 952 | 1,228 | **+29%** |
| Prefill 30K | 2,951 | 3,102 | +5% |
| Tool calls (10 tasks) | 10/10, 90 s | 10/10, 0 invalid JSON, 76 s | |
| RAM used after load | 104 of 125 GB | 84 of 125 GB | −20 GB |
| Size on disk | 158 GB | 111 GB | |

- Most experts run from system RAM on the Xeon, so RAM bandwidth sets the speed. Smaller experts mean less RAM
  traffic per token, and more of them fit in the VRAM cache.
- On quality we only have Strata's own figures so far: the top token matches Q8_0 in 93.1% of positions for Q4 and
  94.6% for Q5 (mean KL 0.056 vs 0.038). **We have not yet compared answer quality on our own tasks.**
- The Strata engine update 0.1.60 → 0.1.69 gave **no real decode gain** for Q5 on this machine. It was +6% just after a
  start, then the same once warm (65.0–65.3 vs 65.0 tok/s by the third run). The release notes' 3090 gains were
  measured on smaller quants that keep more on the GPU.

### `iommu=pt` and a full rerun (27 November)

The kernel's IOMMU translated every DMA transfer (all 54 IOMMU groups were `DMA-FQ`). Strata's docs say pinned
RAM↔GPU copies ran slower that way. We booted once with `iommu=pt` (pass-through: the IOMMU stays on, host devices
skip translation), using a one-time GRUB entry so that a power cycle would fall back to the old boot. Then we made it
permanent. gpu-unlock kept working, and there were no Xid errors. Every setup was then started fresh and measured with
the same scripts; ninfer is no longer installed.

Decode, total tok/s, before → after (1 request: mean of 3 runs):

| Setup | 1 request | 2 | 4 | 6 |
|---|---|---|---|---|
| HyperQwen 64K | 129 → 129 | 228 ¹ → 234 | 361 → 358 | 371 → 365 |
| HyperQwen 150K (MTP) | new: **98** | 184 | 334 | **402** |
| HyperQwen 240K (KVarN, 2 slots) | new: **117** | 127 ² | 208 | – |
| q27 (llama.cpp) | 58 → 57 | – | 132 → 130 | 104 → 103 |
| Inkling | 145 → 142 | 210 ¹ → 218 | 314 → 299 | 402 → 387 |
| Strata Q5 128K / 256K | 67 → 68 / 67 → 67 | 59 → 59 / 59 → 60 | 57 → 56 / 57 → 56 | – |
| Strata Q4 128K / 256K | new: 82 / 80 → 81 | 72 / 71 → 71 | 71 / 69 → 68 | – |

¹ Before gpu-unlock (no later number). ² The second request waited 3.5 s for a slot.

Prefill, tok/s, before → after:

| Setup | 8K | 30K | 60K |
|---|---|---|---|
| HyperQwen 64K | 1,880 → 1,831 | 1,720 → 1,675 | 1,522 → 1,491 |
| HyperQwen 150K / 240K | new: 1,771 / 1,745 | 1,594 / 1,597 | 1,389 / 1,423 |
| q27 | 1,128 → 1,102 | 1,098 → 1,075 | – (32K context) |
| **Inkling** | 4,632 → **5,242 (+13%)** | 3,993 → **4,577 (+15%)** | 3,590 → 3,794 (+6%) |
| **Strata Q5** (256K) | 948 → **1,015 (+7%)** | 2,939 → 3,008 (+2%) | – → 2,942 |
| **Strata Q4** (256K) | 1,220 → **1,312 (+8%)** | 3,090 → 3,086 | – → 3,110 |

- **Who gains:** the engines that copy a lot between RAM and GPU while reading a prompt. Strata streams the experts the
  card doesn't hold; Inkling keeps a 16 GB prompt cache in RAM. During Strata's prefill, PCIe bursts now reach ~12 GB/s
  (8.7 before). HyperQwen and llama.cpp keep everything in VRAM and gain nothing; HyperQwen's −2–3% is one run.
- **Decode didn't change** for any setup (within ±3%; Inkling's single-request runs alone spread 132–150).
- **HyperQwen 150K is the best multi-user setup** (402 tok/s total at 6 requests), at ~25% less single-request speed
  than 64K. 240K is faster for one request but has only 2 slots. Long-context quality is not tested yet.
- Strata Q4 runs at the same speed with 128K and 256K context; the larger context costs only RAM.

### Tuning Strata on this machine: what did not help

After readers suggested CPU-side tuning (one gained ~10% decode on a DeepSeek MoE, whose RAM delivered only 33 of 90 GB/s),
we tried everything we could find on Strata Q4 (256K). Each variant was a fresh start plus 3 × 512 tokens; runs vary by about ±3 tok/s.

| Variant | Decode, mean tok/s |
|---|---|
| Baseline | 80.8 |
| Huge pages for the 71.7 GiB expert arena (`STRATA_ARENA_THP=1`) | 79.3 |
| `--pool-workers` 21 / 16 / 12 (default 20 on 22 cores) | 81.7 / 80.1 / ~74 |
| `--pool-tasks 126` (default 63) / `--aux-cpus auto` / `--host-core sibling` | 79.8 / 81.0 / 79.2 |
| GPU at 390 W instead of 370 W | 80.4 |
| More VRAM for experts (`--kv-resident 20480`, 5,350 instead of 5,299 expert slots) | 80.7 |
| DFlash2 `--spec` 4 / 5 / 8 (default 6, `--draft-conf 0.7`) | 80.8 / 82.3 / 78.5 |
| `--draft-conf` 0.5 / 0.85 | **75.7** / 80.5 |

- **RAM bandwidth actually used** during decode, from the memory controllers' counters (`perf stat` with
  `uncore_imc_*/cas_count_read/`, run as root): **24.6 GB/s** of the theoretical 76.8, with all four channels equal.
- So the RAM has room to spare and the CPU pool is not on the critical path: 16 workers are as fast as 20, and huge pages
  change nothing. The GPU draws 340–350 W during single-request decode, and at 390 W its clock barely moves
  (~1,890 → 1,905 MHz). **On this box Strata Q4 decode is limited by the GPU side.** Q5 (more experts in RAM) may behave
  differently; we haven't tested it.
- The DFlash2 defaults are right: a lower `--draft-conf` drafts 50% more tokens but gets few more accepted, and the GPU pays
  for checking the rejected ones.
- Long answers are faster than these 512-token runs: 2,048 tokens gave 86–87 tok/s, because Strata keeps adapting which
  experts it holds in VRAM.
- If you script Strata's launcher: `strata launch` keeps the flags in its own launch preset and keeps the first copy of a
  flag, so a flag you add once sticks there until you remove it.

## Inkling: exact configuration and the 600+ tok/s reports

We installed HyperInkling exactly as its README describes (docker compose, prebuilt image). Changes from the defaults
are in **bold**.

**Software**

| | Ours |
|---|---|
| HyperInkling | 0.1.4, git `14f2283` (2026-11-24) |
| Image | `ghcr.io/pento95/hyperinkling:0.1.4`, digest `sha256:0cdd2f1b788f…bfb42721` |
| Checkpoint | `Pentium95/Inkling-2-Mini-W4A16-g128-gptq` (INT4 experts, INT8 attention / LM head) |
| Host OS | Ubuntu 24.04.5, kernel 6.8.0-149 (HyperInkling was tested on Fedora 44) |
| NVIDIA driver / CUDA | 595.99.02 / 13.2 (driver 580+ is required) |
| Docker / Compose | 29.1.3 / 2.40.3, NVIDIA Container Toolkit from NVIDIA's apt repository |
| GPU | RTX 3090 (not Ti), VBIOS 94.02.42.80.88, headless (no display attached), persistence mode on |
| GPU link | PCIe 3.0 x16 (the T5810 has no PCIe 4.0) |
| GPU power limit | **250 W** in the first round; **370 W** since 25 November (board maximum 390 W) |
| gpu-unlock | not used in the first round; **2.0.0** since 25 November |

**Server settings** (`.env` plus the defaults of `start.sh`)

| Setting | Value | Note |
|---|---|---|
| `SPEC` | `dspark` (default) | `num_speculative_tokens` 7, `SPEC_K=[[1,2,4],[3,8,3]]`, `SPEC_DRAFT=probabilistic` |
| `HYPERINKLING_SPEC_ADAPTIVE` | `2,4,7` (default) | verify length chosen per step (replaces `SPEC_K` while on) |
| `HYPERINKLING_LOOKUP` | 1 (default) | drafts copied from the request's own context on a match of 8+ tokens |
| `MAX_SEQS` | 8 (default) | |
| `MAX_LEN` | auto (default) | served as 268,544 tokens |
| `NBT` (prefill chunk) | 2048 (default) | `LONG_PREFILL` 1024 |
| `KV_DTYPE` | fp8 (default) | E4M3, emulated on sm86 |
| `GPU_UTIL` | 0.95 (default) | ~21 GB VRAM in use |
| `ASYNC` | 1 (default) | async scheduling |
| `WARMUP` | 1 (default) | |
| `KV_OFFLOAD_GB` | **16** | default "auto" = min(0.6 × RAM − 8, 36) = 36 GB of RAM for the CPU prefix cache; we keep it smaller |
| `SHM_GB` | **24** | default 48 |
| `BIND`, `PORT` | **127.0.0.1, 8080** | local only; reached over an SSH tunnel |
| compose `restart` | **"no"** (override file) | default `unless-stopped` would take the GPU on every boot |

**How our numbers compare with the published ones**

| | HyperInkling README | HyperInkling field report | Ours, round 1 | **Ours, now** |
|---|---|---|---|---|
| GPU | RTX 3090 Ti | RTX 3090 | RTX 3090 | RTX 3090 |
| Power | 350 W, undervolted | 320 W | 250 W | **370 W** |
| gpu-unlock | yes | yes | no | **yes** |
| Version | 0.1.x | 0.1.2 | 0.1.4 | 0.1.4 |
| Benchmark | `bench/context_bench.sh` | same | `quick_bench.py 6 512` | `concurrency_sweep.py` (same prompts and method) |
| Prompt | 8k or 32k tokens (AA-LCR documents), greedy | same | short one-line prompts, greedy, `ignore_eos` | same as round 1 |
| What "aggregate" counts | decode only, **while all 6 requests generate** | same | total tokens ÷ wall time of the whole run | same as round 1 |
| 1 request, DSpark | 267 (8k) / 188 (32k) | 268 / 180 | 138 | **145** |
| 1 request, no DSpark | 131 / 124 | 123 / 116 | 106 | not rerun |
| 6 requests, DSpark, aggregate | **686 / 646** | **611 / 590** | 318–329 | **402** |
| 6 requests, DSpark, per request | 114 / 108 | 102 / 98 | 56–79 | 64–92 (before unlock) |
| 6 requests, no DSpark, aggregate | 407 / 350 | 381 / 326 | 335–340 | not rerun |

More power and gpu-unlock closed only part of the gap (6 requests: 329 → 402). What still explains the rest, most
important first:

1. **The measurement.** Our script divides by the wall time of the whole run, so the tail counts too. With DSpark the
   streams run at different speeds, and the fastest ones finish early. The published numbers count only the window in
   which all six requests generate. Our numbers are closer to what a user of six chats sees.
2. **The text.** DSpark gains most on text that repeats the prompt (summaries of a long document, code) and least on
   free prose. Our prompts ask for free prose, while the published runs ask for summaries of 8k–32k documents. On our
   tool and coding tasks, DSpark gave 1.6–1.8x (see below), against +15–30% on prose.
3. **3090 Ti vs 3090:** about 7% more memory bandwidth (1,008 vs 936 GB/s) and more SMs on the Ti.
4. **Power, before:** at 250 W the card sat at its cap with the SM clock at 1,245–1,500 MHz. At 370 W it runs at ~1,500–1,900 MHz.

We have not yet run `bench/context_bench.sh` (the published method, which needs the AA-LCR dataset).

**DSpark on vs off** (250 W, round 1)

| Requests | DSpark on: total (per stream) | DSpark off: total (per stream) | DSpark gain |
|---|---|---|---|
| 1 | 122 (129) | 106 (110) | +15% |
| 2 | 186 (99–106) | 175 (93) | +6% |
| 3 | 252 (90–113) | 228 (81) | +11% |
| 4 | 276 (75–97) | 266 (71) | +4% |
| 6 | 340 (60–72) | 335 (59) | +1% |

At the 250 W cap, drafting took power that batching would otherwise use. DSpark pays much more on tool calls and code.
The same agent test, run twice with DSpark on and twice with `SPEC=off`, gave the same scores but:

| Inkling, 250 W | Tool tasks: tok/s, time | Coding tasks: tok/s, time |
|---|---|---|
| DSpark on | 138–176 tok/s, 23–28 s | **186–203 tok/s**, 65–80 s |
| DSpark off | 92–95 tok/s, 36–49 s | **106 tok/s**, 153–190 s |

That is ~1.8x on code and ~1.6x on tool tasks (completion tokens ÷ wall time, including prefill and tool round trips).
Raw results: `tests/agent_test/results_ds_*.json`.

**To compare your 3090 / 3090 Ti setup with ours:** run `python3 tests/speed/concurrency_sweep.py <model> 512 1,2,3,4,6`
and `python3 tests/speed/prefill_bench.py <model> 8,30 2` on the GPU box (run each twice; the first run compiles
kernels). Report the GPU model, power limit, gpu-unlock yes/no, engine version, driver, and the SM clock under load (the
sweep prints it).

## Writing test: Marktplaats seller replies

**Setup:** a private seller of used e-bikes on Marktplaats (the Dutch eBay) gets 10 buyer messages. The assistant
drafts replies for a human to approve. The system prompt gives two listings plus hidden rules: a minimum price,
pickup only, cash or Tikkie at pickup, never share the address before an appointment, and never use links or codes
from the buyer. The messages cover a battery question, a low bid (€900 for €1,450), a fair bid (€1,250), a question
with no answer in the listing (warranty), a shipping request, a fake payment-link scam, a "forward me the SMS code"
scam, defects, a buyer writing in the other language, and booking an appointment. One sample per prompt,
temperature 0.7. The answers were compared by hand.

| | Inkling (250 W) | q27 (300 W) | Strata Q5 (250 W) | HyperQwen (250 W and 370 W + unlock) |
|---|---|---|---|---|
| Kept every hidden rule (no address, phone, code or link; nothing invented) | yes | yes | yes | yes |
| **Dutch** language quality | stiff; often talks about "de verkoper" in the third person while speaking as the seller; wrong idiom ("dat laat hij na") | natural, short | natural, short | natural, short; one or two clumsier phrases in 10 |
| Dutch negotiation | turned down €1,250 without a counter-offer | countered €1,250 with €1,300 | offered €1,300 straight away to the €900 bid | countered at €1,400 (first run) |
| **English** language quality | fluent, natural | natural, short | natural, short | fluent |
| English judgement errors | offered €1,300 to a buyer who had already agreed to €1,450; added "Here's a draft:" and a note revealing the floor price | offered €1,300 straight away to the €900 bid | same as q27 | "1,300 is the lowest I can do" (floor leak) |
| Median reply time, NL / EN | **7 s / 5 s** | 16 s / 8 s | 15 s / 8 s | 7.4 s / 6.0 s (250 W), **6.2 s / 4.3 s** (370 W) |

**Floor-price leak, repeated:** we ran the two price prompts 5 times each in both languages (20 replies per model).
HyperQwen said the floor outright ("lowest", "minimum", "can't go below") in ~5 of 20 replies, and q27 in ~4 of 20.
That is the same rate within noise, so the leak comes from the model and the prompt, not from the 4-bit quant. A seller
prompt should say how to negotiate ("counter close to the asking price first", never "lowest" or "minimum").

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

All answers: [`tests/writing_test/results_*.json`](tests/writing_test/). To judge the Dutch round yourself without
knowing which model wrote what, use the blind A/B/C sheet [`blind_nl.md`](tests/writing_test/blind_nl.md) (Inkling,
q27, Strata). Then check [`key.md`](tests/writing_test/key.md) for the key and our per-answer notes, HyperQwen included.

## Tool calling and coding test (small agents)

[`tests/agent_test/run_agent_test.py`](tests/agent_test/run_agent_test.py) is one stdlib-only Python script
that scores itself.

**Tool calling:** 10 tasks against mock tools that really execute: a small listings database, weather, a file store,
a calendar and invoices. The model can take up to 8 rounds of calls. A task passes only with the right calls, valid
JSON arguments and a correct final answer.

| Task | What it tests | Inkling | q27 | Strata Q5 | Strata Q4 | HyperQwen |
|---|---|---|---|---|---|---|
| t01 | single lookup | ✓ | ✓ | ✓ | ✓ | ✓ |
| t02 | enum filter (brand, price) | ✓ | ✓ | ✓ | ✓ | ✓ ¹ |
| t03 | chain: search, then details | ✓ | ✓ | ✓ | ✓ | ✓ |
| t04 | two calls in parallel (weather in 2 cities, "tomorrow") | ✓ | ✓ | ✓ | ✓ | ✓ |
| t05 | recover from a not-found error (mistyped id) | ✓ | ✓ | ✓ | ✓ | ✓ |
| t06 | knowledge question, no tool needed | ✓ | ✓ | ✓ | ✓ | ✓ |
| t07 | list files, read a CSV, sum it | ✓ | ✓ | ✓ | ✓ | ✓ |
| t08 | date maths ("Saturday 11:00 for one hour" → 2026-11-28 11:00–12:00) | ✓ | ✓ | ✓ | ✓ | ✓ |
| t09 | nested arguments: invoice with an array of 2 line items, 0% VAT | **3/7 runs** | 6/6 | 6/6 | ✓ | 10/10 |
| t10 | trap: the bike is sold, so the default "available" search finds nothing | ✓ | ✓ | ✓ | ✓ | ✓ |
| | **Time for the 10 tasks** | **24 s** (250 W) | 46 s (300 W) | 107 s (250 W), 90 s (370 W) | 76 s (370 W) | 26 s (250 W), 14 s (370 W) ¹ |

¹ After gpu-unlock, t02 once repeated the same search 186 times in one turn (the answer was still right). That run took
60 s; the other 9 tasks took 14 s. In 5 reruns, t02 made 1–2 calls each, so we count it as a one-off sampling loop.

Inkling's t09 failure is systematic: it drops the closing `]` of the array (`"items":[{…},{…,"unit_price":35}}`).
After the error message it usually sends the same broken call again and runs out of rounds. This happens with DSpark
off too, so it comes from the model, not the drafter. Flat arguments were always fine. Inkling also tends to make extra
read calls it doesn't need, such as reading notes before writing an invoice.

**Coding:** 8 small Python tasks with unit tests: a Dutch price parser, a postcode validator, the next pickup slot
from opening hours, removing duplicate listings, fixing a buggy function, CSV totals, a retry wrapper with backoff,
and extracting JSON from a chatty model reply. If the tests fail, the model gets the error output once and tries
again, as a minimal agent loop would. Token budget 8,000 unless noted.

| | First try | After one fix | Time | Notes |
|---|---|---|---|---|
| Inkling (250 W) | 7/8 (two full runs) | **8/8** every run | **~1–1.5 min** | small slips, such as `datetime.datetime` after `from datetime import datetime` |
| q27 (300 W) | 5/8 | 6/8 | ~20 min | all failures produced **no code at all**: it used the whole budget on thinking |
| q27, 32K tokens (3 hard tasks, 2 runs each) | 3/6 | 6/6 | 17–18 min for the price parser | the price parser still ran out of tokens twice |
| HyperQwen (250 W) | 5/8 | 6/8 | ~9 min | same failure as q27: no code, out of tokens while thinking |
| HyperQwen (370 W, gpu-unlock) | 3/8 | 4/8 | ~9 min | again every failure is no code; the code it did write was correct |
| Strata Q5 (250 W) | **8/8** | 8/8 | ~10 min | |

The two Qwen3.8-27B setups (q27 and HyperQwen) fail the same way: with thinking on, they think through easy tasks
until the budget runs out. The 4-bit quant is not the cause. With 8 tasks at temperature 0.6, a swing of 2 tasks
between runs is within noise.

The first harness version cut off code that contained `` ``` `` inside strings, which caused two false failures. The
fixed harness is the one in this repo, and the reruns are in `results_r2_*.json`. Always check your harness with
reference solutions before blaming the model.

## What we take from this

- **For chat, writing and tools with several users: HyperQwen.** It gives the 27B's quality at 2–3.6x llama.cpp's speed
  and handles 6 chats at once. It is young software, so we keep llama.cpp (q27) as the fallback. Since 27 November our own
  default is Strata Q4 (the 125B, one user at a time).
- **For Dutch (or English) text that customers will read:** HyperQwen, q27 or Strata. Not Inkling.
- **For small agents and scripts:** Inkling is the fastest, if your tool schemas stay flat (no arrays of objects) or
  your agent loop validates and repairs JSON arguments.
- **For the hardest tasks and long context:** Strata 125B. Use Q4 if it holds up on your own tasks: it is 18% faster and uses 20 GB
  less RAM. A 125B MoE at ~80 tok/s on 2016 DDR4 is usable.
- **The 27B with thinking on is a poor fit for coding loops:** it overthinks easy tasks. Thinking off or a capped
  budget is the next thing to test.
- **Power:** going from 250 W to 370 W gave +17–21% on the power-capped vLLM engine and little elsewhere. gpu-unlock
  gave more: +26–49% prefill on the vLLM engines.
- **`iommu=pt` is free speed** for engines that copy a lot between RAM and GPU (Strata, Inkling's RAM prompt cache):
  +7–15% prefill. Engines that keep everything in VRAM gain nothing.
- **Several users at once: HyperQwen 150K.** Strata, the 125B, answers one request at a time.

## Caveats

- Small samples: 10 writing prompts with one answer each (plus 20 repeated price replies), 10 tool tasks, and 8 coding
  tasks with 1–7 runs each.
- We judged the writing quality by hand.
- Rows come from 17–27 November 2026. The quality tests partly ran at 250 W (marked). Scores don't depend on power, but
  times do. Our speed prompts are short free prose. Code, summaries and long prompts behave differently, especially
  with speculative decoding.
- Our system prompt said "say the seller will check it", which may have pushed Inkling towards the third person.
- Not yet tested: Strata Q4 quality on our tasks; HyperQwen 150K/240K quality (only speed measured); recall at 200K+
  tokens on any setup.

## Rerun it

Start a model on an OpenAI-compatible endpoint (port 8080 here), then:

```bash
python3 tests/writing_test/run_writing_test.py nl_mymodel 8080 "" prompts_nl.json
python3 tests/writing_test/run_writing_test.py en_mymodel 8080 "" prompts_en.json
python3 tests/agent_test/run_agent_test.py mymodel 8080
TASKS=t09_nested_args REPEAT=5 python3 tests/agent_test/run_agent_test.py mymodel_t09 8080 only=tools
python3 tests/speed/concurrency_sweep.py <served-model-id> 512 1,2,3,4,6   # on the GPU box (reads nvidia-smi)
python3 tests/speed/prefill_bench.py <served-model-id> 8,30,60 2
```

All scripts use only the Python standard library. The agent test runs model-written code in a subprocess
(`python3 -I`, 10 s timeout, temporary directory). That code is not sandboxed further, so run it on a machine where
that is acceptable.

## License

MIT, see [LICENSE](LICENSE). Model outputs in `tests/` were generated by the models named above.
