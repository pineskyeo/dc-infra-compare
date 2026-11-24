"""최종 판정 (1·2단계 → 판정 길 3단계), LoQ 판정 (DOE 구간), 소비처(summarize·fail_evidence·plot_verdicts) 선택.
합성 데이터만."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fail_evidence as fe  # noqa: E402
import plot_verdicts as pv  # noqa: E402
import summarize  # noqa: E402
from por_doe_compare import (  # noqa: E402
    R_ABS, R_EXCLUDED, R_LIMIT, R_LINEAR, R_LOG, R_LOQ, V_EXCLUDED, add_final_verdict, final_verdict, loq_verdict,
)

METHODS = {"verdict_log": "동등", "verdict_log_run": "미결", "verdict_abs": "차이", "verdict_limit": "동등",
           "verdict_with_accuracy": "동등"}


@pytest.mark.parametrize("route, level, want", [
    (R_LIMIT, "정량", ("동등", "limit")),
    (R_ABS, "0 중심", ("차이", "abs")),
    (R_LOG, "정량", ("동등", "log")),
    (R_LINEAR, "바닥 근처", ("동등", "accuracy")),
    (R_LINEAR, "정량", ("미결", "linear")),        # 선형 TOST 길은 1단계 판정 그대로
    (R_LOQ, "바닥 아래", ("미결", "linear")),       # LoQ 판정 길은 2단계 판정 그대로
    (R_EXCLUDED, "정량", ("미결", "linear")),
])
def test_route_decides_stage_three(route, level, want):
    row = {"verdict": "미결", "zone": "정량", "route": route, "cls_level": level, **METHODS}
    assert final_verdict(row) == want


def test_stage_one_equal_is_final_whatever_the_route_says():
    row = {"verdict": "동등", "zone": "정량", "route": R_ABS, "cls_level": "0 중심", **METHODS}
    assert final_verdict(row) == ("동등", "linear")
    assert final_verdict({**row, "zone": "검출~정량"}) == ("동등", "loq")


@pytest.mark.parametrize("missing", [np.nan, "", V_EXCLUDED])
def test_route_that_cannot_judge_keeps_stage_one_two(missing):
    row = {"verdict": "차이", "zone": "검출한계 이하", "route": R_ABS, "cls_level": "0 중심", "verdict_abs": missing}
    assert final_verdict(row) == ("차이", "loq")


def test_excluded_base_can_be_judged_by_its_route():
    row = {"verdict": V_EXCLUDED, "zone": V_EXCLUDED, "route": R_ABS, "cls_level": "0 중심", "verdict_abs": "동등"}
    assert final_verdict(row) == ("동등", "abs")


def test_log_run_reference_swaps_only_the_log_route():
    log_row = {"verdict": "미결", "zone": "정량", "route": R_LOG, "cls_level": "정량", **METHODS}
    abs_row = {**log_row, "route": R_ABS}
    assert final_verdict(log_row, "verdict_log_run") == ("미결", "log")
    assert final_verdict(abs_row, "verdict_log_run") == final_verdict(abs_row)


def test_add_final_verdict_columns_and_old_csv_without_route():
    d = add_final_verdict(pd.DataFrame({"ITEM": ["A", "B"], "verdict": ["미결", "미결"], "zone": ["정량"] * 2,
                                        "reason": ["r"] * 2, "route": [R_LOG, ""], "cls_level": ["정량"] * 2,
                                        "verdict_log": ["동등"] * 2, "verdict_log_run": ["차이"] * 2}))
    cols = list(d.columns)
    i = cols.index("verdict")
    assert cols[i:i + 4] == ["verdict", "verdict_final", "verdict_basis", "verdict_final_log_run"]
    assert list(d["verdict_final"]) == ["동등", "미결"]
    assert list(d["verdict_final_log_run"]) == ["차이", "미결"]
    assert "verdict_final_log_run" not in add_final_verdict(d.drop(columns=["verdict_log_run", "verdict_final_log_run"]))


@pytest.mark.parametrize("lo, hi, delta, want", [
    (2.000000000000001e-06, 3.999999999999999e-06, 1.9999999999999944e-06, "미결"),   # 끝이 값 간격과 같음: 경계
    (-2.0000000000000004e-06, 2.0000000000000004e-06, 1.9999999999999998e-06, "동등"),  # 끝이 ±값 간격: 안으로 본다
    (2.1e-06, 4e-06, 2e-06, "차이"),
])
def test_tost_compares_grid_values_not_float_noise(lo, hi, delta, want):
    from por_doe_compare import tost
    assert tost((lo + hi) / 2, lo, hi, delta)[0] == want


LOQ = 10.0


@pytest.mark.parametrize("base, lo, hi, delta, want, why", [
    (2.0, -0.5, 0.5, 1.0, "동등", "이동이 ±Δ 안"),             # 이동이 허용폭 안
    (2.0, 2.0, 5.0, 1.0, "동등", "DOE 구간도 LoQ 미만"),        # DOE 4~7 < LoQ
    (2.0, 9.0, 12.0, 1.0, "차이", "이상이고"),                  # DOE 11~14 ≥ LoQ, 이동 밖
    (2.0, 5.0, 12.0, 1.0, "동등", "DOE 구간이 LoQ에 걸침"),     # DOE 7~14 가 LoQ 에 걸침
    (2.0, 0.5, 12.0, 1.0, "동등", "DOE 구간이 LoQ에 걸침"),
    (9.5, 0.8, 3.0, 1.0, "미결", "±Δ(1)에 걸침"),              # DOE 10.3~12.5 ≥ LoQ, 이동이 Δ 에 걸침
    (-2.0, -12.0, -9.0, 1.0, "차이", "이상이고"),               # 음수 쪽으로 LoQ 넘음
])
def test_loq_verdict_uses_the_doe_interval(base, lo, hi, delta, want, why):
    verdict, reason = loq_verdict((lo + hi) / 2, lo, hi, delta, base, LOQ)
    assert verdict == want and why in reason


def items_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "ITEM": ["A", "B", "C", "D"],
        "UNIT": ["V"] * 4,
        "zone": ["정량"] * 4,
        "verdict": ["차이", "동등", "미결", "동등"],
        "reason": ["r"] * 4,
        "route": [R_LOG, R_LOG, R_LOG, R_LINEAR],
        "cls_level": ["정량"] * 4,
        "verdict_log": ["동등", "차이", V_EXCLUDED, "차이"],
    })


def test_summarize_not_equivalent_follows_verdict_final():
    d = add_final_verdict(items_frame())
    assert list(d["verdict_final"]) == ["동등", "동등", "미결", "동등"]
    assert list(summarize.not_equivalent(d)["ITEM"]) == ["C"]
    old = items_frame().drop(columns=["route"])                           # 옛 CSV: verdict 로 대체
    assert list(summarize.not_equivalent(old)["ITEM"]) == ["A", "C"]


def test_fail_evidence_select_follows_verdict_final():
    d = add_final_verdict(items_frame())
    assert fe.select_items(d, []) == (["C"], [])
    assert fe.select_items(items_frame(), []) == (["A", "C"], [])


def test_plot_verdicts_detail_selection_follows_verdict_final():
    d = add_final_verdict(items_frame())
    assert pv.select_detail_items(d) == ["C"]
    assert pv.select_detail_items(items_frame()) == ["A", "C"]
