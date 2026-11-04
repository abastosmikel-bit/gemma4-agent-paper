<!-- DRAFT: user rewrites. Every prose paragraph below is a draft for Mikel to say in his own words.
Every number maps to a row in research/claims.md. Held-out numbers come from results/D1_analysis.json,
results/D1v_analysis.json and results/D2_analysis.json on this branch.
Word count (title + abstract + body + captions + tables + references, HTML comments excluded): python paper/wordcount.py -->

# Lost or Clueless? Where a Gemma 4 Coding Agent Gets Stuck

**Freezing the agent mid-run to see which information changes its next move**

## Abstract

<!-- DRAFT: user rewrites -->
In the Gemma 4 Developer Agent competition, public scores top out at 0.29, and much stronger models solve only 4–5 more of 124 tasks in the same harness. We test the common explanation that small agents get lost in large codebases, using a probe that freezes the agent at a real point of a run, adds one piece of information, and measures how much more likely its correct next action becomes. On 30 audited practice tasks and three Gemma 4 sizes, naming the file and function makes the correct first read 19–33 nats more likely. Once the code has been read, the same hint changes the correct edit by less than 2 nats, while a description of the change raises it by 11–14. Code graphs help only through the file they name, and the larger models rarely edit even when given the exact diff. Two harness problems, context-window crashes and a compaction step that deletes the task statement, distort end-to-end scores, and one setting removes the crashes. The probe results replicate on 24 held-out tasks from three other projects.

## 1 Introduction

<!-- DRAFT: user rewrites (spoken around the 11 pins) -->
This competition asks for coding agents that run on small open models, on hardware a developer already owns [1]. Progress has been slow: the best public score is 0.29, and most leading teams sit at 0.24. The model is not the only limit. One participant ran DeepSeek V4 Pro and Qwen3.6-27B through the same harness, and they solved only 4–5 more of 124 tasks than Gemma 4 31B [2].

The usual explanation is that small agents get lost in large codebases, so much work goes into navigation aids such as code graphs, similarity search and repository maps, and the competition ships graphs and embeddings as tools. We test that assumption. An agent can be lost, not knowing where to look, or clueless, knowing where but not what to change, and the two need different fixes. Another participant came to a similar conclusion by reading run traces [3]. We reached ours with controlled interventions.

We stop real runs at two moments, before the agent has read any code (find) and just after it has read the right code (use). At each moment we add information one rung at a time: the file, the function, the reproduction test, a description of the change, the exact fix. Length-matched wrong hints serve as controls. We did this for three Gemma 4 sizes, checked the results in real runs with real tests, and repeated it on 24 tasks from three other projects, fixed after Gemma 4's release. Hypotheses were committed before the data.

Location is worth a lot at find and almost nothing at use, for all three sizes, as pre-registered and on held-out tasks. A description of the change does the opposite. The larger models also hesitate. They rarely edit even with the exact diff in hand, though on practice tasks 31B's edits usually pass when it makes them. In held-out runs the agent made 442 file reads and 346 commands but 16 edits, and most runs ended on a budget. Graphs help the first read by naming the file, but at the edit an unrelated graph does as well. The harness hides much of this. As other participants also found [4, 5], long conversations overflow the context window, and one setting raised no-hint solves from 6 to 9 of 30. Compaction erased the task statement in every run where it fired, and 32 of 33 failed practice edits targeted code that was never in the file.

We contribute the probe, these findings, the measured crash fix, a per-task audit of the practice set (71 of 129 valid) and 101 valid held-out tasks. For builders: spend less on navigation, tell the agent what to change, keep its task and what it read through compaction, and push it to edit once it knows the change.

## 2 Setting

<!-- DRAFT: user rewrites -->
**Harness.** We use the official sample agent, built on Google ADK, with the competition's file, shell, graph and embedding-search tools and a budget of 40 tool calls or 15 minutes per task. Gemma 4 QAT models are served by vLLM in a 32,768-token window. A task counts as solved when its required tests pass with the agent's patch [1].

