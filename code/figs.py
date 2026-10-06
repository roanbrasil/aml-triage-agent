"""Figures of the article (white background).   python3 figs.py pt|en   (run from the aml/ folder)"""
import json
import sys

import graphviz
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, 'code')
from evaluate import load_proposals, wilson

LANG = sys.argv[1]; pt = LANG == 'pt'
LABELS = sys.argv[2] if len(sys.argv) > 2 else 'vault/labels.json'
BG = '#ffffff'; INK = '#20202e'; BLUE = '#3b5b92'; BLUEF = '#cddaeb'; GREEN = '#4a7c59'; GREENF = '#cbdccf'
RED = '#bf4f4a'; REDF = '#ecccc9'; AMBER = '#c98a2b'; AMBERF = '#eddcc0'; GREY = '#8d8d8d'
dec = (lambda v, d=2: f'{v:.{d}f}'.replace('.', ',')) if pt else (lambda v, d=2: f'{v:.{d}f}')
num = (lambda v: f'{v:,.0f}'.replace(',', '.')) if pt else (lambda v: f'{v:,.0f}')
usd = (lambda v, d=3: 'US$ ' + dec(v, d)) if pt else (lambda v, d=3: '$' + dec(v, d))

L = json.load(open(LABELS))
H = load_proposals('results/proposals_haiku.jsonl'); S = load_proposals('results/proposals_sonnet.jsonl')
B = json.load(open('results/baseline.json'))
CH = json.load(open('results/cost_haiku.json')); CS = json.load(open('results/cost_sonnet.json'))
score = lambda p: p['confidence'] if p['decision'] == 'escalate' else 1 - p['confidence']

