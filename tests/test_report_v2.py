"""새 브라우저 리포트의 상대 경로, chunk, 익명 출력과 원데이터 값을 검사한다."""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import dcc  # noqa: E402
import golden_cases as gc  # noqa: E402
import item_view  # noqa: E402
import por_doe_compare  # noqa: E402
import report_v2  # noqa: E402
import simple_xlsx  # noqa: E402

ECHARTS_SHA256 = "bf4a223524e40b77c304bec67e1222cf551f14880cf42c69dc046558e11c07b1"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("report_v2_pages")
    data = base / "por3"
    gc.make_por3(data)
    out = base / "out"
    common = [*(a for k in (1, 2, 3) for a in ("--por", data / f"por_run{k}")), "--doe", data / "doe",
              "--level", data / "level.csv", "--blank", data / "blank", "--blank-map", data / "blank_map.csv"]
    gc._run([ROOT / "por_doe_compare.py", *common, "--out", out])
    gc._run([ROOT / "raw_stats.py", *common, "--out", out])
    gc._run([ROOT / "loq_check.py", "--input", out / "items.csv", "--out", out, *common])
    gc._run([ROOT / "report_v2.py", out, *common])
    gc._run([ROOT / "report_v2.py", out, *common, "--anon"])
    return {"base": base, "out": out, "common": common,
            "items": pd.read_csv(out / "items.csv", encoding="utf-8-sig"),
            "table": pd.read_csv(out / "report" / "table.csv", encoding="utf-8-sig")}


def read_assignment(path: Path, name: str):
    text = path.read_text(encoding="utf-8").strip()
    prefix = f"window.{name} = "
    assert text.startswith(prefix) and text.endswith(";"), path
    return json.loads(text[len(prefix):-1])


def test_pages_assets_and_all_html_references_are_local(built):
    folder = built["out"] / "report"
    expected = ["index.html", "table.html", "analysis.html", "assets/report.js", "assets/report.css",
                "assets/echarts.min.js", "assets/echarts.LICENSE.txt", "assets/echarts.NOTICE.txt",
                "data/table.js", "data/index.js"]
    for relative in expected:
        assert (folder / relative).is_file(), relative
    for page in ("index.html", "table.html", "analysis.html"):
        text = (folder / page).read_text(encoding="utf-8")
        for ref in re.findall(r"(?:src|href)=\"([^\"]+)\"", text):
            target = ref.split("#", 1)[0]
            if not target:
                continue
            assert not target.startswith(("http:", "https:", "//", "/")), (page, ref)
            assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target), (page, ref)
            assert (folder / target).is_file(), (page, ref)


def test_chunk_names_counts_and_index_cover_every_key_exactly_once(built):
    folder = built["out"] / "report"
    index = read_assignment(folder / "data" / "index.js", "__dcIndex")
    chunks = sorted((folder / "data" / "chunks").iterdir())
    assert all(re.fullmatch(r"c\d{5}\.js", path.name) for path in chunks)
    assert len(chunks) == math.ceil(len(built["items"]) / 100)
    assert set(index) == {str(row) for row in built["table"]["row"]}
    seen = {}
    for path in chunks:
        keys = re.findall(r"window\.__dcItem\[\"([^\"]+)\"\] =", path.read_text(encoding="utf-8"))
        for key in keys:
            assert key not in seen, (key, seen.get(key), path.name)
            seen[key] = path.name
    assert set(seen) == set(index)
    for key, chunk_number in index.items():
        assert seen[key] == f"c{chunk_number:05d}.js"


def test_table_js_matches_items_rows_and_table_csv_columns(built):
    payload = read_assignment(built["out"] / "report" / "data" / "table.js", "__dcTable")
    assert len(payload["rows"]) == len(built["items"])
    assert payload["cols"] == list(built["table"].columns)
    assert payload["meta"]["n_items"] == len(built["items"])
    assert payload["meta"]["chunk_size"] == 100
    assert payload["meta"]["chunks"] is True


def test_table_xlsx_matches_table_csv_and_page_links_it(built):
    folders = ("report", "report_anon")
    for folder in folders:
        assert (built["out"] / folder / "table.xlsx").is_file(), folder

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(built["out"] / "report" / "table.xlsx") as zf:
        root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
    rows = root.findall(".//m:sheetData/m:row", ns)

    columns = list(pd.read_csv(built["out"] / "report" / "table.csv", encoding="utf-8-sig", nrows=0).columns)
    assert columns == list(built["table"].columns)
    table = pd.read_csv(built["out"] / "report" / "table.csv", encoding="utf-8-sig", float_precision="round_trip")

    # (a) header row
    header = [c.find("m:is/m:t", ns).text for c in rows[0].findall("m:c", ns)]
    assert header == columns

    # (b) one header row plus one row per table row
    assert len(rows) == len(table) + 1

    # Map each data row (1-based) to {column letter: cell element}.
    cells_by_row = {}
    for i, row in enumerate(rows[1:], start=1):
        cells_by_row[i] = {c.get("r").rstrip("0123456789"): c for c in row.findall("m:c", ns)}

    # (c) numeric columns hold the exact csv values; (d) NaN means no cell at all.
    assert "center" in table.columns and "delta" in table.columns
    numeric = ("center", "delta", "delta_pct", "ms3_limit_POR1", "ms3_limit_pct_POR1")
    for name in numeric:
        if name not in table.columns:
            continue
        letter = simple_xlsx.col_letter(columns.index(name))
        for r, value in enumerate(table[name], start=1):
            cells = cells_by_row[r]
            if pd.isna(value):
                assert letter not in cells, (name, r)
                continue
            assert letter in cells, (name, r)
            cell = cells[letter]
            assert cell.get("t") != "inlineStr", (name, r)
            assert float(cell.find("m:v", ns).text) == float(value), (name, r)

    # (e) each page links the xlsx and states the row count
    for folder in folders:
        n = len(pd.read_csv(built["out"] / folder / "table.csv", encoding="utf-8-sig"))
        text = (built["out"] / folder / "table.html").read_text(encoding="utf-8")
        assert 'href="table.xlsx"' in text, folder
        assert f"전체 {n}행" in text, folder