**Audit.** Before using the 129 practice tasks we ran each in the official Kaggle sandbox with the official fix and with no change. 71 are valid: the fix passes and the unchanged code fails (Table 1). Others had reported the 71 gold passes, the missing fastapi modules and the shadowed libraries [6]. Our audit adds a no-patch run and a cause for each invalid task. In all 14 requests and httpx tasks, the tests import the library installed on the host instead of the repository, so no patch can change the outcome.

*Table 1. Why 58 of 129 practice tasks are invalid in the official sandbox.*

| Cause | Tasks |
|---|---|
| test module missing from the image | 34 |
| tests import the host's installed library, not the repo | 14 |
| expected output depends on the environment | 5 |
| async test plugin missing | 2 |
| tests pass with no patch | 2 |
| required test skipped on Python 3.12 | 1 |

**Held-out tasks.** We mined fixes merged May–October 2026 in five projects outside the practice set (sqlglot, tomlkit, networkx, sympy, pyparsing). Of 114 tasks, 101 are valid in the Kaggle image. Graphs follow the released generator's rules, which reproduce the node ids of all 7 practice graphs, and embeddings come from a disclosed open model, since the released one is not public. Probes and runs use 24 tasks whose statement is an issue rather than a pull-request description, which often gives the fix away: 11 from sqlglot, 8 from tomlkit, 5 from networkx. Sympy's graph is too large for the graph tools.

## 3 The probe

<!-- DRAFT: user rewrites -->
We run the real agent loop against a server that records every request and keep two states per task: find, after the task prompt and before any code is read, and use, right after the agent has read the gold function. We then add one hint (Table 2) and score the correct next action, which is reading the gold function at find and making the gold edit at use. Its log-likelihood, computed with each model's own chat template, is measured in nats. Bigger is better and the scale is logarithmic: +1 nat makes the action 2.7 times more likely, +20 nats about 500 million times. Only the hint changes between conditions, and unlike a solve rate the measure does not sit at zero for small models.

*Table 2. Hints. L1–L5 are cumulative; the others are added alone. Wrong hints are length-matched.*

| Code | Added to the task |
|---|---|
| L1, L2 | the file; plus the function |
| L3, L4, L5 | plus the reproduction test; the change in words; the exact diff |
| W | the change in words only |
| G, G-null | graph-tool output around the gold function; around an unrelated file |
| X-file, X-func, X-graph | wrong file; wrong function; graph focused on a wrong function |

We also sample the actual next action (once at find, twice at use), classify it, apply each sampled edit on its own and run the task's required tests. Statistics are medians over tasks with bootstrap confidence intervals and Wilcoxon tests with Holm correction. Rescoring the same cell moves it by a median 0.2–0.6 nats. We probe 30 valid practice tasks with Gemma 4 E4B, 12B and 31B, and ran 12B end to end on the same tasks, once with no hint and once with the file, function and test names. The plan was committed before any GPU run, and the held-out criteria before any held-out data existed.

## 4 Results

### 4.1 Where helps finding, not fixing

<!-- DRAFT: user rewrites -->
With the file and function named, the correct first read becomes 19.4, 25.3 and 33.4 nats more likely for E4B, 12B and 31B (Figure 1). After the code has been read, the same hint moves the correct edit by +1.9, −1.8 and −1.5 nats. The pre-registered find-versus-use test holds for every size (Holm p < 0.001). A wrong file costs 9–19 nats against the right one, while a wrong function in the right file still helps, because the file is right. The description of the change, which says nothing about location, adds only 1–3 nats at find.

The held-out tasks give the same picture: +18.0, +21.2 and +31.5 nats at find, +1.7, +0.4 and −0.5 at use, and all four pre-registered criteria hold for all three sizes. Sampled actions mostly agree. On practice tasks the hint lifts first reads of the gold function from 3–13% to 93–97%. On held-out tasks E4B follows the hint every time. 31B reads the gold file first in only 1 of 24 tasks even with the hint, so making a read more likely does not make it the first move.

