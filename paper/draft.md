<!-- DRAFT: user rewrites. Every prose paragraph below is a draft for Mikel to say in his own words.
Numbers: each one maps to a row in research/claims.md. Markers:
  ⟦HO⟧ = held-out number taken from Mikel's run notes; its results file is not committed yet (see claims.md, "pending evidence").
  ⟦TODO …⟧ = a value to fill from a held-out results file before submitting.
Word count (title + abstract + body + captions + table + references, HTML comments excluded): run `python paper/wordcount.py`. -->

# Lost or Clueless? Where a Gemma 4 Coding Agent Actually Gets Stuck

**Freezing an agent mid-run shows that location helps it find code, not fix it, and that the harness hides the rest**

## Abstract

<!-- DRAFT: user rewrites -->
Gemma 4 should let developers run coding agents on their own hardware, yet in the Gemma 4 Developer Agent competition public scores sit near 0.24, and much stronger models solve only 4–5 more tasks in the same harness. The common explanation is that small agents get lost in large codebases. We test it with a probe: freeze the agent at a real moment of a run, add one piece of information, and measure how much more likely the right next action becomes. On 30 audited tasks and three Gemma 4 sizes, naming the file and function makes the right first read 19–33 nats more likely, but changes the right edit by under 2 nats once the code has been read; describing the change adds 11–14. Code graphs help finding only through the file they name. Test-verified edits agree; the larger models mostly hesitate rather than edit wrongly. Two harness defects, context crashes and compaction that erases the task, distort every measurement; one setting removes the crashes. The probe findings replicate on 24 held-out tasks from three new projects.

## 1 Introduction

<!-- DRAFT: user rewrites (spoken around the 11 pins) -->
The Gemma 4 Developer Agent competition asks for coding agents that run on small open models, on hardware a normal developer owns, instead of on large cloud models [1]. It is hard. Public scores sit around 0.24, and the limit is not only the model: a participant ran DeepSeek V4 Pro and Qwen3.6-27B through the same harness and they solved just 4–5 more of 124 tasks than Gemma 4 31B [2].

The default explanation is that small agents get lost in big codebases, so much effort goes into navigation: code graphs, similarity search, repository maps; the competition itself ships graphs and embeddings as tools. We test this assumption. Is the agent *lost*, not knowing where to look, or *clueless*, knowing where but not what to change? The two need different fixes. A participant's trace study points to the second [3]; we test it with controlled interventions.

Instead of only reading final scores, we look inside the agent's decisions. We freeze real runs at two moments, before the agent looks at any code (*find*) and just after it has read the right code (*use*), and feed it one more rung of information at a time: the file, the function, the reproduction test, the change described in words, the exact fix. Wrong hints check that it is not just reacting to any hint. We probe three Gemma 4 sizes, check the findings in real runs with real tests, and repeat everything on 24 held-out tasks from three other projects, all fixed after Gemma 4's release. Hypotheses were committed before the data.

Four findings follow. **Where helps finding, not fixing**: naming the file and function makes the right first read far more likely, but once the code is read the same hint does nothing for the fix, for all three sizes, as pre-registered, and on held-out tasks. **What matters more than where**: describing the change helps the fix, and the bigger models often do not edit at all, even when handed the exact answer; when 31B edits, it is usually right. In held-out runs the agent made 442 file reads and 346 commands but only 16 edits ⟦HO⟧, and most runs ended on a budget, not a wrong fix. **Graphs help by naming the file**: at the fix, a graph of an unrelated file helps as much as the right one, and plain words naming the function beat any graph. **The harness hides all of this**: confirming community reports [4, 5], it crashes on long conversations, and one setting moves no-hint solves from 6 to 9 of 30; its compaction erases the task statement in every compacted run, and 32 of 33 failed edits then target code that never existed.

We contribute the diagnosis method, these findings, the measured fix, a per-task audit of the practice set (71 of 129 valid), and a held-out set of 101 valid tasks. For builders: stop investing mainly in navigation; tell the agent what to change, keep its task and what it read through compaction, and push it to act once it knows what to change.

## 2 Setting

