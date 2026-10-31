"""Kaggle-side runner for the information-ladder probe (docs/PLAN.md). Runs only on Kaggle / dry runs.

Flow per session:
  1. records  : Level-B probe records for the valid, eligible tasks (CPU)
  2. graph    : harness get_code_neighbors / get_code_subgraph for gold and wrong symbols (CPU)
  3. capture  : real agent loop against the capture server -> exact S-find / S-use contexts (CPU)
  4. per size : start vLLM (starter-identical) -> self-check -> [31b: words] -> depth 1 -> depth 2
Used by notebooks/C03_probe__L4x4.ipynb and notebooks/C03v_test_verify__CPU.ipynb.
Outputs: /kaggle/working/C03_probe.json (numbers + task ids only; commit it),
         /kaggle/working/private/probe_*.jsonl (contexts, records, sampled edits; never commit).
"""
from __future__ import annotations

import concurrent.futures as cf
import copy
import difflib
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from pilot_c import kaggle_runner as kr
from pilot_c import probe as pb
from common.server_watchdog import ServerFrozen, TRIPPED, tracked
from pilot_c.capture_server import CaptureServer, needle_for

AGENT_SAMPLING = {"temperature": 0.2, "top_p": 0.95, "max_tokens": 6144,
                  "chat_template_kwargs": {"enable_thinking": True}, "thinking_token_budget": 4096}
SCORE_KW = {"chat_template_kwargs": {"enable_thinking": False}}
MAX_CELL_TOKENS = 28000


# --------------------------------------------------------------------------- http

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # local server: never via a proxy


# per-request timeouts (s): a 28k-token prefill takes ~10 s on 31b; sampling is <= 6,144 new tokens
TIMEOUT_TOKENIZE, TIMEOUT_SCORE, TIMEOUT_SAMPLE, TIMEOUT_WORDS = 60, 180, 900, 300


def _post(url: str, body: dict, timeout: int = TIMEOUT_SCORE) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with tracked():  # counted by the watchdog; fails fast once the server is declared frozen
        with _OPENER.open(req, timeout=timeout) as r:
            return json.loads(r.read())


def _get(url: str) -> dict:
    with _OPENER.open(url, timeout=60) as r:
        return json.loads(r.read())


def server_root(server) -> str:
    base = getattr(server, "base_url", None) or "http://127.0.0.1:8000"
    base = str(base).rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


# --------------------------------------------------------------------------- 1-2: records and graphs

def build_records(task_ids: list[str]) -> tuple[list[dict], dict[str, str]]:
    d = kr.data_dir()
    tasks = {t["instance_id"]: t for t in kr.load_tasks(d / "tasks.jsonl")}
    gold = kr.build_gold(task_ids)
    recs, excluded = [], {}
    for iid in task_ids:
        rec, why = pb.build_probe_record(tasks[iid], gold[iid], d / "snapshots" / f"{iid}.tgz")
        if rec is None:
            excluded[iid] = why
        else:
            recs.append(rec)
    return recs, excluded


def attach_graphs(recs: list[dict]) -> None:
    """Gold and wrong-symbol subgraphs from the harness's own graph tools (no sandbox needed)."""
    from adk_submission.registry import ModelRegistry
    from swegemma.config import EvalConfig
    from swegemma.context import SwegemmaContext
    from swegemma.models import load_tasks as sg_load
    d = kr.data_dir()
    tasks = {t.instance_id: t for t in sg_load(d / "tasks.jsonl")}
    cfg = EvalConfig(tasks_path=d / "tasks.jsonl", snapshots_dir=d / "snapshots", results_dir=kr.PRIVATE / "graph_ctx",
                     submission_dir=d / "sample_submission", models=ModelRegistry(), sandbox="subprocess",
                     graph_dir=str(d / "graphs"), embeddings_dir=str(d / "embeddings"), display_mode="quiet")
    for rec in recs:
        t = tasks[rec["instance_id"]]
        ctx = SwegemmaContext(docker_manager=None, container_id="", problem_statement="", task=t, repo=t.repo,
                              graph_dir=cfg.graph_dir, embeddings_dir=cfg.embeddings_dir, budget=cfg.budget,
                              harness=cfg.harness)
        if hasattr(ctx, "start_agent_session"):
            ctx.start_agent_session()
        tools = ctx.create_tools()

        def sub(sym: str) -> dict | None:
            try:
                nb = tools["get_code_neighbors"](node=sym, max_neighbors=50)
                nb = json.loads(nb) if isinstance(nb, str) else nb
                neigh = [n.split(";", 1)[-1] for n in nb.get("neighbors", [])]
                neigh = [n for n in neigh if not n.startswith(("tests.", "test."))][:10]
                sg = tools["get_code_subgraph"](nodes=[sym] + neigh)
                sg = json.loads(sg) if isinstance(sg, str) else sg
                return {"focal": sym, "nodes": sg.get("nodes", [sym]), "edges": sg.get("edges", [])}
            except Exception as e:  # noqa: BLE001
                return {"focal": sym, "nodes": [sym], "edges": [], "error": f"{type(e).__name__}"}
        rec["graph"] = sub(rec["gold"]["dotted"])
        if rec["wrong"].get("dotted"):
            rec["wrong"]["graph"] = sub(rec["wrong"]["dotted"])


