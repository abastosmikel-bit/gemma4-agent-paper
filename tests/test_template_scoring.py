"""LOCAL-ONLY: the probe's target-token rule against the REAL Gemma 4 chat templates (31b and 12b add an empty
thought block to the generation prompt after a user turn; e2b/e4b don't). Needs the model tokenizer files
(chat_template.jinja, tokenizer.json, tokenizer_config.json) in $GEMMA_TOK/<size>/ and a captured context file in
$PROBE_CONTEXTS (from a dry run of notebooks/C03_probe__L4x4.ipynb); skipped otherwise. No task data is committed.
"""
import copy
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TOK_DIR = Path(os.environ.get("GEMMA_TOK", "/home/user/kdata/gemma_tok"))
CTX = Path(os.environ.get("PROBE_CONTEXTS", "/kaggle/input/c03-probe-l4x4/private/probe_contexts.json"))
pytestmark = pytest.mark.skipif(not (TOK_DIR.exists() and CTX.exists()), reason="needs local tokenizer files and contexts")


@pytest.mark.parametrize("size,expect_find_mode", [("31b", "spliced"), ("12b", "spliced"), ("e4b", "direct")])
def test_target_tokens_are_exactly_the_call(size, expect_find_mode):
    transformers = pytest.importorskip("transformers")
    from pilot_c import probe_runner as pr
    tok = transformers.AutoTokenizer.from_pretrained(TOK_DIR / size)
    ctxs = json.loads(CTX.read_text())
    recs = [json.loads(l) for l in open(CTX.parent / "probe_records.jsonl")]
    last = {}

    def vllm_style(msgs):  # vLLM's chat_utils parses tool-call argument strings into dicts before templating
        m2 = copy.deepcopy(msgs)
        for m in m2:
            for tc in m.get("tool_calls") or []:
                if isinstance(tc["function"].get("arguments"), str):
                    tc["function"]["arguments"] = json.loads(tc["function"]["arguments"])
        return m2

    def fake_post(url, body, timeout=0):
        if url.endswith("/tokenize"):
            ids = tok.apply_chat_template(vllm_style(body["messages"]), tools=body.get("tools"), tokenize=True,
                                          add_generation_prompt=body["add_generation_prompt"], **body.get("chat_template_kwargs", {}))
            return {"tokens": ids if isinstance(ids, list) else ids["input_ids"]}
        last["S"] = body["prompt"]
        return {"choices": [{"prompt_logprobs": [None] + [{str(t): {"logprob": -0.1}} for t in body["prompt"][1:]]}]}

    pr._post = fake_post
    for rec in recs[:2]:
        rec["_base_text"] = ""
        for st, cond in (("find", "L0"), ("use", "L0"), ("find", "G-json"), ("use", "L5")):
            msgs, target, _ = pr.build_messages(rec, ctxs[rec["instance_id"]], st, cond)
            r = pr.score("http://x", "m", msgs, ctxs[rec["instance_id"]]["tools"], target)
            assert r["ok"], (size, st, cond, r)
            text = tok.decode(last["S"][-r["n_tok"]:])
            name = "read_file" if st == "find" else "edit_file"
            assert text.startswith("<|tool_call>call:" + name), text[:60]
            # action/arguments split: the action part is the call header up to the first argument-dependent token
            assert 0 < r["n_tok_action"] < r["n_tok"], r
            act = tok.decode(last["S"][-r["n_tok"]:][:r["n_tok_action"]])
            assert act.startswith("<|tool_call>call:" + name) and len(act) <= len("<|tool_call>call:" + name) + 2, act
            assert abs(r["logp_action"] + r["logp_args"] - r["logp"]) < 1e-3
            if (st, cond) == ("find", "L0"):
                assert r["mode"] == expect_find_mode
            if st == "use":
                assert r["mode"] == "direct"
