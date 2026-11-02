"""Synthetic test of the D1/D2 task selection (pilot_c/heldout.py): rules 1, 3, 4, 6, the sympy exclusion, and that the
sample equals pilot D's own script (pilot_d/select_d_tasks.py at pilot/d-heldout 04dd8d1) on the same pool.
usage: python -m tests.test_heldout_select"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot_c import heldout as ho  # noqa: E402

REPOS = {"tobymao/sqlglot": 16, "python-poetry/tomlkit": 9, "networkx/networkx": 6, "pyparsing/pyparsing": 1,
         "sympy/sympy": 4}


def make_export(root: Path) -> tuple[Path, list[dict], set[str]]:
    E = root / "heldout_export"
    (E / "graphs").mkdir(parents=True)
    tasks, meta, val, ok = [], [], [], set()
    k = 0
    for repo, n in REPOS.items():
        short = repo.split("/")[1]
        for j in range(n):
            k += 1
            iid, base = f"{short}_{1000 + j}", f"{k:040x}"
            tasks.append({"instance_id": iid, "repo": repo, "base_commit": base})
            src = "pr_body#9" if j % 5 == 1 else ("pending" if j % 7 == 3 else f"issue#{j}")
            meta.append({"instance_id": iid, "problem_statement_source": src, "issue_refs": [j] if j % 2 else []})
            nodes = 39500 if repo == "sympy/sympy" else (25000 if (repo, j) == ("networkx/networkx", 0) else 900)
            (E / "graphs" / f"{short}_{base}.json").write_text(json.dumps({"nodes": [{"id": f"n{x}"} for x in range(nodes)]}))
            val.append({"instance_id": iid, "repo": repo, "valid": True, "base_exit": 124 if j == 2 and short == "sqlglot" else 1})
            if j % 6 != 4:
                ok.add(iid)
    with open(E / "tasks.jsonl", "w") as f:
        f.writelines(json.dumps(t) + "\n" for t in tasks)
    with open(E / "heldout_meta.jsonl", "w") as f:
        f.writelines(json.dumps(m) + "\n" for m in meta)
    (E / "EXPORT.json").write_text("{}")
    return E, val, ok


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        E, val, ok = make_export(td)
        (td / "val.jsonl").write_text("".join(json.dumps(v) + "\n" for v in val))
        cand, why, counts = ho.cheap_rules(E, val, hang_ids=())
        assert not [i for i in cand if i.startswith("sympy_")], "sympy must be excluded"
        assert why["sympy_1000"] == "excluded repo"
        assert why["sqlglot_1002"] == "300 s hang without a patch"
        assert why["networkx_1000"].startswith("graph >")
        assert all(why[i].startswith("statement not from an issue") for i in ("sqlglot_1001", "tomlkit_1003"))
        srcs = [json.loads(l)["problem_statement_source"].split("#")[0] for l in open(E / "heldout_meta.jsonl")]
        assert counts["statement_source"] == {k: srcs.count(k) for k in set(srcs)}, counts["statement_source"]
        assert sum(counts["statement_source"].values()) == counts["exported"] == sum(REPOS.values())
        pool = [i for i in cand if i in ok]
        repo_of = {i: next(r for r in REPOS if r.endswith("/" + i.split("_")[0])) for i in pool}
        mine = ho.select(pool, repo_of, 24)
        assert mine["selected_by_repo"]["tobymao/sqlglot"] <= 12 and "pyparsing/pyparsing" not in mine["selected_by_repo"]
        # the frozen hang list alone (no validation file) also drops the known hang task
        cand2, why2, _ = ho.cheap_rules(E, None, hang_ids=("sqlglot_1002",))
        assert why2["sqlglot_1002"] == "300 s hang without a patch" and cand2 == cand
        # equal to pilot D's own script on the same inputs (sympy removed by its graph rule there)
        src = subprocess.run(["git", "-C", str(ROOT), "show", "origin/pilot/d-heldout:pilot_d/select_d_tasks.py"],
                             capture_output=True, text=True)
        if src.returncode == 0:
            (td / "sel.py").write_text(src.stdout)
            (td / "ok.json").write_text(json.dumps(sorted(ok)))
            subprocess.run([sys.executable, "-I", str(td / "sel.py"), str(E), str(td / "val.jsonl"), str(td / "ok.json"),
                            str(td / "out.json"), "--n", "24"], check=True, capture_output=True)
            theirs = json.load(open(td / "out.json"))
            assert theirs["selected"] == mine["selected"], (theirs["selected"], mine["selected"])
            assert theirs["pool"] == mine["pool"]
            print("matches pilot D's script:", theirs["selected_by_repo"])
        else:
            print("pilot D's script not available here; equality check skipped")
    print("test_heldout_select OK:", mine["selected_by_repo"], "pool", mine["pool"])


if __name__ == "__main__":
    main()
