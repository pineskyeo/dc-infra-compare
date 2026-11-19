"""compare 모드(기존·개선 비교) 테스트. 합성 데이터(tests/data/compare_ba_*.tsv)만 사용."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd

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
    by_id = df.set_index("ID")

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
