# Pilot A (skills as weight-free post-training): interim report

Status 2026-10-30: **stopped at the GPU gate.** Everything that needs no GPU is built and checked
locally. **No GPU quota used yet (0 L4x4 h).** The next step needs your OK (estimate in §5).

Branch: `pilot/a-skills` (orphan, as requested; this environment's default branch was a
different one, `claude/epic-curie-mitb86`, and I left it untouched).

## 1. Environment

| Item | Found |
|---|---|
| Python | 3.13.17 (Kaggle image runs 3.12) |
| Docker | 29.9.2 client present (not needed; Kaggle uses the subprocess sandbox) |
| kaggle CLI | not installed. Installed `kaggle 2.2.5`. |
| `KAGGLE_API_TOKEN` | **not set**, but the session proxy injects your Kaggle credentials for `*.kaggle.com`. A dummy `~/.kaggle/kaggle.json` is enough, and listing/downloading competition files works. |
| Free disk | 31 GB |
| Downloaded (git-ignored, `data/`) | HARNESS_README, tasks.jsonl, sample_submission (no adapters), sandbox/docker files, 4 harness wheels, 1 small snapshot (`httpx_3672`, 1.5 MB) for a local dry run, e4b `config.json` |

## 2. What I did

1. **Harness study (step 1)**, written up in [docs/HARNESS_SKILLS.md](docs/HARNESS_SKILLS.md). Key facts:
   - **Skills are half-visible by default.** The model is told that skills exist and how to load
     them, but the list of names and descriptions is *never* put in the prompt (an ADK 1.36.1
     quirk: the list is only injected when there is no `list_skills` tool, and that tool is always
     there). Checked by compiling submissions with the real compiler and capturing the exact
     request. Fix: our arms list the skills in `system.md`. This is not a stop condition, but it is
     a design choice you should know about (Q1 below).
   - `load_skill` / `list_skills` / `load_skill_resource` are **free** for the tool-call budget.
     `run_skill_script` **counts** as one call. All of them cost an LLM turn and wall time.
   - Skill scripts run **inside the agent sandbox** (Container A), as `python3`, from a temp dir.
     Only `.py` is allowed (`.sh` fails validation).
   - Two traps I hit and fixed: (a) on Kaggle's subprocess sandbox, `/workspace` written inside a
     Python script points nowhere; (b) the harness's temp `.adk_exec_*.py` file sits in the repo
     while a script runs, and a careless `git add` would put it into the patch.
2. **Shared code in `common/`**: task loader with deterministic splits, ATIF trace parser,
   all shared metrics, and paired statistics (exact McNemar, paired bootstrap, seed-flip rate).
   Tested on a trace written by the harness's own `SessionTrace` class.
3. **Arms**: `build_submission.py` turns the official sample into any arm. Arms differ from the
   baseline only in the `skills/` folder and an appended skills section.
   - `baseline`: the starter agent on e4b (dummy 31B LoRAs removed, model lines switched).
   - `hand_written`: 3 skills: `reproduce-first`, `verify-before-submit` (with a pre-submit check
     script), `recover-from-failed-calls`.
   - `self_distilled`: `distill_skills.py` (runs on Kaggle). e4b reads digests of its *own failed*
     rich traces, names recurring mistakes (trigger → what to do instead), and merges them into
     2–4 skills. Temperature 0, thinking off, generic wording enforced, raw outputs logged.
   - `frontier`: I will write these after reading the same rich traces. They are labelled
     FRONTIER-WRITTEN and kept out of any main-track submission.
   - Controls ready if wanted: `--no-index` (plain ADK default visibility) and `inline_<arm>`
     (same text pasted into the system prompt, no skill tools).
4. **End-to-end dry run on CPU**: the real swegemma Evaluator on `httpx_3672`, subprocess
   sandbox, with a *scripted fake model* that lists skills, loads one, edits, runs the skill
   script, repeats a call, asks for a missing skill, and submits. Everything worked. The patch
   contained only the intended file, and the metrics read the trace correctly. All 4 arm
   folders pass the official `validate_directory`.
