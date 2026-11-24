#!/usr/bin/env python3
"""por_doe_compare.py 결과 표를 읽어 ITEM별 근거를 내거나, 기존·개선 두 표를 ID로 맞춰 비교한다.

사용:
  python3 compare_before_after.py evidence RESULT.tsv -o OUTDIR
  python3 compare_before_after.py compare BEFORE.tsv AFTER.tsv -o OUTDIR [--groups ITEM,그룹 파일]

compare 는 두 결과 모두에 있는 ITEM 만 비교한다. --groups 를 주면 그룹 파일에 있는 ITEM 만 (나머지는 개수만 센다).
  compare.csv          비교한 ITEM 마다 한 행 (--groups 면 group 열)
  scope.csv            무엇을 비교했나: 결과마다 ITEM 수, 한쪽에만 있는 수, 그룹 파일에 없어 뺀 수 등 한 행
  overview.csv         요약 지표 (측정 정밀도, 반복성, 회차 이동, 90% 구간 폭, 동등 아닌 수) 마다 기존·개선·비·판단
  group_levels.csv     --groups 이고 두 결과 폴더에 stability/group_levels.csv 가 있을 때: 그룹 × LEVEL 측정 정밀도
  summary.txt, stability_overall.csv, worst_items.csv, 지표 그림 (compare_metrics.METRICS)

입력은 탭 또는 쉼표 구분. 헤더는 ID로 시작하는 줄. reason 열은 없어도 되고, 추가 열은 무시한다.
"""
from __future__ import annotations

import argparse
import io
from dataclasses import asdict, dataclass
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

import compare_metrics  # noqa: E402
import group_summary  # noqa: E402
from fail_evidence import J_DIFF, J_PEND, remove_own_outputs  # noqa: E402  (fail_evidence와 같은 차이/미결 이름)
from infra_compare import group_lookup, read_groups  # noqa: E402
from por_doe_compare import V_EXCLUDED  # noqa: E402

# ---------------------------------------------------------------------------
# 분류·정렬 상수. group은 verdict를 그대로 따른다(차이/미결). 미결은 나누지 않고,
# 원인(조건 불안정, 회차 흔들림 등)은 items.csv status 열을 참고 열로 옮겨 적기만 한다.
# ---------------------------------------------------------------------------
MEDIAN_MISALIGN = 0.20  # 같은 ID인데 |por_median| 상대차가 이 값을 넘으면 정렬 의심

GROUP_ORDER = (J_DIFF, J_PEND)

NAVY, LIGHT, GRAY, RED, BAND = (
    "#3D4C61", "#9AA8BC", "#7F8C9F", "#B5523B", "#E1E6ED",
)
GROUP_COLOR = {J_DIFF: NAVY, J_PEND: LIGHT}
BEFORE_COLOR, AFTER_COLOR, WARN_COLOR = "#7F8C9F", "#3D4C61", "#B5523B"

NUMERIC_COLS = frozenset((
    "n_die", "por_median", "center", "ci_low", "ci_high", "delta",
    "policy_margin", "run_margin", "sigma_die", "sigma_run", "LoQ", "LoD",
    "meas_precision_pct",
))
MEAN_RE = re.compile(r"^.+_mean$")
KEY_NAMES = ("ID", "ITEM")
POR_RE = re.compile(r"^POR(\d+)_mean$")

# 비교 CSV 열 순서
COMPARE_COLS = [
    "ID", "presence", "misaligned", "por_median_rel_diff",
    "verdict_before", "verdict_after", "verdict_transition",
    "sigma_die_pct_before", "sigma_die_pct_after", "sigma_die_pct_change", "sigma_die_status",
    "sigma_run_pct_before", "sigma_run_pct_after", "sigma_run_pct_change", "sigma_run_status",
    "meas_precision_pct_before", "meas_precision_pct_after", "meas_precision_pct_change", "meas_precision_status",
    "delta_pct_before", "delta_pct_after", "delta_pct_change",
    "ci_width_pct_before", "ci_width_pct_after", "ci_width_pct_change",
    "both_lower",
    "por_median_before", "por_median_after",
    "sigma_die_before", "sigma_die_after",
    "sigma_run_before", "sigma_run_after",
    "center_delta_before", "center_delta_after",
]

