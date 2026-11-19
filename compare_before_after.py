#!/usr/bin/env python3
"""por_doe_compare.py 결과 표를 읽어 ITEM별 근거를 내거나, 기존·개선 두 표를 ID로 맞춰 비교한다.

사용:
  python3 compare_before_after.py evidence RESULT.tsv -o OUTDIR
  python3 compare_before_after.py compare BEFORE.tsv AFTER.tsv -o OUTDIR

입력은 탭 또는 쉼표 구분. 헤더는 ID로 시작하는 줄. reason 열은 없어도 되고, 추가 열은 무시한다.
"""
from __future__ import annotations

import argparse
import io
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

# ---------------------------------------------------------------------------
# 분류·정렬 상수 (내부 기준).
#   미결-기준 흔들림: POR 회차 간격/Δ >= POR_GAP_OVER_DELTA
#                    또는 por_median이 세 회차 평균(POR·DOE) 밖으로
#                    MEDIAN_OUT_OVER_DELTA·Δ 이상.
#   POR 회차끼리 일치하고 por_median이 [min, max](POR, DOE) 안이면
#   median_out=0이라 미결-정상으로 둔다(해상도 부족 미결).
# ---------------------------------------------------------------------------
POR_GAP_OVER_DELTA = 0.25
MEDIAN_OUT_OVER_DELTA = 0.10
MEDIAN_MISALIGN = 0.20  # 같은 ID인데 |por_median| 상대차가 이 값을 넘으면 정렬 의심
RATIO_DIGITS = 9

J_DIFF = "차이"
J_OK = "미결-정상"
J_BASE = "미결-기준 흔들림"
GROUP_ORDER = (J_DIFF, J_OK, J_BASE)

NAVY, LIGHT, GRAY, RED, BAND, GOLD = (
    "#3D4C61", "#9AA8BC", "#7F8C9F", "#B5523B", "#E1E6ED", "#C9A27A",
)
GROUP_COLOR = {J_DIFF: NAVY, J_OK: LIGHT, J_BASE: GOLD}
BEFORE_COLOR, AFTER_COLOR, WARN_COLOR = "#7F8C9F", "#3D4C61", "#B5523B"

NUMERIC_COLS = frozenset((
    "n_die", "por_median", "center", "ci_low", "ci_high", "delta",
    "policy_margin", "run_margin", "sigma_die", "sigma_run", "LoQ", "LoD",
))
MEAN_RE = re.compile(r"^\w+_mean$")
POR_RE = re.compile(r"^POR(\d+)_mean$")

# 비교 CSV 열 순서
COMPARE_COLS = [
    "ID", "presence", "misaligned", "por_median_rel_diff",
    "verdict_before", "verdict_after", "verdict_transition",
    "sigma_die_pct_before", "sigma_die_pct_after", "sigma_die_pct_change", "sigma_die_status",
    "sigma_run_pct_before", "sigma_run_pct_after", "sigma_run_pct_change", "sigma_run_status",
    "delta_pct_before", "delta_pct_after", "delta_pct_change",
    "ci_width_pct_before", "ci_width_pct_after", "ci_width_pct_change",
    "both_lower",
    "por_median_before", "por_median_after",
    "sigma_die_before", "sigma_die_after",
    "sigma_run_before", "sigma_run_after",
]

EVIDENCE_COLS = [
    "ID", "verdict", "group", "doe_pct", "por_gap_pct",
    "center_over_delta", "ci_low_over_delta", "ci_high_over_delta",
    "ci_halfwidth_over_delta", "loq_ratio",
    "sigma_die_pct", "sigma_run_pct", "delta_pct",
    "median_outside_runs", "por_gap_over_delta", "median_out_over_delta",
    "judgment",
]


# ---------------------------------------------------------------- 글꼴·읽기

def configure_font() -> str:
    names = {f.name for f in fm.fontManager.ttflist}
    font = next((n for n in ("Pretendard", "Noto Sans CJK KR", "NanumGothic") if n in names), "DejaVu Sans")
    plt.rcParams.update({
        "font.family": font,
        "axes.unicode_minus": False,
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#808080",
        "axes.labelcolor": "#404040",
        "xtick.color": "#595959",
        "ytick.color": "#595959",
    })
    return font


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="cp949")


