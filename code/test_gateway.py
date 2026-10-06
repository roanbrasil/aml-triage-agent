#!/usr/bin/env python3
"""What the gateway refuses, checked from the outside.

    python3 test_gateway.py /path/to/tools/aml.py

Copies aml.py into a temporary folder (so the audit log of a real run is untouched),
links the tools database next to it, and drives the CLI the same way the agent does.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile


def call(cli, case, *args):
    r = subprocess.run([sys.executable, cli, "--case", case, *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main(src):
    tmp = tempfile.mkdtemp()
    cli = os.path.join(tmp, "aml.py")
    shutil.copy(src, cli)
    os.symlink(os.path.join(os.path.dirname(os.path.abspath(src)), "aml_tools.duckdb"), os.path.join(tmp, "aml_tools.duckdb"))
    audit = lambda: [json.loads(l) for l in open(os.path.join(tmp, "audit.jsonl"))]

    code, out = call(cli, "ALR-0001", "get_alert")
    assert code == 0 and json.loads(out)["alert_id"] == "ALR-0001"
    assert "label" not in out and "launder" not in out, "ground truth must not be reachable"

    for tool in ("close_alert", "file_report", "update_customer_risk"):       # human-only
        code, out = call(cli, "ALR-0001", tool)
        assert code != 0 and "requires a human" in out, out
        assert audit()[-1]["decision"] == "deny:requires_human"

    code, out = call(cli, "ALR-0001", "drop_table")                           # not in the registry
    assert code != 0 and audit()[-1]["decision"] == "deny:unknown_tool"

    code, out = call(cli, "ALR-0001", "propose_disposition", "--decision", "close")   # incomplete proposal
    assert code != 0 and audit()[-1]["decision"] == "deny:bad_arguments"
    assert not os.path.exists(os.path.join(tmp, "proposals.jsonl")), "a rejected proposal must not be stored"

    code, out = call(cli, "ALR-0001", "list_transactions", json.loads(call(cli, "ALR-0001", "get_alert")[1])["account"], "--limit", "500")
    assert code == 0 and json.loads(out)["returned"] <= 40, "page size is capped at 40"

    n = 0                                                                     # the call budget is per alert
    while call(cli, "ALR-0002", "get_alert")[0] == 0:
        n += 1
        assert n < 100
    assert n == 14 and audit()[-1]["decision"] == "deny:rate_limited", n
    assert call(cli, "ALR-0003", "get_alert")[0] == 0, "another alert has its own budget"

    code, out = call(cli, "ALR-0003", "propose_disposition", "--decision", "escalate", "--confidence", "0.7",
                     "--rationale", "test")
    assert code == 0 and "human analyst makes the final decision" in out
    events = audit()
    assert all({"ts", "case", "tool", "args", "decision", "rows", "bytes"} <= set(e) for e in events)
    denied = sum(1 for e in events if e["decision"].startswith("deny"))
    print(f"ok: {len(events)} audit events, {denied} denied, {len(events) - denied} allowed")
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tools/aml.py")
