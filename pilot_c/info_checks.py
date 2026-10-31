"""CPU-only information checks behind the Rethink section (aggregate numbers only).

1) spec  - "unfindable specification": does a task's hidden test require a name or a message
           string that the gold patch introduces and that the issue text never mentions?
           Such information cannot be found by searching the repo; only the hidden test has it.
           Heuristic (estimated, not exact):
             new_names   = def/class names on gold '+' lines that are not on gold '-' lines
                           (no dunders, >= 4 chars, not defined by the test patch itself)
             new_strings = string literals (>= 6 chars) on gold '+' lines, not on '-' lines
             required    = those that also occur on test_patch '+' lines
             unfindable  = required items absent from problem_statement (+ hints_text)
2) bits  - how much a location hint narrows the search, counted in definitions
           (functions/classes/methods in the code graph, tests and docs excluded):
             file_bits = log2(defs in repo / defs in gold file)
             func_bits = log2(defs in gold file / gold functions)

usage:
  python -I pilot_c/info_checks.py spec <tasks.jsonl> <gold_all.json> <out.json>
  python -I pilot_c/info_checks.py bits <tasks.jsonl> <gold_all.json> <graphs_dir> <out.json>
"""
from __future__ import annotations

import json
import math
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.locate import module_path  # noqa: E402
from common.tasks import load_tasks  # noqa: E402

_DEF = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_STR = re.compile(r"""(?:"([^"\\\n]{6,})"|'([^'\\\n]{6,})')""")


def _side(patch: str, tag: str) -> list[str]:
    return [l[1:] for l in patch.splitlines() if l.startswith(tag) and not l.startswith(tag * 3 + " ")]


def spec_row(t: dict) -> dict:
    plus, minus = _side(t["patch"], "+"), _side(t["patch"], "-")
    tplus = "\n".join(_side(t["test_patch"], "+"))
    issue = (t.get("problem_statement") or "") + "\n" + (t.get("hints_text") or "")
    minus_txt = "\n".join(minus)
    names = {m.group(1) for l in plus if (m := _DEF.match(l))} - {m.group(1) for l in minus if (m := _DEF.match(l))}
    tdefs = {m.group(1) for l in _side(t["test_patch"], "+") if (m := _DEF.match(l))}
    names = {n for n in names if not n.startswith(("test_", "__")) and len(n) >= 4 and n not in tdefs}
    strings = {a or b for l in plus for a, b in _STR.findall(l)} - {a or b for l in minus for a, b in _STR.findall(l)}
    strings = {s for s in strings if s not in minus_txt and not s.startswith(("http", "/"))}
    req_names = {n for n in names if re.search(rf"\b{re.escape(n)}\b", tplus)}
    req_strings = {s for s in strings if s in tplus}
    unf_names = {n for n in req_names if not re.search(rf"\b{re.escape(n)}\b", issue)}
    unf_strings = {s for s in req_strings if s not in issue}
    return {"req_names": len(req_names), "unf_names": len(unf_names), "req_strings": len(req_strings),
            "unf_strings": len(unf_strings)}


def spec(tasks_path: str, gold_path: str, out: str) -> None:
    tasks = load_tasks(tasks_path)
    gold = json.load(open(gold_path))
    rows = {t["instance_id"]: spec_row(t) for t in tasks}
    unf = {i for i, r in rows.items() if r["unf_names"] or r["unf_strings"]}
    new_tests = {i for i, g in gold.items() if g["test_files"] and set(g["new_test_files"]) == set(g["test_files"])}
    res = {
        "n_tasks": len(rows),
        "tasks_requiring_new_name_or_string": sum(1 for r in rows.values() if r["req_names"] or r["req_strings"]),
        "tasks_with_unfindable_requirement": len(unf),
        "  of_which_name": sum(1 for r in rows.values() if r["unf_names"]),
        "  of_which_string": sum(1 for r in rows.values() if r["unf_strings"]),
        "unfindable_among_all_new_test_file_tasks": f"{len(unf & new_tests)}/{len(new_tests)}",
        "unfindable_among_existing_test_file_tasks": f"{len(unf - new_tests)}/{len(rows) - len(new_tests)}",
        "method": "heuristic, see pilot_c/info_checks.py docstring",
    }
    try:
        from pilot_c.select_tasks import eligible
        el = {i for i, g in gold.items() if eligible(g)}
        res["unfindable_among_pilot_eligible"] = f"{len(unf & el)}/{len(el)}"
    except Exception:  # noqa: BLE001
        pass
    Path(out).write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


def bits(tasks_path: str, gold_path: str, graphs_dir: str, out: str) -> None:
    tasks = {t["instance_id"]: t for t in load_tasks(tasks_path)}
    gold = json.load(open(gold_path))
    cache: dict[str, list[str]] = {}
    fb, ub, tb = [], [], []
    for iid, g in gold.items():
        t = tasks[iid]
        gf = Path(graphs_dir) / f"{iid.split('_')[0]}_{t['base_commit']}.json"
        if not gf.exists() or len(g["src_files"]) != 1 or g["new_src_files"] or not g["functions"]:
            continue
        if str(gf) not in cache:
            ids = [n["id"] for n in json.load(open(gf))["nodes"]]
            cache[str(gf)] = [i for i in ids if not i.startswith(("tests.", "test.", "docs_src.", "docs.", "benchmarks."))]
        ids = cache[str(gf)]
        mod = module_path(g["src_files"][0])
        in_file = [i for i in ids if i.startswith(mod + ".")]
        if not in_file:
            continue
        fb.append(math.log2(len(ids) / len(in_file)))
        ub.append(math.log2(max(1.0, len(in_file) / len(g["functions"]))))
        tb.append(fb[-1] + ub[-1])

    def q(xs):
        return {"median": round(statistics.median(xs), 2), "q1": round(statistics.quantiles(xs, n=4)[0], 2),
                "q3": round(statistics.quantiles(xs, n=4)[2], 2)}

    res = {"n_tasks_single_existing_file_with_functions": len(fb), "file_hint_bits": q(fb), "function_hint_bits_given_file": q(ub),
           "total_location_bits": q(tb), "unit": "log2 of candidate definitions eliminated (code graph, tests/docs excluded)"}
    Path(out).write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "spec":
        spec(*sys.argv[2:5])
    else:
        bits(*sys.argv[2:6])