def _header_index(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        stripped = line.lstrip("\ufeff")
        if stripped.startswith("ID\t") or stripped.startswith("ID,"):
            return i
    raise ValueError(f"ID로 시작하는 헤더 줄이 없습니다: 파일을 확인하세요.")


def _detect_sep(header: str) -> str:
    # 탭이 있으면 TSV. 없으면 CSV.
    if "\t" in header:
        return "\t"
    return ","


def read_result(path: str | Path) -> pd.DataFrame:
    """por_doe_compare 결과 표. 헤더 앞 안내 문장은 버린다. 빈 칸은 결측."""
    path = Path(path)
    lines = _read_text(path).splitlines()
    skip = _header_index(lines)
    sep = _detect_sep(lines[skip])
    df = pd.read_csv(
        io.StringIO("\n".join(lines[skip:])),
        sep=sep,
        dtype=str,
        keep_default_na=False,
    )
    df.columns = [str(c).strip() for c in df.columns]
    if "ID" not in df.columns:
        raise ValueError(f"{path}: ID 열이 없습니다.")
    if "verdict" not in df.columns:
        raise ValueError(f"{path}: verdict 열이 없습니다.")
    df["ID"] = df["ID"].str.strip()
    df = df[df["ID"] != ""].copy()
    dup = df["ID"][df["ID"].duplicated()].tolist()
    if dup:
        raise ValueError(f"{path}: 중복 ID {dup[:5]}")
    for col in df.columns:
        if col in NUMERIC_COLS or MEAN_RE.match(col):
            df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce")
    if "reason" not in df.columns:
        df["reason"] = ""
    return df.reset_index(drop=True)


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(row, col: str) -> float:
    if col not in row.index and not (hasattr(row, "get") and col in getattr(row, "index", [])):
        try:
            value = row[col]
        except Exception:
            return math.nan
    else:
        value = row[col] if col in row.index else math.nan
    return float(value) if _finite(value) else math.nan


def por_cols(columns) -> list[str]:
    found = [c for c in columns if POR_RE.match(str(c))]
    return sorted(found, key=lambda c: int(POR_RE.match(c).group(1)))


def pct_of_median(num, den) -> float:
    if not (_finite(num) and _finite(den)) or float(den) == 0:
        return math.nan
    return 100.0 * float(num) / abs(float(den))


# ---------------------------------------------------------------- evidence

def median_out_distance(med: float, means: list[float]) -> float:
    """por_median이 회차 평균들의 [min, max] 밖으로 나간 거리. 안이면 0."""
    ok = [m for m in means if _finite(m)]
    if not ok or not _finite(med):
        return math.nan
    return max(0.0, min(ok) - med, med - max(ok))


def classify_group(verdict: str, por_gap_over_delta: float, median_out_over_delta: float) -> str:
    if verdict == J_DIFF:
        return J_DIFF
    if verdict != "미결":
        return verdict or ""
    gap_hit = _finite(por_gap_over_delta) and round(por_gap_over_delta, RATIO_DIGITS) >= POR_GAP_OVER_DELTA
    med_hit = _finite(median_out_over_delta) and round(median_out_over_delta, RATIO_DIGITS) >= MEDIAN_OUT_OVER_DELTA
    if gap_hit or med_hit:
        return J_BASE
    return J_OK


def judgment_text(row: pd.Series) -> str:
    group = row["group"]
    if group == J_DIFF:
        return "CI 전체가 ±Δ 밖"
    parts = []
    if group == J_BASE:
        if _finite(row["por_gap_over_delta"]) and round(row["por_gap_over_delta"], RATIO_DIGITS) >= POR_GAP_OVER_DELTA:
            parts.append(f"POR 회차 간격/Δ={row['por_gap_over_delta']:.2f} (≥{POR_GAP_OVER_DELTA:g})")
        if _finite(row["median_out_over_delta"]) and round(row["median_out_over_delta"], RATIO_DIGITS) >= MEDIAN_OUT_OVER_DELTA:
            parts.append(f"중앙값이 회차 평균 밖/Δ={row['median_out_over_delta']:.2f} (≥{MEDIAN_OUT_OVER_DELTA:g})")
        return "기준 조건 흔들림: " + "; ".join(parts) if parts else "기준 조건 흔들림"
    reason = str(row.get("reason") or "").strip()
    if "해상도" in reason:
        return "미결 · 해상도 부족 (CI 반폭 ≥ Δ)"
    if "경계" in reason:
        return "미결 · 경계 (CI가 ±Δ에 걸침)"
    return "미결 · 정상"


def evidence_table(df: pd.DataFrame) -> pd.DataFrame:
    pors = por_cols(df.columns)
    rows = []
    for _, r in df.iterrows():
        med = _num(r, "por_median")
        delta = _num(r, "delta")
        doe = _num(r, "DOE_mean")
        por_vals = [_num(r, c) for c in pors]
        por_ok = [v for v in por_vals if _finite(v)]
        if len(por_ok) >= 2:
            por_gap = max(por_ok) - min(por_ok)
            por_avg = sum(por_ok) / len(por_ok)
        elif len(por_ok) == 1:
            por_gap, por_avg = 0.0, por_ok[0]
        else:
            por_gap, por_avg = math.nan, math.nan
        all_means = por_ok + ([doe] if _finite(doe) else [])
        med_out = median_out_distance(med, all_means)
        gap_over_d = por_gap / delta if (_finite(por_gap) and _finite(delta) and delta != 0) else math.nan
        med_over_d = med_out / delta if (_finite(med_out) and _finite(delta) and delta != 0) else math.nan
        rec = {
            "ID": r["ID"],
            "verdict": str(r["verdict"]).strip(),
            "reason": r["reason"] if "reason" in r.index else "",
            "doe_pct": pct_of_median((doe - med) if (_finite(doe) and _finite(med)) else math.nan, med),
            "por_gap_pct": (100.0 * por_gap / abs(por_avg)) if (_finite(por_gap) and _finite(por_avg) and por_avg != 0) else math.nan,
            "center_over_delta": _num(r, "center") / delta if (_finite(_num(r, "center")) and _finite(delta) and delta != 0) else math.nan,
            "ci_low_over_delta": _num(r, "ci_low") / delta if (_finite(_num(r, "ci_low")) and _finite(delta) and delta != 0) else math.nan,
            "ci_high_over_delta": _num(r, "ci_high") / delta if (_finite(_num(r, "ci_high")) and _finite(delta) and delta != 0) else math.nan,
            "ci_halfwidth_over_delta": (
                (_num(r, "ci_high") - _num(r, "ci_low")) / 2.0 / delta
                if (_finite(_num(r, "ci_high")) and _finite(_num(r, "ci_low")) and _finite(delta) and delta != 0)
                else math.nan
            ),
            "loq_ratio": (abs(med) / _num(r, "LoQ")) if (_finite(med) and _finite(_num(r, "LoQ")) and _num(r, "LoQ") > 0) else math.nan,
            "sigma_die_pct": pct_of_median(_num(r, "sigma_die"), med),
            "sigma_run_pct": pct_of_median(_num(r, "sigma_run"), med),
            "delta_pct": pct_of_median(delta, med),
            "median_outside_runs": bool(_finite(med_out) and med_out > 0),
            "por_gap_over_delta": gap_over_d,
            "median_out_over_delta": med_over_d,
            "p1_pct": pct_of_median((_num(r, "POR1_mean") - med) if _finite(_num(r, "POR1_mean")) and _finite(med) else math.nan, med),
            "p2_pct": pct_of_median((_num(r, "POR2_mean") - med) if _finite(_num(r, "POR2_mean")) and _finite(med) else math.nan, med),
        }
        rec["group"] = classify_group(rec["verdict"], gap_over_d, med_over_d)
        rec["judgment"] = judgment_text(pd.Series(rec))
        rows.append(rec)
    out = pd.DataFrame(rows)
    out["_ord"] = out["group"].map({g: i for i, g in enumerate(GROUP_ORDER)}).fillna(99)
    out = out.sort_values(["_ord"], kind="mergesort").drop(columns=["_ord", "reason"], errors="ignore").reset_index(drop=True)
    return out


def plot_forest(ev: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.2, max(2.2, 0.28 * len(ev) + 0.8)), dpi=200)
    y = np.arange(len(ev))[::-1]
    ax.axvspan(-1, 1, color=BAND, zorder=0)
    for v in (-1, 1):
        ax.axvline(v, color=RED, lw=1, ls="--", zorder=1)
    for yy, (_, r) in zip(y, ev.iterrows()):
        c = GROUP_COLOR.get(r.group, GRAY)
        if _finite(r.ci_low_over_delta) and _finite(r.ci_high_over_delta):
            ax.plot([r.ci_low_over_delta, r.ci_high_over_delta], [yy, yy], color=c, lw=2.2, solid_capstyle="butt", zorder=2)
        if _finite(r.center_over_delta):
            ax.plot(r.center_over_delta, yy, "o", color=c, ms=5, mec="white", mew=0.6, zorder=3)
    ax.set_yticks(y, ev["ID"].tolist())
    for t, g in zip(ax.get_yticklabels(), ev["group"]):
        t.set_color(NAVY if g == J_DIFF else "#595959")
        t.set_fontweight("bold" if g == J_DIFF else "normal")
    ax.set_xlabel("차이 중앙값과 90% 신뢰구간 (Δ 단위)")
    ax.axvline(0, color="#BFBFBF", lw=0.6, zorder=1)
    handles = [Line2D([], [], color=GROUP_COLOR[k], lw=3, label=k) for k in GROUP_ORDER if (ev["group"] == k).any()]
    ax.legend(handles=handles, fontsize=8, frameon=False, loc="lower center",
              bbox_to_anchor=(0.5, 1.0), ncol=3, handlelength=1.1, columnspacing=0.9)
    fig.savefig(out_path, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def plot_strips(ev: pd.DataFrame, out_dir: Path) -> None:
    xl = 25
    for _, r in ev.iterrows():
        fig, ax = plt.subplots(figsize=(3.8, 0.32), dpi=200)
        fig.subplots_adjust(0, 0, 1, 1)
        if _finite(r.delta_pct):
            ax.axvspan(-r.delta_pct, r.delta_pct, color=BAND, zorder=0)
        ax.axvline(0, color="#BFBFBF", lw=0.6, zorder=1)
        for v, mk, c in ((r.get("p1_pct", math.nan), "o", GRAY),
                         (r.get("p2_pct", math.nan), "s", GRAY),
                         (r.doe_pct, "D", RED)):
            if not _finite(v):
                continue
            if abs(v) <= xl:
                ax.plot(v, 0, mk, color=c, ms=6, mec="white", mew=0.6, zorder=3)
            else:
                ax.plot(math.copysign(xl - 0.6, v), 0, ">" if v > 0 else "<", color=c, ms=6, zorder=3)
        ax.set_xlim(-xl, xl)
        ax.set_ylim(-1, 1)
        ax.axis("off")
        fig.savefig(out_dir / f"strip_{r.ID}.png", bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)


def run_evidence(result_path: str, out_dir: str) -> pd.DataFrame:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    configure_font()
    ev = evidence_table(read_result(result_path))
    ev[EVIDENCE_COLS].to_csv(out / "evidence.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
    plot_forest(ev, out / "forest.png")
    plot_strips(ev, out)
    counts = ev["group"].value_counts()
    lines = [
        "evidence 요약",
        f"입력: {result_path}",
        f"건수: {len(ev)}",
    ]
    for g in GROUP_ORDER:
        ids = ev.loc[ev["group"] == g, "ID"].tolist()
        lines.append(f"  {g}: {len(ids)}  " + (", ".join(ids) if ids else ""))
    extra = ev.loc[~ev["group"].isin(GROUP_ORDER), "group"]
    if len(extra):
        lines.append(f"  그 외: {extra.value_counts().to_dict()}")
    text = "\n".join(lines)
    (out / "summary.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    print(ev[EVIDENCE_COLS].to_string(index=False))
    return ev


# ---------------------------------------------------------------- compare

def rel_diff(a, b) -> float:
    """|a-b| / max(|a|, |b|). 둘 다 0이면 0, 한쪽만 결측이면 nan."""
    if not (_finite(a) and _finite(b)):
        return math.nan
    a, b = float(a), float(b)
    denom = max(abs(a), abs(b))
    if denom == 0:
        return 0.0
    return abs(a - b) / denom


def change_status(before, after) -> str:
    if not (_finite(before) and _finite(after)):
        return ""
    b, a = float(before), float(after)
    if b == 0 and a == 0:
        return "same 0"
    if a < b:
        return "lower"
    if a > b:
        return "higher"
    return "same"


def both_lower_flag(die_status: str, run_status: str) -> str:
    """둘 다 하락이면 yes. σ_die는 하락이고 σ_run이 0으로 같으면 'same 0'."""
    if die_status == "lower" and run_status == "lower":
        return "yes"
    if die_status == "lower" and run_status == "same 0":
        return "same 0"
    return "no"


def _side_metrics(row: pd.Series, side: str) -> dict:
    med = _num(row, "por_median")
    ci_w = (_num(row, "ci_high") - _num(row, "ci_low")) if (
        _finite(_num(row, "ci_high")) and _finite(_num(row, "ci_low"))
    ) else math.nan
    return {
        f"verdict_{side}": str(row["verdict"]).strip() if "verdict" in row.index else "",
        f"por_median_{side}": med,
        f"sigma_die_{side}": _num(row, "sigma_die"),
        f"sigma_run_{side}": _num(row, "sigma_run"),
        f"sigma_die_pct_{side}": pct_of_median(_num(row, "sigma_die"), med),
        f"sigma_run_pct_{side}": pct_of_median(_num(row, "sigma_run"), med),
        f"delta_pct_{side}": pct_of_median(_num(row, "delta"), med),
        f"ci_width_pct_{side}": pct_of_median(ci_w, med),
    }


def _empty_side(side: str) -> dict:
    keys = [
        f"verdict_{side}", f"por_median_{side}",
        f"sigma_die_{side}", f"sigma_run_{side}",
        f"sigma_die_pct_{side}", f"sigma_run_pct_{side}",
        f"delta_pct_{side}", f"ci_width_pct_{side}",
    ]
    out = {k: math.nan for k in keys}
    out[f"verdict_{side}"] = ""
    return out


def compare_tables(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    b = before.set_index("ID", drop=False)
    a = after.set_index("ID", drop=False)
    ids_b, ids_a = list(b.index), list(a.index)
    set_b, set_a = set(ids_b), set(ids_a)
    matched = [i for i in ids_b if i in set_a]
    only_b = [i for i in ids_b if i not in set_a]
    only_a = [i for i in ids_a if i not in set_b]
    rows = []

    def finish(rec: dict) -> dict:
        rec.setdefault("misaligned", False)
        rec.setdefault("por_median_rel_diff", math.nan)
        rec.setdefault("verdict_transition", "")
        rec.setdefault("both_lower", "")
        for stem in ("sigma_die_pct", "sigma_run_pct", "delta_pct", "ci_width_pct"):
            rec[f"{stem}_change"] = (
                rec[f"{stem}_after"] - rec[f"{stem}_before"]
                if _finite(rec.get(f"{stem}_before")) and _finite(rec.get(f"{stem}_after"))
                else math.nan
            )
        rec["sigma_die_status"] = change_status(rec.get("sigma_die_before"), rec.get("sigma_die_after"))
        rec["sigma_run_status"] = change_status(rec.get("sigma_run_before"), rec.get("sigma_run_after"))
        if rec["presence"] == "matched" and not rec["misaligned"]:
            rec["both_lower"] = both_lower_flag(rec["sigma_die_status"], rec["sigma_run_status"])
        return rec

    for i in matched:
        rec = {"ID": i, "presence": "matched"}
        rec.update(_side_metrics(b.loc[i], "before"))
        rec.update(_side_metrics(a.loc[i], "after"))
        rec["por_median_rel_diff"] = rel_diff(rec["por_median_before"], rec["por_median_after"])
        rec["misaligned"] = bool(_finite(rec["por_median_rel_diff"]) and rec["por_median_rel_diff"] > MEDIAN_MISALIGN)
        if rec["verdict_before"] or rec["verdict_after"]:
            rec["verdict_transition"] = f"{rec['verdict_before']}→{rec['verdict_after']}"
        rows.append(finish(rec))
    for i in only_b:
        rec = {"ID": i, "presence": "only_before"}
        rec.update(_side_metrics(b.loc[i], "before"))
        rec.update(_empty_side("after"))
        rows.append(finish(rec))
    for i in only_a:
        rec = {"ID": i, "presence": "only_after"}
        rec.update(_empty_side("before"))
        rec.update(_side_metrics(a.loc[i], "after"))
        rows.append(finish(rec))
    return pd.DataFrame(rows, columns=COMPARE_COLS)


def _valid_matched(cmp_df: pd.DataFrame) -> pd.DataFrame:
    return cmp_df[(cmp_df["presence"] == "matched") & (~cmp_df["misaligned"])].copy()


def compare_summary(cmp_df: pd.DataFrame, before_path: str, after_path: str) -> str:
    matched = cmp_df[cmp_df["presence"] == "matched"]
    only_b = cmp_df[cmp_df["presence"] == "only_before"]
    only_a = cmp_df[cmp_df["presence"] == "only_after"]
    suspect = matched[matched["misaligned"]]
    ok = _valid_matched(cmp_df)
    n_ok = len(ok)

    def n_status(col: str, status: str) -> int:
        return int((ok[col] == status).sum())

    die_lower = n_status("sigma_die_status", "lower")
    run_lower = n_status("sigma_run_status", "lower")
    both_yes = int((ok["both_lower"] == "yes").sum())
    both_same0 = int((ok["both_lower"] == "same 0").sum())
    run_same0 = n_status("sigma_run_status", "same 0")

    ratios = []
    for _, r in ok.iterrows():
        if _finite(r.sigma_die_before) and _finite(r.sigma_die_after) and float(r.sigma_die_before) != 0:
            ratios.append(float(r.sigma_die_after) / float(r.sigma_die_before))
    med_ratio = float(np.median(ratios)) if ratios else math.nan

    lines = [
        "compare_runs 비교 요약",
        f"기존: {before_path}",
        f"개선: {after_path}",
        "",
        "건수",
        f"- 공통 ID: {len(matched)}",
        f"- 기존에만: {len(only_b)}" + (f"  ({', '.join(only_b.ID)})" if len(only_b) else ""),
        f"- 개선에만: {len(only_a)}" + (f"  ({', '.join(only_a.ID)})" if len(only_a) else ""),
        (
            f"- 정렬 의심 (por_median 상대차 > {MEDIAN_MISALIGN:.0%}): {len(suspect)}"
            + (f"  ({', '.join(suspect.ID)})" if len(suspect) else "")
        ),
        "",
        f"σ 변화 (공통·정렬 정상 {n_ok}건)",
        f"- σ_die 하락: {die_lower}/{n_ok}",
        f"- σ_run 하락: {run_lower}/{n_ok}",
        f"- 둘 다 하락: {both_yes}",
        f"- σ_die 하락·σ_run 둘 다 0 (same 0): {both_same0}",
        f"- σ_run 둘 다 0: {run_same0}",
        f"- σ_die 중앙값 비 (개선/기존): {med_ratio:.6g}" if _finite(med_ratio) else "- σ_die 중앙값 비 (개선/기존): (해당 없음)",
        "",
        "판정 전이 (공통·정렬 정상)",
    ]
    if n_ok:
        trans = pd.crosstab(ok["verdict_before"], ok["verdict_after"], margins=True, margins_name="합계")
        lines.append(trans.to_string())
    else:
        lines.append("(해당 없음)")
    if len(suspect):
        lines += ["", "정렬 의심 상세"]
        for _, r in suspect.iterrows():
            lines.append(
                f"- {r.ID}: por_median 상대차 {r.por_median_rel_diff:.1%}  "
                f"({r.por_median_before:g} → {r.por_median_after:g})"
            )
    return "\n".join(lines) + "\n"


def _paired_plot(ok: pd.DataFrame, before_col: str, after_col: str, title: str, xlabel: str, path: Path) -> None:
    rows = []
    for _, r in ok.iterrows():
        if _finite(r[before_col]) or _finite(r[after_col]):
            rows.append(r)
    if not rows:
        return
    sub = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(5.4, max(2.0, 0.32 * len(sub) + 0.9)), dpi=200)
    y = np.arange(len(sub))[::-1]
    for yy, (_, r) in zip(y, sub.iterrows()):
        b, a = r[before_col], r[after_col]
        if _finite(b) and _finite(a):
            color = AFTER_COLOR if a < b else (WARN_COLOR if a > b else GRAY)
            ax.plot([b, a], [yy, yy], color=color, lw=1.4, zorder=2)
        if _finite(b):
            ax.plot(b, yy, "o", color=BEFORE_COLOR, ms=6, mec="white", mew=0.5, zorder=3)
        if _finite(a):
            ax.plot(a, yy, "o", color=AFTER_COLOR, ms=6, mec="white", mew=0.5, zorder=3)
    ax.set_yticks(y, sub["ID"].tolist())
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=10, loc="left", color="#404040")
    ax.legend(
        handles=[
            Line2D([], [], color=BEFORE_COLOR, marker="o", lw=0, label="기존"),
            Line2D([], [], color=AFTER_COLOR, marker="o", lw=0, label="개선"),
        ],
        frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2,
    )
    fig.savefig(path, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def _scatter_plot(ok: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.6), dpi=200)
    specs = (
        ("sigma_die_pct_before", "sigma_die_pct_after", "σ_die / |중앙값| (%)"),
        ("sigma_run_pct_before", "sigma_run_pct_after", "σ_run / |중앙값| (%)"),
    )
    for ax, (xb, xa, title) in zip(axes, specs):
        x = ok[xb].astype(float)
        y = ok[xa].astype(float)
        mask = x.map(_finite) & y.map(_finite)
        ax.scatter(x[mask], y[mask], s=28, color=AFTER_COLOR, zorder=3, edgecolors="white", linewidths=0.5)
        vals = pd.concat([x[mask], y[mask]])
        if len(vals):
            lo, hi = float(vals.min()), float(vals.max())
            pad = (hi - lo) * 0.1 if hi > lo else max(abs(hi), 1) * 0.1
            lo, hi = lo - pad, hi + pad
            ax.plot([lo, hi], [lo, hi], color="#BFBFBF", lw=1, ls="--", zorder=1, label="y = x")
            ax.set_xlim(lo, hi)
            ax.set_ylim(lo, hi)
        ax.set_xlabel("기존")
        ax.set_ylabel("개선")
        ax.set_title(title, fontsize=10, loc="left", color="#404040")
        ax.set_aspect("equal", adjustable="box")
        ax.legend(frameon=False, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def run_compare(before_path: str, after_path: str, out_dir: str) -> pd.DataFrame:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    configure_font()
    cmp_df = compare_tables(read_result(before_path), read_result(after_path))
    cmp_df.to_csv(out / "compare.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
    text = compare_summary(cmp_df, before_path, after_path)
    (out / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    ok = _valid_matched(cmp_df)
    _paired_plot(ok, "sigma_die_pct_before", "sigma_die_pct_after",
                 "ITEM별 σ_die (%)", "σ_die / |중앙값| (%)", out / "sigma_die_paired.png")
    _paired_plot(ok, "sigma_run_pct_before", "sigma_run_pct_after",
                 "ITEM별 σ_run (%)", "σ_run / |중앙값| (%)", out / "sigma_run_paired.png")
    _scatter_plot(ok, out / "scatter_before_after.png")
    return cmp_df


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POR/DOE 결과 근거 또는 기존·개선 비교")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ev = sub.add_parser("evidence", help="한 결과 파일의 ITEM별 근거")
    p_ev.add_argument("result")
    p_ev.add_argument("-o", required=True, dest="out")

    p_cmp = sub.add_parser("compare", help="기존·개선 결과 비교")
    p_cmp.add_argument("before")
    p_cmp.add_argument("after")
    p_cmp.add_argument("-o", required=True, dest="out")

    args = parser.parse_args(argv)
    if args.cmd == "evidence":
        run_evidence(args.result, args.out)
    else:
        run_compare(args.before, args.after, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
