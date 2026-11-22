"""TOST 의 오류율: ci_median (부호검정 90% CI) + tost 를 t(3) 잡음으로 반복. seed 고정."""
import numpy as np
import pytest

from por_doe_compare import ci_median, tost

REPS = 4000
DELTA = 0.8      # t(3) 척도 단위. 61 die 에서 shift 0 의 동등 비율이 95% 를 조금 넘는 폭 (4000회 98.9%)


def rates(n_die: int, shift: float, seed: int) -> tuple[float, float]:
    """(동등 비율, 90% CI 가 참 중앙값 shift 를 담은 비율). 잡음은 중앙값 0인 t(3)."""
    rng = np.random.default_rng(seed)
    equal = covered = 0
    for _ in range(REPS):
        center, lo, hi = ci_median(shift + rng.standard_t(3, n_die))
        equal += tost(center, lo, hi, DELTA)[0] == "동등"
        covered += lo <= shift <= hi
    return equal / REPS, covered / REPS


@pytest.mark.parametrize("n_die, seed", [(20, 11), (61, 12)])
def test_true_shift_at_delta_rarely_equal(n_die, seed):
    equal, covered = rates(n_die, DELTA, seed)
    assert equal <= 0.05, equal
    assert covered >= 0.90, covered


def test_no_shift_with_61_dies_mostly_equal():
    equal, covered = rates(61, 0.0, 13)
    assert equal >= 0.95, equal
    assert covered >= 0.90, covered
