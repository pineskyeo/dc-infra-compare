from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fail_evidence as fe  # noqa: E402
from plot_verdicts import configure_font  # noqa: E402

SYNTH = ROOT / "tests" / "data" / "fail_evidence_synth.tsv"

EXPECTED = {
    "D1": fe.J_DIFF,
    "N1": fe.J_OK,
    "GEQ": fe.J_BASE,   # por_gap/Δ = 0.25 정확히
    "GLO": fe.J_OK,     # por_gap/Δ = 0.245
    "MEQ": fe.J_BASE,   # median_out/Δ = 0.10 정확히
    "MHI": fe.J_BASE,   # median_out/Δ = 0.11
    "MLO": fe.J_OK,     # median_out/Δ = 0.09
    "P3": fe.J_BASE,    # POR 3회차, por_gap/Δ = 0.5
    "NEG": fe.J_OK,
    "VD": fe.J_OK,      # verdict 차이, 규칙은 미결-정상
    "VM": fe.J_DIFF,    # verdict 미결, 규칙은 차이
    "OVF": fe.J_NA,     # DOE_mean 엑셀 넘침
    "BLK": fe.J_NA,     # ci_low 빈칸
    "EQ1": fe.J_SKIP,
}
PLOTTED = sorted(k for k, v in EXPECTED.items() if v in fe.PLOT_ORDER)


@pytest.fixture()
def table() -> pd.DataFrame:
    return fe.evidence_table(fe.read_table(SYNTH)).set_index("ID")


def test_classify_rules_and_boundaries():
    c = fe.classify
    assert c(2.0001, 5, 2, 0, 0)[0] == fe.J_DIFF
    assert c(-5, -2.0001, 2, 0, 0)[0] == fe.J_DIFF
    assert c(2, 5, 2, 0, 0)[0] == fe.J_OK            # ci_low == Δ 는 밖이 아님
    assert c(3, 5, 2, 9, 9)[0] == fe.J_DIFF           # 규칙 1이 먼저
    assert c(-1, 3, 2, 0.25, 0) == (fe.J_BASE, "por_gap/Δ >= 0.25")
    assert c(-1, 3, 2, 0.2499, 0)[0] == fe.J_OK
    assert c(-1, 3, 2, 0, 0.10) == (fe.J_BASE, "median_out/Δ >= 0.1")
    assert c(-1, 3, 2, 0, 0.0999)[0] == fe.J_OK
    assert c(-1, 3, 2, 0.3, 0.2)[1] == "por_gap/Δ >= 0.25; median_out/Δ >= 0.1"
    # 상수는 인자로 바꿀 수 있다
    assert c(-1, 3, 2, 0.3, 0, por_gap_limit=0.5)[0] == fe.J_OK
    assert c(-1, 3, 2, 0, 0.05, median_out_limit=0.05)[0] == fe.J_BASE


def test_parse_value():
    assert fe.parse_value(" 1.5 ") == (1.5, None)
    assert fe.parse_value("") == (None, "빈칸")
    v, p = fe.parse_value("-49595******")
    assert v is None and p.startswith("숫자 아님")
    assert fe.parse_value("nan")[0] is None


def test_judgements_and_notes(table):
    assert table["judgement"].to_dict() == EXPECTED
    assert table.at["VD", "note"] == fe.MISMATCH_NOTE
    assert table.at["VM", "note"] == fe.MISMATCH_NOTE
    assert table.at["D1", "note"] == ""
    assert "DOE_mean 숫자 아님" in table.at["OVF", "note"]
    assert "ci_low 빈칸" in table.at["BLK", "note"]
    assert table.at["GEQ", "rule_hit"] == "por_gap/Δ >= 0.25"
    assert table.at["MEQ", "rule_hit"] == "median_out/Δ >= 0.1"
    assert table.at["D1", "rule_hit"] == "CI 전체가 ±Δ 밖"
    assert pd.isna(table.at["EQ1", "doe_pct"])
    assert pd.isna(table.at["OVF", "center_over_delta"])


