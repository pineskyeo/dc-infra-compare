"""조건 불안정: 짝지은 회차 차(die별 회차 평균을 뺀 값)와 그 열(GAP_COLS) 테스트. 합성 데이터만."""
import math

import numpy as np
import pytest

from por_doe_compare import GAP_COLS, POR_GAP_NOISE_K, item_status


def parts(s: str) -> list[str]:
    return s.split(";") if s else []


def base_values() -> np.ndarray:
    """die 60개, 값 50~150."""
    return np.linspace(50, 150, 60)


def test_large_die_noise_without_run_offset_is_not_unstable():
    rng = np.random.default_rng(11)
    base = base_values()
    Y = base[:, None] + rng.normal(0, 3, (60, 3))
    st = item_status(Y, base.copy(), 1.0)
    assert "조건 불안정" not in parts(st["status"])
    assert st["por_gap_over_noise"] < POR_GAP_NOISE_K


def test_large_run_offset_is_unstable():
    rng = np.random.default_rng(12)
    base = base_values()
    Y = base[:, None] + np.array([0.0, 5.0, -5.0]) + rng.normal(0, 0.3, (60, 3))
    st = item_status(Y, base.copy(), 2.0)
    assert "조건 불안정" in parts(st["status"])
    assert st["por_gap_over_delta"] == pytest.approx(5.0, abs=0.2)
    assert st["por_gap_over_noise"] >= POR_GAP_NOISE_K


def test_huge_die_spread_with_identical_rounds_is_not_unstable():
    rng = np.random.default_rng(13)
    base = 10 ** np.linspace(0, 4, 60)
    Y = base[:, None] + rng.normal(0, 1e-3, (60, 3))
    st = item_status(Y, base.copy(), 1.0)
    assert "조건 불안정" not in parts(st["status"])
    assert st["por_gap_over_delta"] < 1


def test_one_por_round_gives_nan_gap():
    base = base_values()
    st = item_status(base[:, None] + 10.0, base.copy(), 1.0)
    assert all(math.isnan(st[c]) for c in GAP_COLS)
    assert "조건 불안정" not in parts(st["status"])
