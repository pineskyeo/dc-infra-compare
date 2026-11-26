"""새 리포트의 표와 요약 데이터를 만든다. 이 단계는 HTML 페이지나 그림을 만들지 않는다.

  python report_v2.py <out_folder> [--anon]
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import loq_check
import raw_stats as raw_stats_module
from compare_before_after import pct_of_median
from explain import BASIS_NAMES, LOQ_ZONES
from report import Namer


ITEM_COLUMNS = (
    "zone", "data_type", "cls_scale", "route", "verdict_final", "verdict_basis", "judged_by", "reason",
    "center", "ci_low", "ci_high", "center_log", "ci_low_log", "ci_high_log", "delta", "delta_log", "abs_delta",
    "accuracy_margin", "delta_pct", "sigma_die", "sigma_run", "rsd_pct", "LoQ", "LoD", "limit_source",
    "por_median", "loq_ratio",
)
OVERALL_RULE = "전체 판정 규칙(가정): 차이 ITEM이 1개라도 있으면 전체 차이, 아니면 미결이 있으면 전체 미결, 아니면 동등. 판정 제외는 전체 판정에 넣지 않고 개수로 따로 보인다."
VERDICTS = ("동등", "미결", "차이", "판정 제외")


def _text(value) -> str:
    return "" if value is None or (isinstance(value, float) and math.isnan(value)) else str(value).strip()


def _anon_text(value, namer: Namer, anon: bool):
    return html.unescape(namer.text(value)) if anon and isinstance(value, str) else value


def _basis_name(row) -> str:
    basis = _text(row.get("verdict_basis"))
    return BASIS_NAMES.get(basis, basis)


def judged_by(row) -> str:
    """최종 판정이 어느 근거로 나왔는지, 기존 pass_kind 분기를 그대로 표시한다."""
    final = _text(row.get("verdict_final"))
    if final == "판정 제외":
        return final
    basis = _basis_name(row)
    if final in ("차이", "미결") or _text(row.get("zone")) not in LOQ_ZONES:
        return basis
    if final == "동등":
        kind = loq_check.pass_kind(row)
        if kind == loq_check.K_SHIFT:
            return "TOST"
        if kind in loq_check.RULE_PASSES:
            return "LoQ 규칙"
        if kind == loq_check.K_STAGE3:
            return f"판정 길({basis})"
    return basis


def _n_runs(items: pd.DataFrame) -> int:
    runs = [int(match.group(1)) for col in items.columns if (match := re.fullmatch(r"POR(\d+)_mean", str(col)))]
    return max(runs, default=0)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def make_table(items: pd.DataFrame, raw: pd.DataFrame | None = None, anon: bool = False) -> pd.DataFrame:
    """items.csv 행 순서를 지켜 표를 만들고 raw_stats.csv 는 ITEM 으로 붙인다."""
    items = items.copy().reset_index(drop=True)
    raw_columns = raw_stats_module.column_names(_n_runs(items))[1:] if raw is None else [c for c in raw.columns if c != "ITEM"]
    if raw is None:
        raw = pd.DataFrame({"ITEM": pd.Series(dtype=str), **{c: pd.Series(dtype=float) for c in raw_columns}})
    merged = items.merge(raw, on="ITEM", how="left", sort=False, validate="one_to_one", suffixes=("", "_raw_stats"))
    present = [c for c in ITEM_COLUMNS if c in {"data_type", "judged_by", "delta_pct"} or c in items.columns]
    records = []
    namer = Namer(items, anon)
    for number, row in enumerate(merged.to_dict("records"), 1):
        zone = _text(row.get("zone"))
        out = {"row": number, "ITEM": namer.label(row["ITEM"])}
        for col in ITEM_COLUMNS:
            if col == "data_type":
                out[col] = "LoQ" if zone in LOQ_ZONES else zone
            elif col == "judged_by":
                out[col] = judged_by(row)
            elif col == "delta_pct":
                out[col] = pct_of_median(row.get("delta"), row.get("por_median"))
            elif col in items.columns:
                out[col] = row.get(col)
        out.update({col: row.get(col, np.nan) for col in raw_columns})
        records.append({key: _anon_text(value, namer, anon) for key, value in out.items()})
    return pd.DataFrame(records, columns=["row", "ITEM", *present, *raw_columns])


def summarize(table: pd.DataFrame) -> dict:
    """표의 최종 판정과 LoQ 구간을 센다. 판정 규칙을 새로 만들지 않는다."""
    records = table.to_dict("records")
    verdict_counts = {verdict: sum(_text(r.get("verdict_final")) == verdict for r in records) for verdict in VERDICTS}
    in_loq = [r for r in records if _text(r.get("zone")) in LOQ_ZONES]
    labels = [_text(r.get("judged_by")) for r in in_loq]
    loq = {
        "n_items": len(in_loq),
        "TOST로 동등": labels.count("TOST"),
        "LoQ 규칙으로 동등": labels.count("LoQ 규칙"),
        "판정 길": sum(label.startswith("판정 길(") for label in labels),
        "미결": sum(_text(r.get("verdict_final")) == "미결" for r in in_loq),
        "차이": sum(_text(r.get("verdict_final")) == "차이" for r in in_loq),
    }
    if verdict_counts["차이"]:
        overall = "차이"
    elif verdict_counts["미결"]:
        overall = "미결"
    elif verdict_counts["동등"]:
        overall = "동등"
    else:
        overall = "판정 없음"
    return {"verdict_counts": verdict_counts, "loq": loq, "overall": overall,
            "overall_rule": OVERALL_RULE, "loq_headline": []}


def _json_value(value):
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or value is pd.NA or (isinstance(value, float) and not math.isfinite(value)):
        return None
    return value


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def write_reports(out: Path, anon: bool = False) -> tuple[pd.DataFrame, dict]:
    items = _read_csv(out / "items.csv")
    raw_path = out / "raw_stats.csv"
    raw = _read_csv(raw_path) if raw_path.is_file() else None
    if raw is None:
        print(f"경고: {raw_path} 가 없어 원데이터 통계 열을 빈 칸으로 둡니다.", file=sys.stderr)
    table = make_table(items, raw, anon=anon)
    summary = summarize(table)
    if (out / "loq" / "loq_items.csv").is_file():
        namer = Namer(items, anon)
        summary["loq_headline"] = [_anon_text(line, namer, anon) for line in loq_check.load(out).headline_lines()]
    folder = out / ("report_anon" if anon else "report")
    folder.mkdir(parents=True, exist_ok=True)
    table.to_csv(folder / "table.csv", index=False, encoding="utf-8-sig")
    _write_json(folder / "table.json", {"cols": list(table.columns),
                                       "rows": [[_json_value(v) for v in row] for row in table.itertuples(index=False, name=None)]})
    _write_json(folder / "summary.json", summary)
    print(f"report v2 데이터: {folder}")
    return table, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out_folder", type=Path)
    ap.add_argument("--anon", action="store_true")
    a = ap.parse_args(argv)
    write_reports(a.out_folder, anon=a.anon)
    return 0


if __name__ == "__main__":
    sys.exit(main())
