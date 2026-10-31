"""Synthetic tests for diff parsing + scope mapping (no competition data)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.diffs import parse_unified_diff, is_test_path
from common.locate import changed_scopes, module_path

SRC = '''import os


class C:
    x = 1

    def m(self):
        a = 1
        return a

    @property
    def p(self):
        return 2


def f():
    def inner():
        return 3
    return inner()
'''


def scopes_for(diff):
    fd = parse_unified_diff(diff)[0]
    s, mod = changed_scopes(SRC, fd)
    return [x.qualname for x in s], mod


def test_modify_method_body():
    d = "--- a/x.py\n+++ b/x.py\n@@ -8,2 +8,2 @@\n-        a = 1\n+        a = 2\n         return a\n"
    assert scopes_for(d) == (["C.m"], False)


def test_insert_new_method_between_methods():
    d = ("--- a/x.py\n+++ b/x.py\n@@ -9,2 +9,5 @@\n         return a\n \n"
         "+    def n(self):\n+        return 0\n+\n")
    assert scopes_for(d) == (["C"], False)


def test_insert_top_level_function_and_import():
    d = ("--- a/x.py\n+++ b/x.py\n@@ -1,1 +1,2 @@\n import os\n+import re\n"
         "@@ -19,1 +20,4 @@\n     return inner()\n+\n+def g():\n+    pass\n")
    assert scopes_for(d) == ([], True)


def test_nested_function_reports_outer_and_decorator_counts():
    d = ("--- a/x.py\n+++ b/x.py\n@@ -18,1 +18,1 @@\n-        return 3\n+        return 4\n"
         "@@ -11,1 +11,1 @@\n-    @property\n+    @staticmethod\n")
    assert scopes_for(d) == (["C.p", "f"], False)


def test_class_attribute_maps_to_class():
    d = "--- a/x.py\n+++ b/x.py\n@@ -5,1 +5,1 @@\n-    x = 1\n+    x = 2\n"
    assert scopes_for(d) == (["C"], False)


def test_new_file_detection_and_paths():
    fd = parse_unified_diff("--- a/n.py\n+++ b/n.py\n@@ -0,0 +1,2 @@\n+a = 1\n+b = 2\n")[0]
    assert fd.maybe_new_file and fd.added == 2
    assert module_path("src/requests/models.py") == "requests.models"
    assert module_path("rich/__init__.py") == "rich"
    assert is_test_path("tests/test_x.py") and is_test_path("pkg/foo_test.py") and not is_test_path("fastapi/routing.py")
