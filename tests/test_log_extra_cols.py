"""WO-U U-A 추가: log 분석용 열 (sigma_die_log, sigma_run_log). 판정 불변.
below_linear_loq·policy_margin_log 는 남은 열에서 바로 나와 items.csv 에서 뺐다."""
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
EXTRA = ["sigma_die_log", "sigma_run_log"]


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
    assert LOG_COLS[-3:] == EXTRA + ["sigma_rep_log"]
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


def test_w3_removed_columns_absent_and_derivable():
    for data in (size_jitter_data, larger_jitter_data, far_data, near_zero_data, zero_value_data):
        row = run_item(pdc, *data())
        assert {"below_linear_loq", "policy_margin_log", "spearman_size_jitter_log", "rel_shift"}.isdisjoint(row)
        if row["verdict_log"] != V_EXCLUDED:
            assert row["delta_log"] - row["sigma_rep_log"] == pytest.approx(math.log10(1 + R), rel=1e-12)


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
    # WO-W: verdict_log 은 Δ_log 의 회차 항이 sigma_rep_log 로 바뀌어 HEAD 와 같을 필요가 없다.
    # 판정 제외 (0값·부호 섞임) 는 그대로.
    if b["verdict_log"] == V_EXCLUDED and b["log_reason"] in ("0값 있음", "부호 섞임", "0값 있음; 부호 섞임"):
        assert a["verdict_log"] == V_EXCLUDED and a["log_reason"] == b["log_reason"]
