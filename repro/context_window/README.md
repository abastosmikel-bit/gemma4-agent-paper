# Context-window overflow before compaction: minimal reproduction and one-line fix

**Private until the paper is submitted. Do not post to the forum or a public repo before then.**

## The problem

The official starter serves the model with vLLM at `max_model_len=32768`. The sample agent asks for up to
`max_output_tokens: 16384` (`configs/sampling.yaml`; swegemma's default). vLLM 0.19.1 rejects any request whose prompt
plus requested output exceeds `max_model_len`, so **the prompt may never exceed 32,768 − 16,384 = 16,384 tokens**.

ADK compacts the history when the most recent prompt *it has already seen* is ≥ 14,336 tokens (starter:
`EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5)`). The
check uses the previous request's size, so one step that adds more than ~2,000 tokens (a long file read, a test log) can
take the prompt from below 14,336 to above 16,384. The request is then rejected before compaction has had a chance to
run. litellm raises `ContextWindowExceededError`, and the harness ends the task.

## Run it (CPU, a few seconds)

```bash
pip install google-adk==1.36.1
```

```bash
python repro.py
```

- **Real in this repro:** google-adk 1.36.1 itself (agent loop, token-threshold compaction with the starter's
  settings, summarizer).
- **Simulated:** only the model and server. A fake model counts prompt tokens (as whitespace-separated words), reports
  them as usage the way vLLM does, and applies vLLM's length rule.
- **Tool outputs:** five reads of 2,000 words, then one 4,000-word test log.
- Tested with Python 3.12 and 3.13.

Output (abridged):

```
== starter setting: max_output_tokens 16384 (effective prompt limit 32768 - 16384 = 16384)
  6  agent        12591     16384    28975  ok          <- 12,591 < 14,336: no compaction
  7  agent        16606     16384    32990  REJECTED    <- one large tool output: 16,606 + 16,384 > 32,768
== fix: max_output_tokens 8192 (effective prompt limit 24576)
  7  agent        16606      8192    24798  ok
  8  summarizer      51         0       51  ok   (compaction: summarizer call)
  9  agent         9074      8192    17266  ok          <- compacted
REPRODUCED: the starter setting overflows before compaction runs; 8192 avoids it.
```

## The fix (one line in the agent's `configs/sampling.yaml`)

```yaml
max_output_tokens: 8192   # was 16384; prompt limit becomes 32768 - 8192 = 24576
```

The thinking budget stays at 4,096, so 8,192 still leaves room for a tool call after the thinking. This file is shared
by the agent and its `code_analyzer` sub-agent.

## What it does on real GPUs (documented numbers; Kaggle, 4×L4, vLLM 0.19.1, gemma-4-12b)

- **Starter setting**, `notebooks/C05_validation_12b__L4x4.ipynb` (`results/C05_analysis.json` on `pilot/c-bottleneck`):
  - 14 of 30 no-hint runs and 9 of 30 hinted runs ended with `ContextWindowExceeded`. 11 of the 23 never reached a
    compaction (they died at tool call 5–23).
  - The server log shows vLLM's `VLLMValidationError`.
- **With the fix:** `notebooks/C06_validation_fix_12b__L4x4.ipynb` (same 30 tasks, only this line changed): *pending*.
  It also logs the requested output tokens and the prompt size before any context error, per request.

## Sources

- vLLM 0.19.1: `vllm/entrypoints/openai/engine/serving.py`. The check is
  `if max_tokens is not None and token_num + max_tokens > max_model_len: raise VLLMValidationError(...)`.
- google-adk 1.36.1: `google/adk/apps/compaction.py`. `_latest_prompt_token_count` returns the most recent event's
  `prompt_token_count`; compaction runs only if it is ≥ `token_threshold`.
- google-adk 1.36.1: `google/adk/models/lite_llm.py` maps `max_output_tokens` to `max_completion_tokens`.
- swegemma 0.2.11: `swegemma/config.py`, default `max_output_tokens: 16384`.
- Starter notebook (ryanholbrook/getting-started-gemma-4-developer-agent): `VllmConfig(max_model_len=32768, …)` and the
  `EventsCompactionConfig` above.
