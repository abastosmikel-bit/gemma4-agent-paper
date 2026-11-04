# Claims → evidence for `paper/draft.md`

Every number in the draft is listed here with where it comes from. Branches/commits: **C** = `pilot/c-bottleneck`
@ 14e9d00 (all `results/…` paths below), **P** = `paper/main` @ 3b5b7e3 (`docs/CLAIMS.md`, `RESULTS.md`),
**D** = `pilot/d-heldout` @ 04dd8d1, **F** = forum dump of 2026-10-21 on `claude/gemma4-agent-research-l7vw8l`
(`research/raw/kaggle/…/forum.md`). The longer claim sheet with caveats is P `docs/CLAIMS.md`; this file only maps the
paper's numbers.

Status: **measured** (single run unless noted) · **exploratory** (not pre-registered) · **community** (someone
else's measurement, cited) · **PENDING EVIDENCE** (stated in Mikel's run notes; the results file is not in the repo yet,
so the number must not ship until it is committed and checked) · **verify** (check on Kaggle before submitting).

## Competition facts

| # | Draft says | Source | Status |
|---|---|---|---|
| K1 | Public scores around 0.24 | F topic 750496 (S. D. Biswas, 2026-10-18: "teams reaching 0.22–0.24") | **verify** on the live leaderboard |
| K2 | Stronger models +4–5 of 124 tasks | F topic 747168 (R. Zhu, 2026-10-08): Gemma 31B 54/124 & 53/123; DeepSeek V4 Pro 58/124; Qwen3.6-27B 59/123 | community |
| K3 | 15% of tasks flip between identical passes | same thread: 19/123 | community |
| K4 | Crash mechanism (16,384 reserve, 14,336 threshold, 2,048 headroom) reported | F 747791 (Ruihuan, 2026-10-09); F 744692 (A. Wright, 2026-09-30: overflow discards the patch) | community; our measurement in M17–M20 |
| K5 | Summarizer keeps only text, drops tool calls/outputs | F 747186 (Whisper Last, 2026-10-08); confirmed in google-adk 1.36.1 `apps/llm_event_summarizer.py` (P LEARNINGS 2026-10-31) | community + code check |
| K6 | Gold-pass count, missing fastapi test modules and requests/httpx shadowing were reported on the forum before our audit | F 744370 (O. Zhukov, 2026-09-29: 71 gold-pass in the Kaggle image, 42 rich + 29 fastapi; requests/httpx untestable, src layout); F 742882 (yesterdays_rebel, 2026-09-25: installed requests/httpx shadow /workspace, some pass before the gold patch); F 745775 (babycare, 2026-10-04: missing fastapi test deps) | community. Our additions: no-patch check on Kaggle, a reason for all 58 invalid tasks, 6/14 valid with src/ first |
| K8 | A trace study found agents naming the right file but never editing it; forcing early edits mostly yields wrong edits | F 749198 (kimdonggyu1255, 2026-10-14): 27/71 default-prompt tasks never changed a source file, 23 of them had named a gold file; an edit-by-call-12 prompt cut no-edit tasks 25→7 but solves only 26→30 | community; overlaps our thesis (cited as the observational version) |
| K9 | Lexical search ranks the gold file first in 30% of tasks | F 747980 (H. Jain, 2026-10-10): top identifier-grep hit is a gold file 30% of the time (128 tasks) | community |
| K7 | 3,000-word limit, five equal criteria, deadline 2026-11-12 | paper-track pages in the F dump (`gemma-4-developer-agent-paper/pages.md`) | **verify** (Kaggle overrides) |

## Practice-set measurements (dev, 30 tasks unless noted)

