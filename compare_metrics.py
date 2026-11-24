"""compare.csv(기존 vs 개선) 지표 계산과 지표별 그림 한 장씩.

compare_before_after.py 와 group_summary.py 가 같이 쓴다.
numpy / pandas / matplotlib 만 쓴다 (scipy 없이 import 되어야 함).

지표 이름 (METRICS, draw_all 이 <out_dir>/<이름>.png 로 저장):
  sigma_die_ratio, sigma_run_ratio, meas_precision_ratio   r = 개선/기존, 1보다 작으면 개선
  stability_sigma_die_pct, stability_meas_precision_pct    기존·개선 각각의 분포 (낮을수록 안정)
  verdict_center_delta                                     center/Δ 분포 (열이 없으면 건너뜀)
"""
from dataclasses import dataclass
from functools import partial
from pathlib import Path
import re

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

SIDES = ("before", "after")
SIDE = {"before": "기존", "after": "개선"}
C_BEFORE, C_AFTER = "#8c8c8c", "#2f6db5"

# change_status(compare_before_after.py)는 a < b / a > b / 그 외 '같음' 으로 정확히 비교한다
# (상대 허용오차 없음). 그래서 r = a/b 에서도 '같음'은 r == 1 뿐이다.
SAME_TOL = 0.0

METRIC_RATIO = {
    "sigma_die_ratio": ("sigma_die_before", "sigma_die_after"),
    "sigma_run_ratio": ("sigma_run_before", "sigma_run_after"),
    "meas_precision_ratio": ("meas_precision_pct_before", "meas_precision_pct_after"),
}
METRIC_STABILITY = {
    "stability_sigma_die_pct": "sigma_die_pct",
    "stability_meas_precision_pct": "meas_precision_pct",
}
LABEL = {
    "sigma_die_ratio": "σ_die",
    "sigma_run_ratio": "σ_run",
    "meas_precision_ratio": "측정정밀도%",
    "stability_sigma_die_pct": "σ_die %",
    "stability_meas_precision_pct": "측정정밀도 %",
    "verdict_center_delta": "center/Δ",
}


# ---------------------------------------------------------------- 글꼴·축

def set_font():
    """group_summary.set_font 과 같은 규칙: 한글 글꼴이 있으면 쓴다."""
    names = {f.name for f in fm.fontManager.ttflist}
    for n in ("Apple SD Gothic Neo", "AppleGothic", "Malgun Gothic", "Pretendard",
              "Noto Sans CJK KR", "NanumGothic"):
        if n in names:
            plt.rcParams["font.family"] = n
            break
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 10


_PLAIN = FuncFormatter(lambda v, _: f"{v:g}")


def _plain_log_axis(axis, subs=(1.0, 2.0, 5.0)):
    """로그 축 눈금을 일반 숫자 글자로 (mathtext 마이너스가 그려지지 않게).
    subs=(1.0,) 이면 10의 거듭제곱 주 눈금만 찍는다 (범위가 넓을 때)."""
    axis.set_major_locator(LogLocator(base=10, subs=subs))
    axis.set_major_formatter(_PLAIN)
    axis.set_minor_formatter(NullFormatter())
    axis.set_tick_params(which="major", labelbottom=True, labelleft=True)


# ---------------------------------------------------------------- 계산

def _num(df, col):
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype=float)


def with_pct(df):
    """sigma_die_pct_*, sigma_run_pct_*, meas_precision_pct_* 를 채운 복사본.
    열이 있으면 그 값, 없으면 por_median 기준으로 계산 (group_summary 와 같은 규칙)."""
    out = df.copy()
    for side in SIDES:
        med = _num(out, f"por_median_{side}").abs().replace(0, np.nan)
        for k in ("die", "run"):
            col = f"sigma_{k}_pct_{side}"
            out[col] = _num(out, col) if col in out.columns else 100 * _num(out, f"sigma_{k}_{side}") / med
        col = f"meas_precision_pct_{side}"
        if col in out.columns:
            out[col] = _num(out, col)
        else:
            s_meas = np.hypot(_num(out, f"sigma_die_{side}"), _num(out, f"sigma_run_{side}"))
            out[col] = 100 * s_meas / med
    return out


