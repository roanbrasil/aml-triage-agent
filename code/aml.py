#!/usr/bin/env python3
"""AML triage tools behind a small gateway.

    python3 aml.py --case ALR-0001 <tool> [args]

The agent can READ (five tools) and PROPOSE (one tool). Closing an alert, filing a
report, or changing a customer's risk rating exist in the registry and are denied:
those are human decisions. Every call, allowed or not, leaves one audit event.
"""
import argparse
import json
import os
import sys
import time

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
DB, AUDIT, PROPOSALS = (os.path.join(HERE, f) for f in ("aml_tools.duckdb", "audit.jsonl", "proposals.jsonl"))
MAX_CALLS = 14                       # per alert, proposals included
WINDOW = ("2022-09-01", "2022-09-11")

REGISTRY = {                         # tool -> (read_only, in the agent's bundle)
    "get_alert": (True, True), "get_account": (True, True), "account_profile": (True, True),
    "list_transactions": (True, True), "counterparty_summary": (True, True),
    "propose_disposition": (False, True),
    "close_alert": (False, False), "file_report": (False, False), "update_customer_risk": (False, False),
}

HELP = """TOOLS (read-only unless noted). Any account id may be inspected, not just the alerted one.
  get_alert                                  the alert: account, rules that fired, window, summary stats
  get_account ACCT                           bank, entity type, how many accounts the entity holds
  account_profile ACCT                       totals by direction, currency, payment format and day
  list_transactions ACCT [--direction in|out|both] [--sort time|amount] [--limit N<=40] [--offset K]
  counterparty_summary ACCT [--direction in|out] [--limit N<=25]
                                             per counterparty: count, total, formats, and the counterparty's own in/out degree
  propose_disposition --decision escalate|close --confidence 0..1 --rationale '...'     (WRITE: stores your proposal)
                                             put the rationale in SINGLE quotes and write amounts without the $ sign

RULES THAT GENERATE ALERTS (window 2022-09-01 .. 2022-09-10)
  FAN_IN        received from >= 8 distinct accounts
  FAN_OUT       sent to >= 12 distinct accounts
  PASS_THROUGH  money in ~= money out (within 10%), both >= 10,000, at most 50 outgoing payments
  STRUCTURING   >= 3 outgoing payments between 8,000 and 9,999.99

WHAT TO LOOK FOR
  Laundering typologies: fan-out, fan-in, gather-scatter (many in, then many out), scatter-gather, cycles
  (money returning to its origin through intermediaries), stacks/bipartite layering through accounts that
  only relay. Legitimate look-alikes: payroll, supplier payments, merchant receipts, internal reinvestment.
  About 4% of alerts from these rules are true positives. Missing a true case costs far more than an
  unnecessary escalation, and escalating everything makes the triage worthless.
"""


def audit(case, tool, args, decision, rows=0, size=0):
    with open(AUDIT, "a") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), "case": case, "tool": tool, "args": args,
                            "decision": decision, "rows": rows, "bytes": size}) + "\n")


def calls_so_far(case):
    if not os.path.exists(AUDIT):
        return 0
    return sum(1 for line in open(AUDIT) if json.loads(line)["case"] == case)


