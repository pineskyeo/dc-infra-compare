"""새 리포트의 표, 요약 데이터와 브라우저 페이지를 만든다.

  python report_v2.py <out_folder> [--anon] [--images fail|fail+pending|all|none]

POR/DOE 공통 인자를 함께 주면 ITEM 원데이터 chunk 도 만든다. 인자가 없으면
표와 페이지만 만들고 ITEM 상세 원데이터는 비워 둔다.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import loq_check
import por_doe_compare
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
CHUNK_SIZE = 100


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


def _page(title: str, current: str, body: str, scripts: list[str]) -> str:
    pages = (("index.html", "요약"), ("table.html", "ITEM 표"), ("analysis.html", "ITEM 분석"))
    nav_parts = []
    for href, label in pages:
        current_attr = ' aria-current="page"' if href == current else ""
        nav_parts.append(f'<a href="{href}"{current_attr}>{label}</a>')
    nav = "".join(nav_parts)
    script_tags = "".join(f'<script defer src="{src}"></script>\n' for src in scripts)
    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="assets/report.css">
{script_tags}</head>
<body>
<header class="top"><a class="brand" href="index.html">DC 리포트</a><span>{html.escape(title)}</span></header>
<nav class="side" aria-label="리포트 페이지"><p class="nav-h">리포트</p>{nav}</nav>
{body}
</body>
</html>
'''


def _summary_html(summary: dict) -> str:
    overall = html.escape(_text(summary["overall"]))
    rule = html.escape(_text(summary["overall_rule"]))
    counts = "".join(f'<div class="count-card"><dt>{html.escape(v)}</dt><dd>{summary["verdict_counts"].get(v, 0)}</dd></div>'
                     for v in VERDICTS)
    loq = summary["loq"]
    loq_rows = "".join(f'<div class="count-card"><dt>{html.escape(label)}</dt><dd>{loq.get(key, 0)}</dd></div>'
                       for key, label in (("TOST로 동등", "TOST로 동등"), ("LoQ 규칙으로 동등", "LoQ 규칙으로 동등"),
                                          ("판정 길", "판정 길"), ("미결", "미결"), ("차이", "차이")))
    headlines = "".join(f"<li>{html.escape(_text(line))}</li>" for line in summary["loq_headline"])
    if not headlines:
        headlines = "<li>LoQ 점검 요약이 없습니다.</li>"
    return f'''<main class="page">
<h1 class="overall">전체 판정: {overall}</h1>
<p class="overall-rule">{rule}</p>
<h2>최종 판정</h2><dl class="card-grid">{counts}</dl>
<h2>LoQ 구간 ({loq["n_items"]} ITEM)</h2><dl class="card-grid">{loq_rows}</dl>
<h2>LoQ 점검</h2><ul class="headline">{headlines}</ul>
</main>'''


TABLE_BODY = '''<main class="page page-wide">
<h1>ITEM 표</h1>
<div id="dc-error" class="dc-error" role="alert" hidden></div>
<div class="table-tools" aria-label="표 필터">
<div class="menu" role="group" aria-label="LoQ 필터"><button type="button" data-filter="all" aria-pressed="true">전체</button><button type="button" data-filter="loq" aria-pressed="false">LoQ만</button><button type="button" data-filter="not-loq" aria-pressed="false">LoQ 아님</button></div>
<label>ITEM 검색 <input id="table-search" type="search" autocomplete="off"></label>
<strong id="table-count" aria-live="polite"></strong>
</div>
<p class="hint">열 머리글을 누륵면 정렬합니다. 행을 누륵면 ITEM 분석으로 이동합니다.</p>
<div class="dc-table-scroll"><div id="dc-table-head" class="dc-grid dc-head"></div><div id="dc-viewport"><div id="dc-spacer"><div id="dc-rows"></div></div></div></div>
</main>'''


ANALYSIS_BODY = '''<main class="page">
<h1>ITEM 분석</h1>
<div id="dc-error" class="dc-error" role="alert" hidden></div>
<form id="analysis-search" class="analysis-search"><label>ITEM 검색 <input id="analysis-query" type="search" autocomplete="off"></label><button type="submit">첫 항목 열기</button></form>
<section id="item-detail" aria-live="polite"></section>
<section class="charts" aria-label="ITEM 차트"><div id="chart-scatter-lin" class="chart-slot">차트는 다음 단계</div><div id="chart-scatter-log" class="chart-slot">차트는 다음 단계</div><div id="chart-box" class="chart-slot">차트는 다음 단계</div><div id="chart-ci" class="chart-slot">차트는 다음 단계</div></section>
</main>'''


def _write_js(path: Path, name: str, value) -> None:
    path.write_text(f"window.{name} = {json.dumps(value, ensure_ascii=False, allow_nan=False)};\n", encoding="utf-8")


def _write_pages(table: pd.DataFrame, summary: dict, out: Path, anon: bool, a: argparse.Namespace) -> None:
    """브라우저 페이지와 ITEM chunk 를 쓴다. 기존 CSV/JSON 작성과 분리한다."""
    folder = out / ("report_anon" if anon else "report")
    assets = folder / "assets"
    data = folder / "data"
    chunks_dir = data / "chunks"
    assets.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent
    for name in ("report.js", "report.css"):
        shutil.copyfile(root / "assets" / "report" / name, assets / name)
    for source, target in (("echarts.min.js", "echarts.min.js"), ("LICENSE", "echarts.LICENSE.txt"),
                           ("NOTICE", "echarts.NOTICE.txt")):
        try:
            shutil.copyfile(root / "assets" / "report" / "vendor" / source, assets / target)
        except FileNotFoundError:
            print(f"경고: vendor 파일 {source} 가 없어 복사하지 않았습니다.", file=sys.stderr)

    (folder / "index.html").write_text(_page("요약", "index.html", _summary_html(summary), []), encoding="utf-8")
    (folder / "table.html").write_text(_page("ITEM 표", "table.html", TABLE_BODY,
                                                ["data/table.js", "assets/report.js"]), encoding="utf-8")
    (folder / "analysis.html").write_text(_page("ITEM 분석", "analysis.html", ANALYSIS_BODY,
                                                   ["assets/echarts.min.js", "data/table.js", "data/index.js",
                                                    "assets/report.js"]), encoding="utf-8")

    has_raw = bool(a.por and a.doe)
    rows = [[_json_value(v) for v in row] for row in table.itertuples(index=False, name=None)]
    table_text = "window.__dcTable = " + json.dumps({
        "cols": list(table.columns), "rows": rows,
        "meta": {"name": folder.name, "anon": anon, "n_items": len(table), "chunk_size": CHUNK_SIZE,
                 "chunks": has_raw, "images": a.images, "overall": summary["overall"]},
    }, ensure_ascii=False, allow_nan=False) + ";\n"
    (data / "table.js").write_text(table_text, encoding="utf-8")
    if len(table_text.encode("utf-8")) > 5 * 1024 * 1024:
        print("경고: data/table.js 가 5 MB를 넘습니다. 첫 화면이 느려질 수 있습니다.", file=sys.stderr)

    for old in chunks_dir.iterdir():
        if re.fullmatch(r"c\d{5}\.js", old.name):
            old.unlink()
    index = {}
    if not has_raw:
        print("경고: --por/--doe 가 없어 ITEM 원데이터 chunk 를 만들지 않았습니다.", file=sys.stderr)
    else:
        wide, por_cols, units = por_doe_compare.load_wide(a)
        groups = {item: group for item, group in wide.groupby("ITEM", sort=False)}
        items = _read_csv(out / "items.csv")
        die_cols = [key for key in a.key.split(",") if key != "ITEM"]
        value_cols = [*por_cols, "DOE"]
        chunk_lines = []
        for position, row in enumerate(table.to_dict("records")):
            key = str(row["row"])
            raw_item = items.iloc[position]["ITEM"]
            group = groups.get(raw_item)
            if group is None:
                die, values = [], []
            else:
                die = [[_json_value(v) for v in values_in] for values_in in
                       group[die_cols].itertuples(index=False, name=None)]
                values = [[_json_value(v) for v in values_in] for values_in in
                          group[value_cols].itertuples(index=False, name=None)]
            payload = {"key": key, "item": _json_value(row["ITEM"]), "unit": _json_value(units.get(raw_item)),
                       "cols": value_cols, "die": die, "v": values}
            chunk_lines.append(f"window.__dcItem[{json.dumps(key)}] = "
                               f"{json.dumps(payload, ensure_ascii=False, allow_nan=False)};\n")
            chunk_number = position // CHUNK_SIZE
            index[key] = chunk_number
            if len(chunk_lines) == CHUNK_SIZE or position == len(table) - 1:
                text = "window.__dcItem = window.__dcItem || {};\n" + "".join(chunk_lines)
                (chunks_dir / f"c{chunk_number:05d}.js").write_text(text, encoding="utf-8")
                chunk_lines = []
    _write_js(data / "index.js", "__dcIndex", index)
    print(f"report v2 브라우저 페이지: {folder / 'index.html'}")


def _add_optional_common_args(ap: argparse.ArgumentParser) -> None:
    """por_doe_compare.add_common_args 와 같되, 페이지만 만들 수 있게 선택으로 둔다."""
    ap.add_argument("--por", nargs="+", action="append", required=False,
                    help="POR 1회분. 회차마다 --por 를 따로")
    ap.add_argument("--doe", nargs="+", required=False, help="DOE 1회분")
    ap.add_argument("--r", type=float, default=0.05, help="허용폭 = r × |POR| + POR 회차 흔들림 (기본 0.05)")
    ap.add_argument("--level", help="item_info CSV: ITEM,LEVEL,CALCVAL,DERIVED. 장비 분해능·정확도와 blank 환산에 씀")
    ap.add_argument("--blank", nargs="*", default=[], help="blank 데이터. LoQ 하한으로만 씀")
    ap.add_argument("--blank-map", help="CSV ITEM,BLANK_ITEM. 없으면 같은 이름끼리 연결")
    ap.add_argument("--key", default="WAFERID,COORD_X_Y,ITEM")
    ap.add_argument("--encoding", default="auto")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out_folder", type=Path)
    ap.add_argument("--anon", action="store_true")
    ap.add_argument("--images", choices=("fail", "fail+pending", "all", "none"), default="fail",
                    help="R3에서 넣을 그림 범위. 현재는 meta 에만 저장")
    _add_optional_common_args(ap)
    a = ap.parse_args(argv)
    if bool(a.por) != bool(a.doe):
        ap.error("--por 와 --doe 는 함께 주거나 함께 생략해야 합니다")
    table, summary = write_reports(a.out_folder, anon=a.anon)
    _write_pages(table, summary, a.out_folder, a.anon, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
