"""Pilot A run plan: which (arm, seed, split) runs belong to each notebook phase."""
from __future__ import annotations

import json
from pathlib import Path

SPLITS = json.loads((Path(__file__).with_name("splits.json")).read_text())

# (arm, seed, split)
PHASES: dict[str, list[tuple[str, int, str]]] = {
    # 3 tasks x 2 arms: checks the whole pipeline and gives per-task timing to extrapolate
    "smoke": [("baseline", 1, "smoke"), ("hand_written", 1, "smoke")],
    # cheap-accelerator probe (T4 x2 etc.): one task, baseline only
    "probe": [("baseline", 1, "smoke1")],
    # baseline traces: rich = skill-building traces, fastapi = evaluation seed 1;
    # then Gemma distils its own failed rich traces into skills (see DISTILL_AFTER)
    "phase2": [("baseline", 1, "skill_build_rich"), ("baseline", 1, "eval_fastapi")],
    # headline comparison: baseline vs hand-written, 2 seeds, same 15 fastapi tasks
    "phase3": [("baseline", 2, "eval_fastapi"), ("hand_written", 1, "eval_fastapi"),
               ("hand_written", 2, "eval_fastapi")],
    # only if budget allows (skills must already be committed under pilot_a/skills/)
    "phase4": [("self_distilled", 1, "eval_fastapi"), ("frontier", 1, "eval_fastapi")],
}

# phase -> run whose failed traces feed distill_skills.py
DISTILL_AFTER = {"phase2": ("baseline", 1, "skill_build_rich")}


def split_ids(name: str) -> list[str]:
    if name == "smoke1":
        return SPLITS["smoke"][:1]
    return SPLITS[name]


def run_tag(arm: str, seed: int, split: str) -> str:
    return f"{arm}_s{seed}_{split}"
