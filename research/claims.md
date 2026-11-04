# Claims → evidence for `paper/draft.md`

Every number in the draft is listed here with where it comes from. Branches/commits: **C** = `pilot/c-bottleneck`
@ 14e9d00 (all `results/…` paths below), **P** = `paper/main` @ 3b5b7e3 (`docs/CLAIMS.md`, `RESULTS.md`),
**D** = `pilot/d-heldout` @ 04dd8d1, **F** = forum dump of 2026-10-21 on `claude/gemma4-agent-research-l7vw8l`
(`research/raw/kaggle/…/forum.md`). The longer claim sheet with caveats is P `docs/CLAIMS.md`; this file only maps the
paper's numbers.

Status: **measured** (single run unless noted) · **exploratory** (not pre-registered) · **community** (someone
else's measurement, cited) · **PENDING EVIDENCE** (no results file yet; none left as of 2026-11-04) · **verify** (check on Kaggle before submitting).

## Competition facts

| # | Draft says | Source | Status |
|---|---|---|---|
| K1 | (removed) Leaderboard figures | Removed from the draft on 2026-11-04 at Mikel's request: public data that can change | — |
| K2 | Stronger models +4–5 of 124 tasks | F topic 747168 (R. Zhu, 2026-10-08): Gemma 31B 54/124 & 53/123; DeepSeek V4 Pro 58/124; Qwen3.6-27B 59/123 | community |
| K3 | 15% of tasks flip between identical passes | same thread: 19/123 | community |
| K4 | Crash mechanism (16,384 reserve, 14,336 threshold, 2,048 headroom) reported | F 747791 (Ruihuan, 2026-10-09); F 744692 (A. Wright, 2026-09-30: overflow discards the patch) | community; our measurement in M17–M20 |
| K5 | Summarizer keeps only text, drops tool calls/outputs | F 747186 (Whisper Last, 2026-10-08); confirmed in google-adk 1.36.1 `apps/llm_event_summarizer.py` (P LEARNINGS 2026-10-31) | community + code check |
| K6 | Others had reported the 71 gold passes, the missing test modules, and that requests/httpx could not be tested because of their src layout | Live pages read 2026-11-04: O. Zhukov's comment in 744370 (71 gold passes, 42 rich + 29 fastapi; missing inline_snapshot/dirty_equals; "requests and httpx can't be tested there because of their src layout"); babycare 745775 (missing fastapi test deps); yesterdays_rebel's visible comment in 742882 lists missing test packages. The shadowing text seen in the 2026-10-21 dump of 742882 is **no longer visible** (edited or deleted), so the draft no longer credits shadowing to it | community, verified |
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

## Held-out (D) — files on this branch: `results/D1_analysis.json`, `results/D1v_analysis.json`, `results/D2_analysis.json`

| # | Draft says | Evidence | Status |
|---|---|---|---|
| H1 | 101/114 held-out tasks valid in the Kaggle image; five repos; fixes merged May–Oct 2026 | C `results/D0b_summary.json`; D `pilot_d/manifest.json` (since 2026-05-01) | measured |
| H2 | Released-rule graphs reproduce node ids on 7/7 dev graphs | D `results/graph_fidelity_dev.json` | measured locally |
| H3 | 24 issue-statement tasks: sqlglot 11, tomlkit 8, networkx 5 | `D1_analysis.json` selection (seed 20261102, pool 32) | measured |
| H4 | R1–R4 replicate for all three sizes | `D1_analysis.json` verdicts | measured, single run, pre-registered (682a34f) |
| H5 | Find L2−L0 +18.0 / +21.2 / +31.5; use L2−L0 +1.7 / +0.4 / −0.5 | `D1_analysis.json` R1 | measured |
| H6 | Use W−L0 ≈ +22 (22.0 / 22.2 / 22.2); L5−L0 +107 / +125 / +119 (n = 18) | `D1_analysis.json` R2 | measured; W and L5 exist for 18/24 tasks |
| H7 | Use T−L0 +3.9 / +11.0 / +4.9 ("4–11") | `D1_analysis.json` depth1 | measured; larger than dev (0.4–2.2), reported as such |
| H8 | Graph at find G-json−G-null +4.3 / +3.9 / +6.5; at use G-null matches or beats G-json | `D1_analysis.json` R3, R4 (use G-json−G-null +0.5 / −4.0 / −1.6) | measured |
| H9 | Sampled find: E4B reads gold function with hint 24/24; 31B reads gold file first in 1/24 even with hint | `D1_analysis.json` R5 find (e4b/L2 hit_func 1.0; 31b/L2 hit_file 0.042); 12B 54% file / 33% function | measured, 1 sample per task. **Differs from dev (93–97%)**, reported |
| H10 | 31B edits once in 132 held-out samples (0/48, 0/48, 1/36); first move without hint: write_file 19/48 | `D1_analysis.json` R5 use first_tools | measured |
| H11 | E4B held-out pass rate 10% / 8% / 56% (L0 / L2 / L5) | `D1v_analysis.json` V | measured (exploratory) |
| H12 | 442 reads, 346 commands, 16 edit_file + 15 write_file; 5/24 solved; 17/24 ended on time (6) or tool-call (11) budget | `D2_analysis.json` tool_mix, ended | measured, single run |
| H13 | 1 of 24 runs crashed (R7 holds) | `D2_analysis.json` R7 | measured |
| H14 | 24/24 compacted, prompt compacted 24/24; 0 of 582 later requests contain the statement; median 5-gram retention 1.1%, words 31% | `D2_analysis.json` R6, summary_retention | measured |
| H15 | 3 of 16 edits failed, all after compaction (2 never matched) | `D2_analysis.json` failed_edits | measured |
| H16 | Totals used in the draft: 137 compacted runs (113 dev + 24 held-out); 2,054 checked requests in 82 runs (C06 58 + D2 24) | M21 + H14; C06 A5 (1,472) + D2 (582) | derived |
| H17 | "Fixed after Gemma 4's release" | family released 2026-03-31; **12B released 2026-06-03**, so a few May fixes predate the 12B release; all are after the stated Jan-2025 training cutoff | fact; wording caveat |

## Not claimed (kept out on purpose)

- The held-out solve rate is stated (5/24) but not compared with dev: different repos (plan D2 §4).
- Any claim that the location hint improves solve rate: +4 net, p = 0.29.
- H2 (words gain grows with size) and H5 were not supported; H4's size trend not supported. Not in the draft for space;
  add one line in Limitations if a reviewer asks for the full scorecard.

## Provenance of the forum credits (checked 2026-11-04)

The paper credits [3]–[7] for priority and says our numbers are our own. It does **not** say we found the posts only
after our experiments, because the project's own notes show otherwise: Phase 0 (2026-10-21, branch
`claude/gemma4-agent-research-l7vw8l`, `research/failure-modes.md`, `novelty-map.md`) lists 744692, 747186, 749198 and
747168; pilot C's REPORT §5/§8.1 (2026-10-31, before the probe was designed) cites 749198 as a "direct competitor"; the
missing-fastapi-module count was known before C00 (RESULTS row "forum reported 27"). What is true and stated: the crash
mechanism and the summarizer behaviour were traced in vLLM/ADK source during our own diagnosis (LEARNINGS 2026-10-31,
2026-11-01; RELATED_WORK §B "searched papers only, not forums"), and every number comes from our runs.

