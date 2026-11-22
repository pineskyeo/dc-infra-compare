"""WO-U U-A: 분포 모양 지표 열(SHAPE_COLS)과 status 'log 후보'·'두 덩어리'. 합성 데이터만 (seed 고정)."""
import importlib.util
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

import fail_evidence
from por_doe_compare import (BIMODAL_BC_MIN, BIMODAL_MIN_DIE, LOG_DECADES_MIN, LOG_FIT_MIN, METRIC_COLS, SHAPE_COLS, SHAPE_EXCLUDE_ABS, ST_BIMODAL,
                             ST_LOG_CANDIDATE, ST_OK, STATUS_COLS, bimodality_coef, item_status, judge, shape_cols)

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
    assert st["log_fit"] > LOG_FIT_MIN
    assert st["log_fit"] == pytest.approx(abs(st["skew_lin"]) - abs(st["skew_log"]))
    assert ST_LOG_CANDIDATE in names(st)
    assert ST_BIMODAL not in names(st)


# w2
def test_w2_normal_is_not_log_candidate():
    st = item_status(*normal(), DELTA)
    assert st["decades"] < LOG_DECADES_MIN
    assert ST_LOG_CANDIDATE not in names(st) and ST_BIMODAL not in names(st)


def test_decades_between_1_and_2_is_log_candidate():
    """LOG_DECADES_MIN = 1.0: decades ≈ 1.5 (log10 표준편차 0.32 → P1~P99 폭 ≈ 4.65 × 0.32), log_fit > LOG_FIT_MIN 이면 후보."""
    rng = np.random.default_rng(21)
    st = item_status(*runs(10 ** (0.32 * norm_quantiles(300)), rng), DELTA)
    assert LOG_DECADES_MIN == 1.0
    assert 1.0 <= st["decades"] < 2.0
    assert st["decades"] == pytest.approx(1.5, abs=0.1)
    assert st["log_fit"] > LOG_FIT_MIN
    assert ST_LOG_CANDIDATE in names(st)


@pytest.mark.parametrize("log_fit, cand", [(0.05, False), (0.15, True)])
def test_z3_log_fit_min_boundary(log_fit, cand):
    """LOG_FIT_MIN = 0.1: decades = 4 (0.01 ×5, 100 ×5 꼬리)이고 사분위가 1, r, r² (log 등간격 → skew_log = 0,
    skew_lin = (r−1)/(r+1) = log_fit). n = 100 → P1·P99 는 꼬리, P25·P50·P75 는 각 블록 안."""
    r = (1 + log_fit) / (1 - log_fit)
    x = np.array([0.01] * 5 + [1.0] * 30 + [r] * 30 + [r * r] * 30 + [100.0] * 5)
    st = item_status(np.repeat(x[:, None], 3, axis=1), x.copy(), DELTA)
    assert LOG_FIT_MIN == 0.1
    assert st["decades"] == pytest.approx(4.0)
    assert st["log_fit"] == pytest.approx(log_fit, abs=1e-9)
    assert (ST_LOG_CANDIDATE in names(st)) is cand


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


# WO-Z 1단계: Bowley 왜도, decades = log10(P99/P1), |x| ≥ 1E+90 제외
def same_shape(a: dict, b: dict) -> bool:
    return all(same(a[c], b[c]) for c in SHAPE_COLS)


def test_z1_bowley_skew_hand_computed():
    """x = 1,2,4,8,16: Q1=2, Q2=4, Q3=8 → skew_lin = (8+2−8)/6 = 1/3. log10 은 등간격 → skew_log = 0.
    decades: log10 등간격이라 P99 − P1 = 0.98 × log10(16)."""
    st = shape_cols(np.array([1.0, 2, 4, 8, 16]))
    assert st["skew_lin"] == pytest.approx(1 / 3)
    assert st["skew_log"] == pytest.approx(0, abs=1e-12)
    assert st["log_fit"] == pytest.approx(1 / 3)
    assert st["decades"] == pytest.approx(0.98 * math.log10(16))
    # 1,2,3,4,10: Q1=2, Q2=3, Q3=4 → 0 (큰 값 하나는 사분위에 안 들어감)
    assert shape_cols(np.array([1.0, 2, 3, 4, 10]))["skew_lin"] == pytest.approx(0, abs=1e-12)


