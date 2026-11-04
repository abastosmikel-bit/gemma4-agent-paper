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

1. **Commit the held-out results** to `results/` on this branch: `D1_analysis.json`, `D1v_analysis.json`,
   `D2_analysis.json`, `D_selection.json` (the analysis outputs of the D1/D1v/D2 notebooks; numbers only). Then rerun
   `make_figures.py`: held-out values appear as hollow markers in Figs 1–2 and as a fifth bar in Fig. 3.
2. Replace every `⟦HO⟧` and `⟦TODO⟧` in `draft.md` with numbers from those files, and move the matching rows in
   `research/claims.md` from PENDING EVIDENCE to measured. Check whether "16 edits" counts `write_file`.
3. Verify on Kaggle: the leaderboard top (~0.24), the 3,000-word limit and what counts, the deadline. Re-check the
   forum after 2026-10-21 for anything overlapping the find/use split, the graph control or task erasure.
4. Rewrite the prose in your voice; then rerun `wordcount.py` (now 2,837 with the placeholders; limit 3,000).
5. Reviewer round (strict judge on the five criteria), after steps 1–4.
6. Make the code public (notebooks, `pilot_c/`, `pilot_d/` mining scripts, `repro/context_window/`) without any
   competition data, and link it in the Writeup's Project Links.