# --------------------------------------------------------------------------- 3: capture

def capture_contexts(recs: list[dict], budget: dict, concurrency: int = 6) -> dict[str, dict]:
    """Run the real agent loop (sample agent) against the capture server; return per-task contexts."""
    import litellm
    from adk_submission import discover_adapters
    from adk_submission.registry import ModelRegistry
    from adk_submission.resolvers.generation import install_litellm_reasoning_patch
    from google.adk.models.lite_llm import LiteLlm
    from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS

    routes = {r["instance_id"]: {"needle": needle_for(r["problem_statement"]),
                                 "script": [{"name": "read_file", "arguments": r["find_target"]["args"]},
                                            {"name": "submit_patch", "arguments": {}}]} for r in recs}
    srv = CaptureServer(routes)
    try:
        litellm.drop_params = True
        install_litellm_reasoning_patch()
        model = "gemma-4-e4b-it-qat-w4a16-ct"  # alias only; system prompt and tools are size-independent
        agent_dir = kr.prepare_agent_dir(model, budget)
        reg = ModelRegistry()
        reg.register(model, LiteLlm(model="openai/capture", api_base=srv.url, api_key="EMPTY"))
        ad = discover_adapters(str(agent_dir), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
        ids = [r["instance_id"] for r in recs]
        gold = {r["instance_id"]: {"src_files": [r["gold"]["file"]], "functions": []} for r in recs}
        kr.run_condition(agent_dir, reg, ad, ids, gold, "O0", 0, concurrency)
    finally:
        srv.stop()
    out = {}
    for r in recs:
        reqs = srv.captured.get(r["instance_id"], [])
        if len(reqs) >= 2:
            out[r["instance_id"]] = {"find": reqs[0]["messages"], "use": reqs[1]["messages"], "tools": reqs[0].get("tools")}
    return out


# --------------------------------------------------------------------------- message construction

def _content_text(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, list):
        return "".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
    return str(c or "")


def _set_content_text(m: dict, text: str) -> None:
    c = m.get("content")
    if isinstance(c, list):
        done = False
        for x in c:
            if isinstance(x, dict) and "text" in x and not done:
                x["text"], done = text, True
            elif isinstance(x, dict) and "text" in x:
                x["text"] = ""
    else:
        m["content"] = text


def _replace_leaf(obj: Any, old: str, new: str) -> tuple[Any, bool]:
    if isinstance(obj, str):
        return (new, True) if obj == old else (obj, False)
    if isinstance(obj, dict):
        hit = False
        out = {}
        for k, v in obj.items():
            out[k], h = _replace_leaf(v, old, new)
            hit = hit or h
        return out, hit
    if isinstance(obj, list):
        res = [_replace_leaf(v, old, new) for v in obj]
        return [x for x, _ in res], any(h for _, h in res)
    return obj, False


def rewrap_tool_content(captured: str, old_payload: str, new_payload: str) -> str | None:
    """Put `new_payload` into a tool message exactly where the harness put `old_payload`."""
    if captured == old_payload:
        return new_payload
    try:
        dec = json.loads(captured)
    except ValueError:
        return captured.replace(old_payload, new_payload) if old_payload in captured else None
    new, hit = _replace_leaf(dec, old_payload, new_payload)
    if not hit:
        try:
            new, hit = _replace_leaf(dec, json.dumps(json.loads(old_payload)), new_payload)
        except ValueError:
            pass
    if not hit:
        return None
    for ea in (False, True):
        if json.dumps(dec, ensure_ascii=ea) == captured:
            return json.dumps(new, ensure_ascii=ea)
    return json.dumps(new, ensure_ascii=False)


def context_check(rec: dict, ctx: dict) -> dict:
    """Is the captured S-use tool message the harness read of the gold span, as the record predicts?"""
    use = ctx["use"]
    tool_msg = next((m for m in reversed(use) if m.get("role") == "tool"), None)
    ok = tool_msg is not None and rewrap_tool_content(_content_text(tool_msg), rec["read_output"], "X") is not None
    return {"read_output_matches": ok, "n_find_msgs": len(ctx["find"]), "n_use_msgs": len(use)}


def build_messages(rec: dict, ctx: dict, state: str, cond: str) -> tuple[list[dict], dict, str] | None:
    """(messages without target, target assistant message, hint insertion method) or None if the cell is unavailable."""
    base = copy.deepcopy(ctx["find"] if state == "find" else ctx["use"])
    ui = next(i for i, m in enumerate(base) if m.get("role") == "user")
    method = "none"
    if cond in pb.GRAPH_CONDS:
        g = rec["graph"] if cond != "X-graph" else rec["wrong"].get("graph")
        if not g:
            return None
        payload = pb.encode_graph(g["focal"], g["nodes"], g["edges"], pb.GRAPH_CONDS[cond])
        a_tpl = next(m for m in ctx["use"] if m.get("role") == "assistant" and m.get("tool_calls"))
        t_tpl = next(m for m in ctx["use"] if m.get("role") == "tool")
        a = copy.deepcopy(a_tpl)
        a["tool_calls"] = [copy.deepcopy(a_tpl["tool_calls"][0])]
        a["tool_calls"][0]["id"] = "call_probe_graph"
        a["tool_calls"][0]["function"] = {"name": "get_code_subgraph", "arguments": json.dumps({"nodes": [g["focal"]] + [n for n in g["nodes"] if n != g["focal"]]})}
        t = copy.deepcopy(t_tpl)
        if "tool_call_id" in t:
            t["tool_call_id"] = "call_probe_graph"
        if "name" in t:
            t["name"] = "get_code_subgraph"
        wrapped = rewrap_tool_content(_content_text(t_tpl), rec["read_output"], payload)
        if wrapped is None:
            return None
        _set_content_text(t, wrapped)
        base[ui + 1:ui + 1] = [a, t]
        method = "graph-turn"
    else:
        hint = pb.rung_text(rec, cond)
        if hint is None:
            return None
        text, method = pb.insert_hint(_content_text(base[ui]), rec["problem_statement"], hint)
        _set_content_text(base[ui], text)
    tgt_spec = rec["find_target"] if state == "find" else rec["edit_target"]
    a_tpl = next(m for m in ctx["use"] if m.get("role") == "assistant" and m.get("tool_calls"))
    target = copy.deepcopy(a_tpl)
    target["tool_calls"] = [copy.deepcopy(a_tpl["tool_calls"][0])]
    target["tool_calls"][0]["id"] = "call_probe_target"
    target["tool_calls"][0]["function"] = {"name": tgt_spec["tool"], "arguments": json.dumps(tgt_spec["args"], ensure_ascii=False)}
    return base, target, method


# --------------------------------------------------------------------------- scoring and sampling

def score(root: str, model: str, msgs: list[dict], tools: Any, target: dict) -> dict:
    body = {"model": model, "messages": msgs, "tools": tools, "add_generation_prompt": True, **SCORE_KW}
    pre = _post(f"{root}/tokenize", body, TIMEOUT_TOKENIZE)["tokens"]
    full = _post(f"{root}/tokenize", {**body, "messages": msgs + [target], "add_generation_prompt": False},
                 TIMEOUT_TOKENIZE)["tokens"]
    if full[:len(pre)] != pre or len(full) <= len(pre):
        return {"ok": False, "why": "prefix-mismatch", "n_ctx": len(pre)}
    if len(full) > MAX_CELL_TOKENS:  # PLAN §9 rule 4
        return {"ok": False, "why": "too-long", "n_ctx": len(pre)}
    r = _post(f"{root}/v1/completions", {"model": model, "prompt": full, "max_tokens": 1, "temperature": 0,
                                         "prompt_logprobs": 0}, TIMEOUT_SCORE)
    pl = r["choices"][0].get("prompt_logprobs")
    if not pl or len(pl) != len(full):
        return {"ok": False, "why": "no-prompt-logprobs", "n_ctx": len(pre)}
    lps = []
    for i in range(len(pre), len(full)):
        e = pl[i] or {}
        v = e.get(str(full[i])) or e.get(full[i])
        if v is None:
            return {"ok": False, "why": "token-missing", "n_ctx": len(pre)}
        lps.append(float(v["logprob"] if isinstance(v, dict) else v))
    return {"ok": True, "logp": round(sum(lps), 4), "n_tok": len(lps), "mean_logp": round(sum(lps) / len(lps), 5),
            "n_ctx": len(pre)}


def sample(root: str, model: str, msgs: list[dict], tools: Any, n: int, seed: int) -> list[dict]:
    r = _post(f"{root}/v1/chat/completions", {"model": model, "messages": msgs, "tools": tools, "n": n, "seed": seed,
                                               **AGENT_SAMPLING}, TIMEOUT_SAMPLE)
    out = []
    for ch in r.get("choices", []):
        m = ch.get("message") or {}
        out.append({"tool_calls": m.get("tool_calls") or [], "finish": ch.get("finish_reason"),
                    "completion_tokens": (r.get("usage") or {}).get("completion_tokens")})
    return out


def write_words(root: str, model: str, recs: list[dict]) -> dict[str, str]:
    status = {}
    for rec in recs:
        rec["words"] = None
        for strict in (False, True):
            r = _post(f"{root}/v1/chat/completions", {"model": model, "temperature": 0, "max_tokens": 300,
                      "messages": [{"role": "user", "content": pb.words_prompt(rec["diff"], strict)}],
                      "chat_template_kwargs": {"enable_thinking": False}}, TIMEOUT_WORDS)
            w = ((r["choices"][0].get("message") or {}).get("content") or "").strip()
            if w and not pb.words_leak(w, rec["diff"]):
                rec["words"] = w
                break
        status[rec["instance_id"]] = "ok" if rec["words"] else "leak/empty"
    return status


# --------------------------------------------------------------------------- the per-size loop

def cells_for(rec: dict) -> tuple[list[tuple], list[tuple]]:
    d1 = [("find", c, 1) for c in pb.FIND_CONDS] + [("use", c, 1) for c in pb.USE_CONDS] + [("find", "L0", 2), ("use", "L0", 2)]
    d2 = [("find", c, 1) for c in pb.D2_FIND] + [("use", c, 2) for c in pb.D2_USE]
    return d1, d2


def run_size(server, model_alias: str, recs: list[dict], ctxs: dict[str, dict], deadline: float, workers: int = 16,
             write_words_here: bool = False) -> dict[str, Any]:
    root = server_root(server)
    mid = _get(f"{root}/v1/models")["data"][0]["id"]
    size = kr.SHORT[model_alias]
    out: dict[str, Any] = {"size": size, "d1": [], "d2": [], "words_status": None, "skipped": [], "selfcheck": None}
    usable = [r for r in recs if r["instance_id"] in ctxs]
    if not usable:
        raise RuntimeError("SELFCHECK failed: no captured agent contexts (the capture phase produced nothing)")
    # self-check on one cell before spending time
    r0 = usable[0]
    m = build_messages(r0, ctxs[r0["instance_id"]], "use", "L0")
    sc = score(root, mid, m[0], ctxs[r0["instance_id"]]["tools"], m[1])
    out["selfcheck"] = sc
    if not sc.get("ok"):
        raise RuntimeError(f"SELFCHECK failed on {size}: {sc}")
    if write_words_here:
        out["words_status"] = write_words(root, mid, usable)
        pb.assign_cross_task_controls(usable)
    t0 = time.time()

    def d1_job(rec, st, cond, rep):
        if TRIPPED.is_set() or time.time() > deadline:
            return {"task": rec["instance_id"], "size": size, "state": st, "cond": cond, "rep": rep, "ok": False,
                    "why": "server_frozen" if TRIPPED.is_set() else "time_guard"}
        mm = build_messages(rec, ctxs[rec["instance_id"]], st, cond)
        if mm is None:
            return {"task": rec["instance_id"], "size": size, "state": st, "cond": cond, "rep": rep, "ok": False, "why": "unavailable"}
        res = score(root, mid, mm[0], ctxs[rec["instance_id"]]["tools"], mm[1])
        return {"task": rec["instance_id"], "size": size, "state": st, "cond": cond, "rep": rep, "hint_method": mm[2], **res}

    jobs = [(rec, st, c, rep) for rec in usable for (st, c, rep) in cells_for(rec)[0]]
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(d1_job, *j) for j in jobs]
        for f in cf.as_completed(futs):
            try:
                out["d1"].append(f.result())
            except Exception as e:  # noqa: BLE001
                why = "server_frozen" if isinstance(e, ServerFrozen) or TRIPPED.is_set() else f"{type(e).__name__}: {str(e)[:120]}"
                out["d1"].append({"size": size, "ok": False, "why": why})
    out["d1_minutes"] = round((time.time() - t0) / 60, 2)
    samples_private: list[dict] = []
    if TRIPPED.is_set():
        out["skipped"].append("depth2 (server frozen)")
        return out
    if time.time() > deadline:
        out["skipped"].append("depth2 (time guard)")
        return out
    t1 = time.time()

    def d2_job(rec, st, cond, n):
        if TRIPPED.is_set() or time.time() > deadline:
            return [], [{"task": rec["instance_id"], "size": size, "state": st, "cond": cond, "ok": False,
                         "why": "server_frozen" if TRIPPED.is_set() else "time_guard"}]
        mm = build_messages(rec, ctxs[rec["instance_id"]], st, cond)
        if mm is None:
            return [], [{"task": rec["instance_id"], "size": size, "state": st, "cond": cond, "ok": False, "why": "unavailable"}]
        rows, priv = [], []
        for k, smp in enumerate(sample(root, mid, mm[0], ctxs[rec["instance_id"]]["tools"], n, seed=1)):
            if st == "find":
                flags, edited = pb.classify_find(rec, smp["tool_calls"]), None
            else:
                flags, edited = pb.classify_use(rec, smp["tool_calls"])
            rows.append({"task": rec["instance_id"], "size": size, "state": st, "cond": cond, "sample": k, "ok": True,
                         "finish": smp["finish"], **flags})
            if edited is not None:
                diff = "".join(difflib.unified_diff(rec["_base_text"].splitlines(True), edited.splitlines(True),
                                                    f"a/{rec['gold']['file']}", f"b/{rec['gold']['file']}"))
                priv.append({"task": rec["instance_id"], "size": size, "cond": cond, "sample": k, "patch": diff})
        return priv, rows

    jobs2 = [(rec, st, c, n) for rec in usable for (st, c, n) in cells_for(rec)[1]]
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(d2_job, *j) for j in jobs2]
        for f in cf.as_completed(futs):
            try:
                priv, rows = f.result()
                out["d2"] += rows
                samples_private += priv
            except Exception as e:  # noqa: BLE001
                why = "server_frozen" if isinstance(e, ServerFrozen) or TRIPPED.is_set() else f"{type(e).__name__}: {str(e)[:120]}"
                out["d2"].append({"size": size, "ok": False, "why": why})
    out["d2_minutes"] = round((time.time() - t1) / 60, 2)
    kr.PRIVATE.mkdir(parents=True, exist_ok=True)
    with open(kr.PRIVATE / f"probe_samples_{size}.jsonl", "w") as f:
        for s in samples_private:
            f.write(json.dumps(s) + "\n")
    return out