def test_table_page_has_verdict_and_column_panels(built):
    text = (built["out"] / "report" / "table.html").read_text(encoding="utf-8")
    verdicts = re.findall(r'<input type="checkbox" name="verdict" value="([^"]+)" checked>', text)
    assert verdicts == list(report_v2.VERDICTS)
    for expected in ('id="verdict-panel"', 'id="column-panel"', 'id="cols-all"', 'id="cols-default"',
                     'id="column-list"'):
        assert expected in text, expected
    count = f'<span id="col-count">{1 + len(report_v2.TABLE_DEFAULT_COLUMNS)}/{len(built["table"].columns)}</span>'
    assert count in text
    assert 'href="table.xlsx"' in text
    assert f"전체 {len(built['table'])}행" in text


def test_table_js_default_cols_match_constant_and_exist(built):
    payload = read_assignment(built["out"] / "report" / "data" / "table.js", "__dcTable")
    defaults = payload["meta"]["default_cols"]
    assert defaults == list(report_v2.TABLE_DEFAULT_COLUMNS)
    for name in defaults:
        assert name in payload["cols"], name
    assert len(set(defaults)) == 17


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_row_passes_and_visible_column_order():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
const cols = ['row', 'ITEM', 'data_type', 'verdict_final', 'center', 'zone', 'reason', 'delta'];
const defaults = ['data_type', 'verdict_final', 'center', 'delta'];
const rows = [['A', 'LoQ', '차이'], ['B', 'LoQ', '동등'], ['C', 'normal', '차이'],
              ['D', 'normal', '미결'], ['E', 'LoQ', '판정 제외']];