def test_z1_iqr_zero_gives_nan():
    st = shape_cols(np.array([5.0, 5, 5, 5, 9]))
    for c in ("skew_lin", "skew_log", "log_fit"):
        assert math.isnan(st[c]), c
    assert math.isfinite(st["decades"])


def norm_quantiles(n: int) -> np.ndarray:
    """표준정규 분위수 n개 (대칭이라 Bowley 왜도 = 0, 난수 없음)."""
    return stats.norm.ppf((np.arange(n) + 0.5) / n)


def test_z1_decades_ignores_single_outlier():
    x = 10 ** (0.3 * norm_quantiles(1000))
    base = shape_cols(x)["decades"]
    with_out = shape_cols(np.append(x, x.max() * 1e6))["decades"]
    assert abs(with_out - base) < 0.1
    assert math.log10(x.max() * 1e6 / x.min()) - with_out > 5      # 옛 max/min 이면 6자리 넘게 커졌을 값


@pytest.mark.parametrize("code", [1e97, -1e97, SHAPE_EXCLUDE_ABS])
def test_z1_open_code_die_is_excluded(code):
    rng = np.random.default_rng(12)
    x = 10 ** rng.normal(0, 0.6, 50)
    st = shape_cols(np.append(x, code))
    assert same_shape(st, shape_cols(x))
    assert all(math.isfinite(st[c]) for c in SHAPE_COLS)       # 음수 코드여도 뺀 뒤엔 부호 하나


def test_z1_open_code_die_excluded_in_item_status():
    Y, z = lognormal(seed=13, n=60)
    Y2 = np.vstack([Y, np.full((1, Y.shape[1]), 1e97)])
    z2 = np.append(z, 1e97)
    a, b = item_status(Y, z, DELTA), item_status(Y2, z2, DELTA)
    assert same_shape(a, b)


def test_z2_open_code_die_not_counted_for_bimodal():
    """두 덩어리 die 수 조건에서 1E+97 die는 세지 않는다. 1 근처 3개 + 1000 근처 6·7개 (점 질량, BC 손계산 ≈ 0.61·0.67)."""
    def item(n_hi: int) -> dict:
        x = np.array([1.0] * 3 + [1000.0] * n_hi + [1e97])
        return item_status(np.repeat(x[:, None], 3, axis=1), x.copy(), DELTA)
    nine, ten = item(6), item(7)      # 유한 die 9개 + 코드 1, 유한 die 10개 + 코드 1
    assert BIMODAL_MIN_DIE == 10
    assert nine["bimodality_log"] > BIMODAL_BC_MIN and ten["bimodality_log"] > BIMODAL_BC_MIN
    assert ST_BIMODAL not in names(nine)
    assert ST_BIMODAL in names(ten)


def test_z1_single_outlier_does_not_pin_skew():
    """정규 60개 + 큰 값 1개. 옛 모멘트 왜도는 ~7.7 로 튀던 경우."""
    x = 100 + norm_quantiles(60)
    base, st = shape_cols(x), shape_cols(np.append(x, 1e4))
    for c in ("skew_lin", "skew_log"):
        assert abs(st[c]) < 0.5, c
        assert abs(st[c] - base[c]) < 0.1, c


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
    # 결정 4: verdict_no_accuracy 자리에 verdict_with_accuracy. --level 이 없으면 참고 판정도 없다
    assert list(new_res) == ["verdict_with_accuracy" if k == "verdict_no_accuracy" else k for k in old_res]
    assert all(same(new_res[k], old_res[k]) for k in new_res if k != "verdict_with_accuracy"), name
    assert same(new_res.get("verdict_with_accuracy", np.nan), np.nan), name
    assert np.array_equal(new_mask, old_mask)

    new_st = item_status(Y, z, new_res["delta"])
    old_st = old_module.item_status(Y, z, old_res["delta"])
    assert without_shape(new_st["status"]) == old_st["status"]
    assert all(same(new_st[k], old_st[k]) for k in old_st if k != "status")
