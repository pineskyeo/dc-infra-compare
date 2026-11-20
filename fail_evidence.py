"""Fail(차이·미결) ITEM별 근거를 규칙으로 계산해 CSV·차트·요약을 내고, ITEM마다 items/<유형>_<ID>/ 폴더를 만든다.

입력은 por_doe_compare.py 결과 표(--out 폴더의 items.csv, 쉼표 구분) 또는 같은 열의 탭 구분 표이다.
    python fail_evidence.py --input <items.csv> --out <폴더> [--items ID ...] [--compare <compare.csv>]
        [--por <회차1> --por <회차2> ... --doe <DOE> [--blank ...] [--blank-map ...] [--key ...] [--encoding ...]]
원데이터 인자(--por, --doe 등)는 por_doe_compare.py 와 같고, 주면 ITEM 폴더에 raw.csv(die별 값)를 더 쓴다.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import rcParams  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from compare_metrics import safe_group_name  # noqa: E402
from por_doe_compare import (  # noqa: E402
    ST_FLAT, ST_OK, ST_RESOLUTION, ST_RUN_JITTER, ST_SETUP_ERROR, ST_SIZE_JITTER, ST_UNSTABLE,
    add_common_args, load_blank, load_wide, read_csv_auto,
)

try:
    from plot_verdicts import configure_font
except ImportError:  # plot_verdicts가 없으면 DejaVu 그대로 쓴다.
    def configure_font(font_path: str | None = None) -> str | None:
        rcParams["axes.unicode_minus"] = False
        return None

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
NAN = math.nan


# ---------------------------------------------------------------- 읽기

KEY_NAMES = ("ID", "ITEM")
RUN_MEAN_RE = re.compile(r"^.+_mean$")


def read_plain(path: str | Path) -> pd.DataFrame:
    """표를 열 이름·값(문자열) 그대로 읽는다. 탭·쉼표 구분 모두 받는다."""
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline()
    sep = "\t" if header.count("\t") >= header.count(",") else ","
    df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [str(c).strip().strip('"') for c in df.columns]
    return df


def key_column(df: pd.DataFrame) -> str:
    """ITEM 이름이 든 열. ITEM 열이 없으면 ID 열(예전 표)."""
    for want in ("ITEM", "ID"):
        col = next((c for c in df.columns if c.upper() == want), None)
        if col is not None:
            return col
    raise ValueError("ITEM 열이 없습니다.")


def read_table(path: str | Path) -> pd.DataFrame:
    """결과 표를 읽는다. 탭·쉼표 구분 모두 받는다(por_doe_compare.py items.csv는 쉼표).

    ITEM 열을 키(내부 이름 ID)로 쓰고, 익명 ID 열이 같이 있으면 ANON_ID로 남긴다. POR1_mean이 없으면 DOE_mean을 뺀 '<이름>_mean' 열을
    나온 순서대로 POR1_mean, POR2_mean, ...으로 바꾼다.
    """
    df = read_plain(path)
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
    lines.append(f"  ({MISMATCH_NOTE}: {mismatch})")
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


# ---------------------------------------------------------------- ITEM별 폴더

ITEMS_DIR = "items"
ITEMS_MARKER = ".fail_evidence_items"
ITEMS_INDEX = "items_index.csv"
INDEX_COLUMNS = ("ID", "유형", "verdict", "status", "폴더")
CMP_PREFIX = "cmp_"
NO_RAW_MSG = "원데이터 없음: raw.csv·drill.png 건너뜀"
# 대표 status(폴더 <유형>): 여러 status가 ';'로 붙어 있으면 이 표에서 앞에 있는 것. 표에 없는 이름은 맨 뒤(나온 순서).
STATUS_PRIORITY = (ST_SETUP_ERROR, ST_UNSTABLE, ST_FLAT, ST_RESOLUTION, ST_RUN_JITTER, ST_SIZE_JITTER)


def item_type(status: str, verdict: str) -> str:
    """대표 status. status가 비었거나 정상이면 verdict."""
    names = [s.strip() for s in str(status).split(";") if s.strip() and s.strip() != ST_OK]
    if not names:
        return verdict
    rank = {s: i for i, s in enumerate(STATUS_PRIORITY)}
    return min(names, key=lambda s: rank.get(s, len(rank)))


def select_items(plain: pd.DataFrame, extra: list[str]) -> tuple[list[str], list[str]]:
    """폴더를 만들 ITEM(verdict 차이·미결 + extra, 입력 순서)과 입력에 없는 extra ID."""
    key = key_column(plain)
    ids = plain[key].astype(str).str.strip()
    verdict = plain["verdict"].astype(str).str.strip() if "verdict" in plain.columns else pd.Series("", index=plain.index)
    wanted = set(extra)
    chosen = ids[verdict.isin(TARGET_VERDICTS) | ids.isin(wanted)]
    return list(dict.fromkeys(chosen)), sorted(wanted - set(ids))


def items_index(plain: pd.DataFrame, ids: list[str]) -> pd.DataFrame:
    """ID, 유형, verdict, status, 폴더(--out 기준 상대 경로). 이름이 겹치면 _2, _3 을 붙인다."""
    key = key_column(plain)
    first = plain.assign(_k=plain[key].astype(str).str.strip()).drop_duplicates("_k").set_index("_k")
    rows, used = [], set()
    for item in ids:
        r = first.loc[item]
        verdict = str(r.get("verdict", "")).strip()
        status = str(r.get("status", "")).strip()
        typ = item_type(status, verdict)
        name = base = safe_group_name(f"{typ}_{item}")
        n = 2
        while name in used:
            name, n = f"{base}_{n}", n + 1
        used.add(name)
        rows.append(dict(zip(INDEX_COLUMNS, (item, typ, verdict, status, f"{ITEMS_DIR}/{name}"))))
    return pd.DataFrame(rows, columns=list(INDEX_COLUMNS))


def read_compare(path: str | Path) -> pd.DataFrame:
    """compare_before_after.py compare 결과(compare.csv). 키 열은 _k, 나머지 열은 cmp_ 접두사."""
    df = read_plain(path)
    key = key_column(df)
    out = df.rename(columns={c: CMP_PREFIX + c for c in df.columns})
    out.insert(0, "_k", df[key].astype(str).str.strip())
    return out.drop_duplicates("_k")


def item_summary(plain: pd.DataFrame, item: str, cmp: pd.DataFrame | None) -> pd.DataFrame:
    """items.csv의 그 ITEM 행(모든 열) + compare 결과에 같은 ITEM이 있으면 cmp_ 열."""
    rows = plain[plain[key_column(plain)].astype(str).str.strip() == item].reset_index(drop=True)
    if cmp is not None:
        hit = cmp[cmp["_k"] == item].drop(columns="_k")
        if not hit.empty:
            rows = pd.concat([rows, pd.concat([hit] * len(rows), ignore_index=True)], axis=1)
    return rows


def add_raw_args(p: argparse.ArgumentParser) -> None:
    """por_doe_compare.py 와 같은 원데이터 인자(add_common_args 그대로). 여기서는 --por/--doe 가 선택이다."""
    add_common_args(p)
    for act in p._actions:
        if act.dest in ("por", "doe"):
            act.required = False


def load_raw(a: argparse.Namespace, items: list[str]) -> pd.DataFrame:
    """die별 원데이터: die 좌표(--key의 ITEM 밖 열), ITEM, POR 회차별, DOE, (blank), d = DOE − POR 회차 평균, por_range."""
    wide, por_cols, _ = load_wide(a)
    wide = wide[wide["ITEM"].astype(str).isin(items)].copy()
    por = wide[por_cols].astype(float)
    if a.blank:
        blank = load_blank(a.blank, a.encoding).set_index("BLANK_ITEM")
        bmap = {}
        if a.blank_map:
            mp = read_csv_auto(Path(a.blank_map), a.encoding)
            mp.columns = [c.strip().upper() for c in mp.columns]
            bmap = dict(zip(mp["ITEM"], mp["BLANK_ITEM"]))
        bitem = wide["ITEM"].map(lambda it: bmap.get(it, it))
        wide["blank_item"] = bitem.where(bitem.isin(blank.index), "")
        for col, name in (("sigma0", "blank_sigma0"), ("blank_offset", "blank_offset")):
            wide[name] = bitem.map(blank[col]) if col in blank.columns else math.nan
    wide["d"] = wide["DOE"].astype(float) - por.mean(axis=1)
    wide["por_range"] = por.max(axis=1) - por.min(axis=1)
    return wide


def items_dir_blocked(d: Path) -> str | None:
    """표식 없이 파일이 든 items/ 이면 이유 문장, 아니면 None."""
    if d.is_dir() and not (d / ITEMS_MARKER).is_file() and any(d.iterdir()):
        return (f"{d} 에 표식 파일 {ITEMS_MARKER} 이 없는데 파일이 있어 아무것도 지우지 않고 멈춥니다. "
                f"fail_evidence 가 만든 폴더가 아니면 다른 --out 을 쓰고, 맞으면 {d} 를 직접 비운 뒤 다시 실행하세요.")
    return None


def reset_items_dir(d: Path) -> None:
    """표식이 있는 items/ 아래를 모두 지우고(rmtree 없이 파일·빈 폴더 단위로) 표식을 다시 쓴다."""
    d.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(d, topdown=False):
        for name in files:
            Path(root, name).unlink()
        for name in dirs:
            p = Path(root, name)
            p.unlink() if p.is_symlink() else p.rmdir()
    (d / ITEMS_MARKER).write_text("fail_evidence.py 가 만든 폴더. 다시 실행하면 이 폴더 안을 모두 지우고 새로 만든다.\n",
                                  encoding="utf-8")


# ---------------------------------------------------------------- CLI

OWN_OUTPUTS = ("fail_evidence.csv", "summary.txt", "forest.png", ITEMS_INDEX)   # items/ 는 표식으로 따로 지운다


def remove_own_outputs(out: Path, patterns) -> None:
    """같은 --out에 다시 돌릴 때 지난 실행의 자기 출력 파일만 지운다(폴더·다른 파일은 그대로)."""
    for pat in patterns:
        for p in out.glob(pat):
            if p.is_file():
                p.unlink()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fail(차이·미결) ITEM별 근거를 규칙으로 계산한다.")
    p.add_argument("--input", required=True, help="por_doe_compare.py 결과 items.csv")
    p.add_argument("--out", required=True, help="출력 폴더")
    p.add_argument("--items", nargs="*", default=[], metavar="ID",
                   help="ITEM 폴더를 더 만들 ID(공백 또는 쉼표 구분). 기본 대상 = verdict 차이·미결")
    p.add_argument("--compare", help="compare_before_after.py compare 결과 compare.csv. 같은 ITEM 행을 summary.csv에 cmp_ 열로 붙임")
    raw = p.add_argument_group("원데이터 (por_doe_compare.py 와 같은 인자, 주면 raw.csv 작성)")
    add_raw_args(raw)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if bool(args.por) != bool(args.doe):
        print("오류: 원데이터는 --por 와 --doe 를 같이 주어야 합니다.", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        src = read_table(args.input)
        table = evidence_table(src)
        plain = read_plain(args.input)
        cmp = read_compare(args.compare) if args.compare else None
    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    items_dir = out / ITEMS_DIR
    blocked = items_dir_blocked(items_dir)
    if blocked:
        print(f"오류: {blocked}", file=sys.stderr)
        return 3

    extra = [s.strip() for arg in args.items for s in arg.split(",") if s.strip()]
    ids, unknown = select_items(plain, extra)
    if unknown:
        print(f"입력에 없는 ID: {', '.join(unknown)}")
    index = items_index(plain, ids)
    raw = load_raw(args, ids) if args.por else None

    remove_own_outputs(out, OWN_OUTPUTS)
    with_status(with_anon(table, src), src).to_csv(out / "fail_evidence.csv", index=False, encoding="utf-8-sig")

    configure_font()
    rcParams["axes.unicode_minus"] = False
    plot_forest(table, out / "forest.png")

    reset_items_dir(items_dir)
    for rec in index.to_dict("records"):
        folder = out / rec["폴더"]
        folder.mkdir(parents=True)
        item_summary(plain, rec["ID"], cmp).to_csv(folder / "summary.csv", index=False, encoding="utf-8-sig")
        if raw is not None:
            rows = raw[raw["ITEM"].astype(str) == rec["ID"]]
            if rows.empty:
                print(f"{rec['ID']}: 원데이터에 행 없음 (raw.csv는 머리줄만)")
            rows.to_csv(folder / "raw.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
    index.to_csv(out / ITEMS_INDEX, index=False, encoding="utf-8-sig")

    summary = summary_text(table, Path(args.input).name)
    summary += f"\nITEM 폴더: {len(index)}개 ({ITEMS_DIR}/, 목록 {ITEMS_INDEX})\n"
    if raw is None:
        summary += NO_RAW_MSG + "\n"
    (out / "summary.txt").write_text(summary, encoding="utf-8")
    print(summary, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