5. **Kaggle notebook** `notebooks/pilot_a_run.ipynb`: one file with the code embedded. Set
   `PHASE` and run all. It writes `pilot_a_<PHASE>.json` (aggregates and per-task metric rows only).

Task splits (ids in `pilot_a/splits.json`, sampled with a fixed seed):
- 10 rich tasks for building skills.
- 15 fastapi tasks for evaluation.
- Smoke test: the first 3 of the fastapi set.

Per-task budget for every arm (Q3): 15 min, 40 tool calls, 80 turns, 120 s per command.

## 3. Numbers

None yet. All results need GPU runs. The only "numbers" so far are harness facts (label: *verified-run on CPU*).

## 4. Surprises

- The skills list is missing from the default prompt, as described above.
- A rich problem statement is very short: median 139 characters, versus 677 for fastapi. Skills
  distilled from rich traces may therefore encode "how to work with almost no spec". That makes
  them a fairly hard cross-repo test.
- The e4b weights are 11.5 GB despite the int4 label (unquantized per-layer embeddings and
  vision/audio towers). They fit on T4 x2 by memory, but T4 has no bf16 (see `probe` phase).
- The starter's system prompt pushes for "under 8–10 turns". That works *against*
  "reproduce first" and "verify" skills. I kept it, because the baseline must be the starter
  agent, but it may suppress skill use.

## 5. GPU plan and estimates (awaiting your OK)

Per-task time for e4b is unknown until the smoke run. The estimates assume a typical 5–8 min per
task (setup, agent, verification) with 4 tasks in parallel. The worst case assumes every task
hits the 15-min cap. Each session also pays ~10–15 min of fixed setup (installing ~1 GB of wheels,
starting vLLM).

| Phase | Runs (arm × seed × tasks) | Task-runs | L4x4 wall h (typical / worst) | Quota h (2×) |
|---|---|---|---|---|
| **smoke** (ask now) | baseline + hand_written × 3 tasks | 6 | **0.4 / 0.7** | 0.8 / 1.4 |
| probe (optional, T4 x2) | baseline × 1 task | 1 | 0.4 T4 h | 0.4 |
| phase2 | baseline s1 × (10 rich + 15 fastapi) + self-distillation | 25 | 0.9 / 1.9 | 1.8 / 3.8 |
| phase3 | baseline s2 + hand_written s1, s2 × 15 fastapi | 45 | 1.4 / 3.0 | 2.8 / 6.0 |
| phase4 (only if budget) | self_distilled s1 + frontier s1 × 15 fastapi | 30 | 1.0 / 2.0 | 2.0 / 4.0 |

The core comparison (smoke + phase2 + phase3) is about **2.7 L4x4 h typical**, inside your 3 h
ceiling, but the worst case is about 5.6 h. After the smoke run I will extrapolate from measured
times. If the numbers point past 3 h, I'll cut tasks or the second seed and ask you first.

**How to run the smoke test:**
1. Upload `notebooks/pilot_a_run.ipynb` to Kaggle.
2. Attach the competition, the wheelhouse dataset and the `gemma-4-e4b-it-qat-w4a16-ct` v2 model.
3. Pick GPU L4 x4 and leave `PHASE = "smoke"`.
4. Run all.
5. Commit `/kaggle/working/pilot_a_smoke.json` to `results/`, or tell me the notebook slug and I'll pull the output with the CLI.

**Statistical power, honestly:** 15 tasks × 2 seeds gives 30 paired outcomes. Even if every
discordant pair goes one way, the exact McNemar test needs about 6 such pairs to reach p < 0.05.
Only a large change in resolve rate is detectable. The behaviour metrics (skill load rate,
repeats, failed edits, malformed calls) will be the more sensitive signal, and the seed-flip rate
tells us the noise floor.

## 6. Closest prior work (scan by a Sonnet sub-agent; arXiv ids opened, abstracts only)

