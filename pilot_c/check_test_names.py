"""Check common.diffs.required_test_names against the scorer's own function.

usage: python -I pilot_c/check_test_names.py <tasks.jsonl> <swegemma/harness/verification.py>
Prints only counts (no task content).
"""
import ast, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.tasks import load_tasks
from common.diffs import required_test_names

src = Path(sys.argv[2]).read_text()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_extract_test_functions_from_patch")
ns = {"re": re}
exec(compile(ast.Module([fn], []), "scorer_fn", "exec"), ns)
scorer = ns["_extract_test_functions_from_patch"]
tasks = load_tasks(sys.argv[1])
mism = [t["instance_id"] for t in tasks if scorer(t["test_patch"]) != required_test_names(t["test_patch"])]
print(f"tasks={len(tasks)} mismatches={len(mism)} {mism[:5]}")
