"""Synthetic unit tests for pilot_c/probe.py (no competition data)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.diffs import parse_unified_diff
from pilot_c.probe import (apply_edit, canonical_edit, classify_find, classify_use, encode_graph,
                           harness_read_output, insert_hint, words_leak)
from pilot_c.probe import test_source as probe_test_source

BASE = "import os\n\n\ndef f(x):\n    if x:\n        return 1\n    return 2\n\n\ndef g():\n    return 3\n"


def test_canonical_edit_replacement_and_apply():
    d = "--- a/m.py\n+++ b/m.py\n@@ -5,2 +5,2 @@\n-    if x:\n-        return 1\n+    if x is None:\n+        return 0\n"
    fd = parse_unified_diff(d)[0]
    e = canonical_edit(BASE, fd, 4, 7)
    assert e["old_string"] == "    if x:\n        return 1"
    assert e["new_string"] == "    if x is None:\n        return 0"
    out, how = apply_edit(BASE, e["old_string"], e["new_string"])
    assert how == "exact" and "x is None" in out


def test_canonical_edit_pure_deletion_keeps_anchor():
    d = "--- a/m.py\n+++ b/m.py\n@@ -5,3 +5,1 @@\n-    if x:\n-        return 1\n     return 2\n"
    fd = parse_unified_diff(d)[0]
    e = canonical_edit(BASE, fd, 4, 7)
    out, _ = apply_edit(BASE, e["old_string"], e["new_string"])
    assert out == "import os\n\n\ndef f(x):\n    return 2\n\n\ndef g():\n    return 3\n"


def test_flexible_apply_and_read_output():
    out, how = apply_edit(BASE, "if x:\n  return 1", "if x:\n  return 9")
    # base indent of the matched block (4) + new_string's own relative indent (2), as the harness's flexible tier
    assert how == "flexible" and "\n    if x:\n      return 9\n" in out
    r = json.loads(harness_read_output("m.py", BASE, 4, 400))
    assert r["start_line"] == 4 and r["end_line"] == 11 and r["total_lines"] == 11 and r["content"].startswith("def f")


def test_insert_hint_and_test_source_and_leak():
    prompt = "Problem Statement:\nBug here.\n\n## Task Budget\n..."
    txt, how = insert_hint(prompt, "Bug here.", "## Location hints\n- x")
    assert how == "exact" and "Bug here.\n\n## Location hints\n- x\n\n\n## Task Budget" in txt
    tp = "--- a/tests/test_m.py\n+++ b/tests/test_m.py\n@@ -1,2 +1,4 @@\n def test_a():\n-    assert 1\n+    assert 2\n+\n+def test_b(): pass\n"
    src = probe_test_source(tp)
    assert "assert 2" in src and "assert 1" not in src and src.startswith("# tests/test_m.py")
    assert words_leak("we now return 0 when x is None", "+        return 0 if x is None else 1") is False
    assert words_leak("it adds `return 0 if x is None else 1`", "+        return 0 if x is None else 1") is True


def test_graph_encodings_same_content():
    edges = [{"from": "p.f", "to": "p.g", "type": "calls"}]
    j = json.loads(encode_graph("p.f", ["p.g", "p.f"], edges, "json"))
    assert j["nodes"][0] == "p.f" and j["edge_count"] == 1
    assert encode_graph("p.f", ["p.g"], edges, "edges") == "p.f -[calls]-> p.g"
    assert "p.g: calls -; called by p.f" in encode_graph("p.f", ["p.g"], edges, "adj")


def _rec():
    return {"gold": {"file": "m.py", "start_line": 4, "end_line": 7, "qualname": "f", "dotted": "m.f"},
            "wrong": {"file": "n.py", "qualname": "g", "def_line": 10},
            "edit_target": {"args": {"old_string": "    if x:\n        return 1", "new_string": "    if x is None:\n        return 0"}},
            "changed_lines": [5, 6], "_base_text": BASE}


def test_classify_find_and_use():
    call = lambda name, args: [{"function": {"name": name, "arguments": json.dumps(args)}}]  # noqa: E731
    f = classify_find(_rec(), call("read_file", {"filepath": "/workspace/m.py", "start_line": 1, "end_line": 20}))
    assert f["hit_file"] and f["hit_func"] and not f["followed_wrong"]
    f = classify_find(_rec(), call("run_command", {"command": "cat n.py"}))
    assert not f["hit_file"] and f["followed_wrong"]
    u, edited = classify_use(_rec(), call("edit_file", {"filepath": "m.py", "old_string": "    if x:\n        return 1",
                                                        "new_string": "    if x is None:\n        return 0"}))
    assert u["applies"] and u["on_target"] and u["exact"] and edited
    u, _ = classify_use(_rec(), call("edit_file", {"filepath": "m.py", "old_string": "    return 3", "new_string": "    return 4"}))
    assert u["applies"] and not u["on_target"] and not u["exact"]
    assert classify_use(_rec(), [])[0]["tool_call"] is False
