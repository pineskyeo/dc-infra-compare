"""ITEM 한 장 보기 (item_view.png)와 근거 표 한 행 (evidence.csv). 설계 1-6·1-7·1-8.

rows = 그 ITEM 의 die별 원데이터 (fail_evidence.load_raw: die 좌표, ITEM, POR1..PORn, DOE, blank 열),
row  = items.csv 그 ITEM 한 행 (값은 문자열이어도 된다).

  basis_numbers(row)            최종 판정을 정한 숫자 (log 판정이면 log 열, accuracy 면 장비 정확도 폭까지)
  die_evidence(rows, row)       die별 차이 d 와 신뢰구간 끝 die, 튀는 die
  evidence_row(rows, row)       evidence.csv 한 행 (EVIDENCE_COLUMNS)
  plot_item_view(rows, row, path)
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import ticker  # noqa: E402

import explain  # noqa: E402
from por_doe_compare import K_LOQ, OUTLIER_K, ST_NEAR_LOQ, ci_rank, robust_sigma  # noqa: E402

POR_COL_RE = re.compile(r"^POR\d+$")
NOT_DIE_COLS = {"ITEM", "DOE", "d", "por_range", "blank_item", "blank_sigma0", "blank_offset"}
XY_PAIRS = (("X", "Y"), ("DIE_X", "DIE_Y"), ("COORD_X", "COORD_Y"), ("DIEX", "DIEY"))
XY_TEXT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[_,:/ ]\s*(-?\d+(?:\.\d+)?)\s*$")
LOG_BASES = ("log", "log_physics")
POR_COLOR, DOE_COLOR, BAR_COLOR, MEDIAN_COLOR = "#9a9a9a", "#d62728", "#8fb3d9", "#1f3b73"
BAND_COLOR, DELTA_COLOR, ACC_COLOR, OUTLIER_COLOR = "#cfe3f7", "#ff7f0e", "#2ca02c", "#000000"


def _num(row, key: str) -> float:
    try:
        return float(row.get(key))
    except (TypeError, ValueError):
        return math.nan


def _text(row, key: str) -> str:
    v = row.get(key)
    return "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v).strip()


def por_columns(rows: pd.DataFrame) -> list[str]:
    return [c for c in rows.columns if POR_COL_RE.match(str(c))]


def die_xy(rows: pd.DataFrame) -> tuple[pd.Series, pd.Series] | None:
    """die 좌표 (x, y). X/Y 같은 숫자 열 쌍, 없으면 COORD_X_Y 처럼 '1_2' 글자 열. 둘 다 없으면 None."""
    upper = {str(c).strip().upper(): c for c in rows.columns}
    for xn, yn in XY_PAIRS:
        if xn in upper and yn in upper:
            x = pd.to_numeric(rows[upper[xn]], errors="coerce")
            y = pd.to_numeric(rows[upper[yn]], errors="coerce")
            if x.notna().all() and y.notna().all():
                return x, y
    for name, col in upper.items():
        if "X_Y" in name or "XY" in name:
            parts = rows[col].astype(str).str.extract(XY_TEXT_RE)
            if parts.notna().all().all():
                return parts[0].astype(float), parts[1].astype(float)
    return None


def die_labels(rows: pd.DataFrame) -> list[str]:
    """die 이름: 좌표 열 값 (모든 die 가 같은 값인 열은 뺌, 예: 웨이퍼 하나). 좌표 열이 없으면 'die <순번>'."""
    cols = [c for c in rows.columns if c not in NOT_DIE_COLS and not POR_COL_RE.match(str(c))]
    varying = [c for c in cols if rows[c].nunique() > 1] or cols
    if not varying:
        return [f"die {i + 1}" for i in range(len(rows))]
    return [" ".join(str(v) for v in vals) for vals in rows[varying].itertuples(index=False)]


# ---------------------------------------------------------------- 판정 숫자

@dataclass(frozen=True)
class Basis:
    """최종 판정(verdict_final)을 정한 숫자. log 판정이면 모두 log10 값 (center 는 log10(DOE/POR) 중앙값)."""
    name: str                 # verdict_basis
    log: bool
    center: float
    ci_low: float
    ci_high: float
    delta: float              # 정책 + 회차 (log 면 Δ_log)
    policy: float
    run: float
    accuracy: float           # 장비 정확도 폭 (accuracy 판정만, 아니면 NaN)

    @property
    def margin(self) -> float:
        """판정에 쓴 허용폭. accuracy 판정이면 max(Δ, 장비 정확도 폭)."""
        return max(self.delta, self.accuracy) if math.isfinite(self.accuracy) else self.delta


def basis_numbers(row) -> Basis:
    name = _text(row, "verdict_basis") or "linear"
    if name in LOG_BASES:
        delta, rep = _num(row, "delta_log"), _num(row, "sigma_rep_log")
        return Basis(name, True, _num(row, "center_log"), _num(row, "ci_low_log"), _num(row, "ci_high_log"),
                     delta, delta - rep, rep, math.nan)
    return Basis(name, False, _num(row, "center"), _num(row, "ci_low"), _num(row, "ci_high"), _num(row, "delta"),
                 _num(row, "policy_margin"), _num(row, "run_margin"),
                 _num(row, "accuracy_margin") if name == "accuracy" else math.nan)


# ---------------------------------------------------------------- die별 근거

@dataclass(frozen=True)
class DieEvidence:
    basis: Basis
    labels: list[str]
    d: np.ndarray             # die별 차이 (basis 척도): DOE − POR 회차 평균, log 면 log10|DOE| − 회차 평균 log10|POR|
    order: np.ndarray         # d 작은 순서 (같으면 원래 순서)
    k: int                    # 신뢰구간 아래 끝의 1-based 순번. 위 끝은 n − k + 1
    outlier: np.ndarray       # 판정의 튀는 die (선형 d 가 중앙값에서 OUTLIER_K × robust σ 넘게 떨어짐)
    keep: np.ndarray          # rows 중 d 가 유한해 쓴 die

    @property
    def n(self) -> int:
        return len(self.d)

    @property
    def ci_positions(self) -> tuple[int, int]:
        """신뢰구간 끝 두 die 의 rows 위치."""
        return int(self.order[self.k - 1]), int(self.order[self.n - self.k])

    @property
    def median_rank(self) -> float:
        return (self.n + 1) / 2


def die_evidence(rows: pd.DataFrame, row) -> DieEvidence:
    """rows 는 d 가 유한한 die 만 쓴다 (원데이터 행 순서 유지)."""
    basis = basis_numbers(row)
    por = rows[por_columns(rows)].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    doe = pd.to_numeric(rows["DOE"], errors="coerce").to_numpy(float)
    linear = doe - por.mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.log10(np.abs(doe)) - np.log10(np.abs(por)).mean(axis=1) if basis.log else linear
    keep = np.isfinite(d)
    d, linear = d[keep], linear[keep]
    rs = robust_sigma(linear) if len(linear) else 0.0
    outlier = np.abs(linear - np.median(linear)) > OUTLIER_K * rs if rs > 0 else np.zeros(len(d), bool)
    labels = [lab for lab, k in zip(die_labels(rows), keep) if k]
    return DieEvidence(basis, labels, d, np.argsort(d, kind="stable"), ci_rank(len(d)) + 1 if len(d) else 0, outlier,
                       keep)


EVIDENCE_COLUMNS = ("ITEM", "ID", "verdict_final", "verdict_basis", "reason_plain", "d_scale", "center", "ci_low",
                    "ci_high", "n_die", "ci_rank_k", "ci_low_die", "ci_low_d", "ci_high_die", "ci_high_d",
                    "n_d_pos", "n_d_neg", "n_d_zero", "delta", "policy_margin", "run_margin", "accuracy_margin",
                    "n_outlier_die", "outlier_dies", "LoQ", "por_over_loq")


def evidence_row(rows: pd.DataFrame, row) -> dict:
    """evidence.csv 한 행. center·ci·Δ 는 items.csv (판정이 낸 값), 순번·die·d 는 원데이터에서 다시 셈."""
    ev = die_evidence(rows, row)
    b = ev.basis
    por, loq = _num(row, "por_median"), _num(row, "LoQ")
    out = dict.fromkeys(EVIDENCE_COLUMNS, "")
    out.update(ITEM=_text(row, "ITEM"), ID=_text(row, "ID"),
               verdict_final=_text(row, "verdict_final") or _text(row, "verdict"), verdict_basis=b.name,
               reason_plain=explain.reason_plain(row), d_scale="log" if b.log else "linear",
               center=b.center, ci_low=b.ci_low, ci_high=b.ci_high, n_die=ev.n,
               n_d_pos=int((ev.d > 0).sum()), n_d_neg=int((ev.d < 0).sum()), n_d_zero=int((ev.d == 0).sum()),
               delta=b.delta, policy_margin=b.policy, run_margin=b.run, accuracy_margin=b.accuracy,
               n_outlier_die=int(ev.outlier.sum()),
               outlier_dies="; ".join(lab for lab, o in zip(ev.labels, ev.outlier) if o),
               LoQ=loq, por_over_loq=abs(por) / loq if math.isfinite(por) and loq > 0 else math.nan)
    if ev.n:
        lo, hi = ev.ci_positions
        out.update(ci_rank_k=ev.k, ci_low_die=ev.labels[lo], ci_low_d=ev.d[lo], ci_high_die=ev.labels[hi],
                   ci_high_d=ev.d[hi])
    return out


# ---------------------------------------------------------------- 그림

def _value_axis(axis, unit: str) -> None:
    """눈금 글자를 단위 붙은 값 (12.3 pA) 으로. 기본 눈금은 1e-11 같은 공통 배수를 축 끝에 따로 쓴다."""
    axis.set_major_formatter(ticker.FuncFormatter(lambda v, _: explain.fmt(v, unit)))


def _log_axis(axis, unit: str) -> None:
    """log 축 눈금을 1·2·5 × 10^k 에 값 글자 (12.3 pA) 로. 기본 지수 글자는 한글 글꼴에 없는 마이너스를 쓴다."""
    axis.set_major_locator(ticker.LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    axis.set_major_formatter(ticker.FuncFormatter(lambda v, _: explain.fmt(v, unit)))
    axis.set_minor_formatter(ticker.NullFormatter())


def _fmt(v: float, unit: str, b: Basis, signed: bool = False) -> str:
    """판정 척도의 값. log 면 배율 (×1.10)."""
    if b.log:
        return f"×{explain._times(10 ** v)}" if math.isfinite(v) else "-"
    return explain.fmt(v, unit, signed=signed)


MarginLine = tuple[float, str, str, str]        # (허용폭, 이름, 색, 선 모양)


def _margin_lines(b: Basis, unit: str) -> list[MarginLine]:
    """판정 허용폭, accuracy 면 장비 정확도로 넓힌 허용폭까지."""
    lines = []
    if math.isfinite(b.delta):
        size = (f"log ±{explain._sig3(b.delta)} (×{explain._times(10 ** -b.delta)} ~ ×{explain._times(10 ** b.delta)})"
                if b.log else f"±{explain.fmt(b.delta, unit)}")
        lines.append((b.delta, f"허용폭 {size}", DELTA_COLOR, "--"))
    if math.isfinite(b.accuracy) and b.accuracy > b.delta:
        lines.append((b.accuracy, f"장비 정확도로 넓힌 허용폭 ±{explain.fmt(b.accuracy, unit)}", ACC_COLOR, ":"))
    return lines


def _outside_legend(ax, line: MarginLine) -> None:
    """그림 범위 밖이라 안 그린 허용폭을 범례에만."""
    m, name, color, ls = line
    ax.plot([], [], color=color, ls=ls, lw=1.2, label=f"{name}: 그림 범위 밖")


def _panel_pairs(ax, rows: pd.DataFrame, ev: DieEvidence, unit: str) -> None:
    """① 같은 die 짝: x = POR1, y = DOE (색)와 POR2.. (회색), y = x 와 y = x ± 허용폭."""
    b = ev.basis
    por_cols = por_columns(rows)
    vals = {c: pd.to_numeric(rows[c], errors="coerce").to_numpy(float) for c in [*por_cols, "DOE"]}
    if b.log:
        vals = {c: np.abs(v) for c, v in vals.items()}
    x = vals[por_cols[0]]
    for c in por_cols[1:]:
        ax.scatter(x, vals[c], s=14, color=POR_COLOR, alpha=0.6,
                   label="Ref: 같은 die 다시 잼 (" + ", ".join(por_cols[1:]) + ")" if c == por_cols[1] else None)
    ax.scatter(x, vals["DOE"], s=18, color=DOE_COLOR, alpha=0.8, label="DOE")
    if ev.outlier.any():
        ax.scatter(x[ev.outlier], vals["DOE"][ev.outlier], s=70, facecolors="none", edgecolors=OUTLIER_COLOR,
                   lw=1.2, label=f"튀는 die {int(ev.outlier.sum())}개")
    allv = np.concatenate([v[np.isfinite(v)] for v in vals.values()])
    if b.log:
        allv = allv[allv > 0]
        lo, hi = float(allv.min()), float(allv.max())
        lo, hi = lo / (hi / lo) ** 0.05, hi * (hi / lo) ** 0.05
        ax.set_xscale("log")
        ax.set_yscale("log")
        _log_axis(ax.xaxis, unit)
        _log_axis(ax.yaxis, unit)
    else:
        lo, hi = float(allv.min()), float(allv.max())
        pad = (hi - lo) * 0.05 or abs(hi) * 0.05 or 1.0
        lo, hi = lo - pad, hi + pad
        _value_axis(ax.xaxis, unit)
        _value_axis(ax.yaxis, unit)
    grid = np.geomspace(lo, hi, 50) if b.log else np.array([lo, hi])
    ax.plot(grid, grid, color="#333333", lw=1, label="y = x (차이 없음)")
    for line in _margin_lines(b, unit):
        m, name, color, ls = line
        if (math.log10(hi / lo) if b.log else hi - lo) < m:
            _outside_legend(ax, line)
            continue
        for s in (-1, 1):
            ax.plot(grid, grid * 10 ** (s * m) if b.log else grid + s * m, color=color, ls=ls, lw=1.2,
                    label=f"y = x ± {name}" if s > 0 else None)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal", adjustable="box")
    absname = "|값|" if b.log and (pd.to_numeric(rows["DOE"], errors="coerce") < 0).any() else "값"
    ax.set_xlabel(f"{por_cols[0]} {absname} (같은 die)")
    ax.set_ylabel(f"DOE·다른 POR 회차 {absname}")
    ax.set_title("① 같은 die 짝 그림: POR1 대 DOE" + (" (log 축)" if b.log else ""), fontsize=10)
    ax.legend(fontsize=7, loc="upper left" if b.center < 0 else "lower right")
    ax.grid(alpha=0.3, which="both" if b.log else "major")


def _panel_sorted_d(ax, ev: DieEvidence, unit: str) -> None:
    """② die별 차이를 작은 순서로 세운 막대. 중앙값 막대, 신뢰구간 끝 die (k, n − k + 1번째), ±허용폭."""
    b = ev.basis
    n, k = ev.n, ev.k
    ranks = np.arange(1, n + 1)
    ds = ev.d[ev.order]
    colors = [BAR_COLOR] * n
    for r in {math.floor(ev.median_rank), math.ceil(ev.median_rank)}:
        colors[r - 1] = MEDIAN_COLOR
    ax.axvspan(k - 0.5, n - k + 1.5, color=BAND_COLOR, alpha=0.7, lw=0,
               label=f"90% 신뢰구간을 정하는 die ({k}~{n - k + 1}번째)")
    edge = [OUTLIER_COLOR if o else "none" for o in ev.outlier[ev.order]]
    ax.bar(ranks, ds, width=0.85, color=colors, edgecolor=edge, lw=1.0)
    ax.bar([], [], color=MEDIAN_COLOR, label=f"중앙값 = 대표 이동량 {_fmt(b.center, unit, b, signed=True)}")
    if ev.outlier.any():
        ax.bar([], [], color=BAR_COLOR, edgecolor=OUTLIER_COLOR, label="튀는 die (검은 테두리)")
    extent = max(float(np.abs(ds).max()), b.delta if math.isfinite(b.delta) else 0.0)
    shown = []
    for line in _margin_lines(b, unit):
        m, name, color, ls = line
        if m > 1.5 * extent:
            _outside_legend(ax, line)
            continue
        shown.append(m)
        for s in (-1, 1):
            ax.axhline(s * m, color=color, ls=ls, lw=1.3, label=name if s > 0 else None)
    ax.axhline(0, color="#555555", lw=0.8)
    lo_pos, hi_pos = ev.ci_positions
    top = max(float(np.nanmax(ds)), *shown, 0.0)
    bottom = min(float(np.nanmin(ds)), *(-m for m in shown), 0.0)
    span = top - bottom or 1.0
    ax.set_ylim(bottom - 0.08 * span, top + 0.32 * span)
    for rank, pos, ha, y in ((k, lo_pos, "left", top + 0.18 * span), (n - k + 1, hi_pos, "right", top + 0.06 * span)):
        ax.plot([rank, rank], [ev.d[pos], y], color="#1f3b73", lw=0.8)
        ax.text(rank, y, f"{rank}번째 die {ev.labels[pos]}: {_fmt(ev.d[pos], unit, b, signed=True)}", ha=ha,
                va="bottom", fontsize=8, bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=1))
    ax.set_xlim(0.3, n + 0.7)
    ax.set_xlabel(f"die 순번 (차이가 작은 것부터, 모두 {n}개)")
    if b.log:
        ax.set_ylabel("DOE ÷ POR 배율의 log10 (0 = 같음)")
    else:
        ax.set_ylabel("die별 차이 = DOE - POR 회차 평균")
        _value_axis(ax.yaxis, unit)
    ax.set_title("② die별 차이를 작은 순서로 세움", fontsize=10)
    ax.legend(fontsize=7, loc="lower right", ncol=2)
    ax.grid(axis="y", alpha=0.3)


def _panel_map(fig, ax, xy, ev: DieEvidence, unit: str) -> None:
    """③ 웨이퍼맵: die별 차이, 0 중심 발산색, 색 끝 = ±허용폭 (정책 + 회차. 장비 정확도 폭은 넣지 않음)."""
    b = ev.basis
    lim = b.delta if math.isfinite(b.delta) and b.delta > 0 else float(np.abs(ev.d).max()) or 1.0
    sc = ax.scatter(xy[0], xy[1], c=ev.d, cmap="RdBu_r", vmin=-lim, vmax=lim, s=min(60.0, 6000 / max(ev.n, 1)),
                    marker="s", edgecolors=[OUTLIER_COLOR if o else "none" for o in ev.outlier], linewidths=1.0)
    over = int((np.abs(ev.d) > lim).sum())
    what = "log10 배율" if b.log else "차이"
    cb = fig.colorbar(sc, ax=ax, extend="both", shrink=0.9)
    cb.set_label(f"die별 {what} (색 끝 = ±허용폭, 넘는 die {over}개는 끝 색)", fontsize=8)
    if not b.log:
        _value_axis(cb.ax.yaxis, unit)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("die x 좌표")
    ax.set_ylabel("die y 좌표")
    ax.set_title("③ 웨이퍼 위 die별 차이 (빨강 = DOE가 높음)", fontsize=10)


def _panel_values(ax, rows: pd.DataFrame, row, b: Basis, unit: str) -> None:
    """④ POR 회차별·DOE die 값: box + 흩뿌린 점. LoQ zone·LoQ 근처면 LoD·LoQ 선."""
    cols = [*por_columns(rows), "DOE"]
    data = [pd.to_numeric(rows[c], errors="coerce").dropna().to_numpy() for c in cols]
    ax.boxplot([v if len(v) else [math.nan] for v in data], widths=0.5, showfliers=False,
               medianprops={"color": "#333333"})
    for i, (c, v) in enumerate(zip(cols, data), start=1):
        jitter = (np.arange(len(v)) % 7 - 3) * 0.04
        ax.plot(i + jitter, v, "o", ms=3, alpha=0.6, color=DOE_COLOR if c == "DOE" else POR_COLOR)
    loq_zone = _text(row, "zone") in explain.LOQ_ZONES
    if loq_zone or ST_NEAR_LOQ in _text(row, "status").split(";"):
        for key, ls, name in (("LoD", ":", "검출 한계 LoD"), ("LoQ", "--", "정량 한계 LoQ")):
            v = _num(row, key)
            if math.isfinite(v):
                ax.axhline(v, color="#333333", ls=ls, lw=1.1, label=f"{name} {explain.fmt(v, unit)}")
        ax.legend(fontsize=7, loc="best")
    allv = np.concatenate(data) if data else np.array([])
    if len(allv) and (allv > 0).all() and (b.log or loq_zone):
        ax.set_yscale("log")
        _log_axis(ax.yaxis, unit)
    else:
        _value_axis(ax.yaxis, unit)
    ax.set_xticks(range(1, len(cols) + 1))
    ax.set_xticklabels(cols, fontsize=8)
    ax.set_ylabel("die 값" + (" (log 축)" if ax.get_yscale() == "log" else ""))
    ax.set_title("④ POR 회차별·DOE die 값", fontsize=10)
    ax.grid(axis="y", alpha=0.3)


def blank_applies(rows: pd.DataFrame, row) -> bool:
    sig = pd.to_numeric(rows.get("blank_sigma0", pd.Series(dtype=float)), errors="coerce")
    return _text(row, "blank_status") == "적용" and bool((sig > 0).any())


def _panel_blank(ax, rows: pd.DataFrame, row, unit: str) -> None:
    """Blank: blank 흔들림 (σ0·offset, ITEM 단위로 환산)과 POR·DOE 값 분포, LoD·LoQ."""
    sigma = float(pd.to_numeric(rows["blank_sigma0"], errors="coerce").dropna().iloc[0])
    off = pd.to_numeric(rows.get("blank_offset", pd.Series(dtype=float)), errors="coerce").dropna()
    mu = float(off.iloc[0]) if not off.empty else 0.0
    b_loq = _num(row, "blank_LoQ_item")
    scale = b_loq / (abs(mu) + K_LOQ * sigma) if math.isfinite(b_loq) and b_loq > 0 else 1.0
    mu, sigma = mu * scale, sigma * scale
    por = rows[por_columns(rows)].apply(pd.to_numeric, errors="coerce").stack().to_numpy()
    doe = pd.to_numeric(rows["DOE"], errors="coerce").dropna().to_numpy()
    lo = min(mu - 4 * sigma, *por, *doe)
    hi = max(mu + 4 * sigma, *por, *doe, _num(row, "LoQ") if math.isfinite(_num(row, "LoQ")) else -math.inf)
    bins = np.linspace(lo, hi, 40)
    ax.hist(por, bins=bins, density=True, histtype="step", lw=1.5, color=POR_COLOR, label="POR 값")
    ax.hist(doe, bins=bins, density=True, histtype="step", lw=1.5, color=DOE_COLOR, label="DOE 값")
    xs = np.linspace(lo, hi, 400)
    ax.fill_between(xs, np.exp(-0.5 * ((xs - mu) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi)),
                    color="#7f7f7f", alpha=0.25, label=f"Blank(빈 측정) 흔들림 σ {explain.fmt(sigma, unit)}")
    for key, ls, name in (("LoD", ":", "검출 한계 LoD"), ("LoQ", "--", "정량 한계 LoQ")):
        v = _num(row, key)
        if math.isfinite(v):
            ax.axvline(v, color="#333333", ls=ls, lw=1.1, label=f"{name} {explain.fmt(v, unit)}")
    ax.set_yticks([])
    ax.set_ylabel("die 수 (비율)")
    ax.set_xlabel("값")
    _value_axis(ax.xaxis, unit)
    ax.set_title(f"Blank와 정량 한계 (blank {_text(row, 'blank_item') or ''})", fontsize=10)
    ax.legend(fontsize=7, loc="best")


def _how_to_read(ev: DieEvidence, has_map: bool, has_blank: bool) -> str:
    b = ev.basis
    what = "log10(DOE/POR) 배율" if b.log else "차이(DOE - POR 회차 평균)"
    parts = [
        "① 같은 die를 x = POR1, y = DOE(빨강)와 다른 POR 회차(회색)로 찍었다. 회색 점이 퍼진 만큼이 같은 die를 다시 잰 "
        "흔들림이다. 빨간 점이 회색 무리보다 대각선에서 한쪽으로 멀리 몰려 있으면 DOE가 정말 달라진 것이다. "
        "점선은 대각선 ± 허용폭이다.",
        f"② die별 {what}를 작은 것부터 세웠다. 진한 막대가 가운데 die(중앙값 = 대표 이동량), 파란 띠가 90% 신뢰구간을 "
        "정하는 die 범위이고 그 양 끝 die 이름을 적었다. 주황 점선은 ±허용폭이다. 막대가 모두 주황선 밖 한쪽이면 차이, "
        "거의 다 안이면 동등이다.",
    ]
    if has_map:
        parts.append("③ 같은 차이를 웨이퍼 위치에 칠했다. 특정 위치에 몰리면 공정 위치나 프로브 접촉 영향일 수 있다.")
    parts.append("④ 회차별·DOE die 값 분포다.")
    if has_blank:
        parts.append("Blank 칸은 빈 측정의 흔들림과 그것으로 정한 정량 한계(LoQ)를 값 분포와 같이 보인다.")
    return " ".join(parts)


def _this_run(ev: DieEvidence, unit: str) -> str:
    b = ev.basis
    up, down = int((ev.d > 0).sum()), int((ev.d < 0).sum())
    lo, hi = ev.ci_positions
    side = (f"{ev.n}개 die 중 {up}개에서 DOE가 높다." if up >= down else f"{ev.n}개 die 중 {down}개에서 DOE가 낮다.")
    ci = (f"90% 신뢰구간 {_fmt(b.ci_low, unit, b, True)} ~ {_fmt(b.ci_high, unit, b, True)}는 "
          f"{ev.k}번째 die {ev.labels[lo]}와 {ev.n - ev.k + 1}번째 die {ev.labels[hi]}의 값이다.")
    out = f"튀는 die {int(ev.outlier.sum())}개." if ev.outlier.any() else "튀는 die 없음."
    return " ".join([side, ci, out])


CARD_FONTSIZE = 10.5
CARD_LINE_IN = 0.23


def plot_item_view(rows: pd.DataFrame, row, path: Path) -> Path:
    """ITEM 한 장: 판정 카드, ① 같은 die 짝, ② die별 차이 순서 막대, ③ 웨이퍼맵 (좌표 있을 때), ④ 값 분포,
    Blank (blank 가 이 ITEM 에 적용됐을 때), 아래 읽는 법·이번 결과."""
    rows = rows.reset_index(drop=True)
    ev = die_evidence(rows, row)
    rows = rows[ev.keep].reset_index(drop=True)
    unit = _text(row, "UNIT").strip("[]")
    up, down = int((ev.d > 0).sum()), int((ev.d < 0).sum())
    card = [line for line in explain.verdict_card(row, up, down) if line]
    xy = die_xy(rows)
    has_blank = blank_applies(rows, row)
    bottom = 1 + (xy is not None) + has_blank

    width = 15.0
    fig = plt.figure(figsize=(width, 1.0), layout="constrained")
    renderer = fig.canvas.get_renderer()
    probe = fig.text(0, 0, "", fontsize=CARD_FONTSIZE)
    wrapped = [explain._wrap_measured(line, probe, renderer, (width - 0.6) * fig.dpi) for line in card]
    probe.remove()
    n_lines = sum(w.count("\n") + 1 for w in wrapped)
    card_h = CARD_LINE_IN * n_lines + 0.25
    fig.set_size_inches(width, card_h + 5.6 + 4.4)
    gs = fig.add_gridspec(3, 1, height_ratios=[card_h, 5.6, 4.4])
    cax = fig.add_subplot(gs[0])
    cax.set_axis_off()
    cax.text(0, 1, "\n".join(wrapped[1:]), transform=cax.transAxes, va="top", ha="left", fontsize=CARD_FONTSIZE,
             linespacing=1.5)
    cax.set_title(wrapped[0], loc="left", fontsize=CARD_FONTSIZE + 2, weight="bold")
    top = gs[1].subgridspec(1, 2, width_ratios=[1, 1.7])
    _panel_pairs(fig.add_subplot(top[0]), rows, ev, unit)
    _panel_sorted_d(fig.add_subplot(top[1]), ev, unit)
    low = gs[2].subgridspec(1, bottom)
    slot = iter(range(bottom))
    if xy is not None:
        _panel_map(fig, fig.add_subplot(low[next(slot)]), xy, ev, unit)
    _panel_values(fig.add_subplot(low[next(slot)]), rows, row, ev.basis, unit)
    if has_blank:
        _panel_blank(fig.add_subplot(low[next(slot)]), rows, row, unit)
    explain.add_figure_note(fig, _how_to_read(ev, xy is not None, has_blank), _this_run(ev, unit))
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path

