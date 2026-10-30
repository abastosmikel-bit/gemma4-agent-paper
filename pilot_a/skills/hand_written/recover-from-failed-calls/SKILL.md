---
name: recover-from-failed-calls
description: Use whenever a tool call returns status "error" (FileEditError, CommandError, TimeoutExceeded, TypeError) or you notice you are about to repeat a call you already made. Says what to do instead of retrying the same call.
---
# Recover from failed calls

Rule 1: never send the exact same call twice in a row. If it failed once, it will fail again.

By error type:
- **FileEditError (old_string not found / multiple matches)**: call `read_file` on the exact lines first, then copy `old_string` from that output, 3 to 8 lines, including one distinctive line. If it matched several places, add one more surrounding line. Do not retype code from memory.
- **CommandError from pytest**: read the LAST lines of the output. `ModuleNotFoundError`/fixture errors that have nothing to do with your change are pre-existing; ignore them and test with /tmp/repro.py instead. An `AssertionError` in the test you targeted is real: re-read your fix.
- **TimeoutExceeded**: the command was too broad. Narrow it (one test file, `-x`, `-k name`), never rerun it unchanged.
- **TypeError / missing argument**: you called a tool with wrong argument names. `read_file(filepath, start_line, end_line)`, `edit_file(filepath, old_string, new_string)`, `run_command(command)`.
- **Output truncated**: re-run with `| head -n 60`, `| tail -n 60` or `grep -n` instead of reading everything.

If two different attempts at the same step failed, step back: re-read the problem statement and the function you are editing, then choose a different approach.

For quick searches use `run_command` with `grep -rn "name" --include=*.py <package_dir> | head -n 30`.
