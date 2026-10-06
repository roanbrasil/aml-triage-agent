# AML alert-triage agent: gateway, audit log, evaluation

Code and results for the article. Nothing here contains the raw dataset; download it first.

## Data

IBM AML HI-Small (`HI-Small_Trans.csv`, `HI-Small_accounts.csv`), from Altman et al.,
"Realistic Synthetic Financial Transactions for Anti-Money Laundering Models" (arXiv 2306.16424).
License: CDLA-Sharing-1.0. Mirrors: Kaggle `ealtman2019/ibm-transactions-for-anti-money-laundering-aml`,
Hugging Face `OsamaMIT/IBM-AML-HI-Small`.

## Steps

```bash
pip install duckdb scikit-learn pandas

# 1. Build the labeled vault and the label-free tools database (about 40 s)
python3 code/prepare.py HI-Small_Trans.csv HI-Small_accounts.csv
cp code/aml.py tools/

# 2. Check what the gateway refuses
python3 code/test_gateway.py tools/aml.py

# 3. Run the agent: one fresh process per alert, prompt in prompt.txt (replace ALR-00XX and the path)
#    The agent appends to tools/audit.jsonl and tools/proposals.jsonl through the CLI.

# 4. Score it
python3 code/evaluate.py tools/proposals.jsonl tools/audit.jsonl vault/labels.json tools/aml_tools.duckdb
python3 code/baseline.py vault/aml_full.duckdb vault/labels.json results/baseline.json

# 5. Cost per alert (Claude Code subagent transcripts)
python3 code/cost.py ~/.claude/projects/<project>/<session>/subagents "AML triage" results/cost_haiku.json

# 6. Figures and tables
python3 code/figs.py en vault/labels.json && python3 code/tables.py en
```

Keep `vault/` out of the agent's reach. `prepare.py` with the default seed reproduces the
article's 80-alert sample exactly (ALR-0001 .. ALR-0080).

## Files

| File | What it is |
| --- | --- |
| `code/aml.py` | the gateway CLI: registry, bundle check, call budget, audit event per call |
| `code/prepare.py` | loads the CSVs, applies the four alert rules, draws the sample, writes vault/ and tools/ |
| `code/test_gateway.py` | drives the CLI from the outside and asserts on the denials |
| `code/evaluate.py` | confusion matrix, Wilson intervals, AUC of the confidence, audit statistics, rationale grounding |
| `code/baseline.py` | gradient boosting on 19 per-account aggregates, operating points at scale |
| `code/cost.py` | cost per alert from the transcripts, with the harness share split out |
| `code/figs.py`, `code/tables.py` | figures and table images |
| `prompt.txt` | the agent prompt |
| `results/` | audit logs and proposals of both arms, evaluation, cost, baseline, sample labels |

## What was run for the article

Haiku 4.5 on 80 alerts and Sonnet 5.5 on the first 40, each alert as a Claude Code subagent with
Bash as its only route to `aml.py`. Output tokens are partly estimated (see `cost.py`).
