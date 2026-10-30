---
name: reproduce-first
description: Use at the START of every bug-fix task, before editing any file. Shows how to turn the problem statement into a tiny script in /tmp that fails now and will pass once the bug is fixed.
---
# Reproduce first

Goal: before changing code, have one command that shows the bug.

1. Find the smallest public call that shows the problem (a function, a class, a CLI call or a request to an app). Take names and expected values straight from the problem statement.
2. Write the script to **/tmp/repro.py**, never inside /workspace (files in /workspace end up in your patch):
   `write_file` cannot write outside /workspace, so use
   `run_command` with: `cat > /tmp/repro.py <<'PY' ... PY`
3. Make it assert the expected behaviour, e.g. `assert result == expected, result`.
4. Run it: `cd /workspace && python3 /tmp/repro.py`.
   - It fails the same way the issue describes: good, now locate and fix the code.
   - It passes already: your reproduction is wrong. Re-read the problem statement before editing anything.
   - ImportError for the package: run from /workspace, the package is installed in editable mode.
5. After your fix, run the same command again. It must pass before you call `submit_patch`.

Keep the script under 30 lines. Do not try to write the project's real test; the graders bring their own tests.
