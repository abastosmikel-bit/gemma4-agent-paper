#!/bin/bash
# LOCAL-ONLY: dry-run the generated Kaggle notebooks in a real Jupyter kernel with papermill
# (the same executor Kaggle uses), against a fake /kaggle tree. No GPU: notebook 01 / probe
# notebooks use the scripted mock LLM (PILOT_MOCK_LLM=1).
# usage: tests/papermill_dryrun.sh <local_comp_dir> <venv_dir> <out_dir> [00|01|probe ...]
set -euo pipefail
COMP=$1; VENV=$2; OUT=$3; shift 3
REPO=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p /kaggle/input/competitions /kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse /kaggle/working "$OUT"
[ -e /kaggle/input/competitions/gemma-4-developer-agent ] || ln -s "$COMP" /kaggle/input/competitions/gemma-4-developer-agent
PM="$VENV/bin/papermill"
IDS=${PILOT_TEST_IDS:-fastapi_15588,rich_3454,requests_7309,fastapi_14360,rich_4079,requests_7502}
for nb in "$@"; do
  rm -rf /kaggle/working/*
  case $nb in
    00) PILOT_TEST_IDS=$IDS "$PM" "$REPO/notebooks/pilot_c_gold_check_cpu/gold_check_cpu.ipynb" "$OUT/00_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
        mkdir -p /kaggle/input/notebooks/me/pilot-c-gold-check-cpu
        cp /kaggle/working/pilot_c_gold_check_kaggle.json "$OUT/" ;
        cp /kaggle/working/pilot_c_gold_check_kaggle.json /kaggle/input/notebooks/me/pilot-c-gold-check-cpu/ ;;
    01) PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$REPO/notebooks/pilot_c_smoke_timing/smoke_timing.ipynb" "$OUT/01_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
        cp /kaggle/working/pilot_c_smoke_timing.json "$OUT/" ;;
    probe) PILOT_MOCK_LLM=1 PILOT_REPO=$REPO "$PM" "$REPO/notebooks/pilot_c_probe/probe.ipynb" "$OUT/probe_out.ipynb" -k python3 --cwd /tmp --log-level ERROR
        cp /kaggle/working/pilot_c_probe*.json "$OUT/" ;;
  esac
  echo "papermill OK: $nb"
done