## Reference check (2026-11-04)

| Ref | How checked | Result |
|---|---|---|
| [1] | competition pages | fine; leaderboard no longer cited |
| [2] 747168 | live page (headless browser) | author Ruijie Zhu; title "Stronger models barely beat Gemma 4 31B in this harness — teacher comparison on 124 public tasks"; Gemma 31B 54/124 and 53/123, DeepSeek V4 Pro 58/124, Qwen3.6-27B 59/123 (= +4–5) |
| [3] 749198 | live page, full text read | author kimdonggyu1255, posted 2026-10-14. Method: traces of two practice runs (default prompt, 71 tasks; Budget-Fit config, 112 tasks) that differ in nine ways ("compares footprints, not effects"). Findings: 27/71 default-prompt tasks never changed a source file, 23 of them had named a gold file; edit-by-call-12 prompt cut no-edit tasks 25→7 on 69 shared tasks but solves only 26→30, and most unsolved N1 tasks had an edit in a gold file. Conclusion quoted: "mostly loses tasks by not changing the code it has found, not by failing to find it"; "forcing the change early mostly turns that hesitation into wrong edits". No interventions on information, no model sizes compared. The draft's description (traces of two practice runs; names the file but never edits; edit deadline mostly produces wrong edits) and "ours comes from controlled interventions" are fair |
| [4] 747791 | live page | author Ruihuan; "Can the harness compact and retry on context-window overflow?" |
| [5] 744692 | live page | author Avery Wright; "Compaction can't trigger at token_threshold 32,768, and overflow then discards the patch" |
| [6] 744370 / 742882 / 745775 | live pages | see K6 (thread authors are Vivek K N and shimonDanziger; Zhukov and yesterdays_rebel are commenters, so [6] now says "comment in") |
| [7] 747186 | live page | author Whisper Last; "Request: let submissions set the compaction summary prompt (ADK already supports it)" |
| [8]–[10], [13], [16], [17] | arXiv API | titles/authors match: SWE-bench 2310.06770, Agentless 2407.01489, LocAgent 2503.09089, RepoGraph 2410.14684, SWE-agent 2405.15793, Complexity Trap 2508.21433 |
| [11] 2606.30963 | arXiv API + abstract | "Loc2Repair: A Framework for Evaluating the Impact of File-Level Issue Localization in Repo-Level LLM Repair", M. N. Al Awad, S. Ivanov, 2026-06-29. Pooled resolve 44.7% → 52.4% with gold files on SWE-bench Verified. Draft now states the numbers instead of "only modestly" |
| [12] 2604.05481 | arXiv API + abstract | "On the Role of Fault Localization Context for LLM-Based Program Repair", M. Sepidband, H. V. Pham, H. Hemmati, 2026-04-07. File-level localization dominant (15–17× over no file); line-level expansion often degrades. Draft now says "file-level context dominates while line-level context often hurts" (was the broader "finer location context does not help") |
| [14] 742911 / 745731 / 744040 | live pages | Jason Wold "Two data issues: … graphs contain no async functions"; Akhil Chinta "Notes on the graph tools from auditing all 127 graphs"; Tarun Singhal "Embeddings for search_similar_code appear near-collapsed" |
| [15] codegraph-loc | GitHub search | danielmantiglia/codegraph-loc (created 2026-10-05). It is the generator our held-out graphs are built with (pilot D pins commit 1e8e0ab), so §2 now cites it there too. A different repo with the same name exists (Benadict-Git, 2026-09-26); not the one we used |
