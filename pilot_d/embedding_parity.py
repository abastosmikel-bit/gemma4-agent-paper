"""Choose and validate the substitute embeddings for held-out tasks (missing-embeddings confound).

On dev graphs where the released (undisclosed-model) embeddings exist, measure how closely each open
substitute reproduces what the agent would see from `search_similar_code` (harness = raw cosine on the
stored vectors, top-k):
  overlap@10   mean |top10_released ∩ top10_substitute| / 10 over all query nodes (random ≈ 10/N)
  spearman     rank correlation of raw-cosine similarities on 20k random node pairs
  top1_sim     median raw-cosine similarity of the top-1 neighbour (the number the agent is shown)
Variants: raw open-model vectors, and the same vectors passed through a linear map into the released
geometry, fit by ridge regression with LEAVE-ONE-REPO-OUT evaluation (the scored repo never fits its map).

Usage: python pilot_d/embedding_parity.py OUT.json CACHE_DIR GRAPH1.json:EMB1.npz [GRAPH2.json:EMB2.npz ...]
Writes aggregates only (no node ids). The final map (fit on all given repos) is saved to CACHE_DIR/W_<model>_<input>.npz;
it is derived from competition embeddings, so it is not committed: rebuild it with this script.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.embed_nodes import apply_map, embed_texts, node_inputs  # noqa: E402

CANDIDATES = [("gte", "text"), ("gte", "name"), ("bge", "text")]
if __import__("os").environ.get("PARITY_CANDIDATES"):  # e.g. "gte/text,bge/text" (the D0 notebook fits only the chosen one)
    CANDIDATES = [tuple(c.split("/")) for c in __import__("os").environ["PARITY_CANDIDATES"].split(",")]
LAMBDAS = (0.1, 1.0, 10.0, 100.0)


def raw_cos(M):
    n = np.linalg.norm(M, axis=1, keepdims=True)
    n[n == 0] = 1
    U = M / n
    return U @ U.T


def metrics(R, C, rng):
    SR, SC = raw_cos(R.astype(np.float64)), raw_cos(C.astype(np.float64))
    np.fill_diagonal(SR, -np.inf); np.fill_diagonal(SC, -np.inf)
    k = 10
    tr, tc = np.argsort(-SR, axis=1)[:, :k], np.argsort(-SC, axis=1)[:, :k]
    ov = np.mean([len(set(a) & set(b)) / k for a, b in zip(tr, tc)])
    n = len(R)
    i, j = rng.integers(0, n, 20000), rng.integers(0, n, 20000)
    keep = i != j
    from scipy.stats import spearmanr  # noqa: PLC0415
    sp = spearmanr(SR[i[keep], j[keep]], SC[i[keep], j[keep]]).statistic
    return {"overlap@10": round(float(ov), 4), "random@10": round(10 / (n - 1), 4), "spearman": round(float(sp), 4),
            "top1_sim_substitute": round(float(np.median(SC.max(1))), 4),
            "top1_sim_released": round(float(np.median(SR.max(1))), 4)}


def fit_map(Xs, Ys, lam):
    X = np.vstack([np.hstack([x, np.ones((len(x), 1))]) for x in Xs]).astype(np.float64)
    Y = np.vstack(Ys).astype(np.float64)
    A = X.T @ X + lam * len(X) / 1000 * np.eye(X.shape[1])
    A[-1, -1] -= lam * len(X) / 1000  # do not shrink the bias row
    return np.linalg.solve(A, X.T @ Y)


def main():
    out, cache = sys.argv[1], Path(sys.argv[2])
    cache.mkdir(parents=True, exist_ok=True)
    pairs = [a.split(":") for a in sys.argv[3:]]
    rng = np.random.default_rng(0)
    data = []
    for gp, ep in pairs:
        g = json.load(open(gp))
        z = np.load(ep, allow_pickle=False)
        ids = [n["id"] for n in g["nodes"] if n["id"] in z.files]
        data.append({"repo": Path(gp).stem.split("_")[0], "graph": g, "ids": ids,
                     "R": np.stack([z[i] for i in ids]).astype(np.float32)})
    report = {"what": __doc__.split("\n")[0], "repos": [d["repo"] for d in data],
              "nodes": [len(d["ids"]) for d in data], "candidates": {}}
    for model, mode in CANDIDATES:
        X = []
        for d in data:
            f = cache / f"{d['repo']}_{len(d['ids'])}_{model}_{mode}.npy"
            if not f.exists():
                idx = {i: k for k, i in enumerate(n["id"] for n in d["graph"]["nodes"])}
                all_ids, texts = node_inputs(d["graph"], mode)
                E = embed_texts(model, texts)
                np.save(f, E[[idx[i] for i in d["ids"]]])
            X.append(np.load(f))
        res = {"raw": [], "mapped_lorocv": []}
        for t, d in enumerate(data):
            res["raw"].append(metrics(d["R"], X[t], rng) if X[t].shape[1] else None)
            # leave-one-repo-out map; lambda chosen by inner leave-one-out over the training repos
            tr = [s for s in range(len(data)) if s != t]
            best = None
            for lam in LAMBDAS:
                inner = []
                for v in tr:
                    fit = [s for s in tr if s != v]
                    W = fit_map([X[s] for s in fit], [data[s]["R"] for s in fit], lam)
                    inner.append(metrics(data[v]["R"], apply_map(X[v], W), rng)["overlap@10"])
                score = float(np.mean(inner))
                best = max(best or (score, lam), (score, lam))
            W = fit_map([X[s] for s in tr], [data[s]["R"] for s in tr], best[1])
            m = metrics(d["R"], apply_map(X[t], W), rng)
            m["lambda"] = best[1]
            res["mapped_lorocv"].append(m)
        for key in ("raw", "mapped_lorocv"):
            res[key + "_mean"] = {k: round(float(np.mean([r[k] for r in res[key]])), 4)
                                  for k in ("overlap@10", "random@10", "spearman", "top1_sim_substitute")}
        res["top1_sim_released_mean"] = round(float(np.mean([r["top1_sim_released"] for r in res["raw"]])), 4)
        lam_all = max(set(r["lambda"] for r in res["mapped_lorocv"]), key=[r["lambda"] for r in res["mapped_lorocv"]].count)
        np.savez(cache / f"W_{model}_{mode}.npz", W=fit_map(X, [d["R"] for d in data], lam_all).astype(np.float32))
        report["candidates"][f"{model}/{mode}"] = res
        print(model, mode, "raw", res["raw_mean"], "| mapped", res["mapped_lorocv_mean"], flush=True)
    Path(out).write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
