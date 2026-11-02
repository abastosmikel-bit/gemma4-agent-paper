"""Held-out tasks for notebooks/D1_heldout_probe__L4x4.ipynb and notebooks/D2_heldout_rollouts_12b__L4x4.ipynb.

Reads pilot D's export (the output of notebooks/D0b_heldout_export__CPU.ipynb on pilot/d-heldout: `heldout_export/`,
docs/PROBE_INPUT.md Level A, plus `D0_summary.json`) and:
  1. merges it with the competition's agent and sandbox into one data directory, so pilot C's runner
     (pilot_c/kaggle_runner.py, which reads everything from one data directory) runs unchanged on held-out tasks;
  2. installs the export's test-only wheels that this image lacks (the subprocess sandbox uses the host's packages);
  3. selects the D1/D2 task set by the rule frozen in docs/D_SPECS.md (paper/main), rules 1-6.

The selection is pilot D's `pilot_d/select_d_tasks.py` (pilot/d-heldout 04dd8d1), vendored so the notebooks can inline it.
`select()` is that script's sampling code, unchanged. Two changes in what reaches it (coordinator, 2026-11-02):
  - repos in EXCLUDE_REPOS (sympy) are dropped by name, not only through the graph-size rule: sympy's graph stalls the
    harness's graph tools (O(N^2) load above ~25k nodes);
  - rule 4 (no 300 s hang in the no-patch run): D0b's output has no validation rows (it exports valid tasks only), so the
    hang tasks come from a validation file if one is attached, else from HANG_IDS, the hang tasks pilot D found in its
    local validation (results/heldout_pool_local.json on pilot/d-heldout).
Rule 3 is unchanged: the problem statement must come from an issue (`problem_statement_source` starts with "issue#").
PR-body statements often describe the fix, which would leak "where" and "what" into the baseline (L0) of the ladder.
Those tasks still count in pilot D's validity audit (claim 5); they are only kept out of D1/D2.

Outputs: D_selection.json (our own task ids and counts; safe to commit). Task content stays in memory / private/.
"""
from __future__ import annotations

import collections
import glob
import importlib.metadata as md
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SEED = 20261102
MAX_NODES = 20000
EXCLUDE_REPOS = ("sympy/sympy",)
HANG_IDS = ("sqlglot_df5ec1ecd4", "sympy_30515")
RULE = "docs/D_SPECS.md (paper/main 02381e4) rules 1-6; selection code pilot_d/select_d_tasks.py (pilot/d-heldout 04dd8d1)"


# --------------------------------------------------------------------------- locating the inputs

def _input_root() -> str:
    return os.environ.get("PILOT_INPUT_ROOT", "/kaggle/input")


def find_export() -> Path:
    """The attached `heldout_export/` (found by its EXPORT.json, wherever Kaggle mounts D0b's output)."""
    hits = sorted(glob.glob(f"{_input_root()}/**/heldout_export/EXPORT.json", recursive=True))
    if not hits:
        raise FileNotFoundError("heldout_export/EXPORT.json not found under /kaggle/input: attach the output of "
                                "notebooks/D0b_heldout_export__CPU.ipynb (pilot/d-heldout) as an input first")
    return Path(hits[0]).parent


def find_optional(name: str) -> Path | None:
    hits = sorted(glob.glob(f"{_input_root()}/**/{name}", recursive=True))
    return Path(hits[0]) if hits else None


def competition_dir() -> Path:
    for c in ("/kaggle/input/competitions/gemma-4-developer-agent", "/kaggle/input/gemma-4-developer-agent"):
        if Path(c).is_dir():
            return Path(c)
    raise FileNotFoundError("competition gemma-4-developer-agent is not attached")


def merged_data_dir(export: Path, comp: Path, dst: Path) -> Path:
    """One data directory: task data from the export, agent and sandbox from the competition. Sets PILOT_DATA_DIR, so
    call it before kaggle_runner.set_env()."""
    dst.mkdir(parents=True, exist_ok=True)
    links = {"tasks.jsonl": export / "tasks.jsonl", "snapshots": export / "snapshots", "graphs": export / "graphs",
             "embeddings": export / "embeddings", "wheels": export / "wheels",
             "sample_submission": comp / "sample_submission", "sandbox": comp / "sandbox"}
    for name, src in links.items():
        p = dst / name
        if p.is_symlink() or p.exists():
            p.unlink()
        if src.exists():
            p.symlink_to(src.resolve())
    os.environ["PILOT_DATA_DIR"] = str(dst)
    return dst


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def install_test_wheels(export: Path) -> dict[str, Any]:
    """Install the export's test-only wheels whose distribution this image lacks (as D0b did), offline and without
    dependencies. Already-installed distributions are never replaced: the model-serving stack keeps its versions."""
    from pilot_c.kaggle_runner import _dist_of, _wheel_supported
    have = {_norm(d.metadata["Name"] or "") for d in md.distributions()}
    wheels = sorted((export / "wheels").glob("*.whl"))
    todo, seen = [], set()
    for w in wheels:
        dist = _dist_of(w.name)
        if dist in have or dist in seen or not _wheel_supported(w.name):
            continue
        seen.add(dist)
        todo.append(str(w))
    if todo:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-index", "--no-deps", *todo], check=True)
    return {"wheels_in_export": len(wheels), "installed": [Path(t).name for t in todo]}


# --------------------------------------------------------------------------- selection

def _jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in open(p) if l.strip()] if p and Path(p).exists() else []


def graph_nodes(export: Path, task: dict) -> int:
    name = task["repo"].split("/")[1]
    for stem in (name, name.lower()):
        g = export / "graphs" / f"{stem}_{task['base_commit']}.json"
        if g.exists():
            return len(json.load(open(g))["nodes"])
    return 10 ** 9