def summarize(d1: list[dict], d2: list[dict]) -> dict[str, Any]:
    """Quick in-notebook summary (medians of paired deltas); full statistics run offline from the rows."""
    import statistics
    out: dict[str, Any] = {}
    by = {}
    for r in d1:
        if r.get("ok"):
            by[(r["size"], r["state"], r["cond"], r["rep"], r["task"])] = r["logp"]
    sizes = sorted({k[0] for k in by})
    for s in sizes:
        for st in ("find", "use"):
            conds = sorted({k[2] for k in by if k[0] == s and k[1] == st})
            for c in conds:
                ref = {"X-file": "L1", "X-func": "L2", "X-graph": "G-json", "X-test": "L3", "X-words": "L4"}.get(c, "L0")
                ds = [by[(s, st, c, 1, t)] - by[(s, st, ref, 1, t)] for (s2, st2, c2, rep, t) in by
                      if s2 == s and st2 == st and c2 == c and rep == 1 and (s, st, ref, 1, t) in by]
                if ds and c != ref:
                    out[f"{s}/{st}/{c}-vs-{ref}"] = {"n": len(ds), "median_delta_nats": round(statistics.median(ds), 3)}
            noise = [abs(by[(s, st, "L0", 2, t)] - by[(s, st, "L0", 1, t)]) for (s2, st2, c2, rep, t) in by
                     if s2 == s and st2 == st and c2 == "L0" and rep == 2 and (s, st, "L0", 1, t) in by]
            if noise:
                out[f"{s}/{st}/L0-rerun-abs-diff"] = {"n": len(noise), "max": round(max(noise), 4)}
    for s in sorted({r["size"] for r in d2 if r.get("ok")}):
        for st, keys in (("find", ("hit_file", "hit_func", "followed_wrong")), ("use", ("on_target", "exact", "applies", "followed_wrong"))):
            for c in sorted({r["cond"] for r in d2 if r.get("ok") and r["size"] == s and r["state"] == st}):
                rows = [r for r in d2 if r.get("ok") and r["size"] == s and r["state"] == st and r["cond"] == c]
                out[f"{s}/{st}/{c}/depth2"] = {"n": len(rows), "tool_call": round(sum(r["tool_call"] for r in rows) / len(rows), 3),
                                              **{k: round(sum(bool(r.get(k)) for r in rows) / len(rows), 3) for k in keys}}
    return out


