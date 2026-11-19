"""por_doe_compare.py items.csv 형식(ITEM 첫 열, BOM, 쉼표, '<이름>_mean' 회차 열) 입력 테스트.

합성 데이터(tests/data/compare_ba_*.tsv, fail_evidence_synth.tsv)를 그 형식으로 바꿔 쓰고,
원래 TSV로 돌린 결과와 같은지 본다.
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import fail_evidence  # noqa: E402
from compare_before_after import main as cba_main  # noqa: E402

DATA = Path(__file__).parent / "data"


def _to_items_csv(src: Path, dst: Path) -> Path:
    """합성 TSV를 items.csv 형식으로 바꾼다: ID->ITEM, POR1/2_mean->run_a/run_b_mean, UNIT 열 추가."""
    df = pd.read_csv(src, sep="\t", dtype=str, keep_default_na=False, comment="#")
    df = df.rename(columns={"ID": "ITEM", "POR1_mean": "run_a_mean", "POR2_mean": "run_b_mean"})
    df.insert(1, "UNIT", "nm")
    df.to_csv(dst, index=False, encoding="utf-8-sig")
    return dst


def test_compare_before_after_reads_items_csv(tmp_path):
    ref = tmp_path / "ref"
    assert cba_main(["compare", str(DATA / "compare_ba_before.tsv"),
                     str(DATA / "compare_ba_after.tsv"), "-o", str(ref)]) == 0
    b = _to_items_csv(DATA / "compare_ba_before.tsv", tmp_path / "before_items.csv")
    a = _to_items_csv(DATA / "compare_ba_after.tsv", tmp_path / "after_items.csv")
    assert b.read_bytes().startswith(b"\xef\xbb\xbfITEM,")
    out = tmp_path / "out"
    assert cba_main(["compare", str(b), str(a), "-o", str(out)]) == 0
    got = pd.read_csv(out / "compare.csv", dtype=str, keep_default_na=False)
    want = pd.read_csv(ref / "compare.csv", dtype=str, keep_default_na=False)
    pd.testing.assert_frame_equal(got, want)

    ev = tmp_path / "ev"
    assert cba_main(["evidence", str(b), "-o", str(ev)]) == 0
    assert any(ev.iterdir())


def test_fail_evidence_reads_items_csv(tmp_path):
    src = DATA / "fail_evidence_synth.tsv"
    want = fail_evidence.evidence_table(fail_evidence.read_table(src))
    df = fail_evidence.read_table(_to_items_csv(src, tmp_path / "items.csv"))
    assert "ID" in df.columns and "POR1_mean" in df.columns and "POR2_mean" in df.columns
    got = fail_evidence.evidence_table(df)
    pd.testing.assert_frame_equal(got, want)
