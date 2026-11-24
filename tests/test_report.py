"""report.py: 판정·ITEM·그룹 리포트 HTML. 합성 데이터를 dcc.py 로 판정(--detail)·그룹(--before)·review.py 까지 돌린 폴더와
log 판정 ITEM 이 있는 truth 폴더에서 만든다. 외부 주소 없음, 그림이 풀리는지, --anon 에 ITEM 이름이 없는지, 빠진 폴더."""
import base64
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import columns_doc  # noqa: E402
import golden_cases as gc  # noqa: E402
import report  # noqa: E402
from explain import fmt  # noqa: E402
from plot_verdicts import MAP_HOW_TO_READ  # noqa: E402
from stability import LEVEL_HOW_TO_READ  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
DATA_URI = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=]+)")
REPORTS = ("report.html", "item/report.html", "group/report.html")
ANON_REPORTS = tuple(r.replace("report.html", "report_anon.html") for r in REPORTS)
GROUPS = {"VT_SAME": "VT", "VT_SHIFT": "VT", "VT_NOISY_DOE": "VT", "VOS_OFFSET": "VT", "RON_CONTACT": "RES",
          "IOFF_FLOOR": "LEAK", "IOFF_LEAK": "LEAK", "IOFF_RUNWOBBLE": "LEAK", "IOFF_STEP": "LEAK",
          "ION_OUTLIER": "ION", "IDSAT_SPEC": "ION"}


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attrs: list[tuple[str, str, str]] = []
        self.th: list[str] = []
        self.sections: list[dict] = []      # 주제 칸: open, title (h2), tips (제목 옆 풍선)
        self.tips: list[str] = []            # 모든 풍선 글 (data-tip)
        self._in_th = self._in_h2 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.attrs += [(tag, k, v or "") for k, v in attrs]
        self._in_th = tag == "th"
        if self._in_th:
            self.th.append("")
        if tag == "details" and a.get("class") == "sec":
            self.sections.append({"open": "open" in a, "title": "", "id": None})
        if tag == "h2":
            self._in_h2 = True
        if tag == "div" and a.get("class") == "body" and self.sections:
            self.sections[-1]["id"] = a.get("id")
        if "data-tip" in a:
            self.tips.append(a["data-tip"])

    def handle_endtag(self, tag):
        if tag == "th":
            self._in_th = False
        if tag == "h2":
            self._in_h2 = False

    def handle_data(self, data):
        if self._in_th:
            self.th[-1] += data
        if self._in_h2 and self.sections:
            self.sections[-1]["title"] += data


def parse(path: Path) -> Tags:
    t = Tags()
    t.feed(path.read_text(encoding="utf-8"))
    return t


