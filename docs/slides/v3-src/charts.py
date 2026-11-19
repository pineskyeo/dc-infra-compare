"""Charts + computed numbers for dc-equiv-criteria-v3 (real Fails only).
Input: /workspace/real_fail_11.tsv (header on line 1).
Outputs (this folder): charts/s1_forest.png, charts/s2_axis.png, charts/s2_row_<ID>.png, numbers.json
Rerun: python3 charts.py
"""
import json, pathlib
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

W = pathlib.Path(__file__).resolve().parent
OUT = W / 'charts'; OUT.mkdir(exist_ok=True)
names = {f.name for f in fm.fontManager.ttflist}
FONT = next((n for n in ['Pretendard', 'Noto Sans CJK KR', 'NanumGothic'] if n in names), 'DejaVu Sans')
plt.rcParams.update({'font.family': FONT, 'axes.unicode_minus': False, 'font.size': 9,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': '#808080', 'axes.labelcolor': '#404040',
                     'xtick.color': '#595959', 'ytick.color': '#595959'})
NAVY, LIGHT, GRAY, RED, BAND = '#3D4C61', '#9AA8BC', '#A6A6A6', '#B5523B', '#E1E6ED'

df = pd.read_csv('/workspace/real_fail_11.tsv', sep='\t')
# Group = reading of the 11 rows (checked against the descriptors computed below)
GROUP = {'F31_I3475': '차이', 'F65_I6106': '차이',
         'F54_I5492': '미결-정상', 'F54_I5493': '미결-정상', 'F61_I6003': '미결-정상', 'F59_I5574': '미결-정상',
         'F15_I1403': '미결-기준', 'F23_I2064': '미결-기준', 'F14_I1231': '미결-기준', 'F31_I3583': '미결-기준', 'F31_I3870': '미결-기준'}
ORDER = list(GROUP)
COL = {'차이': NAVY, '미결-정상': LIGHT, '미결-기준': '#C9A27A'}
df['group'] = df.ID.map(GROUP)
df = df.set_index('ID').loc[ORDER].reset_index()
pm = df.por_median.abs()
df['p1_pct'] = 100 * (df.POR1_mean - df.por_median) / pm
df['p2_pct'] = 100 * (df.POR2_mean - df.por_median) / pm
df['doe_pct'] = 100 * (df.DOE_mean - df.por_median) / pm
df['delta_pct'] = 100 * df.delta / pm
df['center_pct'] = 100 * df.center / pm
por_avg = (df.POR1_mean + df.POR2_mean) / 2
df['por_gap_pct'] = 100 * (df.POR1_mean - df.POR2_mean).abs() / por_avg.abs()
df['por1_over_por2'] = df.POR1_mean / df.POR2_mean
df['c_over_d'] = df.center / df.delta
df['lo_over_d'] = df.ci_low / df.delta
df['hi_over_d'] = df.ci_high / df.delta
df['half_over_d'] = (df.ci_high - df.ci_low) / 2 / df.delta
df['ci_outside'] = (df.ci_high < -df.delta) | (df.ci_low > df.delta)
df['ci_on_boundary'] = ~df.ci_outside & ((df.ci_low < -df.delta) | (df.ci_high > df.delta))
df['median_over_loq'] = pm / df.LoQ
means = df[['POR1_mean', 'POR2_mean', 'DOE_mean']]
df['median_below_all'] = df.por_median < means.min(axis=1)
df['median_above_all'] = df.por_median > means.max(axis=1)
df['median_gap_min_pct'] = np.where(df.median_below_all, 100 * (means.min(axis=1) - df.por_median) / pm,
                             np.where(df.median_above_all, 100 * (df.por_median - means.max(axis=1)) / pm, 0))
df['median_gap_max_pct'] = np.where(df.median_below_all, 100 * (means.max(axis=1) - df.por_median) / pm,
                             np.where(df.median_above_all, 100 * (df.por_median - means.min(axis=1)) / pm, 0))

N = {'n': len(df), 'verdict': df.verdict.value_counts().to_dict(), 'group': df.group.value_counts().to_dict(),
     'zone': df.zone.value_counts().to_dict(), 'n_die': sorted(df.n_die.unique().tolist()),
     'sigma_run_zero': int((df.sigma_run == 0).sum()), 'run_margin_zero': int((df.run_margin == 0).sum()),
     'delta_pct_min': float(df.delta_pct.min()), 'delta_pct_max': float(df.delta_pct.max()), 'font': FONT,
     'items': json.loads(df.drop(columns=['reason']).to_json(orient='records', force_ascii=False))}
(W / 'numbers.json').write_text(json.dumps(N, ensure_ascii=False, indent=1))

