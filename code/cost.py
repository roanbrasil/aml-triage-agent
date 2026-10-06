#!/usr/bin/env python3
"""Cost per alert, read from the agent transcripts.

    python3 cost.py <subagents_dir> "AML triage"      # description prefix of the runs to price

Each alert was one subagent run. Claude Code writes one JSONL per run plus a .meta.json
with the run's description. A model request can span several lines (one per content
block) that share message.id and repeat the same `usage`, so requests are deduplicated
by id. `output_tokens` is only final on the line that carries a stop_reason; when a
request never logged one, output is estimated as characters / 3.5 and counted apart.
"""
import glob
import json
import os
import re
import statistics as st
import sys

PRICES = {  # USD per million tokens: input, 5-minute cache write, 1-hour cache write, cache read, output
    "claude-haiku-4-5": (1.00, 1.25, 2.00, 0.10, 5.00),
    "claude-sonnet-5-5": (2.00, 2.50, 4.00, 0.20, 10.00),
}


def price_of(model):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    raise KeyError(model)


def chars(content):
    n = 0
    for b in content:
        n += len(b.get("text", "")) + len(b.get("thinking", ""))
        if b.get("type") == "tool_use":
            n += len(json.dumps(b.get("input", {})))
    return n


def run_cost(path):
    reqs = {}
    for line in open(path):
        m = json.loads(line).get("message") or {}
        u = m.get("usage")
        if not u or not m.get("id"):
            continue
        r = reqs.setdefault(m["id"], {"model": m["model"], "u": u, "out": 0, "final": False, "chars": 0})
        r["out"] = max(r["out"], u.get("output_tokens", 0))
        r["final"] = r["final"] or bool(m.get("stop_reason"))
        r["chars"] += chars(m.get("content") or [])
    tok = dict(input=0, write5=0, write1h=0, read=0, out=0, out_est=0)
    usd = dict(input=0.0, write=0.0, read=0.0, out=0.0)
    first = None
    for r in reqs.values():
        pi, pw5, pw1, pr, po = price_of(r["model"])
        u, cc = r["u"], r["u"].get("cache_creation") or {}
        w5 = cc.get("ephemeral_5m_input_tokens", u.get("cache_creation_input_tokens", 0))
        w1 = cc.get("ephemeral_1h_input_tokens", 0)
        out = r["out"] if r["final"] else max(r["out"], round(r["chars"] / 3.5))
        if first is None:                    # the first request carries only the harness prompt and the task
            first = u["input_tokens"] + w5 + w1 + u.get("cache_read_input_tokens", 0)
            first_usd = (u["input_tokens"] * pi + w5 * pw5 + w1 * pw1 + u.get("cache_read_input_tokens", 0) * pr) / 1e6
            reread = first * pr / 1e6        # what each later request pays to read that same prefix again
        tok["input"] += u["input_tokens"]; tok["write5"] += w5; tok["write1h"] += w1
        tok["read"] += u.get("cache_read_input_tokens", 0); tok["out"] += out
        tok["out_est"] += 0 if r["final"] else out
        usd["input"] += u["input_tokens"] * pi / 1e6
        usd["write"] += (w5 * pw5 + w1 * pw1) / 1e6
        usd["read"] += u.get("cache_read_input_tokens", 0) * pr / 1e6
        usd["out"] += out * po / 1e6
    model = next(iter(reqs.values()))["model"]
    return {"model": model, "requests": len(reqs), "final_usage": sum(r["final"] for r in reqs.values()),
            "first_context": first, "harness_usd": first_usd + (len(reqs) - 1) * reread,
            "tokens": tok, "usd": usd, "cost": sum(usd.values())}


def main(folder, prefix):
    rows = {}
    for meta in glob.glob(os.path.join(folder, "*.meta.json")):
        d = json.load(open(meta)).get("description", "")
        if not d.startswith(prefix):
            continue
        case = re.search(r"ALR-\d{4}", d).group(0)
        path = meta.replace(".meta.json", ".jsonl")
        started = json.loads(open(path).readline()).get("timestamp", "")
        if case not in rows or started > rows[case]["started"]:      # a re-run replaces the earlier one
            rows[case] = {**run_cost(path), "started": started}
    costs = [r["cost"] for r in rows.values()]
    n = len(rows)
    summary = {
        "alerts": n, "model": next(iter(rows.values()))["model"],
        "mean": st.mean(costs), "median": st.median(costs), "min": min(costs), "max": max(costs), "total": sum(costs),
        "usd_by_meter": {k: sum(r["usd"][k] for r in rows.values()) for k in ("input", "write", "read", "out")},
        "mean_harness_usd": st.mean(r["harness_usd"] for r in rows.values()),
        "harness_share": sum(r["harness_usd"] for r in rows.values()) / sum(costs),
        "mean_requests": st.mean(r["requests"] for r in rows.values()),
        "mean_first_context": st.mean(r["first_context"] for r in rows.values()),
        "mean_read_tokens": st.mean(r["tokens"]["read"] for r in rows.values()),
        "mean_write_tokens": st.mean(r["tokens"]["write5"] + r["tokens"]["write1h"] for r in rows.values()),
        "mean_output_tokens": st.mean(r["tokens"]["out"] for r in rows.values()),
        "share_requests_with_final_usage": sum(r["final_usage"] for r in rows.values()) / sum(r["requests"] for r in rows.values()),
        "share_output_estimated": sum(r["tokens"]["out_est"] for r in rows.values()) / sum(r["tokens"]["out"] for r in rows.values()),
    }
    return rows, summary


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    rows, summary = main(sys.argv[1], sys.argv[2])
    print(json.dumps(summary, indent=1))
    if len(sys.argv) > 3:
        json.dump({"summary": summary, "per_alert": rows}, open(sys.argv[3], "w"), indent=1)
