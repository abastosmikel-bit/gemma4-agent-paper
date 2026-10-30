---
name: verify-before-submit
description: Use right AFTER you edit source files and BEFORE you call submit_patch. A short checklist (with a script) that catches broken edits, stray files and untested fixes.
---
# Verify before submit

Run the checklist script first. It compiles every changed .py file, shows the diff summary and lists files that would wrongly go into your patch:

`run_skill_script(skill_name="verify-before-submit", file_path="scripts/check_patch.py")`

Then:
1. Every changed file compiles (the script prints `COMPILE OK`). If not, fix the syntax error first.
2. The diff only touches source files you meant to change. Revert accidental edits with `git checkout -- <file>`.
3. No new files in /workspace except real source files (scratch scripts belong in /tmp).
4. Run your /tmp/repro.py again and the most relevant existing test file only, e.g. `python3 -m pytest tests/test_x.py -q -x`. Never run the whole test suite.
5. Re-read the problem statement once: exact error messages, names, status codes and defaults must match it.
6. Only then call `submit_patch`.
