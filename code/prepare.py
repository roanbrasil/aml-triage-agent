#!/usr/bin/env python3
"""Build everything the experiment needs from the IBM AML HI-Small dataset.

    python3 prepare.py /path/to/HI-Small_Trans.csv /path/to/HI-Small_accounts.csv

Writes two places on purpose:
  vault/   aml_full.duckdb + labels.json     ground truth; the agent must never see this folder
  tools/   aml_tools.duckdb                  what the gateway serves: no label column anywhere

Dataset: Altman et al., "Realistic Synthetic Financial Transactions for Anti-Money
Laundering Models" (arXiv 2306.16424), CDLA-Sharing-1.0.
"""
import json
import os
import random
import sys

import duckdb

W0, W1 = "2022-09-01", "2022-09-11"          # monitoring window, end exclusive
SEED, N_PER_CLASS, MAX_TX = 20261003, 40, 2000

RULES = {                                     # name -> SQL predicate over the per-account features
    "FAN_IN": "k_in >= 8",
    "FAN_OUT": "k_out >= 12",
    "PASS_THROUGH": "amt_in >= 10000 AND amt_out >= 10000 AND n_out <= 50 "
                    "AND abs(amt_in - amt_out) / greatest(amt_in, amt_out) < 0.1",
    "STRUCTURING": "n_sub >= 3",
}