One prediction failed. The probe's per-task values did not predict which tasks the hint would rescue in real runs (AUC 0.43, and 0.27 once crashes were removed).

![Figure 1](figures/fig1_where_vs_what.png)
*Figure 1. Gain in log-likelihood of the correct next action over no hint (median, 95% CI). Filled: 30 practice tasks; hollow: 24 held-out tasks. Location helps before the code is read, the description of the change after.*

### 4.2 What to change matters more, and bigger models hesitate

<!-- DRAFT: user rewrites -->
At use, describing the change raises the correct edit by 11.4–14.4 nats on practice tasks and by about 22 on held-out tasks. The exact diff adds 29–42 and 107–125. The reproduction test adds 0.4–2.2 nats on practice tasks and 4–11 on held-out ones. Tests on sampled edits agree. On 27 paired practice tasks, E4B's edits pass in 20% of samples with no hint, 28% with the location and 37% with the description, and 31B's in 0%, 2% and 15%. Only E4B's description-versus-nothing difference survives correction (Holm p = 0.047), because few tasks change. On held-out tasks E4B passes in 10% of samples with no hint, 8% with the location and 56% with the exact diff.

The larger models fail differently from E4B (Figure 2). Right after reading the right code, 31B made no edit in 60 practice samples. It read more, ran a command or wrote a new script instead. With the exact diff in its prompt it edited in 46% of samples, and 20 of those 25 edits passed. On held-out tasks it edited once in 132 samples, and its most common first move without a hint was writing a new file (19 of 48). E4B edits in 58–88% of practice samples and is often wrong. We grade by tests, since exact matching would miss 54 of E4B's 65 passing practice edits below L5.

Full runs show the same habit. In the 24 held-out 12B runs the agent read files 442 times and ran 346 commands but called the edit tool 16 times, plus 15 file writes. Five runs were solved, and 17 ended on the time or tool-call budget.

![Figure 2](figures/fig2_hesitation.png)
*Figure 2. First sampled action right after reading the right code. Filled: practice tasks (95% CI); hollow: held-out tasks (L0, L2, L5 only). The larger models rarely edit, even with the exact diff.*

### 4.3 Graphs help by naming the file

<!-- DRAFT: user rewrites -->
At find, a graph-tool output around the gold function beats the same kind of output for an unrelated file by 6.5, 9.8 and 4.6 nats, close to what naming the file in text gives (6.3–8.2). Moving the graph's focus to a wrong function in the right file costs only 1.0–1.5 nats, against 11–20 for the same swap in text, and a sentence naming the function beats every graph by 7–29 nats. Graph node ids are dotted module paths, so any graph output names the file. At use, the unrelated graph does as well as the right one (gains of 0.5, 9.3 and 8.7 nats against 1.2, 7.5 and 5.3), so the gain there must come from the extra tool turn itself. Held-out tasks agree: the right graph wins at find by 4.3, 3.9 and 6.5 nats, and the unrelated graph matches or beats it at use.

### 4.4 The harness hides all of this

<!-- DRAFT: user rewrites -->
**Crashes.** vLLM refuses a request when the prompt plus the space reserved for the answer exceeds 32,768 tokens. The starter reserves 16,384, and ADK compacts only after the previous prompt has passed 14,336 tokens, so one long tool output can overflow before compaction runs. Participants had described this on the forum [4, 5]. We traced it ourselves in the vLLM and ADK source while working out why our runs crashed. In our first 12B runs, 14 of 30 no-hint runs and 9 of 30 hinted runs crashed this way, and all 7 tasks the hint seemed to rescue had crashed without it. With the reserve lowered to 8,192 (Figure 3), crashes fell from 14 to 0 (McNemar p = 0.0001), no-hint solves rose from 6 to 9, and the hint's advantage fell from 7 tasks to 4 (p = 0.29). One of the 24 held-out runs crashed, within the pre-registered limit.

