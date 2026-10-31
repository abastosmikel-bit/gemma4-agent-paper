"""Collect pilot outputs (outside git) into results/heldout_pilot.json (committable).

Everything here is about OUR held-out tasks (public upstream commits), not competition data.
Usage: python -I pilot_d/finalize.py WORK_DIR OUT_JSON
"""
import json
import statistics
import sys
from pathlib import Path


def jl(p):
    p = Path(p)
    return [json.loads(l) for l in open(p)] if p.exists() else []


def main():
    w, out = Path(sys.argv[1]), Path(sys.argv[2])
    h = w / "heldout"
    meta = {m["instance_id"]: m for m in jl(h / "meta.jsonl")}
    cand = {c["instance_id"]: c for f in ("cand_sqlglot.jsonl", "cand_networkx.jsonl") for c in jl(w / "mine2" / f)}
    vs = {r["instance_id"]: r for r in jl(h / "val_subprocess.jsonl")}
    vd = {r["instance_id"]: r for r in jl(h / "val_docker_final.jsonl")}
    tm = {r["instance_id"]: r for r in jl(h / "testmap.jsonl")}
    an = {r["instance_id"]: r for r in jl(h / "annotations.jsonl")}
    rows = []
    for iid, m in meta.items():
        c, s, d, t, a = cand.get(iid, {}), vs.get(iid, {}), vd.get(iid, {}), tm.get(iid, {}), an.get(iid, {})
        rows.append({
            "instance_id": iid, "repo": m["repo"], "fix_commit": m["fix_commit"], "pr_number": m["pr_number"],
            "issue_refs": sorted(set(c.get("issue_refs", m.get("issue_refs", [])) + c.get("issue_refs_in_tests", []))),
            "committed_at": m["committed_at"], "ai_authored_marker": m["ai_authored_marker"],
            "code_files": len(m["code_files"]), "code_lines_changed": m["code_lines_changed"],
            "history_commits": m["history_commits"], "snapshot_mb": round(m["snapshot_bytes"] / 1e6, 1),
            "build_seconds": m["build_seconds"],
            "valid_subprocess": s.get("valid"), "valid_docker": d.get("valid"),
            "invalid_reason": None if s.get("valid") else ("empty_patch_passes" if s.get("base_resolved") else
                                                           (s.get("gold_error") or s.get("gold_symptom") or "gold_fails")[:80]),
            "base_timeout_hang_bug": s.get("base_exit") == 124,
            "validate_seconds_subprocess": round((s.get("base_seconds") or 0) + (s.get("gold_seconds") or 0), 1),
            "validate_seconds_docker": round((d.get("base_seconds") or 0) + (d.get("gold_seconds") or 0), 1),
            "n_fail_to_pass": len(t.get("FAIL_TO_PASS", [])), "n_pass_to_pass": len(t.get("PASS_TO_PASS", [])),
            "gold_nodes": a.get("gold_nodes", []),
            "gold_nodes_not_representable": a.get("gold_nodes_missing_from_graph_rule", []),
            "added_symbols": len(a.get("added_symbols", [])),
            "repro_verified": a.get("repro_test", {}).get("verified"),
        })
    valid = [r for r in rows if r["valid_subprocess"]]
    agg = {
        "tasks_built": len(rows), "valid_subprocess": len(valid),
        "valid_docker": sum(1 for r in rows if r["valid_docker"]),
        "backend_verdict_agreement": sum(1 for r in rows if r["valid_subprocess"] == r["valid_docker"]),
        "by_repo": {repo: {"built": sum(r["repo"] == repo for r in rows),
                           "valid": sum(r["repo"] == repo for r in valid)} for repo in sorted({r["repo"] for r in rows})},
        "repro_verified_of_valid": sum(1 for r in valid if r["repro_verified"]),
        "all_gold_nodes_in_graph_of_valid": sum(1 for r in valid if r["gold_nodes"] and not r["gold_nodes_not_representable"]),
        "single_function_fixes_of_valid": sum(1 for r in valid if len(r["gold_nodes"]) == 1 and not r["gold_nodes_not_representable"]),
        "ai_authored_marker_of_valid": sum(1 for r in valid if r["ai_authored_marker"]),
        "issue_linked_of_valid": sum(1 for r in valid if r["issue_refs"]),
        "median_f2p_of_valid": statistics.median(r["n_fail_to_pass"] for r in valid),
        "median_p2p_of_valid": statistics.median(r["n_pass_to_pass"] for r in valid),
        "median_build_seconds": statistics.median(r["build_seconds"] for r in rows),
        "median_validate_seconds_subprocess": statistics.median(r["validate_seconds_subprocess"] for r in rows),
        "median_validate_seconds_docker": statistics.median(r["validate_seconds_docker"] for r in rows),
        "committed_at_range": [min(r["committed_at"] for r in rows), max(r["committed_at"] for r in rows)],
        "funnels": {f.stem.replace("funnel_", ""): json.load(open(f)) for f in sorted((w / "mine2").glob("funnel_*.json"))},
    }
    out.write_text(json.dumps({"aggregate": agg, "tasks": rows}, indent=1))
    print(json.dumps(agg, indent=1))


if __name__ == "__main__":
    main()