def build(trans_csv, accounts_csv, vault="vault", tools="tools", sample_file=None):
    os.makedirs(vault, exist_ok=True)
    os.makedirs(tools, exist_ok=True)
    full = os.path.join(vault, "aml_full.duckdb")
    if os.path.exists(full):
        os.remove(full)
    con = duckdb.connect(full)

    # The CSV has two columns called "Account"; read by position.
    con.execute(f"""
        CREATE TABLE tx AS
        SELECT row_number() OVER () AS tx_id, strptime(column00, '%Y/%m/%d %H:%M') AS ts,
               column01 AS from_bank, column02 AS from_acct, column03 AS to_bank, column04 AS to_acct,
               column05::DOUBLE AS amount_received, column06 AS recv_ccy,
               column07::DOUBLE AS amount_paid, column08 AS pay_ccy, column09 AS format,
               column10::INTEGER AS is_laundering
        FROM read_csv('{trans_csv}', header=false, skip=1, all_varchar=true)""")
    con.execute(f"""
        CREATE TABLE accounts AS
        SELECT column0 AS bank_name, column1 AS bank_id, column2 AS acct, column3 AS entity_id, column4 AS entity_name
        FROM read_csv('{accounts_csv}', header=false, skip=1, all_varchar=true)""")

    # Per-account features over the window, self-transfers excluded.
    con.execute(f"""
        CREATE TABLE feat AS
        WITH w AS (SELECT * FROM tx WHERE ts >= '{W0}' AND ts < '{W1}' AND from_acct <> to_acct),
        o AS (SELECT from_acct acct, count(*) n_out, count(DISTINCT to_acct) k_out, sum(amount_paid) amt_out,
                     sum((amount_paid >= 8000 AND amount_paid < 10000)::INT) n_sub,
                     sum((format = 'ACH')::INT) ach_out
              FROM w GROUP BY 1),
        i AS (SELECT to_acct acct, count(*) n_in, count(DISTINCT from_acct) k_in, sum(amount_received) amt_in
              FROM w GROUP BY 1),
        l AS (SELECT DISTINCT acct FROM (SELECT from_acct acct FROM w WHERE is_laundering = 1
                                         UNION ALL SELECT to_acct FROM w WHERE is_laundering = 1))
        SELECT coalesce(o.acct, i.acct) acct,
               coalesce(n_out, 0) n_out, coalesce(k_out, 0) k_out, coalesce(amt_out, 0) amt_out,
               coalesce(n_in, 0) n_in, coalesce(k_in, 0) k_in, coalesce(amt_in, 0) amt_in,
               coalesce(n_sub, 0) n_sub, coalesce(ach_out, 0) ach_out,
               (coalesce(o.acct, i.acct) IN (SELECT acct FROM l))::INT launder
        FROM o FULL JOIN i ON o.acct = i.acct""")

    fired = ", ".join(f"CASE WHEN {p} THEN '{r}' END" for r, p in RULES.items())
    con.execute(f"""
        CREATE TABLE alerts_full AS
        SELECT acct, launder, list_filter([{fired}], x -> x IS NOT NULL) AS rules,
               n_in, k_in, amt_in, n_out, k_out, amt_out, n_sub
        FROM feat WHERE {' OR '.join(f'({p})' for p in RULES.values())}""")

    stats = {
        "transactions": con.execute("SELECT count(*) FROM tx").fetchone()[0],
        "laundering_transactions": con.execute("SELECT sum(is_laundering) FROM tx").fetchone()[0],
        "active_accounts": con.execute("SELECT count(*) FROM feat").fetchone()[0],
        "laundering_accounts": con.execute("SELECT sum(launder) FROM feat").fetchone()[0],
        "alerts": con.execute("SELECT count(*) FROM alerts_full").fetchone()[0],
        "true_alerts": con.execute("SELECT sum(launder) FROM alerts_full").fetchone()[0],
        "by_rule": {r: con.execute(f"SELECT count(*), sum(launder) FROM alerts_full WHERE list_contains(rules, '{r}')").fetchone()
                    for r in RULES},
    }

    # Evaluation sample: balanced, so 80 alerts are enough to estimate sensitivity AND specificity.
    if sample_file:                           # reuse the exact sample of the article
        sample = [(a, acct) for a, acct in json.load(open(sample_file)).items()]
    else:
        pool = {lab: [r[0] for r in con.execute(
            "SELECT acct FROM alerts_full WHERE launder = ? AND n_in + n_out <= ? ORDER BY acct", (lab, MAX_TX)).fetchall()]
            for lab in (0, 1)}
        rng = random.Random(SEED)
        picked = rng.sample(pool[1], N_PER_CLASS) + rng.sample(pool[0], N_PER_CLASS)
        rng.shuffle(picked)
        sample = [(f"ALR-{k + 1:04d}", acct) for k, acct in enumerate(picked)]
    con.execute("CREATE TABLE sample (alert_id VARCHAR, acct VARCHAR)")
    con.executemany("INSERT INTO sample VALUES (?, ?)", sample)
    labels = {a: {"acct": acct, "label": lab} for a, acct, lab in con.execute(
        "SELECT s.alert_id, s.acct, f.launder FROM sample s JOIN alerts_full f USING (acct) ORDER BY 1").fetchall()}
    json.dump(labels, open(os.path.join(vault, "labels.json"), "w"), indent=1)
    con.close()

    # The database the agent reads from: same transactions, no label, window only.
    out = os.path.join(tools, "aml_tools.duckdb")
    if os.path.exists(out):
        os.remove(out)
    t = duckdb.connect(out)
    t.execute(f"ATTACH '{full}' AS v (READ_ONLY)")
    t.execute(f"""CREATE TABLE tx AS SELECT tx_id, ts, from_bank, from_acct, to_bank, to_acct, amount_received,
                         recv_ccy, amount_paid, pay_ccy, format FROM v.tx WHERE ts < '{W1}'""")
    t.execute("CREATE TABLE accounts AS SELECT acct, bank_name, entity_name FROM v.accounts")
    t.execute(f"""CREATE TABLE alerts AS
                  SELECT s.alert_id, s.acct AS account, a.rules, '{W0}..2022-09-10' AS "window",
                         a.n_in, a.k_in AS distinct_senders, round(a.amt_in, 2) AS total_in,
                         a.n_out, a.k_out AS distinct_receivers, round(a.amt_out, 2) AS total_out,
                         a.n_sub AS near_threshold_payments
                  FROM v.sample s JOIN v.alerts_full a USING (acct)""")
    t.execute("CREATE INDEX i_from ON tx(from_acct)")
    t.execute("CREATE INDEX i_to ON tx(to_acct)")
    cols = {r[0] for tb in ("tx", "accounts", "alerts") for r in t.execute(f"DESCRIBE {tb}").fetchall()}
    assert not cols & {"is_laundering", "launder", "label"}, "label leaked into the tools database"
    t.close()
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    s = build(sys.argv[1], sys.argv[2], sample_file=sys.argv[3] if len(sys.argv) > 3 else None)
    print(json.dumps(s, indent=1, default=str))
