"""Open/Short·log 설명 슬라이드용 그림 (합성 데이터만, seed 고정).

출력: charts/s1_shapes.png, charts/s2_runs.png, charts/s3_linlog.png, numbers.json
실행: python3 charts.py  (이 폴더 기준 경로)
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
OUT = HERE / "charts"
OUT.mkdir(exist_ok=True)

SEED = 20261120
NAVY = "#3D4C61"
ACCENT = "#B5523B"
GRAY = "#7F8C9F"
BAND = "#E1E6ED"
TXT = "#262626"

_have = {f.name for f in font_manager.fontManager.ttflist}
for name in ("Pretendard", "AppleGothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "NanumGothic"):
    if name in _have:
        plt.rcParams["font.family"] = name
        break
plt.rcParams.update({
    "axes.unicode_minus": False,
    "font.size": 9,
    "axes.edgecolor": "#8C8C8C",
    "axes.labelcolor": TXT,
    "xtick.color": "#595959",
    "ytick.color": "#595959",
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ------------------------------------------------------------ 지표 (다음 작업 열 이름과 같은 정의)
def _ranks(a):
    r = np.empty(len(a))
    r[np.argsort(a, kind="mergesort")] = np.arange(len(a))
    return r


def spearman(x, y):
    rx, ry = _ranks(np.asarray(x)), _ranks(np.asarray(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def skew(a):
    a = np.asarray(a, float)
    d = a - a.mean()
    s = d.std()
    return float((d ** 3).mean() / s ** 3) if s > 0 else 0.0


def ex_kurt(a):
    a = np.asarray(a, float)
    d = a - a.mean()
    s = d.std()
    return float((d ** 4).mean() / s ** 4 - 3) if s > 0 else 0.0


def bimodality(a):
    """Sarle 의 bimodality coefficient (표본 보정형). 0.555 초과면 두 덩어리 후보."""
    n = len(a)
    g, k = skew(a), ex_kurt(a)
    return float((g ** 2 + 1) / (k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))))


def metrics(x):
    ax = np.abs(np.asarray(x, float))
    lx = np.log10(ax)
    s_lin, s_log = skew(x), skew(lx)
    return {
        "decades": float(np.log10(ax.max() / ax.min())),
        "skew_lin": s_lin,
        "skew_log": s_log,
        "log_fit": abs(s_lin) - abs(s_log),
        "bimodality_log": bimodality(lx),
    }


def r3(d):
    return {k: round(v, 3) for k, v in d.items()}


rng = np.random.default_rng(SEED)
N_DIE = 60
numbers = {"seed": SEED, "n_die": N_DIE}


# ------------------------------------------------------------ 1. 분포 모양 5가지
def lognorm10(mu, sd, n):
    return 10 ** rng.normal(mu, sd, n)


shapes = [
    ("전부 Open", lognorm10(3.0, 0.04, N_DIE)),
    ("전부 Short", lognorm10(-1.0, 0.04, N_DIE)),
    ("Open 정도 차이", lognorm10(2.0, 0.7, N_DIE)),
    ("Short 정도 차이", lognorm10(-1.5, 0.6, N_DIE)),
    ("Open·Short 혼재", np.concatenate([lognorm10(3.0, 0.15, 34), lognorm10(-1.0, 0.15, 26)])),
]

fig, axes = plt.subplots(2, 5, figsize=(12.6, 4.3))
numbers["shapes"] = []
for j, (name, x) in enumerate(shapes):
    m = metrics(x)
    numbers["shapes"].append({"name": name, **r3(m)})
    a_lin, a_log = axes[0, j], axes[1, j]
    a_lin.hist(x, bins=18, color=NAVY, alpha=0.85)
    a_lin.set_title(name, fontsize=11, color=TXT, fontweight="bold")
    a_lin.ticklabel_format(axis="x", style="sci", scilimits=(-2, 3))
    lo, hi = np.log10(x.min()) - 0.1, np.log10(x.max()) + 0.1
    a_log.hist(x, bins=np.logspace(lo, hi, 18), color=ACCENT, alpha=0.85)
    a_log.set_xscale("log")
    a_lin.text(0.97, 0.95, f"skew_lin {m['skew_lin']:+.1f}", transform=a_lin.transAxes,
               ha="right", va="top", fontsize=8, color="#595959")
    a_log.text(0.97, 0.95,
               f"decades {m['decades']:.1f}\nskew_log {m['skew_log']:+.1f}\nBC {m['bimodality_log']:.2f}",
               transform=a_log.transAxes, ha="right", va="top", fontsize=8, color="#595959")
    for a in (a_lin, a_log):
        a.set_yticks([])
        a.spines["left"].set_visible(False)
axes[0, 0].set_ylabel("선형 축", fontsize=10)
axes[1, 0].set_ylabel("log 축", fontsize=10)
fig.supxlabel("die 값 (임의 단위, 합성 데이터 · die 60)", fontsize=9, color="#595959")
fig.tight_layout()
fig.savefig(OUT / "s1_shapes.png", dpi=200)
plt.close(fig)


# ------------------------------------------------------------ 2. 회차 흔들림 → 동등 어려움
RUN_SD = 0.20      # 회차 전체가 함께 움직이는 배수 (ln)
CONTACT_SD = 0.25  # die 마다 매번 달라지는 접촉 배수 (ln)
R = 0.05           # 선형 Δ = r·|중앙값|

n_show, n_run = 10, 4
base = lognorm10(2.0, 0.6, n_show)
run_f = np.exp(rng.normal(0, RUN_SD, n_run))
vals = base[:, None] * run_f[None, :] * np.exp(rng.normal(0, CONTACT_SD, (n_show, n_run)))

n_item = 400
shift_pct = np.empty(n_item)
for i in range(n_item):
    b = lognorm10(rng.uniform(-1, 3), rng.uniform(0.1, 0.8), N_DIE)
    r1 = b * np.exp(rng.normal(0, RUN_SD)) * np.exp(rng.normal(0, CONTACT_SD, N_DIE))
    r2 = b * np.exp(rng.normal(0, RUN_SD)) * np.exp(rng.normal(0, CONTACT_SD, N_DIE))
    m1, m2 = np.median(r1), np.median(r2)
    shift_pct[i] = (m2 - m1) / abs(m1) * 100
inside = float(np.mean(np.abs(shift_pct) <= R * 100))
fold = vals.max(axis=1) / vals.min(axis=1)
numbers["runs"] = {
    "run_sd_ln": RUN_SD, "contact_sd_ln": CONTACT_SD, "r": R, "n_item": n_item,
    "inside_delta_frac": round(inside, 3),
    "median_abs_shift_pct": round(float(np.median(np.abs(shift_pct))), 1),
    "same_die_fold_median": round(float(np.median(fold)), 2),
    "same_die_fold_max": round(float(fold.max()), 2),
}

fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.6, 3.9), gridspec_kw={"width_ratios": [1.15, 1]})
cols = [NAVY, GRAY, ACCENT, "#C9A227"]
for k in range(n_run):
    a1.scatter(np.arange(n_show) + (k - 1.5) * 0.12, vals[:, k], s=26, color=cols[k], label=f"{k + 1}회", zorder=3)
for d in range(n_show):
    a1.plot([d - 0.18, d + 0.18], [vals[d].min(), vals[d].max()], color="#BFBFBF", lw=4, zorder=1,
            solid_capstyle="round")
    a1.text(d, vals[d].max() * 1.35, f"×{fold[d]:.1f}", ha="center", fontsize=8, color="#595959")
a1.set_yscale("log")
a1.set_xticks(range(n_show), [f"die{d + 1}" for d in range(n_show)], fontsize=8)
a1.set_ylabel("die 값 (log 축)")
a1.set_title("같은 조건 · 같은 die 를 4회 측정: 값이 배수로 바뀜", fontsize=10.5, fontweight="bold", color=TXT)
a1.legend(ncol=4, fontsize=8, frameon=False, loc="lower right")
a1.set_ylim(vals.min() / 2, vals.max() * 3)

lim = max(60, np.percentile(np.abs(shift_pct), 99))
a2.axvspan(-R * 100, R * 100, color=BAND, zorder=0)
a2.axvline(-R * 100, color=NAVY, ls="--", lw=1)
a2.axvline(R * 100, color=NAVY, ls="--", lw=1)
a2.hist(np.clip(shift_pct, -lim, lim), bins=np.linspace(-lim, lim, 41), color=GRAY, zorder=2)
a2.text(R * 100 + 1.5, a2.get_ylim()[1] * 0.92, f"±Δ (r = {R * 100:.0f}%) 안: {inside * 100:.0f}%",
        fontsize=9, color=NAVY, fontweight="bold", va="top")
a2.set_xlabel("회차 간 ITEM 중앙값 차 (1회 중앙값 대비 %)")
a2.set_yticks([])
a2.spines["left"].set_visible(False)
a2.set_title(f"같은 조건 2회 반복 · 합성 ITEM {n_item}개", fontsize=10.5, fontweight="bold", color=TXT)
fig.tight_layout()
fig.savefig(OUT / "s2_runs.png", dpi=200)
plt.close(fig)


# ------------------------------------------------------------ 3. 선형 vs log (같은 합성 데이터)
n_run3 = 5
base3 = lognorm10(2.0, 0.8, N_DIE)
v3 = base3[:, None] * np.exp(rng.normal(0, CONTACT_SD, (N_DIE, n_run3)))
size_lin = np.median(v3, axis=1)
jit_lin = v3.std(axis=1, ddof=1)
lv3 = np.log10(v3)
size_log = np.median(lv3, axis=1)
jit_log = lv3.std(axis=1, ddof=1)
rho_lin = spearman(size_lin, jit_lin)
rho_log = spearman(size_log, jit_log)
m3 = metrics(size_lin)
numbers["linlog"] = {"n_run": n_run3, "spearman_size_jitter_lin": round(rho_lin, 2),
                     "spearman_size_jitter_log": round(rho_log, 2), **r3(m3)}

fig, ax = plt.subplots(2, 2, figsize=(10.0, 5.6))
ax[0, 0].scatter(size_lin, jit_lin, s=18, color=NAVY)
ax[0, 0].set_title(f"선형: 클수록 흔들림  (ρ = {rho_lin:+.2f})", fontsize=10.5, fontweight="bold", color=TXT)
ax[0, 0].set_xlabel("die 크기 (회차 중앙값)")
ax[0, 0].set_ylabel("회차 간 표준편차")
ax[0, 1].scatter(size_log, jit_log, s=18, color=ACCENT)
ax[0, 1].set_ylim(0, jit_log.max() * 2.2)
ax[0, 1].set_title(f"log: 흔들림이 고름  (ρ = {rho_log:+.2f})", fontsize=10.5, fontweight="bold", color=TXT)
ax[0, 1].set_xlabel("die 크기 (log10 중앙값)")
ax[0, 1].set_ylabel("회차 간 표준편차 (log10)")
ax[1, 0].hist(size_lin, bins=20, color=NAVY)
ax[1, 0].set_title(f"선형 분포: 한쪽 꼬리  (skew_lin {m3['skew_lin']:+.1f})", fontsize=10.5,
                   fontweight="bold", color=TXT)
ax[1, 1].hist(np.log10(size_lin), bins=20, color=ACCENT)
ax[1, 1].set_title(f"log 분포: 대칭에 가까움  (skew_log {m3['skew_log']:+.1f})", fontsize=10.5,
                   fontweight="bold", color=TXT)
ax[1, 1].set_xlabel("log10(die 값)")
ax[1, 0].set_xlabel("die 값")
for a in (ax[1, 0], ax[1, 1]):
    a.set_yticks([])
    a.spines["left"].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "s3_linlog.png", dpi=200)
plt.close(fig)

(HERE / "numbers.json").write_text(json.dumps(numbers, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(numbers, ensure_ascii=False, indent=1))