def test_metrics(table):
    d1 = table.loc["D1"]
    assert d1["doe_pct"] == pytest.approx(5)
    assert d1["por1_pct"] == pytest.approx(0)
    assert d1["por2_pct"] == pytest.approx(0.1)
    assert pd.isna(d1["por3_pct"])
    assert d1["delta_pct"] == pytest.approx(2)
    assert d1["center_over_delta"] == pytest.approx(2.5)
    assert d1["ci_low_over_delta"] == pytest.approx(1.75)
    assert d1["ci_high_over_delta"] == pytest.approx(3.25)
    assert d1["ci_half_over_delta"] == pytest.approx(0.75)
    assert d1["loq_multiple"] == pytest.approx(20)
    assert d1["por_gap_pct"] == pytest.approx(0.1 / 100.05 * 100)

    neg = table.loc["NEG"]  # |por_median| 로 나눈다
    assert neg["doe_pct"] == pytest.approx(2)
    assert neg["por2_pct"] == pytest.approx(-0.2)
    assert neg["delta_pct"] == pytest.approx(2)
    assert neg["loq_multiple"] == pytest.approx(10)

    p3 = table.loc["P3"]
    assert p3["por3_pct"] == pytest.approx((101 - 100.1) / 100.1 * 100)
    assert p3["por_gap_over_delta"] == pytest.approx(0.5)
    assert p3["por_gap_pct"] == pytest.approx(1 / 100.4 * 100)
    assert p3["median_out_over_delta"] == 0

    assert table.at["GEQ", "por_gap_over_delta"] == pytest.approx(0.25)
    assert table.at["GLO", "por_gap_over_delta"] == pytest.approx(0.245)
    assert table.at["MEQ", "median_out_over_delta"] == pytest.approx(0.10)
    assert table.at["MHI", "median_out_over_delta"] == pytest.approx(0.11)
    assert table.at["MLO", "median_out_over_delta"] == pytest.approx(0.09)


def test_missing_column_marks_targets_uncomputable():
    df = fe.read_table(SYNTH).drop(columns=["LoQ"])
    t = fe.evidence_table(df).set_index("ID")
    targets = [k for k, v in EXPECTED.items() if v != fe.J_SKIP]
    assert (t.loc[targets, "judgement"] == fe.J_NA).all()
    assert "LoQ 열 없음" in t.at["D1", "note"]
    assert t.at["EQ1", "judgement"] == fe.J_SKIP


def test_single_por_column_is_uncomputable():
    df = fe.read_table(SYNTH).drop(columns=["POR2_mean", "POR3_mean"])
    t = fe.evidence_table(df).set_index("ID")
    assert t.at["N1", "judgement"] == fe.J_NA
    assert "POR 회차 평균 1개" in t.at["N1", "note"]


def test_missing_id_column_returns_error(tmp_path: Path):
    bad = tmp_path / "bad.tsv"
    fe.read_table(SYNTH).drop(columns=["verdict"]).to_csv(bad, sep="\t", index=False)
    assert fe.main(["--input", str(bad), "--out", str(tmp_path / "o")]) == 2


def _glyph_warnings(caught) -> list[str]:
    return [
        str(w.message)
        for w in caught
        if "missing from font" in str(w.message).lower()
        or re.search(r"Glyph .* missing", str(w.message), re.IGNORECASE)
    ]


def test_main_writes_outputs(tmp_path: Path, capsys):
    out = tmp_path / "out"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert fe.main(["--input", str(SYNTH), "--out", str(out)]) == 0

    for name in ("fail_evidence.csv", "forest.png", "summary.txt"):
        assert (out / name).stat().st_size > 0, name
    assert sorted(p.stem for p in (out / "items").glob("*.png")) == PLOTTED

    csv = pd.read_csv(out / "fail_evidence.csv", encoding="utf-8-sig",
                      dtype={"ITEM": str}, keep_default_na=False, na_values=[""])
    assert list(csv.columns) == ["ITEM"] + fe.csv_columns([1, 2, 3])[1:]
    assert dict(zip(csv["ITEM"], csv["judgement"])) == EXPECTED

    summary = (out / "summary.txt").read_text(encoding="utf-8")
    for line in ("차이: 2", "미결-정상: 5", "미결-기준 흔들림: 4", "계산 불가: 2",
                 "대상 아님: 1", "POR_GAP_OVER_DELTA = 0.25", "MEDIAN_OUT_OVER_DELTA = 0.1"):
        assert line in summary, line
    assert "fail_evidence 요약" in capsys.readouterr().out

    if configure_font() is None:
        pytest.skip("한글 후보 폰트가 없어 글리프 검사를 생략함")
    assert not _glyph_warnings(caught), _glyph_warnings(caught)


def test_main_items_filter(tmp_path: Path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(SYNTH), "--out", str(out), "--items", "D1,P3,EQ1"]) == 0
    assert sorted(p.stem for p in (out / "items").glob("*.png")) == ["D1", "P3"]
    assert (out / "forest.png").stat().st_size > 0
