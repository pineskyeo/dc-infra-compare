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
        self._in_th = False

    def handle_starttag(self, tag, attrs):
        self.attrs += [(tag, k, v or "") for k, v in attrs]
        self._in_th = tag == "th"
        if self._in_th:
            self.th.append("")

    def handle_endtag(self, tag):
        if tag == "th":
            self._in_th = False

    def handle_data(self, data):
        if self._in_th:
            self.th[-1] += data


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
    fixed = {"항목", "값", "뜻", "열", "볼 것", "차이", "미결", "동등", "판정 제외", "가장 나쁜 ITEM"}
    for rel in REPORTS:
        for th in parse(plain / rel).th:
            assert th in easy or th in fixed or "→" in th, (rel, th)


def test_item_report_has_a_card_per_item_folder(plain):
    html = visible_text(plain / "item" / "report.html")
    index = pd.read_csv(plain / "item" / "items_index.csv")
    assert html.count('<section class="item"') == len(index)
    for d in index["폴더"]:
        assert (plain / "item" / d / "item_view.png").read_bytes() in \
            [base64.b64decode(b) for b in DATA_URI.findall((plain / "item" / "report.html").read_text())]
    assert "근거 숫자 (evidence.csv)" in html and "같다고 보는 범위는" in html


def test_group_table_counts_match_items(plain):
    html = visible_text(plain / "group" / "report.html")
    items = pd.read_csv(plain / "items.csv")
    in_vt = items["ITEM"].map(GROUPS) == "VT"
    vt = items.loc[in_vt, "verdict_final"].value_counts()
    row = re.search(r"<tr><td>VT</td>(.*?)</tr>", html)[1]
    cells = re.findall(r"<td>(.*?)</td>", row)
    assert cells[:5] == [str(int(in_vt.sum())), str(vt.get("차이", 0)), str(vt.get("미결", 0)), str(vt.get("동등", 0)),
                         str(vt.get("판정 제외", 0))]
    assert "판정이 바뀐 ITEM" in html


def test_anon_has_no_item_name_anywhere(anon):
    items = pd.read_csv(anon / "items.csv")
    names = set(items["ITEM"]) | set(items["blank_item"].dropna())
    for rel in ANON_REPORTS:
        text = visible_text(anon / rel)
        assert not [n for n in names if n in text], rel
    judge = visible_text(anon / "report_anon.html")
    assert all(i in judge for i in items.loc[items["verdict_final"].isin(["차이", "미결"]), "ID"])
    assert "익명 리포트라" in judge


def test_anon_figures_are_only_name_free_ones(anon):
    html = (anon / "report_anon.html").read_text(encoding="utf-8")
    blobs = [base64.b64decode(b) for b in DATA_URI.findall(html)]
    assert blobs == [(anon / "stability" / "stability.png").read_bytes()]


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
