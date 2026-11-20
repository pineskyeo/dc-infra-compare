"""group_summary.py: stability_by_group.csv의 측정정밀도% 열. 합성 데이터(tests/data/compare_ba_*.tsv)만 사용."""
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import group_summary  # noqa: E402
from compare_before_after import main as compare_main  # noqa: E402

DATA = Path(__file__).parent / "data"
BEFORE = DATA / "compare_ba_before.tsv"
AFTER = DATA / "compare_ba_after.tsv"

# 공통 ITEM(A1~A5)의 기존 측정정밀도% = 100 × √(σ_die² + σ_run²) / |por_median|
BEFORE_PREC = [
    math.hypot(8.0, 2.0) / 100 * 100,
    math.hypot(12.0, 0.0) / 200 * 100,
    math.hypot(1.5, 0.4) / 50 * 100,
    math.hypot(7.0, 1.0) / 100 * 100,
    math.hypot(6.0, 0.5) / 80 * 100,
]


def _compare_csv(tmp_path: Path) -> Path:
    out = tmp_path / "cmp"
    assert compare_main(["compare", str(BEFORE), str(AFTER), "-o", str(out)]) == 0
    return out / "compare.csv"


def _run_group_summary(monkeypatch, compare_csv: Path, out: Path) -> pd.DataFrame:
    groups = compare_csv.parent / "groups.csv"
    groups.write_text(
        "ITEM,group\nSYNTH_A1,G1\nSYNTH_A2,G1\nSYNTH_A3,G2\nSYNTH_A4,G2\nSYNTH_A5,G2\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "group_summary.py", "--compare", str(compare_csv), "--groups", str(groups), "--out", str(out),
    ])
    group_summary.main()
    return pd.read_csv(out / "stability_by_group.csv", encoding="utf-8-sig").set_index("그룹")


def test_stability_has_meas_precision_columns(tmp_path, monkeypatch):
    st = _run_group_summary(monkeypatch, _compare_csv(tmp_path), tmp_path / "gs")
    for side in ("기존", "개선"):
        for stat in ("중앙값", "25%", "75%"):
            assert f"{side} 측정정밀도% {stat}" in st.columns
    assert st.loc["전체", "기존 측정정밀도% 중앙값"] == pytest.approx(round(float(np.median(BEFORE_PREC)), 3))
    assert st.loc["전체", "기존 측정정밀도% 25%"] == pytest.approx(round(float(np.quantile(BEFORE_PREC, 0.25)), 3))
    # 안정 순위는 그대로 σ_die% 중앙값 기준
    assert "기존 안정 순위" in st.columns


def test_stability_meas_precision_from_old_compare_csv(tmp_path, monkeypatch):
    # 예전 compare.csv(측정정밀도 열 없음)도 σ_die·σ_run·por_median으로 계산
    cmp_csv = _compare_csv(tmp_path)
    old = pd.read_csv(cmp_csv, encoding="utf-8-sig")
    old = old.drop(columns=[c for c in old.columns if c.startswith("meas_precision")])
    old_csv = cmp_csv.parent / "compare_old.csv"
    old.to_csv(old_csv, index=False, encoding="utf-8-sig")
    st = _run_group_summary(monkeypatch, old_csv, tmp_path / "gs_old")
    assert st.loc["전체", "기존 측정정밀도% 중앙값"] == pytest.approx(round(float(np.median(BEFORE_PREC)), 3))