def q(con, sql, params=()):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def run(con, case, a):
    w0, w1 = WINDOW
    if a.tool == "get_alert":
        r = q(con, "SELECT * FROM alerts WHERE alert_id=?", (case,))
        return r[0] if r else {"error": "unknown alert"}
    if a.tool == "get_account":
        r = q(con, "SELECT bank_name, entity_name FROM accounts WHERE acct=? LIMIT 1", (a.acct,))
        if not r:
            return {"error": "unknown account"}
        n = con.execute("SELECT count(*) FROM accounts WHERE entity_name=?", (r[0]["entity_name"],)).fetchone()[0]
        return {"account": a.acct, **r[0], "accounts_held_by_entity": n}
    if a.tool == "account_profile":
        out = {"account": a.acct}
        for d, me, other, amt, ccy in (("out", "from_acct", "to_acct", "amount_paid", "pay_ccy"),
                                       ("in", "to_acct", "from_acct", "amount_received", "recv_ccy")):
            base = f"FROM tx WHERE {me}=? AND {other}<>{me}"
            out[d] = {
                "n": con.execute(f"SELECT count(*) {base}", (a.acct,)).fetchone()[0],
                "distinct_counterparties": con.execute(f"SELECT count(DISTINCT {other}) {base}", (a.acct,)).fetchone()[0],
                "by_currency": q(con, f"SELECT {ccy} ccy, count(*) n, round(sum({amt}),2) total {base} GROUP BY 1 ORDER BY 2 DESC", (a.acct,)),
                "by_format": q(con, f"SELECT format, count(*) n {base} GROUP BY 1 ORDER BY 2 DESC", (a.acct,)),
                "by_day": q(con, f"SELECT strftime(ts,'%m-%d') AS dd, count(*) n {base} GROUP BY 1 ORDER BY 1", (a.acct,)),
            }
        out["self_transfers"] = con.execute("SELECT count(*) FROM tx WHERE from_acct=? AND to_acct=?", (a.acct, a.acct)).fetchone()[0]
        return out
    if a.tool == "list_transactions":
        limit, order = min(a.limit, 40), ("amount DESC" if a.sort == "amount" else "ts")
        parts = []
        if a.direction in ("out", "both"):
            parts.append("SELECT strftime(ts,'%m-%d %H:%M') ts, 'out' dir, to_acct counterparty, amount_paid amount, pay_ccy ccy, format FROM tx WHERE from_acct=? AND to_acct<>from_acct")
        if a.direction in ("in", "both"):
            parts.append("SELECT strftime(ts,'%m-%d %H:%M') ts, 'in' dir, from_acct counterparty, amount_received amount, recv_ccy ccy, format FROM tx WHERE to_acct=? AND to_acct<>from_acct")
        sql = " UNION ALL ".join(parts)
        params = (a.acct,) * len(parts)
        total = con.execute(f"SELECT count(*) FROM ({sql})", params).fetchone()[0]
        rows = q(con, f"SELECT * FROM ({sql}) ORDER BY {order} LIMIT {limit} OFFSET {int(a.offset)}", params)
        return {"account": a.acct, "total_matching": total, "returned": len(rows), "transactions": rows}
    if a.tool == "counterparty_summary":
        me, other, amt = ("from_acct", "to_acct", "amount_paid") if a.direction == "out" else ("to_acct", "from_acct", "amount_received")
        rows = q(con, f"""SELECT {other} counterparty, count(*) n, round(sum({amt}),2) total, string_agg(DISTINCT format, ',') formats,
                                 strftime(min(ts),'%m-%d %H:%M') AS first_seen, strftime(max(ts),'%m-%d %H:%M') AS last_seen
                          FROM tx WHERE {me}=? AND {other}<>{me} GROUP BY 1 ORDER BY total DESC LIMIT {min(a.limit, 25)}""", (a.acct,))
        for r in rows:  # the counterparty's own degree: is it a hub, a relay, or an end point?
            r["cp_in_degree"], r["cp_out_degree"] = con.execute(
                "SELECT (SELECT count(DISTINCT from_acct) FROM tx WHERE to_acct=? AND from_acct<>to_acct), (SELECT count(DISTINCT to_acct) FROM tx WHERE from_acct=? AND from_acct<>to_acct)",
                (r["counterparty"], r["counterparty"])).fetchone()
        return {"account": a.acct, "direction": a.direction, "counterparties": rows}
    if a.tool == "propose_disposition":
        with open(PROPOSALS, "a") as f:
            f.write(json.dumps({"case": case, "decision": a.decision, "confidence": a.confidence,
                                "rationale": a.rationale, "ts": round(time.time(), 3)}) + "\n")
        return {"stored": True, "note": "A human analyst makes the final decision."}


def main():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--case", required=True)
    p.add_argument("tool")
    p.add_argument("acct", nargs="?")
    p.add_argument("--direction", default="both", choices=["in", "out", "both"])
    p.add_argument("--sort", default="time", choices=["time", "amount"])
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--decision", choices=["escalate", "close"])
    p.add_argument("--confidence", type=float)
    p.add_argument("--rationale")
    a = p.parse_args()
    args = {k: v for k, v in vars(a).items() if k not in ("case", "tool") and v is not None}
    if a.tool == "help":
        print(HELP); return
    # ---- gateway checks, in order: known tool, in bundle, rate limit, arguments ----
    if a.tool not in REGISTRY:
        audit(a.case, a.tool, args, "deny:unknown_tool"); sys.exit("error: unknown tool (run `help`)")
    if not REGISTRY[a.tool][1]:
        audit(a.case, a.tool, args, "deny:requires_human"); sys.exit("denied: this action requires a human analyst")
    if calls_so_far(a.case) >= MAX_CALLS:
        audit(a.case, a.tool, args, "deny:rate_limited"); sys.exit(f"denied: call budget of {MAX_CALLS} exhausted for this alert")
    if a.tool == "propose_disposition" and (a.decision is None or a.confidence is None or not a.rationale):
        audit(a.case, a.tool, args, "deny:bad_arguments"); sys.exit("error: --decision, --confidence and --rationale are required")
    if a.tool in ("get_account", "account_profile", "list_transactions", "counterparty_summary") and not a.acct:
        audit(a.case, a.tool, args, "deny:bad_arguments"); sys.exit("error: account id required")
    if a.tool == "counterparty_summary" and a.direction == "both":
        a.direction = "out"
    con = duckdb.connect(DB, read_only=True)
    result = run(con, a.case, a)
    text = json.dumps(result, default=str, separators=(",", ":"))
    rows = len(next((v for v in result.values() if isinstance(v, list)), [])) if isinstance(result, dict) else 0
    audit(a.case, a.tool, args, "allow", rows, len(text))
    print(text)


if __name__ == "__main__":
    main()
