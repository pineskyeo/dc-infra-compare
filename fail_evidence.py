"""Fail(차이·미결) ITEM별 근거를 규칙으로 계산해 CSV·차트·요약을 낸다.

입력은 por_doe_compare.py 결과 표(--out 폴더의 items.csv, 쉼표 구분) 또는 같은 열의 탭 구분 표이다.
    python fail_evidence.py --input <items.csv> --out <폴더> [--items ID,...]
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import rcParams  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

try:
    from plot_verdicts import configure_font
except ImportError:  # plot_verdicts가 없으면 DejaVu 그대로 쓴다.
    def configure_font(font_path: str | None = None) -> str | None:
        rcParams["axes.unicode_minus"] = False
        return None

# 내부 기준 (README 표와 맞춘다)
ITEM_AXIS_OVER_DELTA = 3.0     # ITEM 그림 x축 범위 = ±(이 값)·Δ%

TARGET_VERDICTS = ("차이", "미결")
J_DIFF = "차이"
# 미결은 나누지 않는다. 원인(조건 불안정, 회차 흔들림 등)은 items.csv status 열에서만 보고 여기서는 옮겨 적기만 한다.
J_PEND = "미결"
J_NA = "계산 불가"
J_SKIP = "대상 아님"
# por_doe_compare가 통계를 낼 수 없다고 판정한 ITEM. 근거 대상이 아니지만 '대상 아님'(동등 등)과 섞지 않는다.
J_EXCL = "판정 제외"
JUDGEMENT_ORDER = (J_DIFF, J_PEND, J_NA, J_EXCL, J_SKIP)
PLOT_ORDER = (J_DIFF, J_PEND)
JUDGEMENT_COLORS = {J_DIFF: "#d62728", J_PEND: "#1f77b4"}
MISMATCH_NOTE = "verdict와 다름"
GAP_DEF_PAIRED = "짝지은 회차 차"
GAP_DEF_OLD = "옛 정의(회차 평균 차)"

NUMERIC_COLUMNS = ("por_median", "DOE_mean", "center", "ci_low", "ci_high", "delta", "LoQ")
POR_MEAN_RE = re.compile(r"^POR(\d+)_mean$")
POR_PCT_RE = re.compile(r"^por(\d+)_pct$")
NAN = math.nan


# ---------------------------------------------------------------- 읽기

KEY_NAMES = ("ID", "ITEM")
RUN_MEAN_RE = re.compile(r"^.+_mean$")


def read_table(path: str | Path) -> pd.DataFrame:
    """결과 표를 읽는다. 탭·쉼표 구분 모두 받는다(por_doe_compare.py items.csv는 쉼표).

    ITEM 열을 키(내부 이름 ID)로 쓰고, 익명 ID 열이 같이 있으면 ANON_ID로 남긴다. POR1_mean이 없으면 DOE_mean을 뺀 '<이름>_mean' 열을
    나온 순서대로 POR1_mean, POR2_mean, ...으로 바꾼다.
    """
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline()
    sep = "\t" if header.count("\t") >= header.count(",") else ","
    df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [str(c).strip().strip('"') for c in df.columns]
    # 키는 실제 ITEM 이름이다. summarize.py가 넣은 익명 ID 열이 같이 있으면 ANON_ID로 따로 남긴다.
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
    if "POR1_mean" not in df.columns:
        runs = [c for c in df.columns if RUN_MEAN_RE.match(c) and c != "DOE_mean"]
        df = df.rename(columns={c: f"POR{k}_mean" for k, c in enumerate(runs, 1)})
    return df


def with_anon(table: pd.DataFrame, src: pd.DataFrame) -> pd.DataFrame:
    """출력용: 키(ID)를 ITEM 열로 쓰고, 익명 ID가 있으면 바로 옆 ID 열로 붙인다."""
    out = table.rename(columns={"ID": "ITEM"})
    if "ANON_ID" in src.columns:
        anon = {str(k).strip(): str(v).strip() for k, v in zip(src["ID"], src["ANON_ID"]) if str(v).strip()}
        if anon:
            out.insert(1, "ID", out["ITEM"].map(anon).fillna(""))
    return out


STATUS_COLUMNS = ("status", "status_detail", "mean_median_ratio")
JITTER_COLUMNS = ("run_jitter_pct", "run_jitter_over_delta", "spearman_size_jitter")
GAP_COLUMNS = ("por_gap_over_noise",)    # por_gap_over_delta는 이 파일이 따로 계산하는 열과 이름이 같아 복사하지 않음
PRECISION_COLUMNS = ("sigma_meas", "meas_precision_pct", "sigma_meas_over_delta")


def with_status(table: pd.DataFrame, src: pd.DataFrame) -> pd.DataFrame:
    """입력의 데이터 상태 열을 행 순서 그대로(값은 문자열 그대로) 끝에 붙인다. 입력에 없으면 빈 칸."""
    out = table.copy()
    for c in STATUS_COLUMNS + JITTER_COLUMNS + GAP_COLUMNS + PRECISION_COLUMNS:
        out[c] = src[c].tolist() if c in src.columns else ""
    return out


def parse_value(text) -> tuple[float | None, str | None]:
    """값과 문제(없으면 None)를 돌려준다. 빈칸='빈칸', 엑셀 넘침 등='숫자 아님'."""
    s = "" if text is None else str(text).strip()
    if not s:
        return None, "빈칸"
    try:
        v = float(s)
    except ValueError:
        return None, f"숫자 아님({s})"
    if not math.isfinite(v):
        return None, f"숫자 아님({s})"
    return v, None


def por_ks(columns) -> list[int]:
    return sorted(int(m.group(1)) for c in columns if (m := POR_MEAN_RE.match(str(c))))


def csv_columns(ks: list[int]) -> list[str]:
    return (["ID", "verdict", "judgement", "rule_hit", "doe_pct"]
            + [f"por{k}_pct" for k in ks]
            + ["por_gap_pct", "por_gap_over_delta", "por_gap_def", "median_out_over_delta", "delta_pct",
               "center_over_delta", "ci_low_over_delta", "ci_high_over_delta",
               "ci_half_over_delta", "loq_multiple", "note"])


# ---------------------------------------------------------------- 분류

def classify(ci_low: float, ci_high: float, delta: float) -> tuple[str, str]:
    """(judgement, rule_hit). CI 전체가 ±Δ 밖이면 차이, 아니면 미결."""
    if ci_high < -delta or ci_low > delta:
        return J_DIFF, "CI 전체가 ±Δ 밖"
    return J_PEND, "CI가 ±Δ 경계에 걸림"


# ---------------------------------------------------------------- 행 지표

def row_evidence(row: dict, ks: list[int], missing_cols: list[str]) -> dict:
    verdict = str(row.get("verdict", "")).strip()
    out = {c: NAN for c in csv_columns(ks)}
    out.update(ID=str(row.get("ID", "")).strip(), verdict=verdict, rule_hit="", note="", por_gap_def="")
    if verdict not in TARGET_VERDICTS:
        out["judgement"] = J_EXCL if verdict == J_EXCL else J_SKIP
        return out

    problems = [f"{c} 열 없음" for c in missing_cols]
    vals: dict[str, float] = {}
    for c in NUMERIC_COLUMNS:
        if c in missing_cols:
            continue
        v, p = parse_value(row.get(c))
        if p:
            problems.append(f"{c} {p}")
        else:
            vals[c] = v
    por: dict[int, float] = {}
    for k in ks:
        v, p = parse_value(row.get(f"POR{k}_mean"))
        if p == "빈칸":  # 회차가 없는 ITEM
            continue
        if p:
            problems.append(f"POR{k}_mean {p}")
        else:
            por[k] = v
    if len(por) < 2:
        problems.append(f"POR 회차 평균 {len(por)}개(2개 이상 필요)")
    if not problems and vals["delta"] <= 0:
        problems.append("delta <= 0")
    if problems:
        out.update(judgement=J_NA, note="계산 불가: " + ", ".join(problems))
        return out

    d, med, doe = vals["delta"], vals["por_median"], vals["DOE_mean"]
    means = list(por.values())
    paired, _ = parse_value(row.get("por_gap_over_delta"))
    if paired is not None:
        gap, gap_def = paired * d, GAP_DEF_PAIRED
    else:  # 예전 items.csv(열 없음) 또는 빈칸
        gap, gap_def = max(means) - min(means), GAP_DEF_OLD
    lo, hi = min(means + [doe]), max(means + [doe])
    median_out = max(0.0, lo - med, med - hi)
    mean_por = sum(means) / len(means)

    def pct(x: float) -> float:
        return (x - med) / abs(med) * 100 if med != 0 else NAN

    out["doe_pct"] = pct(doe)
    for k, v in por.items():
        out[f"por{k}_pct"] = pct(v)
    out["por_gap_pct"] = gap / abs(mean_por) * 100 if mean_por != 0 else NAN
    out["por_gap_over_delta"] = paired if paired is not None else gap / d
    out["por_gap_def"] = gap_def
    out["median_out_over_delta"] = median_out / d
    out["delta_pct"] = d / abs(med) * 100 if med != 0 else NAN
    out["center_over_delta"] = vals["center"] / d
    out["ci_low_over_delta"] = vals["ci_low"] / d
    out["ci_high_over_delta"] = vals["ci_high"] / d
    out["ci_half_over_delta"] = (vals["ci_high"] - vals["ci_low"]) / 2 / d
    out["loq_multiple"] = abs(med) / vals["LoQ"] if vals["LoQ"] > 0 else NAN

    judgement, hit = classify(vals["ci_low"], vals["ci_high"], d)
    notes = []
    if (verdict == J_DIFF) != (judgement == J_DIFF):
        notes.append(MISMATCH_NOTE)
    if med == 0:
        notes.append("por_median=0이라 % 계산 불가")
    if vals["LoQ"] <= 0:
        notes.append("LoQ <= 0")
    out.update(judgement=judgement, rule_hit=hit, note="; ".join(notes))
    return out


def evidence_table(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("ID", "verdict"):
        if c not in df.columns:
            raise ValueError(f"필수 열 '{c}'이 없습니다.")
    ks = por_ks(df.columns)
    missing = [c for c in NUMERIC_COLUMNS if c not in df.columns]
    records = [row_evidence(r, ks, missing) for r in df.to_dict("records")]
    return pd.DataFrame(records, columns=csv_columns(ks))


def old_gap_line(n: int) -> str:
    return f"por_gap: {GAP_DEF_OLD} {n}행 (items.csv에 {GAP_DEF_PAIRED} 열 없음)"


def summary_text(table: pd.DataFrame, input_name: str = "") -> str:
    counts = table["judgement"].value_counts()
    mismatch = int(table["note"].astype(str).str.contains(MISMATCH_NOTE).sum())
    lines = ["fail_evidence 요약"]
    if input_name:
        lines.append(f"입력: {input_name}")
    lines += [f"전체 행: {len(table)}", "", "판단별 개수:"]
    lines += [f"  {j}: {int(counts.get(j, 0))}" for j in JUDGEMENT_ORDER]
    lines += [f"  ({MISMATCH_NOTE}: {mismatch})", "", "사용 상수:",
              f"  ITEM_AXIS_OVER_DELTA = {ITEM_AXIS_OVER_DELTA:g}"]
    n_old = int((table["por_gap_def"] == GAP_DEF_OLD).sum()) if "por_gap_def" in table.columns else 0
    if n_old:
        lines.append(old_gap_line(n_old))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 그림

def _footnote(fig, text: str) -> None:
    fig.text(0.01, 0.01, text, fontsize=8, color="#555555", ha="left", va="bottom")


def plot_forest(table: pd.DataFrame, path: Path) -> Path:
    """ITEM별 center/Δ 점 + CI/Δ 막대, ±1 경계선. 정렬=차이→미결."""
    rank = {j: i for i, j in enumerate(PLOT_ORDER)}
    rows = table[table["judgement"].isin(PLOT_ORDER)].copy()
    rows = rows.iloc[rows["judgement"].map(rank).to_numpy().argsort(kind="stable")]
    n = len(rows)
    fig, ax = plt.subplots(figsize=(7.5, max(2.8, 0.32 * n + 1.8)))
    if n == 0:
        ax.text(0.5, 0.5, "표시할 ITEM 없음", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
    else:
        for i, r in enumerate(rows.to_dict("records")):
            color = JUDGEMENT_COLORS[r["judgement"]]
            ax.hlines(i, r["ci_low_over_delta"], r["ci_high_over_delta"],
                      color=color, lw=2.5, alpha=0.55)
            ax.plot(r["center_over_delta"], i, "o", color=color, ms=5)
        for x in (-1, 1):
            ax.axvline(x, color="#555555", ls="--", lw=1)
        ax.axvline(0, color="#999999", lw=0.8)
        ax.set_yticks(list(range(n)))
        ax.set_yticklabels(rows["ID"].astype(str).tolist(), fontsize=8)
        ax.set_ylim(n - 0.5, -0.5)
        span = rows[["ci_low_over_delta", "ci_high_over_delta", "center_over_delta"]].abs()
        xmax = max(1.5, float(span.max().max())) * 1.05
        ax.set_xlim(-xmax, xmax)
        counts = rows["judgement"].value_counts()
        handles = [Line2D([0], [0], color=JUDGEMENT_COLORS[j], marker="o", lw=2.5,
                          label=f"{j} ({counts[j]})") for j in PLOT_ORDER if j in counts]
        ax.legend(handles=handles, loc="best", fontsize=8)
        ax.set_xlabel("center/Δ (점), CI/Δ (막대)")
        ax.grid(axis="x", alpha=0.3)
    ax.set_title("Fail ITEM 근거: CI/Δ")
    n_na = int((table["judgement"] == J_NA).sum())
    n_excl = int((table["judgement"] == J_EXCL).sum())
    n_skip = int((table["judgement"] == J_SKIP).sum())
    _footnote(fig, f"점선 ±1 = Δ 경계. 제외: {J_NA} {n_na}행, {J_EXCL} {n_excl}행, {J_SKIP} {n_skip}행")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_item(rec: dict, path: Path, axis_over_delta: float = ITEM_AXIS_OVER_DELTA) -> Path:
    """0(=por_median) 기준선 위 POR 회차·DOE의 % 위치와 ±Δ% 띠. 축 밖 값은 화살표+숫자."""
    ks = sorted(int(m.group(1)) for c in rec if (m := POR_PCT_RE.match(str(c))))
    points = [(f"POR{k}", rec[f"por{k}_pct"], "#555555") for k in ks
              if isinstance(rec[f"por{k}_pct"], float) and math.isfinite(rec[f"por{k}_pct"])]
    points.append(("DOE", rec["doe_pct"], JUDGEMENT_COLORS.get(rec["judgement"], "#000000")))
    d = rec["delta_pct"]
    lim = axis_over_delta * d
    n = len(points)
    fig, ax = plt.subplots(figsize=(6.5, 0.45 * n + 1.9))
    ax.axvspan(-d, d, color="#cfe3f5", alpha=0.7, label=f"±Δ ({d:.3g}%)")
    ax.axvline(0, color="#333333", lw=1)
    for y, (_, v, color) in enumerate(points):
        if abs(v) <= lim:
            ax.plot(v, y, "o", color=color, ms=6)
            ax.annotate(f"{v:+.2f}%", (v, y), xytext=(0, 7), textcoords="offset points",
                        ha="center", fontsize=7, color=color)
        else:
            sign = 1 if v > 0 else -1
            ax.annotate(f"{v:+.1f}%", xy=(sign * lim * 0.98, y), xytext=(sign * lim * 0.6, y),
                        ha="center", va="center", fontsize=8, color=color,
                        arrowprops=dict(arrowstyle="->", color=color, lw=1.2))
    ax.set_yticks(list(range(n)))
    ax.set_yticklabels([p[0] for p in points])
    ax.set_ylim(n - 0.4, -0.6)
    ax.set_xlim(-lim, lim)
    ax.set_xlabel("por_median 대비 (%)")
    ax.set_title(f"{rec['ID']}  {rec['judgement']}  (verdict {rec['verdict']})", fontsize=10)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    _footnote(fig, f"{rec['rule_hit']} | por_gap/Δ={rec['por_gap_over_delta']:.3g}, "
                   f"median_out/Δ={rec['median_out_over_delta']:.3g}, "
                   f"center/Δ={rec['center_over_delta']:.3g}")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def safe_name(item_id: str) -> str:
    return re.sub(r"[^\w.-]", "_", str(item_id)) or "_"


# ---------------------------------------------------------------- CLI

OWN_OUTPUTS = ("fail_evidence.csv", "summary.txt", "forest.png", "items/*.png")


def remove_own_outputs(out: Path, patterns) -> None:
    """같은 --out에 다시 돌릴 때 지난 실행의 자기 출력 파일만 지운다(폴더·다른 파일은 그대로)."""
    for pat in patterns:
        for p in out.glob(pat):
            if p.is_file():
                p.unlink()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fail(차이·미결) ITEM별 근거를 규칙으로 계산한다.")
    p.add_argument("--input", required=True, help="por_doe_compare.py 결과 TSV")
    p.add_argument("--out", required=True, help="출력 폴더")
    p.add_argument("--items", default="", help="ITEM 그림을 그릴 ID 목록(쉼표 구분). 기본=전체")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        src = read_table(args.input)
        table = evidence_table(src)
    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    remove_own_outputs(out, OWN_OUTPUTS)
    with_status(with_anon(table, src), src).to_csv(out / "fail_evidence.csv", index=False, encoding="utf-8-sig")
    summary = summary_text(table, Path(args.input).name)
    (out / "summary.txt").write_text(summary, encoding="utf-8")

    configure_font()
    rcParams["axes.unicode_minus"] = False
    plot_forest(table, out / "forest.png")

    plottable = table[table["judgement"].isin(PLOT_ORDER)]
    wanted = [s.strip() for s in args.items.split(",") if s.strip()]
    if wanted:
        unknown = sorted(set(wanted) - set(plottable["ID"]))
        if unknown:
            print(f"그림 대상이 아니거나 없는 ID: {', '.join(unknown)}")
        plottable = plottable[plottable["ID"].isin(wanted)]
    items_dir = out / "items"
    items_dir.mkdir(exist_ok=True)
    for rec in plottable.to_dict("records"):
        if not math.isfinite(rec["delta_pct"]):
            print(f"{rec['ID']}: por_median=0이라 ITEM 그림 생략")
            continue
        plot_item(rec, items_dir / f"{safe_name(rec['ID'])}.png")

    print(summary, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