def stability_row(d):
    """group_summary 의 stab() 과 같은 키·반올림. d 는 with_pct 를 거친 표."""
    r = {"ITEM 수": len(d)}
    for side in SIDES:
        dd = d[f"sigma_die_pct_{side}"].dropna()
        rr = d[f"sigma_run_pct_{side}"].dropna()
        r[f"{SIDE[side]} σ_die% 중앙값"] = round(float(dd.median()), 3) if len(dd) else np.nan
        r[f"{SIDE[side]} σ_die% 25%"] = round(float(dd.quantile(0.25)), 3) if len(dd) else np.nan
        r[f"{SIDE[side]} σ_die% 75%"] = round(float(dd.quantile(0.75)), 3) if len(dd) else np.nan
        r[f"{SIDE[side]} σ_run% 중앙값"] = round(float(rr.median()), 3) if len(rr) else np.nan
        r[f"{SIDE[side]} σ_run=0 %"] = round(100 * float((d[f"sigma_run_{side}"] == 0).mean()), 1) if len(d) else np.nan
    for side in SIDES:
        mp = d[f"meas_precision_pct_{side}"].dropna()
        r[f"{SIDE[side]} 측정정밀도% 중앙값"] = round(float(mp.median()), 3) if len(mp) else np.nan
        r[f"{SIDE[side]} 측정정밀도% 25%"] = round(float(mp.quantile(0.25)), 3) if len(mp) else np.nan
        r[f"{SIDE[side]} 측정정밀도% 75%"] = round(float(mp.quantile(0.75)), 3) if len(mp) else np.nan
    return r


def _before_after(df, metric):
    d = with_pct(df) if metric == "meas_precision_ratio" else df
    b_col, a_col = METRIC_RATIO[metric]
    return _num(d, b_col), _num(d, a_col)


def ratio(df, metric):
    """r = 개선/기존. 어느 쪽이든 0·음수·NaN 이면 NaN (제외).
    sigma_run_ratio 는 둘 다 0 인 행을 r.attrs['both_zero'] 로 따로 센다."""
    b, a = _before_after(df, metric)
    ok = (b > 0) & (a > 0)
    r = (a / b).where(ok)
    r.name = metric
    r.attrs["both_zero"] = int(((b == 0) & (a == 0)).sum()) if metric == "sigma_run_ratio" else 0
    return r


def ratio_counts(r):
    """개선(r<1)·악화(r>1)·같음(|r-1|≤SAME_TOL)·제외(NaN) 수와 중앙 r.
    r.attrs['both_zero'] 가 있으면 제외에서 빼고 'both_zero' 로 따로 준다."""
    v = r.dropna()
    same = (v - 1).abs() <= SAME_TOL
    both_zero = int(r.attrs.get("both_zero", 0))
    return {
        "improved": int(((v < 1) & ~same).sum()),
        "worse": int(((v > 1) & ~same).sum()),
        "same": int(same.sum()),
        "excluded": int(r.isna().sum()) - both_zero,
        "both_zero": both_zero,
        "median": float(v.median()) if len(v) else np.nan,
    }


def worst_items(df, metric, top=10):
    """악화(r>1) 항목을 r 큰 순으로 top 개. 열: ID, before, after, ratio."""
    b, a = _before_after(df, metric)
    r = ratio(df, metric)
    ids = df["ID"] if "ID" in df.columns else pd.Series(df.index, index=df.index)
    t = pd.DataFrame({"ID": ids, "before": b, "after": a, "ratio": r})
    t = t[t["ratio"] > 1].sort_values("ratio", ascending=False, kind="mergesort")
    return t.head(top).reset_index(drop=True)


# ---------------------------------------------------------------- 좋아졌나 (요약 지표)

BETTER, SAME, WORSE = "좋아짐", "비슷", "나빠짐"
TREND_BAND = 0.10      # 비 중앙값이 1 ± 이 값 안이면 비슷
EQUIV = "동등"


@dataclass(frozen=True)
class Kpi:
    """요약 지표 하나. value 는 기존·개선 중앙값을 내는 열 줄기(<value>_before/_after, with_pct 뒤),
    ratio 는 ITEM 별 비(개선/기존)를 내는 열 줄기, compare.csv 에는 <key>_ratio 열로 쓴다. 둘 다 낮을수록 좋다."""
    key: str
    name: str
    value: str
    ratio: str


