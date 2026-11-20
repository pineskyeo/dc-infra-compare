"""WO-U U-A 추가: log 분석용 열 4개 (sigma_die_log, sigma_run_log, below_linear_loq, policy_margin_log). 판정 불변."""
import math
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import por_doe_compare as pdc
from por_doe_compare import LOG_COLS, V_EXCLUDED

R = 0.05
REPO = Path(__file__).resolve().parents[1]
EXTRA = ["sigma_die_log", "sigma_run_log", "below_linear_loq", "policy_margin_log"]


def size_jitter_data(seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """die 40개, 크기 1e-12~1e-6, 작은 die일수록 log 범위가 큼 → 작을수록 흔들림."""
    rng = np.random.default_rng(seed)
    size = 10 ** np.linspace(-12, -6, 40)
    half = np.linspace(0.4, 0.02, 40) * (1 + 0.1 * rng.random(40))
    return size[:, None] * 10 ** (half[:, None] * np.array([1.0, 0.0, -1.0])), size.copy()


def larger_jitter_data() -> tuple[np.ndarray, np.ndarray]:
    """die 20개, log 범위 순위를 구간별로 뒤집어 클수록 흔들림."""
    rank, start = [], 0
    for k in (10, 8, 1, 1):
        rank.extend(range(start + k - 1, start - 1, -1))
        start += k
    size = 10 ** np.linspace(-12, -6, 20)
    half = 0.02 + 0.01 * np.asarray(rank, float)
    return size[:, None] * 10 ** (half[:, None] * np.array([1.0, 0.0, -1.0])), size.copy()


def near_zero_data(seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """중심 0 근처, 잡음 1 → 선형 LoQ(≈10σ) 아래."""
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1, (30, 3)), rng.normal(0, 1, 30)


def far_data(seed: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """중심 100, 잡음 1 → 선형 LoQ 위."""
    rng = np.random.default_rng(seed)
    return 100 + rng.normal(0, 1, (30, 3)), 100 + rng.normal(0, 1, 30)


def above_loq_data(seed: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """die 30개·회차 3, POR·DOE 중심 1000, 잡음 σ=1 → 중심이 선형 LoQ(≈10σ)보다 훨씬 큼."""
    rng = np.random.default_rng(seed)
    return 1000 + rng.normal(0, 1, (30, 3)), 1000 + rng.normal(0, 1, 30)


def zero_value_data() -> tuple[np.ndarray, np.ndarray]:
    Y, z = size_jitter_data()
    Y[0, 0] = 0.0
    return Y, z


def run_item(mod, Y: np.ndarray, z: np.ndarray) -> dict:
    g = pd.DataFrame(Y, columns=["POR1", "POR2", "POR3"]).assign(DOE=z)
    blank = pd.DataFrame(columns=["BLANK_ITEM"]).set_index("BLANK_ITEM")
    return mod.judge_item("IT", g, ["POR1", "POR2", "POR3"], {"IT": "A"}, R, {}, blank, {})[0]


def is_target(row: dict) -> bool:
    return bool({pdc.ST_SIZE_JITTER, pdc.ST_SIZE_JITTER_POS} & set(row["status"].split(";")))


def test_w1_names_and_position():
    assert LOG_COLS[-4:] == EXTRA
    assert len(set(LOG_COLS)) == len(LOG_COLS)
    row = run_item(pdc, *size_jitter_data())
    assert list(row)[-len(LOG_COLS):] == LOG_COLS


@pytest.mark.parametrize("data", [size_jitter_data, larger_jitter_data])
def test_w2_sigma_log_equals_judge_internal(data):
    Y, z = data()
    row = run_item(pdc, Y, z)
    assert is_target(row) and row["verdict_log"] != V_EXCLUDED
    L, w = np.log10(np.abs(Y)), np.log10(np.abs(z))
    level = abs(float(np.median(L.mean(axis=1))))
    inner = pdc.judge(L, w, math.log10(1 + R) / level, None, None)[0]
    assert row["sigma_die_log"] == inner["sigma_die"]
    assert row["sigma_run_log"] == inner["sigma_run"]
    assert np.isfinite(row["sigma_die_log"]) and np.isfinite(row["sigma_run_log"])


def test_w2_sigma_log_blank_when_excluded():
    row = run_item(pdc, *far_data())          # 흔들림 status 아니어도 0 없고 부호 하나면 채움 (WO-U-A2)
    assert not is_target(row)
    assert np.isfinite(row["sigma_die_log"]) and np.isfinite(row["sigma_run_log"])
    for data in (zero_value_data, near_zero_data):
        row = run_item(pdc, *data())
        assert row["verdict_log"] == V_EXCLUDED
        assert math.isnan(row["sigma_die_log"]) and math.isnan(row["sigma_run_log"])


def test_w3_below_linear_loq_true_false_blank():
    for data, want in ((near_zero_data, True), (above_loq_data, False)):
        row = run_item(pdc, *data())
        doe_c = row["por_median"] + row["center"]
        if not want:
            assert abs(doe_c) >= 10 * row["LoQ"], (doe_c, row["LoQ"])
        assert bool(abs(doe_c) < row["LoQ"]) is want
        assert row["below_linear_loq"] is want
    # log 대상·판정 제외 ITEM 에도 채운다
    assert isinstance(run_item(pdc, *zero_value_data())["below_linear_loq"], bool)
    Y, z = far_data()
    for res in ({}, {"LoQ": np.nan, "por_median": 100.0, "center": 0.0}):
        assert math.isnan(pdc.log_columns(Y, z, R, res)["below_linear_loq"])


def test_w4_policy_margin_log():
    for data in (size_jitter_data, larger_jitter_data, far_data):
        row = run_item(pdc, *data())
        assert row["policy_margin_log"] == pytest.approx(math.log10(1 + R), rel=1e-12)
    assert math.isnan(run_item(pdc, *near_zero_data())["policy_margin_log"])     # 부호 섞임
    assert math.isnan(run_item(pdc, *zero_value_data())["policy_margin_log"])


def load_head_module() -> types.ModuleType:
    src = subprocess.run(["git", "show", "HEAD:por_doe_compare.py"], cwd=REPO, check=True,
                         capture_output=True, text=True).stdout
    name = "por_doe_compare_head"
    mod = types.ModuleType(name)
    mod.__file__ = str(REPO / "por_doe_compare.py")
    sys.modules[name] = mod
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


@pytest.mark.parametrize("data", [size_jitter_data, larger_jitter_data, near_zero_data, far_data, zero_value_data])
def test_w5_verdicts_same_as_head(data):
    old = load_head_module()
    Y, z = data()
    a, b = run_item(pdc, Y, z), run_item(old, Y, z)
    assert a["verdict"] == b["verdict"]
    va, vb = a["verdict_log"], b["verdict_log"]
    # HEAD 는 흔들림 status ITEM 만 채웠다 (WO-U-A2 에서 대상 확대). HEAD 가 채운 곳은 같아야 한다.
    assert va == vb or (isinstance(vb, float) and math.isnan(vb))
