# Pilot B: the code graph as an editing interface

One of four parallel pilots for the Kaggle "Google – Gemma 4 Developer Agent" paper track.
The question: the competition's code graphs are used to *find* code. Can the same graph names
also *address edits* ("replace `fastapi.routing.APIRoute.__init__`") instead of string matching,
and does that cut malformed or lost edits for small models?

Results and the go/no-go call are in **[REPORT.md](REPORT.md)**.

## Layout
| Path | What |
|---|---|
| `common/` | Reusable, pilot-neutral code: task and graph loading (`tasks.py`), exact graph-name emulator (`graphnames.py`), AST index (`pyindex.py`), diff parsing (`patches.py`), ATIF trace parser (`traces.py`), shared metrics (`metrics.py`) |
| `pilot_b/skill/graph-edit/` | The ADK skill: `SKILL.md` plus `scripts/show_symbol.py`, `edit_symbol.py`, `insert_symbol.py` (stdlib only, run inside the sandbox) |
| `pilot_b/analysis/graph_spans.py` | Step 2: graph node to source span mapping and what the graph omits |
| `pilot_b/analysis/expressibility.py` | Steps 3–4: gold patches as symbol edits, replayed through the skill code |
| `pilot_b/analysis/replay_tests.py` | Step 4: run tests on base / gold / replay trees |
| `pilot_b/analysis/scoping.py` | Is a minimal `old_string` unique file-wide vs inside its symbol? |
| `pilot_b/tests/adk_integration.py` | Offline check through the real ADK compiler and skill-script executor |
| `pilot_b/build_notebook.py` → `notebooks/pilot_b_live.ipynb` | Step 5 live check on Kaggle (E4B, with vs without the skill) |
| `docs/blocker_check.md` | Step 1: can a skill script write to the repo and reach the patch? (yes) |
| `results/*.json` | Aggregate numbers only |

## Data policy
No competition data is in git (tasks, snapshots, graphs, embeddings, patches, traces). The
scripts rebuild everything from `DATA_DIR` (default `/tmp/kdata`, see `common/tasks.py`):
`kaggle competitions download gemma-4-developer-agent -f tasks.jsonl` and `-f graphs/<file>`,
plus upstream git clones of fastapi, rich, requests and httpx. The 129 base commits are public
upstream, and snapshot tarballs matched upstream byte-for-byte on the 2 we checked.

## Reproduce (CPU)
```bash
python -m pilot_b.analysis.graph_spans
```
```bash
python -m pilot_b.analysis.expressibility
```
```bash
python -m pilot_b.analysis.scoping
```
```bash
python -m pilot_b.analysis.replay_tests
```
