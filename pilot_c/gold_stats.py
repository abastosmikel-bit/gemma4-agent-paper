"""Aggregate statistics of gold locations (numbers only; safe to commit).

usage: python -I pilot_c/gold_stats.py <gold_all.json> <out.json>
"""
import collections
import json
import statistics
import sys


def dist(xs):
    c = collections.Counter(xs)
    return {str(k): c[k] for k in sorted(c)}


def main():
    G = json.load(open(sys.argv[1]))
    rows = list(G.values())
    by_repo = collections.Counter(g["repo"] for g in rows)
    nfiles = [len(g["src_files"]) for g in rows]
    nfunc = [len(g["functions"]) for g in rows]
    size = [g["gold_added"] + g["gold_removed"] for g in rows]
    out = {
        "n_tasks": len(rows),
        "by_repo": dict(by_repo),
        "src_files_per_task": dist(min(n, 6) for n in nfiles),  # 6 = 6+
        "tasks_with_new_src_file": sum(bool(g["new_src_files"]) for g in rows),
        "tasks_with_no_py_src_change": sum(n == 0 for n in nfiles),
        "functions_per_task": dist(min(n, 10) for n in nfunc),  # 10 = 10+
        "tasks_with_module_level_change": sum(bool(g["module_level_files"]) for g in rows),
        "tasks_module_level_only": sum(bool(g["module_level_files"]) and not g["functions"] for g in rows),
        "tasks_with_non_py_or_test_files_in_gold": sum(bool(g["other_files"]) for g in rows),
        "gold_changed_lines_median": statistics.median(size),
        "gold_changed_lines_quartiles": statistics.quantiles(size, n=4),
        "test_files_per_task": dist(len(g["test_files"]) for g in rows),
        "tasks_all_test_files_new": sum(bool(g["test_files"]) and set(g["new_test_files"]) == set(g["test_files"]) for g in rows),
        "tasks_some_test_file_new": sum(bool(g["new_test_files"]) for g in rows),
        "required_tests_per_task": dist(min(len(g["test_names"]), 10) for g in rows),
        "tasks_with_zero_required_test_names": sum(not g["test_names"] for g in rows),
        "parse_errors": sum(bool(g["parse_errors"]) for g in rows),
        # the slice where function-level localization is well defined and small
        "single_file_existing_le2_funcs": sum(len(g["src_files"]) == 1 and not g["new_src_files"] and 1 <= len(g["functions"]) <= 2 for g in rows),
    }
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
