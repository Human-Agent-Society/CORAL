#!/usr/bin/env python3
# ruff: noqa: N803, N806, E741, E402, E401, E701, E702, S101  (numeric notation; owner-side analysis script)
"""Re-embed every prompt with upstream's recipe and refit the predictor out of fold.

Upstream (train_generic.py) fits per-model Ridge(alpha=10) heads on Qwen2.5-0.5B
mean-pooled embeddings of the merged train matrices and predicts train IN SAMPLE.
Builders therefore trained against a cleaner signal than val/test deliver. This
script rebuilds the embeddings locally (MPS/CPU), checks the recipe against the
saved heads, and writes: (a) 5-fold out-of-fold train predictions, (b) val and
test predictions from the full-train fit. Owner-side only; reads private matrices.
"""

import hashlib
import json
import os
import sys

import numpy as np

PRIV = os.environ.get("SKYSYNTH_PRIVATE") or sys.exit(
    "set SKYSYNTH_PRIVATE to the owner-only data root"
)
DATA = f"{PRIV}/build/llm-router/evaluator/benchmark/.data/traces"
ART = f"{PRIV}/build/llm-router/evaluator/benchmark/artifacts"
OUT = f"{PRIV}/refit"
TENANTS, SPLITS = ("A", "B"), ("train", "val", "test")


def load(t, s):
    return [json.loads(l) for l in open(f"{DATA}/matrix_tenant{t}_{s}.jsonl")]


def embed_phase():
    import torch
    from transformers import AutoModel, AutoTokenizer

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
    model = (
        AutoModel.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct", torch_dtype=torch.float32)
        .to(dev)
        .eval()
    )
    for t in TENANTS:
        for s in SPLITS:
            path = f"{OUT}/emb_tenant{t}_{s}.npz"
            if os.path.exists(path):
                continue
            rows = load(t, s)
            texts = [r["task"] + " || " + r["prompt_head"] for r in rows]
            out = []
            with torch.no_grad():
                for i in range(0, len(texts), 128):
                    b = tok(
                        texts[i : i + 128],
                        padding=True,
                        truncation=True,
                        max_length=160,
                        return_tensors="pt",
                    ).to(dev)
                    h = model(**b).last_hidden_state
                    m = b["attention_mask"].unsqueeze(-1)
                    out.append(((h * m).sum(1) / m.sum(1)).float().cpu().numpy())
            np.savez(path, X=np.vstack(out), ids=np.array([r["prompt_id"] for r in rows]))
            print("embedded", t, s, len(texts), flush=True)


def fit_phase():
    from sklearn.linear_model import Ridge

    heads = np.load(f"{ART}/generic_heads.npz")
    fleet = list(heads["fleet"])
    up = json.load(open(f"{ART}/generic_predictions.json"))
    tr_rows = load("A", "train") + load("B", "train")
    Xtr = np.vstack([np.load(f"{OUT}/emb_tenant{t}_train.npz")["X"] for t in TENANTS])
    Q = np.array([[r["score"][m] for m in fleet] for r in tr_rows])
    # recipe check: saved heads applied to our embeddings vs upstream's own train predictions
    P_saved = Xtr @ heads["coef"].T + heads["intercept"]
    P_up = np.array([up["pred"][r["prompt_id"]] for r in tr_rows])
    err = np.abs(P_saved - P_up)
    print(
        f"recipe check (saved heads on our embeddings vs upstream train preds): mean abs err {err.mean():.4f}, max {err.max():.4f}, corr {np.corrcoef(P_saved.ravel(), P_up.ravel())[0, 1]:.4f}"
    )
    # full-train refit (should match saved heads) and 5-fold out-of-fold train predictions
    full = [Ridge(alpha=10.0).fit(Xtr, Q[:, j]) for j in range(len(fleet))]
    rng = np.random.RandomState(20260920)
    folds = rng.permutation(len(tr_rows)) % 5
    oof = np.zeros_like(Q, dtype=float)
    for k in range(5):
        tr, te = folds != k, folds == k
        for j in range(len(fleet)):
            oof[te, j] = Ridge(alpha=10.0).fit(Xtr[tr], Q[tr, j]).predict(Xtr[te])
    ins = np.stack([h.predict(Xtr) for h in full], axis=1)

    def corr(a, b):
        return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])

    def hit(P):
        return float(np.mean([Q[i, int(np.argmax(P[i]))] == Q[i].max() for i in range(len(Q))]))

    print(
        f"train: in-sample corr {corr(ins, Q):.3f} hit {hit(ins):.3f} | out-of-fold corr {corr(oof, Q):.3f} hit {hit(oof):.3f}"
    )
    pred = {"train_oof": {}, "train_insample": {}, "val": {}, "test": {}}
    for r, p in zip(tr_rows, oof):
        pred["train_oof"][r["prompt_id"]] = [round(float(x), 4) for x in p]
    for r, p in zip(tr_rows, ins):
        pred["train_insample"][r["prompt_id"]] = [round(float(x), 4) for x in p]
    for s in ("val", "test"):
        rows = sum((load(t, s) for t in TENANTS), [])
        X = np.vstack([np.load(f"{OUT}/emb_tenant{t}_{s}.npz")["X"] for t in TENANTS])
        P = np.stack([h.predict(X) for h in full], axis=1)
        for r, p in zip(rows, P):
            pred[s][r["prompt_id"]] = [round(float(x), 4) for x in p]
        if s == "val":
            Qv = np.array([[r["score"][m] for m in fleet] for r in rows])
            Pu = np.array([up["pred"][r["prompt_id"]] for r in rows])
            print(
                f"val: refit corr {corr(P, Qv):.3f} | upstream-artifact corr {corr(Pu, Qv):.3f} | refit-vs-upstream mean abs diff {np.abs(P - Pu).mean():.4f}"
            )
    art = {
        "meta": {
            "recipe": up["meta"]["recipe"],
            "note": "train_oof = 5-fold out-of-fold; val/test from the full-train fit; rebuilt locally 2026-09-20",
            "folds_seed": 20260920,
        },
        "fleet": fleet,
        "mean_cost_train": up["mean_cost_train"],
        "pred": pred,
    }
    payload = json.dumps(art, sort_keys=True)
    open(f"{OUT}/predictions_refit.json", "w").write(payload)
    print("wrote predictions_refit.json sha256", hashlib.sha256(payload.encode()).hexdigest()[:16])


if __name__ == "__main__":
    {"embed": embed_phase, "fit": fit_phase, "all": lambda: (embed_phase(), fit_phase())}[
        sys.argv[1] if len(sys.argv) > 1 else "all"
    ]()