RATIO_KPIS = (
    Kpi("meas_precision", "측정 정밀도", "meas_precision_pct", "meas_precision_pct"),
    Kpi("sigma_die", "반복성 σ_die", "sigma_die_pct", "sigma_die"),
    Kpi("sigma_run", "회차 이동 σ_run", "sigma_run_pct", "sigma_run"),
    Kpi("ci_width", "90% 구간 폭", "ci_width_pct", "ci_width_pct"),
)
NOT_EQUIV = "not_equivalent"
NOT_EQUIV_NAME = "동등 아닌 ITEM 수"
OVERVIEW_COLS = ["kpi", "name", "before", "after", "change", "ratio_median", "improved_pct", "n_ratio",
                 "n_skipped", "trend"]


def item_ratio(df, kpi):
    """ITEM 별 개선/기존. 기존이 0 이하이거나 어느 쪽이든 비면 NaN (비 계산에서 뺌)."""
    b, a = _num(df, f"{kpi.ratio}_before"), _num(df, f"{kpi.ratio}_after")
    return (a / b).where((b > 0) & a.notna())


def with_ratios(df):
    """compare 표에 <key>_ratio 열 (RATIO_KPIS 마다) 을 더한 복사본."""
    return df.assign(**{f"{k.key}_ratio": item_ratio(df, k) for k in RATIO_KPIS})


def trend(ratio_median):
    """비 중앙값 → 좋아짐(< 1 − TREND_BAND) / 나빠짐(> 1 + TREND_BAND, 무한대 포함) / 비슷. NaN 이면 빈 글자."""
    if np.isnan(ratio_median):
        return ""
    return BETTER if ratio_median < 1 - TREND_BAND else WORSE if ratio_median > 1 + TREND_BAND else SAME


def _median(s):
    s = s.dropna()
    return float(s.median()) if len(s) else np.nan


def kpi_table(d):
    """요약 지표 표 (OVERVIEW_COLS, 지표 한 행). d 는 with_pct 를 거친 compare 행 (판정 제외는 이미 뺀 것).
    improved_pct 는 비가 1 − TREND_BAND 미만인 ITEM 비율 (%), 동등 아닌 수는 기존 동등 아님 중 동등이 된 비율.
    동등 아닌 수의 판단도 개수 비 (개선/기존) 에 같은 ±TREND_BAND 를 쓴다 (기존 0 이면 개선도 0 일 때만 비슷)."""
    rows = []
    for k in RATIO_KPIS:
        r = item_ratio(d, k).dropna()
        before, after = _median(d[f"{k.value}_before"]), _median(d[f"{k.value}_after"])
        med = _median(r)
        rows.append({"kpi": k.key, "name": k.name, "before": before, "after": after, "change": after - before,
                     "ratio_median": med,
                     "improved_pct": 100 * float((r < 1 - TREND_BAND).mean()) if len(r) else np.nan,
                     "n_ratio": len(r), "n_skipped": len(d) - len(r), "trend": trend(med)})
    vb, va = d["verdict_before"].astype(str), d["verdict_after"].astype(str)
    nb, na = int((vb != EQUIV).sum()), int((va != EQUIV).sum())
    fixed = int(((vb != EQUIV) & (va == EQUIV)).sum())
    rows.append({"kpi": NOT_EQUIV, "name": NOT_EQUIV_NAME, "before": nb, "after": na, "change": na - nb,
                 "ratio_median": np.nan, "improved_pct": 100 * fixed / nb if nb else np.nan,
                 "n_ratio": len(d), "n_skipped": 0,
                 "trend": trend(na / nb if nb else (1.0 if na == 0 else np.inf))})
    return pd.DataFrame(rows, columns=OVERVIEW_COLS)


def best_kpi(table):
    """비 중앙값이 가장 작은 지표의 '이름 0.52배'. 그 비도 좋아짐 기준(1 − TREND_BAND) 이상이면 빈 글자."""
    t = table.dropna(subset=["ratio_median"])
    if t.empty or t["ratio_median"].min() >= 1 - TREND_BAND:
        return ""
    row = t.loc[t["ratio_median"].idxmin()]
    return f"{row['name']} {row['ratio_median']:.2f}배"


def safe_group_name(name):
    """groups/<그룹>/ 폴더 이름. 한글·영문·숫자·-·_ 만 남기고 나머지는 _ (빈 이름은 '_')."""
    s = re.sub(r"[^0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ_-]", "_", str(name).strip())
    return s or "_"