# --------------------------------------------------------------------------- CPU verification (notebooks/C03v_test_verify__CPU.ipynb)

def verify_samples(records_path: Path, sample_files: list[Path], out_path: Path, timeout_s: int = 300) -> dict[str, Any]:
    """Apply each sampled S-use edit alone to the base snapshot and run the scorer's Phase-2 verification.
    Writes numbers only: (task, size, cond, sample, solves)."""
    from adk_submission.registry import ModelRegistry
    from swegemma.config import EvalConfig
    from swegemma.deduplication import resolve_task_snapshot_paths
    from swegemma.evaluate import Evaluator
    from swegemma.harness.verification import verify_task
    from swegemma.models import load_tasks as sg_load

    d = kr.data_dir()
    cfg = EvalConfig(tasks_path=d / "tasks.jsonl", snapshots_dir=d / "snapshots", results_dir=kr.PRIVATE / "probe_verify",
                     submission_dir=d / "sample_submission", models=ModelRegistry(), sandbox="subprocess",
                     timeout_seconds=timeout_s, verification_timeout_seconds=timeout_s, wheels_dir=d / "wheels",
                     graph_dir=str(d / "graphs"), embeddings_dir=str(d / "embeddings"), display_mode="quiet")
    ev = Evaluator(cfg)
    tasks = {t.instance_id: t for t in sg_load(d / "tasks.jsonl")}
    rows: list[dict] = []
    cache: dict[tuple[str, str], bool] = {}
    for sf in sample_files:
        for line in open(sf):
            s = json.loads(line)
            t = tasks[s["task"]]
            key = (s["task"], s["patch"])
            if key not in cache:
                snap, base, patch = resolve_task_snapshot_paths(d / "snapshots", t.instance_id, t.repo)
                try:
                    r = kr.run_sync(verify_task, ev.docker, cfg, t, snap, base_snapshot_path=base, patch_path=patch,
                                    agent_patch=s["patch"], agent_error=None, trace=None, start_time=time.perf_counter())
                    cache[key] = bool(r.resolved) and bool(s["patch"].strip())
                except Exception:  # noqa: BLE001
                    cache[key] = False
            rows.append({"task": s["task"], "size": s["size"], "cond": s["cond"], "sample": s["sample"], "solves": cache[key]})
            out_path.write_text(json.dumps({"rows": rows}, indent=1))
    summ: dict[str, Any] = {}
    for r in rows:
        k = f"{r['size']}/{r['cond']}"
        a = summ.setdefault(k, {"n": 0, "solves": 0})
        a["n"] += 1
        a["solves"] += int(r["solves"])
    res = {"rows": rows, "summary": summ, "unique_patches_verified": len(cache)}
    out_path.write_text(json.dumps(res, indent=1))
    return res
