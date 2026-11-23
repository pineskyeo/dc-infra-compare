"""WO-W: judge_log 의 회차 항을 die별 log 회차 흔들림 sigma_rep_log 으로. 합성 데이터만, seed 고정."""
import importlib.util
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import por_doe_compare as pdc
from por_doe_compare import LOG_COLS, V_EXCLUDED

R = 0.05
POR = ["POR1", "POR2", "POR3"]
REPO = Path(__file__).resolve().parents[1]


def multiplicative_data(seed: int = 21) -> tuple[np.ndarray, np.ndarray]:
    """die 60개, 크기 1e-12~1e-6, die마다 독립인 곱셈 회차 흔들림 (웨이퍼 공통 이동 없음)."""
    rng = np.random.default_rng(seed)
    size = 10 ** rng.uniform(-12, -6, 60)
    return size[:, None] * 10 ** rng.normal(0, 0.03, (60, 3)), size * 10 ** rng.normal(0, 0.03, 60)


def size_jitter_data(seed: int = 22) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    size = 10 ** np.linspace(-12, -6, 40)
    half = np.linspace(0.4, 0.02, 40) * (1 + 0.1 * rng.random(40))
    return size[:, None] * 10 ** (half[:, None] * np.array([1.0, 0.0, -1.0])), size.copy()


def far_data(seed: int = 23) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return 100 + rng.normal(0, 1, (30, 3)), 101 + rng.normal(0, 1, 30)


def run_shift_data(seed: int = 24) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    base = 50 + rng.normal(0, 3, 40)
    Y = base[:, None] + np.array([-5.0, 0.0, 5.0]) + rng.normal(0, 0.1, (40, 3))
    return Y, base + rng.normal(0, 0.1, 40)


def mixed_sign_data(seed: int = 25) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1, (30, 3)), rng.normal(0, 1, 30)


def zero_value_data() -> tuple[np.ndarray, np.ndarray]:
    Y, z = multiplicative_data()
    Y[4, 2] = 0.0
    return Y, z


def run_item(mod, Y: np.ndarray, z: np.ndarray) -> dict:
    g = pd.DataFrame(Y, columns=POR).assign(DOE=z)
    blank = pd.DataFrame(columns=["BLANK_ITEM"]).set_index("BLANK_ITEM")
    return mod.judge_item("IT", g, POR, {"IT": "A"}, R, {}, blank, {})[0]


def load_head_module():
    src = subprocess.run(["git", "show", "HEAD:por_doe_compare.py"], cwd=REPO, check=True,
                         capture_output=True, text=True).stdout
    name = "por_doe_compare_head_wow"
    spec = importlib.util.spec_from_loader(name, loader=None, origin=str(REPO / "por_doe_compare.py"))
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(REPO / "por_doe_compare.py")
    sys.modules[name] = mod                         # dataclass 등이 모듈을 찾으므로 exec 전에 등록
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


def same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return bool(a == b)


def test_r1_multiplicative_delta_log_uses_sigma_rep_log():
    Y, z = multiplicative_data()
    row = run_item(pdc, Y, z)
    assert row["verdict_log"] != V_EXCLUDED
    L = np.log10(np.abs(Y))
    want = float(np.median(np.std(L, axis=1, ddof=1)))
    assert bool(row["sigma_rep_log"] > 0)
    assert bool(np.isclose(row["sigma_rep_log"], want, rtol=1e-12, atol=0))
    assert bool(np.isclose(row["delta_log"], math.log10(1 + R) + row["sigma_rep_log"], rtol=1e-12, atol=0))
    # 회차 독립 흔들림 σ = 0.03 dex 근처
    assert bool(0.015 < row["sigma_rep_log"] < 0.05)


def test_r1b_sigma_rep_log_skips_short_die():
    L = np.array([[1.0, 1.2, 1.4], [2.0, np.nan, np.nan], [3.0, 3.1, np.nan], [np.nan] * 3])
    assert bool(np.isclose(pdc.sigma_rep_log(L), np.median([0.2, np.std([3.0, 3.1], ddof=1)])))
    assert math.isnan(pdc.sigma_rep_log(np.full((4, 3), np.nan)))
    assert math.isnan(pdc.sigma_rep_log(np.ones((5, 1))))


def test_r2_linear_unchanged_from_head():
    old = load_head_module()
    for data in (multiplicative_data, size_jitter_data, far_data, run_shift_data, mixed_sign_data, zero_value_data):
        Y, z = data()
        a, b = run_item(pdc, Y, z), run_item(old, Y, z)
        for c in ("verdict", "delta", "sigma_run", "status", "zone", "reason", "run_margin"):
            assert same(a[c], b[c]), (data.__name__, c, a[c], b[c])


def test_r2b_judge_default_path_bitwise():
    old = load_head_module()
    for data in (multiplicative_data, far_data, run_shift_data):
        Y, z = data()
        a, b = pdc.judge(Y, z, R)[0], old.judge(Y, z, R)[0]
        assert list(a) == list(b)
        assert all(same(a[k], b[k]) for k in a), data.__name__


def test_r3_zero_or_mixed_sign_blank():
    for data in (zero_value_data, mixed_sign_data):
        row = run_item(pdc, *data())
        assert row["verdict_log"] == V_EXCLUDED
        assert math.isnan(row["sigma_rep_log"])


def test_r4_sigma_rep_log_is_last_log_column():
    assert LOG_COLS[-1] == "sigma_rep_log"
    assert list(run_item(pdc, *multiplicative_data()))[-1] == "sigma_rep_log"