| # | Draft says | Evidence | Status |
|---|---|---|---|
| M1 | 71/129 valid; reasons 34 / 14 / 5 / 2 / 2 / 1 (Table 1) | C `results/C00_gold_check.json`, `results/C00_audit.md` (`notebooks/C00_gold_check__CPU.ipynb`, Kaggle 2026-10-31) | measured |
| M2 | 14/14 requests/httpx tasks import the host library | C `results/C00_audit_imports.json` | measured locally (Py 3.12, same wheelhouse), not on Kaggle |
| M3 | Find, L2−L0: +19.4 / +25.3 / +33.4 nats | C `results/D1_dev_reference.json` R1 (= `C03C04_tables.md` T2); `paper/numbers.md` | measured, single run, pre-registered (H1) |
| M4 | Use, L2−L0: +1.9 / −1.8 / −1.5; find>use Holm p < 0.001 all sizes | same | measured, pre-registered |
| M5 | First read hits gold function 93–97% with hint vs 3–13% without | C `results/C03C04_tables.md` T3 | measured (1 sample per task) |
| M6 | Wrong file costs 9–19 nats vs right file (X-file − L1) | C `C03C04_tables.md` T1-find: −9.3 / −18.8 / −16.0 | measured |
| M7 | Words at find: +1 to +3 nats | C `D1_dev_reference.json` depth1 find W−L0: +2.8 / +1.9 / +1.0 (31B CI includes 0) | measured |
| M8 | H6 failed: AUC 0.43 (C05), 0.27 (C06) | C `results/C05_analysis.json`, `results/C06_analysis.json` A4 | measured, pre-registered, negative |
| M9 | Use: W−L0 +11.4 / +14.4 / +11.6; L5−L0 +29.2 / +42.4 / +33.8; T−L0 ≤ 2.2 | C `D1_dev_reference.json` R2; `C03C04_tables.md` T1-use | measured. Note: P `docs/CLAIMS.md` lists 12B W as +15.0 (C03-only); the draft uses the merged C03+C04 value +14.4 |
| M10 | Pass rates L0/L2/W on 27 tasks: E4B 20/28/37%, 31B 0/2/15%; E4B W−L0 Holm p = 0.047 | C `results/C03v_checks.json` K2 | exploratory, underpowered |
| M11 | Pass rate with exact diff: E4B 56%, 31B 37% | C `results/C03v_tables.md` V1 (L5, 54 samples, 27 tasks) | measured |
| M12 | 31B first action edits gold file 0/60 at L0 (others: read 32, run 21, write another file 5…) | C `results/C03v_checks.json` K1 | measured |
| M13 | With diff: 31B edits 46%, 20/25 pass; 12B 11/16; E4B edits 58–88% | same K1 | measured, small n |
| M14 | 54 of E4B's 65 passing edits at L0–L4 not exact | C `results/C03v_checks.md` K3 | measured |
| M15 | 82 edits (and 541 reads, 401 commands) in 30 practice runs | C `results/D2_dev_reference.json` tool_mix (C06 no-hint) | measured |
| M16 | Graph at find: G-json − G-null +6.5 / +9.8 / +4.6; L1−L0 +6.3 / +8.2 / +6.9; X-graph swap 1.0–1.5 vs text 11.4–20.1; text beats graphs by 7.2–28.5; at use G-null−L0 +0.5 / +9.3 / +8.7 vs G-json−L0 +1.2 / +7.5 / +5.3; encodings ≤ 1.4 | C `results/C04_tables.md` E1, `C03C04_tables.md` T2/T6 | exploratory (C04), single run |
| M17 | C05: 14/30 and 9/30 runs crashed; all 7 rescued tasks had crashed (7/14 vs 0/10) | C `results/C05_analysis.json` | measured; link post hoc |
| M18 | C06 (reserve 8,192): crashes 14→0 (McNemar p = 0.0001), 9→2 | C `results/C06_analysis.json` A1 | measured, single run |
| M19 | No-hint solves 6→9; hint +7 → +4 net (6 up, 2 down; p = 0.29) | C `results/C06_analysis.json` A2 | measured, single run; part may be variance |
| M20 | First compaction around tool call 10 | C `results/C05_analysis.json` (median 10, range 4–23) | measured |
| M21 | Task prompt compacted in 113/113 compacted runs | C01 10 + C05 45 + C06 58 (P `docs/CLAIMS.md` claim 2) | measured |
| M22 | 0 of 1,472 post-compaction requests contain the statement; median 5-gram retention 0% (O-all 0.3%), word recall ≈ 1/3 | C `results/C06_analysis.json` A5 | measured; lexical measure |
| M23 | Failed edits 6→33; 32/33 never in file; 31/33 after first compaction | C `results/C06_failed_edits.json` | exploratory |
| M24 | Rescoring noise 0.2–0.6 nats | C `results/C03_probe.json` (P LEARNINGS 2026-11-01); C04 E4 0.16–0.32 | measured |
| M25 | Plan frozen before any GPU run; held-out criteria before held-out data | P `DECISIONS.md`: 168d115 (2026-10-31), 682a34f (2026-11-02) | fact |

## Held-out (D)

| # | Draft says | Evidence | Status |
|---|---|---|---|
| H1 | 101/114 held-out tasks valid in the Kaggle image; five repos; fixes merged May–Oct 2026 | C `results/D0b_summary.json`; D `pilot_d/manifest.json` (since 2026-05-01) | measured |
| H2 | Released-rule graphs match node ids on 7/7 dev graphs | D `results/graph_fidelity_dev.json` | measured locally |
| H3 | 24 issue-statement tasks from sqlglot, tomlkit, networkx | C `results/D_selection_predicted.json` (predicted 11/8/5); authoritative `D_selection.json` from the D1/D2 run | **PENDING EVIDENCE** for the final list |
| H4 | All four probe criteria (R1–R4) replicate for all three sizes | expected `results/D1_analysis.json` (`verdicts`) | **PENDING EVIDENCE** |
| H5 | Held-out probe edits show the dev pattern | expected `results/D1v_analysis.json` | **PENDING EVIDENCE** |
| H6 | 442 file reads, 346 commands, 16 edits in 24 runs; most runs ended on time or call budget | expected `results/D2_analysis.json` (`tool_mix`, `ended`) | **PENDING EVIDENCE**; also check whether "16 edits" counts `write_file` |
| H7 | ≤ 1 context crash (R7) and 0 post-compaction requests with the statement (R6) | expected `results/D2_analysis.json` | **PENDING EVIDENCE** |
| H8 | "Fixed after Gemma 4's release" | D `docs/PRIOR_WORK.md`: family released 2026-03-31; **12B released 2026-06-03**, so some May fixes predate the 12B release; all are after the stated Jan-2025 training cutoff | fact; wording caveat |

## Not claimed (kept out on purpose)

- A held-out solve rate (in D2_analysis.json; add if Mikel wants it, with its Wilson CI and "single run").
- Any claim that the location hint improves solve rate: +4 net, p = 0.29.
- H2 (words gain grows with size) and H5 were not supported; H4's size trend not supported. Not in the draft for space;
  add one line in Limitations if a reviewer asks for the full scorecard.