# ---------- slide 1: center/Δ with 90% CI for the 11 (forest)
fig, ax = plt.subplots(figsize=(4.85, 2.75), dpi=300)
y = np.arange(len(df))[::-1]
ax.axvspan(-1, 1, color=BAND, zorder=0)
for v in (-1, 1): ax.axvline(v, color=RED, lw=1, ls='--', zorder=1)
for yy, (_, r) in zip(y, df.iterrows()):
    c = COL[r.group]
    ax.plot([r.lo_over_d, r.hi_over_d], [yy, yy], color=c, lw=2.2, solid_capstyle='butt', zorder=2)
    ax.plot(r.c_over_d, yy, 'o', color=c, ms=5, mec='white', mew=0.6, zorder=3)
ax.set_yticks(y, df.ID, fontsize=9)
for t, g in zip(ax.get_yticklabels(), df.group):
    t.set_color(NAVY if g == '차이' else '#595959'); t.set_fontweight('bold' if g == '차이' else 'normal')
ax.set_xlim(-2.6, 2.6); ax.set_xticks([-2, -1, 0, 1, 2], ['−2Δ', '−Δ', '0', '+Δ', '+2Δ'], fontsize=9)
ax.set_xlabel('차이 중앙값과 90% 신뢰구간 (Δ 단위)', fontsize=9)
from matplotlib.lines import Line2D
h = [Line2D([], [], color=COL[k], lw=3, label=l) for k, l in [('차이', '차이'), ('미결-정상', '미결 · 경계'), ('미결-기준', '미결 · 기준 흔들림')]]
from matplotlib.patches import Patch
h.append(Patch(color=BAND, label='동등 범위 ±Δ'))
ax.legend(handles=h, fontsize=9, frameon=False, loc='lower center', bbox_to_anchor=(0.45, 0.99), ncol=4, handlelength=1.0, columnspacing=0.9, borderaxespad=0)
ax.set_ylim(-0.6, len(df) - 0.1)
fig.savefig(OUT / 's1_forest.png', bbox_inches='tight', pad_inches=0.03); plt.close(fig)

# ---------- slide 2: per-ITEM mini strip (POR1, POR2, DOE % vs por_median, ±Δ band)
XL = 25
def mini(ax, r):
    ax.axvspan(-r.delta_pct, r.delta_pct, color=BAND, zorder=0)
    ax.axvline(0, color='#BFBFBF', lw=0.6, zorder=1)
    for v, mk, c in [(r.p1_pct, 'o', '#7F8C9F'), (r.p2_pct, 's', '#7F8C9F'), (r.doe_pct, 'D', RED)]:
        if abs(v) <= XL:
            ax.plot(v, 0, mk, color=c, ms=6.5 if mk != 'D' else 6, mec='white', mew=0.6, zorder=3)
        else:
            ax.plot(np.sign(v) * (XL - 0.6), 0, '>' if v > 0 else '<', color=c, ms=6.5, zorder=3)
    big = [v for v in (r.p1_pct, r.p2_pct, r.doe_pct) if abs(v) > XL]
    if big:
        ax.text(XL - 2.2, 0.0, ' · '.join(f'+{v:.0f}%' for v in big) + ' →', ha='right', va='center', fontsize=9, color='#595959')
    ax.set_xlim(-XL, XL); ax.set_ylim(-1, 1); ax.axis('off')

for _, r in df.iterrows():
    fig, ax = plt.subplots(figsize=(3.7, 0.3), dpi=300); fig.subplots_adjust(0, 0, 1, 1)
    mini(ax, r); fig.savefig(OUT / f's2_row_{r.ID}.png'); plt.close(fig)

fig, ax = plt.subplots(figsize=(3.7, 0.3), dpi=300); fig.subplots_adjust(0, 0.98, 1, 1)
ax.set_xlim(-XL, XL); ax.set_xticks([-20, -10, -5, 0, 5, 10, 20], ['−20%', '−10', '−5', '0', '+5', '+10', '+20%'], fontsize=9)
ax.tick_params(axis='x', length=2, pad=1); ax.set_yticks([]); [ax.spines[k].set_visible(False) for k in ('left', 'right', 'top')]
fig.savefig(OUT / 's2_axis.png', bbox_inches='tight', pad_inches=0.01); plt.close(fig)

cols = ['ID', 'group', 'p1_pct', 'p2_pct', 'doe_pct', 'delta_pct', 'center_pct', 'por_gap_pct', 'por1_over_por2', 'c_over_d', 'lo_over_d', 'hi_over_d', 'half_over_d', 'ci_outside', 'ci_on_boundary', 'median_over_loq', 'median_below_all', 'median_above_all', 'median_gap_min_pct', 'median_gap_max_pct']
print(df[cols].round(3).to_string()); print({k: v for k, v in N.items() if k != 'items'})
