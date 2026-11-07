# Lost or Clueless? Where a Gemma 4 Coding Agent Gets Stuck

Code, frozen plans and results for our paper in the Kaggle competition
*Google – The Gemma 4 Developer Agent* (paper track).

We freeze the official sample agent at real points of its runs, add one piece of information
(the file, the function, a description of the change, the exact fix, a code graph, or a wrong hint),
and measure how much more likely its correct next action becomes. We check the results in real
agent runs with real tests, and replicate them on 24 held-out tasks from three other projects.

## Where things are

| Branch | Contents |
|---|---|
| `claude/beautiful-volta-w78lso` | The paper: `paper/draft.md`, its figures, `paper/make_figures.py` (rebuilds every figure from committed results) and `paper/wordcount.py` |
| `pilot/c-bottleneck` | Probe and agent-run code, Kaggle notebooks, frozen analysis plans, all results, and `REPRODUCE.md` (start here to reproduce a table or figure) |
| `pilot/d-heldout` | Building and validating the held-out tasks from public GitHub history |
| `paper/main` | Shared notes: claims and their evidence, results log, decisions, history of the experiments, related work |
| `pilot/a-skills`, `pilot/b-graph-edit` | Earlier exploratory pilots |

## Reproducing

See `REPRODUCE.md` on `pilot/c-bottleneck`. Every table and figure is rebuilt from the committed
result files by a script; the GPU experiments run as Kaggle notebooks on the competition's own
environment.

## Data

No competition data is redistributed here. Result files contain task IDs, counts and statistics
only. Held-out tasks are rebuilt by script from public GitHub repositories.

## AI assistance

Experiment code and analyses were written with Claude Code; the paper text was drafted with
AI assistance and revised by the author.

## Licence

MIT, see `LICENSE`.
