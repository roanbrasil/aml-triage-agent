"""Render the article tables as white-background PNGs (Medium has no tables).   python3 tables.py pt|en"""
import sys

from playwright.sync_api import sync_playwright

LANG = sys.argv[1]; pt = LANG == 'pt'
CSS = """body{margin:0;background:#fff;font-family:Georgia,serif;color:#20202e}
table{border-collapse:collapse;margin:28px;font-size:19px}
th{background:#20202e;color:#fff;text-align:left;padding:11px 16px;font-family:Arial,sans-serif;font-size:16px;white-space:nowrap}
td{padding:11px 16px;border-bottom:1px solid #dddddd;vertical-align:top}
td.n{text-align:right;white-space:nowrap} td.k{white-space:nowrap}
tr.tot td{font-weight:bold;border-top:2px solid #20202e;border-bottom:none}
tr.deny td{background:#f8ebe9}
code{font-family:Menlo,Consolas,monospace;font-size:16px;background:#f2f2f2;padding:1px 5px;border-radius:3px}
small{color:#8d8d8d;font-size:15px}"""

if pt:
    t1 = [["Regra", "Condição na janela de 10 dias", "Alertas", "Verdadeiros", "Precisão"],
          ["<code>FAN_IN</code>", "recebeu de 8 ou mais contas distintas", "4.111", "359", "8,7%"],
          ["<code>FAN_OUT</code>", "enviou para 12 ou mais contas distintas", "2.360", "86", "3,6%"],
          ["<code>PASS_THROUGH</code>", "entrada ≈ saída (diferença &lt; 10%), ambas ≥ 10.000, até 50 pagamentos", "2.378", "90", "3,8%"],
          ["<code>STRUCTURING</code>", "3 ou mais pagamentos entre 8.000 e 9.999,99", "8.247", "168", "2,0%"],
          ["Qualquer regra", "contas com pelo menos uma regra disparada", "16.471", "644", "3,9%"]]
    t2 = [["", "Agente Haiku 4.5", "Agente Sonnet 5.5", "Gradient boosting"],
          ["Alertas avaliados", "80 (40 + 40)", "40 (19 + 21)", "os mesmos 80"],
          ["Propôs escalar", "73 de 80 (91,3%)", "35 de 40 (87,5%)", "depende do corte"],
          ["Sensibilidade <small>IC 95%</small>", "92,5% <small>80,1–97,4</small>", "94,7% <small>75,4–99,1</small>", "depende do corte"],
          ["Especificidade <small>IC 95%</small>", "10,0% <small>4,0–23,1</small>", "19,0% <small>7,7–40,0</small>", "depende do corte"],
          ["AUC do score", "0,50 <small>0,38–0,63</small>", "0,49", "0,85 <small>0,76–0,93</small>"],
          ["Fechou caso verdadeiro", "3 dos 7 que fechou", "1 dos 5 que fechou", "0 nos 7 de menor score"],
          ["Chamadas ao modelo por alerta", "10,3", "5,1", "nenhuma"],
          ["Tempo por alerta", "40 s", "15 s", "milissegundos"],
          ["Custo por alerta", "US$ 0,093", "US$ 0,149", "desprezível"]]
    t3 = [["Tool", "Tipo", "No bundle do agente", "O que o gateway faz"],
          ["<code>get_alert</code>", "leitura", "sim", "devolve o alerta do caso, sem rótulo"],
          ["<code>get_account</code>", "leitura", "sim", "banco, tipo de entidade, quantas contas a entidade tem"],
          ["<code>account_profile</code>", "leitura", "sim", "totais por direção, moeda, formato e dia"],
          ["<code>list_transactions</code>", "leitura", "sim", "página de até 40 transações"],
          ["<code>counterparty_summary</code>", "leitura", "sim", "até 25 contrapartes, com o grau de cada uma"],
          ["<code>propose_disposition</code>", "escrita", "sim", "grava a proposta; exige decisão, confiança e justificativa"],
          ["<code>close_alert</code>", "escrita", "não", "nega: <code>deny:requires_human</code>"],
          ["<code>file_report</code>", "escrita", "não", "nega: <code>deny:requires_human</code>"],
          ["<code>update_customer_risk</code>", "escrita", "não", "nega: <code>deny:requires_human</code>"]]
