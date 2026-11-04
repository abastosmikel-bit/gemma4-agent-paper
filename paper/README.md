# Paper: "Lost or Clueless? Where a Gemma 4 Coding Agent Actually Gets Stuck"

| File | What it is |
|---|---|
| `draft.md` | Full draft for the Kaggle Writeup. Every prose paragraph is marked `<!-- DRAFT: user rewrites -->`. |
| `figures/` | Fig. 1 (where vs what, find vs use), Fig. 2 (does it edit, and is the edit right), Fig. 3 (how 12B runs ended). |
| `make_figures.py` | Rebuilds the figures and `numbers.md` from committed result JSONs (dev: `pilot/c-bottleneck` @ 14e9d00, read through `git show`). |
| `numbers.md` | Every plotted number, generated; do not edit. |
| `wordcount.py` | Word count as the limit counts it (title, abstract, captions, tables, references; HTML comments excluded). |
| `../research/claims.md` | Every number in the draft → evidence file → status. |
| `../research/novelty-map.md` | Prior work that limits what the paper can call new (incl. two forum overlaps found 2026-11-04). |

```bash
python paper/make_figures.py
```

```bash
python paper/wordcount.py
```

## Before submitting

1. Held-out results are in `results/` (D1, D1v, D2 analysis files) and every number in the draft is mapped in
   `research/claims.md`; no placeholders remain. `D_selection.json` itself is not needed: the selection is inside
   `D1_analysis.json` and `D2_analysis.json`.
2. Rewrite the prose in your voice, then rerun `wordcount.py` (about 2,810 by its rules, about 2,870 by a raw
   `wc -w` that also counts table pipes; limit 3,000).
3. On submit day: check the forum for anything new on the find/use split, the unrelated-graph control or task
   erasure. References were checked on 2026-11-04 (`research/claims.md`, "Reference check").
4. Reviewer round (strict judge on the five criteria) after your rewrite.
5. Make the code public (notebooks, `pilot_c/`, `pilot_d/` mining scripts, `repro/context_window/`) without any
   competition data, and link it in the Writeup's Project Links.
