"""판정 기준 장표 (slides.py): pptx 패키지, 결과 숫자, 익명 번호, 미결 원인. 합성 데이터만."""
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import golden_cases as gc  # noqa: E402
import slides  # noqa: E402

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


@pytest.fixture(scope="module")
def judged(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("slides")
    d = gc.build_data(base / "data", ["por3"])["por3"]
    (d / "groups.csv").write_text("ITEM,group\nVT_SAME,VT\nVT_SHIFT,VT\nVT_NOISY_DOE,VT\nIOFF_LEAK,IOFF\n"
                                  "IOFF_FLOOR,IOFF\n", encoding="utf-8")
    out = base / "out"
    gc._run([ROOT / "por_doe_compare.py", *gc._por3_lb(d), "--groups", d / "groups.csv", "--out", out])
    return out


def slide_texts(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
        return ["".join(t.text or "" for t in ElementTree.fromstring(z.read(n)).iter(f"{A}t")) for n in names]


def test_package_has_two_slides_with_their_images_and_parses(judged, tmp_path):
    path = slides.write_pptx(tmp_path / "deck.pptx", slides.build(judged, label="합성"))
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for part in ("[Content_Types].xml", "ppt/presentation.xml", "ppt/slideMasters/slideMaster1.xml",
                     "ppt/theme/theme1.xml", "ppt/slides/slide1.xml", "ppt/slides/slide2.xml"):
            assert part in names, part
        for n in names:
            if n.endswith((".xml", ".rels")):
                ElementTree.fromstring(z.read(n))
        for n in ("ppt/slides/_rels/slide1.xml.rels", "ppt/slides/_rels/slide2.xml.rels"):
            targets = re.findall(r'Target="\.\./media/([^"]+)"', z.read(n).decode())
            assert targets and all(f"ppt/media/{t}" in names for t in targets), n
        sld_ids = re.findall(r'<p:sldId id="(\d+)"', z.read("ppt/presentation.xml").decode())
        assert len(sld_ids) == 2


def test_numbers_come_from_items_csv_and_names_stay_anonymous(judged, tmp_path):
    items = pd.read_csv(judged / "items.csv")
    first, second = slide_texts(slides.write_pptx(tmp_path / "deck.pptx", slides.build(judged, label="합성")))
    assert "01  기존 문제" in first and "3  ITEM 유형별 판정" in first and "무엇이 바뀌나" in first
    counts = items["verdict_final"].value_counts()
    for v in ("동등", "미결", "차이"):
        assert f"{v}{int(counts.get(v, 0)):,}" in second, v
    assert "04  그룹별 측정 정밀도" in second and "05  미결 분석" in second and "다음 조치" in second
    assert not [n for n in items["ITEM"] if n in first + second]


def test_before_adds_old_counts(judged, tmp_path):
    old = pd.read_csv(judged / "items.csv").assign(verdict_final="미결")
    old.to_csv(tmp_path / "old.csv", index=False, encoding="utf-8-sig")
    first, second = slide_texts(slides.write_pptx(tmp_path / "deck.pptx",
                                                  slides.build(judged, tmp_path / "old.csv", "합성")))
    assert "기존 → 새 판정" in first and f"기존 {len(old):,}" in second


def test_undecided_causes_take_the_first_matching_rule():
    def cause(**facts) -> str:
        base = {"zone": "정량", "basis": "linear", "reason": "", "status": "", "y": 0.3}
        return next(c.name for c in slides.CAUSES if c.hit({**base, **facts}))
    assert cause(zone="die 부족", y=-np.inf) == "die 부족"
    assert cause(basis="loq", reason="DOE 구간 11~12가 LoQ(10) 이상이지만 이동 구간이 ±Δ(1)에 걸침") == "허용폭 경계"
    assert cause(y=1.4, status="회차 흔들림") == "측정 흔들림"
    assert cause(status="정상;회차 흔들림") == "기준 조건 흔들림"
    assert cause() == "허용폭 경계"


def test_forest_rows_merge_identical_intervals_and_rotate_causes():
    rows = pd.DataFrame({"ID": ["A", "B", "C", "D"], "cause": ["측정 흔들림", "측정 흔들림", "측정 흔들림", "허용폭 경계"],
                         "color": ["C27C0E"] * 3 + ["B5523B"], "x": [0.5, 0.5, 2.0, 1.1], "y": [1.2, 1.2, 1.5, 0.2]})
    rows = rows.assign(lo=rows["x"] - rows["y"], hi=rows["x"] + rows["y"])
    picked = slides.forest_rows(rows, 2)
    assert list(picked["ID"]) == ["A 외 1개", "D"]
    assert list(slides.forest_rows(rows, 5)["ID"]) == ["A 외 1개", "C", "D"]


def test_dcc_plans_slides_with_before(tmp_path):
    import dcc
    for name in ("p1", "p2", "d", "old.csv"):
        (tmp_path / name).mkdir() if "." not in name else (tmp_path / name).write_text("x")
    cfg = tmp_path / "combos.ini"
    cfg.write_text("[A1]\npor = p1\n  p2\ndoe = d\n", encoding="utf-8")
    (tmp_path / "결과" / "A1").mkdir(parents=True)
    (tmp_path / "결과" / "A1" / "items.csv").write_text("x")
    cfg.write_text("[defaults]\nout = 결과\n[A1]\npor = p1\n  p2\ndoe = d\n", encoding="utf-8")
    a = dcc.build_parser().parse_args(["slides", "A1", "--before", str(tmp_path / "old.csv"), "--config", str(cfg)])
    c = dcc.load_config(cfg)["A1"]
    (name, args), = dcc.plan(a.cmd, c, a)
    out = tmp_path / "결과" / "A1"
    assert name == "slides" and args == ["slides.py", str(out.resolve()), "--out", str(out.resolve() / "slides.pptx"),
                                         "--label", "A1", "--before", str((tmp_path / "old.csv").resolve())]
