#!/bin/bash
# LOCAL-ONLY: dry-run the generated Kaggle notebooks in a real Jupyter kernel with papermill
# (the same executor Kaggle uses), against a fake /kaggle tree. No GPU: notebooks/C01_smoke_timing__L4x4.ipynb
# and notebooks/C03_probe__L4x4.ipynb use the scripted mock LLM (PILOT_MOCK_LLM=1).
# Attached notebook outputs are placed where Kaggle mounts them: /kaggle/input/<slug of the notebook title>/.
# The venv must be Python 3.12 (the official starter's Kaggle environment) and WHEELHOUSE must hold the full
# wheelhouse (41 wheels), so each notebook's real `pip install` of the wheelhouse runs exactly as on Kaggle.
# Extra key NEG313=<py3.13 venv>: runs C00 under Python 3.13 and expects the environment check to stop it.
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
for nb in "$@"; do
  rm -rf /kaggle/working/*
  case $nb in
    C00) PILOT_TEST_IDS=$IDS "$PM" "$NB/C00_gold_check__CPU.ipynb" "$OUT/C00_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         rm -rf /kaggle/input/c00-gold-check-cpu && mkdir -p /kaggle/input/c00-gold-check-cpu
         cp /kaggle/working/C00_gold_check.json "$OUT/"
         cp /kaggle/working/C00_gold_check.json /kaggle/input/c00-gold-check-cpu/ ;;
    C01) PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$NB/C01_smoke_timing__L4x4.ipynb" "$OUT/C01_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C01_smoke_timing.json "$OUT/" ;;
    C03) MOCK_PROBE=1 PILOT_MIN_VALID=${PILOT_MIN_VALID:-2} PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$NB/C03_probe__L4x4.ipynb" "$OUT/C03_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C03_probe.json "$OUT/"
         rm -rf /kaggle/input/c03-probe-l4x4 && mkdir -p /kaggle/input/c03-probe-l4x4
         cp /kaggle/working/C03_probe.json /kaggle/input/c03-probe-l4x4/
         cp -r /kaggle/working/private /kaggle/input/c03-probe-l4x4/ ;;
    C03v) "$PM" "$NB/C03v_test_verify__CPU.ipynb" "$OUT/C03v_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
         cp /kaggle/working/C03v_test_verify.json "$OUT/" ;;
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
    *) echo "unknown notebook key $nb (use C00 C01 C03 C03v NEG313)"; exit 2 ;;
  esac
  echo "papermill OK: $nb"
done
