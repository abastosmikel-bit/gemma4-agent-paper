# Gemma 4 Developer Agent — Paper Track

## The goal
Win a prize in "Google – The Gemma 4 Developer Agent Paper Track" (Kaggle) with ORIGINAL research
that advances agentic software engineering, centred on making Gemma 4 a better agent.
Not a remix of an arXiv paper. Not a pure repo-mapping paper (navigation may be one part).

## Ambition rule (the user's explicit priority)
- The contribution must be a NEW METHOD or mechanism: a new algorithm, training signal, agent-loop
  design, representation, or search/verification scheme that does not exist yet.
- Not acceptable as the core contribution: applying a published method to Gemma, prompt tuning,
  hyperparameter sweeps, ensembling known tricks, or measurement-only studies.
- Prefer a bold idea with a real chance of failing over a safe idea that will certainly work a little.
- Honesty still wins: if a bold method fails, the paper reports WHY, with evidence.

## Hard facts (re-verify on Kaggle before relying on them; Kaggle overrides this file)
- Paper deadline: 2026-11-12 23:59 UTC. Target internal submit: 2026-11-09.
- Writeup ≤ 3,000 words. Count title, abstract, captions and references until the host says otherwise.
- Judged 0–5 on five equal criteria: Novelty, Quality (generality beyond this competition),
  Relevance, Verifiability, Clarity. Prizes: Best Paper, Best New Resource, Best New Application.
- Host warning: purely LLM-generated prose scores badly. Tasteful LLM editing is fine.
- Competition data (tasks, graphs, embeddings) must NOT be redistributed. Release scripts that rebuild, not data.
- Main track model: gemma-4-31b-it-qat-w4a16-ct. Paper track names no required model.
  Small-footprint bonus in main track: Gemma E2B / E4B.

## Already taken (must cite and go beyond, never repeat)
- Graph audits: async gap, calls-only edges, collapsed embeddings, broken search_similar_code.
- codegraph-loc (ast graph generator + localization benchmark).
- Passing-tests-vs-solving / verifier gaming benchmark.
- OPSD / self-distillation for thinking-off agents, Hindsight Hint Distillation, Patches-to-Trajectories.
Keep research/novelty-map.md updated as you find more.

## Compute reality
- Kaggle only: max 30 GPU-hours per week (~85 h total until the deadline). No cluster, no paid GPUs.
- Budget: pilots ≤ 2 h each; all experiments ≤ ~65 h total; keep ~20 h buffer for reruns and final seeds.
- Track hours used in research/log.md (one line per run) and warn the user before a week's budget runs out.
- Prefer inference-time, harness, tooling, data or evaluation contributions over 31B training.

## Environment
- This runs in a fresh cloud environment on a private GitHub repo, not on the user's machine.
- The repo is the only persistent state: everything (notes, code, notebooks, results) lives in it.
- Commit and push at the end of every phase and after every experiment iteration.
- GPU work never runs here: write Kaggle notebooks to notebooks/, the user runs them on Kaggle and
  commits the result JSONs into results/.

## How the user works
- The user is the coordinator: he decides, you deliver. Explain results so he understands them;
  he is new to LLM agents, so define terms once, then move on. No condescension.
- Ask him only at the GATES below. Between gates, work autonomously.
- Never submit anything to Kaggle and never publish datasets. He does that himself.

## Model routing (save Opus for thinking)
The main session runs Opus. It decides, synthesises and designs; it does NOT do bulk reading itself.
Delegate by tier, always starting with the cheapest tier that can do the job:
- Haiku (`fetcher`, built-in `Explore`): fetching pages, pulling facts/tables out of forum threads and
  repos, grepping logs, parsing result JSONs, word counts, formatting. No judgment calls.
- Sonnet (`scout`, `experimenter`): reading and summarising papers, comparing related work,
  writing and debugging code, notebooks, statistics.
- Opus (`novelty-critic`, `reviewer`, `deep-thinker`): only for judgment that decides the paper —
  attacking ideas, designing a new mechanism, diagnosing why a method fails, scoring the draft.
Escalation: if a cheaper agent's output is shallow or wrong, rerun that task one tier up (pass the
`model` parameter on the call) and note it in research/log.md. Never start at Opus "to be safe".
Batching: send ideas, results or drafts to Opus agents in ONE batched call, not one call per item.
Keep subagent reports short: ask for tables and bullet findings, not essays.

## Research integrity (non-negotiable)
- Every claim in the paper must map to a row in research/claims.md with the evidence file and run ids.
- Report negative and weak results as they are. Never call something verified that wasn't run.
- Any number from a single run is labelled "single run". Use ≥2 seeds and paired comparisons for headline claims.
- Distinguish: measured / estimated / hypothesised. Mark each.
- If an idea turns out to exist already, say so immediately and log it in novelty-map.md.

## Files you maintain
- research/novelty-map.md — prior work, what each does, the gap it leaves.
- research/ideas.md — candidate ideas with scores and kill reasons.
- research/log.md — experiment log (one entry per run, keep/discard decision).
- research/claims.md — claim → evidence → status.
- paper/ — outline, figures, tables, and DRAFT prose (see Writing).

## Writing
- You produce: outline, figures, tables, method details, related-work notes, and DRAFT paragraphs
  clearly marked `<!-- DRAFT: user rewrites -->`.
- The user rewrites the prose in his own voice. You then edit for clarity and word count.