EVIDENCE_COLS = [
    "ID", "verdict", "group", "doe_pct", "por_gap_pct",
    "center_over_delta", "ci_low_over_delta", "ci_high_over_delta",
    "ci_halfwidth_over_delta", "loq_ratio",
    "sigma_die_pct", "meas_precision_pct", "sigma_run_pct", "delta_pct",
    "median_outside_runs", "por_gap_over_delta", "por_gap_def", "median_out_over_delta",
    "status", "judgment",
]
GAP_DEF_PAIRED = "짝지은 회차 차"
GAP_DEF_OLD = "옛 정의(회차 평균 차)"

# 실행 시작 때 지우는 자기 그림(--out 기준 glob). 개수가 바뀌거나 건너뛸 수 있는 그림이 남지 않게 한다.
OWN_OUTPUTS = {
    "evidence": ("forest.png", "strip_*.png"),
    "compare": (
        *(f"{name}.png" for name in compare_metrics.METRICS),
        "stability_overall.csv", "worst_items.csv", "overview.csv", "scope.csv", "group_levels.csv",
        # 예전 이름: 재실행 때 옛 결과도 지운다
        "sigma_die_paired.png", "sigma_run_paired.png", "scatter_before_after.png",
    ),
}


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
        first = re.split(r"[\t,]", line.lstrip("\ufeff"), maxsplit=1)[0].strip().strip('"').upper()
        if first in KEY_NAMES:
            return i
    raise ValueError("ITEM 또는 ID로 시작하는 헤더 줄이 없습니다: por_doe_compare.py의 items.csv인지 확인하세요.")


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
    df.columns = [str(c).strip().strip('"') for c in df.columns]
    # 비교 키는 실제 ITEM 이름이다. summarize.py가 넣은 익명 ID 열이 같이 있으면 ANON_ID로 따로 남긴다.
    item_col = next((c for c in df.columns if c.upper() == "ITEM"), None)
    if item_col is not None:
        if "ID" in df.columns:
            df = df.rename(columns={"ID": "ANON_ID"})
        df = df.rename(columns={item_col: "ID"})
    elif "ID" not in df.columns:
        for c in df.columns:
            if c.upper() in KEY_NAMES:
                df = df.rename(columns={c: "ID"})
                break
    # 회차 평균 열 이름은 POR 입력 이름을 따른다(<이름>_mean). POR1_mean/POR2_mean이 없으면 순서대로 붙인다.
    if "POR1_mean" not in df.columns:
        runs = [c for c in df.columns if MEAN_RE.match(c) and c != "DOE_mean"]
        df = df.rename(columns={c: f"POR{k}_mean" for k, c in enumerate(runs[:2], 1)})
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


def meas_precision_pct(row) -> float:
    """측정 정밀도 % (낮을수록 좋음). items.csv에 meas_precision_pct 열이 있으면 그 값,
    없으면(예전 결과) 100 × sqrt(σ_die² + σ_run²) / |por_median|."""
    if "meas_precision_pct" in row.index:
        return _num(row, "meas_precision_pct")
    die, run = _num(row, "sigma_die"), _num(row, "sigma_run")
    if not (_finite(die) and _finite(run)):
        return math.nan
    return pct_of_median(math.hypot(die, run), _num(row, "por_median"))


# ---------------------------------------------------------------- evidence

def median_out_distance(med: float, means: list[float]) -> float:
    """por_median이 회차 평균들의 [min, max] 밖으로 나간 거리. 안이면 0."""
    ok = [m for m in means if _finite(m)]
    if not ok or not _finite(med):
        return math.nan
    return max(0.0, min(ok) - med, med - max(ok))


def classify_group(verdict: str) -> str:
    """verdict 그대로: 차이, 미결, 그 밖(판정 제외·동등 등)은 verdict 문자열."""
    return verdict or ""