def log_clip(values, lo_pct=1, hi_pct=99, pad=0.05):
    """로그 축용 정리. 양수만 쓰고 (0·음수·NaN 은 제외로 셈),
    양수의 lo_pct–hi_pct 백분위 밖 값은 경계로 붙이고 셈.
    반환 (붙인 양수 값, (축 하한, 축 상한), 붙인 수, 제외 수).
    축 범위는 경계에서 로그로 pad 디케이드만큼 넓혀 경계 점이 축 안에 보이게 한다."""
    v = pd.to_numeric(pd.Series(np.asarray(values, dtype=float).ravel()), errors="coerce").to_numpy()
    pos = np.isfinite(v) & (v > 0)
    n_excluded = int((~pos).sum())
    p = v[pos]
    if len(p) == 0:
        return p, (np.nan, np.nan), 0, n_excluded
    lo, hi = np.percentile(p, [lo_pct, hi_pct])
    n_clipped = int(((p < lo) | (p > hi)).sum())
    clipped = np.clip(p, lo, hi)
    if lo == hi:
        lo, hi = lo / 1.5, hi * 1.5
    return clipped, (lo * 10 ** -pad, hi * 10 ** pad), n_clipped, n_excluded


# ---------------------------------------------------------------- 그림

def _skip(name, reason):
    print(f"[compare_metrics] {name} 건너뜀: {reason}")
    return None


def _save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _fmt(v):
    return "" if not np.isfinite(v) else f"{v:.4g}"


def plot_ratio(df, metric, path, top=10, title_suffix=""):
    """왼쪽: r 로그 히스토그램, 오른쪽: 기존 vs 개선 로그-로그 산점도, 아래: 악화 상위 표."""
    set_font()
    lab = LABEL[metric]
    r = ratio(df, metric)
    c = ratio_counts(r)
    rv, (rlo, rhi), r_clip, _ = log_clip(r)
    if len(rv) == 0:
        return _skip(metric, "비교 가능한 r 이 없음")
    b, a = _before_after(df, metric)
    ok = (b > 0) & (a > 0)
    both = np.concatenate([b[ok].to_numpy(), a[ok].to_numpy()])
    _, (slo, shi), _, _ = log_clip(both)
    plo, phi = np.percentile(both, [1, 99])
    b0, a0 = b[ok].to_numpy(), a[ok].to_numpy()
    edge = (b0 < plo) | (b0 > phi) | (a0 < plo) | (a0 > phi)
    n_edge = int(edge.sum())
    bx, ay = np.clip(b0, plo, phi), np.clip(a0, plo, phi)

    fig = plt.figure(figsize=(12, 7.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[3, 1.3])
    ax1, ax2, ax3 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])
    ax2.set_xscale("log")
    ax2.set_yscale("log")

    lo_b, hi_b = min(rlo, 0.9), max(rhi, 1.1)
    ax1.hist(rv, bins=np.geomspace(lo_b, hi_b, 41), color=C_AFTER, alpha=0.85)
    ax1.set_xscale("log")
    ax1.set_xlim(lo_b, hi_b)
    _plain_log_axis(ax1.xaxis)
    ax1.axvline(1, color="black", lw=1, ls="--")
    ax1.set_xlabel(f"r = 개선 {lab} / 기존 {lab}")
    ax1.set_ylabel("ITEM 수")
    txt = (f"개선(r<1) {c['improved']} · 악화(r>1) {c['worse']} · 같음 {c['same']} · "
           f"제외 {c['excluded']} · 중앙 r={c['median']:.3g}")
    if metric == "sigma_run_ratio":
        txt += f"\n둘 다 0 제외 {c['both_zero']}"
    txt += f"\n1–99% 밖 경계로 붙임 {r_clip}"
    ax1.set_title(txt, fontsize=9)

    if ok.sum() > 2000:
        hb = ax2.hexbin(bx, ay, xscale="log", yscale="log", gridsize=50, mincnt=1, cmap="Blues", bins="log")
        fig.colorbar(hb, ax=ax2, label="ITEM 수")
    else:
        ax2.scatter(bx[~edge], ay[~edge], s=10, color=C_AFTER, alpha=0.6, lw=0)
        ax2.scatter(bx[edge], ay[edge], s=18, marker="x", color="#d1495b", label=f"경계로 붙임 {n_edge}")
        if n_edge:
            ax2.legend(loc="upper left", fontsize=8)
    ax2.set_xlim(slo, shi)
    ax2.set_ylim(slo, shi)
    ax2.plot([slo, shi], [slo, shi], color="black", lw=1, ls="--")
    _plain_log_axis(ax2.xaxis, subs=(1.0,))
    _plain_log_axis(ax2.yaxis, subs=(1.0,))
    ax2.set_xlabel(f"기존 {lab}")
    ax2.set_ylabel(f"개선 {lab}")
    ax2.set_title(f"대각선 아래 = 개선 · n={int(ok.sum())} · 1–99% 밖 {n_edge}", fontsize=9)

    ax3.axis("off")
    w = worst_items(df, metric, top)
    if len(w):
        cells = [[str(i), _fmt(x), _fmt(y), _fmt(z)] for i, x, y, z in w.itertuples(index=False)]
        tb = ax3.table(cellText=cells, colLabels=["ID", f"기존 {lab}", f"개선 {lab}", "r"],
                       loc="upper center", cellLoc="center")
        tb.auto_set_font_size(False)
        tb.set_fontsize(7)
        tb.scale(1, 0.9)
        ax3.set_title(f"가장 나빠진 {len(w)}개 (r 큰 순)", fontsize=9)
    else:
        ax3.text(0.5, 0.5, "악화(r>1) 항목 없음", ha="center", va="center")

    fig.suptitle(f"{lab} 비율(개선/기존): 1보다 왼쪽이 개선{title_suffix}", fontsize=12)
    fig.tight_layout()
    return _save(fig, path)


