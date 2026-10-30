"""Offline test of distill_skills.py with a mocked LLM endpoint."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pilot_a"))

import distill_skills as ds  # noqa: E402
from test_common import build_trace  # noqa: E402


def fake_chat(endpoint, model, prompt, max_tokens=1500):
    if "Action log" in prompt:
        assert "edit_file(" in prompt and "ERROR FileEditError" in prompt
        return 'Sure: {"patterns": [{"pattern": "retries edit", "trigger": "FileEditError", "instead": "read_file first"}]}'
    return json.dumps({"skills": [
        {"name": "Re-read Before Edit", "description": "Use when edit_file fails with {x}.", "steps": ["read_file", "copy old_string"]},
        {"name": "small-steps", "description": "Use when a command times out.", "steps": ["narrow the command"]},
    ]})


def test_distill():
    ds.chat = fake_chat
    ds.served_model = lambda e: "m"
    with tempfile.TemporaryDirectory() as td:
        runs = Path(td) / "runs"
        (runs / "traces").mkdir(parents=True)
        build_trace().save(runs / "traces" / "trace_rich_1.json")
        (runs / "task_results.jsonl").write_text(json.dumps({"instance_id": "rich_1", "resolved": False}) + "\n")
        out = Path(td) / "skills"
        sys.argv = ["x", "--runs", str(runs), "--out", str(out)]
        ds.main()
        names = sorted(p.name for p in out.iterdir() if p.is_dir())
        assert names == ["re-read-before-edit", "small-steps"], names
        text = (out / "re-read-before-edit" / "SKILL.md").read_text()
        assert "{x}" not in text and "<x>" in text
        # the generated skills must load with the real ADK loader
        from google.adk.skills import load_skill_from_dir
        sk = load_skill_from_dir(out / "re-read-before-edit")
        assert sk.name == "re-read-before-edit" and sk.description.startswith("Use when")


if __name__ == "__main__":
    test_distill(); print("ok")
