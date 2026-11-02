"""Synthetic test of the frozen D2 analysis (pilot_c/analyze_d2.py). usage: python -m tests.test_analyze_d2"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot_c import analyze_d2 as a2  # noqa: E402


def row(i: int, resolved: bool, crash: bool = False, orig_after: int = 0, ssc: int = 0) -> dict:
    return {"instance_id": f"t{i}", "resolved": resolved, "error": "ContextWindowExceeded: prompt too long" if crash else
            (None if resolved else "tool call budget exhausted"), "wall_s": 600, "tool_calls": 30, "repeat_share": 0.1,
            "malformed_share": 0.0, "failed_edits": 1, "skill_calls": 0, "calls_by_tool": {"read_file": 20, "search_similar_code": ssc},
            "cmp_compactions": 2, "cmp_task_prompt_compacted": True, "cmp_requests_after_first_compaction": 10,
            "cmp_after_with_task_prompt": 3, "cmp_after_marker_in_prompt": 0, "cmp_after_marker_in_summary_only": 3,
            "cmp_after_marker_other_only": 0, "cmp_after_with_original_prompt": orig_after, "cmp_summaries": 2,
            "cmp_summaries_with_marker": 1, "cmp_summary_ngram5_recall_mean": 0.02 * (i % 3), "cmp_summary_word_recall_mean": 0.2,
            "cmp_requested_output_tokens": [8192], "cmp_max_prompt_tokens": 20000, "cmp_context_errors": int(crash)}


def run(rows: list[dict]) -> dict:
    return {"notebook": "notebooks/D2_heldout_rollouts_12b__L4x4.ipynb", "task_ids": [r["instance_id"] for r in rows],
            "runs": [{"condition": "O0", "replicate": 1, "rows": rows[:12]}, {"condition": "O0", "replicate": 1, "rows": rows[12:]}],
            "selection": {"selected_by_repo": {"a/x": 12, "b/y": 8, "c/z": 4}}}


def main() -> None:
    dev = ROOT / "results" / "D2_dev_reference.json"
    D = json.loads(dev.read_text())
    assert D["R6_claim2_compaction"]["holds"] and D["R7_claim4_crashes"]["holds"] and D["solve_rate"]["resolved"] == 9
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "D2.json"
        rows = [row(i, i % 4 == 0, ssc=1) for i in range(24)]
        p.write_text(json.dumps(run(rows)))
        fe = Path(td) / "fe.json"
        fe.write_text(json.dumps({"runs": [{"task": "t1"}], "total": {"edits": 10, "failed": 4, "after_first_compaction": 3}}))
        A = a2.main(str(p), str(dev), td, str(fe))
        assert A["solve_rate"]["resolved"] == 6 and A["solve_rate"]["wilson95"][0] < 0.25 < A["solve_rate"]["wilson95"][1]
        assert A["R7_claim4_crashes"]["holds"] is True and A["R6_claim2_compaction"]["holds"] is True
        assert A["search_similar_code"]["share"] == round(24 / 720, 4) and A["search_similar_code"]["negligible"] is True
        assert A["failed_edits"]["failed_after_first_compaction"] == 3 and A["setting_check"]["ok"]
        assert A["figures"] == ["D2_fig1_how_runs_ended.png", "D2_fig2_summary_retention.png"]
        assert all((Path(td) / f).exists() for f in ("D2_analysis.json", "D2_tables.md", *A["figures"]))
        # two crashes and a request with the original statement after compaction: both criteria fail
        rows = [row(i, False, crash=i < 2, orig_after=int(i == 5)) for i in range(24)]
        p.write_text(json.dumps(run(rows)))
        B = a2.main(str(p), str(dev), td)
        assert B["R7_claim4_crashes"]["holds"] is False and B["R6_claim2_compaction"]["holds"] is False
        assert B["ended"]["context_crash"] == 2 and B["solve_rate"]["wilson95"][0] == 0.0
        # no compaction at all: R6 not evaluable
        rows = [dict(row(i, True), cmp_compactions=0) for i in range(5)]
        p.write_text(json.dumps(run(rows)))
        C = a2.main(str(p), None, td)
        assert C["R6_claim2_compaction"]["holds"] is None and "not evaluable" in (Path(td) / "D2_tables.md").read_text()
    print("test_analyze_d2 OK")


if __name__ == "__main__":
    main()
