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
# usage: WHEELHOUSE=<dir> tests/papermill_dryrun.sh <local_comp_dir> <py3.12 venv_dir> <out_dir> [C00 C01 C03 C03v NEG313 ...]
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
    ok = len(d["rows"]) > 0
    msg = f"{len(d['rows'])} verified samples"
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
    C03v) "$PM" "$NB/C03v_test_verify__CPU.ipynb" "$OUT/C03v_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C03v_test_verify.json "$OUT/"; check_content C03v "$OUT/C03v_test_verify.json" ;;
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
    C01F|C03F)
         KEY=${nb%F}; FILE=$([ "$KEY" = C01 ] && echo C01_smoke_timing__L4x4 || echo C03_probe__L4x4)
         OUTJ=$([ "$KEY" = C01 ] && echo C01_smoke_timing.json || echo C03_probe.json)
         AFTER=$([ "$KEY" = C01 ] && echo 8 || echo 40)
         T0=$(date +%s)
         MOCK_FREEZE_AFTER=$AFTER PILOT_WD_INTERVAL=2 PILOT_WD_HEALTH_TIMEOUT=2 PILOT_WD_MAX_FAIL=2 PILOT_AGENT_REQUEST_TIMEOUT=60 \
           MOCK_PROBE=1 PILOT_MIN_VALID=${PILOT_MIN_VALID:-2} PILOT_MOCK_LLM=1 PILOT_REPO=$REPO \
           "$PM" "$NB/$FILE.ipynb" "$OUT/${nb}_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/$OUTJ "$OUT/${nb}_$OUTJ"
         "$VENV/bin/python" - "$OUT/${nb}_$OUTJ" "$KEY" "$(( $(date +%s) - T0 ))" <<'PY'
import json, sys
d, key, secs = json.load(open(sys.argv[1])), sys.argv[2], int(sys.argv[3])
fr = d.get("freezes", [])
stop = "second inference-server freeze"
skipped = [x.get("model") for x in (d.get("skipped", []) if key == "C01" else d.get("sizes", []))
           if x.get("reason") == stop or x.get("skipped") == stop]
ok = len(fr) == 2 and d.get("stopped") == "second inference-server freeze" and skipped and secs < 900
if key == "C01":
    ok = ok and d.get("restarts") == 1
else:  # the sizes after the stop must be listed as skipped, and nothing may have been scored for them
    ok = ok and len(skipped) == 2 and not any(r.get("ok") and r.get("size") in ("12b", "e2b") for r in d["d1"])
print(f"{key} freeze test:", "OK" if ok else "FAILED", f"| freezes={len(fr)} restarts={d.get('restarts')} stopped={d.get('stopped')!r}",
      f"| skipped={skipped} | {secs}s | reasons={[f.get('reason') for f in fr]}")
sys.exit(0 if ok else 1)
PY
         ;;
    *) echo "unknown notebook key $nb (use C00 C01 C03 C03v NEG313 C01F C03F)"; exit 2 ;;
  esac
  echo "papermill OK: $nb"
done
