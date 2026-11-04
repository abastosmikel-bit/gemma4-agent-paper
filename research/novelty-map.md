# Novelty map — paper-relevant entries

The full Phase-0 map (≈360 rows) is on `claude/gemma4-agent-research-l7vw8l` (`research/novelty-map.md`). This file holds
the entries that decide what `paper/draft.md` may claim as new. Forum items come from the forum dump of 2026-10-21 on
that branch; they are the authors' claims, not ours.

| Prior work | What it already shows | What the paper adds | Paper wording |
|---|---|---|---|
| O. Zhukov, main forum 744370 (2026-09-29) | 71 dev tasks pass with the gold patch in the Kaggle image (42 rich, 29 fastapi); remaining fastapi failures are missing `inline_snapshot`/`dirty_equals`; requests/httpx untestable (src layout) | No-patch check; a reason for each of the 58 invalid tasks; 6/14 requests/httpx valid once the repo's `src/` is imported | "Participants had reported…; we add…" (§2). **Found 2026-11-04: the 71 count is not new.** |
| yesterdays_rebel, main forum 742882 (2026-09-25) | Installed requests/httpx can shadow `/workspace`; some requests tasks pass before the gold patch | Measured on all 14 tasks (14/14 import the host copy) | credited in [6] |
| babycare, main forum 745775 (2026-10-04) | Missing fastapi test dependencies in the sandbox | — | credited in [6] |
| Ruihuan, main forum 747791 (2026-10-09); A. Wright, 744692 (2026-09-30) | Crash mechanism: 32,768 − 14,336 − 16,384 = 2,048 headroom; ADK checks the previous prompt; overflow discards the patch | Measured crash rate (14/30), its link to the hint effect, and the fix's effect in a paired rerun (14→0; solves 6→9; hint +7→+4) | "confirming community reports [4, 5]" |
| Whisper Last, main forum 747186 (2026-10-08) | ADK's summarizer keeps only `part.text`; tool calls/outputs dropped | Measured: task prompt compacted in 113/113 runs; 0/1,472 later requests keep the statement; 32/33 failed edits target code never in the file | cited [7] |
| kimdonggyu1255, main forum 749198 (2026-10-14) | **Closest overlap with the thesis.** From traces: "the default agent mostly loses tasks by not changing the code it has found, not by failing to find it"; 38% of tasks never edit a source file; forcing an edit by call 12 mostly turns hesitation into wrong edits | Causal, per-decision evidence: controlled hints at frozen states with wrong-hint controls; location's value is ~0 at the edit while the change in words adds 11–14 nats; hesitation persists even with the exact diff in hand (31B edits 46%), and its edits are right (20/25). Their 'forcing yields wrong edits' supports our 'tell it what to change' | Intro: "A participant's trace study points to the second [3]; we test it with controlled interventions." **Found 2026-11-04.** They say they are preparing a paper-track writeup: expect a judge to compare. |
| H. Jain, main forum 747980 (2026-10-10) | First grep hit is a gold file 30% of the time; BM25+grep top-5 61% | Context for why finding is hard without hints | removed from the draft for length |
| R. Zhu, main forum 747168 (2026-10-08) | Stronger models +4–5 of 124 tasks in the same harness | Motivation only | cited [2] |
| J. Wold, A. Chinta, T. Singhal (742911, 745731, 744040) | Graph/embedding audits (missing async nodes, calls-only edges, collapsed embeddings) | We measure the effect of graph output on the model's next action, with an unrelated-graph control | cited [14] |
| D. Mantiglia, codegraph-loc | Graph generator + localization benchmark | Held-out graphs use our re-implementation of the released rules (built on codegraph-loc) | cited [15] |
| Loc2Repair (arXiv 2606.30963); Sepidband et al. (2604.05481) | Gold file gives modest end-to-end gains; finer location does not help repair | Per-step measurement: location acts at find, not at the edit | cited [11, 12] |
| Lindenbauer et al., Complexity Trap (2508.21433) | Observation masking matches LLM summarization | A deployed summarizer that drops the task itself | cited [17] |

Searched and not found (forum dump, 2026-11-04): a find/use split of hint value measured by intervention; an
unrelated-graph control; a measurement that compaction removes the task statement. The "agents find but don't edit"
observation IS on the forum (749198, above); ours is the controlled version. These are the
paper's novelty claims and still need a final forum check on Kaggle (the dump stops at 2026-10-21).
