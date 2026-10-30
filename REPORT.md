# Pilot A (skills as weight-free post-training): interim report

Status 2026-10-30: **stopped at the GPU gate; plan rethought in §8 (recommendation: pivot to direction B).** Everything that needs no GPU is built and checked
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

## 8. Rethink (added before any GPU run; still 0 GPU hours)

Labels: **verified-run** = checked by running the harness code on CPU. **read** = from reading
source, not run. **estimate** / **hypothesis** = not measured.

### 8.1 The question one level up

A skill is not a weight change. It is text that only changes behaviour if it gets through a chain
of steps. Its expected benefit is roughly a product:

> benefit ≈ P(**exposed**) × P(**retrieved** when its trigger occurs) × P(**still in context** at that
> moment) × P(**complied with**, given it is in context) × **gain** of the complied action

| Factor | Meaning | Your four failure causes |
|---|---|---|
| exposed | the model knows the skill exists | (not in your list: the harness default) |
| retrieved | it calls `load_skill` for the right skill | never retrieved |
| in context at trigger | loaded before the moment it applies, and not yet dropped | retrieved at the wrong moment |
| complied | its next actions follow the guidance | model too small to act on it |
| gain | following the guidance actually helps | wrong content |

So the higher-level question is:

**Where along this chain does procedural guidance get lost in a small agent, and is the loss a
property of the model or of the delivery channel?**

This also sharpens the LoRA analogy. A LoRA skips the first three factors: it is always on, needs
no retrieval and uses no context. "Can skills act like a LoRA?" therefore splits into two
questions. First, can the delivery factors be pushed to ~1 cheaply? Second, once they are, is a
4B model's compliance high enough to matter?

It also explains the prior nulls. Each factor is below 1, and they multiply. An end-to-end resolve
rate on a few dozen tasks measures only the product, so a null cannot say which factor broke.
SkillsBench and SWE-Skills-Bench report end-to-end effects. Neither decomposes them (abstract-level reading).

### 8.2 What this harness can and cannot separate

| Factor | Observable in swegemma traces | How we can manipulate it |
|---|---|---|
| exposure | catalog in prompt or not | hidden (ADK default) / indexed / inline: all three already buildable |
| retrieval | `load_skill` calls, which skill, at which step | inline removes it; description wording |
| in context at trigger | step of load vs step of trigger; `compaction` events are in the trace (parser already counts them) | inline (system prompt survives compaction) vs on-demand |
| compliance | only if a skill's prescribed action is observable, e.g. "after a `FileEditError`, the next call is `read_file` on that file" | inject the guidance exactly at the trigger (replay, direction B) |
| gain | **per-event** outcomes: does the retried edit succeed, does the repeat stop | same |

Per-event outcomes are the key to statistical power. A task has one resolved/unresolved bit but
many trigger events (errors, edits, submits). Hundreds of events give power that 30 paired task
outcomes never will.

What the harness cannot separate on its own:
- **Content vs capacity when compliance is low.** Partial fix: frontier-written content as an upper
  bound on content quality, and a larger Gemma as an upper bound on capacity.
- **Causal gain from observed compliance.** Fix: an intervention (replay), not correlation.

### 8.3 What the evidence says so far

- **Exposure is ~0 by default** (verified-run). ADK 1.36.1 never puts the skill catalog in the
  prompt. Every competitor who drops a `skills/` folder into a submission without listing the
  skills in the prompt is running a near-inert skill library, and an end-to-end metric would show
  only a null. So yes: your hunch is right, the hidden names are part of the answer, not a setup detail.
- **On-demand skills have a short lifetime in this harness** (read).
  - The mechanism: ADK's compaction summariser formats only plain *text* parts and drops every
    function call and function response (`apps/llm_event_summarizer.py`). A body returned by
    `load_skill` is a function response, so it is not even summarised. It disappears at the next
    compaction.
  - What survives: the system instruction, and with it an indexed catalog or inlined skills.
  - Who sets it: the scorer's `inference.py` (threshold 14,336 tokens, last 5 events kept). It
    is part of the target environment, not something a submission can change.
  - Estimate: `read_file` returns up to ~2.5k tokens, so the threshold is crossed after roughly
    5–10 calls. A skill loaded at the start is likely gone before its trigger fires late in the
    episode. Hypothesis until phase-2 traces count compactions.
  - The original task prompt is a text part, so it gets *summarised*, not kept verbatim (read).
