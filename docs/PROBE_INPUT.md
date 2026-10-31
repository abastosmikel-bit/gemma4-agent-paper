# Probe input — what pilot C's information-ladder probe needs per task

Owner: pilot C (`pilot/c-bottleneck`). Consumer of held-out tasks from pilot D. Version 2, 2026-10-31
(v2: `test.source` rule changed, pure-deletion anchor; see PLAN §11 on `pilot/c-bottleneck`).
Code that reads this: `pilot_c/probe.py` (`build_probe_record`) on branch `pilot/c-bottleneck`.

There are two levels. **Level A is what pilot D should export.** Level B is derived from Level A by
CPU code; it is documented so D can check what the probe will see, or supply it directly if a
snapshot is impossible.

## Level A — competition layout (preferred)

A directory laid out exactly like the competition data:

| Path | Format |
|---|---|
| `tasks.jsonl` | one JSON object per line, fields below |
| `snapshots/<instance_id>.tgz` | gzip tar of the repo working tree at `base_commit`, member paths prefixed `./`, includes `.git` whose history ends at `base_commit` (fast-export → fast-import, branch `main`); must install offline with `pip install --no-index --find-links=/wheels --no-deps -e .` |
| `graphs/<repo_short>_<base_commit>.json` | NetworkX node-link JSON: `{"directed": true, "multigraph": true, "graph": {}, "nodes": [{"id", "name", "text"}], "edges": [{"source", "target", "type", "key"}]}`; node ids are dotted symbol paths with no leading `src.` (e.g. `requests.models.Response.json`), test code included as `tests.*`, edge `type` e.g. `calls`. Say which generator you used. |
| `embeddings/<repo_short>_<base_commit>.npz` | optional (only `search_similar_code` needs it; the probe does not) |
| `wheels/*.whl` | any extra offline wheels the repo's tests need |

`tasks.jsonl` fields (all strings):

| Field | Content |
|---|---|
| `instance_id` | unique, `[A-Za-z0-9_.-]+`, convention `<repo_short>_<number>` |
| `repo` | `owner/name` |
| `base_commit` | 40-hex SHA |
| `patch` | reference fix as a unified diff: `--- a/<path>` / `+++ b/<path>` / `@@ -a,b +c,d @@`, repo-relative paths, non-test source files only, no `diff --git` header needed |
| `test_patch` | unified diff adding/changing test files; the **required tests** are the `def test_*` functions it adds (the scorer's rule; if none are added, the test functions named in hunk headers/context) |
| `problem_statement` | the issue text as a user would write it (no fix hints) |
| `hints_text` | usually `""` |
| `created_at` | ISO-8601 |

Hard requirements per task (`notebooks/C00_gold_check__CPU.ipynb` on `pilot/c-bottleneck` checks 1–2 and writes `C00_gold_check.json`):
1. the gold patch applies and the required tests pass in the subprocess sandbox;
2. with **no** patch the same verification fails (otherwise any harmless edit "solves" it);
3. probe eligibility: exactly one changed non-test `.py` file that exists at `base_commit`; the change
   lies in 1–2 enclosing functions/classes (module-level edits such as imports may come in addition);
   ≤ 40 changed lines; ≥ 1 required test name.

Tasks failing 1–2 are excluded and reported. Tasks failing 3 can still be used for agent rollouts, but not for the probe.
Data rule: commit task IDs and rebuild scripts, never task content.

## Level B — derived probe record (what the probe consumes)

One JSON object per task (built on CPU from Level A):

```
instance_id, repo, base_commit, problem_statement, hints_text
gold:        {file, qualname, dotted, kind: "function"|"class", start_line, def_line, end_line, file_total_lines}
find_target: {tool: "read_file", args: {filepath, start_line, end_line}}
read_output: str        # the exact harness read_file response for find_target
edit_target: {tool: "edit_file", args: {filepath, old_string, new_string}}
outside_edits: int      # gold hunks outside the target function (e.g. imports), not part of the target
diff:        str        # gold patch restricted to the gold file
test:        {files: [...], names: [...], files_exist: bool, source: str}
graph:       {focal, nodes: [...], edges: [{from, to, type}]}
words:       str | null # plain-language description of the change; generated in-notebook by 31B if null
wrong:       {file, dotted, def_line, graph_focal, test_from, words_from}
```

Rules:
- `start_line` = first decorator line of the gold function; `end_line` = min(function end, start_line + 149)
  (the harness reads at most 150 lines).
- `read_output` = `json.dumps({"status": "ok", "filepath", "content", "start_line", "end_line", "total_lines",
  "is_truncated"}, ensure_ascii=False)`, content = raw lines joined by `\n` (no line numbers, ≤ 10,000 chars),
  as swegemma 0.2.11 `read_file` returns it.
- **Canonical edit:**
  - Take the gold hunks inside the gold function's span.
  - `old_string` = base lines from the first to the last changed old line, inclusive.
  - For a pure insertion, add the preceding line as an anchor in both strings; for a pure deletion
    (empty `new_string`), add one neighbouring line to both.
  - Extend by one surrounding line at a time until `old_string` occurs exactly once in the base file.
  - `new_string` = the corresponding new lines.
  - Argument order is `filepath, old_string, new_string`.
- `test.source` = `test_patch` as it reads after applying it: per file a `# <path>` line, then per hunk the
  context + added lines (no removed lines), hunks separated by `# ...`, ≤ 60 lines in total.
- `graph` = the induced subgraph on the gold symbol + up to 10 non-test neighbours, from the harness's own
  `get_code_neighbors` / `get_code_subgraph`.
- `wrong` = matched-length controls (see PLAN): another file of similar path length in the same repo, another
  function in the same file with a similar dotted-name length, and another task's test/words of similar length.

## What the probe adds at run time (no need to export)

- `graph` is computed on Kaggle with the harness's own graph tools (needs `graphs/` from Level A).
- `words` is written by 31b in the session.
- The agent contexts (system prompt, tool schema, task prompt with workspace layout, read_file turn) are captured by
  running the real swegemma agent loop against a capture server. So pilot D's tasks must run in the harness
  (Level A + `sandbox/setup.py` compatible).
- Checks you can run yourself: `notebooks/C00_gold_check__CPU.ipynb` (validity), then a probe dry run of `notebooks/C03_probe__L4x4.ipynb` with
  `tests/papermill_dryrun.sh <your_layout_dir> <venv> <out> C00 C03` on `pilot/c-bottleneck`.
