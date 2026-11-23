"""WO-S S1: items.csv 의 log 판정 참고 열 (WO-U-A2 부터 0 없고 부호 하나인 모든 ITEM)."""
import math

import numpy as np
import pandas as pd
import pytest

import por_doe_compare as pdc
from por_doe_compare import LOG_COLS, V_EXCLUDED

R = 0.05
LOG_NUM = [c for c in LOG_COLS if c not in ("verdict_log", "verdict_log_run", "log_reason", "ci_half_over_delta")]


def parts(s: str) -> list[str]:
    return s.split(";") if s else []


def size_jitter_data(seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """die 40개, 크기 1e-12~1e-6, 작은 die일수록 log 범위가 큼 → 작을수록 흔들림."""
    rng = np.random.default_rng(seed)
    size = 10 ** np.linspace(-12, -6, 40)
    half = np.linspace(0.4, 0.02, 40) * (1 + 0.1 * rng.random(40))
    return size[:, None] * 10 ** (half[:, None] * np.array([1.0, 0.0, -1.0])), size.copy()


def larger_jitter_data() -> tuple[np.ndarray, np.ndarray]:
    """die 20개, log 범위 순위를 구간별로 뒤집어 ρ = +0.6256 → 클수록 흔들림."""
    rank, start = [], 0
    for k in (10, 8, 1, 1):
        rank.extend(range(start + k - 1, start - 1, -1))
        start += k
    size = 10 ** np.linspace(-12, -6, 20)
    half = 0.02 + 0.01 * np.asarray(rank, float)
    return size[:, None] * 10 ** (half[:, None] * np.array([1.0, 0.0, -1.0])), size.copy()


def log_normal_data(seed: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """die 200개, 크기와 무관한 작은 곱셈 흔들림 → 흔들림 status 없음."""
    rng = np.random.default_rng(seed)
    size = 10 ** rng.uniform(-12, -6, 200)
    return size[:, None] * 10 ** rng.normal(0, 0.01, (200, 3)), size * 10 ** rng.normal(0, 0.01, 200)


def run_item(Y: np.ndarray, z: np.ndarray) -> dict:
    g = pd.DataFrame(Y, columns=["POR1", "POR2", "POR3"]).assign(DOE=z)
    blank = pd.DataFrame(columns=["BLANK_ITEM"]).set_index("BLANK_ITEM")
    return pdc.judge_item("IT", g, ["POR1", "POR2", "POR3"], {"IT": "A"}, R, {}, blank, {})[0]


def assert_log_nan(row: dict) -> None:
    assert all(math.isnan(row[c]) for c in LOG_NUM)


def test_t1_smaller_jitter_fills_log_columns():
    Y, z = size_jitter_data()
    row = run_item(Y, z)
    assert pdc.ST_SIZE_JITTER in parts(row["status"])
    assert row["verdict_log"] in {"동등", "차이", "미결"}
    assert all(np.isfinite(row[c]) for c in LOG_NUM)
    assert row["delta_log"] > 0
    assert row["ci_half_over_delta_log"] == pytest.approx(
        (row["ci_high_log"] - row["ci_low_log"]) / 2 / row["delta_log"])
    assert row["ci_half_over_delta"] == pytest.approx((row["ci_high"] - row["ci_low"]) / 2 / row["delta"])
    assert row["log_reason"]


def test_judge_log_policy_is_log10_1_plus_r():
    Y, z = size_jitter_data()
    lr = pdc.judge_log(Y, z, R)
    assert lr["policy_margin"] == pytest.approx(math.log10(1 + R))
    assert lr["delta"] == pytest.approx(math.log10(1 + R) + lr["run_margin"])
    assert lr["run_margin"] == lr["sigma_rep_log"]          # WO-W: 회차 항 = die별 log 회차 흔들림
    assert "blank_status" not in lr and "accuracy_margin" not in lr


def test_log_run_tolerance_has_the_linear_form_and_judges_the_same_interval():
    Y, z = size_jitter_data()
    lr = pdc.judge_log(Y, z, R)
    assert lr["delta_run"] == pytest.approx(math.log10(1 + R) + pdc.run_factor(3) * lr["sigma_run"])
    assert lr["verdict_run"] == pdc.tost(lr["center"], lr["ci_low"], lr["ci_high"], lr["delta_run"])[0]


def test_repeat_noise_counted_twice_makes_only_the_current_log_tolerance_pass():
    """die 반복 잡음 0.04 decade, 회차 공통 이동 없음, DOE 가 실제로 ×1.08: 지금 Δ_log 는 반복 잡음을 한 번 더 더해 동등,
    선형 꼴 Δ_log_run 은 동등을 주지 않는다."""
    rng = np.random.default_rng(3)
    size = 10 ** rng.uniform(-12, -6, 61)
    Y = size[:, None] * 10 ** rng.normal(0, 0.04, (61, 3))
    z = size * 1.08 * 10 ** rng.normal(0, 0.04, 61)
    lr = pdc.judge_log(Y, z, R)
    assert lr["delta"] > lr["delta_run"]
    assert lr["verdict"] == "동등" and lr["verdict_run"] in ("미결", "차이")


def test_t2_non_jitter_status_still_fills_log_columns():
    """WO-U-A2: log 열 대상은 status 무관 (0 없고 부호 하나인 모든 ITEM)."""
    row = run_item(*log_normal_data())
    assert not {pdc.ST_SIZE_JITTER, pdc.ST_SIZE_JITTER_POS} & set(parts(row["status"]))
    assert row["verdict_log"] in {"동등", "차이", "미결"}
    assert all(np.isfinite(row[c]) for c in LOG_NUM)
    assert row["log_reason"]


def test_t3_zero_value_excluded():
    Y, z = size_jitter_data()
    Y[0, 0] = 0.0
    row = run_item(Y, z)
    assert pdc.ST_SIZE_JITTER in parts(row["status"])
    assert row["verdict_log"] == V_EXCLUDED
    assert row["log_reason"] == "0값 있음"
    assert_log_nan(row)
    assert np.isfinite(row["ci_half_over_delta"])


def test_t4_mixed_sign_excluded():
    Y, z = size_jitter_data()
    Y[5], z[5] = -Y[5], -z[5]
    row = run_item(Y, z)
    assert pdc.ST_SIZE_JITTER in parts(row["status"])
    assert row["verdict_log"] == V_EXCLUDED
    assert row["log_reason"] == "부호 섞임"
    assert_log_nan(row)


def test_t4b_zero_and_mixed_sign():
    Y, z = size_jitter_data()
    Y[5], z[5] = -Y[5], -z[5]
    z[0] = 0.0
    row = run_item(Y, z)
    assert row["verdict_log"] == V_EXCLUDED
    assert row["log_reason"] == "0값 있음; 부호 섞임"


# 수정 전 judge_item 이 모든 zone 경로에서 내던 열 (blank·level 없음, POR 3회). 이 순서로 들어 있어야 한다.
# zone 경로별 열(doe_center, range_doe, delta_source, verdict_with_accuracy)은 zone 과 verdict 사이에 낀다.
OLD_COLS = [
    "ITEM", "UNIT", "n_die", "por_median", "POR1_mean", "POR2_mean", "POR3_mean", "DOE_mean",
    "center", "ci_low", "ci_high", "delta", "policy_margin", "run_margin", "sigma_die", "sigma_run",
    "LoQ", "LoD", "limit_source", "n_outlier_die", "ttest", "ttest_p", "por_ttest_sig",
    "zone", "verdict", "reason",
    *pdc.STATUS_COLS, *pdc.PRECISION_COLS,
]


def is_subsequence(sub: list, seq: list) -> bool:
    it = iter(seq)
    return all(c in it for c in sub)


@pytest.mark.parametrize("data", [size_jitter_data, larger_jitter_data, log_normal_data])
def test_t5_old_columns_unchanged(monkeypatch, data):
    Y, z = data()
    row = run_item(Y, z)
    monkeypatch.setattr(pdc, "OPTIONS", ())      # 옵션 열을 안 붙이던 수정 전 경로
    old = run_item(Y, z)
    assert is_subsequence(OLD_COLS, list(old))
    assert list(old)[-len(OLD_COLS[-11:]):] == OLD_COLS[-11:]
    assert list(row) == list(old) + LOG_COLS
    for c in old:
        a, b = row[c], old[c]
        assert (a == b) or (isinstance(a, float) and math.isnan(a) and math.isnan(b)), c


def test_u5_larger_jitter_is_target():
    Y, z = larger_jitter_data()
    row = run_item(Y, z)
    assert pdc.ST_SIZE_JITTER_POS in parts(row["status"])
    assert row["verdict_log"] in {"동등", "차이", "미결"}
    assert all(np.isfinite(row[c]) for c in LOG_NUM)
    assert row["spearman_size_jitter"] == pytest.approx(0.6256, abs=1e-4)
