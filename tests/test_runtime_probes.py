"""common/runtime_probes.py: where the task-prompt marker sits after compaction, summary retention, request numbers.
Stand-in objects for ADK events / compaction results (no harness, no model)."""
import json
import time
from types import SimpleNamespace as NS

from common import runtime_probes as rp

STMT = "Problem Statement:\nThe parser drops trailing commas in nested lists when the input ends with a newline."


def _event(author, text):
    return NS(author=author, content=NS(parts=[NS(text=text, function_call=None, function_response=None)]))


def _result(summary, thought=""):
    parts = ([NS(text=thought, thought=True)] if thought else []) + [NS(text=summary, thought=False)]
    return NS(actions=NS(compaction=NS(compacted_content=NS(parts=parts))))


def test_retention_numbers():
    r = rp.statement_retention("a b c d e f g", "x a b c d e y")
    assert r["ngram5_recall"] == round(1 / 3, 4) and r["statement_words"] == 7
    assert rp.statement_retention("abc", "zzz")["ngram5_recall"] is None


def test_marker_sources_and_task_stats(tmp_path):
    rp.reset()
    tok = rp.CURRENT_TASK.set("t1")
    try:
        rp.PROBLEM["t1"] = STMT
        prompt = {"role": "user", "content": "Task:\n" + STMT + "\n## Workspace"}
        before = rp.request_shape([prompt], tools=[1], kwargs={"max_completion_tokens": 8192})
        before.update(prompt_tokens=15000)
        rp.REQUESTS.append(before)
        time.sleep(0.01)
        summary = "Summary. Problem Statement: The parser drops trailing commas in nested lists. Agent read parser.py."
        rp.COMPACTIONS.append(rp.compaction_record([_event("user", prompt["content"])], _result(summary, thought="(thinking)")))
        time.sleep(0.01)
        # how ADK shows a summary: a user message "For context: [model] said: <summary>"
        after = rp.request_shape([{"role": "user", "content": [{"type": "text", "text": "For context:"},
                                                               {"type": "text", "text": "[model] said: " + summary}]},
                                  {"role": "tool", "content": "ok"}], tools=[1], kwargs={"max_completion_tokens": 8192})
        assert after["marker_sources"] == ["summary"] and after["summary_present"] and not after["original_prompt_present"]
        rp.REQUESTS.append(after)
        failed = rp.request_shape([{"role": "user", "content": STMT}], tools=[1])
        failed["error"] = "ContextWindowExceededError"
        rp.REQUESTS.append(failed)
        st = rp.task_compaction_stats("t1", [])
        assert st["task_prompt_compacted"] and st["summaries"] == 1 and st["summaries_with_marker"] == 1
        assert st["after_marker_in_summary_only"] == 1 and st["after_marker_in_prompt"] == 1  # the failed request had the prompt
        assert st["after_with_original_prompt"] == 1
        assert 0 < st["summary_ngram5_recall_mean"] < 1 and st["requested_output_tokens"] == [8192]
        assert st["context_errors"] == 1 and st["prompt_tokens_before_first_context_error"] == 15000
        assert "(thinking)" not in rp.SUMMARIES["t1"][0]["text"]          # thought parts are not what requests see
        n = rp.dump_summaries(tmp_path / "s.jsonl")
        line = json.loads((tmp_path / "s.jsonl").read_text().splitlines()[0])
        assert n == 1 and line["task"] == "t1" and "fp" not in line and line["has_marker"]
    finally:
        rp.CURRENT_TASK.reset(tok)
        rp.reset()