**Compaction.** Around the tenth tool call, ADK replaces older history with a summary written by the model. The summarizer only reads text, so tool calls and their outputs are dropped, as another participant also found [7]. In all 137 compacted runs (113 practice, 24 held-out) the task prompt was among the summarized events. In the 82 runs where we checked every later request, none of 2,054 contained the original statement. The median summary kept 0–1% of the statement's five-word phrases and about a third of its words. The agent then edits from memory. Once practice runs stopped crashing, failed edits rose from 6 to 33. Of these, 32 tried to replace text that had never been in the file and 31 came after the first compaction. In one run, 11 edits repeated a replacement that had already failed. Held-out runs edited too rarely to add much (3 of 16 edits failed, all after compaction).

![Figure 3](figures/fig3_runs_ended.png)
*Figure 3. How 12B runs ended, before and after lowering the output reserve from 16,384 to 8,192 tokens. Most of the hint's apparent benefit was avoided crashes.*

## 5 Related work

<!-- DRAFT: user rewrites -->
Localization is often treated as the bottleneck. Oracle retrieval in SWE-bench [8], hierarchical localization in Agentless [9] and graph-guided agents such as LocAgent [10] all help, but giving the gold file raises resolve rates only modestly [11], and finer location context does not help repair [12]. Our probe fits these results together: location acts when the agent looks for code, and much less when it changes it. Repository graphs report gains [10, 13], and participants have audited the competition's graphs and embeddings [14] and rebuilt its generator [15]. What we add is a measurement of what a graph output does to the model's next decision, with an unrelated graph as the control. For context management, SWE-agent keeps the task while trimming old observations [16], and simple masking matches LLM summarization [17]. The summarizer here drops both the task and the tool outputs. Benchmark audits have found underspecified tasks and broken environments [18], and here some tests cannot see the patch at all. Several of our observations appeared first in forum posts [3–7], which we cite for priority; every number in this paper comes from our own runs.

## 6 Limitations

<!-- DRAFT: user rewrites -->
Each condition is a single run, and full runs are noisy (15% of tasks flip between identical passes [2]), so part of the change from 6 to 9 solves may be chance. The practice tasks come from two projects (fastapi, rich) and the held-out tasks from three, and the description rung exists for only 18 of the 24 held-out tasks. The graph condition is one synthetic tool turn, not a multi-step exploration. The descriptions of the change were written by 31B from the gold diff. The probe measures average value, not per-task outcomes. Held-out embeddings are a substitute.

## 7 Takeaways for builders

<!-- DRAFT: user rewrites -->
For small Gemma 4 agents we would tell the agent what to change, keep the task statement and the code it has read through compaction (masking old tool outputs instead of summarizing them does this), and set the output reserve so prompts fit. Pushing for early edits helps only once the agent knows the change. On its own, an edit deadline mostly produces wrong edits [3].

**Reproducibility.** Notebooks, frozen plans, analysis scripts and the figure script are released with the paper, and held-out tasks are rebuilt from public GitHub by script. No competition data is redistributed.

## References

[1] Kaggle. Google – The Gemma 4 Developer Agent: competition pages and public leaderboard, accessed November 2026.
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
[13] S. Ouyang et al. RepoGraph. ICLR 2025.
[14] J. Wold; A. Chinta; T. Singhal. Graph and embedding audits. Kaggle forum 742911, 745731, 744040, 2026.
[15] D. Mantiglia. codegraph-loc. GitHub, 2026.
[16] J. Yang et al. SWE-agent. NeurIPS 2024.
[17] T. Lindenbauer et al. The Complexity Trap. arXiv 2508.21433, 2025.
[18] OpenAI. Introducing SWE-bench Verified, 2024.
