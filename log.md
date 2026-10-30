# log

## 2026-10-30 — Pilot A step 1 (harness skill exposure), 0 GPU-h
- Pulled HARNESS_README, sample_submission, tasks.jsonl, starter notebook and harness wheels via Kaggle CLI into vendor/ (gitignored, not redistributed).
- Read skill path in source myself (Opus) instead of delegating: it decides the pilot's go/no-go and needed line-level reading.
- Finding: ADK 1.36.1 SkillToolset never injects skill names/descriptions (list_skills always present); model only sees generic text + 4 tools. run_skill_script counts toward tool_calls; others don't. Scripts run in Container A, cwd = tempdir, .py only.
- Decision: KEEP pilot, add visibility factor (V0 default / V1 index in instruction) and flag inline-prompt control. Write-up: research/pilot-a/01-harness-skills.md
