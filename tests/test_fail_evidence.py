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

# WO-L 정정: 미결을 나누지 않는다. por_gap/Δ·median_out/Δ는 참고 열일 뿐이라 경계값 행도 모두 J_PEND.
EXPECTED = {
    "D1": fe.J_DIFF,
    "N1": fe.J_PEND,
    "GEQ": fe.J_PEND,   # por_gap/Δ = 0.25 정확히
    "GLO": fe.J_PEND,   # por_gap/Δ = 0.245
    "MEQ": fe.J_PEND,   # median_out/Δ = 0.10 정확히
    "MHI": fe.J_PEND,   # median_out/Δ = 0.11
    "MLO": fe.J_PEND,   # median_out/Δ = 0.09
    "P3": fe.J_PEND,    # POR 3회차, por_gap/Δ = 0.5
    "NEG": fe.J_PEND,
    "VD": fe.J_PEND,    # verdict 차이, 규칙은 미결
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
    # WO-L 정정: classify는 CI와 Δ만 본다(por_gap/median_out 인자·기준 상수 삭제). 경계에 걸리면 모두 미결.
    c = fe.classify
    assert c(2.0001, 5, 2) == (fe.J_DIFF, "CI 전체가 ±Δ 밖")
    assert c(-5, -2.0001, 2)[0] == fe.J_DIFF
    assert c(2, 5, 2) == (fe.J_PEND, "CI가 ±Δ 경계에 걸림")   # ci_low == Δ 는 밖이 아님
    assert c(-2, -1, 2)[0] == fe.J_PEND                       # ci_high == -Δ 도 밖이 아님
    assert c(-1, 3, 2)[0] == fe.J_PEND


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
    # WO-L 정정: por_gap/median_out 기준이 없어져 rule_hit는 CI 문구뿐이다.
    assert table.at["GEQ", "rule_hit"] == "CI가 ±Δ 경계에 걸림"
    assert table.at["MEQ", "rule_hit"] == "CI가 ±Δ 경계에 걸림"
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
    assert list(csv.columns) == ["ITEM"] + fe.csv_columns([1, 2, 3])[1:] + ["status", "status_detail", "mean_median_ratio",
                                                                        "run_jitter_pct", "run_jitter_over_delta", "spearman_size_jitter",
                                                                        "por_gap_over_noise",
                                                                        "sigma_meas", "meas_precision_pct", "sigma_meas_over_delta"]
    assert dict(zip(csv["ITEM"], csv["judgement"])) == EXPECTED

    summary = (out / "summary.txt").read_text(encoding="utf-8")
    # WO-L 정정: 미결 하나로 합쳐 9개(옛 5+4), 삭제된 기준 상수 줄은 없고 ITEM_AXIS 줄만 남는다.
    for line in ("차이: 2", "미결: 9", "계산 불가: 2",
                 "대상 아님: 1", "ITEM_AXIS_OVER_DELTA = 3"):
        assert line in summary, line
    assert "POR_GAP_OVER_DELTA" not in summary and "MEDIAN_OUT_OVER_DELTA" not in summary
    assert "fail_evidence 요약" in capsys.readouterr().out

    if configure_font() is None:
        pytest.skip("한글 후보 폰트가 없어 글리프 검사를 생략함")
    assert not _glyph_warnings(caught), _glyph_warnings(caught)


def test_main_items_filter(tmp_path: Path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(SYNTH), "--out", str(out), "--items", "D1,P3,EQ1"]) == 0
    assert sorted(p.stem for p in (out / "items").glob("*.png")) == ["D1", "P3"]
    assert (out / "forest.png").stat().st_size > 0