const idx = {{item: 0, type: 1, verdict: 2}};
function pick(state) {{
  return rows.filter(r => h.rowPasses(r, idx, state)).map(r => r[0]);
}}
console.log(JSON.stringify({{
  def: h.visibleColumnOrder(cols, defaults, defaults),
  extra: h.visibleColumnOrder(cols, defaults, defaults.concat(['zone'])),
  extraTwo: h.visibleColumnOrder(cols, defaults, ['reason', 'center', 'row']),
  noItem: h.visibleColumnOrder(cols, defaults, []),
  verdictOnly: pick({{filter: 'all', query: '', verdicts: ['차이']}}),
  verdictAndLoq: pick({{filter: 'loq', query: '', verdicts: ['차이']}}),
  verdictEmpty: pick({{filter: 'all', query: '', verdicts: []}}),
  verdictNull: pick({{filter: 'all', query: '', verdicts: null}}),
  verdictAll: pick({{filter: 'all', query: '', verdicts: ['동등', '미결', '차이', '판정 제외']}}),
  searchAndNotLoq: pick({{filter: 'not-loq', query: 'd', verdicts: null}})
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert values["def"] == [1, 2, 3, 4, 7]
    assert values["extra"] == [1, 2, 3, 4, 7, 5]
    assert values["extraTwo"] == [1, 4, 0, 6]
    assert values["noItem"] == [1]
    assert values["verdictOnly"] == ["A", "C"]
    assert values["verdictAndLoq"] == ["A"]
    assert values["verdictEmpty"] == []
    assert values["verdictNull"] == ["A", "B", "C", "D", "E"]
    assert values["verdictAll"] == ["A", "B", "C", "D", "E"]
    assert values["searchAndNotLoq"] == ["D"]


def legacy_row(zone, verdict_final, shifts, sigmas):
    row = {"zone": zone, "verdict_final": verdict_final}
    for k, (shift, sigma) in enumerate(zip(shifts, sigmas), start=1):
        row[f"med_shift_POR{k}"] = shift
        row[f"sigma_ratio_POR{k}"] = sigma
    return row


def test_legacy_verdict_rules():
    nan = float("nan")
    loq_zones = ("검출한계 이하", "검출~정량")
    for zone in loq_zones:
        for verdict in ("동등", "미결", "차이"):
            row = legacy_row(zone, verdict, [9.0, 9.0, 9.0], [9.0, 9.0, 9.0])
            assert report_v2.legacy_verdict(row, 3) == (verdict, ""), (zone, verdict)

    # 정량: 한계값(같음)은 실패가 아니다.
    assert report_v2.legacy_verdict(legacy_row("정량", "차이", [3.0] * 3, [1.8] * 3), 3) == ("Pass", "")
    shift_por2 = legacy_row("정량", "차이", [0.0, 3.01, 0.0], [1.0] * 3)
    assert report_v2.legacy_verdict(shift_por2, 3) == ("Fail", "shift")
    sigma_por3 = legacy_row("정량", "차이", [0.0] * 3, [1.0, 1.0, 1.81])
    assert report_v2.legacy_verdict(sigma_por3, 3) == ("Fail", "sigma")
    both = legacy_row("정량", "차이", [3.5, 0.0, 0.0], [1.0, 1.9, 1.0])
    assert report_v2.legacy_verdict(both, 3) == ("Fail", "shift / sigma")
    one_of_three = legacy_row("정량", "동등", [0.0, 0.0, 3.5], [1.0] * 3)
    assert report_v2.legacy_verdict(one_of_three, 3)[0] == "Fail"

    # 값 없음: NaN 과 None 은 모두 누락 실행이다.
    assert report_v2.legacy_verdict(legacy_row("정량", "Pass", [nan] * 3, [nan] * 3), 3) == ("판정 불가", "값 없음")
    none_row = legacy_row("정량", "Pass", [None] * 3, [None] * 3)
    assert report_v2.legacy_verdict(none_row, 3) == ("판정 불가", "값 없음")
    # 실패가 누락보다 우선한다.
    missing_fail = legacy_row("정량", "Pass", [nan, 5.0, 1.0], [nan, 1.0, 1.0])
    assert report_v2.legacy_verdict(missing_fail, 3) == ("Fail", "shift")
    missing_ok = legacy_row("정량", "Pass", [nan, 0.5, 0.5], [nan, 1.0, 1.0])
    assert report_v2.legacy_verdict(missing_ok, 3) == ("판정 불가", "값 없음")

    # die 부족: shift/sigma 와 무관하게 항상 판정 불가이고, verdict_final 과도 무관하다.
    for verdict in report_v2.VERDICTS:
        under = legacy_row("die 부족", verdict, [0.5] * 3, [1.0] * 3)
        assert report_v2.legacy_verdict(under, 3) == ("판정 불가", "die 부족"), verdict
        shift = legacy_row("die 부족", verdict, [0.0, 3.5, 0.0], [1.0] * 3)
        assert report_v2.legacy_verdict(shift, 3) == ("판정 불가", "die 부족"), verdict
        sigma = legacy_row("die 부족", verdict, [0.0] * 3, [9.0] * 3)
        assert report_v2.legacy_verdict(sigma, 3) == ("판정 불가", "die 부족"), verdict
        missing = legacy_row("die 부족", verdict, [nan] * 3, [nan] * 3)
        assert report_v2.legacy_verdict(missing, 3) == ("판정 불가", "die 부족"), verdict

    # 판정 제외: verdict_final 을 복사하지 않고 같은 shift/sigma 규칙을 적용한다.
    for zone in ("판정 제외",):
        ok = legacy_row(zone, "차이", [0.5] * 3, [1.0] * 3)
        assert report_v2.legacy_verdict(ok, 3) == ("Pass", ""), zone
        bad = legacy_row(zone, "동등", [0.5, 3.5, 0.5], [1.0] * 3)
        assert report_v2.legacy_verdict(bad, 3) == ("Fail", "shift"), zone

    # sigma_ratio = 0 은 정상 값이다.
    zero_sigma = legacy_row("정량", "차이", [0.5] * 3, [0.0] * 3)
    assert report_v2.legacy_verdict(zero_sigma, 3) == ("Pass", "")

    # n_runs 가 0 이하이면 값 없음이다.
    assert report_v2.legacy_verdict(legacy_row("정량", "Pass", [3.0] * 3, [1.8] * 3), 0) == ("판정 불가", "값 없음")


def test_table_outputs_have_legacy_columns_after_verdict_final(built):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    loq_zones = ("검출한계 이하", "검출~정량")
    csv_columns = {}
    for folder in ("report", "report_anon"):
        base = built["out"] / folder
        columns = list(pd.read_csv(base / "table.csv", encoding="utf-8-sig", nrows=0).columns)
        csv_columns[folder] = columns
        i = columns.index("verdict_final")
        assert columns[i + 1:i + 3] == ["verdict_legacy", "verdict_legacy_reason"], folder

        payload = json.loads((base / "table.json").read_text(encoding="utf-8"))
        assert payload["cols"] == columns, folder
        js = read_assignment(base / "data" / "table.js", "__dcTable")
        assert js["cols"] == columns, folder

        with zipfile.ZipFile(base / "table.xlsx") as zf:
            root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        first = root.find(".//m:sheetData/m:row", ns)
        header = [c.find("m:is/m:t", ns).text for c in first.findall("m:c", ns)]
        assert header == columns, folder

    columns = csv_columns["report"]
    table = pd.read_csv(built["out"] / "report" / "table.csv", encoding="utf-8-sig", float_precision="round_trip")
    assert len(table) == len(built["items"])
    assert all(v in report_v2.LEGACY_VERDICTS for v in table["verdict_legacy"])
    n_runs = sum(1 for c in columns if re.fullmatch(r"med_shift_POR\d+", c))
    assert n_runs >= 1
    for i, row in table.iterrows():
        reason = "" if pd.isna(row["verdict_legacy_reason"]) else row["verdict_legacy_reason"]
        if row["zone"] in loq_zones:
            assert row["verdict_legacy"] == row["verdict_final"], i
            assert reason == "", i
        else:
            expected = report_v2.legacy_verdict(row.to_dict(), n_runs)
            assert (row["verdict_legacy"], reason) == expected, i
    for i, row in table.iterrows():
        if row["zone"] != "die 부족":
            continue
        reason = "" if pd.isna(row["verdict_legacy_reason"]) else row["verdict_legacy_reason"]
        assert row["verdict_legacy"] == "판정 불가", i
        assert reason == "die 부족", i
    assert table["verdict_final"].tolist() == built["items"]["verdict_final"].tolist()


def test_table_page_has_verdict_mode_switch(built):
    folder = built["out"] / "report"
    text = (folder / "table.html").read_text(encoding="utf-8")
    assert '<div class="verdict-mode" id="verdict-mode"' in text
    radios = ('<label><input type="radio" name="verdict-mode" value="A" checked> 방식 A (현재: TOST·LoQ)</label>'
              '<label><input type="radio" name="verdict-mode" value="B"> 방식 B (기존식: shift·sigma)</label>')
    assert radios in text
    assert 'value="B" checked' not in text

    verdicts = re.findall(r'<input type="checkbox" name="verdict" value="([^"]+)" checked>', text)
    assert verdicts == list(report_v2.VERDICTS)

    payload = read_assignment(folder / "data" / "table.js", "__dcTable")
    assert payload["meta"]["verdict_modes"] == {
        "A": {"column": "verdict_final", "values": list(report_v2.VERDICTS)},
        "B": {"column": "verdict_legacy", "values": list(report_v2.LEGACY_VERDICTS)},
    }
    assert payload["meta"]["default_cols"] == list(report_v2.TABLE_DEFAULT_COLUMNS)

    count = f'<span id="col-count">{1 + len(report_v2.TABLE_DEFAULT_COLUMNS)}/{len(built["table"].columns)}</span>'
    assert count in text


def test_index_page_has_verdict_mode_switch_and_both_card_sets(built):
    radios = ('<label><input type="radio" name="verdict-mode" value="A" checked> 방식 A (현재: TOST·LoQ)</label>'
              '<label><input type="radio" name="verdict-mode" value="B"> 방식 B (기존식: shift·sigma)</label>')
    folder = built["out"] / "report"
    text = (folder / "index.html").read_text(encoding="utf-8")
    assert '<div class="verdict-mode" id="verdict-mode"' in text
    assert radios in text
    assert 'value="A" checked' in text
    assert 'value="B" checked' not in text
    assert "<script" not in text

    # 방식 A 카드: 최종 판정 (verdict_final)
    section_a = re.search(r'id="mode-a-cards".*?</section>', text, re.S)
    assert section_a, "mode-a-cards 섹션이 없습니다"
    pairs_a = re.findall(r"<dt>([^<]*)</dt><dd>([^<]*)</dd>", section_a.group(0))
    table_csv = pd.read_csv(folder / "table.csv", encoding="utf-8-sig", keep_default_na=False)
    final_counts = table_csv["verdict_final"].astype(str).value_counts()
    assert [(v, int(n)) for v, n in pairs_a] == [(v, int(final_counts.get(v, 0))) for v in report_v2.VERDICTS]

    # 방식 B 카드: 기존식 판정 (verdict_legacy), 0 건도 포함
    section_b = re.search(r'id="mode-b-cards".*?</section>', text, re.S)
    assert section_b, "mode-b-cards 섹션이 없습니다"
    pairs_b = re.findall(r"<dt>([^<]*)</dt><dd>([^<]*)</dd>", section_b.group(0))
    legacy_counts_csv = table_csv["verdict_legacy"].astype(str).value_counts()
    assert [(v, int(n)) for v, n in pairs_b] == [(v, int(legacy_counts_csv.get(v, 0)))
                                                  for v in report_v2.LEGACY_VERDICTS]

    # Fail 사유 줄: table.csv 의 Fail 행을 사유별로 센 값과 같아야 한다.
    reasons_line = re.search(r'<p class="legacy-reasons">([^<]*)</p>', section_b.group(0))
    assert reasons_line, "legacy-reasons 줄이 없습니다"
    reasons_match = re.fullmatch(r"Fail 사유: shift (\d+) · sigma (\d+) · shift / sigma (\d+)", reasons_line.group(1))
    assert reasons_match, reasons_line.group(1)
    fail_rows = table_csv[table_csv["verdict_legacy"] == "Fail"]
    fail_reason_counts = fail_rows["verdict_legacy_reason"].value_counts()
    expected_reasons = [int(fail_reason_counts.get(r, 0)) for r in ("shift", "sigma", "shift / sigma")]
    assert [int(g) for g in reasons_match.groups()] == expected_reasons

    # summary.json: 방식 A 판정 개수는 그대로, overall 은 같은 의미, 방식 B 값은 table.csv 와 같다.
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["verdict_counts"] == {v: int(final_counts.get(v, 0)) for v in report_v2.VERDICTS}
    assert summary["overall"] in {"동등", "미결", "차이", "판정 없음"}
    counts = summary["verdict_counts"]
    if counts["차이"]:
        expected_overall = "차이"
    elif counts["미결"]:
        expected_overall = "미결"
    elif counts["동등"]:
        expected_overall = "동등"
    else:
        expected_overall = "판정 없음"
    assert summary["overall"] == expected_overall
    assert summary["legacy_counts"] == {v: int(legacy_counts_csv.get(v, 0)) for v in report_v2.LEGACY_VERDICTS}
    assert summary["legacy_fail_reasons"] == dict(zip(("shift", "sigma", "shift / sigma"), expected_reasons))

    # 익명 출력도 같은 라디오 줄을 가진다.
    anon_text = (built["out"] / "report_anon" / "index.html").read_text(encoding="utf-8")
    assert radios in anon_text


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_method_b_filter_and_mode_helpers():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
const rows = [['A', 'LoQ', '동등', '동등'], ['B', 'normal', '동등', 'Fail'], ['C', 'normal', '차이', 'Pass'],
              ['D', 'LoQ', '미결', '미결'], ['E', 'normal', '판정 제외', '판정 불가'], ['F', 'LoQ', '차이', '차이'],
              ['G', 'normal', '동등', 'Fail']];
const LEGACY = ['Pass', 'Fail', '판정 불가', '동등', '미결', '차이'];
const idxB = {{item: 0, type: 1, verdict: 3}};
const idxA = {{item: 0, type: 1, verdict: 2}};
function pick(idx, state) {{
  return rows.filter(r => h.rowPasses(r, idx, state)).map(r => r[0]);
}}
const d1 = ['data_type', 'verdict_final', 'center'];
const d2 = ['data_type', 'center'];
console.log(JSON.stringify({{
  bFail: pick(idxB, {{filter: 'all', query: '', verdicts: ['Fail']}}),
  loqFail: pick(idxB, {{filter: 'loq', query: '', verdicts: ['Fail']}}),
  notLoqFailPass: pick(idxB, {{filter: 'not-loq', query: '', verdicts: ['Fail', 'Pass']}}),
  empty: pick(idxB, {{filter: 'all', query: '', verdicts: []}}),
  nul: pick(idxB, {{filter: 'all', query: '', verdicts: null}}),
  allLegacy: pick(idxB, {{filter: 'all', query: '', verdicts: LEGACY}}),
  aDiff: pick(idxA, {{filter: 'all', query: '', verdicts: ['차이']}}),
  modeCols: h.modeDefaultCols(d1, 'verdict_final', 'verdict_legacy'),
  d1After: d1,
  modeAbsent: h.modeDefaultCols(d2, 'verdict_final', 'verdict_legacy'),
  absentIsCopy: h.modeDefaultCols(d2, 'verdict_final', 'verdict_legacy') !== d2,
  counts: h.verdictCounts(rows, 3, LEGACY),
  noIndex: h.verdictCounts(rows, -1, ['a', 'b'])
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert values["bFail"] == ["B", "G"]
    assert values["loqFail"] == []
    assert values["notLoqFailPass"] == ["B", "C", "G"]
    assert values["empty"] == []
    assert values["nul"] == ["A", "B", "C", "D", "E", "F", "G"]
    assert values["allLegacy"] == ["A", "B", "C", "D", "E", "F", "G"]
    assert values["aDiff"] == ["C", "F"]
    assert values["modeCols"] == ["data_type", "verdict_legacy", "center"]
    assert values["d1After"] == ["data_type", "verdict_final", "center"]
    assert values["modeAbsent"] == ["data_type", "center"]
    assert values["absentIsCopy"] is True
    assert values["counts"] == [1, 2, 1, 1, 1, 1]
    assert values["noIndex"] == [0, 0]


def test_anon_has_no_real_item_or_blank_name_in_text_outputs(built):
    folder = built["out"] / "report_anon"
    names = set(built["items"]["ITEM"].dropna()) | set(built["items"]["blank_item"].dropna())
    for path in folder.rglob("*"):
        if not path.is_file() or path.suffix not in {".html", ".js", ".csv", ".json"}:
            continue
        if path.parent == folder / "assets" and path.name.startswith("echarts."):
            continue
        text = path.read_text(encoding="utf-8-sig")
        assert not [name for name in names if str(name) in text], path.relative_to(folder)


def test_vendor_and_copied_echarts_have_expected_sha256(built):
    source = ROOT / "assets" / "report" / "vendor" / "echarts.min.js"
    copied = built["out"] / "report" / "assets" / "echarts.min.js"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ECHARTS_SHA256
    assert hashlib.sha256(copied.read_bytes()).hexdigest() == ECHARTS_SHA256


def test_without_raw_args_succeeds_with_table_and_empty_index(built):
    out = built["base"] / "without_raw"
    out.mkdir()
    shutil.copyfile(built["out"] / "items.csv", out / "items.csv")
    shutil.copyfile(built["out"] / "raw_stats.csv", out / "raw_stats.csv")
    gc._run([ROOT / "report_v2.py", out])
    payload = read_assignment(out / "report" / "data" / "table.js", "__dcTable")
    assert len(payload["rows"]) == len(built["items"])
    assert payload["meta"]["chunks"] is False
    assert payload["meta"]["img_rows"] == []
    assert payload["meta"]["log_bases"] == list(item_view.LOG_BASES)
    assert read_assignment(out / "report" / "data" / "index.js", "__dcIndex") == {}


def test_table_has_static_column_docs_and_matching_metadata(built):
    folder = built["out"] / "report"
    text = (folder / "table.html").read_text(encoding="utf-8")
    for expected in (
            "median shift = |median_ref − median_com| / σ_ref",
            "sigma ratio = σ_com / σ_ref",
            "σ = 표본 표준편차(n−1)",
            "가공 없음 (원 데이터 전체)",
            report_v2.OVERALL_RULE,
            'id="col-docs"',
    ):
        assert expected in text
    payload = read_assignment(folder / "data" / "table.js", "__dcTable")
    formula = payload["meta"]["col_docs"]["med_shift_POR1"]["formula"]
    assert "|median_POR1 − median_DOE| / σ_POR1" in formula


def test_ms3_column_docs_and_table_column_order(built):
    folder = built["out"] / "report"
    payload = read_assignment(folder / "data" / "table.js", "__dcTable")
    col_docs = payload["meta"]["col_docs"]
    assert "3 · σ_POR1" in col_docs["ms3_limit_POR1"]["formula"]
    assert "med_shift ≤ 3" in col_docs["ms3_limit_POR1"]["formula"]
    assert "|median_POR1| × 100" in col_docs["ms3_limit_pct_POR1"]["formula"]
    cols = payload["cols"]
    assert cols[cols.index("sigma_ratio_POR1") + 1] == "ms3_limit_POR1"
    assert cols[cols.index("ms3_limit_POR1") + 1] == "ms3_limit_pct_POR1"
    assert cols[cols.index("ms3_limit_pct_POR1") + 1] == "raw_note_POR1"


def test_column_docs_sit_inside_main_above_closing_tag(built):
    text = (built["out"] / "report" / "table.html").read_text(encoding="utf-8")
    docs_at = text.index('id="col-docs"')
    assert text.index("<main") < docs_at < text.index("</main>", docs_at)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_pure_number_extent_and_margin_helpers():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
const tiny = h.extent([1e-13, 1e-13], false);
console.log(JSON.stringify({{
  formatted: [h.fmtNum(1.23456e-13), h.fmtNum(0.5), h.fmtNum(NaN), h.fmtNum(null), h.fmtNum(0)],
  large: h.fmtNum(123456789),
  smallScale: h.displayScale([1e-13, 3e-13]),
  regularScale: h.displayScale([1, 20]),
  tinyWidth: tiny.max - tiny.min,
  extraMax: h.extent([1, 2], false, [10]).max,
  abs: h.marginFor({{verdict_basis: 'abs', abs_delta: 2, delta: 1}}, []),
  accuracy: h.marginFor({{verdict_basis: 'accuracy', accuracy_margin: 3, delta: 2}}, []),
  limit: h.marginFor({{verdict_basis: 'limit', delta: 2}}, []),
  log: h.marginFor({{verdict_basis: 'log', delta_log: 0.2, delta: 5}}, ['log'])
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert values["formatted"] == ["1.23e-13", "0.500", "—", "—", "0"]
    assert "e" in values["large"]
    assert values["smallScale"]["k"] == -13
    assert values["smallScale"]["label"] == "×1e-13"
    assert values["regularScale"]["factor"] == 1
    assert values["tinyWidth"] < 1e-12
    assert values["extraMax"] >= 10
    assert values["abs"] == {"value": 2, "name": "abs_delta"}
    assert values["accuracy"]["value"] == 3
    assert values["limit"] is None
    assert values["log"] == {"value": 0.2, "name": "delta_log"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_loq_placement_number_format_and_raw_tooltip():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
console.log(JSON.stringify({{
  placements: [h.loqPlacement(5, 0, 1), h.loqPlacement(-5, 0, 1),
               h.loqPlacement(0.5, 0, 1), h.loqPlacement(NaN, 0, 1)],
  formatted: [h.fmtNum(0.030263), h.fmtNum(1.4e-11), h.fmtNum(12345),
              h.fmtNum(0.5), h.fmtNum(61), h.fmtNum(0), h.fmtNum(null)],
  sigZeros: [h.fmtNum(0.450211), h.fmtNum(1.1016)],
  edge: h.edgeLabel('LoQ', 1.4e-11, 'above', 'y'),
  tinyTooltip: h.tooltipValueFormatter(1e-11)(3.0263),
  regularTooltip: h.tooltipValueFormatter(1)(0.030263)
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert values["placements"] == ["above", "below", "in", None]
    assert values["formatted"] == ["0.0303", "1.40e-11", "1.23e4", "0.500", "61", "0", "—"]
    assert values["sigZeros"] == ["0.450", "1.10"]
    assert values["edge"] == "LoQ 1.40e-11 (범위 밖 ↑)"
    assert values["tinyTooltip"] == "3.0263e-11"
    assert values["regularTooltip"] == "0.030263"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_ci_axis_ignores_loq_and_moves_outside_lines_to_edge():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
const item = {{
  item: 'IT00006', unit: '', cols: ['POR1', 'POR2', 'DOE'],
  die: [['1'], ['2'], ['3'], ['4']],
  v: [[0.50, 0.50, 0.52], [0.50, 0.50, 0.53],
      [0.50, 0.50, 0.54], [0.50, 0.50, 0.55]]
}};
const record = {{verdict_basis: 'delta', center: 0.03, ci_low: 0.02, ci_high: 0.04,
                 delta: 0.023, LoQ: 0.05, por_median: 0.5}};
const outside = h.ciOption(item, record, ['log']);
const inside = h.ciOption(item, Object.assign({{}}, record, {{LoQ: 0.02, por_median: 0}}), ['log']);
function summary(option) {{
  return {{min: option.yAxis.min, max: option.yAxis.max,
           seriesNames: option.series.map(s => s.name),
           graphics: (option.graphic || []).map(g => g.style.text),
           backgrounds: (option.graphic || []).map(g => g.style.backgroundColor)}};
}}
console.log(JSON.stringify({{outside: summary(outside), inside: summary(inside)}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    outside = values["outside"]
    assert -0.04 < outside["min"] < 0
    assert 0.05 < outside["max"] < 0.08
    assert outside["min"] > -0.1
    assert "DOE가 LoQ에 닿는 이동" not in outside["seriesNames"]
    assert len(outside["graphics"]) == 1
    assert outside["backgrounds"] == ["rgba(255,255,255,0.9)"]
    merged = outside["graphics"][0]
    assert " / " in merged
    assert merged.startswith("LoQ 이동 ")
    assert merged.endswith("(범위 밖 ↓)")
    inside = values["inside"]
    assert inside["seriesNames"].count("DOE가 LoQ에 닿는 이동") == 2
    assert inside["graphics"] == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_edge_labels_same_name_merge_and_different_names_stack():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
const opt = {{}};
const counts = {{}};
h.appendEdgeLabel(opt, counts, 'LoD', 1, 'below', 'y');
h.appendEdgeLabel(opt, counts, 'LoQ', 2, 'below', 'y');
const stacked = opt.graphic.map(g => ({{bottom: g.bottom, text: g.style.text}}));
h.appendEdgeLabel(opt, counts, 'LoQ', 3, 'below', 'y');
console.log(JSON.stringify({{
  stacked: stacked,
  texts: opt.graphic.map(g => g.style.text),
  styles: opt.graphic.map(g => ({{backgroundColor: g.style.backgroundColor, padding: g.style.padding}}))
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert len(values["stacked"]) == 2
    assert abs(values["stacked"][0]["bottom"] - values["stacked"][1]["bottom"]) >= 18
    assert len(values["texts"]) == 2
    assert values["texts"] == ["LoD 1 (범위 밖 ↓)", "LoQ 2 / 3 (범위 밖 ↓)"]
    for style in values["styles"]:
        assert style["backgroundColor"] == "rgba(255,255,255,0.9)"
        assert style["padding"] == [2, 4]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_log_empty_plan_helper():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
console.log(JSON.stringify({{
  noLoq: h.logEmptyPlan(0, null),
  withLoq: h.logEmptyPlan(0, 1e-12),
  hasPoints: h.logEmptyPlan(5, 1e-12),
  series: h.loqLineSeries(1e-12, 1e-13, 1e-11)
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert values["withLoq"]["empty"] is True
    assert values["withLoq"]["helper"] is True
    assert math.isclose(values["withLoq"]["min"], 1e-13, rel_tol=1e-9)
    assert math.isclose(values["withLoq"]["max"], 1e-11, rel_tol=1e-9)
    assert values["noLoq"] == {"empty": True, "helper": False, "min": None, "max": None}
    assert values["hasPoints"]["empty"] is False
    assert values["hasPoints"]["helper"] is False
    line_a, line_b = values["series"]
    for line in (line_a, line_b):
        assert line["type"] == "line"
        assert line["name"] == "LoQ"
        assert line["symbol"] == "none"
        assert line["lineStyle"]["color"] == "#00A888"
        assert line["tooltip"]["show"] is False
    expected_a = [[1e-13, 1e-12], [1e-11, 1e-12]]
    expected_b = [[1e-12, 1e-13], [1e-12, 1e-11]]
    for got, want in ((line_a["data"], expected_a), (line_b["data"], expected_b)):
        assert len(got) == len(want)
        for got_point, want_point in zip(got, want):
            assert all(math.isclose(g, w, rel_tol=1e-9) for g, w in zip(got_point, want_point)), (got, want)



@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_log_scatter_in_range_loq_is_line_series_not_markline():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
const item = {{
  item: 'IT00030', unit: '', cols: ['POR1', 'POR2', 'DOE'],
  die: [['1'], ['2'], ['3'], ['4']],
  v: [[1e-12, 2e-12, 3e-11], [2e-11, 3e-11, 5e-11],
      [5e-11, 8e-11, 1e-10], [1e-10, 9e-11, 4e-11]]
}};
const logRecord = {{verdict_basis: 'log', delta_log: 0.1, delta: 0.05, LoQ: 5e-12}};
const linearRecord = {{verdict_basis: 'delta', delta: 1e-11, LoQ: 5e-11}};
function loqSeries(option) {{
  return option.series.filter(s => s.name === 'LoQ');
}}
const logOption = h.scatterOption(item, logRecord, true).option;
const linOption = h.scatterOption(item, linearRecord, false).option;
console.log(JSON.stringify({{
  logLoqSeries: loqSeries(logOption).map(s => [s.type, s.data.length]),
  logMarkLineNames: logOption.series[0].markLine.data.map(d => d.name),
  logGraphicTexts: (logOption.graphic || []).map(g => (g.style || {{}}).text),
  linLoqSeries: loqSeries(linOption).length,
  linLoqMarkLines: linOption.series[0].markLine.data.filter(d => d.name === 'LoQ').map(d => 'yAxis' in d)
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert values["logLoqSeries"] == [["line", 2], ["line", 2]]
    assert "LoQ" not in values["logMarkLineNames"]
    assert not any(text.startswith("LoQ ") for text in values["logGraphicTexts"])
    assert values["linLoqSeries"] == 0
    assert values["linLoqMarkLines"] == [True]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_log_axis_ticks_within_one_decade_and_no_zero_label():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
const narrowItem = {{
  item: 'IT00030', unit: '', cols: ['POR1', 'POR2', 'DOE'],
  die: [['1'], ['2'], ['3'], ['4']],
  v: [[1.5e-10, 2e-10, 3e-10], [2.5e-10, 3e-10, 5e-10],
      [5e-10, 6e-10, 4e-10], [4e-10, 1.6e-10, 2e-10]]
}};
const wideItem = {{
  item: 'IT00006', unit: '', cols: ['POR1', 'POR2', 'DOE'],
  die: [['1'], ['2'], ['3'], ['4']],
  v: [[1e-13, 2e-13, 1e-10], [1e-12, 1e-11, 1e-9],
      [5e-11, 3e-10, 2e-13], [1e-10, 1e-9, 4e-12]]
}};
const record = {{verdict_basis: 'log', delta_log: 0.05}};
function ticksOf(min, max) {{
  const t = h.logAxisTicks(min, max);
  return t === null ? null : {{values: t, labels: t.map(h.fmtNum)}};
}}
function axisSummary(option) {{
  return {{
    xTicks: option.xAxis.axisLabel.customValues || null,
    yTicks: option.yAxis.axisLabel.customValues || null,
    xTickShow: option.xAxis.axisTick ? option.xAxis.axisTick.show : null,
    yZeroLabel: option.yAxis.axisLabel.formatter(0),
    yNegLabel: option.yAxis.axisLabel.formatter(-1e-10),
    yPosLabel: option.yAxis.axisLabel.formatter(2e-10)
  }};
}}
console.log(JSON.stringify({{
  narrow: ticksOf(1.2e-10, 8e-10),
  mantissa: ticksOf(3.1, 9.7),
  it30: ticksOf(3.464e-12, 6.631e-11),
  wide: ticksOf(1e-13, 1e-9),
  zero: ticksOf(0, 1),
  narrowOption: axisSummary(h.scatterOption(narrowItem, record, true).option),
  wideOption: axisSummary(h.scatterOption(wideItem, record, true).option)
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)

    for key, min_value, max_value in (("narrow", 1.2e-10, 8e-10), ("mantissa", 3.1, 9.7), ("it30", 3.464e-12, 6.631e-11)):
        ticks = values[key]["values"]
        labels = values[key]["labels"]
        assert len(ticks) >= 2, key
        assert ticks == sorted(ticks), key
        assert all(t > 0 and min_value < t < max_value for t in ticks), key
        assert len(set(labels)) == len(labels), key
        assert "0" not in labels, key

    assert values["it30"]["values"] == [5e-12, 1e-11, 2e-11, 5e-11]
    assert values["narrow"]["values"] == [2e-10, 5e-10]

    for key in ("it30", "narrow"):
        ticks = values[key]["values"]
        for a, b in zip(ticks, ticks[1:]):
            assert b / a >= 1.5, key
        assert not any("2.50" in label for label in values[key]["labels"]), key

    assert values["wide"] is None
    assert values["zero"] is None

    narrow = values["narrowOption"]
    assert len(narrow["xTicks"]) >= 2
    assert len(narrow["yTicks"]) >= 2
    assert narrow["xTickShow"] is True
    assert narrow["yZeroLabel"] == ""
    assert narrow["yNegLabel"] == ""
    assert narrow["yPosLabel"] == "2.00e-10"

    wide = values["wideOption"]
    assert wide["xTicks"] is None
    assert wide["yTicks"] is None


def chunk_item(folder: Path, key: str):
    index = read_assignment(folder / "data" / "index.js", "__dcIndex")
    path = folder / "data" / "chunks" / f"c{index[key]:05d}.js"
    prefix = f'window.__dcItem["{key}"] = '
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            assert line.endswith(";")
            return json.loads(line[len(prefix):-1])
    raise AssertionError(f"{key} not in {path}")


def test_two_chunk_items_have_load_wide_values(built):
    parser = argparse.ArgumentParser()
    por_doe_compare.add_common_args(parser)
    args = parser.parse_args([str(value) for value in built["common"]])
    wide, por_cols, _ = por_doe_compare.load_wide(args)
    folder = built["out"] / "report"
    for item in wide["ITEM"].drop_duplicates().iloc[:2]:
        key = str(built["table"].loc[built["table"]["ITEM"] == item, "row"].iloc[0])
        actual = chunk_item(folder, key)
        assert actual["cols"] == [*por_cols, "DOE"]
        expected_group = wide[wide["ITEM"] == item]
        expected = expected_group[[*por_cols, "DOE"]].to_numpy()
        assert len(actual["v"]) == len(expected)
        assert len(actual["die"]) == len(expected)
        for actual_values, expected_values in zip(actual["v"], expected):
            assert len(actual_values) == len(expected_values)
            for actual_value, expected_value in zip(actual_values, expected_values):
                if pd.isna(expected_value):
                    assert actual_value is None
                else:
                    assert actual_value == pytest.approx(expected_value)


def test_chunk_die_evidence_reproduces_items_rank_ci(built):
    checked = 0
    folder = built["out"] / "report"
    for position, item_row in built["items"].iterrows():
        if str(item_row["verdict_basis"]) == "limit":
            continue
        key = str(built["table"].iloc[position]["row"])
        chunk = chunk_item(folder, key)
        if len(chunk["die"]) < 2:
            continue
        rows = pd.DataFrame(chunk["die"], columns=["WAFERID", "COORD_X_Y"])
        for c, col in enumerate(chunk["cols"]):
            rows[col] = [values[c] for values in chunk["v"]]
        evidence = item_view.die_evidence(rows, item_row)
        assert evidence.n >= 2, key
        ordered = np.sort(evidence.d)
        k = evidence.k
        suffix = "_log" if str(item_row["verdict_basis"]) in item_view.LOG_BASES else ""
        low = item_row["ci_low" + suffix]
        high = item_row["ci_high" + suffix]
        assert ordered[k - 1] == pytest.approx(low, rel=1e-9, abs=1e-15), key
        assert ordered[evidence.n - k] == pytest.approx(high, rel=1e-9, abs=1e-15), key
        lo, hi = ordered[k - 1], ordered[evidence.n - k]
        assert ((lo <= evidence.d) & (evidence.d <= hi)).sum() >= evidence.n - 2 * k + 2, key
        assert low <= item_row["center" + suffix] <= high, key
        checked += 1
    assert checked > 0


@pytest.fixture(scope="module")
def image_modes(built):
    folders = {}
    for mode in ("fail+pending", "none"):
        out = built["base"] / ("images_" + mode.replace("+", "_"))
        out.mkdir()
        shutil.copyfile(built["out"] / "items.csv", out / "items.csv")
        shutil.copyfile(built["out"] / "raw_stats.csv", out / "raw_stats.csv")
        gc._run([ROOT / "report_v2.py", out, *built["common"], "--images", mode])
        folders[mode] = out / "report"
    return folders


def png_files(folder: Path):
    image_dir = folder / "img"
    return sorted(image_dir.glob("*.png")) if image_dir.exists() else []


def test_static_image_modes_counts_names_and_no_data_urls(built, image_modes):
    verdicts = built["table"]["verdict_final"].astype(str)
    cases = ((built["out"] / "report", int((verdicts == "차이").sum())),
             (image_modes["fail+pending"], int(verdicts.isin(["차이", "미결"]).sum())),
             (image_modes["none"], 0))
    for folder, expected in cases:
        files = png_files(folder)
        assert len(files) == expected, folder
        assert all(re.fullmatch(r"i\d{5}\.png", path.name) for path in files)
        if expected == 0:
            assert not (folder / "img").exists() or not any((folder / "img").iterdir())
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix in {".html", ".js"} and not path.name.startswith("echarts."):
                assert "data:image" not in path.read_text(encoding="utf-8"), path.relative_to(folder)


def test_table_meta_log_bases_and_img_rows_match_files(built):
    for name in ("report", "report_anon"):
        folder = built["out"] / name
        meta = read_assignment(folder / "data" / "table.js", "__dcTable")["meta"]
        assert meta["log_bases"] == list(item_view.LOG_BASES)
        assert meta["img_rows"] == [int(path.stem[1:]) for path in png_files(folder)]


def test_anon_static_image_names_do_not_contain_item_names(built):
    folder = built["out"] / "report_anon"
    assert png_files(folder), "기본 fail 실행은 차이 ITEM의 익명 PNG를 만들어야 한다"
    assert all(re.fullmatch(r"i\d{5}\.png", path.name) for path in png_files(folder))


@pytest.fixture(scope="module")
def job_images(built):
    folders = {}
    for jobs in (1, 2):
        out = built["base"] / f"images_jobs_{jobs}"
        out.mkdir()
        shutil.copyfile(built["out"] / "items.csv", out / "items.csv")
        shutil.copyfile(built["out"] / "raw_stats.csv", out / "raw_stats.csv")
        gc._run([ROOT / "report_v2.py", out, *built["common"], "--jobs", jobs])
        folders[jobs] = out / "report"
    return folders


def test_static_image_jobs_match_names_meta_and_bytes(job_images):
    sequential, parallel = job_images[1], job_images[2]
    sequential_files, parallel_files = png_files(sequential), png_files(parallel)
    assert [path.name for path in parallel_files] == [path.name for path in sequential_files]
    sequential_meta = read_assignment(sequential / "data" / "table.js", "__dcTable")["meta"]
    parallel_meta = read_assignment(parallel / "data" / "table.js", "__dcTable")["meta"]
    assert parallel_meta["img_rows"] == sequential_meta["img_rows"]
    assert [path.read_bytes() for path in parallel_files] == [path.read_bytes() for path in sequential_files]


def test_static_image_failure_is_isolated(built, monkeypatch, capsys):
    source_files = png_files(built["out"] / "report")
    target_name = source_files[0].name
    original_plot = report_v2.item_view.plot_item_view

    def fail_target(rows, srow, path):
        if path.name == target_name:
            raise RuntimeError("의도한 실패")
        return original_plot(rows, srow, path)

    monkeypatch.setattr(report_v2.item_view, "plot_item_view", fail_target)
    out = built["base"] / "images_one_failure"
    out.mkdir()
    shutil.copyfile(built["out"] / "items.csv", out / "items.csv")
    shutil.copyfile(built["out"] / "raw_stats.csv", out / "raw_stats.csv")
    report_v2.main([str(out), *map(str, built["common"]), "--jobs", "1"])

    expected = [path.name for path in source_files if path.name != target_name]
    assert [path.name for path in png_files(out / "report")] == expected
    assert "정적 그림 실패" in capsys.readouterr().err


def test_jobs_zero_is_argparse_error(built):
    with pytest.raises(SystemExit):
        report_v2.main([str(built["out"]), "--jobs", "0"])


def test_dcc_report_v2_step_forwards_only_explicit_jobs():
    class ComboStub:
        out = Path("out")

        def raw_args(self):
            return ["--por", "POR"]

    combo = ComboStub()
    assert dcc.report_v2_step(combo, jobs=3)[1][-2:] == ["--jobs", "3"]
    assert "--jobs" not in dcc.report_v2_step(combo, jobs=None)[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 없습니다")
def test_report_js_head_transform_follows_horizontal_scroll():
    module_path = json.dumps(str(ROOT / "assets" / "report" / "report.js"))
    script = f"""
const h = require({module_path});
console.log(JSON.stringify({{
  zero: h.headTransform(0),
  shifted: h.headTransform(240),
  missing: h.headTransform(undefined)
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert values["zero"] == "translateX(0px)"
    assert values["shifted"] == "translateX(-240px)"
    assert values["missing"] == "translateX(0px)"


def css_rule_bodies(selector: str):
    css = (ROOT / "assets" / "report" / "report.css").read_text(encoding="utf-8")
    return re.findall(re.escape(selector) + r"\{([^}]*)\}", css)


def test_report_css_viewport_is_the_only_horizontal_scroller():
    viewport_rules = css_rule_bodies("#dc-viewport")
    assert viewport_rules, "#dc-viewport 규칙이 없습니다"
    for body in viewport_rules:
        assert "overflow-x:hidden" not in body
    assert any("overflow:auto" in body or "overflow-x:auto" in body for body in viewport_rules)

    scroll_rules = css_rule_bodies(".dc-table-scroll")
    assert scroll_rules, ".dc-table-scroll 규칙이 없습니다"
    for body in scroll_rules:
        assert "overflow-x:auto" not in body


def test_report_js_init_table_moves_header_with_scroll_left():
    js = (ROOT / "assets" / "report" / "report.js").read_text(encoding="utf-8")
    match = re.search(r"    function initTable\(\) \{(.*?)\n    var chunkLoads = \{\};", js, re.S)
    assert match, "initTable 본문을 찾지 못했습니다"
    body = match.group(1)
    assert "headTransform" in body
    assert "scrollLeft" in body