else:
    t1 = [["Rule", "Condition over the 10-day window", "Alerts", "True", "Precision"],
          ["<code>FAN_IN</code>", "received from 8 or more distinct accounts", "4,111", "359", "8.7%"],
          ["<code>FAN_OUT</code>", "sent to 12 or more distinct accounts", "2,360", "86", "3.6%"],
          ["<code>PASS_THROUGH</code>", "money in ≈ money out (within 10%), both ≥ 10,000, at most 50 payments", "2,378", "90", "3.8%"],
          ["<code>STRUCTURING</code>", "3 or more payments between 8,000 and 9,999.99", "8,247", "168", "2.0%"],
          ["Any rule", "accounts with at least one rule fired", "16,471", "644", "3.9%"]]
    t2 = [["", "Agent, Haiku 4.5", "Agent, Sonnet 5.5", "Gradient boosting"],
          ["Alerts evaluated", "80 (40 + 40)", "40 (19 + 21)", "the same 80"],
          ["Proposed to escalate", "73 of 80 (91.3%)", "35 of 40 (87.5%)", "depends on the cutoff"],
          ["Sensitivity <small>95% CI</small>", "92.5% <small>80.1–97.4</small>", "94.7% <small>75.4–99.1</small>", "depends on the cutoff"],
          ["Specificity <small>95% CI</small>", "10.0% <small>4.0–23.1</small>", "19.0% <small>7.7–40.0</small>", "depends on the cutoff"],
          ["AUC of the score", "0.50 <small>0.38–0.63</small>", "0.49", "0.85 <small>0.76–0.93</small>"],
          ["Closed a true case", "3 of the 7 it closed", "1 of the 5 it closed", "0 in the 7 lowest scores"],
          ["Model calls per alert", "10.3", "5.1", "none"],
          ["Time per alert", "40 s", "15 s", "milliseconds"],
          ["Cost per alert", "$0.093", "$0.149", "negligible"]]
    t3 = [["Tool", "Type", "In the agent's bundle", "What the gateway does"],
          ["<code>get_alert</code>", "read", "yes", "returns the alert for the case, no label"],
          ["<code>get_account</code>", "read", "yes", "bank, entity type, how many accounts the entity holds"],
          ["<code>account_profile</code>", "read", "yes", "totals by direction, currency, format and day"],
          ["<code>list_transactions</code>", "read", "yes", "a page of at most 40 transactions"],
          ["<code>counterparty_summary</code>", "read", "yes", "up to 25 counterparties, each with its own degree"],
          ["<code>propose_disposition</code>", "write", "yes", "stores the proposal; requires decision, confidence and rationale"],
          ["<code>close_alert</code>", "write", "no", "denies: <code>deny:requires_human</code>"],
          ["<code>file_report</code>", "write", "no", "denies: <code>deny:requires_human</code>"],
          ["<code>update_customer_risk</code>", "write", "no", "denies: <code>deny:requires_human</code>"]]


def html(rows, numeric_from=None, total=False, deny_from=None):
    out = "<table><tr>" + "".join(f"<th>{h}</th>" for h in rows[0]) + "</tr>"
    for i, r in enumerate(rows[1:]):
        cls = "tot" if total and i == len(rows) - 2 else "deny" if deny_from is not None and i >= deny_from else ""
        out += f'<tr class="{cls}">' + "".join(
            f'<td class="n">{c}</td>' if numeric_from is not None and j >= numeric_from else f'<td class="k">{c}</td>'
            for j, c in enumerate(r)) + "</tr>"
    return (f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
            f"<div id='wrap' style='display:inline-block;background:#fff'>{out}</table></div></body></html>")


with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(device_scale_factor=2)
    for name, doc in (("tab1", html(t1, numeric_from=2, total=True)), ("tab2", html(t3, deny_from=6)), ("tab3", html(t2))):
        pg.set_content(doc); pg.locator("#wrap").screenshot(path=f"images/{name}_{LANG}.png")
    b.close()
print("ok", LANG)
