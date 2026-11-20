"""WO-L: fail_evidence·compare_before_after가 items.csv의 짝지은 회차 차(por_gap_over_delta)를 쓰는지. 합성 데이터만."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import compare_before_after as cba  # noqa: E402
import fail_evidence as fe  # noqa: E402

PAIRED = "짝지은 회차 차"
OLD = "옛 정의(회차 평균 차)"
OLD_LINE = f"por_gap: {OLD} 1행 (items.csv에 {PAIRED} 열 없음)"

# 회차 평균 100, 100.5, 101 → 평균 차 1, Δ=2 → 옛 정의 gap/Δ = 0.5 (참고 열일 뿐, 판단에 안 씀).
# por_median 100.5는 [min, max] 안이라 median_out = 0, CI [-1, 3]은 ±Δ에 걸쳐 차이가 아님.
ROW = {
    "ID": "G1", "verdict": "미결", "reason": "경계", "por_median": "100.5", "DOE_mean": "100.5",
    "POR1_mean": "100", "POR2_mean": "100.5", "POR3_mean": "101",
    "center": "1", "ci_low": "-1", "ci_high": "3", "delta": "2", "LoQ": "1",
    "sigma_die": "0.5", "sigma_run": "0.2",
}


def _write(tmp_path: Path, with_paired: bool) -> Path:
    row = dict(ROW, por_gap_over_delta="0.1") if with_paired else dict(ROW)
    path = tmp_path / ("paired.tsv" if with_paired else "old.tsv")
    pd.DataFrame([row]).to_csv(path, sep="\t", index=False)
    return path


# ---------------------------------------------------------------- fail_evidence

def test_fail_evidence_uses_paired_gap(tmp_path):
    t = fe.evidence_table(fe.read_table(_write(tmp_path, True))).set_index("ID")
    assert t.at["G1", "por_gap_over_delta"] == pytest.approx(0.1)
    assert t.at["G1", "por_gap_def"] == PAIRED
    assert t.at["G1", "por_gap_pct"] == pytest.approx(0.1 * 2 / 100.5 * 100)
    assert t.at["G1", "judgement"] == fe.J_PEND  # WO-L 정정: 미결은 하나(J_OK 삭제)
    assert "por_gap:" not in fe.summary_text(t.reset_index())


def test_fail_evidence_old_definition_fallback(tmp_path):
    t = fe.evidence_table(fe.read_table(_write(tmp_path, False))).set_index("ID")
    assert t.at["G1", "por_gap_over_delta"] == pytest.approx(0.5)
    assert t.at["G1", "por_gap_def"] == OLD
    assert t.at["G1", "judgement"] == fe.J_PEND  # WO-L 정정: gap/Δ 0.5여도 미결 하나(J_BASE 삭제)
    assert OLD_LINE in fe.summary_text(t.reset_index())


def test_fail_evidence_blank_paired_falls_back(tmp_path):
    df = fe.read_table(_write(tmp_path, True))
    df["por_gap_over_delta"] = ""
    t = fe.evidence_table(df).set_index("ID")
    assert t.at["G1", "por_gap_over_delta"] == pytest.approx(0.5)
    assert t.at["G1", "por_gap_def"] == OLD


def test_fail_evidence_main_csv_column(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_write(tmp_path, True)), "--out", str(out)]) == 0
    csv = pd.read_csv(out / "fail_evidence.csv", encoding="utf-8-sig", keep_default_na=False)
    cols = list(csv.columns)
    assert cols.count("por_gap_over_delta") == 1  # with_status가 입력 열을 다시 붙이지 않음
    assert cols[cols.index("por_gap_over_delta") + 1] == "por_gap_def"
    assert float(csv.at[0, "por_gap_over_delta"]) == pytest.approx(0.1)
    assert "por_gap:" not in (out / "summary.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------- compare_before_after evidence

def test_compare_evidence_uses_paired_gap(tmp_path):
    ev = cba.evidence_table(cba.read_result(_write(tmp_path, True))).set_index("ID")
    assert ev.at["G1", "por_gap_over_delta"] == pytest.approx(0.1)
    assert ev.at["G1", "por_gap_def"] == PAIRED
    assert ev.at["G1", "por_gap_pct"] == pytest.approx(0.1 * 2 / 100.5 * 100)
    assert ev.at["G1", "group"] == cba.J_PEND  # WO-L 정정: 미결은 하나(J_OK 삭제)

    out = tmp_path / "ev"
    assert cba.main(["evidence", str(_write(tmp_path, True)), "-o", str(out)]) == 0
    assert "por_gap:" not in (out / "summary.txt").read_text(encoding="utf-8")
    cols = list(pd.read_csv(out / "evidence.csv", encoding="utf-8-sig").columns)
    assert cols[cols.index("por_gap_over_delta") + 1] == "por_gap_def"


def test_compare_evidence_old_definition_fallback(tmp_path):
    ev = cba.evidence_table(cba.read_result(_write(tmp_path, False))).set_index("ID")
    assert ev.at["G1", "por_gap_over_delta"] == pytest.approx(0.5)
    assert ev.at["G1", "por_gap_def"] == OLD
    assert ev.at["G1", "group"] == cba.J_PEND  # WO-L 정정: gap/Δ 0.5여도 미결 하나(J_BASE 삭제)

    out = tmp_path / "ev"
    assert cba.main(["evidence", str(_write(tmp_path, False)), "-o", str(out)]) == 0
    assert OLD_LINE in (out / "summary.txt").read_text(encoding="utf-8")
