"""compare 모드(기존·개선 비교) 테스트. 합성 데이터(tests/data/compare_ba_*.tsv)만 사용."""
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from compare_before_after import main  # noqa: E402

DATA = Path(__file__).parent / "data"
BEFORE = DATA / "compare_ba_before.tsv"
AFTER = DATA / "compare_ba_after.tsv"


def _run_compare(out_dir: Path) -> int:
    return main(["compare", str(BEFORE), str(AFTER), "-o", str(out_dir)])


def test_compare_writes_all_outputs(tmp_path):
    out = tmp_path / "out"
    assert _run_compare(out) == 0
    for name in (
        "compare.csv",
        "summary.txt",
        "sigma_die_paired.png",
        "sigma_run_paired.png",
        "scatter_before_after.png",
    ):
        assert (out / name).is_file(), f"missing output: {name}"


def test_compare_presence_misalign_both_lower_and_counts(tmp_path):
    out = tmp_path / "out"
    assert _run_compare(out) == 0

    # compare_tables가 쓰는 열: presence(matched/only_before/only_after), misaligned(bool)
    df = pd.read_csv(out / "compare.csv", encoding="utf-8-sig")
    by_id = df.set_index("ITEM")

    # 존재 여부
    assert by_id.loc["SYNTH_B1", "presence"] == "only_before"
    assert by_id.loc["SYNTH_C1", "presence"] == "only_after"

    # 정렬 의심: por_median 상대차 |100-160|/160 = 0.375 → misaligned 열이 True
    assert bool(by_id.loc["SYNTH_A4", "misaligned"]) is True
    for other in ("SYNTH_A1", "SYNTH_A2", "SYNTH_A3", "SYNTH_A5"):
        assert bool(by_id.loc[other, "misaligned"]) is False, other

    # 둘 다 하락: σ_die 8.0→3.0, σ_run 2.0→0.5
    assert by_id.loc["SYNTH_A1", "both_lower"] == "yes"

    # 개수: 공통 5(A1~A5), 기존에만 1(B1), 개선에만 1(C1)
    counts = df["presence"].value_counts().to_dict()
    assert counts.get("matched") == 5
    assert counts.get("only_before") == 1
    assert counts.get("only_after") == 1

    # summary.txt: '정렬 의심' 줄이 있고 SYNTH_A4가 언급됨
    summary = (out / "summary.txt").read_text(encoding="utf-8")
    assert "정렬 의심" in summary
    assert "SYNTH_A4" in summary


def test_misaligned_included_by_default_and_excluded_with_flag(tmp_path):
    # 기본: 정렬 의심(SYNTH_A4)도 σ 집계에 포함 → 공통 5건, both_lower 계산됨
    out = tmp_path / "default"
    assert _run_compare(out) == 0
    df = pd.read_csv(out / "compare.csv", encoding="utf-8-sig").set_index("ITEM")
    assert bool(df.loc["SYNTH_A4", "misaligned"]) is True  # 표시용 열은 그대로
    assert df.loc["SYNTH_A4", "both_lower"] == "yes"
    summary = (out / "summary.txt").read_text(encoding="utf-8")
    assert "σ 변화 (공통 전체, 정렬 의심 포함 5건)" in summary

    # --exclude-misaligned: SYNTH_A4를 σ 집계에서 뺌 → 4건, both_lower 비움
    out2 = tmp_path / "excluded"
    assert main(["compare", str(BEFORE), str(AFTER), "-o", str(out2), "--exclude-misaligned"]) == 0
    df2 = pd.read_csv(out2 / "compare.csv", encoding="utf-8-sig").set_index("ITEM")
    assert bool(df2.loc["SYNTH_A4", "misaligned"]) is True
    assert pd.isna(df2.loc["SYNTH_A4", "both_lower"])
    summary2 = (out2 / "summary.txt").read_text(encoding="utf-8")
    assert "σ 변화 (공통·정렬 정상 4건)" in summary2


# ---------------------------------------------------------------- 측정 정밀도 (meas_precision_pct)

PREC_HEADER = "ID\tverdict\tpor_median\tsigma_die\tsigma_run\tmeas_precision_pct"