<!-- DRAFT: user rewrites -->
**Harness.** We use the official sample agent (Google ADK) with Gemma 4 QAT models served by vLLM in a 32,768-token window, the competition's file, shell, graph and embedding-search tools, and a budget of 40 tool calls or 15 minutes per task. A task is solved when its required tests pass with the agent's patch [1].

**Audit.** Before trusting the 129 practice tasks, we ran each in the official Kaggle sandbox with the official fix and with no change. Only 71 are valid: the fix passes and doing nothing fails (Table 1). Participants had reported the gold-pass count, the missing fastapi test modules and installed packages shadowing requests and httpx [6]; we add the no-patch check and a reason for every invalid task. In all 14 requests/httpx tasks the tests import the library installed on the host, not the repository, so no patch can change the result.

*Table 1. Why 58 of 129 practice tasks are invalid in the official sandbox.*

| Reason | Tasks |
|---|---|
| test module missing from the image | 34 |
| tests import the host's installed library, not the repo | 14 |
| environment-dependent expected output | 5 |
| async test plugin missing | 2 |
| tests pass with no patch | 2 |
| required test skipped on Python 3.12 | 1 |

**Held-out tasks.** We mined fixes merged May–October 2026 in five projects outside the practice set (sqlglot, tomlkit, networkx, sympy, pyparsing); 101 of 114 are valid in the Kaggle image. Graphs follow the released generator's rules (node ids match all 7 practice graphs); embeddings come from a disclosed open model, since the released one is not public. Probes and runs use 24 tasks whose statement is a real issue (a pull-request description can leak the fix), from sqlglot, tomlkit and networkx; sympy's graph stalls the graph tools.

## 3 The probe

<!-- DRAFT: user rewrites -->
A probe freezes the agent at one moment of a real run. We run the real agent loop against a server that records its exact requests, and keep two states per task: *find*, after the task prompt and before any code is read, and *use*, right after the agent has read the gold function. We add one hint to the task prompt (graphs arrive as a tool response; Table 2) and score the correct next action: reading the gold function at find, the gold edit at use. Its log-likelihood, from the model's own chat template, is measured in **nats**: bigger is better and the scale is logarithmic, so +1 nat makes the action 2.7 times more likely and +20 nats about 500 million times. One variable changes, everything else stays identical, and unlike solve rates the measure does not floor at zero for small models.

*Table 2. Hints. L1–L5 are cumulative; the others are single hints. Wrong hints are length-matched.*

| Code | Added to the task |
|---|---|
| L1 / L2 | the file / plus the function |
| L3 / L4 / L5 | plus the reproduction test / the change in words / the exact diff |
| W | the change in words only |
| G / G-null | a graph-tool output around the gold function / around an unrelated file |
| X-file, X-func, X-graph | wrong file / wrong function / graph focused on a wrong function |

We also *sample* the next action (one sample at find, two at use), classify it, and apply each sampled edit alone to run the task's required tests. Statistics are medians over tasks with bootstrap CIs and Wilcoxon tests with Holm correction; rescoring the same cell differs by a median 0.2–0.6 nats. We probe 30 valid practice tasks with Gemma 4 E4B, 12B and 31B. The plan, hypotheses and analysis code were committed before any GPU run, and the held-out replication criteria before any held-out data existed. Finally, we ran 12B for real on the same 30 tasks, once with no hint and once with the file, function and test names.

## 4 Results

### 4.1 Where helps finding, not fixing

<!-- DRAFT: user rewrites -->
Naming the file and function raises the correct first read by a median 19.4, 25.3 and 33.4 nats (E4B, 12B, 31B; Figure 1). After the code is read, the same hint moves the correct edit by +1.9, −1.8 and −1.5 nats. The pre-registered find-minus-use test holds for every size (Holm p < 0.001). Sampled actions agree: with the hint, the first read hits the gold function 93–97% of the time, against 3–13% without. Wrong hints behave as expected: a wrong file costs 9–19 nats; a wrong function in the right file still helps, because the file is right. The pattern is a double dissociation: the change in words, which carries no location, adds only 1–3 nats at find.

On the 24 held-out tasks all four pre-registered criteria replicate for all three sizes ⟦HO⟧ (find-versus-use; words and diff at use; graph at find; graph at use) ⟦TODO: held-out medians from D1_analysis.json⟧.

