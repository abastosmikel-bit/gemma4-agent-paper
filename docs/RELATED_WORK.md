# Related work — notes with links to check (pilot C; not prose)

Checked by web search on 2026-11-02. **Verified** = the paper page (arXiv/proceedings) was found and the title and
authors match. Numbers marked *(secondary)* come from summaries, not the paper itself; check them in the PDF before
citing. "Ours" refers to `docs/CLAIMS.md`.

## A. Localization as the main bottleneck

| Paper | Link | Their point | Agree / disagree with ours | Status |
|---|---|---|---|---|
| Jimenez et al., *SWE-bench* (ICLR 2024) | https://arxiv.org/abs/2310.06770 | "Oracle" retrieval (gold files given) vs BM25: Claude 2 about 1.96% → 4.8% *(secondary)* | **Agree:** giving the files helps. Ours places the effect at the find step (claim 1), and shows it is small once the code has been read. | verified; numbers secondary |
| Xia et al., *Agentless* (FSE 2025) | https://arxiv.org/abs/2407.01489 | Hierarchical localization (file → function → lines) then repair; precise localization is critical | **Agree** for finding. **Add:** after the right code is read, location adds ~0 nats; "what to change" (+11 to +15) and the diff (+29 to +42) drive the edit. | verified |
| Meng et al., *LLM-based Agents for Automated Bug Fixing: How Far Are We?* (ICSE 2026) | https://arxiv.org/abs/2411.10213 | Compares file- and symbol-level localization accuracy across six systems; bug reproduction is weak | **Partly agree:** the reproduction-test rung adds little at the use step in ours too (T − L0: +0.4 to +2.0). | verified |
| Chen et al., *LocAgent* | https://arxiv.org/abs/2503.09089 | A graph-guided agent reaches up to 92.7% file-level localization | **Agree** the graph conveys the file. **Disagree on function level:** a single harness graph turn adds ~1 nat for the right function vs 11–20 in text (claim 3). Their agent traverses multi-hop; ours is one tool turn. | verified |
| CoSIL, *Issue Localization via LLM-Driven Iterative Code Graph Searching* | https://arxiv.org/abs/2503.22424 | Better localization → +4–31% resolve *(secondary)* | **Agree** on find. We don't test iterative graph search. | found; numbers secondary |
| Yu et al., *OrcaLoca* (ICML 2025) | https://proceedings.mlr.press/v267/yu25x.html | Function match 65.33% on SWE-bench Lite; +6.33 pp resolve | **Agree:** function-level location matters for finding (ours: depth-2 hit_func 10–13% → 93–97% with the text hint). | verified (proceedings); the arXiv ID 2502.00350 was **not** confirmed |
| Ouyang et al., *RepoGraph* (ICLR 2025) | https://arxiv.org/abs/2410.14684 | A line-level repository graph boosts SWE-bench systems | **Caution:** part of a graph's gain may be the file name and the context-ending effect (claim 3; C04's G-null control pending). | verified |
| Liu et al., *CodexGraph* (NAACL 2025) | https://arxiv.org/abs/2408.03910 | Graph-database interface for code agents | Same caution as RepoGraph. | verified |
| Al Awad et al., *Loc2Repair* | https://arxiv.org/abs/2606.30963 | Gold file-level localization raises pooled resolve from 44.7% to 52.4% on SWE-bench Verified | **Agree, and consistent in size:** a file hint gives a modest end-to-end gain, as expected if location fixes only the find step. Our own end-to-end hint effect (C05: +7 tasks) ran through crashes; C06 pending. | verified (June 2026) |
| Sepidband, Pham, Hemmati, *On the Role of Fault Localization Context for LLM-Based Program Repair* | https://arxiv.org/abs/2604.05481 | File-level localization matters most; line-level expansion often hurts | **Agree:** ours finds location adds ~0 at the use step, which fits "finer location does not help the edit". | verified (April 2026) |
| Al-Haque & Johnson, *What Makes Software Issue Resolution Tasks Difficult for Agents?* (ESEM 2026) | https://arxiv.org/abs/2608.18280 | Task structure predicts agent difficulty | Complementary: ours measures, per task, which information moves which step. Contents not verified beyond the abstract. | found; contents unverified |
| *SHERLOC: Structured Diagnostic Localization for Code Repair Agents* | arXiv 2606.24820 (seen only on an aggregator) | Accuracy@1 84% on SWE-bench Lite *(secondary)* | — | **unsure:** not seen on arXiv directly |
| *SWE-Ladder* | — | — | — | **not found.** I named it in the Rethink (`REPORT.md` §8); drop it. |