def _write_items(path: Path, header: str, rows: list[str]) -> Path:
    path.write_text("# SYNTHETIC\n" + header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_compare_uses_meas_precision_column(tmp_path):
    # 열 값이 계산값(√(3²+4²)/100 = 5%)과 일부러 다르게 둔다 → 열 값을 그대로 쓰는지 확인
    before = _write_items(tmp_path / "before.tsv", PREC_HEADER, [
        "SYN_X1\t동등\t100\t3\t4\t7.5",
        "SYN_X2\t동등\t50\t1\t0\t2",
    ])
    after = _write_items(tmp_path / "after.tsv", PREC_HEADER, [
        "SYN_X1\t동등\t100\t2\t1\t3",
        "SYN_X2\t동등\t50\t1\t1\t2.5",
    ])
    out = tmp_path / "out"
    assert main(["compare", str(before), str(after), "-o", str(out)]) == 0
    df = pd.read_csv(out / "compare.csv", encoding="utf-8-sig").set_index("ITEM")
    for col in ("meas_precision_pct_before", "meas_precision_pct_after",
                "meas_precision_pct_change", "meas_precision_status"):
        assert col in df.columns, col
    assert df.loc["SYN_X1", "meas_precision_pct_before"] == pytest.approx(7.5)
    assert df.loc["SYN_X1", "meas_precision_pct_after"] == pytest.approx(3.0)
    assert df.loc["SYN_X1", "meas_precision_pct_change"] == pytest.approx(-4.5)
    assert df.loc["SYN_X1", "meas_precision_status"] == "lower"
    assert df.loc["SYN_X2", "meas_precision_pct_change"] == pytest.approx(0.5)
    assert df.loc["SYN_X2", "meas_precision_status"] == "higher"


def test_compare_meas_precision_fallback_without_column(tmp_path):
    # 열이 없는 예전 items.csv: 100 × √(σ_die² + σ_run²) / |por_median|
    hdr = "ID\tverdict\tpor_median\tsigma_die\tsigma_run"
    before = _write_items(tmp_path / "before.tsv", hdr, ["SYN_X1\t동등\t100\t3\t4"])
    after = _write_items(tmp_path / "after.tsv", hdr, ["SYN_X1\t동등\t-100\t0.6\t0.8"])
    out = tmp_path / "out"
    assert main(["compare", str(before), str(after), "-o", str(out)]) == 0
    df = pd.read_csv(out / "compare.csv", encoding="utf-8-sig").set_index("ITEM")
    assert df.loc["SYN_X1", "meas_precision_pct_before"] == pytest.approx(5.0)
    assert df.loc["SYN_X1", "meas_precision_pct_after"] == pytest.approx(1.0)
    assert df.loc["SYN_X1", "meas_precision_status"] == "lower"

    # tests/data의 합성 TSV(열 없음)도 같은 공식
    out2 = tmp_path / "data"
    assert _run_compare(out2) == 0
    df2 = pd.read_csv(out2 / "compare.csv", encoding="utf-8-sig").set_index("ITEM")
    assert df2.loc["SYNTH_A1", "meas_precision_pct_before"] == pytest.approx(math.hypot(8.0, 2.0))
    assert df2.loc["SYNTH_A1", "meas_precision_pct_after"] == pytest.approx(math.hypot(3.0, 0.5))
    assert df2.loc["SYNTH_A1", "meas_precision_status"] == "lower"
    assert pd.isna(df2.loc["SYNTH_B1", "meas_precision_pct_after"])  # 기존에만 있는 ITEM
    # 기존 판정 열은 그대로
    assert df2.loc["SYNTH_A1", "both_lower"] == "yes"


def test_evidence_has_meas_precision_pct(tmp_path):
    out = tmp_path / "ev"
    assert main(["evidence", str(BEFORE), "-o", str(out)]) == 0
    ev = pd.read_csv(out / "evidence.csv", encoding="utf-8-sig")
    cols = list(ev.columns)
    assert "meas_precision_pct" in cols
    assert cols.index("meas_precision_pct") == cols.index("sigma_die_pct") + 1
    a1 = ev.set_index("ITEM").loc["SYNTH_A1", "meas_precision_pct"]
    assert a1 == pytest.approx(math.hypot(8.0, 2.0))
