"""판정 제외 순서 (WO-R): 중심·CI → die 산포 0 → 중앙값 0·σ_run 0 → zone 판정 (정량만 최종 Δ 검사). 합성 배열만."""
import numpy as np

from por_doe_compare import V_EXCLUDED, ItemInfo, item_status, judge, meas_precision

N = 200
LOQ_ZONES = ("검출한계 이하", "검출~정량")


def make(base: np.ndarray, run_shift: float = 0.0, scale: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """POR 2회 + DOE. 회차값 = base ∓ h (∓ run_shift/2), h = (c, −c) 라 die 평균 R = base, 회차별 중앙값 차는
    run_shift 뿐 (run_shift = 0 이면 σ_run = 0), σ_die > 0. 정수·0.5 배수라 평균이 정확히 base."""
    rng = np.random.default_rng(1)
    c = rng.integers(1, 6, N // 2).astype(float)
    h = np.concatenate([c, -c]) * scale
    Y = np.column_stack([base - h - run_shift / 2, base + h + run_shift / 2])
    z = base + 0.25 * scale
    return Y, z


def sym_base() -> np.ndarray:
    """중앙값 0, 값이 모두 다름."""
    a = np.arange(1, N // 2 + 1, dtype=float)
    return np.concatenate([a, -a])


def test_s1_sigma_die_zero():
    base = sym_base() + 1000
    Y, z = np.column_stack([base, base]), base + 0.25
    res, _ = judge(Y, z, 0.05)
    assert res["sigma_die"] == 0
    assert res["verdict"] == V_EXCLUDED and res["zone"] == V_EXCLUDED
    assert res["reason"].startswith(f"{V_EXCLUDED}: ") and "die 산포 0 (σ_die=0)" in res["reason"]


def test_s2_majority_flat():
    base = sym_base() + 1000
    base[:120] = 1000.0                 # R 의 60%가 같은 값
    Y, z = make(base)
    res, _ = judge(Y, z, 0.05)
    assert res["sigma_die"] > 0
    assert res["verdict"] == V_EXCLUDED
    assert "die 산포 0 (고정값 60%)" in res["reason"]
    assert "산포 0" in item_status(Y, z, res["delta"])["status"].split(";")


def test_s3_minority_flat_is_judged():
    base = sym_base() + 1000
    base[:80] = 1000.0                  # 40%
    Y, z = make(base)
    res, _ = judge(Y, z, 0.05)
    assert res["sigma_die"] > 0
    assert res["verdict"] != V_EXCLUDED and res["zone"] == "정량"


def test_r1_median_zero_and_no_run_shift():
    Y, z = make(sym_base())
    res, _ = judge(Y, z, 0.05)
    assert res["por_median"] == 0 and res["sigma_run"] == 0 and res["sigma_die"] > 0
    assert res["verdict"] == V_EXCLUDED
    assert "고정값 (중앙값 0·σ_run 0)" in res["reason"]


def test_r2_median_zero_with_run_shift_goes_to_loq_zone():
    Y, z = make(sym_base(), run_shift=3.0)
    res, _ = judge(Y, z, 0.05)
    assert res["por_median"] == 0 and res["sigma_run"] > 0 and res["sigma_die"] > 0
    assert res["verdict"] != V_EXCLUDED
    assert res["zone"] in LOQ_ZONES


def test_r3_nonzero_median_without_run_shift_is_judged():
    Y, z = make(sym_base() + 1000)
    res, _ = judge(Y, z, 0.05)
    assert res["por_median"] == 1000 and res["sigma_run"] == 0 and res["sigma_die"] > 0
    assert res["verdict"] != V_EXCLUDED and res["zone"] == "정량"
    assert res["delta"] == 50.0


def test_c_nan_center():
    Y, z = make(sym_base() + 1000)
    z[0] = np.nan
    res, _ = judge(Y, z, 0.05)
    assert np.isnan(res["center"])
    assert res["verdict"] == V_EXCLUDED
    assert "중심·신뢰구간 계산 불가 (center)" in res["reason"]


def test_d_accuracy_margin_does_not_replace_zero_policy_delta():
    # 1.0~1.2 V, r = 0, σ_run = 0 → Δ = 0. 장비 정확도 폭은 판정에 안 쓰여 판정 제외, 참고 판정만 남는다
    Y, z = make(1.0 + np.arange(N) * 1e-3, scale=1e-4)
    info = ItemInfo(1.0, "V", 1.0, False)
    res, _ = judge(Y, z, 0.0, info=info)
    assert res["policy_margin"] == 0 and res["sigma_run"] == 0 and res["accuracy_margin"] > 0
    assert res["verdict"] == V_EXCLUDED
    assert res["delta_source"] == "정책 + 회차" and res["delta"] == 0
    assert res["verdict_with_accuracy"] == "동등"


def test_accuracy_margin_larger_keeps_policy_run_delta():
    # Δ = 1e-5 × 1.1 V 정도, shift 2.5e-5 → 차이. 장비 정확도 폭(≈1.7e-3)을 썼다면 동등
    Y, z = make(1.0 + np.arange(N) * 1e-3, scale=1e-4)
    info = ItemInfo(1.0, "V", 1.0, False)
    res, _ = judge(Y, z, 1e-5, info=info)
    assert res["accuracy_margin"] > res["delta"]
    assert res["delta"] == res["policy_margin"] + res["run_margin"]
    assert res["delta_source"] == "정책 + 회차"
    assert res["verdict"] == "차이"
    assert res["verdict_with_accuracy"] == "동등"


def test_no_accuracy_margin_leaves_verdict_with_accuracy_empty():
    Y, z = make(1.0 + np.arange(N) * 1e-3, scale=1e-4)
    res, _ = judge(Y, z, 1e-5)
    assert "accuracy_margin" not in res and np.isnan(res["verdict_with_accuracy"])


def test_quant_zone_final_delta_zero_is_excluded():
    Y, z = make(1.0 + np.arange(N) * 1e-3, scale=1e-4)
    res, _ = judge(Y, z, 0.0)
    assert res["verdict"] == V_EXCLUDED and res["zone"] == V_EXCLUDED
    assert "최종 Δ가 0 이하이거나 유효하지 않음 (Δ=0, 출처 정책 + 회차)" in res["reason"]


def test_all_causes_joined_in_order():
    # center NaN (1) + 중앙값 0·σ_run 0 (3) 이 둘 다 맞음. 첫 원인만 접두사, '; ' 로 순서대로
    Y, z = make(sym_base())
    z[0] = np.nan
    res, _ = judge(Y, z, 0.05)
    assert res["verdict"] == V_EXCLUDED
    assert res["reason"] == (f"{V_EXCLUDED}: 중심·신뢰구간 계산 불가 (center); 고정값 (중앙값 0·σ_run 0)")


def test_loq_zone_zero_delta_status_has_no_inf():
    # 중앙값 0.5 (< LoQ), r = 0, σ_run = 0 → Δ = 0 이어도 LoQ zone 판정, status 의 /Δ 열은 NaN
    Y, z = make(sym_base() + 0.5)
    res, _ = judge(Y, z, 0.0)
    assert res["delta"] == 0 and res["zone"] in LOQ_ZONES and res["verdict"] != V_EXCLUDED
    st = item_status(Y, z, res["delta"])
    for k in ("run_jitter_over_delta", "por_gap_over_delta"):
        assert np.isnan(st[k])
    assert not any(s in st["status"] for s in ("조건 불안정", "회차 흔들림", "분해능 부족"))
    prec = meas_precision(res["sigma_die"], res["sigma_run"], res["por_median"], res["delta"])
    assert np.isnan(prec["sigma_meas_over_delta"])
