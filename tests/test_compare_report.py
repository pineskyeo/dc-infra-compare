"""기존·개선 비교 요약 (compare/): 그룹 파일에 없는 ITEM 빼기, 요약 지표·판단, 리포트, 엑셀. 손으로 만든 합성 결과만 쓴다.

그룹 GOOD 은 흔들림이 반으로, SAME 은 그대로, BAD 는 두 배가 된다. 그룹 파일에 없는 SYN_U* 는 흔들림이 1/10 이고
판정이 차이 → 동등이라, 비교에 섞이면 '전체' 숫자가 달라진다."""
import io
import math
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
sys.path.insert(0, str(ROOT))

import compare_book  # noqa: E402
import compare_metrics as cm  # noqa: E402
import group_summary  # noqa: E402
import report  # noqa: E402
import simple_xlsx  # noqa: E402
from compare_before_after import main as compare_main  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
FACTORS = {  # ITEM → (그룹, 개선/기존 흔들림 배수, 기존 판정, 개선 판정)
    "SYN_A1": ("GOOD", 0.5, "미결", "동등"), "SYN_A2": ("GOOD", 0.55, "동등", "동등"),
    "SYN_A3": ("GOOD", 0.45, "동등", "동등"), "SYN_A4": ("GOOD", 0.5, "동등", "동등"),
    "SYN_B1": ("SAME", 1.0, "동등", "동등"), "SYN_B2": ("SAME", 1.02, "동등", "동등"),
    "SYN_B3": ("SAME", 0.98, "동등", "동등"), "SYN_B4": ("SAME", 1.0, "동등", "동등"),
    "SYN_C1": ("BAD", 2.0, "동등", "차이"), "SYN_C2": ("BAD", 1.8, "동등", "동등"),
    "SYN_C3": ("BAD", 2.2, "동등", "동등"), "SYN_C4": ("BAD", 2.0, "동등", "동등"),
    **{f"SYN_U{i}": (None, 0.1, "차이", "동등") for i in range(1, 5)},
}
GROUPED = [i for i, f in FACTORS.items() if f[0]]
UNGROUPED = [i for i, f in FACTORS.items() if not f[0]]


def items_frame(side: str) -> pd.DataFrame:
    rows = []
    names = list(FACTORS) + (["SYN_OLD"] if side == "before" else ["SYN_NEW"])
    for n, item in enumerate(names, 1):
        group, k, vb, va = FACTORS.get(item, (None, 1.0, "동등", "동등"))
        k = k if side == "after" else 1.0
        die, run, med = 2.0 * k, 1.0 * k, 100.0 + n
        rows.append({"ITEM": item, "ID": f"I{n:02d}", "verdict": vb if side == "before" else va,
                     "verdict_final": vb if side == "before" else va, "por_median": med, "sigma_die": die,
                     "sigma_run": run, "meas_precision_pct": 100 * math.hypot(die, run) / med,
                     "center": 0.0, "ci_low": -3 * k, "ci_high": 3 * k, "delta": 5.0})
    return pd.DataFrame(rows)


