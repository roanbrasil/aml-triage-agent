#!/usr/bin/env python3
"""Score the agent's proposals against ground truth and read the audit log.

    python3 evaluate.py proposals.jsonl audit.jsonl labels.json [tools/aml_tools.duckdb]

Prints the confusion matrix, sensitivity and specificity with Wilson 95% intervals,
the AUC of the agent's confidence, what the audit log says about how it investigated,
and (with the tools database) whether the account ids quoted in each rationale are
real counterparties of the alerted account.
"""
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from math import sqrt


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def auc(scores, labels):
    """Probability that a random true case scores above a random false one (ties count half)."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def load_proposals(path):
    last = {}
    for line in open(path):
        d = json.loads(line)
        last[d["case"]] = d                  # if an agent proposed twice, the last one counts
    return last


def evaluate(proposals, labels):
    cm, scores, ys = Counter(), [], []
    for case, p in sorted(proposals.items()):
        y = labels[case]["label"]
        esc = p["decision"] == "escalate"
        cm[("TP" if y else "FP") if esc else ("FN" if y else "TN")] += 1
        scores.append(p["confidence"] if esc else 1 - p["confidence"])   # one scale: P(suspicious)
        ys.append(y)
    tp, fn, fp, tn = cm["TP"], cm["FN"], cm["FP"], cm["TN"]
    return {
        "n": len(ys), "TP": tp, "FN": fn, "FP": fp, "TN": tn,
        "escalated": (tp + fp) / len(ys),
        "sensitivity": tp / (tp + fn), "sensitivity_ci": wilson(tp, tp + fn),
        "specificity": tn / (tn + fp), "specificity_ci": wilson(tn, tn + fp),
        "auc": auc(scores, ys),
        "mean_score_true": st.mean(s for s, y in zip(scores, ys) if y),
        "mean_score_false": st.mean(s for s, y in zip(scores, ys) if not y),
        "false_closes": sorted((c, p["confidence"]) for c, p in proposals.items()
                               if p["decision"] == "close" and labels[c]["label"] == 1),
    }


def read_audit(path, labels):
    by_case, decisions = defaultdict(list), Counter()
    for line in open(path):
        e = json.loads(line)
        by_case[e["case"]].append(e)
        decisions[e["decision"]] += 1
    n_calls = [len(v) for v in by_case.values()]
    hops = {c: sum(1 for e in v if e["args"].get("acct") and e["args"]["acct"] != labels[c]["acct"])
            for c, v in by_case.items()}
    return {
        "events": sum(n_calls), "decisions": dict(decisions),
        "calls_per_case": (min(n_calls), round(st.mean(n_calls), 2), max(n_calls)),
        "cases_that_inspected_a_counterparty": sum(1 for h in hops.values() if h),
        "mean_counterparty_calls": round(st.mean(hops.values()), 2),
        "mean_bytes_returned": round(st.mean(sum(e["bytes"] for e in v) for v in by_case.values())),
        "tools": dict(Counter(e["tool"] for v in by_case.values() for e in v)),
    }


def grounding(proposals, labels, db):
    import duckdb
    con = duckdb.connect(db, read_only=True)
    cited = real = with_id = dollars = 0
    words = []
    for case, p in proposals.items():
        acct = labels[case]["acct"]
        cps = {r[0] for r in con.execute(
            "SELECT to_acct FROM tx WHERE from_acct=? UNION SELECT from_acct FROM tx WHERE to_acct=?", (acct, acct)).fetchall()}
        ids = set(re.findall(r"\b8[0-9A-F]{8}\b", p["rationale"])) - {acct}
        with_id += bool(ids); cited += len(ids); real += len(ids & cps)
        dollars += "$" in p["rationale"]
        words.append(len(p["rationale"].split()))
    return {"rationales_citing_an_account": with_id, "ids_cited": cited, "ids_that_are_real_counterparties": real,
            "rationales_with_dollar_sign": dollars, "median_words": st.median(words), "max_words": max(words)}


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    proposals, labels = load_proposals(sys.argv[1]), json.load(open(sys.argv[3]))
    out = {"decision": evaluate(proposals, labels), "audit": read_audit(sys.argv[2], labels)}
    if len(sys.argv) > 4:
        out["grounding"] = grounding(proposals, labels, sys.argv[4])
    print(json.dumps(out, indent=1))