One prediction failed: the probe's per-task numbers do not forecast which tasks the hint rescues in real runs (AUC 0.43, then 0.27 without crashes).

![Figure 1](figures/fig1_where_vs_what.png)
*Figure 1. Gain in log-likelihood of the correct next action over no hint (median, 95% CI, 30 practice tasks). Location helps before the code is read, not after; the description of the change does the reverse. Graph content (right file minus unrelated file) matters only before.*

### 4.2 What to change matters more, and bigger models hesitate

<!-- DRAFT: user rewrites -->
At the use step, the change in words raises the correct edit by 11.4–14.4 nats and the exact diff by 29–42; the reproduction test adds at most 2.2. Real tests agree. On 27 paired tasks, sampled edits pass in 20%, 28% and 37% of samples for E4B with no hint, location and words; for 31B, 0%, 2% and 15%. With the exact diff they pass in 56% and 37%. Only E4B's words-versus-nothing survives correction (Holm p = 0.047): few tasks change, so power is low.

The larger models score low for a different reason than expected (Figure 2). Right after reading the right code, 31B never edits the file in its first action (0 of 60 samples); it reads more, runs a command or writes a script. Even with the exact diff, it edits in only 46% of samples, but 20 of its 25 edits pass the tests (12B: 11 of 16). E4B is the opposite: it edits 58–88% of the time and is often wrong. We grade by tests, not exact match, which would miss 54 of E4B's 65 passing edits below L5. The held-out probe edits show the same pattern ⟦HO⟧. In 24 held-out 12B runs, the agent made 442 file reads and 346 commands but 16 edits ⟦HO⟧; most runs ended on the time or call budget ⟦TODO: count from D2_analysis.json⟧, not a wrong fix. On practice tasks the same agent made 82 edits in 30 runs.

![Figure 2](figures/fig2_hesitation.png)
*Figure 2. First sampled action after reading the right code (practice tasks; bars are 95% CIs). Bigger models rarely edit, even given the exact diff, but when they do, the edit usually passes.*

### 4.3 Graphs help by naming the file

<!-- DRAFT: user rewrites -->
At find, a graph output around the gold function beats the same kind of graph for an unrelated file by 6.5, 9.8 and 4.6 nats, about what naming the file in text gives (6.3–8.2). Moving the graph's focus to a wrong function in the right file costs only 1.0–1.5 nats, against 11–20 for the same swap in text, and words naming the function beat every graph by 7–29 nats. Graph node ids are dotted module paths, so any graph output names the file. At use, the unrelated graph does as well as the right one (gains of 0.5, 9.3 and 8.7 nats against 1.2, 7.5 and 5.3), so the gain there comes from the extra tool turn, not from graph content. JSON, edge-list and adjacency encodings differ by at most 1.4 nats. Both graph criteria replicate on held-out tasks ⟦HO⟧.

### 4.4 The harness hides all of this

<!-- DRAFT: user rewrites -->
**Crashes.** vLLM refuses any request whose prompt plus reserved output exceeds 32,768 tokens. The starter reserves 16,384 for output, and ADK compacts only after the previous prompt passes 14,336 tokens, so one large tool output overflows first, as participants reported [4, 5]. In our first real runs, 14 of 30 no-hint and 9 of 30 hinted 12B runs crashed this way, and all 7 tasks the hint "rescued" had crashed without it. With the reserve at 8,192 (Figure 3), crashes fell from 14 to 0 (McNemar p = 0.0001), no-hint solves rose from 6 to 9, and the hint's advantage shrank from +7 to +4 tasks (p = 0.29). Held-out runs: at most one crash, as pre-registered ⟦HO⟧.

**Compaction.** Around tool call 10, ADK replaces older history with a model-written summary. Its summarizer keeps only text, dropping every tool call and output [7]. In all 113 compacted practice runs, the summarized events included the task prompt. Of 1,472 later requests, none contained the original statement; the median summary kept 0% of its five-word phrases and a third of its words. The agent then edits from memory. With crashes gone, failed edits rose from 6 to 33; 32 of the 33 tried to replace text that was never in the file, and 31 came after the first compaction. The held-out runs show the same erasure ⟦HO⟧.