def judgment_text(row: pd.Series) -> str:
    group = row["group"]
    if group == J_DIFF:
        text = "CI 전체가 ±Δ 밖"
    else:
        reason = str(row.get("reason") or "").strip()
        if "해상도" in reason:
            text = "미결 · 해상도 부족 (CI 반폭 ≥ Δ)"
        elif "경계" in reason:
            text = "미결 · 경계 (CI가 ±Δ에 걸침)"
        else:
            text = group
    status = str(row.get("status") or "").strip()
    if status and status != "정상":
        text += f" · 원인(status): {status}"
    return text


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
        paired = _num(r, "por_gap_over_delta")  # items.csv의 짝지은 회차 차/Δ. 열이 없거나 빈칸이면 nan
        if _finite(paired):
            gap_over_d, gap_def = paired, GAP_DEF_PAIRED
            por_gap = paired * delta if _finite(delta) else math.nan
        else:
            gap_over_d = por_gap / delta if (_finite(por_gap) and _finite(delta) and delta != 0) else math.nan
            gap_def = GAP_DEF_OLD
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
            "meas_precision_pct": meas_precision_pct(r),
            "sigma_run_pct": pct_of_median(_num(r, "sigma_run"), med),
            "delta_pct": pct_of_median(delta, med),
            "median_outside_runs": bool(_finite(med_out) and med_out > 0),
            "por_gap_over_delta": gap_over_d,
            "por_gap_def": gap_def,
            "median_out_over_delta": med_over_d,
            "status": str(r["status"]) if "status" in r.index else "",  # 참고 열: items.csv 문자열 그대로
            "p1_pct": pct_of_median((_num(r, "POR1_mean") - med) if _finite(_num(r, "POR1_mean")) and _finite(med) else math.nan, med),
            "p2_pct": pct_of_median((_num(r, "POR2_mean") - med) if _finite(_num(r, "POR2_mean")) and _finite(med) else math.nan, med),
        }
        rec["group"] = classify_group(rec["verdict"])
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
    remove_own_outputs(out, OWN_OUTPUTS["evidence"])
    configure_font()
    df_src = read_result(result_path)
    ev = evidence_table(df_src)
    _with_anon(ev[EVIDENCE_COLS], df_src).to_csv(out / "evidence.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
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
    n_old = int((ev["por_gap_def"] == GAP_DEF_OLD).sum())
    if n_old:
        lines.append(f"por_gap: {GAP_DEF_OLD} {n_old}행 (items.csv에 {GAP_DEF_PAIRED} 열 없음)")
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
        f"verdict_{side}": str(row["verdict_final" if "verdict_final" in row.index else "verdict"]).strip(),
        f"por_median_{side}": med,
        f"sigma_die_{side}": _num(row, "sigma_die"),
        f"sigma_run_{side}": _num(row, "sigma_run"),
        f"sigma_die_pct_{side}": pct_of_median(_num(row, "sigma_die"), med),
        f"sigma_run_pct_{side}": pct_of_median(_num(row, "sigma_run"), med),
        f"meas_precision_pct_{side}": meas_precision_pct(row),
        f"delta_pct_{side}": pct_of_median(_num(row, "delta"), med),
        f"ci_width_pct_{side}": pct_of_median(ci_w, med),
        f"center_delta_{side}": _center_over_delta(row),
    }


def _center_over_delta(row: pd.Series) -> float:
    """center / delta. center 열이 없거나 delta 가 0 이하·NaN 이면 NaN."""
    center, delta = _num(row, "center"), _num(row, "delta")
    if not (_finite(center) and _finite(delta)) or delta <= 0:
        return math.nan
    return center / delta


