"""판정 기준 장표 (slides.py): pptx 패키지, 결과 숫자, 믿을 근거, 익명 번호, 미결 원인. 합성 데이터만."""
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
from por_doe_compare import rescaled_verdicts  # noqa: E402

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
    for h in ("03  판정 결과", "04  믿을 근거", "05  그룹별 측정 정밀도", "06  미결 분석", "다음 조치"):
        assert h in second, h
    counts = items["verdict_final"].value_counts()
    for v in ("동등", "미결", "차이", "판정 제외"):
        assert f"{v}{int(counts.get(v, 0)):,}" in second, v
    by_route = pd.crosstab(items["route"], items["verdict_final"])
    for route, row in by_route.iterrows():
        cells = "".join(f"{int(row.get(v, 0)):,}" if row.get(v, 0) else "·" for v in ("동등", "미결", "차이", "판정 제외"))
        assert f"{route}{int(row.sum()):,}{cells}" in second, route
    moved = items[items["verdict"] != items["verdict_final"]]
    assert len(moved), "합성 결과에 3단계에서 바뀐 ITEM 이 있어야 이 줄을 본다"
    for (a, b), k in moved.groupby(["verdict", "verdict_final"]).size().items():
        assert f"{a}→{b} {k}" in second
    assert not [n for n in items["ITEM"] if n in first + second]


def test_scale_one_reproduces_the_final_verdict_of_a_real_run(judged):
    items = slides.read_items(judged / "items.csv")
    assert list(rescaled_verdicts(items, 1.0)) == list(items["verdict_final"])


def test_proof_numbers_match_an_independent_count(judged, tmp_path):
    items = pd.read_csv(judged / "items.csv")
    second = slide_texts(slides.write_pptx(tmp_path / "deck.pptx", slides.build(judged, label="합성")))[1]
    final = items["verdict_final"]
    judged_rows = items[final.isin(["동등", "미결", "차이"])]
    pairs = judged_rows["por_ttest_sig"].str.split("/", expand=True).astype(int)
    assert f"{100 * pairs[0].sum() / pairs[1].sum():.0f}%같은 조건끼리도 t-test는 '다름'" in second
    diff = items[final == "차이"]
    assert len(diff), "합성 결과에 차이 ITEM 이 있어야 이 근거를 본다"
    assert f"{(diff['ttest'] == '유의차').sum()}/{len(diff)}차이는 t-test로도 확인" in second
    now = judged_rows["verdict_final"]
    kept = (rescaled_verdicts(judged_rows, 0.8) == now) & (rescaled_verdicts(judged_rows, 1.2) == now)
    assert f"{100 * kept.mean():.0f}%허용폭을 ±20% 바꿔도 같은 판정" in second


def test_tolerance_proof_splits_changes_into_boundary_and_flips():
    linear = {"zone": "정량", "route": "선형 TOST", "cls_level": "정량", "delta": 1.0}
    items = pd.DataFrame([
        {**linear, "verdict": "동등", "center": 0.9, "ci_low": 0.85, "ci_high": 0.95},    # ×0.8 → 차이
        {**linear, "verdict": "미결", "center": 0.8, "ci_low": 0.5, "ci_high": 1.1},      # ×1.2 → 동등
        {**linear, "verdict": "동등", "center": 0.0, "ci_low": -0.1, "ci_high": 0.1},
        {**linear, "verdict": "차이", "center": 3.0, "ci_low": 2.9, "ci_high": 3.1},
        {**linear, "verdict": "판정 제외", "zone": "판정 제외"},
    ]).assign(verdict_final=lambda t: t["verdict"])
    proof = slides.tolerance_proof(items)
    assert (proof.big, proof.detail) == ("50%", "바뀌는 2개 · 미결 경계 1 · 동등↔차이 1")
    assert proof.chart.startswith(b"\x89PNG")
    steady = slides.tolerance_proof(items.iloc[2:])
    assert (steady.big, steady.detail) == ("100%", "±20%에서 바뀌는 ITEM 없음")


def test_old_result_without_route_says_so(judged, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    pd.read_csv(judged / "items.csv").drop(columns=["route"]).to_csv(folder / "items.csv", index=False)
    second = slide_texts(slides.write_pptx(tmp_path / "deck.pptx", slides.build(folder, label="합성")))[1]
    assert "판정 길(route) 열이 없어" in second and "03  판정 결과" in second


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