def plot_stability(df, metric, path, title_suffix=""):
    """기존·개선 각각의 분포 (가로 상자그림, 로그 x). 왼쪽일수록 안정."""
    set_font()
    base = METRIC_STABILITY[metric]
    d = with_pct(df)
    data, info = [], []
    for side in SIDES:
        v, _, _, n_ex = log_clip(_num(d, f"{base}_{side}"), lo_pct=0, hi_pct=100)
        data.append(v)
        info.append(n_ex)
    if not all(len(v) for v in data):
        return _skip(metric, "기존 또는 개선 쪽 양수 값이 없음")
    fig, ax = plt.subplots(figsize=(9, 4))
    bp = ax.boxplot(data, vert=False, widths=0.5, patch_artist=True, whis=(1, 99),
                    flierprops=dict(markersize=2, alpha=0.4))
    for patch, col in zip(bp["boxes"], (C_BEFORE, C_AFTER)):
        patch.set_facecolor(col)
        patch.set_alpha(0.5)
    ax.set_xscale("log")
    _plain_log_axis(ax.xaxis)
    labels = []
    for side, v, n_ex in zip(SIDES, data, info):
        q25, q50, q75 = np.percentile(v, [25, 50, 75])
        labels.append(f"{SIDE[side]}\nn={len(v)}" + (f" (제외 {n_ex})" if n_ex else ""))
        y = SIDES.index(side) + 1
        ax.text(q50, y + 0.33, f"중앙 {q50:.3g} · 25% {q25:.3g} · 75% {q75:.3g}", ha="center", fontsize=8)
    ax.set_yticks([1, 2], labels)
    ax.set_xlabel(f"{LABEL[metric]} (수염 1–99%)")
    ax.set_title(f"{LABEL[metric]} 분포 기존 vs 개선: 왼쪽일수록 안정{title_suffix}", fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


def plot_verdict_center_delta(df, path, title_suffix=""):
    """center/Δ 선형 히스토그램 (기존·개선 겹친 계단), 0 과 ±1 에 선."""
    name = "verdict_center_delta"
    cols = [f"center_delta_{s}" for s in SIDES]
    if not all(c in df.columns for c in cols):
        return _skip(name, "center_delta_before/after 열이 없음")
    vals = {s: _num(df, f"center_delta_{s}").dropna().to_numpy() for s in SIDES}
    vals = {s: v[np.isfinite(v)] for s, v in vals.items()}
    if not all(len(v) for v in vals.values()):
        return _skip(name, "center_delta 값이 없음")
    set_font()
    allv = np.concatenate(list(vals.values()))
    plo, phi = np.percentile(allv, [1, 99])
    # 1–99% 밖 값은 경계 칸에 붙인다 (np.clip). 축 범위는 ±1 기준선이 보이도록 넓힌다.
    lo, hi = min(plo, -1.2), max(phi, 1.2)
    bins = np.linspace(lo, hi, 61)
    n_clip = int(((allv < plo) | (allv > phi)).sum())
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for s, col in zip(SIDES, (C_BEFORE, C_AFTER)):
        v = vals[s]
        ax.hist(np.clip(v, plo, phi), bins=bins, histtype="step", lw=1.6, color=col,
                label=f"{SIDE[s]} n={len(v)} · 중앙 {np.median(v):.3g}")
    ax.axvline(0, color="black", lw=1)
    for x in (-1, 1):
        ax.axvline(x, color="#d1495b", lw=1, ls="--")
    ax.set_xlim(lo, hi)
    ax.set_xlabel("center/Δ")
    ax.set_ylabel("ITEM 수")
    ax.legend(fontsize=8)
    ax.set_title(f"center/Δ 분포 기존 vs 개선: ±1 안쪽이 판정 기준 안{title_suffix}\n"
                 f"1~99% 밖 경계로 붙임 {n_clip}", fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


def metric_values(df, metric):
    """그룹 비교에 쓰는 값: 비율 지표는 r, 안정성은 개선 쪽 %, verdict 는 center_delta_after."""
    if metric in METRIC_RATIO:
        return ratio(df, metric)
    if metric in METRIC_STABILITY:
        return _num(with_pct(df), f"{METRIC_STABILITY[metric]}_after")
    if metric == "verdict_center_delta":
        return _num(df, "center_delta_after")
    raise KeyError(metric)


def plot_group_compare(df, groups, metric, path, overall=None, title_suffix=""):
    """그룹별 가로 상자그림 (중앙값 순). groups 는 열 이름 또는 df 와 같은 길이의 값.
    overall 은 기준선(전체 중앙값); None 이면 df 전체에서 계산."""
    set_font()
    log = metric != "verdict_center_delta"
    v = metric_values(df, metric)
    g = df[groups] if isinstance(groups, str) else pd.Series(np.asarray(groups), index=df.index)
    keep = v.notna() & np.isfinite(v) & ((v > 0) if log else True)
    v, g = v[keep], g[keep]
    if v.empty:
        return _skip(f"{metric} 그룹 비교", "쓸 수 있는 값이 없음")
    med = v.groupby(g).median().sort_values()
    order = list(med.index)
    data = [v[g == n].to_numpy() for n in order]
    if overall is None:
        overall = float(v.median())
    fig, ax = plt.subplots(figsize=(9, 1.2 + 0.35 * len(order)))
    ax.boxplot(data, vert=False, widths=0.6, whis=(5, 95), showfliers=False, patch_artist=True,
               boxprops=dict(facecolor=C_AFTER, alpha=0.4), medianprops=dict(color="black"))
    ax.set_yticks(range(1, len(order) + 1), [f"{n} (n={len(x)})" for n, x in zip(order, data)])
    ax.axvline(overall, color="#d1495b", lw=1, ls="--", label=f"전체 중앙 {overall:.3g}")
    if metric in METRIC_RATIO:
        ax.axvline(1, color="black", lw=0.8)
    if log:
        ax.set_xscale("log")
        _plain_log_axis(ax.xaxis)
    ax.legend(fontsize=8, loc="lower right")
    what = "r (개선/기존)" if metric in METRIC_RATIO else "개선 쪽 값"
    ax.set_xlabel(f"{LABEL[metric]} {what} · 상자 25–75%, 수염 5–95%")
    ax.set_title(f"그룹별 {LABEL[metric]}: 중앙값 작은 순{title_suffix}", fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


METRICS = {
    **{m: partial(plot_ratio, metric=m) for m in METRIC_RATIO},
    **{m: partial(plot_stability, metric=m) for m in METRIC_STABILITY},
    "verdict_center_delta": plot_verdict_center_delta,
}


def draw_all(df, out_dir, top=10):
    """<out_dir>/<이름>.png 를 지표마다 쓰고, 실제로 쓴 경로 목록을 돌려준다."""
    out_dir = Path(out_dir)
    written = []
    for name, fn in METRICS.items():
        kw = {"top": top} if name in METRIC_RATIO else {}
        p = fn(df=df, path=out_dir / f"{name}.png", **kw)
        if p is not None:
            written.append(Path(p))
    return written