def _empty_side(side: str) -> dict:
    keys = [
        f"verdict_{side}", f"por_median_{side}",
        f"sigma_die_{side}", f"sigma_run_{side}",
        f"sigma_die_pct_{side}", f"sigma_run_pct_{side}",
        f"meas_precision_pct_{side}",
        f"delta_pct_{side}", f"ci_width_pct_{side}",
        f"center_delta_{side}",
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
        for stem in ("sigma_die_pct", "sigma_run_pct", "meas_precision_pct", "delta_pct", "ci_width_pct"):
            rec[f"{stem}_change"] = (
                rec[f"{stem}_after"] - rec[f"{stem}_before"]
                if _finite(rec.get(f"{stem}_before")) and _finite(rec.get(f"{stem}_after"))
                else math.nan
            )
        rec["sigma_die_status"] = change_status(rec.get("sigma_die_before"), rec.get("sigma_die_after"))
        rec["sigma_run_status"] = change_status(rec.get("sigma_run_before"), rec.get("sigma_run_after"))
        rec["meas_precision_status"] = change_status(
            rec.get("meas_precision_pct_before"), rec.get("meas_precision_pct_after"))
        if rec["presence"] == "matched" and (INCLUDE_MISALIGNED or not rec["misaligned"]):
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


# 기본: 정렬 의심(POR 중앙값이 크게 움직인 ITEM)도 비교에 포함한다. --exclude-misaligned 로 뺄 수 있다.
INCLUDE_MISALIGNED = True


def _scope_matched(cmp_df: pd.DataFrame) -> pd.DataFrame:
    """공통 ID (정렬 의심은 INCLUDE_MISALIGNED에 따라). 판정 제외도 포함 — 판정 전이 표용."""
    if INCLUDE_MISALIGNED:
        return cmp_df[cmp_df["presence"] == "matched"].copy()
    return cmp_df[(cmp_df["presence"] == "matched") & (~cmp_df["misaligned"])].copy()


def _is_excluded(df: pd.DataFrame) -> pd.Series:
    """기존 또는 개선 verdict가 '판정 제외'인 행."""
    return df["verdict_before"].eq(V_EXCLUDED) | df["verdict_after"].eq(V_EXCLUDED)


def _valid_matched(cmp_df: pd.DataFrame) -> pd.DataFrame:
    """σ 집계·그림 대상: _scope_matched에서 판정 제외(기존 또는 개선) 행을 뺀 것."""
    scope = _scope_matched(cmp_df)
    return scope[~_is_excluded(scope)].copy()


def _id_list(ids, limit: int = 10) -> str:
    ids = list(ids)
    text = ", ".join(ids[:limit])
    return text + (f" 외 {len(ids) - limit}개" if len(ids) > limit else "")


def _scope_label() -> str:
    return "공통 전체, 정렬 의심 포함" if INCLUDE_MISALIGNED else "공통·정렬 정상"


@dataclass(frozen=True)
class Scope:
    """무엇을 비교했나 (scope.csv 한 행). 비교 = 두 결과 모두에 있고, 그룹 파일을 주면 거기에도 있는 ITEM."""
    n_before: int
    n_after: int
    n_matched: int
    n_only_before: int
    n_only_after: int
    grouped: bool
    n_ungrouped: int
    n_compared: int
    n_misaligned: int
    misaligned_included: bool
    n_verdict_excluded: int
    n_used: int


def scope_rows(cmp_df: pd.DataFrame, groups: pd.DataFrame | None) -> tuple[pd.DataFrame, Scope]:
    """비교할 행만 (공통 ITEM, 그룹 파일을 주면 그룹이 있는 ITEM) 과 그 범위. 그룹이 있으면 group 열을 붙인다."""
    presence = cmp_df["presence"]
    rows = cmp_df[presence == "matched"].copy()
    n_matched = len(rows)
    if groups is not None:
        rows["group"] = group_lookup(rows["ID"], groups)
        rows = rows[rows["group"].notna()].copy()
    scope_m = _scope_matched(rows)
    excluded = int(_is_excluded(scope_m).sum())
    return rows, Scope(
        n_before=int((presence != "only_after").sum()), n_after=int((presence != "only_before").sum()),
        n_matched=n_matched, n_only_before=int((presence == "only_before").sum()),
        n_only_after=int((presence == "only_after").sum()), grouped=groups is not None,
        n_ungrouped=n_matched - len(rows), n_compared=len(rows), n_misaligned=int(rows["misaligned"].sum()),
        misaligned_included=INCLUDE_MISALIGNED, n_verdict_excluded=excluded, n_used=len(scope_m) - excluded)


def compare_summary(cmp_df: pd.DataFrame, rows: pd.DataFrame, scope: Scope, before_path: str,
                    after_path: str) -> str:
    """cmp_df 는 두 결과를 맞춘 전체 표 (한쪽에만 있는 ITEM 이름용), rows 는 scope_rows 가 고른 비교 행."""
    only_b = cmp_df[cmp_df["presence"] == "only_before"]
    only_a = cmp_df[cmp_df["presence"] == "only_after"]
    suspect = rows[rows["misaligned"]]
    in_scope = _scope_matched(rows)
    excluded = in_scope[_is_excluded(in_scope)]
    ok = _valid_matched(rows)
    n_ok = len(ok)

    def n_status(col: str, status: str) -> int:
        return int((ok[col] == status).sum())

    die_lower = n_status("sigma_die_status", "lower")
    run_lower = n_status("sigma_run_status", "lower")
    prec_lower = n_status("meas_precision_status", "lower")
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
        f"- 공통 ID: {scope.n_matched}",
        f"- 기존에만: {len(only_b)}" + (f"  ({_id_list(only_b.ID)})" if len(only_b) else ""),
        f"- 개선에만: {len(only_a)}" + (f"  ({_id_list(only_a.ID)})" if len(only_a) else ""),
        *([f"- 그룹 파일에 없음 (비교에서 뺌): {scope.n_ungrouped}", f"- 비교: {scope.n_compared}"]
          if scope.grouped else []),
        (
            f"- 정렬 의심 (por_median 상대차 > {MEDIAN_MISALIGN:.0%}): {len(suspect)}"
            + (f"  ({', '.join(suspect.ID)})" if len(suspect) else "")
        ),
    ]
    if len(excluded):
        lines.append(
            f"- {V_EXCLUDED} (기존 또는 개선, σ 집계에서 뺌): {len(excluded)}  ({_id_list(excluded.ID)})"
        )
    lines += [
        "",
        f"σ 변화 ({_scope_label()} {n_ok}건)",
        f"- σ_die 하락: {die_lower}/{n_ok}",
        f"- σ_run 하락: {run_lower}/{n_ok}",
        f"- 둘 다 하락: {both_yes}",
        f"- σ_die 하락·σ_run 둘 다 0 (same 0): {both_same0}",
        f"- σ_run 둘 다 0: {run_same0}",
        f"- 측정정밀도% 하락 (낮을수록 좋음): {prec_lower}/{n_ok}",
        f"- σ_die 중앙값 비 (개선/기존): {med_ratio:.6g}" if _finite(med_ratio) else "- σ_die 중앙값 비 (개선/기존): (해당 없음)",
        "",
        f"판정 전이 ({_scope_label()})",
    ]
    if len(in_scope):  # 판정 제외도 남겨 '동등→판정 제외' 같은 전이가 보이게
        trans = pd.crosstab(in_scope["verdict_before"], in_scope["verdict_after"], margins=True, margins_name="합계")
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


