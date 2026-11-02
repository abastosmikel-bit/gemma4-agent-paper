"""pilot_c/analyze_c06.py end to end on SYNTHETIC data (the real C05 file + a synthetic C06 run + synthetic summaries):
tables, JSON and figures are produced, and the hand-checkable numbers come out right."""
import json
import random
from pathlib import Path

from pilot_c import analyze_c06 as a6

ROOT = Path(__file__).resolve().parents[1]


def make_synthetic(out: Path, seed: int = 7) -> tuple[Path, Path]:
    """A synthetic C06 output shaped like notebooks/C06_validation_fix_12b__L4x4.ipynb's, plus summaries files."""
    rnd = random.Random(seed)
    c05 = json.loads((ROOT / "results/C05_validation_12b.json").read_text())
    tasks = c05["task_ids"]
    runs = []
    for st, ts in ((1, tasks[:15]), (2, tasks[15:])):
        for cond in ("O0", "O-all"):
            rows = []
            for t in ts:
                crash = rnd.random() < 0.05
                res = (not crash) and rnd.random() < (0.3 if cond == "O0" else 0.5)
                err = ("Sandbox execution error: litellm.ContextWindowExceededError" if crash else
                       None if res else rnd.choice([None, "Agent exceeded session timeout (15.0 min)", "Agent exceeded tool call budget (40 calls)"]))
                comp = rnd.randint(0, 3)
                after = rnd.randint(5, 30) if comp else 0
                in_sum = after if (comp and rnd.random() < 0.2) else 0
                rows.append({"instance_id": t, "resolved": res, "error": err, "wall_s": rnd.uniform(100, 900),
                             "tool_calls": rnd.randint(5, 40), "repeat_share": rnd.random() * 0.2, "malformed_share": 0.0,
                             "failed_edits": rnd.randint(0, 3), "skill_calls": 0, "cmp_compactions": comp,
                             "cmp_task_prompt_compacted": bool(comp), "cmp_requests_after_first_compaction": after,
                             "cmp_after_with_task_prompt": in_sum, "cmp_after_marker_in_prompt": 0,
                             "cmp_after_marker_in_summary_only": in_sum, "cmp_after_marker_other_only": 0,
                             "cmp_after_with_original_prompt": 0, "cmp_summaries": comp,
                             "cmp_summaries_with_marker": comp if in_sum else 0,
                             "cmp_summary_ngram5_recall_mean": rnd.random() * 0.3 if comp else None,
                             "cmp_summary_word_recall_mean": rnd.random() if comp else None,
                             "cmp_requested_output_tokens": [8192], "cmp_max_prompt_tokens": rnd.randint(8000, 24000),
                             "cmp_context_errors": int(crash), "cmp_prompt_tokens_before_first_context_error": 23000 if crash else None})
            runs.append({"condition": cond, "stage": st, "rows": rows})
    c06 = {"task_ids": tasks, "runs": runs, "stages": [{"stage": 1, "discordant": 3}, {"stage": 2, "discordant": 4}],
           "stopped": None, "session_elapsed_h": 2.4}
    p = out / "C06_validation_fix_12b.json"
    p.write_text(json.dumps(c06))
    sdir = out / "private" / "runs" / "12b"
    for cond in ("O0", "O-all"):
        d = sdir / f"{cond}_r1_s1"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "summaries.jsonl", "w") as f:
            for t in tasks[:5]:
                f.write(json.dumps({"task": t, "index": 0, "text": "synthetic", "has_marker": rnd.random() < 0.3,
                                    "ngram5_recall": rnd.random() * 0.4, "word_recall": rnd.random()}) + "\n")
    return p, sdir


def test_analysis_on_synthetic_data(tmp_path):
    c06, sdir = make_synthetic(tmp_path)
    A = a6.main(str(c06), str(ROOT / "results/C05_validation_12b.json"), str(ROOT / "results/C06_predictors_12b.json"),
                str(tmp_path / "out"), str(sdir / "*" / "summaries.jsonl"))
    assert A["setting_check"]["ok"] and A["tasks_compared"] == 30
    assert A["A1_crashes"]["O0"]["C05"] == 14 and A["A1_crashes"]["O-all"]["C05"] == 9      # C05's real crash counts
    assert A["A2_hint_effect_all"]["C05"]["fail_to_pass"] == 7 and A["A2_hint_effect_all"]["C05"]["pass_to_fail"] == 0
    assert A["A3_hint_effect_crashes_removed"]["C05"]["tasks"] == 30 - 3 - 11 - 6                # tasks where neither C05 run crashed
    assert A["A5_summary_retention"]["O0"]["source"] == "summaries" and A["A5_summary_retention"]["O0"]["n"] == 5
    for f in ("C06_analysis.json", "C06_tables.md", "C06_fig1_how_runs_ended.png", "C06_fig2_hint_effect.png",
              "C06_fig3_summary_retention.png"):
        assert (tmp_path / "out" / f).exists(), f
