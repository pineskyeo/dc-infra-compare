"""WO-U U-A: 분포 모양 지표 열(SHAPE_COLS)과 status 'log 후보'·'두 덩어리'. 합성 데이터만 (seed 고정)."""
import importlib.util
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import fail_evidence
from por_doe_compare import (BIMODAL_BC_MIN, LOG_DECADES_MIN, METRIC_COLS, SHAPE_COLS, ST_BIMODAL, ST_LOG_CANDIDATE,
                             ST_OK, STATUS_COLS, bimodality_coef, item_status, judge)

ROOT = Path(__file__).resolve().parents[1]
BEFORE_WOU = "f736220"      # WO-U 직전 커밋 (분포 모양 열이 없던 판)
DELTA, R_TOL = 5.0, 0.1


def runs(x: np.ndarray, rng: np.random.Generator, J: int = 3, rel: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    """die별 참값 x → POR die × J 회차, DOE die 값 (각각 상대 잡음 rel)."""
    Y = x[:, None] * (1 + rel * rng.normal(size=(x.size, J)))
    z = x * (1 + rel * rng.normal(size=x.size))
    return Y, z


def lognormal(seed: int = 1, n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return runs(10 ** rng.normal(0, 0.6, n), rng)


def normal(seed: int = 2, n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return runs(100 + rng.normal(0, 1, n), rng)


def with_zero(seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    Y, z = lognormal(seed)
    Y[0, :] = 0.0
    return Y, z


def mixed_sign(seed: int = 4) -> tuple[np.ndarray, np.ndarray]:
    Y, z = lognormal(seed)
    Y[::2] *= -1
    return Y, z


def two_lumps(sep: float, seed: int = 5, n: int = 200) -> tuple[np.ndarray, np.ndarray]:
    """두 로그정규 혼합: 반은 1 근처, 반은 sep 배 근처 (log10 표준편차 0.08)."""
    rng = np.random.default_rng(seed)
    lg = np.where(np.arange(n) < n // 2, 0.0, np.log10(sep)) + rng.normal(0, 0.08, n)
    return runs(10 ** lg, rng)


CASES = {
    "lognormal": lognormal,
    "normal": normal,
    "with_zero": with_zero,
    "mixed_sign": mixed_sign,
    "two_lumps_10x": lambda: two_lumps(10.0),
    "two_lumps_1000x": lambda: two_lumps(1000.0),
}


def names(st: dict) -> list[str]:
    return st["status"].split(";")


# w1
def test_w1_lognormal_is_log_candidate():
    st = item_status(*lognormal(), DELTA)
    assert list(st) == STATUS_COLS
    assert STATUS_COLS[1 + len(METRIC_COLS):1 + len(METRIC_COLS) + len(SHAPE_COLS)] == SHAPE_COLS
    assert st["decades"] >= LOG_DECADES_MIN
    assert st["log_fit"] > 0
    assert st["log_fit"] == pytest.approx(abs(st["skew_lin"]) - abs(st["skew_log"]))
    assert ST_LOG_CANDIDATE in names(st)
    assert ST_BIMODAL not in names(st)


# w2
def test_w2_normal_is_not_log_candidate():
    st = item_status(*normal(), DELTA)
    assert st["decades"] < LOG_DECADES_MIN
    assert ST_LOG_CANDIDATE not in names(st) and ST_BIMODAL not in names(st)


# w3
@pytest.mark.parametrize("make", [with_zero, mixed_sign])
def test_w3_zero_or_mixed_sign_gives_nan(make):
    st = item_status(*make(), DELTA)
    for c in ("decades", "skew_log", "log_fit", "bimodality_log"):
        assert math.isnan(st[c]), c
    assert math.isfinite(st["skew_lin"])
    assert ST_LOG_CANDIDATE not in names(st) and ST_BIMODAL not in names(st)


# w4
@pytest.mark.parametrize("sep", [10.0, 1000.0])
def test_w4_two_lognormal_lumps_are_bimodal(sep):
    st = item_status(*two_lumps(sep), DELTA)
    assert st["bimodality_log"] > BIMODAL_BC_MIN
    assert ST_BIMODAL in names(st)


def test_w4_bimodality_coef_formula():
    """BC = (g² + 1) / (k + 3(n−1)²/((n−2)(n−3))), g·k 는 표본 보정식. 모멘트로 직접 계산한 값과 같은지."""
    v = np.log10(np.abs(two_lumps(10.0)[0].mean(axis=1)))
    n = v.size
    d = v - v.mean()
    m2, m3, m4 = (d ** 2).mean(), (d ** 3).mean(), (d ** 4).mean()
    g = m3 / m2 ** 1.5 * math.sqrt(n * (n - 1)) / (n - 2)
    k = ((n + 1) * (m4 / m2 ** 2 - 3) + 6) * (n - 1) / ((n - 2) * (n - 3))
    assert bimodality_coef(v) == pytest.approx((g ** 2 + 1) / (k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))))
    assert math.isnan(bimodality_coef(v[:3]))
    assert math.isnan(bimodality_coef(np.ones(10)))


def test_w4_new_names_in_fail_evidence_tables():
    for name in (ST_LOG_CANDIDATE, ST_BIMODAL):
        assert name in fail_evidence.STATUS_PRIORITY
        assert name in fail_evidence.STATUS_PANELS


# w5: 판정·기존 status 불변 (WO-U 직전 판과 비교)
@pytest.fixture(scope="module")
def old_module(tmp_path_factory):
    try:
        src = subprocess.run(["git", "show", f"{BEFORE_WOU}:por_doe_compare.py"], cwd=ROOT,
                             check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip(f"git 으로 {BEFORE_WOU} 를 읽을 수 없음")
    path = tmp_path_factory.mktemp("before_wou") / "por_doe_compare_before_wou.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("por_doe_compare_before_wou", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return bool(np.all(a == b))


def without_shape(status: str) -> str:
    rest = [s for s in status.split(";") if s not in (ST_LOG_CANDIDATE, ST_BIMODAL, ST_OK)]
    return ";".join(rest) or ST_OK


@pytest.mark.parametrize("name", list(CASES))
def test_w5_verdict_and_old_status_unchanged(name, old_module):
    Y, z = CASES[name]()
    new_res, new_mask = judge(Y, z, R_TOL)
    old_res, old_mask = old_module.judge(Y, z, R_TOL)
    assert list(new_res) == list(old_res)
    assert all(same(new_res[k], old_res[k]) for k in new_res), name
    assert np.array_equal(new_mask, old_mask)

    new_st = item_status(Y, z, new_res["delta"])
    old_st = old_module.item_status(Y, z, old_res["delta"])
    assert without_shape(new_st["status"]) == old_st["status"]
    assert all(same(new_st[k], old_st[k]) for k in old_st if k != "status")
