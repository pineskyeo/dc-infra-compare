"""흔들림 ITEM 의 CI 반폭/Δ: 선형 척도 vs log 척도 비교 (WO-S S2).

입력: por_doe_compare 의 items.csv. 쓰는 열:
  ITEM, status, verdict, verdict_log, ci_half_over_delta, ci_half_over_delta_log, log_fit, decades
  (log_fit·decades 열이 없으면 NaN)
대상: por_doe_compare.is_log_target 과 같다. status(';' 로 이은 문자열)에 '작을수록 흔들림' 또는
'클수록 흔들림' 이 있는 ITEM + verdict ≠ verdict_log ITEM (verdict_log 판정 제외·빈칸은 아님).

출력 (<out>/, 이 두 파일만 덮어씀):
  log_compare.png  x = 선형 비, y = log 비 (두 축 log), y=x 선. 대각선 아래 = log 쪽 CI 가 좁음.
                   점 색 = log_fit (0 기준 diverging, colorbar), log_fit NaN 은 회색.
                   마커 모양 = changed (같음 o, 바뀜 X), 테두리·크기 = target_status (색은 안 씀).
  log_compare.csv  ITEM, target_status, ci_half_over_delta, ci_half_over_delta_log,
                   verdict, verdict_log, changed, log_fit, decades
                   (log_fit = |skew_lin| − |skew_log|, 양수면 log 쪽이 더 대칭. decades = log10(max|x|/min|x|).
                    둘 다 items.csv 값 그대로)

사용: python log_compare.py items.csv [--out DIR]   (기본 DIR = items.csv 폴더)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D

from compare_metrics import _save, set_font

from por_doe_compare import ST_SIZE_JITTER, ST_SIZE_JITTER_POS, log_target_statuses, verdict_log_differs

PNG_NAME, CSV_NAME = "log_compare.png", "log_compare.csv"
X_COL, Y_COL = "ci_half_over_delta", "ci_half_over_delta_log"
FIT_COL = "log_fit"
CSV_COLS = ["ITEM", "target_status", X_COL, Y_COL, "verdict", "verdict_log", "changed", FIT_COL, "decades"]
VERDICT_DIFF = "verdict≠verdict_log"     # 흔들림 status 없이 verdict 와 verdict_log 가 달라 대상이 된 ITEM

MARKER = {False: "o", True: "X"}         # changed
# target_status → (마커 크기, 검정 테두리 두께). 테두리 유무 × 크기로 네 가지를 무채색으로 구분.
EDGE = {ST_SIZE_JITTER: (40, 0.0), ST_SIZE_JITTER_POS: (40, 1.4), "both": (90, 1.4), VERDICT_DIFF: (90, 0.0)}
CMAP = "RdBu"
C_NAN = "#9e9e9e"
FIT_DEFAULT_RANGE = 1.0                  # log_fit 이 전부 0/NaN 일 때 colorbar 범위 ±이 값


def target_status(status, verdict=None, verdict_log=None) -> str:
    """status 에서 대상 사유만 골라 '; ' 로 잇는다. 없고 verdict ≠ verdict_log 면 VERDICT_DIFF, 둘 다 아니면 ''."""
    hit = log_target_statuses(status)
    if hit:
        return "; ".join(hit)
    return VERDICT_DIFF if verdict_log_differs(verdict, verdict_log) else ""


def build_table(items: pd.DataFrame) -> pd.DataFrame:
    df = items.copy()
    for c in ("ITEM", "status", "verdict", "verdict_log", X_COL, Y_COL, FIT_COL, "decades"):
        if c not in df:
            df[c] = np.nan
    df["target_status"] = [target_status(*a) for a in zip(df["status"], df["verdict"], df["verdict_log"])]
    df = df[df["target_status"] != ""].copy()
    for c in (X_COL, Y_COL, FIT_COL, "decades"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    v = df["verdict"].fillna("").astype(str)
    vl = df["verdict_log"].fillna("").astype(str)
    df["changed"] = v != vl
    return df[CSV_COLS].reset_index(drop=True)


def _usable(t: pd.DataFrame) -> pd.Series:
    return (t[X_COL] > 0) & (t[Y_COL] > 0)  # NaN 비교는 False


def _marker_key(ts: str) -> str:
    return "both" if ";" in ts else ts


def _fit_norm(fit: pd.Series) -> TwoSlopeNorm:
    """0 중심 대칭 범위 ±max|log_fit|. 전부 0/NaN 이면 ±FIT_DEFAULT_RANGE (TwoSlopeNorm 은 vmin<0<vmax 필요)."""
    a = np.abs(fit.to_numpy(dtype=float))
    a = a[np.isfinite(a)]
    m = float(a.max()) if a.size and a.max() > 0 else FIT_DEFAULT_RANGE
    return TwoSlopeNorm(vcenter=0.0, vmin=-m, vmax=m)


def plot(t: pd.DataFrame, path: Path) -> dict:
    set_font()
    plt.rcParams["font.family"] = [plt.rcParams["font.family"][0], "DejaVu Sans"]
    ok = _usable(t)
    d, n_excl = t[ok], int((~ok).sum())
    below = int((d[Y_COL] < d[X_COL]).sum())
    above = int((d[Y_COL] > d[X_COL]).sum())
    on = len(d) - below - above
    changed = int(d["changed"].sum())

    fig, ax = plt.subplots(figsize=(7, 6.5))
    if d.empty:
        ax.axis("off")
        msg = "대상 ITEM 없음" + (f"\n(제외 {n_excl})" if n_excl else "")
        ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=14, transform=ax.transAxes)
        _save(fig, path)
        return {"n": 0, "below": 0, "above": 0, "changed": 0, "excluded": n_excl}

    keys = d["target_status"].map(_marker_key)
    norm = _fit_norm(d[FIT_COL])
    has_fit = d[FIT_COL].notna()
    n_nan = int((~has_fit).sum())
    for key, (size, lw) in EDGE.items():
        for chg, mk in MARKER.items():
            g = (keys == key) & (d["changed"] == chg)
            style = dict(marker=mk, s=size, alpha=0.85, edgecolors="black" if lw else "none",
                         linewidths=lw, zorder=3)
            s = d[g & has_fit]
            if not s.empty:
                ax.scatter(s[X_COL], s[Y_COL], c=s[FIT_COL], cmap=CMAP, norm=norm, **style)
            s = d[g & ~has_fit]
            if not s.empty:
                ax.scatter(s[X_COL], s[Y_COL], c=C_NAN, **style)
    fig.colorbar(ScalarMappable(norm=norm, cmap=CMAP), ax=ax, label=FIT_COL,
                 fraction=0.046, pad=0.03)

    vals = np.concatenate([d[X_COL].to_numpy(), d[Y_COL].to_numpy()])
    lo, hi = vals.min() / 1.5, vals.max() * 1.5
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.plot([lo, hi], [lo, hi], color="#555555", lw=1, ls="--", zorder=2)
    ax.grid(True, which="major", color="#e5e5e5", lw=0.6)
    ax.set_xlabel("CI 반폭 / Δ  (선형 척도)")
    ax.set_ylabel("CI 반폭 / Δ  (log 척도)")

    note = f"대각선 위 {above}  (log 쪽 CI 넓음)"
    ax.text(0.03, 0.97, note, transform=ax.transAxes, ha="left", va="top", fontsize=9)
    note = f"대각선 아래 {below}  (log 쪽 CI 좁음)"
    if on:
        note += f"\ny=x 와 같음 {on}"
    if n_excl:
        note += f"\n제외 {n_excl}  (비가 NaN 또는 ≤0)"
    ax.text(0.97, 0.03, note, transform=ax.transAxes, ha="right", va="bottom", fontsize=9)

    hollow = dict(ls="", markerfacecolor="#e0e0e0", markeredgecolor="black")
    handles = [
        Line2D([], [], marker=MARKER[False], markersize=7, label=f"판정 같음 {len(d) - changed}",
               **{**hollow, "markeredgewidth": 0}),
        Line2D([], [], marker=MARKER[True], markersize=7,
               label=f"판정 바뀜 (verdict ≠ verdict_log) {changed}", **{**hollow, "markeredgewidth": 0}),
    ]
    present = set(keys)
    handles += [Line2D([], [], marker="o", markersize=EDGE[k][0] ** 0.5, markeredgewidth=EDGE[k][1],
                       label="테두리: " + ("둘 다" if k == "both" else k), **hollow) for k in EDGE if k in present]
    if n_nan:
        handles.append(Line2D([], [], ls="", marker="o", color=C_NAN, markersize=7,
                              label=f"log_fit 없음 {n_nan}"))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 0.9), fontsize=8, framealpha=0.9)
    ax.set_title(f"흔들림 ITEM: 선형 vs log 척도 CI 반폭/Δ  (n={len(d)})", fontsize=11)
    fig.tight_layout()
    _save(fig, path)
    return {"n": len(d), "below": below, "above": above, "changed": changed, "excluded": n_excl}


def run(items_csv, out_dir=None) -> dict:
    """그림·표를 쓰고 그림에 들어간 ITEM 기준 개수를 돌려준다.

    n/below/above/changed 는 그림에 찍힌(두 비 모두 > 0) ITEM 수, excluded 는 대상이지만 뺀 수.
    csv 에는 제외 행도 포함한 대상 ITEM 전부가 들어간다.
    """
    items_csv = Path(items_csv)
    out = Path(out_dir) if out_dir is not None else items_csv.parent
    out.mkdir(parents=True, exist_ok=True)
    items = pd.read_csv(items_csv, encoding="utf-8-sig")
    t = build_table(items)
    t.to_csv(out / CSV_NAME, index=False, encoding="utf-8-sig")
    return plot(t, out / PNG_NAME)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="흔들림 ITEM 의 선형 vs log 척도 CI 반폭/Δ 비교")
    ap.add_argument("items_csv")
    ap.add_argument("--out", default=None, help="출력 폴더 (기본: items.csv 폴더)")
    a = ap.parse_args(argv)
    r = run(a.items_csv, a.out)
    print(f"[log_compare] n={r['n']} 아래={r['below']} 위={r['above']} "
          f"판정 바뀜={r['changed']} 제외={r['excluded']}")


if __name__ == "__main__":
    main()