- **The baseline already contains inline guidance** (read). The starter `system.md` is a
  workflow-plus-anti-patterns skill set. It overlaps with my hand-written skills (targeted tests,
  don't touch tests) and tells the model to finish in 8–10 turns. Baseline vs hand-written would
  therefore measure a small marginal content gain, delivered through the weakest channel,
  against an instruction to hurry. A null there would teach us nothing.
- **Prior work** (abstract-level) points at retrieval and compliance, not just content:
  - very small models fail to select skills (2602.16653);
  - models ≤7B often ignore even oracle-retrieved context (2603.11513, QA only);
  - agents "acknowledge skills but don't invoke them" (SkillsBench);
  - harmful skills anchor agents on templates (SWE-Skills-Bench), so compliance can also be *too* high.
- **No Gemma behaviour has been measured yet.** Everything above is about the channel, not the model.

### 8.4 Is the four-arm experiment the right one?

Mostly no, for four reasons.
1. **It varies the wrong factor.** It changes content source (hand / self / frontier) and holds
   delivery fixed at the weakest channel (hidden-or-indexed, on demand, compacted away). If most
   loss is in delivery, content differences are invisible.
2. **It is underpowered.** 30 paired task outcomes detect only large resolve-rate changes. Content
   differences in prior work are a few points.
3. **Content is confounded with retrieval.** Better-written descriptions get loaded more often.
   "Frontier skills help" could just mean "frontier descriptions get clicked".
4. **"Like a LoRA" is not testable as designed.** There is no always-on condition (and no real
   LoRA). What we *can* test is always-on in-context vs on-demand.

Keep the three content sources, but compare them where delivery is held fixed (direction B).

### 8.5 Three reframed directions

**A. Guidance funnel (diagnostic).**

Design:
- Conditions: baseline, hidden catalog (ADK default), indexed catalog, inline (always on).
- All conditions use the same three hand-written skills, rewritten so each has an observable
  trigger and an observable prescribed action.
- Tasks: 15 fastapi × 1 seed.
- Each funnel factor is measured from the traces.

| | |
|---|---|
| **Claim** | "For a 4B agent in a compacting harness, most of a skill's potential effect is lost at stage X". Plus a concrete platform finding: ADK's default and its compaction make on-demand skills near-inert. |
| **New vs prior** | Prior work reports end-to-end effects. This locates the loss, with delivery under experimental control. I found the compaction mechanism in no scanned skills paper (to my knowledge; needs a check). |
| **Weakness** | A diagnostic, not a method. Alone, it fails your ambition rule. |
| **L4x4 cost** | phase-2 baseline 0.9 h + 45 runs ≈ 1.4 h typical (3.0 worst) → **≈ 2.3 h** plus smoke |

**B. Counterfactual trigger replay: an acceptance test for skills (method).**

*Prefix replay*, defined:
1. Take a baseline trace.
2. Cut it just before a trigger event, e.g. right after a `FileEditError`.
3. Rebuild the conversation up to that point.
4. Ask the model for its next action twice: as it was, and with the skill text inserted at that
   moment.
5. Compare the two next actions.

Each sample is one generation, with no sandbox, so it is cheap and yields hundreds of events.

Each skill carries a *contract*:
- a trigger predicate (when it applies, checked on the trace);
- an action predicate (what the next call should look like);
- the text itself.

All three distillers (hand, self, frontier) must emit the contract.

What it is for:
1. **Measure compliance directly**, per content source, with delivery held fixed. This fixes the
   four-arm design.
2. **Separate "too small to act" from "not retrieved".** If behaviour does not shift even when
   the skill is injected at the right moment, the problem is the model or the content, not the
   delivery.
3. **Verified self-distillation.** e4b's own distilled skills are kept, or rewritten using the
   replay feedback, only if they shift the next action on *held-out* prefixes. Then one
   end-to-end check validates the result.

The cross-repo test stays: skills come from rich traces and are replayed on fastapi prefixes.

| | |
|---|---|
| **Claim** | (hypothesis) Next-action replay predicts end-to-end skill value at a fraction of the cost. Replay-verified self-distillation turns a 4B model's own failures into skills that change its behaviour, where unverified distillation (SkillsBench: −1.3 pp) does not. |
| **New vs prior** | SkillLens / SkillsBench / SWE-Skills-Bench evaluate end to end. CODESKILL trains an extractor on end reward. A trigger-conditional counterfactual replay as an acceptance test, plus skills with checkable contracts, is not in the work scanned so far. **Needs a targeted novelty check before committing** (no GPU, a Sonnet scout). |
| **Risks** | (1) Rebuilding faithful context (thinking blocks, compaction summaries) is fiddly, so start with prefixes before the first compaction. (2) A next-action shift may not turn into resolved tasks; the end-to-end check tests exactly that. (3) It needs enough trigger events in baseline traces (likely for e4b; kill criterion below). |
| **L4x4 cost** | phase-2 baseline 0.9 h + replay ≈ 0.5–1 h (estimate: a few hundred prefixes × 4 conditions × 2 samples, prefix-cached) + one end-to-end validation (2 conditions × 15 tasks) ≈ 1.0 h → **≈ 2.4–2.9 h** plus smoke |

**C. Does the bottleneck move with model size? (generalisation).**

Design: run the funnel and the replay on e2b, e4b and 12b.

| | |
|---|---|
| **Claim** | "Load-on-demand pays only above a size threshold. Below it, guidance must be always-on." A design rule for any small-model agent platform. |
| **New vs prior** | I found no work that maps where skill effects are lost against model size within one family. |
| **L4x4 cost** | baseline traces for e2b and 12b (15 fastapi tasks each, ≈ 0.5 + 1.2 h; 12b timing is a guess) + replay ≈ 0.5 h each → **≈ 3 h on top of B**. Beyond the pilot ceiling; full-study only. |

### 8.6 Recommendation

**Make B the core, use A's delivery ladder as B's end-to-end check, and do C only if B works
and quota remains.**

- **Why B:**
  - It is the only direction that is a *method* (replay-verified distillation of skills with contracts).
  - It has the statistical power that end-to-end runs lack.
  - It keeps the cross-repo split and all three content sources.
  - It answers the higher-level question (delivery vs compliance) by intervention, not correlation.
- **Why not A alone:** it is a measurement paper.
- **Why not C now:** it does not fit the budget.

**Unchanged:** the next GPU steps. Every direction needs the smoke run and then the phase-2
baseline traces. I suggest extending the smoke run from 2 to 4 delivery conditions
(baseline / hidden / indexed / inline × 3 tasks). It would show early whether e4b ever loads a
skill, and whether compaction fires before triggers. That costs ≈ 0.7 h typical (1.4 h worst)
instead of 0.4.

**Budget honesty:** B plus the extended smoke run is ≈ 3.1–3.6 h typical, slightly over your 3 h
pilot ceiling. Ways to fit:
- keep the 2-condition smoke run (−0.3 h); or
- validate end to end on 10 instead of 15 tasks.

**Code still to write (no GPU, ~1 day):**
- the replay tool (rebuild an OpenAI-format conversation from an ATIF trace and query vLLM);
- skill contracts and trigger/action detectors;
- make the distiller emit contracts;
- fix the inline arm (its `verify-before-submit` text refers to the script tool, which is absent there).

**Kill criteria:**
- **Too few trigger events:** phase-2 traces show fewer than ~50 across 25 tasks. Then replay
  lacks power: fall back to A.
- **No shift at all:** replay shows no next-action shift for *every* skill, frontier-written
  included. Then the answer is "too small to act". Report that, and consider 12b before spending
  more.

## 9. Open questions, revisited after the rethink

1. **Skill visibility** (was: index on or off?). No longer a default for me to pick. It is the
   *exposure* factor, so both hidden and indexed become experimental conditions. Hidden is also
   what a typical competitor's submission does. **OK to treat it as a factor?**
2. **Inline control** (was: optional). Now **essential**. It is the always-on condition, the only
   in-context analogue of a LoRA, and the only skill text that survives compaction. Needs the
   small fix noted in 8.6.
3. **Per-task budget 15 min / 40 calls.** Keep it for end-to-end runs (cost). But it now
   interacts with the question: longer episodes mean more compactions, so more loss of on-demand
   skills. Compaction counts will be reported per task. Replay (B) barely depends on the budget.
   If most tasks hit the cap in phase 2, the validation run should use 60 calls.
4. **New: pivot to direction B** (replay-verified skills, with A as its end-to-end check)?
5. **New: extended smoke run** with 4 delivery conditions (≈ 0.7 h typical, 1.4 h worst), or the
   original 2 conditions (≈ 0.4 h)?

Original questions as first asked:

1. **Skill visibility.** I list skill names and descriptions in the system prompt in all skill
   arms. Without that, the model has to call `list_skills` first. Keep it (my default)? Or also
   run the plain-ADK `--no-index` arm to measure discoverability itself?
2. **Inline control.** Add an arm with the same skill text pasted into the system prompt (no
   loading)? It is the only way to tell "skills as a mechanism" from "just a longer prompt". It
   matters for the "like a LoRA" claim and costs about 0.5–1 L4x4 h.
3. **Per-task budget** 15 min / 40 calls. The main-track scorer default is 60 min / 100. A tighter
   budget saves quota but may hide gains from slower, more careful skills.
