# Pilot C — D2 held-out rollouts, 12b, C06 configuration: pre-registered plan (`notebooks/D2_heldout_rollouts_12b__L4x4.ipynb`)

Status: written 2026-11-02, before any D2 run and before D0b's output exists. Frozen when committed, together with
`pilot_c/heldout.py` (selection, shared with D1), the analysis code `pilot_c/analyze_d2.py` and the dev reference
`results/D2_dev_reference.json`. The commit hash is written into the notebook (`PLAN_COMMIT`) and into `docs/HISTORY.md` on
`paper/main`. Later changes go into §10 with date and reason.

Spec this follows: `docs/D_SPECS.md` on `paper/main` (02381e4), pilot D. Known before the run: C05, C06 and the
context-window repro (`docs/CLAIMS.md`, claims 2 and 4).

## 1. Question

On held-out tasks, with the paper's agent configuration (official sample agent, 12b, `max_output_tokens` 8192):
1. Does compaction still erase the task statement (claim 2)?
2. Does the 8192 fix still prevent context-window crashes (claim 4)?
3. What is the held-out solve rate?

## 2. Design (C06's no-hint arm on the D1 task set)

- **Tasks:** the D1 task set: `pilot_c/heldout.py`, `docs/D_SPECS.md` rules 1–6 (issue statements only, sympy excluded),
  seeded sample of N = 24 (at most 12 per repo). The rule is deterministic, so D2 computes the same set as D1 from the
  same export. If D1's `D_selection.json` is attached, its list is used and any difference is recorded.
- **Agent:** the official sample agent with adapters removed, 12b, starter vLLM settings, 40 tool calls / 15 min /
  120 s per command. `configs/sampling.yaml` gets `max_output_tokens: 8192` (C06's change); thinking budget stays 4,096.
- **Condition:** O0 (no hint), 1 run per task, concurrency 5. Two batches of 12 tasks so results are saved half-way.
  No sequential rule (there is no comparison).
- **Instrumentation:** C06's, unchanged (`common/runtime_probes.py`): per request, where the task-prompt marker comes from
  (original prompt / summary / elsewhere), whether the original prompt is present, requested output tokens, prompt
  tokens, context errors; per summary, the statement's 5-gram and word retention. Summary text stays in `private/`.
- **Test-only dependencies:** the subprocess sandbox uses the host's packages, so the export's test wheels that the image
  lacks are installed first (offline, no dependencies, nothing already installed is replaced), as D0b did.
- **Failed-edit replay:** after the runs, `pilot_c/edit_failures.py` replays each trace on CPU (as for C06) and writes
  counts only (`D2_failed_edits.json`).

## 3. Outcomes

- `resolved`: scorer rule (harness resolved and a non-empty patch).
- How a run ended: resolved / context crash (`ContextWindowExceeded`) / time budget / tool-call budget / other.

## 4. Replication criteria (frozen; from `docs/D_SPECS.md`)

- **R6 — claim 2.** Among runs that compact, **0** post-compaction requests contain the original task statement (and
  0 carry the marker from the original prompt). Not evaluable if no run compacts. Dev (C06, O0): 0 of 759 requests in
  30 compacted runs.
- **R7 — claim 4.** At most **1** of the runs ends in `ContextWindowExceeded`. Dev (C06, O0): 0 of 30.
- **Solve rate:** resolved / runs with a Wilson 95% CI. Reported, not tested against dev (the repos differ). Dev
  (C06, O0): 9/30.

## 5. Analysis (code: `pilot_c/analyze_d2.py`; the notebook's last cell; tested on synthetic data)

- R6 and R7 with verdicts; solve rate with its Wilson CI; how runs ended; compaction (runs compacted, requests after
  the first compaction by marker source, summaries with the marker); statement retention per summary (5-gram and word);
  context numbers (requested output tokens, maximum prompt tokens, context errors); failed edits, and those after the
  first compaction; the shared metrics (wall time, tool calls, repeated-call share, malformed share, failed edits, skill
  calls); the tool mix.
- **`search_similar_code` share** of all tool calls: that tool runs on pilot D's substitute embeddings. It counts as
  negligible below 5%. If it is not negligible, dev vs held-out differences may partly reflect this tool. Dev: 0.9%.
- **Setting check:** every request must have asked for 8192 output tokens.
- Dev column: the same code on C06's no-hint runs (`results/D2_dev_reference.json`; dev summary retention there is the
  per-run mean, as the summary files stay on Kaggle).
- Figures: `D2_fig1_how_runs_ended.png`, `D2_fig2_summary_retention.png`. Outputs: `D2_analysis.json`, `D2_tables.md`.

## 6. Exclusions

None. Harness errors count as unresolved, as the scorer counts them.

## 7. Not in the main version

- O-all (the location hint) on the same tasks: an add-on, ≈ +1.1 h, direction only. C06 measured the hint effect at +4
  net on 30 dev tasks (p = 0.29); N ≈ 24 cannot test it.

## 8. What it can and cannot show

- One run per task on N ≈ 24 post-cutoff tasks from 3 repos outside the dev set; labelled as a single run.
- Claims 2 and 4 are mechanism claims (what compaction keeps; whether the prompt fits), so a held-out check tests whether
  they depend on the dev repos. The solve rate depends on the repos and is not compared with dev.

## 9. Cost (L4x4 hours, from C06's measured run times)

- C06's no-hint runs: mean wall 728 s per task at concurrency 5 (C06 batches of 15: 40.7 and 40.9 min).
- 24 tasks in two batches of 12: 2 × (12 × 728 s / 5 + tail) ≈ 1.05 h; plus ≈ 0.17 h fixed (install, selection and
  gold locations, test wheels, server start and stop, failed-edit replay).
- **≈ 1.25 h (range 1.1–1.6;** 1.6 if every run uses its full 15 minutes). Hard stop 2.0 h: a batch starts only if it
  fits (728 s per task × 1.3).

## 10. Deviations

None yet.
