"""Self-distilled skills: turn Gemma's own FAILED traces into 2-4 SKILL.md files,
using the same Gemma model (served by the notebook's vLLM) as the summarizer.

Pipeline (all calls temperature 0, thinking off):
  1. digest   each unresolved trace -> compact action log (tool, short args, outcome),
              plus the shared metric flags (repeats, failed edits, malformed, no submit)
  2. diagnose one Gemma call per trace -> up to 3 failure patterns as JSON
              {pattern, trigger, instead}
  3. merge    one Gemma call over all patterns -> 2-4 skills as JSON
              {name, description, steps[]}
  4. write    validate (kebab name, description <= 1024 chars, no ADK {braces})
              and render SKILL.md. Raw model outputs are kept next to the skills.

Nothing task-specific is asked for: the prompts request repo-agnostic advice, and
the evaluation repo (fastapi) is never shown, so the cross-repo test stays clean.

  python distill_skills.py --runs /kaggle/working/runs/baseline_s1 --out skills_out \
      [--endpoint http://127.0.0.1:8000/v1] [--max-traces 10]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.metrics import task_metrics  # noqa: E402
from common.trace_parser import parse_trace_file  # noqa: E402

ARG_CHARS = 80
MAX_EVENTS = 60

DIAGNOSE = """You are reviewing the action log of a coding agent that FAILED to fix a bug.
The agent works in /workspace with tools such as run_command, read_file, edit_file and submit_patch.

Action log (one line per tool call: tool, arguments, outcome):
{log}

Flags: {flags}

Find up to 3 recurring MISTAKES in how the agent worked (process mistakes, not facts about
this particular codebase). For each give:
- pattern: the mistake, in one sentence
- trigger: the observable situation in which it happens (what the agent sees just before)
- instead: what the agent should do instead, as concrete tool actions
Do not mention file names, class names or library names from this task.
Answer with JSON only: {{"patterns": [{{"pattern": "...", "trigger": "...", "instead": "..."}}]}}"""

MERGE = """Below are mistakes a coding agent made across several failed bug-fixing attempts.

{patterns}

Group them into 2 to 4 reusable SKILLS the agent can load when the trigger happens.
Each skill:
- name: lowercase-kebab-case, at most 4 words
- description: one or two sentences that start with "Use when" and name the trigger,
  so the agent knows when to load it
- steps: 3 to 7 short imperative steps with concrete tool actions
Skills must be generic (any Python repository). No file, class or library names.
Answer with JSON only: {{"skills": [{{"name": "...", "description": "...", "steps": ["..."]}}]}}"""


def chat(endpoint: str, model: str, prompt: str, max_tokens: int = 1500) -> str:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "seed": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"] or ""


def served_model(endpoint: str) -> str:
    with urllib.request.urlopen(endpoint.rstrip("/") + "/models", timeout=30) as r:
        return json.loads(r.read())["data"][0]["id"]


def extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


def short(v) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    s = " ".join(s.split())
    return s if len(s) <= ARG_CHARS else s[:ARG_CHARS] + "..."


def digest(trace_path: Path) -> tuple[str, str]:
    pt = parse_trace_file(trace_path)
    lines = []
    for ev in pt.events[:MAX_EVENTS]:
        args = ", ".join(f"{k}={short(v)}" for k, v in ev.args.items())
        r = ev.response or {}
        if ev.ok:
            ec = r.get("exit_code")
            out = "ok" + (f" (exit {ec})" if ec not in (None, 0) else "")
        else:
            msg = r.get("error_message") or r.get("error") or ""
            out = f"ERROR {ev.error_type}: {short(msg)}"
        lines.append(f"{ev.index + 1}. {ev.name}({args}) -> {out}")
    if len(pt.events) > MAX_EVENTS:
        lines.append(f"... {len(pt.events) - MAX_EVENTS} more calls")
    m = task_metrics(pt)
    flags = (f"{m['tool_calls']} calls, {m['repeat_calls']} repeated, {m['failed_edits']} failed edits, "
             f"{m['malformed_calls']} malformed, submitted={m['submitted']}")
    return "\n".join(lines) or "(no tool calls)", flags


NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def render(skill: dict) -> tuple[str, str]:
    name = re.sub(r"[^a-z0-9-]+", "-", str(skill["name"]).lower()).strip("-")[:64]
    if not NAME_RE.match(name):
        raise ValueError(f"bad skill name {skill['name']!r}")
    desc = " ".join(str(skill["description"]).split())[:1000]
    steps = [" ".join(str(s).split()) for s in skill.get("steps", []) if str(s).strip()]
    body = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    text = f"---\nname: {name}\ndescription: {json.dumps(desc)}\n---\n# {name}\n\n{body}\n"
    # ADK templates {identifier} in prompts; keep skill text free of them.
    text = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", r"<\1>", text)
    return name, text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True, help="results dir with task_results.jsonl and traces/")
    ap.add_argument("--out", required=True)
    ap.add_argument("--endpoint", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--max-traces", type=int, default=10)
    a = ap.parse_args()

    runs = Path(a.runs)
    results = [json.loads(l) for l in (runs / "task_results.jsonl").read_text().splitlines() if l.strip()]
    failed = [r["instance_id"] for r in results if not r.get("resolved")][: a.max_traces]
    model = served_model(a.endpoint)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = {"model": model, "failed_traces": len(failed), "diagnoses": [], "merge_raw": None}

    patterns = []
    for iid in failed:
        tp = runs / "traces" / f"trace_{iid.replace('/', '__')}.json"
        if not tp.exists():
            continue
        action_log, flags = digest(tp)
        raw = chat(a.endpoint, model, DIAGNOSE.format(log=action_log, flags=flags))
        try:
            ps = extract_json(raw).get("patterns", [])[:3]
        except (ValueError, json.JSONDecodeError):
            ps = []
        log["diagnoses"].append({"raw": raw, "parsed": len(ps)})
        patterns += ps

    if not patterns:
        raise SystemExit("no failure patterns extracted; nothing to distill")
    plist = "\n".join(f"- mistake: {p.get('pattern')} | when: {p.get('trigger')} | instead: {p.get('instead')}"
                      for p in patterns)
    raw = chat(a.endpoint, model, MERGE.format(patterns=plist), max_tokens=2500)
    log["merge_raw"] = raw
    skills = extract_json(raw).get("skills", [])[:4]

    written = []
    for s in skills:
        try:
            name, text = render(s)
        except (KeyError, ValueError) as e:
            log.setdefault("rejected", []).append(str(e))
            continue
        if name in written:
            continue
        (out / name).mkdir(exist_ok=True)
        (out / name / "SKILL.md").write_text(text, encoding="utf-8")
        written.append(name)
    log["skills"] = written
    (out / "_distill_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps({"patterns": len(patterns), "skills": written}, indent=2))
    if len(written) < 2:
        raise SystemExit("fewer than 2 valid skills; see _distill_log.json")


if __name__ == "__main__":
    main()
