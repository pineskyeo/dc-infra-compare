"""판정 제외 원인 표 (EXCLUSION_CAUSES): 판정할 것이 없을 때만 판정 제외. 합성 데이터만, seed 고정."""
import numpy as np

from por_doe_compare import V_EXCLUDED, item_status, judge

N = 200
LOQ_ZONES = ("검출한계 이하", "검출~정량")
STEP = 2e-6


def quantized(seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """0.575 V 근처, 2e-6 V 단위로 양자화, die 60%가 가운데 값 (fixed_share > 0.5)."""
    rng = np.random.default_rng(seed)
    k = rng.choice([-1, 0, 1], p=[0.2, 0.6, 0.2], size=(N, 4))
    return 0.575 + STEP * k[:, :3], 0.575 + STEP * k[:, 3]


def normal_data(seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return 100 + rng.normal(0, 1, (N, 3)), 100 + rng.normal(0, 1, N)


def test_quantized_near_constant_is_judged():
    Y, z = quantized()
    res, _ = judge(Y, z, 0.05)
    st = item_status(Y, z, res["delta"])
    assert st["fixed_share"] > 0.5 and "산포 0" in st["status"].split(";")
    assert st["resolution_over_delta"] < 1e-3
    assert res["zone"] == "정량" and res["verdict"] == "동등", res["reason"]


def test_quantized_with_zero_sigma_die_is_judged():
    rng = np.random.default_rng(4)
    base = 0.575 + STEP * rng.choice([-1, 0, 1], p=[0.2, 0.6, 0.2], size=N)
    Y = np.column_stack([base] * 3)
    z = base + STEP * (rng.random(N) < 0.1)
    res, _ = judge(Y, z, 0.05)
    assert res["sigma_die"] == 0
    assert res["zone"] == "정량" and res["verdict"] == "동등", res["reason"]


def test_one_por_run_of_zeros_is_excluded():
    Y, z = normal_data()
    Y[:, 1] = 0.0
    res, _ = judge(Y, z, 0.05)
    assert res["verdict"] == V_EXCLUDED and res["zone"] == V_EXCLUDED
    assert res["reason"].startswith(f"{V_EXCLUDED}: ") and "회차 0값 (POR2)" in res["reason"]


def test_doe_mostly_zero_is_excluded():
    Y, z = normal_data()
    z[:150] = 0.0
    res, _ = judge(Y, z, 0.05)
    assert res["verdict"] == V_EXCLUDED
    assert "회차 0값 (DOE)" in res["reason"]
    Y[:, 1] = 0.0
    res, _ = judge(Y, z, 0.05)
    assert "회차 0값 (POR2, DOE)" in res["reason"]


def test_constant_everywhere_is_excluded():
    Y, z = np.full((N, 3), 400.0), np.full(N, 400.0)
    res, _ = judge(Y, z, 0.05)
    assert res["verdict"] == V_EXCLUDED
    assert res["reason"] == f"{V_EXCLUDED}: 모든 값 같음; die 산포 0 (σ_die=0)"


def test_centred_on_zero_with_spread_goes_to_loq_judgment():
    rng = np.random.default_rng(5)
    half = rng.normal(0, 1, (N // 2, 3))
    Y = np.vstack([half, -half])                 # die 평균이 ±쌍이라 POR 중앙값이 정확히 0
    z = np.concatenate([half[:, 0], -half[:, 0]]) + 0.01
    res, _ = judge(Y, z, 0.05)
    assert res["por_median"] == 0 and res["sigma_die"] > 0 and res["LoQ"] > 0
    assert res["zone"] in LOQ_ZONES and res["verdict"] == "동등", res["reason"]


def test_coarse_flat_data_above_loq_is_excluded():
    rng = np.random.default_rng(6)
    k = rng.choice([-1, 0, 1], p=[0.15, 0.7, 0.15], size=(N, 4))
    Y, z = 1000 + 20.0 * k[:, :3], 1000 + 20.0 * k[:, 3]
    res, _ = judge(Y, z, 0.05)
    st = item_status(Y, z, res["delta"])
    assert st["resolution_over_delta"] >= 0.1 and st["fixed_share"] > 0.5
    assert abs(res["por_median"]) >= res["LoQ"]
    assert res["verdict"] == V_EXCLUDED and "die 산포 0" in res["reason"]
