#!/bin/bash
# LOCAL-ONLY: dry-run the generated Kaggle notebooks in a real Jupyter kernel with papermill
# (the same executor Kaggle uses), against a fake /kaggle tree. No GPU: notebooks/C01_smoke_timing__L4x4.ipynb
# and notebooks/C03_probe__L4x4.ipynb use the scripted mock LLM (PILOT_MOCK_LLM=1).
# Attached notebook outputs are placed where Kaggle mounts them: /kaggle/input/<slug of the notebook title>/.
# The venv must be Python 3.12 (the official starter's Kaggle environment) and WHEELHOUSE must hold the full
# wheelhouse (41 wheels), so each notebook's real `pip install` of the wheelhouse runs exactly as on Kaggle.
# Extra key NEG313 (needs NEG313_VENV=<py3.13 venv>): runs C00 under Python 3.13; expects the environment check to stop it.
# Extra key C03X: the 12b server fails to start; expects the other three sizes to finish and save their own files.
# Extra keys C01F / C03F: the mock server hangs (also on /health) after a few requests; expects the watchdog to kill it,
# restart once, then stop the session after the second freeze, within minutes.
# Keys C04 (needs C03 first: uses its output, trimmed to look like the real C03 run), C05 (both stages forced), C05S
# (expects the sequential rule to stop after stage 1), C04F / C05F (freeze tests).
# usage: WHEELHOUSE=<dir> tests/papermill_dryrun.sh <local_comp_dir> <py3.12 venv_dir> <out_dir> [C00 C01 C03 C04 C05 C05S C03v ...]
set -euo pipefail
COMP=$1; VENV=$2; OUT=$3; shift 3
WHEELHOUSE=${WHEELHOUSE:?set WHEELHOUSE to the directory with the 41 wheelhouse wheels}
PYV=$("$VENV/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
[ "$PYV" = "3.12" ] || { echo "dry-run venv is Python $PYV; it must be 3.12 like the Kaggle starter environment"; exit 2; }
[ "$(ls "$WHEELHOUSE"/*.whl | wc -l)" -ge 41 ] || { echo "WHEELHOUSE has fewer than 41 wheels"; exit 2; }
REPO=$(cd "$(dirname "$0")/.." && pwd)
NB=$REPO/notebooks
mkdir -p /kaggle/input/competitions /kaggle/input/datasets/metric /kaggle/working "$OUT"
rm -rf /kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse
ln -s "$WHEELHOUSE" /kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse
[ -e /kaggle/input/competitions/gemma-4-developer-agent ] || ln -s "$COMP" /kaggle/input/competitions/gemma-4-developer-agent
rm -rf /kaggle/input/notebooks   # old layout from earlier dry runs
PM="$VENV/bin/papermill"
IDS=${PILOT_TEST_IDS:-fastapi_15588,rich_3454,rich_3470,rich_3518,requests_7309,fastapi_14360,rich_4079,requests_7502}
check_content() {  # a dry run must exercise the real code path, not just finish
  "$VENV/bin/python" - "$1" "$2" <<'PY'
import json, sys
key, path = sys.argv[1], sys.argv[2]
d = json.load(open(path))
if key == "C01":
    runs = d["runs"]
    ok = runs and all(r["aggregate"]["tool_calls_mean"] > 0 and r["aggregate"]["errors"] == 0 for r in runs) and not d.get("stopped")
    msg = f"{len(runs)} runs, tool calls/task {[r['aggregate']['tool_calls_mean'] for r in runs]}, errors {[r['aggregate']['errors'] for r in runs]}"
elif key in ("C03", "C03X"):
    import os
    d1 = sum(r.get("ok", False) for r in d["d1"]); d2 = sum(r.get("ok", False) for r in d["d2"])
    failed = [s["size"] for s in d["sizes"] if s.get("error")]
    per_size = {z: json.load(open(f"/kaggle/working/C03_probe_{z}.json")) for z in ("31b", "e4b", "12b", "e2b")
                if os.path.exists(f"/kaggle/working/C03_probe_{z}.json")}
    good = [z for z, v in per_size.items() if sum(r.get("ok", False) for r in v["d1"]) > 0]
    modes = sorted({r.get("mode") for r in d["d1"] if r.get("ok")})
    expect_failed = ["12b"] if key == "C03X" else []
    ok = (not d.get("capture_missing") and d1 > 0 and d2 > 0 and failed == expect_failed
          and sorted(good) == sorted(z for z in ("31b", "e4b", "12b", "e2b") if z not in expect_failed))
    msg = (f"captured {len(d['task_ids']) - len(d.get('capture_missing', []))}/{len(d['task_ids'])}, depth-1 ok {d1}, "
           f"depth-2 ok {d2}, failed sizes {failed}, per-size files with results {sorted(good)}, score modes {modes}")
elif key == "C03v":
    import os
    srcs = sorted({r.get("source") for r in d["rows"]})
    A = json.load(open("/kaggle/working/C03v_analysis.json")) if os.path.exists("/kaggle/working/C03v_analysis.json") else {}
    ok = (len(d["rows"]) > 0 and srcs == ["C03", "C04"] and bool(A) and A["verified_without_sample_row"] == 0
          and os.path.exists("/kaggle/working/C03v_tables.md") and A.get("figures") == ["C03v_fig_solves.png"])
    msg = f"{len(d['rows'])} verified samples from {srcs}; analysis: {len(A.get('V1', {}))} size/condition cells, figures {A.get('figures')}"
elif key == "C04":
    import os
    by = lambda rows, **kw: [r for r in rows if r.get("ok") and all(r.get(k) == v for k, v in kw.items())]
    sizes = ("12b", "31b", "e4b")
    files = {z: os.path.exists(f"/kaggle/working/C04_probe_followup_{z}.json") for z in sizes}
    split = [r for r in d["d1"] if r.get("ok")]
    outs = ("C04_analysis.json", "C04_tables.md", "C03C04_tables.md", "C04_fig4_graph_control.png", "C04_fig5_action_args.png",
            "C03C04_fig1_depth1_deltas.png")
    checks = {
        "no failed size, no e2b": not [s for s in d["sizes"] if s.get("error") or s.get("skipped")] and not d.get("stopped")
                                  and not [r for r in d["d1"] if r.get("size") == "e2b"],
        "per-size files": all(files.values()),
        "12b tail d1 + d2": len(by(d["d1"], size="12b", purpose="design")) > 0 and len(by(d["d2"], size="12b", cond="L5")) > 0,
        "no design cells for 31b/e4b": not [r for r in d["d1"] if r.get("size") in ("31b", "e4b") and r.get("purpose") == "design"],
        "G-null d1 all sizes": all(by(d["d1"], size=z, cond="G-null") for z in sizes),
        "X-graph and G-null d2 all sizes": all(by(d["d2"], size=z, cond=c) for z in sizes for c in ("X-graph", "G-null")),
        "rescore at find and use, 3 sizes": all(by(d["d1"], size=z, purpose="rescore", state=st) for z in sizes for st in ("find", "use")),
        "split on every scored cell": split and all("n_tok_action" in r for r in split),
        "null controls": len(d.get("null_controls", {})) == len(d["task_ids"]),
        "analysis cell outputs": all(os.path.exists(f"/kaggle/working/{f}") for f in outs),
    }
    ok = all(checks.values())
    msg = ", ".join(f"{k}: {'ok' if v else 'FAILED'}" for k, v in checks.items()) + f" | d1 ok {len(split)}, d2 ok {len(by(d['d2']))}"
elif key == "C06":
    import glob, os
    rows = [x for r in d["runs"] for x in r["rows"]]
    A = json.load(open("/kaggle/working/C06_analysis.json")) if os.path.exists("/kaggle/working/C06_analysis.json") else {}
    checks = {
        "4 runs, 2 stages": len(d["runs"]) == 4 and len(d["stages"]) == 2,
        "agent config has 8192": (d.get("agent") or {}).get("sampling", {}).get("max_output_tokens") == 8192
                                 and d.get("sampling_overrides") == {"max_output_tokens": 8192},
        "every request asked for 8192": rows and all(x.get("cmp_requested_output_tokens") == [8192] for x in rows if x.get("tool_calls")),
        "marker traced to summary": sum(x.get("cmp_after_marker_in_summary_only") or 0 for x in rows) > 0,
        "no marker from the original prompt after compaction": sum(x.get("cmp_after_marker_in_prompt") or 0 for x in rows) == 0,
        "summary retention recorded": any(x.get("cmp_summary_ngram5_recall_mean") is not None for x in rows),
        "context crash classified": any("ContextWindowExceeded" in (x.get("error") or "") for x in rows)
                                    and sum(x.get("cmp_context_errors") or 0 for x in rows) > 0,
        "summaries saved privately": sum(r.get("summaries_saved") or 0 for r in d["runs"]) > 0
                                     and bool(glob.glob("/kaggle/working/private/runs/12b/*/summaries.jsonl")),
        "analysis cell outputs": bool(A) and A["setting_check"]["ok"] and len(A.get("figures", [])) == 3
                                 and os.path.exists("/kaggle/working/C06_tables.md"),
        "summary numbers from private files": A.get("A5_summary_retention", {}).get("O0", {}).get("source") == "summaries",
    }
    ok = all(checks.values())
    msg = ", ".join(f"{k}: {'ok' if v else 'FAILED'}" for k, v in checks.items())
elif key in ("C05", "C05S"):
    runs, st = d["runs"], d["stages"]
    good = runs and all(r["aggregate"]["tool_calls_mean"] > 0 and r["aggregate"]["errors"] == 0 for r in runs)
    if key == "C05":
        ok = good and len(runs) == 4 and len(st) == 2 and all("discordant" in s for s in st) and not d.get("stopped") \
             and all(v["O0"] is not None and v["O-all"] is not None for v in d["per_task"].values())
    else:
        ok = good and len(runs) == 2 and str(d.get("stopped", "")).startswith("sequential rule") and st[0].get("discordant", 9) < 2
    msg = f"runs {len(runs)}, stages {[(s['stage'], s.get('discordant', s.get('skipped'))) for s in st]}, stopped {d.get('stopped')!r}, paired {d.get('paired_all')}"
elif key in ("D1", "D1F"):
    import os
    sel = json.load(open("/kaggle/working/D_selection.json"))
    sizes = ("31b", "e4b", "12b")
    ok_rows = lambda rows, **kw: [r for r in rows if r.get("ok") and all(r.get(k) == v for k, v in kw.items())]
    n = len(d["task_ids"])
    A = json.load(open("/kaggle/working/D1_analysis.json")) if os.path.exists("/kaggle/working/D1_analysis.json") else {}
    checks = {
        "selection: sympy, PR-body and pending excluded": sel["excluded_before_records"].get("excluded repo") == 1
            and any("pr_body" in k for k in sel["excluded_before_records"]) and any("pending" in k for k in sel["excluded_before_records"])
            and not [i for i in sel["selected"] if i.startswith("sympy_")] and sel["n_repos"] == 3,
        "all tasks captured": not d.get("capture_missing") and n == len(sel["selected"]),
        "3 sizes, no error, no skip": [s.get("size") for s in d["sizes"]] == list(sizes)
            and not [s for s in d["sizes"] if s.get("error") or (s.get("skipped") and not isinstance(s.get("skipped"), list))] and not d.get("stopped"),
        "every depth-1 cell scored": all(len(ok_rows(d["d1"], size=z, state=st, cond=c)) == n
                                         for z in sizes for st, conds in (("find", ("L0", "L1", "L2", "W", "G-json", "G-null", "X-func", "X-graph")),
                                                                         ("use", ("L0", "L2", "W", "T", "L5", "G-json", "G-null"))) for c in conds),
        "words written": d.get("words_written") == n,
        "per-size files": all(os.path.exists(f"/kaggle/working/D1_heldout_probe_{z}.json") for z in sizes),
        "analysis cell outputs": bool(A) and len(A.get("figures", [])) == 2 and os.path.exists("/kaggle/working/D1_tables.md"),
    }
    if key == "D1":
        checks["depth 2: 5 find + 3 use cells, 2 samples per use cell"] = all(
            len(ok_rows(d["d2"], size=z, state="find", cond=c)) == n for z in sizes for c in ("L0", "L2", "G-json", "X-graph", "G-null")) and all(
            len(ok_rows(d["d2"], size=z, state="use", cond=c)) == 2 * n for z in sizes for c in ("L0", "L2", "L5"))
        checks["R5 in the analysis"] = len(A.get("R5_depth2", {}).get("use", {})) == 9
    else:
        checks["fallback: no depth 2"] = d.get("depth2") is False and not d["d2"] and A.get("R5_depth2") == {"find": {}, "use": {}}
    ok = all(checks.values())
    msg = ", ".join(f"{k}: {'ok' if v else 'FAILED'}" for k, v in checks.items()) + f" | tasks {n}, verdicts {A.get('verdicts')}"
elif key == "D2":
    import os
    rows = [x for r in d["runs"] for x in r["rows"]]
    A = json.load(open("/kaggle/working/D2_analysis.json")) if os.path.exists("/kaggle/working/D2_analysis.json") else {}
    sel = json.load(open("/kaggle/working/D_selection.json"))
    checks = {
        "selection: sympy excluded, same list as D1": not [i for i in d["task_ids"] if i.startswith("sympy_")]
            and d.get("d1_selection_matches") is True and sel["used_by_D2"] == d["task_ids"],
        "test wheels: only the missing one installed": d["test_wheels"]["installed"] == ["dtestdep-0.0.1-py3-none-any.whl"],
        "2 batches, every task run": len(d["runs"]) == 2 and len(rows) == len(d["task_ids"]) and not d.get("stopped"),
        "agent config has 8192": (d.get("agent") or {}).get("sampling", {}).get("max_output_tokens") == 8192,
        "every request asked for 8192": rows and all(x.get("cmp_requested_output_tokens") == [8192] for x in rows if x.get("tool_calls")),
        "marker traced to summary": sum(x.get("cmp_after_marker_in_summary_only") or 0 for x in rows) > 0,
        "failed-edit replay ran": os.path.exists("/kaggle/working/D2_failed_edits.json"),
        "analysis cell outputs": bool(A) and A["setting_check"]["ok"] and len(A.get("figures", [])) == 2
                                 and os.path.exists("/kaggle/working/D2_tables.md") and A["summary_retention"]["source"] == "summaries",
    }
    ok = all(checks.values())
    msg = ", ".join(f"{k}: {'ok' if v else 'FAILED'}" for k, v in checks.items()) + \
          f" | solved {A.get('solve_rate')}, R6 {A.get('R6_claim2_compaction', {}).get('holds')}, R7 {A.get('R7_claim4_crashes', {}).get('holds')}"
elif key == "D1v":
    import os
    A = json.load(open("/kaggle/working/D1v_analysis.json")) if os.path.exists("/kaggle/working/D1v_analysis.json") else {}
    srcs = sorted({r.get("source") for r in d["rows"]})
    ok = (len(d["rows"]) > 0 and srcs == ["D1"] and bool(A) and A["verified_without_sample_row"] == 0
          and len(A.get("V", {})) == 9 and os.path.exists("/kaggle/working/D1v_tables.md"))
    msg = f"{len(d['rows'])} verified samples from {srcs}; analysis cells {len(A.get('V', {}))}"
else:
    ok, msg = True, ""
print(f"content check {key}:", "OK" if ok else "FAILED", "|", msg)
sys.exit(0 if ok else 1)
PY
}
for nb in "$@"; do
  rm -rf /kaggle/working/*
  case $nb in
    C00) PILOT_TEST_IDS=$IDS "$PM" "$NB/C00_gold_check__CPU.ipynb" "$OUT/C00_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         rm -rf /kaggle/input/c00-gold-check-cpu && mkdir -p /kaggle/input/c00-gold-check-cpu
         cp /kaggle/working/C00_gold_check.json "$OUT/"
         cp /kaggle/working/C00_gold_check.json /kaggle/input/c00-gold-check-cpu/ ;;
    C01) PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$NB/C01_smoke_timing__L4x4.ipynb" "$OUT/C01_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C01_smoke_timing.json "$OUT/"; check_content C01 "$OUT/C01_smoke_timing.json" ;;
    C03) MOCK_PROBE=1 PILOT_MIN_VALID=${PILOT_MIN_VALID:-2} PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$NB/C03_probe__L4x4.ipynb" "$OUT/C03_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C03_probe.json "$OUT/"; check_content C03 "$OUT/C03_probe.json"
         rm -rf /kaggle/input/c03-probe-l4x4 && mkdir -p /kaggle/input/c03-probe-l4x4
         cp /kaggle/working/C03_probe.json /kaggle/input/c03-probe-l4x4/
         cp -r /kaggle/working/private /kaggle/input/c03-probe-l4x4/ ;;
    C03X) PILOT_MOCK_FAIL_START=12b MOCK_PROBE=1 PILOT_MIN_VALID=${PILOT_MIN_VALID:-2} PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$NB/C03_probe__L4x4.ipynb" "$OUT/C03X_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C03_probe.json "$OUT/C03X_C03_probe.json"; check_content C03X "$OUT/C03X_C03_probe.json" ;;
    C04) # the attached C03 output is trimmed to look like the real run: no e2b, 12b without depth 2 and with 2 tasks cut
         rm -rf "$OUT/c03_input_backup" && cp -r /kaggle/input/c03-probe-l4x4 "$OUT/c03_input_backup"
         "$VENV/bin/python" - /kaggle/input/c03-probe-l4x4/C03_probe.json <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); cut = set(d["task_ids"][:2])
d["d1"] = [r for r in d["d1"] if r.get("size") != "e2b"]
d["d2"] = [r for r in d["d2"] if r.get("size") not in ("e2b", "12b")]
for r in d["d1"]:
    if r.get("size") == "12b" and r.get("task") in cut:
        r.update(ok=False, why="time_guard")
json.dump(d, open(sys.argv[1], "w"))
PY
         MOCK_PROBE=1 PILOT_MIN_TASKS=2 PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$NB/C04_probe_followup__L4x4.ipynb" "$OUT/C04_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         rm -rf /kaggle/input/c03-probe-l4x4 && cp -r "$OUT/c03_input_backup" /kaggle/input/c03-probe-l4x4
         cp /kaggle/working/C04_probe_followup.json "$OUT/"; check_content C04 "$OUT/C04_probe_followup.json"
         rm -rf /kaggle/input/c04-probe-followup-l4x4 && mkdir -p /kaggle/input/c04-probe-followup-l4x4
         cp /kaggle/working/C04_probe_followup*.json /kaggle/input/c04-probe-followup-l4x4/
         mkdir -p /kaggle/input/c04-probe-followup-l4x4/private && cp /kaggle/working/private/probe_samples_C04_*.jsonl /kaggle/input/c04-probe-followup-l4x4/private/ ;;
    C05|C05S)
         MIND=$([ "$nb" = C05 ] && echo 0 || echo 2)
         PILOT_C05_STAGE1_N=2 PILOT_C05_MIN_DISCORDANT=$MIND PILOT_MIN_TASKS=2 PILOT_MOCK_LLM=1 PILOT_REPO=$REPO \
           "$PM" "$NB/C05_validation_12b__L4x4.ipynb" "$OUT/${nb}_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C05_validation_12b.json "$OUT/${nb}_C05_validation_12b.json"; check_content $nb "$OUT/${nb}_C05_validation_12b.json" ;;
    C06) PILOT_C05_STAGE1_N=2 PILOT_C05_MIN_DISCORDANT=0 PILOT_MIN_TASKS=2 MOCK_SUMMARY_ECHO=1 MOCK_CWE_AT_STEP=3 \
           PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$NB/C06_validation_fix_12b__L4x4.ipynb" "$OUT/C06_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C06_validation_fix_12b.json /kaggle/working/C06_analysis.json /kaggle/working/C06_tables.md "$OUT/"
         check_content C06 "$OUT/C06_validation_fix_12b.json" ;;
    C03v) "$PM" "$NB/C03v_test_verify__CPU.ipynb" "$OUT/C03v_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C03v_test_verify.json "$OUT/"; check_content C03v "$OUT/C03v_test_verify.json" ;;
    D1|D1F) # needs a held-out export where Kaggle mounts D0b's output (tests/make_fake_heldout.py builds a synthetic one)
         HELD=${HELDOUT_FAKE:?set HELDOUT_FAKE to the output dir of tests/make_fake_heldout.py}
         rm -rf /kaggle/input/d0b-heldout-export-cpu && ln -s "$HELD" /kaggle/input/d0b-heldout-export-cpu
         NBF="$NB/D1_heldout_probe__L4x4.ipynb"
         if [ "$nb" = D1F ]; then sed 's/DEPTH2 = True /DEPTH2 = False/' "$NBF" > "$OUT/D1F_in.ipynb"; NBF="$OUT/D1F_in.ipynb"; fi
         PILOT_D_N=6 PILOT_MIN_TASKS=2 MOCK_PROBE=1 PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$NBF" "$OUT/${nb}_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/D1_heldout_probe.json "$OUT/${nb}_D1_heldout_probe.json"; check_content $nb "$OUT/${nb}_D1_heldout_probe.json"
         if [ "$nb" = D1 ]; then
           rm -rf /kaggle/input/d1-heldout-probe-l4x4 && mkdir -p /kaggle/input/d1-heldout-probe-l4x4
           cp /kaggle/working/D1_heldout_probe*.json /kaggle/working/D_selection.json /kaggle/input/d1-heldout-probe-l4x4/
           cp -r /kaggle/working/private /kaggle/input/d1-heldout-probe-l4x4/
         fi ;;
    D2)  # needs the fake export (as D1) and, to test the shared task list, D1's output from a D1 dry run before it
         HELD=${HELDOUT_FAKE:?set HELDOUT_FAKE to the output dir of tests/make_fake_heldout.py}
         rm -rf /kaggle/input/d0b-heldout-export-cpu && ln -s "$HELD" /kaggle/input/d0b-heldout-export-cpu
         PILOT_D_N=6 PILOT_D2_BATCH=3 PILOT_MIN_TASKS=2 MOCK_SUMMARY_ECHO=1 PILOT_MOCK_LLM=1 PILOT_REPO=$REPO \
           "$PM" "$NB/D2_heldout_rollouts_12b__L4x4.ipynb" "$OUT/D2_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/D2_heldout_rollouts_12b.json /kaggle/working/D2_analysis.json /kaggle/working/D2_tables.md "$OUT/"
         check_content D2 "$OUT/D2_heldout_rollouts_12b.json" ;;
    D1v) # needs the fake export and D1's output from a D1 dry run before it
         HELD=${HELDOUT_FAKE:?set HELDOUT_FAKE to the output dir of tests/make_fake_heldout.py}
         rm -rf /kaggle/input/d0b-heldout-export-cpu && ln -s "$HELD" /kaggle/input/d0b-heldout-export-cpu
         "$PM" "$NB/D1v_test_verify__CPU.ipynb" "$OUT/D1v_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/D1v_test_verify.json /kaggle/working/D1v_tables.md "$OUT/"; check_content D1v "$OUT/D1v_test_verify.json" ;;
    NEG313) V13=${NEG313_VENV:?set NEG313_VENV to a Python 3.13 venv with papermill}
         if PILOT_TEST_IDS=$IDS "$V13/bin/papermill" "$NB/C00_gold_check__CPU.ipynb" "$OUT/NEG313_out.ipynb" -k python3 --cwd /tmp --log-level ERROR > "$OUT/NEG313.log" 2>&1; then
           echo "NEG313 FAILED: C00 ran under Python 3.13"; exit 1; fi
         "$VENV/bin/python" - "$OUT/NEG313_out.ipynb" <<'PY'
import json, sys
nb = json.load(open(sys.argv[1]))
ran = [c for c in nb["cells"] if c["cell_type"] == "code" and c.get("execution_count")]
err = [o for c in ran for o in c.get("outputs", []) if o.get("output_type") == "error"]
ok = (len(ran) == 1 and "".join(ran[0]["source"]).startswith("# Environment check")
      and err and err[0]["ename"] == "RuntimeError" and "WRONG ENVIRONMENT" in err[0]["evalue"])
print("NEG313:", "stopped by the environment check after 1 cell" if ok else f"FAILED ({len(ran)} cells ran)")
sys.exit(0 if ok else 1)
PY
         ;;
    C01F|C03F|C04F|C05F)
         KEY=${nb%F}
         case $KEY in
           C01) FILE=C01_smoke_timing__L4x4; OUTJ=C01_smoke_timing.json; AFTER=8 ;;
           C03) FILE=C03_probe__L4x4; OUTJ=C03_probe.json; AFTER=40 ;;
           C04) FILE=C04_probe_followup__L4x4; OUTJ=C04_probe_followup.json; AFTER=40 ;;
           C05) FILE=C05_validation_12b__L4x4; OUTJ=C05_validation_12b.json; AFTER=8 ;;
         esac
         T0=$(date +%s)
         MOCK_FREEZE_AFTER=$AFTER PILOT_WD_INTERVAL=2 PILOT_WD_HEALTH_TIMEOUT=2 PILOT_WD_MAX_FAIL=2 PILOT_AGENT_REQUEST_TIMEOUT=60 \
           MOCK_PROBE=1 PILOT_MIN_VALID=${PILOT_MIN_VALID:-2} PILOT_MIN_TASKS=2 PILOT_C05_STAGE1_N=2 PILOT_C05_MIN_DISCORDANT=0 \
           PILOT_MOCK_LLM=1 PILOT_REPO=$REPO \
           "$PM" "$NB/$FILE.ipynb" "$OUT/${nb}_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/$OUTJ "$OUT/${nb}_$OUTJ"
         "$VENV/bin/python" - "$OUT/${nb}_$OUTJ" "$KEY" "$(( $(date +%s) - T0 ))" <<'PY'
import json, sys
d, key, secs = json.load(open(sys.argv[1])), sys.argv[2], int(sys.argv[3])
fr = d.get("freezes", [])
stop = "second inference-server freeze"
if key == "C05":
    skipped = [s["stage"] for s in d.get("stages", []) if s.get("skipped") == stop]
else:
    skipped = [x.get("model") for x in (d.get("skipped", []) if key == "C01" else d.get("sizes", []))
               if x.get("reason") == stop or x.get("skipped") == stop]
ok = len(fr) == 2 and d.get("stopped") == "second inference-server freeze" and secs < 900
if key == "C01":
    ok = ok and bool(skipped) and d.get("restarts") == 1
elif key == "C05":  # the frozen batch gets a restarted server, the second freeze stops the session before stage 2
    ok = ok and d.get("restarts") == 1 and skipped == [2]
else:  # the sizes after the stop must be listed as skipped, and nothing may have been scored for them
    late = ("12b", "e2b") if key == "C03" else ("31b", "e4b")
    ok = ok and len(skipped) == 2 and not any(r.get("ok") and r.get("size") in late for r in d["d1"])
print(f"{key} freeze test:", "OK" if ok else "FAILED", f"| freezes={len(fr)} restarts={d.get('restarts')} stopped={d.get('stopped')!r}",
      f"| skipped={skipped} | {secs}s | reasons={[f.get('reason') for f in fr]}")
sys.exit(0 if ok else 1)
PY
         ;;
    *) echo "unknown notebook key $nb (use C00 C01 C03 C04 C05 C05S C06 C03v D1 D1F D2 D1v NEG313 C03X C01F C03F C04F C05F)"; exit 2 ;;
  esac
  echo "papermill OK: $nb"
done
