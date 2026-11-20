"""Fail(차이·미결) ITEM별 근거를 규칙으로 계산해 CSV·차트·요약을 내고, ITEM마다 items/<유형>_<ID>/ 폴더를 만든다.

입력은 por_doe_compare.py 결과 표(--out 폴더의 items.csv, 쉼표 구분) 또는 같은 열의 탭 구분 표이다.
    python fail_evidence.py --input <items.csv> --out <폴더> [--items ID ... | --only ID ...] [--compare <compare.csv>]
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
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import rcParams  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import por_doe_compare  # noqa: E402
from compare_metrics import safe_group_name  # noqa: E402
from infra_compare import find_files, read_dcnormal  # noqa: E402
from por_doe_compare import (  # noqa: E402
    POR_GAP_NOISE_K, ST_BIMODAL, ST_FLAT, ST_LOG_CANDIDATE, ST_OK, ST_RESOLUTION, ST_RUN_JITTER, ST_SETUP_ERROR,
    ST_SIZE_JITTER, ST_SIZE_JITTER_POS, ST_UNSTABLE, is_log_target,
    add_common_args, load_blank, load_wide, pool_map, read_csv_auto,
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


# status 와 지표 묶음(items.csv 순서). por_gap_over_delta는 이 파일이 따로 계산하는 열과 이름이 같아 복사하지 않음
STATUS_COLUMNS = tuple(c for c in por_doe_compare.STATUS_COLS if c != "por_gap_over_delta")
PRECISION_COLUMNS = ("sigma_meas", "meas_precision_pct", "sigma_meas_over_delta")


def with_status(table: pd.DataFrame, src: pd.DataFrame) -> pd.DataFrame:
    """입력의 데이터 상태·지표 열을 행 순서 그대로(값은 문자열 그대로) 끝에 붙인다. 입력에 없으면 빈 칸."""
    out = table.copy()
    for c in STATUS_COLUMNS + PRECISION_COLUMNS:
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
INDEX_COLUMNS = ("ID", "유형", "verdict", "status", "폴더", "log_target")
CMP_PREFIX = "cmp_"
NO_RAW_MSG = "원데이터 없음: raw.csv·drill.png 건너뜀"
# 대표 status(폴더 <유형>): 여러 status가 ';'로 붙어 있으면 이 표에서 앞에 있는 것. 표에 없는 이름은 맨 뒤(나온 순서).
STATUS_PRIORITY = (ST_SETUP_ERROR, ST_UNSTABLE, ST_FLAT, ST_RESOLUTION, ST_RUN_JITTER, ST_SIZE_JITTER,
                   ST_SIZE_JITTER_POS, ST_LOG_CANDIDATE, ST_BIMODAL)


def item_type(status: str, verdict: str) -> str:
    """대표 status. status가 비었거나 정상이면 verdict."""
    names = [s.strip() for s in str(status).split(";") if s.strip() and s.strip() != ST_OK]
    if not names:
        return verdict
    rank = {s: i for i, s in enumerate(STATUS_PRIORITY)}
    return min(names, key=lambda s: rank.get(s, len(rank)))


def select_items(plain: pd.DataFrame, extra: list[str], base: bool = True) -> tuple[list[str], list[str]]:
    """폴더를 만들 ITEM(최종 판정 차이·미결 + extra, 입력 순서)과 입력에 없는 extra ID.
    최종 판정 = verdict_final, 열이 없는 옛 CSV 면 verdict. base=False(--only)면 차이·미결 없이 extra 만.
    extra 는 실제 ITEM 이름이나 익명 ID(ITEM 열과 같이 있는 ID 열, read_table 의 ANON_ID). 둘 다 맞으면 실제 이름 우선."""
    key = key_column(plain)
    ids = plain[key].astype(str).str.strip()
    col = next((c for c in ("verdict_final", "verdict") if c in plain.columns), None)
    verdict = plain[col].astype(str).str.strip() if col else pd.Series("", index=plain.index)
    anon = {}
    if key != "ID" and "ID" in plain.columns:
        anon = {a: i for a, i in zip(plain["ID"].astype(str).str.strip(), ids) if a}
    known = set(ids)
    wanted = {e if e in known else anon.get(e, e) for e in extra}
    chosen = ids[(verdict.isin(TARGET_VERDICTS) & base) | ids.isin(wanted)]
    return list(dict.fromkeys(chosen)), sorted(wanted - known)


def _row_log_target(r) -> bool:
    return is_log_target(r.get("status", ""), r.get("verdict", ""), r.get("verdict_log", ""))


def log_only_items(plain: pd.DataFrame, ids: list[str]) -> list[str]:
    """log 대상(is_log_target)인데 ids(차이·미결·--items)에 없는 ITEM(입력 순서). 폴더에 summary.csv·raw.csv(원데이터 있을 때)·log_diag.png 만 쓴다."""
    if plain.empty:
        return []
    keys = plain[key_column(plain)].astype(str).str.strip()
    hit = keys[plain.apply(_row_log_target, axis=1)]
    return [i for i in dict.fromkeys(hit) if i not in set(ids)]


def items_index(plain: pd.DataFrame, ids: list[str]) -> pd.DataFrame:
    """ID, 유형, verdict, status, 폴더(--out 기준 상대 경로), log_target. 이름이 겹치면 _2, _3 을 붙인다."""
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
        rows.append(dict(zip(INDEX_COLUMNS, (item, typ, verdict, status, f"{ITEMS_DIR}/{name}", _row_log_target(r)))))
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


def read_side_items(inputs: list[str], label: str, encoding: str, items) -> pd.DataFrame:
    """infra_compare.load_side 와 같은 측정 행이되 파일마다 읽자마자 ITEM 이 items 인 행만 남긴다.
    결과는 load_side 전체를 읽고 ITEM 으로 거른 것과 같다(행 순서·열·dtype)."""
    files = find_files(inputs)
    if not files:
        sys.exit(f"{label}: DCNORMAL 파일이 없습니다 ({inputs})")
    keep = {str(i) for i in items}
    parts = [df[df["ITEM"].astype(str).isin(keep)] for df in (read_dcnormal(f, encoding) for f in files)]
    return pd.concat(parts, ignore_index=True).dropna(subset=["DATA"]).reset_index(drop=True)


def load_wide_items(a: argparse.Namespace, items) -> tuple[pd.DataFrame, list[str]]:
    """por_doe_compare.load_wide 의 wide 표·POR 열을 items 행만 읽어 만든다(--only)."""
    key = a.key.split(",")
    side = [(paths, f"POR{i + 1}") for i, paths in enumerate(a.por)] + [(a.doe, "DOE")]
    cols = [read_side_items(paths, label, a.encoding, items).groupby(key)["DATA"].median().rename(label)
            for paths, label in side]
    wide = pd.concat(cols, axis=1, join="inner").reset_index()
    por_cols = [f"POR{i + 1}" for i in range(len(a.por))]
    print(f"원데이터: --only ITEM {len(set(items)):,}개 행만 읽음, 모든 회차에 있는 die·ITEM {len(wide):,}개")
    return wide, por_cols


def load_raw(a: argparse.Namespace, items: list[str], only: bool = False) -> pd.DataFrame:
    """die별 원데이터: die 좌표(--key의 ITEM 밖 열), ITEM, POR 회차별, DOE, (blank), d = DOE − POR 회차 평균, por_range.
    only 면 원데이터를 읽을 때부터 items 행만 남긴다(load_wide_items)."""
    wide, por_cols = load_wide_items(a, items) if only else load_wide(a)[:2]
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


DRILL_PNG = "drill.png"
POR_COL_RE = re.compile(r"^POR\d+$")
XY_PAIRS = (("X", "Y"), ("DIE_X", "DIE_Y"), ("COORD_X", "COORD_Y"), ("DIEX", "DIEY"))
XY_TEXT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[_,:/ ]\s*(-?\d+(?:\.\d+)?)\s*$")
POR_COLOR, DOE_COLOR, D_COLOR = "#7f7f7f", "#d62728", "#1f77b4"


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


def _num(row: dict, name: str) -> float:
    v = pd.to_numeric(pd.Series([row.get(name)]), errors="coerce").iloc[0]
    return float(v) if pd.notna(v) else NAN


def _no_data(ax, text: str = "자료 없음") -> None:
    ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes, color="#555555")
    ax.set_xticks([])
    ax.set_yticks([])


def _drill_values(ax, rows: pd.DataFrame, por_cols: list[str]) -> None:
    """① POR 회차별·DOE die 값: box + 흩뿌린 점."""
    cols = por_cols + (["DOE"] if "DOE" in rows.columns else [])
    data = [pd.to_numeric(rows[c], errors="coerce").dropna().to_numpy() for c in cols]
    if not any(len(v) for v in data):
        _no_data(ax)
    else:
        ax.boxplot([v if len(v) else [NAN] for v in data], widths=0.5, showfliers=False,
                   medianprops={"color": "#333333"})
        for i, (c, v) in enumerate(zip(cols, data), start=1):
            jitter = (pd.Series(range(len(v))) % 7 - 3) * 0.04
            ax.plot(i + jitter.to_numpy(), v, "o", ms=3, alpha=0.6,
                    color=DOE_COLOR if c == "DOE" else POR_COLOR)
        ax.set_xticks(range(1, len(cols) + 1))
        ax.set_xticklabels(cols, fontsize=8)
        ax.grid(axis="y", alpha=0.3)
    ax.set_title("POR 회차별·DOE die 값", fontsize=10)


def _drill_blank(ax, rows: pd.DataFrame, s: dict) -> None:
    """② Blank 분포(σ0·offset 기준 정규 곡선)와 LoD·LoQ 선."""
    lod, loq = _num(s, "LoD"), _num(s, "LoQ")
    sig = pd.to_numeric(rows.get("blank_sigma0", pd.Series(dtype=float)), errors="coerce").dropna()
    off = pd.to_numeric(rows.get("blank_offset", pd.Series(dtype=float)), errors="coerce").dropna()
    sigma = float(sig.iloc[0]) if not sig.empty and sig.iloc[0] > 0 else NAN
    mu = float(off.iloc[0]) if not off.empty else 0.0
    lines = [(v, n, ls) for v, n, ls in ((lod, "LoD", ":"), (loq, "LoQ", "--")) if math.isfinite(v)]
    if not math.isfinite(sigma) and not lines:
        _no_data(ax)
    else:
        if math.isfinite(sigma):
            xs = [mu + sigma * (i / 50 - 4) for i in range(401)]
            ys = [math.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi)) for x in xs]
            ax.fill_between(xs, ys, color=POR_COLOR, alpha=0.3, label=f"Blank (σ0={sigma:.3g})")
        for v, n, ls in lines:
            ax.axvline(v, color="#333333", ls=ls, lw=1.2, label=f"{n}={v:.3g}")
        ax.legend(fontsize=7, loc="best")
        ax.set_yticks([])
    ax.set_title("Blank 분포와 LoD·LoQ", fontsize=10)


def _center_lines(ax, s: dict, vertical: bool) -> None:
    line = ax.axvline if vertical else ax.axhline
    center, delta = _num(s, "center"), _num(s, "delta")
    if math.isfinite(center):
        line(center, color="#333333", lw=1.5, label=f"center={center:.3g}")
    if math.isfinite(delta):
        for sign in (-1, 1):
            line(sign * delta, color="#555555", ls="--", lw=1, label="±Δ" if sign > 0 else None)
    line(0, color="#999999", lw=0.8)


def _drill_d_hist(ax, d: pd.Series, s: dict) -> None:
    """③ d 히스토그램 + center·CI·±Δ 세로선."""
    if d.empty:
        _no_data(ax)
    else:
        ax.hist(d, bins=min(30, max(5, len(d) // 3)), color=D_COLOR, alpha=0.6)
        lo, hi = _num(s, "ci_low"), _num(s, "ci_high")
        if math.isfinite(lo) and math.isfinite(hi):
            ax.axvspan(lo, hi, color="#ff7f0e", alpha=0.2, label="CI")
        _center_lines(ax, s, vertical=True)
        ax.legend(fontsize=7, loc="best")
        ax.set_xlabel("d = DOE − POR 회차 평균", fontsize=8)
    ax.set_title("d 분포", fontsize=10)


def _drill_d_order(ax, d: pd.Series, s: dict) -> None:
    """④ raw.csv 행 순서별 d + center·±Δ 가로선."""
    if d.empty:
        _no_data(ax)
    else:
        ax.plot(range(1, len(d) + 1), d.to_numpy(), "o-", ms=3, lw=0.6, color=D_COLOR)
        _center_lines(ax, s, vertical=False)
        ax.legend(fontsize=7, loc="best")
        ax.set_xlabel("die 순서 (raw.csv 행)", fontsize=8)
        ax.set_ylabel("d", fontsize=8)
        ax.grid(alpha=0.3)
    ax.set_title("die 순서별 d", fontsize=10)


def _drill_map(fig, ax, xy: tuple[pd.Series, pd.Series], d: pd.Series) -> None:
    """⑤ 웨이퍼맵: die 좌표에 d 색(0 중심 발산색)."""
    lim = float(d.abs().max()) if d.notna().any() else 1.0
    lim = lim if lim > 0 else 1.0
    sc = ax.scatter(xy[0], xy[1], c=d, cmap="RdBu_r", vmin=-lim, vmax=lim, s=40, marker="s")
    fig.colorbar(sc, ax=ax, label="d")
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x", fontsize=8)
    ax.set_ylabel("y", fontsize=8)
    ax.set_title("웨이퍼맵 (d)", fontsize=10)


def plot_drill(rows: pd.DataFrame, summary: dict, item: str, path: Path) -> Path:
    """ITEM 한 개의 공통 그림: 값 분포, Blank·LoD·LoQ, d 분포, die 순서별 d, (좌표 있으면) 웨이퍼맵."""
    rows = rows.reset_index(drop=True)
    por_cols = [c for c in rows.columns if POR_COL_RE.match(str(c))]
    d = pd.to_numeric(rows["d"], errors="coerce") if "d" in rows.columns else pd.Series(dtype=float)
    xy = die_xy(rows)
    fig, axes = plt.subplots(2, 3 if xy is not None else 2, figsize=(14 if xy is not None else 10, 7.5))
    ax = axes.ravel()
    _drill_values(ax[0], rows, por_cols)
    _drill_blank(ax[1], rows, summary)
    if xy is not None:
        _drill_map(fig, ax[2], xy, d)
        ax[5].set_axis_off()
        hist_ax, order_ax = ax[3], ax[4]
    else:
        hist_ax, order_ax = ax[2], ax[3]
    _drill_d_hist(hist_ax, d.dropna(), summary)
    _drill_d_order(order_ax, d, summary)
    parts = [item, summary.get("verdict"), summary.get("status")]
    fig.suptitle(" · ".join(str(p).strip() for p in parts if not pd.isna(p) and str(p).strip()))
    _footnote(fig, f"die {len(rows)}개, POR 회차 {len(por_cols)}개. 실선 = center, 점선 = ±Δ, 주황 띠 = CI")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ---------------------------------------------------------------- status별 패널 (status_<이름>.png)

STATUS_PNG = "status_{}.png"


def _por_matrix(rows: pd.DataFrame, por_cols: list[str]) -> pd.DataFrame:
    """die × POR 회차 숫자 표 (NaN 있는 die 제외)."""
    return rows[por_cols].apply(pd.to_numeric, errors="coerce").dropna() if por_cols else pd.DataFrame()


def _status_unstable(ax, rows: pd.DataFrame, s: dict, por_cols: list[str]) -> None:
    """조건 불안정: 회차별 짝지은 차 중앙값의 폭(gap)과 K·se 막대, ±Δ. gap·se는 summary 의 GAP_COLS 에서 되돌린다."""
    delta, over_delta, over_noise = _num(s, "delta"), _num(s, "por_gap_over_delta"), _num(s, "por_gap_over_noise")
    if not (math.isfinite(delta) and math.isfinite(over_delta)):
        _no_data(ax, "summary 에 delta·por_gap_over_delta 없음")
    else:
        gap = over_delta * delta
        bars = [("회차 차 중앙값 폭", gap, D_COLOR)]
        if math.isfinite(over_noise) and over_noise > 0:
            bars.append((f"{POR_GAP_NOISE_K:g}·se", POR_GAP_NOISE_K * gap / over_noise, POR_COLOR))
        ax.bar([b[0] for b in bars], [b[1] for b in bars], color=[b[2] for b in bars], alpha=0.7, width=0.5)
        for sign in (-1, 1):
            ax.axhline(sign * delta, color="#555555", ls="--", lw=1, label="±Δ" if sign > 0 else None)
        ax.axhline(0, color="#999999", lw=0.8)
        ax.legend(fontsize=7, loc="best")
        ax.grid(axis="y", alpha=0.3)
    ax.set_title("회차별 짝지은 차 중앙값 폭 vs ±Δ", fontsize=10)


def _status_run_jitter(ax, rows: pd.DataFrame, s: dict, por_cols: list[str]) -> None:
    """회차 흔들림: die별 (회차 max−min)/|회차 평균| 히스토그램 + Δ/|POR 중앙값| 선."""
    P = _por_matrix(rows, por_cols)
    m = P.mean(axis=1) if P.shape[1] >= 2 else pd.Series(dtype=float)
    keep = m != 0
    rel = ((P.max(axis=1) - P.min(axis=1))[keep] / m[keep].abs()) if not m.empty else m
    if rel.empty:
        _no_data(ax, "POR 회차 2개 이상 필요")
    else:
        ax.hist(rel, bins=min(30, max(5, len(rel) // 3)), color=POR_COLOR, alpha=0.7)
        delta, med = _num(s, "delta"), float(m.median())
        if math.isfinite(delta) and med != 0:
            ax.axvline(delta / abs(med), color="#333333", ls="--", lw=1.2, label=f"Δ/|POR 중앙값| = {delta / abs(med):.3g}")
            ax.legend(fontsize=7, loc="best")
        ax.set_xlabel("(회차 max − min) / |회차 평균|", fontsize=8)
        ax.set_ylabel("die 수", fontsize=8)
    ax.set_title("die별 회차 흔들림", fontsize=10)


def _status_size_jitter(ax, rows: pd.DataFrame, s: dict, por_cols: list[str]) -> None:
    """작을수록 흔들림: log10|회차 평균| vs log10|값|의 회차 범위 + ρ(summary 의 spearman_size_jitter)."""
    P = _por_matrix(rows, por_cols)
    if P.shape[1] >= 2:
        m = P.mean(axis=1)
        P = P[(P != 0).all(axis=1) & (m != 0)]
    if P.shape[1] < 2 or P.empty:
        _no_data(ax, "0 아닌 POR 회차 2개 이상 필요")
    else:
        lg = np.log10(P.abs())
        ax.scatter(np.log10(P.mean(axis=1).abs()), lg.max(axis=1) - lg.min(axis=1), s=20, color=POR_COLOR, alpha=0.7)
        rho = _num(s, "spearman_size_jitter")
        text = f"ρ = {rho:.2f}".replace("-", "−") if math.isfinite(rho) else "ρ 없음"
        ax.text(0.97, 0.95, text, transform=ax.transAxes, ha="right", va="top", fontsize=11)
        ax.set_xlabel("log10 |회차 평균|", fontsize=8)
        ax.set_ylabel("log10 |값| 의 회차 범위", fontsize=8)
        ax.grid(alpha=0.3)
    ax.set_title("크기별 회차 흔들림", fontsize=10)


def _status_resolution(ax, rows: pd.DataFrame, s: dict, por_cols: list[str]) -> None:
    """분해능 부족: 원값(POR 모든 회차·DOE) 계단형 히스토그램."""
    por = _por_matrix(rows, por_cols).stack()
    doe = pd.to_numeric(rows.get("DOE", pd.Series(dtype=float)), errors="coerce").dropna()
    both = pd.concat([por, doe])
    if both.empty:
        _no_data(ax)
    else:
        lo, hi = float(both.min()), float(both.max())
        rng = (lo, hi) if hi > lo else (lo - 0.5, hi + 0.5)
        bins = min(60, max(10, both.nunique() * 2))
        for v, name, color in ((por, "POR", POR_COLOR), (doe, "DOE", DOE_COLOR)):
            if not v.empty:
                ax.hist(v, bins=bins, range=rng, histtype="step", lw=1.5, color=color, label=name)
        ax.legend(fontsize=7, loc="best")
        ax.set_xlabel("원값", fontsize=8)
        ax.set_ylabel("개수", fontsize=8)
    ax.set_title("원값 분포 (계단형)", fontsize=10)


def _status_flat(ax, rows: pd.DataFrame, s: dict, por_cols: list[str]) -> None:
    """산포 0: POR 회차 평균·DOE 값의 위치(strip)와 Blank·LoD·LoQ 세로선."""
    P = _por_matrix(rows, por_cols)
    por = P.mean(axis=1) if not P.empty else pd.Series(dtype=float)
    doe = pd.to_numeric(rows.get("DOE", pd.Series(dtype=float)), errors="coerce").dropna()
    off = pd.to_numeric(rows.get("blank_offset", pd.Series(dtype=float)), errors="coerce").dropna()
    lines = [(v, n, ls) for v, n, ls in ((float(off.iloc[0]) if not off.empty else NAN, "Blank", "-"),
                                         (_num(s, "LoD"), "LoD", ":"), (_num(s, "LoQ"), "LoQ", "--"))
             if math.isfinite(v)]
    if por.empty and doe.empty:
        _no_data(ax)
    else:
        for y, (v, name, color) in enumerate(((doe, "DOE", DOE_COLOR), (por, "POR 회차 평균", POR_COLOR))):
            jitter = (pd.Series(range(len(v))) % 7 - 3) * 0.04
            ax.plot(v.to_numpy(), y + jitter.to_numpy(), "o", ms=4, alpha=0.6, color=color, label=name)
        for v, n, ls in lines:
            ax.axvline(v, color="#333333", ls=ls, lw=1.2, label=f"{n}={v:.3g}")
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["DOE", "POR"], fontsize=8)
        ax.legend(fontsize=7, loc="best")
        ax.grid(axis="x", alpha=0.3)
    ax.set_title("Blank·LoD·LoQ 대비 값 위치", fontsize=10)


def _status_shape(ax, rows: pd.DataFrame, s: dict, por_cols: list[str]) -> None:
    """log 후보·두 덩어리: die별 log10|POR 회차 평균| 히스토그램 + summary 의 decades·log_fit·bimodality_log."""
    P = _por_matrix(rows, por_cols)
    m = P.mean(axis=1) if not P.empty else pd.Series(dtype=float)
    if m.empty or (m == 0).any() or ((m > 0).any() and (m < 0).any()):
        _no_data(ax, "POR 회차 평균에 0 또는 부호 섞임")
    else:
        lg = np.log10(m.abs())
        ax.hist(lg, bins=min(30, max(5, len(lg) // 3)), color=POR_COLOR, alpha=0.7)
        text = "\n".join(f"{c} = {_num(s, c):.3g}" for c in ("decades", "log_fit", "bimodality_log")
                         if math.isfinite(_num(s, c)))
        if text:
            ax.text(0.97, 0.95, text.replace("-", "−"), transform=ax.transAxes, ha="right", va="top", fontsize=9)
        ax.set_xlabel("log10 |회차 평균|", fontsize=8)
        ax.set_ylabel("die 수", fontsize=8)
        ax.grid(axis="y", alpha=0.3)
    ax.set_title("die별 크기 분포 (log)", fontsize=10)


STATUS_PANELS = {
    ST_UNSTABLE: _status_unstable,
    ST_RUN_JITTER: _status_run_jitter,
    ST_SIZE_JITTER: _status_size_jitter,
    ST_SIZE_JITTER_POS: _status_size_jitter,
    ST_RESOLUTION: _status_resolution,
    ST_FLAT: _status_flat,
    ST_LOG_CANDIDATE: _status_shape,
    ST_BIMODAL: _status_shape,
}


def plot_status_panels(rows: pd.DataFrame, summary: dict, item: str, status: str, folder: Path) -> list[Path]:
    """status(';' 구분, 정상 제외)마다 패널 한 장을 folder/status_<이름>.png 로. 모르는 status는 경고 한 줄만."""
    rows = rows.reset_index(drop=True)
    por_cols = [c for c in rows.columns if POR_COL_RE.match(str(c))]
    text = "" if pd.isna(status) else str(status)
    names = dict.fromkeys(n.strip() for n in text.split(";") if n.strip() and n.strip() != ST_OK)
    paths = []
    for name in names:
        draw = STATUS_PANELS.get(name)
        if draw is None:
            print(f"{item}: 경고: 모르는 status '{name}' — 패널 없음")
            continue
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        draw(ax, rows, summary, por_cols)
        fig.suptitle(f"{item} · {name}")
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        path = folder / STATUS_PNG.format(safe_group_name(name))
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    return paths


# ---------------------------------------------------------------- 선형 vs log 진단 (log_diag.png)

LOG_DIAG_PNG = "log_diag.png"
LOG_SUFFIX = "_log"
CI_KEYS = ("center", "ci_low", "ci_high", "delta")


def _sub_summary(s: dict, suffix: str) -> dict:
    """center·ci_low·ci_high·delta 를 suffix 열(예: center_log)에서 꺼낸 dict."""
    return {k: s.get(k + suffix) for k in CI_KEYS}


def _log_missing_text(s: dict) -> str:
    reason = s.get("log_reason")
    return str(reason).strip() if reason is not None and not pd.isna(reason) and str(reason).strip() else "log 열 없음"


def _log_verdict(ax, s: dict, suffix: str, title: str) -> None:
    """(a) 판정 한 칸: CI 막대 + center 점 + ±Δ 선 + verdict 글자."""
    sub = _sub_summary(s, suffix)
    center, lo, hi, delta = (_num(sub, k) for k in CI_KEYS)
    if not all(math.isfinite(v) for v in (center, lo, hi)):
        _no_data(ax, _log_missing_text(s) if suffix else "center·CI 없음")
    else:
        ax.errorbar([center], [0], xerr=[[max(0.0, center - lo)], [max(0.0, hi - center)]], fmt="o", color=D_COLOR, capsize=6, lw=2,
                    label="center·CI")
        _center_lines(ax, sub, vertical=True)
        verdict = s.get("verdict" + suffix)
        text = str(verdict).strip() if verdict is not None and not pd.isna(verdict) else "verdict 없음"
        ax.text(0.03, 0.92, text, transform=ax.transAxes, ha="left", va="top", fontsize=12, weight="bold")
        ax.set_yticks([])
        ax.set_ylim(-1, 1)
        ax.legend(fontsize=7, loc="lower right")
    ax.set_title(title, fontsize=10)


def _log_size_scatter(ax, rows: pd.DataFrame, s: dict, por_cols: list[str]) -> None:
    """(b) log10|회차 평균| vs 회차 범위: 선형 범위(왼쪽 축)와 log 범위(오른쪽 축) + 두 ρ."""
    P = _por_matrix(rows, por_cols)
    if P.shape[1] >= 2:
        P = P[(P != 0).all(axis=1) & (P.mean(axis=1) != 0)]
    if P.shape[1] < 2 or P.empty:
        _no_data(ax, "0 아닌 POR 회차 2개 이상 필요")
    else:
        size = np.log10(P.mean(axis=1).abs())
        lg = np.log10(P.abs())
        ax.scatter(size, P.max(axis=1) - P.min(axis=1), s=20, color=POR_COLOR, alpha=0.7, label="선형 범위")
        ax.set_ylabel("선형 범위 (max − min)", fontsize=8, color=POR_COLOR)
        ax2 = ax.twinx()
        ax2.scatter(size, lg.max(axis=1) - lg.min(axis=1), s=20, marker="^", color=DOE_COLOR, alpha=0.7, label="log 범위")
        ax2.set_ylabel("log10 |값| 범위", fontsize=8, color=DOE_COLOR)
        lines = []
        for name, col in (("선형", "spearman_size_jitter"), ("log", "spearman_size_jitter" + LOG_SUFFIX)):
            rho = _num(s, col)
            lines.append(f"ρ {name} = {rho:.2f}".replace("-", "−") if math.isfinite(rho) else f"ρ {name} 없음")
        ax.text(0.97, 0.95, "\n".join(lines), transform=ax.transAxes, ha="right", va="top", fontsize=10)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left")
        ax.set_xlabel("log10 |회차 평균|", fontsize=8)
        ax.grid(alpha=0.3)
    ax.set_title("크기 vs 회차 흔들림 (선형·log)", fontsize=10)


def _log_d(rows: pd.DataFrame, por_cols: list[str]) -> pd.Series | None:
    """log d = log10|DOE| − 회차 평균 log10|POR|. POR·DOE 에 0값이 있으면 None."""
    vals = rows[por_cols + ["DOE"]].apply(pd.to_numeric, errors="coerce") if "DOE" in rows.columns else pd.DataFrame()
    if vals.empty or (vals == 0).any().any():
        return None
    return (np.log10(vals["DOE"].abs()) - np.log10(vals[por_cols].abs()).mean(axis=1)).dropna()


def plot_log_diag(rows: pd.DataFrame, summary: dict, item: str, path: Path) -> Path:
    """작을수록·클수록 흔들림 ITEM: (a) 선형 vs log 판정 (b) 크기 vs 회차 흔들림 (c) 선형·log d 분포."""
    rows = rows.reset_index(drop=True)
    por_cols = [c for c in rows.columns if POR_COL_RE.match(str(c))]
    fig = plt.figure(figsize=(11, 11))
    gs = fig.add_gridspec(3, 2)
    _log_verdict(fig.add_subplot(gs[0, 0]), summary, "", "선형 판정")
    _log_verdict(fig.add_subplot(gs[0, 1]), summary, LOG_SUFFIX, "log 판정")
    _log_size_scatter(fig.add_subplot(gs[1, :]), rows, summary, por_cols)
    d = pd.to_numeric(rows["d"], errors="coerce").dropna() if "d" in rows.columns else pd.Series(dtype=float)
    ax = fig.add_subplot(gs[2, 0])
    _drill_d_hist(ax, d, summary)
    ax.set_title("선형 d 분포", fontsize=10)
    ax = fig.add_subplot(gs[2, 1])
    dlog = _log_d(rows, por_cols)
    if dlog is None:
        _no_data(ax, "0값 있음")
    else:
        _drill_d_hist(ax, dlog, _sub_summary(summary, LOG_SUFFIX))
        if not dlog.empty:
            ax.set_xlabel("log d = log10|DOE| − 회차 평균 log10|POR|", fontsize=8)
    ax.set_title("log d 분포", fontsize=10)
    parts = [item, summary.get("status")]
    fig.suptitle(" · ".join(str(p).strip() for p in parts if not pd.isna(p) and str(p).strip()) + " · 선형 vs log")
    _footnote(fig, "실선 = center, 점선 = ±Δ, 주황 띠 = CI. log 열은 items.csv 의 *_log 열")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


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


# main 이 pool_map 전에 채운다: "plain"(items.csv 표), "raw"(ITEM ID -> 그 ITEM 의 원데이터 행, 원데이터 없으면 None).
# fork 자식이 그대로 물려받으므로 큰 표를 피클로 넘기지 않는다.
_SHARED: dict = {}


def _split_raw(raw: pd.DataFrame, ids: list[str]) -> dict[str, pd.DataFrame]:
    """raw[raw["ITEM"].astype(str) == id] 와 같은 행·열·dtype 을 ID마다 한 번에. 없는 ID 는 같은 열의 빈 표."""
    groups = dict(list(raw.groupby(raw["ITEM"].astype(str), sort=False)))
    return {i: groups.get(i, raw.iloc[0:0]) for i in ids}


def _write_item(rec: dict, out: Path, cmp: pd.DataFrame | None, log_only: bool) -> None:
    """items/<폴더>/ 하나: summary.csv, (원데이터 있으면) raw.csv 와 그림. log_only 면 log_diag.png 만."""
    plain, raw = _SHARED["plain"], _SHARED["raw"]
    folder = out / rec["폴더"]
    folder.mkdir(parents=True)
    isum = item_summary(plain, rec["ID"], cmp)
    isum.to_csv(folder / "summary.csv", index=False, encoding="utf-8-sig")
    srow = isum.iloc[0].to_dict() if not isum.empty else {}
    if raw is None:
        return
    rows = raw[rec["ID"]]
    if log_only:
        rows.to_csv(folder / "raw.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
        if not rows.empty:
            plot_log_diag(rows, srow, rec["ID"], folder / LOG_DIAG_PNG)
        return
    if rows.empty:
        print(f"{rec['ID']}: 원데이터에 행 없음 (raw.csv는 머리줄만, {DRILL_PNG} 없음)")
    rows.to_csv(folder / "raw.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
    if not rows.empty:
        plot_drill(rows, srow, rec["ID"], folder / DRILL_PNG)
        plot_status_panels(rows, srow, rec["ID"], rec["status"], folder)
        if rec["log_target"]:
            plot_log_diag(rows, srow, rec["ID"], folder / LOG_DIAG_PNG)


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
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--items", nargs="*", default=[], metavar="ID",
                     help="ITEM 폴더를 더 만들 ID(공백 또는 쉼표 구분, 실제 ITEM 이름 또는 익명 ID, 겹치면 실제 이름). 기본 대상 = verdict 차이·미결")
    sel.add_argument("--only", nargs="+", metavar="ID",
                     help="기본 대상 없이 이 ITEM 만(--items 와 같은 형식, 판정 제외 ITEM 도 가능). 원데이터·출력 표도 이 ITEM 만")
    p.add_argument("--compare", help="compare_before_after.py compare 결과 compare.csv. 같은 ITEM 행을 summary.csv에 cmp_ 열로 붙임")
    raw = p.add_argument_group("원데이터 (por_doe_compare.py 와 같은 인자, 주면 raw.csv 작성)")
    add_raw_args(raw)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if bool(args.por) != bool(args.doe):
        print("오류: 원데이터는 --por 와 --doe 를 같이 주어야 합니다.", file=sys.stderr)
        return 2
    only = args.only is not None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    extra = [s.strip() for arg in (args.only if only else args.items) for s in arg.split(",") if s.strip()]
    try:
        src = read_table(args.input)
        plain = read_plain(args.input)
        ids, unknown = select_items(plain, extra, base=not only)
        if only:
            if not ids:
                raise ValueError(f"--only 에 입력과 맞는 ITEM 이 없습니다 (입력에 없는 ID: {', '.join(unknown)}).")
            if "ID" in src.columns:
                src = src[src["ID"].astype(str).str.strip().isin(ids)].reset_index(drop=True)
        table = evidence_table(src)
        cmp = read_compare(args.compare) if args.compare else None
    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    items_dir = out / ITEMS_DIR
    blocked = items_dir_blocked(items_dir)
    if blocked:
        print(f"오류: {blocked}", file=sys.stderr)
        return 3

    if unknown:
        print(f"입력에 없는 ID: {', '.join(unknown)}")
    log_ids = [] if only else log_only_items(plain, ids)
    log_only = set(log_ids)
    index = items_index(plain, ids + log_ids)
    raw = load_raw(args, list(index["ID"]), only) if args.por else None

    remove_own_outputs(out, OWN_OUTPUTS)
    with_status(with_anon(table, src), src).to_csv(out / "fail_evidence.csv", index=False, encoding="utf-8-sig")

    configure_font()
    rcParams["axes.unicode_minus"] = False
    plot_forest(table, out / "forest.png")

    reset_items_dir(items_dir)
    records = index.to_dict("records")
    _SHARED["plain"] = plain
    _SHARED["raw"] = None if raw is None else _split_raw(raw, [r["ID"] for r in records])
    try:
        pool_map(_write_item, [(rec, out, cmp, rec["ID"] in log_only) for rec in records])
    finally:
        _SHARED.clear()
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
