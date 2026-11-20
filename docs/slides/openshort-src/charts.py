"""Open/Short·log 설명 슬라이드 5장용 그림과 수치 (합성 데이터만, seed 고정).

흐름: 물리 커브 → 곱셈형 산포 → 두 축 → 판정 변화 → 언제 log.
판정·지표는 저장소의 por_doe_compare.py 실제 함수(judge, log_columns, item_status, shape_cols)로 계산한다.

출력: charts/s1_verdict.png, s2_curve.png, s3_hist.png, s3_jitter.png, s4_ratio.png, numbers.json
실행: python3 charts.py
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from scipy import stats

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
import por_doe_compare as pdc  # noqa: E402

OUT = HERE / "charts"
OUT.mkdir(exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()

NAVY = "#3D4C61"
ACCENT = "#B5523B"
GRAY = "#7F8C9F"
BAND = "#E1E6ED"
BAND2 = "#F3DDD7"
TXT = "#262626"
CASE_COLORS = ["#3D4C61", "#7F8C9F", "#B5523B", "#C9A227", "#5B8C6A"]

_have = {f.name for f in font_manager.fontManager.ttflist}
for name in ("Pretendard", "AppleGothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "NanumGothic"):
    if name in _have:
        plt.rcParams["font.family"] = name
        break
plt.rcParams.update({
    "axes.unicode_minus": False, "font.size": 9,
    "axes.edgecolor": "#8C8C8C", "axes.labelcolor": TXT,
    "xtick.color": "#595959", "ytick.color": "#595959",
    "axes.spines.top": False, "axes.spines.right": False,
})

# ------------------------------------------------------------ 합성 설정 (값은 모두 여기서만 정함)
SEED = 20261120
N_DIE = 60
J = 3                    # POR 회차 수
R = 0.05                 # 정책 허용폭 r (por_doe_compare 기본값)

# 측정 커브 (추정): log10 y(m) = LOG_SHORT + (LOG_OPEN − LOG_SHORT) / (1 + exp(K·m))
#   m = 공정 마진. m 이 작으면 Open 평탄부(높은 값), 크면 Short 평탄부(낮은 값), 사이는 지수 기울기부
LOG_OPEN, LOG_SHORT, K = 12.0, 1.0, 0.6
MEAS_SD_DEX = 0.002      # 장비 측정 잡음 (log10, ≈0.5%)
DIE_E_SD = 0.001         # die·회차마다 마진 흔들림 (m 단위)
RUN_U = (0.0, 0.0, 0.0)  # POR 회차 공통 마진 이동 (m 단위)
U_DOE = 0.010            # DOE 가 모든 die 의 마진을 옮기는 양 (m 단위) → 기울기부에서 같은 비율 이동

CASES = [  # (key, 이름, 마진 중심, 마진 산포)
    ("open_all", "전부 Open", -9.0, 0.3),
    ("open_deg", "Open 정도 차이", -1.2, 1.5),
    ("short_deg", "Short 정도 차이", 1.2, 1.5),
    ("short_all", "전부 Short", 9.0, 0.3),
    ("mixed", "Open·Short 혼재", None, None),
]
MIX_M, MIX_SD = 9.0, 0.3         # 혼재: 두 평탄부 마진 위치 ±MIX_M
OPEN_SHARE_POR = 0.55            # 혼재: POR 에서 Open die 비율
MIX_FLIP = 0.15                  # 혼재: DOE 에서 Open → Short 로 바뀌는 Open die 비율
S1_CASE = "open_deg"             # 1장에 쓰는 ITEM

# 2장 개념 그림 (추정): R = R0·exp(−k·m), I = I0·exp(k·m)
K_EXP, SIG_M, M_LO, M_HI = 1.5, 0.15, -1.0, 1.0

rng = np.random.default_rng(SEED)


def logy(m):
    return LOG_SHORT + (LOG_OPEN - LOG_SHORT) / (1 + np.exp(K * np.asarray(m, float)))


def meas(m):
    m = np.asarray(m, float)
    return 10 ** (logy(m) + rng.normal(0, MEAS_SD_DEX, m.shape))


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return None if not np.isfinite(v) else float(f"{v:.6g}")
    return v


# ------------------------------------------------------------ 데이터 생성
def make_case(key, mu, sd):
    run_u = np.asarray(RUN_U)[None, :]
    if key == "mixed":
        is_open = rng.random(N_DIE) < OPEN_SHARE_POR
        m = np.where(is_open, -MIX_M, MIX_M) + rng.normal(0, MIX_SD, N_DIE)
        open_idx = np.flatnonzero(is_open)
        flip = rng.choice(open_idx, int(round(MIX_FLIP * open_idx.size)), replace=False)
        m_doe = m.copy()
        m_doe[flip] = MIX_M + rng.normal(0, MIX_SD, flip.size)
        extra = {"open_share_por": float(is_open.mean()),
                 "open_share_doe": float((m_doe < 0).mean()), "n_flip": int(flip.size)}
    else:
        m = rng.normal(mu, sd, N_DIE)
        m_doe = m
        extra = {}
    Y = meas(m[:, None] + run_u + rng.normal(0, DIE_E_SD, (N_DIE, J)))
    z = meas(m_doe + U_DOE + rng.normal(0, DIE_E_SD, N_DIE))
    return m, Y, z, extra


def judge_case(Y, z):
    res, _ = pdc.judge(Y, z, R)
    lc = pdc.log_columns(Y, z, R, res)
    st = pdc.item_status(Y, z, res["delta"])
    Rm = Y.mean(axis=1)
    lin_range = Y.max(axis=1) - Y.min(axis=1)
    rho_lin = float(stats.spearmanr(np.abs(Rm), lin_range)[0])     # 참고 계산 (코드 열 아님)
    return res, lc, st, rho_lin


def recommend(st):
    s = st["status"].split(";")
    if pdc.ST_BIMODAL in s:
        return "따로 봄 (Open/Short 비율)"
    if pdc.ST_LOG_CANDIDATE in s:
        return "log 판정 참고"
    return "선형 그대로"


numbers = {"seed": SEED, "n_die": N_DIE, "n_run": J, "r": R,
           "params": {"log_open": LOG_OPEN, "log_short": LOG_SHORT, "k_curve": K, "meas_sd_dex": MEAS_SD_DEX,
                      "die_e_sd": DIE_E_SD, "run_u": list(RUN_U), "u_doe": U_DOE,
                      "mix_m": MIX_M, "open_share_por_set": OPEN_SHARE_POR, "mix_flip": MIX_FLIP},
           "thresholds": {"log_decades_min": pdc.LOG_DECADES_MIN, "log_fit_min": pdc.LOG_FIT_MIN, "bimodal_bc_min": pdc.BIMODAL_BC_MIN,
                          "bimodal_min_die": pdc.BIMODAL_MIN_DIE, "size_jitter_rho": pdc.SIZE_JITTER_RHO,
                          "size_jitter_rho_pos": pdc.SIZE_JITTER_RHO_POS,
                          "size_jitter_min_die": pdc.SIZE_JITTER_MIN_DIE, "policy_margin_log": float(np.log10(1 + R))},
           "s1_case": S1_CASE, "cases": []}

data = {}
for key, name, mu, sd in CASES:
    m, Y, z, extra = make_case(key, mu, sd)
    res, lc, st, rho_lin = judge_case(Y, z)
    data[key] = (name, m, Y, z, res, lc, st)
    numbers["cases"].append({
        "key": key, "name": name, "margin_mu": mu, "margin_sd": sd,
        "verdict": res["verdict"], "reason": res["reason"], "zone": res.get("zone", ""),
        "center": res["center"], "ci_low": res["ci_low"], "ci_high": res["ci_high"], "delta": res["delta"],
        "por_median": res["por_median"], "ci_half_over_delta": lc["ci_half_over_delta"],
        "verdict_log": lc["verdict_log"], "log_reason": lc["log_reason"],
        "center_log": lc["center_log"], "ci_low_log": lc["ci_low_log"], "ci_high_log": lc["ci_high_log"],
        "delta_log": lc["delta_log"], "ci_half_over_delta_log": lc["ci_half_over_delta_log"],
        "status": st["status"], **{c: st[c] for c in pdc.SHAPE_COLS},
        "spearman_size_jitter": st["spearman_size_jitter"], "run_jitter_pct": st["run_jitter_pct"],
        "rho_lin_range": rho_lin, "reco": recommend(st), **extra,
    })

# DOE 실제 이동(참값): 기울기부 die 의 z/POR 비 중앙값 (잡음 없는 커브로)
m_s1 = data[S1_CASE][1]
numbers["s1_true_shift_pct"] = float(100 * (np.median(10 ** (logy(m_s1 + U_DOE) - logy(m_s1))) - 1))
C = {c["key"]: c for c in numbers["cases"]}

# ------------------------------------------------------------ 1장: 결론 막대
s1 = C[S1_CASE]
fig, ax = plt.subplots(figsize=(5.6, 4.2))
vals = [s1["ci_half_over_delta"], s1["ci_half_over_delta_log"]]
bars = ax.bar([0, 1], vals, width=0.55, color=[NAVY, ACCENT])
ax.axhline(1.0, color=TXT, ls="--", lw=1)
ax.set_xticks([0, 1], [f"선형 축\n{s1['verdict']}", f"log 축\n{s1['verdict_log']}"], fontsize=11)
ax.set_ylabel("CI 반폭 / Δ  (1 이상이면 동등 불가)")
top = max(vals) * 1.25
ax.set_ylim(0, max(top, 1.3))
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + max(top, 1.3) * 0.02, f"{v:.2f}", ha="center", va="bottom",
            fontsize=11, fontweight="bold", color=TXT)
ax.set_title(f"같은 ITEM ({s1['name']}) · 판정 코드 그대로", fontsize=11, fontweight="bold", color=TXT)
fig.tight_layout()
fig.savefig(OUT / "s1_verdict.png", dpi=200)
plt.close(fig)

# ------------------------------------------------------------ 2장: 왜 곡선인가 (추정)
mm = np.linspace(-2, 2, 200)
Rc, Ic = np.exp(-K_EXP * mm), np.exp(K_EXP * mm)
s2 = {"k_exp": K_EXP, "sigma_m": SIG_M, "m_lo": M_LO, "m_hi": M_HI}
for tag, m0 in (("lo", M_LO), ("hi", M_HI)):
    y0 = float(np.exp(-K_EXP * m0))
    w = float(np.exp(-K_EXP * (m0 - SIG_M)) - np.exp(-K_EXP * (m0 + SIG_M)))
    s2.update({f"r_{tag}": y0, f"width_{tag}": w, f"relwidth_{tag}": w / y0})
s2["width_ratio"] = s2["width_lo"] / s2["width_hi"]
s2["value_ratio"] = s2["r_lo"] / s2["r_hi"]
s2["log_width_dex"] = float(2 * K_EXP * SIG_M / np.log(10))
numbers["s2"] = s2

fig, axs = plt.subplots(1, 3, figsize=(12.6, 3.9), gridspec_kw={"width_ratios": [1, 1, 1.35]})
for a, logscale in ((axs[0], False), (axs[1], True)):
    a.plot(mm, Rc, color=NAVY, lw=2, label="컨택 저항 R = R0·exp(−k·m)")
    a.plot(mm, Ic, color=ACCENT, lw=2, ls="--", label="누설 I = I0·exp(k·m)")
    for m0, col in ((M_LO, BAND), (M_HI, BAND2)):
        a.axvspan(m0 - SIG_M, m0 + SIG_M, color=col, zorder=0)
        a.axhspan(np.exp(-K_EXP * (m0 + SIG_M)), np.exp(-K_EXP * (m0 - SIG_M)), color=col, zorder=0)
    a.set_xlabel("공정 마진 m")
    if logscale:
        a.set_yscale("log")
        a.set_title("같은 그림, log y축: 띠 높이 같음", fontsize=10.5, fontweight="bold", color=TXT)
    else:
        a.set_ylim(0, Rc.max() * 1.02)
        a.set_title("선형 y축: 같은 ±σ 마진 → y 폭 다름", fontsize=10.5, fontweight="bold", color=TXT)
axs[0].set_ylabel("측정값 (R0 = I0 = 1)")
h, l = axs[0].get_legend_handles_labels()

mc = np.linspace(-11.5, 11.5, 400)
a = axs[2]
a.plot(mc, 10 ** logy(mc), color=TXT, lw=2)
a.set_yscale("log")
a.set_xlabel("공정 마진 m")
a.set_ylabel("Open/Short 측정값 (log 축)")
a.set_title("Open/Short 측정 커브 (추정) · 5 케이스 위치", fontsize=10.5, fontweight="bold", color=TXT)
for i, (key, name, mu, sd) in enumerate(CASES):
    col = CASE_COLORS[i]
    if key == "mixed":
        pts = [-MIX_M, MIX_M]
        a.scatter(pts, 10 ** logy(pts), s=140, facecolors="none", edgecolors=col, lw=2.2, zorder=4, label=name)
    else:
        a.errorbar([mu], [10 ** logy(mu)], xerr=[[sd], [sd]], fmt="o", ms=8, color=col, capsize=4, lw=1.8,
                   zorder=5, label=name)
h2, l2 = a.get_legend_handles_labels()
fig.legend(h + h2, l + l2, loc="lower center", ncol=7, frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, 0.0))
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.savefig(OUT / "s2_curve.png", dpi=200)
plt.close(fig)

# ------------------------------------------------------------ 3장: 같은 데이터, 두 축
fig, axes = plt.subplots(2, 5, figsize=(12.0, 5.0))
for j, (key, name, _, _) in enumerate(CASES):
    x = data[key][2].mean(axis=1)
    a_lin, a_log = axes[0, j], axes[1, j]
    a_lin.hist(x, bins=18, color=NAVY, alpha=0.9)
    a_lin.set_title(name, fontsize=11, color=TXT, fontweight="bold")
    a_lin.ticklabel_format(axis="x", style="sci", scilimits=(-2, 3))
    a_log.hist(np.log10(x), bins=18, color=ACCENT, alpha=0.9)
    for a in (a_lin, a_log):
        a.set_yticks([])
        a.spines["left"].set_visible(False)
        a.tick_params(axis="x", labelsize=7.5)
axes[0, 0].set_ylabel("선형 축\n(die 값)", fontsize=10)
axes[1, 0].set_ylabel("log 축\n(log10 die 값)", fontsize=10)
fig.tight_layout()
fig.savefig(OUT / "s3_hist.png", dpi=200)
plt.close(fig)

Yj = data[S1_CASE][2]
mean_j = np.abs(Yj.mean(axis=1))
fig, (b1, b2) = plt.subplots(2, 1, figsize=(4.2, 5.3))
b1.scatter(mean_j, Yj.max(axis=1) - Yj.min(axis=1), s=14, color=NAVY)
b1.set_xlabel("die 값 (회차 평균)")
b1.set_ylabel("회차 범위 (선형)")
b1.set_title(f"선형: 클수록 크게 흔들림  ρ {C[S1_CASE]['rho_lin_range']:+.2f}", fontsize=10,
             fontweight="bold", color=TXT)
b1.ticklabel_format(style="sci", scilimits=(-2, 3))
lgj = np.log10(np.abs(Yj))
rng_log = lgj.max(axis=1) - lgj.min(axis=1)
b2.scatter(np.log10(mean_j), rng_log, s=14, color=ACCENT)
b2.set_ylim(0, rng_log.max() * 2.5)
b2.set_xlabel("log10 die 값 (회차 평균)")
b2.set_ylabel("회차 범위 (log10)")
b2.set_title(f"log: 평평 (상대 흔들림 일정)  ρ {C[S1_CASE]['spearman_size_jitter']:+.2f}", fontsize=10,
             fontweight="bold", color=TXT)
fig.tight_layout()
fig.savefig(OUT / "s3_jitter.png", dpi=200)
plt.close(fig)

# ------------------------------------------------------------ 4장: 케이스별 CI 반폭/Δ
fig, ax = plt.subplots(figsize=(7.0, 4.3))
xs = np.arange(len(CASES))
lin_v = [C[k]["ci_half_over_delta"] for k, *_ in CASES]
log_v = [C[k]["ci_half_over_delta_log"] for k, *_ in CASES]
FLOOR = 1e-3   # 이보다 작은 값 (혼재의 선형처럼 사실상 0) 은 바닥 막대 + '≈0'
ax.set_yscale("log")
pos = [v for v in lin_v + log_v if v is not None and v > 0]
ytop = max(pos + [1.0]) * 3
ax.set_ylim(FLOOR / 1.5, ytop)
for dx, vs, col, lab in ((-0.19, lin_v, NAVY, "선형 축"), (0.19, log_v, ACCENT, "log 축")):
    hs = [max(v, FLOOR) if v is not None else FLOOR for v in vs]
    ax.bar(xs + dx, hs, width=0.36, color=col, label=lab)
    for x0, v in zip(xs + dx, vs):
        if v is None or v < FLOOR:
            ax.text(x0, FLOOR * 1.15, "≈0", ha="center", va="bottom", fontsize=8, color=TXT)
ax.axhline(1.0, color=TXT, ls="--", lw=1)
ax.set_xticks(xs, [n.replace(" ", "\n", 1) for _, n, *_ in CASES], fontsize=9)
ax.set_ylabel("CI 반폭 / Δ  (log 축, 점선 = 1)")
ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)
fig.tight_layout()
fig.savefig(OUT / "s4_ratio.png", dpi=200)
plt.close(fig)

numbers = clean(numbers)
(HERE / "numbers.json").write_text(json.dumps(numbers, ensure_ascii=False, indent=1), encoding="utf-8")
for c in numbers["cases"]:
    print(f"{c['name']:<14} lin {c['verdict']:<4} {c['ci_half_over_delta']}  log {c['verdict_log']:<4} "
          f"{c['ci_half_over_delta_log']}  status {c['status']}  dec {c['decades']}  rho_log {c['spearman_size_jitter']}")