def write_result(folder: Path, side: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    items_frame(side).to_csv(folder / "items.csv", index=False, encoding="utf-8-sig")
    return folder / "items.csv"


def groups_file(path: Path) -> Path:
    # SYN_A2 는 접두어가 붙은 이름으로만 적어, 접두어를 떼고 맞추는지도 본다
    rows = [(("F12_" + i) if i == "SYN_A2" else i, FACTORS[i][0]) for i in GROUPED]
    path.write_text("ITEM,group\n" + "".join(f"{i},{g}\n" for i, g in rows), encoding="utf-8")
    return path


def run_compare(base: Path, grouped: bool) -> Path:
    before = write_result(base / "old", "before")
    after = write_result(base / "new", "after")
    out = base / "new" / "compare"
    extra = ["--groups", str(groups_file(base / "groups.csv"))] if grouped else []
    assert compare_main(["compare", str(before), str(after), "-o", str(out), *extra]) == 0
    if grouped:
        group_summary.main(["--compare", str(out / "compare.csv"), "--out", str(out / "groups")])
    return out


def build_reports(folder: Path, anon: bool) -> Path:
    items = pd.read_csv(folder / "items.csv", dtype=str)
    return report.compare_report(folder, report.Namer(items, anon))


@pytest.fixture(scope="module")
def grouped(tmp_path_factory) -> Path:
    out = run_compare(tmp_path_factory.mktemp("grouped"), grouped=True)
    build_reports(out.parent, anon=False)
    build_reports(out.parent, anon=True)
    return out


@pytest.fixture(scope="module")
def ungrouped(tmp_path_factory) -> Path:
    out = run_compare(tmp_path_factory.mktemp("plain"), grouped=False)
    build_reports(out.parent, anon=False)
    return out


def read_xlsx(path: Path) -> dict[str, list[list]]:
    """시트 이름 → 행 (칸 값: 숫자 칸은 float, 글자 칸은 str)."""
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        names = [s.get("name") for s in wb.find("m:sheets", NS)]
        out = {}
        for i, name in enumerate(names, 1):
            sheet = ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml"))
            rows = []
            for row in sheet.iter(f"{{{NS['m']}}}row"):
                cells = {}
                for c in row:
                    col = "".join(ch for ch in c.get("r") if ch.isalpha())
                    idx = sum((ord(ch) - 64) * 26 ** p for p, ch in enumerate(reversed(col))) - 1
                    if c.get("t") == "inlineStr":
                        cells[idx] = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                    else:
                        cells[idx] = float(c.find("m:v", NS).text)
                rows.append([cells.get(j) for j in range(max(cells) + 1)] if cells else [])
            out[name] = rows
    return out


def ratios(items: list[str], value: str) -> list[float]:
    b, a = items_frame("before").set_index("ITEM"), items_frame("after").set_index("ITEM")
    return [a.loc[i, value] / b.loc[i, value] for i in items]


# ── 그룹 파일에 없는 ITEM 은 어디에도 없다 ─────────────────────────────────────────

def test_overall_numbers_are_grouped_items_only(grouped):
    ov = pd.read_csv(grouped / "overview.csv").set_index("kpi")
    b, a = items_frame("before").set_index("ITEM"), items_frame("after").set_index("ITEM")
    prec = ov.loc["meas_precision"]
    assert prec["ratio_median"] == pytest.approx(np.median(ratios(GROUPED, "meas_precision_pct")))
    assert prec["before"] == pytest.approx(b.loc[GROUPED, "meas_precision_pct"].median())
    assert prec["after"] == pytest.approx(a.loc[GROUPED, "meas_precision_pct"].median())
    assert prec["n_ratio"] == len(GROUPED)
    assert ov.loc["sigma_die", "ratio_median"] == pytest.approx(np.median(ratios(GROUPED, "sigma_die")))
    ne = ov.loc["not_equivalent"]
    assert (ne["before"], ne["after"]) == (1, 1)          # SYN_A1 미결, SYN_C1 차이 (SYN_U* 의 차이 넷은 빠짐)
    total = pd.read_csv(grouped / "groups" / "group_summary.csv").set_index("그룹").loc["전체"]
    assert total["ITEM 수"] == len(GROUPED)
    assert total["측정 정밀도 비 중앙값(개선/기존)"] == pytest.approx(round(prec["ratio_median"], 3))
    assert total["기존 동등 아님"] == 1


def test_compare_rows_and_worst_list_hold_grouped_items_only(grouped):
    rows = pd.read_csv(grouped / "compare.csv")
    assert sorted(rows["ITEM"]) == sorted(GROUPED)
    assert dict(zip(rows["ITEM"], rows["group"]))["SYN_A2"] == "GOOD"
    worst = pd.read_csv(grouped / "worst_items.csv")
    assert not set(worst["ITEM"]) & set(UNGROUPED)
    scope = pd.read_csv(grouped / "scope.csv").iloc[0]
    assert (scope["n_matched"], scope["n_ungrouped"], scope["n_compared"]) == (16, 4, 12)
    assert (scope["n_only_before"], scope["n_only_after"]) == (1, 1)


def test_ungrouped_label_appears_nowhere(grouped):
    for csv in grouped.rglob("*.csv"):
        assert "미지정" not in csv.read_text(encoding="utf-8-sig"), csv
    for page in ("report.html", "report_anon.html"):
        text = (grouped / page).read_text(encoding="utf-8")
        assert "미지정" not in text and not [u for u in UNGROUPED if u in text]
    for book in (compare_book.WORKBOOK, compare_book.WORKBOOK_ANON):
        for rows in read_xlsx(grouped / book).values():
            assert not [v for r in rows for v in r if isinstance(v, str) and ("미지정" in v or "SYN_U" in v)]


def test_scope_line_states_dropped_count_once(grouped):
    text = (grouped / "report.html").read_text(encoding="utf-8")
    assert text.count("그룹 파일에 없는 ITEM 4개는 비교에서 뺌") == 1
    assert "한쪽에만 있는 2개는 뺌" in text


# ── 요약 지표와 판단 ───────────────────────────────────────────────────────────

def test_group_trend_follows_the_ten_percent_rule(grouped):
    tab = pd.read_csv(grouped / "groups" / "group_summary.csv").set_index("그룹")
    assert tab.loc["GOOD", "판단"] == cm.BETTER and tab.loc["GOOD", "측정 정밀도 비 중앙값(개선/기존)"] == 0.5
    assert tab.loc["SAME", "판단"] == cm.SAME
    assert tab.loc["BAD", "판단"] == cm.WORSE and tab.loc["BAD", "측정 정밀도 비 중앙값(개선/기존)"] == 2.0
    assert tab.loc["GOOD", "측정 정밀도 좋아진 %"] == 100.0 and tab.loc["SAME", "측정 정밀도 좋아진 %"] == 0.0
    assert tab.loc["GOOD", "가장 좋아진 것"].endswith("0.50배")
    assert pd.isna(tab.loc["BAD", "가장 좋아진 것"])


def test_kpi_table_on_hand_built_frame():
    d = pd.DataFrame({
        "meas_precision_pct_before": [1.0, 1.0, 1.0, 0.0, np.nan],
        "meas_precision_pct_after": [0.5, 0.95, 1.5, 1.0, 1.0],
        "verdict_before": ["차이", "동등", "미결", "동등", "동등"],
        "verdict_after": ["동등", "동등", "동등", "차이", "동등"],
    })
    for stem in ("sigma_die", "sigma_run", "ci_width_pct"):
        d[f"{stem}_before"], d[f"{stem}_after"] = 1.0, [0.8, 0.85, 0.9, 0.95, 1.0]
    for stem in ("sigma_die_pct", "sigma_run_pct"):
        d[f"{stem}_before"], d[f"{stem}_after"] = 1.0, 1.0
    t = cm.kpi_table(d).set_index("kpi")
    prec = t.loc["meas_precision"]
    assert prec["ratio_median"] == pytest.approx(0.95) and prec["trend"] == cm.SAME
    assert (prec["n_ratio"], prec["n_skipped"]) == (3, 2)          # 기존 0, 기존 빈 칸은 비에서 뺀다
    assert prec["improved_pct"] == pytest.approx(100 / 3)          # 0.5 만 0.9 미만
    die = t.loc["sigma_die"]
    assert die["ratio_median"] == pytest.approx(0.9) and die["trend"] == cm.SAME
    assert cm.trend(0.89) == cm.BETTER and cm.trend(1.11) == cm.WORSE and cm.trend(1.1) == cm.SAME
    ne = t.loc["not_equivalent"]
    assert (ne["before"], ne["after"], ne["trend"]) == (2, 1, cm.BETTER)
    assert ne["improved_pct"] == pytest.approx(100.0)             # 동등 아니던 둘 다 동등이 됨


# ── 그룹 파일 없이 ─────────────────────────────────────────────────────────────

def test_without_groups_file_all_matched_items_and_no_group_sections(ungrouped):
    rows = pd.read_csv(ungrouped / "compare.csv")
    assert sorted(rows["ITEM"]) == sorted(FACTORS) and "group" not in rows
    ov = pd.read_csv(ungrouped / "overview.csv").set_index("kpi")
    assert ov.loc["meas_precision", "ratio_median"] == pytest.approx(np.median(ratios(list(FACTORS),
                                                                                       "meas_precision_pct")))
    assert not (ungrouped / "groups").exists()
    html = (ungrouped / "report.html").read_text(encoding="utf-8")
    assert ">그룹별</h2>" not in html and ">그룹 × LEVEL</h2>" not in html and "그룹 파일에 없는" not in html
    assert compare_book.GROUPS not in read_xlsx(ungrouped / compare_book.WORKBOOK)


def test_rerun_without_groups_removes_old_group_summary(tmp_path):
    out = run_compare(tmp_path, grouped=True)
    assert (out / "groups" / "group_summary.csv").is_file()
    assert compare_main(["compare", str(tmp_path / "old" / "items.csv"), str(tmp_path / "new" / "items.csv"),
                         "-o", str(out)]) == 0
    assert not (out / "groups").exists()


# ── 리포트 ───────────────────────────────────────────────────────────────────

def test_report_headline_numbers_match_overview(grouped):
    ov = pd.read_csv(grouped / "overview.csv").set_index("kpi")
    html = (grouped / "report.html").read_text(encoding="utf-8")
    summary = html.split('id="summary"')[1].split("</details>")[0]
    prec = ov.loc["meas_precision"]
    row = summary.split("측정 정밀도 % 중앙값</td>")[1].split("</tr>")[0]
    for v in (prec["before"], prec["after"], prec["ratio_median"]):
        assert f"<td>{report.plain_num(float(f'{v:.3g}'))}</td>" in row, v
    assert f'class="{prec["trend"]}"' in row
    headline = summary.split('<p class="headline">')[1].split("</p>")[0]
    assert headline.startswith(f"측정 정밀도 {prec['trend']}")         # 비 1.0 은 비슷
    assert "그룹 3개 중 1개 좋아짐 (가장 큰 GOOD 0.50배)" in headline and "나빠짐 BAD" in headline
    assert "0.9 미만이면 좋아짐" in summary


def test_groups_sorted_best_first(grouped):
    table = read_xlsx(grouped / compare_book.WORKBOOK)[compare_book.GROUPS]
    assert [r[0] for r in table[1:4]] == ["전체", "GOOD", "SAME"] and table[4][0] == "BAD"


def test_anon_report_and_workbook_have_no_item_names(grouped):
    names = list(FACTORS)
    html = (grouped / "report_anon.html").read_text(encoding="utf-8")
    assert not [n for n in names if n in html]
    book = read_xlsx(grouped / compare_book.WORKBOOK_ANON)
    cells = [v for rows in book.values() for r in rows for v in r if isinstance(v, str)]
    assert not [c for c in cells if any(n in c for n in names)]
    assert book[compare_book.ITEMS][0][:2] == ["ID", "그룹"]
    assert read_xlsx(grouped / compare_book.WORKBOOK)[compare_book.ITEMS][0][:3] == ["ID", "ITEM", "그룹"]


# ── 엑셀 파일 ─────────────────────────────────────────────────────────────────

def test_xlsx_parts_and_round_trip(grouped):
    path = grouped / compare_book.WORKBOOK
    with zipfile.ZipFile(path) as z:
        parts = set(z.namelist())
        assert {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels",
                "xl/styles.xml"} <= parts
        for part in parts:
            ET.fromstring(z.read(part))
        first = z.read("xl/worksheets/sheet1.xml").decode()
        assert 'state="frozen"' in first and 's="1"' in first
    book = read_xlsx(path)
    assert list(book)[:2] == [compare_book.SUMMARY, compare_book.GROUPS]
    summary = book[compare_book.SUMMARY]
    assert summary[0][:4] == ["지표", "기존", "개선", "변화"]
    ov = pd.read_csv(grouped / "overview.csv").set_index("kpi")
    assert summary[1][0] == "측정 정밀도 % 중앙값"
    assert summary[1][4] == pytest.approx(round(ov.loc["meas_precision", "ratio_median"], 3))
    assert summary[5][1] == 1.0 and isinstance(summary[5][1], float)
    items = pd.DataFrame(book[compare_book.ITEMS][1:], columns=book[compare_book.ITEMS][0])
    assert items.set_index("ITEM").loc["SYN_C1", "개선 판정"] == "차이"


def test_sheet_names_and_cells():
    assert simple_xlsx.sheet_names(["a/b", "x" * 40, "X" * 40]) == ["a_b", "x" * 31, "X" * 29 + "_2"]
    assert simple_xlsx.col_letter(0) == "A" and simple_xlsx.col_letter(26) == "AA"


def test_soffice_opens_workbook(grouped, tmp_path):
    soffice = shutil.which("soffice")
    if soffice is None:
        pytest.skip("soffice 없음")
    shutil.copy(grouped / compare_book.WORKBOOK, tmp_path / "book.xlsx")
    proc = subprocess.run([soffice, "--headless", "--convert-to", "csv", "--outdir", str(tmp_path),
                           str(tmp_path / "book.xlsx")], capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr
    first = pd.read_csv(io.StringIO((tmp_path / "book.csv").read_text(encoding="utf-8")), header=None)
    assert first.iloc[0, 0] == "지표" and first.iloc[1, 0] == "측정 정밀도 % 중앙값"