def _write_metric_tables(d: pd.DataFrame, out: Path, top: int) -> None:
    """stability_overall.csv (전체 한 행)와 worst_items.csv (지표별 악화 상위 top)."""
    if d["sigma_die_pct_before"].isna().all() and d["sigma_die_pct_after"].isna().all():
        print("stability_overall.csv 건너뜀: σ_die % 값이 기존·개선 모두 없음")
    else:
        pd.DataFrame([{"그룹": "전체", **compare_metrics.stability_row(d)}]).to_csv(
            out / "stability_overall.csv", index=False, encoding="utf-8-sig")
    parts = [
        compare_metrics.worst_items(d, m, top).assign(metric=m)
        for m in compare_metrics.METRIC_RATIO
    ]
    worst = pd.concat(parts, ignore_index=True)[["metric", "ID", "before", "after", "ratio"]].rename(columns={"ID": "ITEM"})
    worst.to_csv(out / "worst_items.csv", index=False, encoding="utf-8-sig", float_format="%.10g")


def _with_anon(df: pd.DataFrame, *sources: pd.DataFrame) -> pd.DataFrame:
    """출력용: 키(ID)를 ITEM 이름으로 쓰고, 익명 ID가 있으면 바로 옆 ID 열로 붙인다."""
    out = df.rename(columns={"ID": "ITEM"})
    anon = {}
    for src in sources:
        if "ANON_ID" in src.columns:
            for k, v in zip(src["ID"], src["ANON_ID"]):
                if str(v).strip():
                    anon.setdefault(k, str(v).strip())
    if anon:
        out.insert(1, "ID", out["ITEM"].map(anon).fillna(""))
    return out