def cheap_rules(export: Path, validation: list[dict] | None = None, hang_ids=HANG_IDS,
                exclude_repos=EXCLUDE_REPOS) -> tuple[list[str], dict[str, str], dict]:
    """Rules 1, 3, 4, 6 and the repo exclusion (no snapshot access). Returns (candidate ids, reason per excluded id,
    counts). Rule 1: the export holds valid tasks only; a validation file, if given, must also say valid."""
    tasks = {t["instance_id"]: t for t in _jl(export / "tasks.jsonl")}
    meta = {m["instance_id"]: m for m in _jl(export / "heldout_meta.jsonl")}
    val = {v["instance_id"]: v for v in (validation or [])}
    hang = set(hang_ids) | {i for i, v in val.items() if v.get("base_exit") == 124}
    cand, why = [], {}
    for i in sorted(tasks):
        src = (meta.get(i, {}).get("problem_statement_source") or "pending")
        if tasks[i]["repo"] in exclude_repos:
            why[i] = "excluded repo"
        elif val and not val.get(i, {}).get("valid"):
            why[i] = "not valid"
        elif not src.startswith("issue#"):
            why[i] = "statement not from an issue (" + src.split("#")[0] + ")"
        elif i in hang:
            why[i] = "300 s hang without a patch"
        elif graph_nodes(export, tasks[i]) > MAX_NODES:
            why[i] = f"graph > {MAX_NODES} nodes"
        else:
            cand.append(i)
    src_counts = collections.Counter((meta.get(i, {}).get("problem_statement_source") or "pending").split("#")[0] for i in tasks)
    counts = {"exported": len(tasks), "statement_source": dict(src_counts),
              "exported_by_repo": dict(collections.Counter(t["repo"] for t in tasks.values())),
              "excluded_before_records": dict(collections.Counter(why.values())), "candidates": len(cand)}
    return cand, why, counts


def eligible_any_repo(g: dict) -> bool:
    """pilot_c/select_tasks.eligible, the dev probe rule, without its dev-repo filter (D_SPECS rule 2). The rule itself is
    reused unchanged: only the repo field is set to a dev repo for the check."""
    from pilot_c.select_tasks import QUOTA, eligible
    return eligible({**g, "repo": next(iter(QUOTA))})


def probe_ready(ids: list[str]) -> tuple[dict[str, dict], dict[str, str]]:
    """Rule 2: C's eligibility rule (minus the dev-repo filter) and probe.build_probe_record == ok. Uses the merged data
    directory (PILOT_DATA_DIR). Returns ({id: probe record}, {id: reason})."""
    from pilot_c import kaggle_runner as kr
    from pilot_c import probe as pb
    d = kr.data_dir()
    tasks = {t["instance_id"]: t for t in kr.load_tasks(d / "tasks.jsonl")}
    gold = kr.build_gold(ids)
    recs, why = {}, {}
    for i in ids:
        if not eligible_any_repo(gold[i]):
            why[i] = "not eligible"
            continue
        rec, reason = pb.build_probe_record(tasks[i], gold[i], d / "snapshots" / f"{i}.tgz")
        if rec is None:
            why[i] = reason
        else:
            recs[i] = rec
    return recs, why


def select(pool: list[str], repo_of: dict[str, str], n: int = 24, seed: int = SEED) -> dict[str, Any]:
    """pilot_d/select_d_tasks.py's sampling, unchanged: rule 5 (>= 2 pool tasks per repo), then a seeded,
    repo-stratified round-robin sample of n, at most n // 2 per repo, from >= 3 repos."""
    by = collections.defaultdict(list)
    for i in sorted(pool):
        by[repo_of[i]].append(i)
    by = {r: ids for r, ids in by.items() if len(ids) >= 2}           # rule 5
    rng = random.Random(seed)
    for r in sorted(by):
        rng.shuffle(by[r])
    cap = n // 2
    chosen, repos = [], sorted(by, key=lambda r: (-len(by[r]), r))
    while len(chosen) < n and any(by[r] for r in repos):            # round-robin over repos, respecting the cap
        for r in repos:
            if by[r] and sum(repo_of[c] == r for c in chosen) < cap and len(chosen) < n:
                chosen.append(by[r].pop(0))
        if all(not by[r] or sum(repo_of[c] == r for c in chosen) >= cap for r in repos):
            break
    out = {"seed": seed, "n_target": n, "cap_per_repo": cap, "pool": len(pool),
           "pool_by_repo": dict(collections.Counter(repo_of[i] for i in pool)),
           "selected": sorted(chosen), "selected_by_repo": dict(collections.Counter(repo_of[i] for i in chosen)),
           "n_repos": len({repo_of[i] for i in chosen})}
    if out["n_repos"] < 3:
        out["warning"] = "fewer than 3 repos: the spec requires >= 3"
    return out


def select_tasks(export: Path, n: int = 24, validation_path: Path | None = None) -> tuple[dict[str, Any], list[dict]]:
    """Rules 1-6 and the sample. Returns (D_selection dict, probe records of the selected tasks, in id order)."""
    validation = _jl(validation_path) if validation_path else None
    cand, why0, counts = cheap_rules(export, validation)
    recs, why2 = probe_ready(cand)
    repo_of = {i: r["repo"] for i, r in recs.items()}
    sel = select(sorted(recs), repo_of, n)
    out = {"rule": RULE, "issue_rule": "problem_statement_source startswith 'issue#'",
           "exclude_repos": list(EXCLUDE_REPOS), "hang_ids": sorted(set(HANG_IDS)),
           "validation_file": str(validation_path) if validation_path else None, **counts,
           "not_probe_ready": dict(collections.Counter(why2.values())), "probe_ready": len(recs), **sel}
    return out, [recs[i] for i in sel["selected"]]