## B. Compaction and context overflow

| Paper / source | Link | Their point | Agree / disagree with ours | Status |
|---|---|---|---|---|
| Lindenbauer et al., *The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management* (NeurIPS 2025 DL4C workshop) | https://arxiv.org/abs/2508.21433 | Masking old observations matches LLM summarization at about half the cost (SWE-agent, SWE-bench Verified) | **Agree** summarization is not free. Ours adds what ADK's summarizer drops: tool calls/outputs and the task prompt itself, in 55/55 compacted runs (claim 2). Masking keeps the task. | verified |
| Yang et al., *SWE-agent* (NeurIPS 2024) | https://arxiv.org/abs/2405.15793 | History processors truncate old observations and keep the task | **Contrast:** the starter's ADK compaction also compacts the task prompt. The SWE-agent detail is *(secondary)*; check the paper's appendix. | verified; mechanism secondary |
| Kang et al., *ACON: Optimizing Context Compression for Long-horizon LLM Agents* | https://arxiv.org/abs/2510.00615 | Optimized compression guidelines; smaller models gain up to 46% | **Agree** that compression quality matters most for small models. 12b/31b compact in every run in ours. | verified |
| OpenHands context condenser (`LLMSummarizingCondenser`, `keep_first`) | https://docs.all-hands.dev | Summarizes older history; `keep_first` keeps the first events | **Contrast:** `keep_first` would keep the task; the starter's ADK config keeps only the *last* 5 events. | **unsure:** seen only in third-party example code; check the OpenHands docs |
| Liu et al., *Lost in the Middle* (TACL 2024) | https://arxiv.org/abs/2307.03172 | Models use information in the middle of long contexts poorly | Background only: our crashes come from a request-size rule, not from attention. | not re-checked in this session |
| Prior report of "the reserved output length shrinks the prompt limit below the compaction threshold" | — | — | — | **none found.** I searched papers only, not forums or issue trackers; check the competition forum and the ADK/vLLM issues before claiming novelty (claim 4). |

## C. Benchmark validity (claim 5)

| Paper | Link | Their point | Agree / disagree with ours | Status |
|---|---|---|---|---|
| OpenAI, *Introducing SWE-bench Verified* (Aug 2024) | https://openai.com/index/introducing-swe-bench-verified/ | 1,699 samples annotated, 500 kept; underspecified issues, overly specific tests, hard environments | **Agree:** environments break validity. Ours: 58/129 dev tasks invalid in the official sandbox, mostly the environment (missing modules or fixtures, the host's installed copy shadowing the repo). | verified |
| Aleithan et al., *SWE-Bench+* | https://arxiv.org/abs/2410.06992 | Solution leakage in 32.67% and weak tests in 31.08% of passed patches | Complementary: they find leaks and weak tests; we find tests that cannot see the patch at all. | verified |
| Wang, Pradel, Liu, *Are "Solved Issues" in SWE-bench Really Solved Correctly?* (ICSE 2026) | https://arxiv.org/abs/2503.15223 | 7.8% of "correct" patches fail the developer test suite (PatchDiff) | Complementary: ours flags tasks that pass with **no** patch (3/129 on Kaggle), where any non-empty edit "solves" them. | verified |

## D. Graph encodings (H3)

| Paper | Link | Their point | Agree / disagree with ours | Status |
|---|---|---|---|---|
| Markowitz et al., *KG-LLM-Bench* | https://arxiv.org/abs/2504.07087 | Textualization format changes accuracy (up to ~15% *(secondary)*) | **Partly:** in ours the encodings differ by at most ~1.4 nats. Edges/adjacency beat JSON only slightly for e4b (+0.6 / +0.8); format matters little for location. | verified |
| Markowitz et al., *Tree-of-Traversals* | https://arxiv.org/abs/2407.21358 | LLMs acting over knowledge-graph queries | Background for the graph rung (`docs/PLAN.md` §4.2). | cited by KG-LLM-Bench; not re-checked directly |

Sources (searches of 2026-11-02): arxiv.org pages linked above;
[ICML 2025 proceedings (OrcaLoca)](https://proceedings.mlr.press/v267/yu25x.html);
[OpenAI SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/);
[NeurIPS 2025 (Complexity Trap)](https://neurips.cc/virtual/2025/131688);
[ICLR 2025 (RepoGraph)](https://iclr.cc/virtual/2025/poster/28957); [ICSE 2026 track pages](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/59/Are-Solved-Issues-in-SWE-bench-Really-Solved-Correctly-An-Empirical-Study).
