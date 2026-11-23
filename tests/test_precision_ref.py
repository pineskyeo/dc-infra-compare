"""items.csv 참고 열 (판정에 안 씀): LoQ 배수·정밀도 %·분해능 %, robust 퍼짐·잡음 기울기와 잡음 모양, 판정력."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from por_doe_compare import K_LOQ, judgeability, loq_ref, noise_cols, noise_pattern, spread_robust, theil_sen

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *args) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "OMP_NUM_THREADS": "1"}
    subprocess.run([sys.executable, "-B", str(ROOT / script), *map(str, args)], cwd=ROOT, env=env,
                   check=True, capture_output=True, text=True)


@pytest.fixture(scope="module")
def items(tmp_path_factory) -> pd.DataFrame:
    base = tmp_path_factory.mktemp("precision_ref")
    data = base / "por3"
    run("examples/make_por3_data.py", data)
    run("por_doe_compare.py", "--por", data / "por_run1", "--por", data / "por_run2", "--por", data / "por_run3",
        "--doe", data / "doe", "--level", data / "level.csv", "--blank", data / "blank",
        "--blank-map", data / "blank_map.csv", "--out", base / "out")
    return pd.read_csv(base / "out" / "items.csv", encoding="utf-8-sig", keep_default_na=False, na_values=[""],
                       float_precision="round_trip")


def test_loq_columns_follow_their_formulas_on_every_row(items):
    med, loq, step = (items[c].astype(float) for c in ("por_median", "LoQ", "resolution_step"))
    nonzero = (med != 0) & med.notna()
    np.testing.assert_array_equal(items["rsd_pct"], (100 * (loq / K_LOQ) / med.abs()).where(nonzero))
    np.testing.assert_array_equal(items["resolution_pct"], (100 * step / med.abs()).where(nonzero))
    np.testing.assert_array_equal(items["loq_ratio"], (med.abs() / loq).where(loq > 0))
    assert items["rsd_pct"].notna().sum() >= len(items) - 2


def test_judgeability_matches_ci_half_over_delta_bands_on_every_row(items):
    x = items["ci_half_over_delta"].astype(float)
    expected = np.select([x <= 0.5, x <= 0.8, x > 0.8], ["안정", "주의", "불안정"], default="")
    assert items["judgeability"].fillna("").tolist() == expected.tolist()
    assert {"안정"} <= set(items["judgeability"].dropna())


def test_loq_ref_blank_when_median_or_loq_is_zero_or_nan():
    assert all(np.isnan(v) for k, v in loq_ref(0.0, 1.0, 0.1).items() if k != "loq_ratio")
    assert loq_ref(0.0, 1.0, 0.1)["loq_ratio"] == 0.0
    assert np.isnan(loq_ref(5.0, 0.0, 0.1)["loq_ratio"])
    assert all(np.isnan(v) for v in loq_ref(np.nan, np.nan, np.nan).values())
    assert loq_ref(-4.0, 2.0, 0.04) == {"loq_ratio": 2.0, "rsd_pct": 100 * 0.2 / 4, "resolution_pct": 1.0}


def test_judgeability_band_edges():
    assert [judgeability(v) for v in (0.0, 0.5, 0.5001, 0.8, 0.81, 5.0, np.nan, np.inf)] == \
        ["안정", "안정", "주의", "주의", "불안정", "불안정", "", ""]


def noise(Y: np.ndarray) -> dict:
    return noise_cols(Y, spread_robust(Y.mean(axis=1)))


def test_spread_robust_ignores_a_few_dropped_dies_and_noise_slope_tells_noise_shape():
    rng = np.random.default_rng(3)
    level = 10 ** rng.normal(0, 0.5, 61)
    narrow = np.full(61, 1.0) + rng.normal(0, 0.01, 61)
    narrow[:2] = 0.05
    assert spread_robust(narrow) < 0.1
    assert spread_robust(level) == pytest.approx(2.3, abs=0.6)
    mult = level[:, None] * (1 + 0.05 * rng.standard_normal((61, 3)))
    add = level[:, None] + 0.05 * rng.standard_normal((61, 3))
    assert noise(mult)["noise_slope"] == pytest.approx(1.0, abs=0.2)
    assert noise(add)["noise_slope"] == pytest.approx(0.0, abs=0.2)
    assert np.isnan(noise(-mult)["noise_slope"]) and noise(-mult)["noise_pattern"] == "판별 불가"


def test_theil_sen_matches_scipy_slope_and_interval_with_ties():
    for seed in range(50):
        rng = np.random.default_rng(seed)
        x, y = np.round(rng.normal(size=40), 1), np.round(rng.normal(size=40), 1)
        r = stats.theilslopes(y, x)
        assert theil_sen(x, y) == (r.slope, r.low_slope, r.high_slope)


def noise_case(kind: str, rng) -> np.ndarray:
    """die 61개 × POR 3회. 잡음 크기가 값에 따라 다르게 바뀌는 네 가지."""
    e = rng.standard_normal((61, 3))
    if kind == "additive":
        return 10 ** rng.uniform(1, 3, (61, 1)) + e
    if kind == "multiplicative":
        return 10 ** rng.uniform(1, 3, (61, 1)) * (1 + 0.03 * e)
    if kind == "reciprocal":           # 잡음이 더해지는 전류의 역수 (저항): SD ∝ 값²
        return 1 / (10 ** rng.uniform(-1, 1, (61, 1)) + 0.002 * e)
    level = 10 ** rng.uniform(0, 4, (61, 1))   # 바닥 잡음 1, 그 위는 값의 1%
    return level + np.sqrt(1 + (0.01 * level) ** 2) * e


@pytest.mark.parametrize("kind, pattern, slope", [("additive", "일정", 0.0), ("multiplicative", "비례", 1.0),
                                                  ("reciprocal", "위로 갈수록 벌어짐", 2.0),
                                                  ("floor_then_proportional", "사이 (꺾임)", 0.5)])
def test_noise_pattern_names_each_synthetic_class(kind, pattern, slope):
    cols = [noise(noise_case(kind, np.random.default_rng(seed))) for seed in range(20)]
    hits = sum(c["noise_pattern"] == pattern for c in cols)
    assert hits >= 16, [c["noise_pattern"] for c in cols]
    assert np.median([c["noise_slope"] for c in cols]) == pytest.approx(slope, abs=0.15)
    assert all(c["noise_slope_lo"] <= c["noise_slope"] <= c["noise_slope_hi"] for c in cols)
    if kind == "floor_then_proportional":
        low, high = (np.median([c[k] for c in cols]) for k in ("noise_slope_low", "noise_slope_high"))
        assert low < 0.3 and high > 0.8


def test_noise_pattern_unknown_when_narrow_few_dies_or_interval_spans_zero_and_one():
    rng = np.random.default_rng(1)
    narrow = 100 + rng.uniform(-1, 1, (61, 1)) + rng.standard_normal((61, 3))
    assert noise(narrow)["noise_pattern"] == "판별 불가"
    assert noise(noise_case("multiplicative", rng)[:9])["noise_pattern"] == "판별 불가"
    assert noise_pattern(1.0, 61, -0.2, 1.3, 0.5, 0.5) == "판별 불가"
    assert noise_pattern(1.0, 61, 0.2, 0.8, 0.0, 0.71) == "사이 (꺾임)"
    assert noise_pattern(1.0, 61, -1.5, -0.1, np.nan, 0.0) == "아래로 갈수록 벌어짐"