# ---------------------------------------------------------------- fig 1: architecture
T = dict(
    q='Fila de alertas\n16.471 em 10 dias\n3,9% verdadeiros' if pt else 'Alert queue\n16,471 in 10 days\n3.9% true',
    ag='AGENTE\nlê, investiga, propõe' if pt else 'AGENT\nreads, investigates, proposes',
    gw='GATEWAY  ·  aml.py', steps=(['1  a tool existe no registry?', '2  está no bundle do agente?', '3  cabe no limite de 14 chamadas?',
                                      '4  os argumentos estão completos?', '5  executa e grava o evento']
                                     if pt else ['1  is the tool in the registry?', "2  is it in the agent's bundle?", '3  within the 14-call budget?',
                                                 '4  are the arguments complete?', '5  run it and write the event']),
    rd=('5 tools de leitura\nbanco sem a coluna de rótulo' if pt else '5 read tools\ndatabase without the label column'),
    pr=('propose_disposition\ngrava uma proposta' if pt else 'propose_disposition\nstores a proposal'),
    dn=('close_alert\nfile_report\nupdate_customer_risk\nNEGADO: exige humano' if pt else 'close_alert\nfile_report\nupdate_customer_risk\nDENIED: requires a human'),
    au=('audit.jsonl\num evento por chamada,\npermitida ou negada' if pt else 'audit.jsonl\none event per call,\nallowed or denied'),
    hu=('ANALISTA\ndecide: fecha ou escala' if pt else 'ANALYST\ndecides: close or escalate'),
    e1='alerta' if pt else 'alert', e2='toda chamada' if pt else 'every call', e3='proposta + justificativa' if pt else 'proposal + rationale',
    e4='trilha' if pt else 'trail', e5='só o humano' if pt else 'human only',
)
g = graphviz.Digraph(format='png')
g.attr(rankdir='LR', bgcolor=BG, nodesep='0.38', ranksep='0.75', fontname='Georgia', dpi='150', newrank='true')
g.attr('node', shape='box', style='rounded,filled', fontname='Georgia', fontsize='13', color=INK, penwidth='1.4', margin='0.2,0.13', fillcolor='#f1efe8')
g.attr('edge', color=INK, penwidth='1.4', fontname='Georgia', fontsize='11', arrowsize='0.8')
g.node('q', T['q']); g.node('ag', T['ag'], fillcolor=GREENF, color=GREEN)
rows = ''.join(f'<TR><TD ALIGN="LEFT" BGCOLOR="{BLUEF}" BORDER="1" COLOR="{BLUE}" CELLPADDING="7">{s}</TD></TR>' for s in T['steps'])
g.node('gw', f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="5"><TR><TD><B>{T["gw"]}</B></TD></TR>{rows}</TABLE>>', fillcolor=AMBERF, color=AMBER)
g.node('rd', T['rd']); g.node('pr', T['pr'], fillcolor=BLUEF, color=BLUE)
g.node('dn', T['dn'], fillcolor=REDF, color=RED); g.node('au', T['au'])
g.node('hu', T['hu'], fillcolor=GREENF, color=GREEN)
g.edge('q', 'ag', label=T['e1']); g.edge('ag', 'gw', label=T['e2'])
g.edge('gw', 'rd'); g.edge('gw', 'pr'); g.edge('gw', 'dn', style='dashed', color=RED, arrowhead='tee'); g.edge('gw', 'au', style='dashed')
g.edge('pr', 'hu', label=T['e3']); g.edge('au', 'hu', label=T['e4'], style='dashed')
g.edge('hu', 'dn', label=T['e5'], color=GREY, fontcolor=GREY, constraint='false')
g.render(f'images/fig1_{LANG}', cleanup=True)

mpl.rcParams.update({'figure.facecolor': BG, 'axes.facecolor': BG, 'savefig.facecolor': BG, 'font.family': 'serif', 'font.size': 13,
                     'axes.edgecolor': INK, 'axes.labelcolor': INK, 'text.color': INK, 'xtick.color': INK, 'ytick.color': INK,
                     'axes.grid': True, 'grid.color': '#dddddd', 'grid.linewidth': 0.8, 'axes.linewidth': 1.1})

# ---------------------------------------------------------------- fig 2: does the score separate the classes?
cases = sorted(H)
y = np.array([L[c]['label'] for c in cases])
panels = [(np.array([score(H[c]) for c in cases]), 0.502,
           'Agente (Haiku 4.5): confiança da proposta' if pt else 'Agent (Haiku 4.5): confidence of the proposal',
           'confiança se escalou, 1 − confiança se fechou' if pt else 'confidence if escalated, 1 − confidence if closed'),
          (np.array([B['scores'][c] for c in cases]), B['sample_auc'],
           'Gradient boosting: 19 agregados por conta' if pt else 'Gradient boosting: 19 per-account aggregates',
           'probabilidade prevista de lavagem' if pt else 'predicted probability of laundering')]
fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), layout='constrained', sharey=True)
rng = np.random.default_rng(3)
for ax, (s, a, title, xl) in zip(axes, panels):
    for lab, col in ((1, RED), (0, BLUE)):
        v = s[y == lab]
        ax.scatter(v, lab + rng.uniform(-0.24, 0.24, len(v)), s=58, color=col, alpha=0.72, edgecolor='white', linewidth=0.7, zorder=3)
        ax.plot([np.median(v)] * 2, [lab - 0.34, lab + 0.34], color=INK, lw=2.2, zorder=4)
    ax.set_title(f'{title}\nAUC {dec(a)}', loc='left', fontsize=13, pad=10)
    ax.set_xlim(-0.03, 1.03); ax.set_ylim(-0.6, 1.6); ax.grid(axis='y', visible=False)
    ax.set_xlabel(xl); ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: dec(v, 1)))
axes[0].set_yticks([0, 1], (['legítima\n(40 alertas)', 'lavagem\n(40 alertas)'] if pt else ['legitimate\n(40 alerts)', 'laundering\n(40 alerts)']))
fig.text(0.01, -0.07, ('Mesmos 80 alertas nos dois painéis. Traço preto: mediana. O modelo foi treinado nos outros 16.391 alertas.' if pt else
                       'Same 80 alerts in both panels. Black tick: median. The model was trained on the other 16,391 alerts.'), fontsize=10, color=GREY)
fig.savefig(f'images/fig2_{LANG}.png', dpi=150, bbox_inches='tight'); plt.close(fig)

# ---------------------------------------------------------------- fig 3: what one alert costs, by origin
fig, ax = plt.subplots(figsize=(11, 3.9), layout='constrained')
names = ['Haiku 4.5\n(80 alertas)' if pt else 'Haiku 4.5\n(80 alerts)', 'Sonnet 5.5\n(40 alertas)' if pt else 'Sonnet 5.5\n(40 alerts)']
segs = [('prefixo do harness (carga inicial + releituras)' if pt else 'harness prefix (first load + re-reads)', RED),
        ('contexto da investigação (resultados das tools)' if pt else 'investigation context (tool results)', BLUE),
        ('output (raciocínio, chamadas, justificativa)' if pt else 'output (reasoning, calls, rationale)', GREEN)]
