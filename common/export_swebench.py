"""Export swegemma-format tasks to SWE-bench instance format (generality beyond this competition).

Differences handled:
  * FAIL_TO_PASS / PASS_TO_PASS become JSON-encoded strings (SWE-bench convention);
  * patches get standard `diff --git` headers back (swegemma dev style omits them; both apply with git);
  * `version` / `environment_setup_commit` are filled from the base commit (one env per task);
  * the swegemma-only signal (snapshot path, graph path) goes under `extra`.

Usage: python -I common/export_swebench.py TASKS_WITH_F2P.jsonl OUT.jsonl
"""
import json
import re
import sys


def add_git_headers(patch: str) -> str:
    out = []
    for line in patch.splitlines():
        m = re.match(r"^--- a/(.+)$", line)
        if m:
            out.append(f"diff --git a/{m.group(1)} b/{m.group(1)}")
        out.append(line)
    return "\n".join(out) + "\n"


def main():
    with open(sys.argv[2], "w") as out:
        for line in open(sys.argv[1]):
            t = json.loads(line)
            out.write(json.dumps({
                "instance_id": t["instance_id"].replace("_", "__", 1),
                "repo": t["repo"], "base_commit": t["base_commit"],
                "patch": add_git_headers(t["patch"]), "test_patch": add_git_headers(t["test_patch"]),
                "problem_statement": t["problem_statement"], "hints_text": t.get("hints_text", ""),
                "created_at": t.get("created_at", ""),
                "version": t["base_commit"][:7], "environment_setup_commit": t["base_commit"],
                "FAIL_TO_PASS": json.dumps(list(t.get("FAIL_TO_PASS", []))),
                "PASS_TO_PASS": json.dumps(list(t.get("PASS_TO_PASS", []))),
                "extra": {"swegemma_instance_id": t["instance_id"],
                          "graph_file": f"graphs/{t['repo'].split('/')[1].lower()}_{t['base_commit']}.json"},
            }) + "\n")


if __name__ == "__main__":
    main()
