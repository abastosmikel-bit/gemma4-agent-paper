"""Build one pilot-A arm as a submission directory, starting from the official sample.

Arms
  baseline       starter agent (sample_submission) switched to the chosen model
  hand_written   baseline + skills/hand_written     (on-demand via load_skill)
  self_distilled baseline + skills/self_distilled   (built by distill_skills.py)
  frontier       baseline + skills/frontier         (FRONTIER-WRITTEN; never ship in main track)
  inline_<arm>   control: same skill text pasted into the system prompt, no SkillToolset

Every arm differs from baseline ONLY in (a) the skills/ folder + `skills:` list and
(b) an appended "## Skills" section in prompts/system.md, so differences are attributable.

Usage:
  python build_submission.py --sample /kaggle/input/.../sample_submission \
      --arm hand_written --model gemma-4-e4b-it-qat-w4a16-ct --seed 1 --out /kaggle/working/sub_hw_s1
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE / "skills"

# Pilot budget (per task). The sample's 1 min / 10 calls is a smoke-test value;
# the main-track scorer defaults are 60 min / 100 calls. We use a middle ground
# so a weak model cannot burn the whole GPU budget looping on one task.
EVAL_CONFIG = """evaluation:
  timeout_seconds: 120
  max_tool_calls: {max_tool_calls}
  max_time_minutes: {max_time_minutes}
  max_turns: {max_turns}
"""

SAMPLING = """temperature: {temperature}
top_p: 0.95
max_output_tokens: 16384
seed: {seed}
thinking_config:
  thinking_budget: 4096
  include_thoughts: true
"""

INDEX_HEADER = """

## Skills
You have a small library of skills: short guides for situations that come up in bug fixing.
The skill tools do not list them for you, so here they are. When a description matches your
situation, call `load_skill` with that `skill_name` and follow the guide. Loading a skill does
not use your tool-call budget.
"""

INLINE_HEADER = """

## Working guides
Follow these guides when they apply.
"""


def read_frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{skill_md}: missing YAML frontmatter")
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            fm[k.strip()] = json.loads(v) if v.startswith('"') else v
    fm["body"] = m.group(2).strip()
    return fm


def skill_dirs(arm_skills: str) -> list[Path]:
    root = SKILL_ROOT / arm_skills
    dirs = sorted(p for p in root.iterdir() if (p / "SKILL.md").is_file())
    if not dirs:
        raise SystemExit(f"no skills found under {root}")
    return dirs


def set_model(text: str, model: str) -> str:
    text = re.sub(r"^(\s*model:\s*).*$", rf"\g<1>{model}", text, flags=re.M)
    return re.sub(r"^\s*adapter:\s*.*\n?", "", text, flags=re.M)


def check_no_template_braces(text: str, where: str) -> None:
    # ADK interpolates {identifier} in instructions from session state; an
    # unknown key raises at run time, so skill text pasted into a prompt must not have them.
    bad = re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\??\}", text)
    if bad:
        raise SystemExit(f"{where}: ADK would try to template {bad}; rephrase without braces")


def build(args: argparse.Namespace) -> Path:
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(args.sample, out)
    shutil.rmtree(out / "adapters", ignore_errors=True)  # 31B-shaped dummy LoRAs

    for y in [out / "agent.yaml", *sorted((out / "sub_agents").glob("*.yaml"))]:
        y.write_text(set_model(y.read_text(encoding="utf-8"), args.model), encoding="utf-8")

    (out / "eval_config.yaml").write_text(EVAL_CONFIG.format(**vars(args)), encoding="utf-8")
    (out / "configs" / "sampling.yaml").write_text(SAMPLING.format(**vars(args)), encoding="utf-8")

    arm = args.arm
    if arm == "baseline":
        return out

    inline = arm.startswith("inline_")
    arm_skills = arm[len("inline_"):] if inline else arm
    dirs = skill_dirs(arm_skills)
    system_md = out / "prompts" / "system.md"
    system = system_md.read_text(encoding="utf-8")

    if inline:
        section = INLINE_HEADER + "".join(
            f"\n### {fm['name']}\n{fm['body']}\n" for fm in map(read_frontmatter, (d / "SKILL.md" for d in dirs))
        )
        check_no_template_braces(section, "inline skills")
    else:
        (out / "skills").mkdir()
        lines = []
        for d in dirs:
            fm = read_frontmatter(d / "SKILL.md")
            if fm["name"] != d.name:
                raise SystemExit(f"{d}: frontmatter name {fm['name']!r} must equal folder name")
            shutil.copytree(d, out / "skills" / d.name)
            lines.append(f"- `{fm['name']}`: {fm['description']}")
        # --no-index reproduces plain ADK behaviour: names reachable only via list_skills
        section = "" if args.no_index else INDEX_HEADER + "\n".join(lines) + "\n"
        check_no_template_braces(section, "skill index")
        agent_yaml = out / "agent.yaml"
        text = agent_yaml.read_text(encoding="utf-8").rstrip("\n")
        text += "\nskills:\n" + "".join(f"  - skills/{d.name}\n" for d in dirs)
        agent_yaml.write_text(text, encoding="utf-8")

    system_md.write_text(system.rstrip("\n") + section, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--model", default="gemma-4-e4b-it-qat-w4a16-ct")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tool-calls", dest="max_tool_calls", type=int, default=40)
    ap.add_argument("--max-time-minutes", dest="max_time_minutes", type=float, default=15)
    ap.add_argument("--max-turns", dest="max_turns", type=int, default=80)
    ap.add_argument("--no-index", dest="no_index", action="store_true",
                    help="do not list skills in system.md (plain ADK default visibility)")
    ap.add_argument("--out", required=True)
    print(build(ap.parse_args()))


if __name__ == "__main__":
    main()
