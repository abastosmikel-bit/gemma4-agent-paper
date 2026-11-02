"""Embed code-graph nodes with an OPEN model and write the harness's embeddings .npz.

Why: the harness adds the "Code Intelligence Tools" prompt section only if both a graph .json and an
embeddings .npz (>100 bytes) exist for the task (swegemma.harness.agent_runner). The released
embeddings come from an undisclosed Google-internal model (embedding_utils.DEFAULT_FUNC_EMBEDDINGS_SSTABLE),
so held-out tasks need a disclosed substitute. Format: npz of {node id: float32[dim]}, allow_pickle=False,
same keys as the graph's node ids (embedding_utils.load_embeddings_from_npz).

Models (ungated, permissive, NATIVE transformers architectures + safetensors only: no remote code is executed,
no pickled weights are loaded; models needing trust_remote_code, e.g. CodeT5+ or nomic, are excluded on purpose):
  gte       Alibaba-NLP/gte-modernbert-base     (Apache-2.0) 768-d, trained incl. code retrieval
  bge       BAAI/bge-small-en-v1.5              (MIT)        384-d
Optional --map W.npz: a linear map (d_model+1 x 256) fit by pilot_d/embedding_parity.py that translates the
open model's space into the released embeddings' geometry (raw-cosine neighbours, collapsed scale).

Usage: python common/embed_nodes.py GRAPH.json OUT.npz --model gte [--input text|name] [--map W.npz]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MODELS = {
    "gte": ("Alibaba-NLP/gte-modernbert-base", None),
    "bge": ("BAAI/bge-small-en-v1.5", None),
}
MAX_CHARS = 2000  # node texts are code; long bodies are truncated (tokenizers truncate anyway)


def node_inputs(graph: dict, mode: str) -> tuple[list[str], list[str]]:
    ids = [n["id"] for n in graph["nodes"]]
    if mode == "name":
        return ids, ids
    return ids, [f"{n['id']}\n{(n.get('text') or '')[:MAX_CHARS]}" for n in graph["nodes"]]


def embed_texts(model_key: str, texts: list[str], batch: int = 32) -> np.ndarray:
    import torch
    from sentence_transformers import SentenceTransformer

    name, mrl = MODELS[model_key]
    model = SentenceTransformer(name, trust_remote_code=False, truncate_dim=mrl, device="cpu",
                                model_kwargs={"use_safetensors": True, "dtype": torch.float32})
    model.max_seq_length = min(model.max_seq_length or 512, 512)
    return model.encode(texts, batch_size=batch, convert_to_numpy=True,
                        normalize_embeddings=True).astype(np.float32)


def apply_map(X: np.ndarray, W: np.ndarray) -> np.ndarray:
    return (np.hstack([X, np.ones((len(X), 1), dtype=X.dtype)]) @ W).astype(np.float32)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("graph")
    p.add_argument("out")
    p.add_argument("--model", default="gte", choices=sorted(MODELS))
    p.add_argument("--input", default="text", choices=["text", "name"])
    p.add_argument("--map")
    a = p.parse_args()
    g = json.load(open(a.graph))
    ids, texts = node_inputs(g, a.input)
    X = embed_texts(a.model, texts)
    if a.map:
        X = apply_map(X, np.load(a.map)["W"])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, **{i: X[k].astype(np.float32) for k, i in enumerate(ids)})
    print(a.out, X.shape)


if __name__ == "__main__":
    main()