| Work | Why close | Gap we could fill |
|---|---|---|
| **SkillLens** (arXiv 2605.23899, id from project page) | model-generated skills across extractor/consumer models, including SWE-bench. A small Qwen-9B consumer gained only +0.37. | no 4B model, no self-vs-frontier comparison from the *same* traces, no on-demand loading, no cross-repo split |
| **SWE-Skills-Bench** (2603.15401) | 98 public skills on real repos: 92 show no significant effect, some hurt by up to −17 | frontier agents only, hand-written skills only |
| **SkillsBench** (2602.12670) | curated skills +16.6 pp, self-generated −1.3 pp; models often "acknowledge skills but don't invoke them" | smallest model is Haiku 4.5; "self-generated" means written before solving, not distilled from failures |
| **Socratic-SWE** (2606.07412, confirmed) | trace → skills in SWE | its skills feed *training* (curriculum), not context-loaded at inference |
| CODESKILL (2605.25430), SKILLER (2608.10538), Skill-to-LoRA (2606.16769), Agent Memory Distillation (2608.07169) | RL-trained skill extraction; strong-model skills helping 4B/9B; literal "skill vs LoRA" at 27B; teacher memories to 4–8B students | none combines a 4B-class SWE agent, self-distilled skills from its own failures, and measured invocation |
| Older: ExpeL, AWM, ACE, Dynamic Cheatsheet, SWE-Exp, Reflexion, Voyager | experience-to-memory | not SWE, or frontier models, or injected (not tool-loaded) |

Competition-specific: I found public entrant repos with a `skills/` folder
(e.g. Peoplerepabulic/kaggle-gemma4-developer-agent, M4-on-Github/Gemma4_Dev_Agent_Kaggle).
None reports invocation rates or E4B results. The Kaggle discussion pages could not be read by the
sub-agent (JavaScript-rendered), so forum coverage is **incomplete**. Worth a manual look by you.

**Novelty warning (your CLAUDE.md ambition rule):** as framed, this pilot is a *measurement*
(does X help?), and SkillLens / SWE-Skills-Bench already measured similar things. What would be
new: a clean three-arm comparison built from identical traces on a 4B-class model, a cross-repo
split, and an invocation breakdown (never loaded / loaded but ignored / loaded and followed).
That still sits close to "measurement-only". To become a method paper it needs a mechanism.
One candidate: a distillation loop that accepts a skill only if it changes the targeted behaviour
on held-out traces (a verified skill-acceptance test).

## 7. Go / no-go

**Go for the smoke run only** (≈0.4 L4x4 h). It answers the questions that decide the pilot:
does e4b open skills at all, how long a task really takes, and is the baseline resolve rate
above zero on fastapi? If e4b resolves ~0/3 or never loads a skill, I'd recommend no-go for the
full study (or switching to 12b) before spending phase-2/3 quota.

Full version, if the pilot is promising (estimate; to be revised after smoke):
4 arms (baseline, hand-written, self-distilled, frontier) + 1 inline control, 2 seeds, ~40
cross-repo evaluation tasks (fastapi + requests):

| Item | Estimate |
|---|---|
| L4x4 time | ≈ 10–12 h (≈ 20–24 quota h) |
| Calendar | ≈ 6–8 days, given ~15 L4x4 h/week shared by four pilots and the 12 Nov deadline |

## 8. Questions for you (each changes the research question)

1. **Skill visibility.** I list skill names and descriptions in the system prompt in all skill
   arms. Without that, the model has to call `list_skills` first. Keep it (my default)? Or also
   run the plain-ADK `--no-index` arm to measure discoverability itself?
2. **Inline control.** Add an arm with the same skill text pasted into the system prompt (no
   loading)? It is the only way to tell "skills as a mechanism" from "just a longer prompt". It
   matters for the "like a LoRA" claim and costs about 0.5–1 L4x4 h.
3. **Per-task budget** 15 min / 40 calls. The main-track scorer default is 60 min / 100. A tighter
   budget saves quota but may hide gains from slower, more careful skills.