def visible_text(path: Path) -> str:
    return DATA_URI.sub("", path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict[str, Path]:
    """이름 → 결과 폴더. full = dcc judge --detail + group --before + review, truth = log 판정 + review."""
    base = tmp_path_factory.mktemp("report")
    data = gc.build_data(base / "data", ["por3", "truth"])
    d = data["por3"]
    (base / "groups.csv").write_text("ITEM,GROUP\n" + "".join(f"{k},{v}\n" for k, v in GROUPS.items()))
    por = "\n      ".join(str(d / f"por_run{k}") for k in (1, 2, 3))
    (base / "combos.ini").write_text(
        f"[defaults]\nout = {base / 'out'}\ngroups = {base / 'groups.csv'}\n"
        f"[FULL]\npor = {por}\ndoe = {d / 'doe'}\nlevel = {d / 'level.csv'}\nblank = {d / 'blank'}\n"
        f"blank_map = {d / 'blank_map.csv'}\n")
    full = base / "out" / "FULL"
    gc._run([ROOT / "dcc.py", "judge", "--config", base / "combos.ini", "FULL", "--detail"])
    shutil.copy(full / "items.csv", base / "before.csv")
    gc._run([ROOT / "dcc.py", "group", "--config", base / "combos.ini", "FULL", "--before", base / "before.csv"])
    gc._run([ROOT / "review.py", "--input", full / "items.csv", "--out", full, *gc._por3_lb(d)])

    truth = base / "truth"
    gc.run_case(next(c for c in gc.CASES if c.name == "truth_scales"), data["truth"], truth)
    gc._run([ROOT / "review.py", "--input", truth / "items.csv", "--out", truth, *gc._truth(data["truth"])])
    return {"full": full, "truth": truth, "groups": base / "groups.csv"}


@pytest.fixture(scope="module")
def plain(built, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("plain") / "FULL"
    shutil.copytree(built["full"], out)
    report.write_reports(out, groups=built["groups"])
    return out


@pytest.fixture(scope="module")
def anon(built, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("anon") / "FULL"
    shutil.copytree(built["full"], out)
    assert report.main([str(out), "--anon", "--groups", str(built["groups"])]) == 0
    return out


def test_three_reports_written(plain):
    for rel in REPORTS:
        assert (plain / rel).is_file(), rel


@pytest.mark.parametrize("rel", REPORTS)
def test_no_external_address(plain, rel):
    tags = parse(plain / rel)
    for tag, key, value in tags.attrs:
        if key in ("src", "href") and not DATA_URI.fullmatch(value):
            assert "http" not in value and "://" not in value, (tag, key, value)
    assert not [t for t, _, _ in tags.attrs if t in ("script", "link", "iframe")]
    assert "<script" not in (plain / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", REPORTS)
def test_every_embedded_figure_is_a_png_from_the_folder(plain, rel):
    pngs = {p.read_bytes() for p in plain.rglob("*.png")}
    blobs = [base64.b64decode(b, validate=True) for b in DATA_URI.findall((plain / rel).read_text(encoding="utf-8"))]
    assert blobs, rel
    for blob in blobs:
        assert blob.startswith(PNG_MAGIC)
        assert blob in pngs


def test_judge_report_figures_and_sections(plain):
    html = (plain / "report.html").read_text(encoding="utf-8")
    blobs = [base64.b64decode(b) for b in DATA_URI.findall(html)]
    for fig in ("plots/summary.png", "review/loq_review.png", "stability/stability.png"):
        assert (plain / fig).read_bytes() in blobs, fig
    for flagged in pd.read_csv(plain / "review" / "loq_review.csv").query("flag")["ITEM"]:
        assert report.review_figure(plain, flagged).read_bytes() in blobs, flagged
    for heading in ("한눈에", "판정 지도", "차이·미결", "판정 제외", "LoQ 확인 필요", "log 확인 필요", "측정 안정도", "읽는 법"):
        assert f">{heading}</h2>" in html, heading
    assert 'href="' in html and "docs/sop/columns.html" in html
    assert "유형별 판정" not in html


@pytest.mark.parametrize("rel", REPORTS)
def test_every_topic_is_a_collapsible_section_and_only_the_first_screen_is_open(plain, rel):
    tags = parse(plain / rel)
    titles = [s["title"] for s in tags.sections]
    assert titles and len(titles) == len(set(titles)), titles
    opened = {s["title"] for s in tags.sections if s["open"]}
    first = {"report.html": {"한눈에", "판정 지도", "차이·미결"},
             "item/report.html": {"ITEM 별 변화량", "ITEM 카드"},
             "group/report.html": {"그룹별 표", "그룹 × LEVEL 측정 정밀도"}}[rel]
    assert opened == first
    links = [v.removeprefix("#") for t, k, v in tags.attrs if t == "a" and k == "href" and v.startswith("#")]
    assert links == [s["id"] for s in tags.sections], "목차는 칸마다 하나, 칸 내용을 가리킨다 (가리키면 브라우저가 펼친다)"


def test_explanations_are_hover_tips_not_page_text(plain):
    tags = parse(plain / "report.html")
    assert MAP_HOW_TO_READ in tags.tips and LEVEL_HOW_TO_READ in tags.tips
    text = re.sub(r"<[^>]+>", "", visible_text(plain / "report.html"))
    assert MAP_HOW_TO_READ not in text and LEVEL_HOW_TO_READ not in text
    assert ('<span class="tip" tabindex="0"' in (plain / "report.html").read_text(encoding="utf-8")), "키보드로도 연다"


def test_problem_table_shows_normalized_numbers_with_raw_values_on_hover(plain):
    items = pd.read_csv(plain / "items.csv").set_index("ITEM")
    r = items.loc["VT_SHIFT"]
    assert r["verdict_final"] == "차이" and r["verdict_basis"] == "linear"
    x = (r["ci_low"] + r["ci_high"]) / 2 / r["delta"]
    y = (r["ci_high"] - r["ci_low"]) / 2 / r["delta"]
    section = visible_text(plain / "report.html").split('id="problems"')[1].split('id="excluded"')[0]
    row = re.search(r"<tr><td>F\w+</td><td>VT_SHIFT</td>(.*?)</tr>", section)[1]
    cells = re.findall(r'<td(?: title="([^"]*)")?>(.*?)</td>', row)
    assert any(c == "선형 TOST" for _, c in cells)
    shift = next(t for t, c in cells if c == f"{x:+.2f}")
    assert f"변화량 {fmt(r['center'], r['UNIT'], signed=True)}" in shift and f"허용폭 ±{fmt(r['delta'], r['UNIT'])}" in shift
    assert any(c == f"{y:.2f}" and "신뢰구간 반폭" in t for t, c in cells)
    assert any(c == "차이" and "허용폭 밖" in t for t, c in cells), "판정 칸 풍선은 판정 이유"


def test_problem_table_is_severity_ordered_with_both_names(plain):
    items = pd.read_csv(plain / "items.csv")
    html = visible_text(plain / "report.html")
    section = html.split('id="problems"')[1].split('id="excluded"')[0]
    severe = items[items["verdict_final"].isin(["차이", "미결"])]
    positions = {r.ITEM: section.index(f"<td>{r.ITEM}</td>") for r in severe.itertuples()}
    assert all(f"<td>{i}</td>" in section for i in severe["ID"])
    order = sorted(positions, key=positions.get)
    verdict = dict(zip(items["ITEM"], items["verdict_final"]))
    assert [verdict[i] for i in order] == sorted((verdict[i] for i in order), key=["차이", "미결"].index)
    assert "VT_SAME" not in section


def test_headers_are_easy_names(plain):
    easy = {d.easy_name for docs in columns_doc.load().values() for d in docs if d.easy_name}
    fixed = {"항목", "값", "뜻", "열", "볼 것", "차이", "미결", "동등", "판정 제외", "가장 나쁜 ITEM", "판정 방법",
             "정규화 변화량", "정규화 불확실성", "변화 %", "확인 근거", "방향"}
    for rel in REPORTS:
        for th in parse(plain / rel).th:
            assert th in easy or th in fixed or "→" in th, (rel, th)


def test_item_report_has_a_card_per_item_folder(plain):
    html = visible_text(plain / "item" / "report.html")
    index = pd.read_csv(plain / "item" / "items_index.csv")
    assert html.count('<details class="item"') == len(index)
    for d in index["폴더"]:
        assert (plain / "item" / d / "item_view.png").read_bytes() in \
            [base64.b64decode(b) for b in DATA_URI.findall((plain / "item" / "report.html").read_text())]
    assert "<summary>근거 숫자</summary>" in html and "같다고 보는 범위는" in html


def test_group_table_counts_match_items(plain):
    html = visible_text(plain / "group" / "report.html")
    items = pd.read_csv(plain / "items.csv")
    in_vt = items["ITEM"].map(GROUPS) == "VT"
    vt = items.loc[in_vt, "verdict_final"].value_counts()
    row = re.search(r"<tr><td>VT</td>(.*?)</tr>", html)[1]
    cells = re.findall(r"<td>(.*?)</td>", row)
    assert cells[:5] == [str(int(in_vt.sum())), str(vt.get("차이", 0)), str(vt.get("미결", 0)), str(vt.get("동등", 0)),
                         str(vt.get("판정 제외", 0))]
    assert '<a href="../compare/report.html">기존·개선 비교는 compare 리포트에 있다</a>' in html
    assert "판정이 바뀐 ITEM" not in html and "기존·개선 비교</h2>" not in html


def test_compare_report_written_next_to_its_workbook(plain):
    html = (plain / "compare" / "report.html").read_text(encoding="utf-8")
    for heading in ("요약", "그룹별", "판정 변화", "그룹 × LEVEL", "나빠진 ITEM", "그림", "열 뜻"):
        assert f">{heading}</h2>" in html, heading
    assert (plain / "compare" / "비교.xlsx").is_file()
    assert not (plain / "group" / "compare").exists() and not (plain / "group" / "summary").exists()


def test_anon_has_no_item_name_anywhere(anon):
    items = pd.read_csv(anon / "items.csv")
    names = set(items["ITEM"]) | set(items["blank_item"].dropna())
    for rel in (*ANON_REPORTS, "compare/report_anon.html"):
        text = visible_text(anon / rel)
        assert not [n for n in names if n in text], rel
    import zipfile
    with zipfile.ZipFile(anon / "compare" / "비교_anon.xlsx") as z:
        xml = "".join(z.read(n).decode("utf-8") for n in z.namelist())
    assert not [n for n in names if n in xml]
    judge = visible_text(anon / "report_anon.html")
    assert all(i in judge for i in items.loc[items["verdict_final"].isin(["차이", "미결"]), "ID"])
    assert "익명 리포트라" in judge


def test_anon_figures_are_only_name_free_ones(anon):
    html = (anon / "report_anon.html").read_text(encoding="utf-8")
    blobs = [base64.b64decode(b) for b in DATA_URI.findall(html)]
    assert blobs == [(anon / "stability" / n).read_bytes() for n in ("group_levels.png", "stability.png")]


def test_log_review_rows_render(built, tmp_path):
    out = tmp_path / "truth"
    shutil.copytree(built["truth"], out)
    log_csv = out / "review" / "log_review.csv"
    log = pd.read_csv(log_csv)
    assert len(log)
    if not log["flag"].any():
        log.loc[0, ["flag", "why"]] = [True, "확인 필요(시험용 표시)."]
        log.to_csv(log_csv, index=False, encoding="utf-8-sig")
    report.write_reports(out)
    html = visible_text(out / "report.html")
    section = html.split('id="log"')[1].split('id="stability"')[0]
    assert f"대상 {len(log):,}개 중 확인 필요 {int(log['flag'].sum()):,}개" in section
    for row in log.loc[log["flag"]].itertuples():
        assert f"<td>{row.ITEM}</td>" in section and row.why in section


def test_builds_with_only_items_csv(built, tmp_path):
    out = tmp_path / "bare"
    out.mkdir()
    shutil.copy(built["full"] / "items.csv", out / "items.csv")
    written = report.write_reports(out, anon=True)
    assert written == [out / "report_anon.html"]
    html = visible_text(out / "report_anon.html")
    for missing in ("review/loq_review.csv", "review/log_review.csv", "stability/ 폴더", "그림 파일"):
        assert f"{missing} 없음" in html, missing


def test_missing_items_csv_is_a_clear_error(tmp_path, capsys):
    assert report.main([str(tmp_path)]) == 2
    assert "items.csv" in capsys.readouterr().err


def test_log_run_section_lists_only_items_whose_final_verdict_changes(tmp_path):
    items = pd.DataFrame({"ID": ["I1", "I2"], "ITEM": ["LEAK_WIDE", "LEAK_SAME"], "verdict_final": ["동등", "동등"],
                          "verdict_final_log_run": ["미결", "동등"], "center_log": [0.02, 0.0],
                          "ci_low_log": [0.01, -0.01], "ci_high_log": [0.03, 0.01], "delta_log": [0.05, 0.05],
                          "delta_log_run": [0.0212, 0.0212]})
    page = report.Page("t", report.Namer(items, False), tmp_path / "r.html")
    report.log_run_compare(page, items)
    html = visible_text(page.write())
    assert "동등 → 미결 1개" in html and "LEAK_WIDE" in html and "LEAK_SAME" not in html
    assert "+5.0%" in html and "+12.2%" in html       # delta_log_run 0.0212 → 1.05배, delta_log 0.05 → 1.122배


def test_stability_section_shows_group_by_level(built):
    html = (built["full"] / "report.html").read_text(encoding="utf-8")
    section = html.split('id="stability"')[1]
    assert "그룹 × LEVEL" in section
    table = pd.read_csv(built["full"] / "stability" / "group_levels.csv")
    assert set(GROUPS.values()) <= set(table["group"])
    assert table["n_items"].sum() == len(pd.read_csv(built["full"] / "items.csv"))
    blob = (built["full"] / "stability" / "group_levels.png").read_bytes()
    assert base64.b64encode(blob).decode() in section


def test_review_section_caps_item_figures_and_says_where_the_rest_are(built, tmp_path, monkeypatch):
    folder = tmp_path / "FULL"
    shutil.copytree(built["full"], folder)
    flagged = pd.read_csv(folder / "review" / "loq_review.csv").query("flag")
    assert len(flagged) >= 1
    monkeypatch.setattr(report, "REVIEW_FIGURES", 0)
    report.write_reports(folder, groups=built["groups"])
    section = (folder / "report.html").read_text(encoding="utf-8").split('id="loq"')[1].split('id="log"')[0]
    assert "확인 필요 상세" not in section
    assert f"상세 그림은 근거가 센 0개만 싣는다 (확인 필요 {len(flagged):,}개" in section
