Read CLAUDE.md fully. We are entering the Gemma 4 Developer Agent Paper Track. Today is 2026-10-21;
the paper is due 2026-11-12. Your job is to run a real research programme, not to write a survey.

Work in four phases. Use subagents for breadth, and keep the main thread for judgment and synthesis. Follow the Model
routing section in CLAUDE.md: Haiku for fetching, Sonnet for reading and code, Opus only for judgment.
Commit to git at the end of every phase.

## PHASE 0 — Ground truth (today)
1. Use `fetcher` (Haiku) to collect raw material and `scout` (Sonnet, several in parallel, one per
   area) to read and summarise: the paper track Overview, Rules
   and every forum thread; the main track Data/Evaluation/Rules; public writeups, notebooks and repos
   about this competition; and 2026 papers on SWE agents, small/local coding agents, tool-use failure
   modes, agent harness design, test-time compute for agents, and code graphs.
2. Build research/novelty-map.md: for each prior work, its claim, method, evidence, and the gap it leaves.
3. Mine failure modes: from public trajectories/logs and forum reports, list what concretely goes wrong
   for Gemma 4 as an agent (looping, malformed calls, context overflow, wrong localisation, premature
   finish, test gaming...). Quantify where data exists.
Output: a one-page summary for me of the landscape and the 5 biggest open gaps.

## PHASE 1 — Invent, then try to kill
Read the Ambition rule in CLAUDE.md first. We want a new method, not a better-tuned old one.

1. Generate at least 25 candidate METHODS. Every candidate must answer: "What does the agent or model
   do that no published system does?" Use each generator at least three times:
   - First principles: from the quantified failures in Phase 0, derive what an ideal agent would need,
     ignoring how current agents are built. Then design the mechanism that provides it.
   - Assumption inversion: take a design choice every SWE agent shares (one model call per step,
     text-only actions, linear trajectories, fixed thinking, tests as the only verifier, a single
     context window...) and build an agent where that choice is reversed.
   - Cross-domain transplant: a concrete mechanism from compilers, databases, OS scheduling, control
     theory, game-tree search, program synthesis, neuroscience, or distributed systems, turned into an
     agent mechanism. Name the source mechanism precisely.
   - Combination nobody tried: two ideas from different fields whose combination creates a new
     capability (not just additive gains).
   - Small-model-native: a method that only makes sense because the model is small/local (cheap
     repeated calls, white-box access to logits/hidden states, LoRA hot-swapping, etc.).
2. Auto-reject, before the critic sees them: "apply paper X to Gemma", prompt/hyperparameter tuning,
   pure benchmarks or audits, and anything already in novelty-map.md.
3. For each survivor write: the mechanism in 3 sentences, why it might work, why nobody has done it
   yet (a real reason, not "nobody thought of it"), the cheapest falsifying experiment, GPU-hour cost.
4. Send all survivors to `novelty-critic` in one batched call. It kills prior work, confounds, infeasibility AND
   incrementalism.
5. Score survivors 0–5 on: Novelty (counts double), Ambition (counts double), Quality, Relevance,
   Verifiability, Feasibility in our compute. Keep the top 3. At least 2 of the 3 must be high-risk.
6. For each, design a pilot (≤ 2 GPU-h) whose result would clearly show signal or kill the idea.

GATE 1: Present the top 3 to me with the pilot plans, honest odds, and your recommendation.
Stop and wait for my choice.

## PHASE 2 — Experiment loop (until ~2026-11-04)
Run this loop. One iteration = one hypothesis.
  a. Write the hypothesis and the predicted result in research/log.md BEFORE running.
  b. Implement the smallest change that tests it. Use the `experimenter` subagent for code and runs.
     Prepare Kaggle notebooks; I push and run them when needed, then give you the outputs.
  c. Analyse: compare against baseline with seeds and paired tests. Record measured numbers.
  d. Decide KEEP, DISCARD or PIVOT. Update claims.md.
     - If it works: push it. Find its limit, scale it, make it stronger, remove crutches.
     - If it fails: find out WHY (inspect trajectories, logits, failure cases) and try at least one
       principled variant before discarding. A failure explained is a finding.
     - PIVOT when a result reveals a more interesting question than the one you asked.
     For the hard "why did it fail / what should the mechanism be" questions, use `deep-thinker`.
  e. Every 3 iterations, ask `novelty-critic` to re-attack the method, and to check for drift:
     has the work quietly turned into safe tuning? If yes, return to the core mechanism.
  f. Spend at least a third of iterations on bold variants, not only refinements of what works.
Requirements before leaving this phase:
  - At least one held-out evaluation beyond the public fastapi/rich tasks (generality = Quality score).
  - Ablations that isolate each component of the method.
  - At least one result that explains WHY the method works, not only that it does.
GATE 2 (around 2026-11-01): show me the results table and the story they support. If the method
failed, propose the honest paper: the new method, the evidence for why it fails, and what that teaches
about agents. Wait for my go-ahead.

## PHASE 3 — Paper (2026-11-04 → 2026-11-09)
1. Build paper/outline.md: title, abstract, intro, method, experiments, related work, limitations.
2. Make figures and tables from scripts in the repo so every number is reproducible.
3. Write DRAFT paragraphs marked for my rewrite. Keep total ≤ 2,800 words to leave margin.
4. Loop with the `reviewer` subagent: it scores the draft on the five criteria as a strict judge and
   lists the top fixes. Apply fixes and re-review until two rounds in a row show no score gain.
5. Prepare a public reproduction notebook/repo plan that respects the no-redistribution rule.
GATE 3: hand me the final package and a submit checklist. I submit myself.

General rules for the whole run:
- Think hard before each phase and before each KEEP/DISCARD decision.
- Prefer one new, well-evidenced mechanism over many shallow tweaks. Novelty over safety.
- If you are about to repeat prior work, stop and say so.
- Keep me informed with short status notes at the end of each phase, in plain language.