vals = []
for C in (CH, CS):
    s = C['summary']; n = s['alerts']
    out = s['usd_by_meter']['out'] / n; har = s['mean_harness_usd']
    vals.append([har, s['mean'] - har - out, out])
left = np.zeros(2)
for k, (lab, col) in enumerate(segs):
    v = np.array([r[k] for r in vals])
    ax.barh(names, v, left=left, color=col, height=0.52, label=lab, zorder=3)
    for i in range(2):
        if v[i] > 0.011:
            ax.text(left[i] + v[i] / 2, i, dec(v[i], 3), ha='center', va='center', color='white', fontsize=12, zorder=4)
    left += v
for i in range(2):
    ax.text(left[i] + 0.003, i, f"{usd(left[i])} " + ('por alerta' if pt else 'per alert'), va='center', fontsize=12.5, fontweight='bold')
ax.invert_yaxis(); ax.grid(axis='y', visible=False); ax.set_xlim(0, 0.205); ax.set_xticks([0, 0.05, 0.10, 0.15, 0.20])
ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: usd(v, 2)))
ax.set_xlabel('custo médio por alerta (US$)' if pt else 'mean cost per alert (USD)')
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.24), ncol=1, frameon=False, fontsize=11.5)
fig.savefig(f'images/fig3_{LANG}.png', dpi=150, bbox_inches='tight'); plt.close(fig)

# ---------------------------------------------------------------- fig 4: alerts closed vs. true cases lost
PREV = 644 / 16471
fig, ax = plt.subplots(figsize=(9.6, 6.2), layout='constrained')
c = np.array(B['curve_cv'])
ax.plot([0, 100], [0, 100], color=GREY, ls='--', lw=1.4, label='fechar ao acaso' if pt else 'closing at random')
ax.plot(c[:, 0] * 100, c[:, 1] * 100, color=GREEN, lw=2.6,
        label=('gradient boosting (validação cruzada, 16.391 alertas)' if pt else 'gradient boosting (cross-validation, 16,391 alerts)'))
for P, name, col, n_alerts in ((H, 'Haiku 4.5', RED, 80), (S, 'Sonnet 5.5', AMBER, 40)):
    fn = sum(1 for k, p in P.items() if p['decision'] == 'close' and L[k]['label'] == 1); npos = sum(L[k]['label'] for k in P)
    tn = sum(1 for k, p in P.items() if p['decision'] == 'close' and L[k]['label'] == 0); nneg = len(P) - npos
    miss, spec = fn / npos, tn / nneg
    mlo, mhi = wilson(fn, npos); slo, shi = wilson(tn, nneg)
    closed = lambda m, s: 100 * (PREV * m + (1 - PREV) * s)
    x = closed(miss, spec)
    ax.errorbar([x], [miss * 100], xerr=[[x - closed(miss, slo)], [closed(miss, shi) - x]], yerr=[[(miss - mlo) * 100], [(mhi - miss) * 100]],
                fmt='o', color=col, ms=10, capsize=4, lw=1.6, zorder=5, label=f'{("agente" if pt else "agent")} {name} (n = {n_alerts}, ' + ('IC 95%' if pt else '95% CI') + ')')
ax.set_xlim(0, 60); ax.set_ylim(0, 30)
ax.set_xlabel('alertas fechados sem revisão humana (% da fila)' if pt else 'alerts closed without human review (% of the queue)')
ax.set_ylabel('casos verdadeiros perdidos (%)' if pt else 'true cases lost (%)')
ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(decimals=0)); ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(decimals=0))
ax.legend(loc='upper left', frameon=True, facecolor=BG, edgecolor='#dddddd', fontsize=11)
fig.text(0.01, -0.06, ('Pontos do agente: taxas da amostra balanceada reponderadas para a prevalência da fila (3,9%).\nAbaixo da diagonal é melhor.' if pt else
                       "Agent points: rates from the balanced sample reweighted to the queue's prevalence (3.9%).\nBelow the diagonal is better."), fontsize=10, color=GREY)
fig.savefig(f'images/fig4_{LANG}.png', dpi=150, bbox_inches='tight'); plt.close(fig)
print('ok', LANG)