def group_levels(before_path: str | Path, after_path: str | Path, groups: pd.DataFrame) -> pd.DataFrame | None:
    """두 결과 폴더의 stability/group_levels.csv 를 (그룹, LEVEL) 로 맞춘 측정 정밀도 중앙값 표.
    둘 중 하나라도 없으면 None. 그룹 파일에 없는 그룹(미지정 포함)은 뺀다."""
    paths = [Path(p).parent / "stability" / "group_levels.csv" for p in (before_path, after_path)]
    if not all(p.is_file() for p in paths):
        return None
    col = "meas_precision_pct_median"
    b, a = (pd.read_csv(p, encoding="utf-8-sig", dtype={"group": str, "level": str})[["group", "level", "n_items", col]]
            for p in paths)
    t = b.merge(a, on=["group", "level"], suffixes=("_before", "_after"))
    t = t[t["group"].isin(set(groups["group"]))]
    t = t.rename(columns={f"{col}_before": "before", f"{col}_after": "after"})
    t["ratio"] = (t["after"] / t["before"]).where(t["before"] > 0)
    return t[["group", "level", "n_items_before", "n_items_after", "before", "after", "ratio"]].reset_index(drop=True)


def run_compare(before_path: str, after_path: str, out_dir: str, plot_top: int = 10,
                groups_path: str | None = None) -> pd.DataFrame:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    remove_own_outputs(out, OWN_OUTPUTS["compare"])
    configure_font()
    groups = read_groups(groups_path) if groups_path else None
    if groups is None:      # 지난 실행의 그룹 요약이 이번 결과처럼 보이지 않게
        stale = out / group_summary.OUT_DIR
        group_summary.remove_own_outputs(stale, group_summary.OWN_OUTPUTS)
        if stale.is_dir() and not any(stale.iterdir()):
            stale.rmdir()
    before, after = read_result(before_path), read_result(after_path)
    cmp_df = compare_tables(before, after)
    rows, scope = scope_rows(cmp_df, groups)
    rows = compare_metrics.with_ratios(rows)
    table = _with_anon(rows.drop(columns="presence"), before, after)
    if groups is not None:
        table.insert(2 if "ID" in table.columns[:2] else 1, "group", table.pop("group"))
    table.to_csv(out / "compare.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
    pd.DataFrame([asdict(scope)]).to_csv(out / "scope.csv", index=False, encoding="utf-8-sig")
    text = compare_summary(cmp_df, rows, scope, before_path, after_path)
    (out / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    d = compare_metrics.with_pct(_valid_matched(rows))
    compare_metrics.kpi_table(d).to_csv(out / "overview.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
    compare_metrics.draw_all(d, out, top=plot_top)
    _write_metric_tables(d, out, plot_top)
    if groups is not None:
        levels = group_levels(before_path, after_path, groups)
        if levels is None:
            print("group_levels.csv 건너뜀: 기존·개선 결과 폴더 둘 다 stability/group_levels.csv 가 있어야 함")
        else:
            levels.to_csv(out / "group_levels.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
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
    p_cmp.add_argument("--exclude-misaligned", action="store_true",
                       help="정렬 의심(POR 중앙값 상대차 > 20%%) ITEM을 비교에서 뺀다 (기본: 포함)")
    p_cmp.add_argument("--plot-top", type=int, default=10,
                       help="지표별 그림의 악화 상위 표에 ITEM N개 (기본 10)")
    p_cmp.add_argument("--groups", help="ITEM,그룹 파일. 주면 그룹 파일에 있는 ITEM 만 비교하고 compare.csv 에 group 열")

    args = parser.parse_args(argv)
    if args.cmd == "compare" and args.plot_top < 1:
        parser.error("--plot-top 은 1 이상이어야 합니다")
    global INCLUDE_MISALIGNED
    INCLUDE_MISALIGNED = not getattr(args, "exclude_misaligned", False)
    if args.cmd == "evidence":
        run_evidence(args.result, args.out)
    else:
        run_compare(args.before, args.after, args.out, plot_top=args.plot_top, groups_path=args.groups)
    return 0


if __name__ == "__main__":
    sys.exit(main())
