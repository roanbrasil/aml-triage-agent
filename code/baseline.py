#!/usr/bin/env python3
"""The boring comparison: gradient boosting on 19 per-account aggregates.

    python3 baseline.py vault/aml_full.duckdb vault/labels.json [out.json]

Trains on every alert that is NOT in the agent's evaluation sample, reports 5-fold
cross-validated AUC on those, then scores the same 80 alerts the agent saw. Also
prints what happens at scale if the lowest-scored share of alerts is closed.
"""
import json
import sys

import duckdb
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

W0, W1 = "2022-09-01", "2022-09-11"
FEATURES = ["n_in", "k_in", "amt_in", "n_out", "k_out", "amt_out", "n_sub",
            "ach_out", "ccy_out", "max_out", "med_out", "btc_out", "cash_out", "chq_out", "cc_out",
            "ach_in", "ccy_in", "max_in", "med_in"]


def frame(db):
    con = duckdb.connect(db, read_only=True)
    return con.execute(f"""
        WITH w AS (SELECT * FROM tx WHERE ts >= '{W0}' AND ts < '{W1}' AND from_acct <> to_acct),
        o AS (SELECT from_acct acct, sum((format='ACH')::INT) ach_out, count(DISTINCT pay_ccy) ccy_out,
                     max(amount_paid) max_out, median(amount_paid) med_out,
                     sum((format='Bitcoin')::INT) btc_out, sum((format='Cash')::INT) cash_out,
                     sum((format='Cheque')::INT) chq_out, sum((format='Credit Card')::INT) cc_out
              FROM w GROUP BY 1),
        i AS (SELECT to_acct acct, sum((format='ACH')::INT) ach_in, count(DISTINCT recv_ccy) ccy_in,
                     max(amount_received) max_in, median(amount_received) med_in
              FROM w GROUP BY 1)
        SELECT a.acct, a.launder, a.n_in, a.k_in, a.amt_in, a.n_out, a.k_out, a.amt_out, a.n_sub,
               coalesce(ach_out,0) ach_out, coalesce(ccy_out,0) ccy_out, coalesce(max_out,0) max_out,
               coalesce(med_out,0) med_out, coalesce(btc_out,0) btc_out, coalesce(cash_out,0) cash_out,
               coalesce(chq_out,0) chq_out, coalesce(cc_out,0) cc_out, coalesce(ach_in,0) ach_in,
               coalesce(ccy_in,0) ccy_in, coalesce(max_in,0) max_in, coalesce(med_in,0) med_in
        FROM alerts_full a LEFT JOIN o USING (acct) LEFT JOIN i USING (acct) ORDER BY a.acct""").df()


def main(db, labels_path):
    df = frame(db)
    labels = json.load(open(labels_path))
    sample = {v["acct"]: k for k, v in labels.items()}
    test = df[df.acct.isin(sample)]
    train = df[~df.acct.isin(sample)]
    model = lambda: HistGradientBoostingClassifier(max_depth=4, learning_rate=0.08, max_iter=200, random_state=0)

    Xtr, ytr = train[FEATURES].to_numpy(float), train.launder.to_numpy()
    cv = cross_val_predict(model(), Xtr, ytr, cv=StratifiedKFold(5, shuffle=True, random_state=0), method="predict_proba")[:, 1]
    fitted = model().fit(Xtr, ytr)
    p = fitted.predict_proba(test[FEATURES].to_numpy(float))[:, 1]
    scores = {sample[a]: float(s) for a, s in zip(test.acct, p)}

    order = np.argsort(cv)                          # lowest score first = first to be closed
    points = []
    for share in (0.10, 0.25, 0.50, 0.75):
        k = int(round(share * len(cv)))
        missed = int(ytr[order[:k]].sum())
        kept = ytr[order[k:]]
        points.append({"closed_share": share, "closed": k, "true_missed": missed,
                       "miss_rate": missed / int(ytr.sum()), "precision_of_rest": float(kept.mean())})
    closed = np.arange(len(cv) + 1)
    lost = np.concatenate([[0], np.cumsum(ytr[order])]) / ytr.sum()
    idx = np.unique(np.linspace(0, len(cv), 201).round().astype(int))
    curve = [[float(closed[i] / len(cv)), float(lost[i])] for i in idx]
    ys = np.array([labels[c]["label"] for c in scores])
    ss = np.array(list(scores.values()))
    so = np.argsort(ss)
    return {
        "train_alerts": len(train), "train_true": int(ytr.sum()),
        "cv_auc": float(roc_auc_score(ytr, cv)), "sample_auc": float(roc_auc_score(ys, ss)),
        "single_feature_auc_on_sample": {f: float(roc_auc_score(test.launder, test[f])) for f in ("ach_out", "ach_in")},
        "operating_points_cv": points,
        "sample_true_missed_if_lowest_closed": {k: int(ys[so[:k]].sum()) for k in (7, 20, 40)},
        "scores": scores, "curve_cv": curve,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = main(sys.argv[1], sys.argv[2])
    if len(sys.argv) > 3:
        json.dump(out, open(sys.argv[3], "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("scores", "curve_cv")}, indent=1))
