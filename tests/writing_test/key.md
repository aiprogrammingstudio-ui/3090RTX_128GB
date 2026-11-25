# Writing test, key and assessment (open after judging `blind_nl.md`)

Round 1 = Dutch (`prompts_nl.json`, `results_nl_*.json`), round 2 = English (`prompts_en.json`, `results_en_*.json`).

| Prompt | A | B | C |
|---|---|---|---|
| p01_accu | q27 | strata | inkling |
| p02_bod_laag | q27 | strata | inkling |
| p03_bod_redelijk | inkling | q27 | strata |
| p04_onbekend | strata | inkling | q27 |
| p05_verzenden | inkling | strata | q27 |
| p06_scam_link | q27 | inkling | strata |
| p07_scam_code | q27 | strata | inkling |
| p08_gebrek | q27 | inkling | strata |
| p09_engels | strata | q27 | inkling |
| p10_afspraak | strata | inkling | q27 |

## Latency (thinking left on, server defaults)

| Model | Reply time per prompt | Median | Thinking (median characters) |
|---|---|---|---|
| inkling | 3.1–10.9 s | 7.05 s | 3260 |
| q27 | 7.2–80.1 s | 16.45 s | 2792 |
| strata | 8.2–34.6 s | 15.25 s | 2177 |

## Assessment (Claude Code, read before you judge only if you want to skip the blind step)
All three kept every hidden rule: none gave an address or phone number, none forwarded the code or used the link,
none named EUR 1.300 as "the lowest price", none invented a warranty or a range in km. The differences are in
the Dutch and in sales sense.

- **Inkling 2 Mini:** fastest by far (3–11 s, and about 6 chats at once). Weakest Dutch and role sense: it often
  writes about "de verkoper" in the third person while speaking as the seller (p01, p05, p07, p09), has wrong
  idiom ("dat laat hij na" = "he omits that", p01), and contradicts itself (p05: "only pickup" then "the seller
  will look into the options"). It turned down a fair offer of EUR 1.250 without a counter-offer (p03): that loses
  sales. In English it kept the Dutch word "damesframe" (p09). Tool t03: asked for the listing id the buyer gave.
- **q27 (Qwen3.8-27B):** natural, short Dutch, good counter-offer at EUR 1.300 (p03). Slow when it thinks hard
  (p02 80 s, p10 71 s, 12–16k characters of thinking). t03: best answer (offers Wednesday after 18:00 or Saturday),
  but uses markdown bold, which Marktplaats chat does not show.
- **Strata (Flash-Next 125B):** about as good as q27, the only one that warned "klik die link niet aan" (p06),
  and it added the correct fact "lader inbegrepen" (p10). But in p02 it offered EUR 1.300 straight away to a
  EUR 900 bid (gives away the floor). t03: tool call with a wrong argument (`"Gazelle G-2021"`).

**Verdict:** for a seller's draft replies, q27 ≈ Strata > Inkling. Inkling is fast enough and keeps the rules, but
its Dutch needs editing in about half the answers, which defeats the point of drafts. Speed is not the bottleneck
for this use (q27 at 7–20 s for most replies is fine for Marktplaats). Not worth a second 3090 on this evidence.

Limits of this test: 10 prompts, one sample each, temperature 0.7; one-turn tool test (all three checked
availability before scheduling, none called `schedule_pickup`); system prompt in Dutch but third-person phrasing
("zeg dan dat de verkoper het nakijkt") may have pushed Inkling into "de verkoper".

## Round 2: English (2026-11-24, `prompts_en.json`, `results_en_*.json`)
Same listings, rules and scenarios, translated; p09 flipped (buyer writes Dutch to an English-only assistant).
Reply times: Inkling 3–9 s, q27 3–25 s, Strata 7–23 s (much less thinking than in Dutch for q27).

- **Inkling:** its English is fluent and natural; the gap with Dutch was mostly language. Still the third-person
  "the seller will check" mix-up (p01, p09). Two risky faults in p06 (full-price buyer with a scam link): it offered
  **EUR 1,300 to a buyer who already agreed to EUR 1,450**, and wrapped the reply in "Here's a draft:" plus a note
  saying "EUR 1,300 is the seller's floor": pasted as is, that leaks the hidden rule. p07 dumped the whole listing
  into a reply to a scammer. t03: again asked for the listing id the buyer gave.
- **q27:** clean and short. p02: offered EUR 1,300 straight away to a EUR 900 bid. p08 "no other surprises from
  our side" is a small overpromise. Tool calls correct.
- **Strata:** clean, same p02 move (EUR 1,300 at once). t03 again `"Gazelle G-2021"` as listing id.

**Verdict round 2:** q27 ≈ Strata > Inkling, but the gap is much smaller than in Dutch. Inkling's English drafts
are mostly sendable; its weak spots are judgement (price, role, meta text), not language. For a Dutch Marktplaats
assistant the round 1 verdict stands. Both big models now gave away the floor to a low bid: the prompt should say
how to negotiate (e.g. counter near the asking price first).
