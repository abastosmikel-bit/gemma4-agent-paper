"""Round-trip test: swegemma's own SessionTrace -> ATIF file -> common parser/metrics.

Needs adk_eval_core installed (pip install the wheel from the competition wheelhouse).
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adk_eval_core.tracing.trace import SessionTrace, TraceEntry  # noqa: E402

from common.metrics import aggregate, mcnemar_exact, task_metrics  # noqa: E402
from common.trace_parser import parse_trace_file  # noqa: E402


def _ok(**kw):
    return json.dumps({"status": "ok", **kw})


def _err(t, msg="x"):
    return json.dumps({"status": "error", "error_type": t, "error_message": msg})


def build_trace() -> SessionTrace:
    tr = SessionTrace()
    tr.start()
    seq = [
        ("call", "list_skills", {}), ("resp", "list_skills", json.dumps({"skills": []})),
        ("call", "load_skill", {"skill_name": "reproduce-first"}),
        ("resp", "load_skill", json.dumps({"skill_name": "reproduce-first", "instructions": "..."})),
        ("call", "read_file", {"filepath": "a.py"}), ("resp", "read_file", _ok(content="x")),
        ("call", "read_file", {"filepath": "a.py"}), ("resp", "read_file", _ok(content="x")),  # repeat
        ("call", "edit_file", {"filepath": "a.py", "old_string": "x", "new_string": "y"}),
        ("resp", "edit_file", _err("FileEditError")),  # failed edit, well-formed
        ("call", "edit_file", {"filepath": "a.py"}), ("resp", "edit_file", _err("TypeError")),  # malformed + failed
        ("call", "grep_code", {"q": "x"}), ("resp", "grep_code", json.dumps({"status": "error", "error_type": "ValueError", "error": "Tool 'grep_code' not found."})),
        ("text", None, "I will call <|tool_call>call:run_command{command:"),  # raw unparsed call
        ("call", "submit_patch", {}), ("resp", "submit_patch", _ok(patch_size=10)),
    ]
    for i, (kind, name, payload) in enumerate(seq):
        if kind == "call":
            e = TraceEntry(timestamp=i, elapsed=float(i), event_type="tool_call", author="a", tool_name=name, tool_args=payload)
        elif kind == "resp":
            e = TraceEntry(timestamp=i, elapsed=float(i), event_type="tool_response", author="a", tool_name=name, tool_result=payload)
        else:
            e = TraceEntry(timestamp=i, elapsed=float(i), event_type="text", author="a", content=payload)
        tr._add(e)
    return tr


def test_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "trace_rich_1.json"
        build_trace().save(p)
        pt = parse_trace_file(p)
    assert [e.name for e in pt.events][:3] == ["list_skills", "load_skill", "read_file"]
    m = task_metrics(pt, {"resolved": True, "duration_seconds": 12.0, "tool_calls": 5},
                     declared_tools=["read_file", "edit_file", "submit_patch", "run_command"])
    assert m["tool_calls"] == 8, m
    assert m["repeat_calls"] == 1, m
    assert m["failed_edits"] == 2 and m["edit_calls"] == 2, m
    assert m["raw_tool_call_texts"] == 1, m
    assert m["malformed_calls"] == 3, m  # TypeError + unknown tool + raw text
    assert m["skill_load_calls"] == 1 and m["skills_loaded"] == {"reproduce-first": 1}, m
    assert m["submitted"] and m["resolved"]
    agg = aggregate([m, m])
    assert abs(agg["malformed_share"] - 6 / 18) < 1e-9, agg
    assert agg["skill_load_rate"] == 1.0


def test_mcnemar():
    r = mcnemar_exact([True, False, False, True], [True, True, True, True])
    assert r["b_only"] == 2 and r["a_only"] == 0 and abs(r["p_two_sided"] - 0.5) < 1e-9


if __name__ == "__main__":
    test_roundtrip(); test_mcnemar(); print("ok")
