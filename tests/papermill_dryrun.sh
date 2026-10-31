#!/bin/bash
# LOCAL-ONLY: dry-run the generated Kaggle notebooks in a real Jupyter kernel with papermill
# (the same executor Kaggle uses), against a fake /kaggle tree. No GPU: notebooks/C01_smoke_timing__L4x4.ipynb
# and notebooks/C03_probe__L4x4.ipynb use the scripted mock LLM (PILOT_MOCK_LLM=1).
# Attached notebook outputs are placed where Kaggle mounts them: /kaggle/input/<slug of the notebook title>/.
# usage: tests/papermill_dryrun.sh <local_comp_dir> <venv_dir> <out_dir> [C00 C01 C03 C03v ...]
set -euo pipefail
COMP=$1; VENV=$2; OUT=$3; shift 3
REPO=$(cd "$(dirname "$0")/.." && pwd)
NB=$REPO/notebooks
mkdir -p /kaggle/input/competitions /kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse /kaggle/working "$OUT"
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
    *) echo "unknown notebook key $nb (use C00 C01 C03 C03v)"; exit 2 ;;
  esac
  echo "papermill OK: $nb"
done