![Figure 3](figures/fig3_runs_ended.png)
*Figure 3. How 12B runs ended on 30 practice tasks. Lowering the output reserve from 16,384 to 8,192 tokens removes the crashes; the hint's apparent benefit was mostly crashes avoided.*

## 5 Related work

<!-- DRAFT: user rewrites -->
Localization is widely treated as the bottleneck. Oracle retrieval in SWE-bench [8], hierarchical localization in Agentless [9] and graph-guided agents such as LocAgent [10] all help; giving the gold file raises resolve rates only modestly [11], and finer location context does not help repair [12]. In this competition, lexical search ranks the gold file first in only 30% of tasks [13], and traces show agents naming the right file without ever editing it [3]. Our probe explains both: location acts at the find step, not at the fix. Repository graphs [10, 14] report gains; participants audited the competition's graphs and embeddings [15] and rebuilt the generator [16]. We measure what graph output does to the model's decision, with an unrelated-graph control. For context management, SWE-agent keeps the task while trimming observations [17], and simple masking matches LLM summarization [18]; we show a deployed summarizer that drops both the task and the tool outputs. Benchmark audits found underspecified tasks and broken environments [19]; we add tests that cannot see the patch.

## 6 Limitations

<!-- DRAFT: user rewrites -->
Each condition is a single run. Probe scores are stable on rescoring, but full runs are noisy (15% of tasks flip between identical passes [2]), so part of the 6 → 9 change may be variance. We use 30 practice tasks from two projects (fastapi, rich) and 24 held-out tasks from three. The graph condition is one synthetic tool turn, not multi-hop exploration. The words rung was written by 31B from the gold diff. The probe measures information, not per-task outcomes: it did not predict which tasks a hint rescues. Held-out embeddings are a substitute.

## 7 Takeaways for builders

<!-- DRAFT: user rewrites -->
Navigation is not where small Gemma 4 agents mostly fail. Tell the agent what to change, keep the task statement and the code it read through compaction (or mask old observations instead of summarizing them), set the output reserve so prompts fit, and push it to edit once it knows what to change; forcing early edits alone mostly yields wrong ones [3].

**Reproducibility.** Notebooks, frozen plans, analysis scripts and the figure script are released with the paper; held-out tasks are rebuilt from public GitHub by script. No competition data is redistributed.

## References

[1] Kaggle. Google – The Gemma 4 Developer Agent, competition pages and leaderboard, 2026.
[2] R. Zhu. Stronger models barely beat Gemma 4 31B in this harness. Kaggle forum 747168, 2026.
[3] kimdonggyu1255. Found, not fixed. Kaggle forum 749198, 2026.
[4] Ruihuan. Compact and retry on context-window overflow? Kaggle forum 747791, 2026.
[5] A. Wright. Compaction can't trigger at token_threshold 32,768. Kaggle forum 744692, 2026.
[6] O. Zhukov; yesterdays_rebel; babycare. Sandbox validity reports. Kaggle forum 744370, 742882, 745775, 2026.
[7] Whisper Last. Let submissions set the compaction summary prompt. Kaggle forum 747186, 2026.
[8] C. Jimenez et al. SWE-bench. ICLR 2024.
[9] C. Xia et al. Agentless. FSE 2025.
[10] Z. Chen et al. LocAgent. arXiv 2503.09089, 2025.
[11] Al Awad et al. Loc2Repair. arXiv 2606.30963, 2026.
[12] Sepidband, Pham, Hemmati. Fault localization context for LLM-based program repair. arXiv 2604.05481, 2026.
[13] H. Jain. How often does the first grep hit find the file? Kaggle forum 747980, 2026.
[14] S. Ouyang et al. RepoGraph. ICLR 2025.
[15] J. Wold; A. Chinta; T. Singhal. Graph and embedding audits. Kaggle forum 742911, 745731, 744040, 2026.
[16] D. Mantiglia. codegraph-loc. GitHub, 2026.
[17] J. Yang et al. SWE-agent. NeurIPS 2024.
[18] T. Lindenbauer et al. The Complexity Trap. arXiv 2508.21433, 2025.
[19] OpenAI. Introducing SWE-bench Verified, 2024.
