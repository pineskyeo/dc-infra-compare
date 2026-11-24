"""허용폭을 s 배로 바꿨을 때의 최종 판정 (por_doe_compare.rescaled_verdicts). 합성 데이터만."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from por_doe_compare import R_ABS, R_LINEAR, R_LOG, R_LOQ, rescaled_verdicts  # noqa: E402

LINEAR = {"zone": "정량", "route": R_LINEAR, "cls_level": "정량"}


def rows(*rs: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rs))


def test_scale_one_keeps_every_verdict_and_scales_move_the_boundary():
    t = rows(
        # 구간 0.85~0.95, Δ 1 → 동등. Δ 0.8 이면 통째로 밖 → 차이
        {**LINEAR, "verdict": "동등", "center": 0.9, "ci_low": 0.85, "ci_high": 0.95, "delta": 1.0},
        # 구간 0.5~1.1 이 Δ 1 에 걸침 → 미결. Δ 1.2 면 안 → 동등
        {**LINEAR, "verdict": "미결", "center": 0.8, "ci_low": 0.5, "ci_high": 1.1, "delta": 1.0},
        # 절대 허용폭 길: 1단계 미결, verdict_abs 는 abs_delta 2 로 동등. abs_delta 1.6 이면 차이
        {**LINEAR, "route": R_ABS, "verdict": "미결", "center": 1.75, "ci_low": 1.7, "ci_high": 1.8, "delta": 1.75,
         "abs_delta": 2.0, "verdict_abs": "동등"},
        # log 길: log 구간 0.1~0.3, Δ_log 0.35 → 동등. 0.28 이면 걸침 → 미결
        {**LINEAR, "route": R_LOG, "verdict": "미결", "center": 1.0, "ci_low": 0.5, "ci_high": 1.5, "delta": 1.0,
         "center_log": 0.2, "ci_low_log": 0.1, "ci_high_log": 0.3, "delta_log": 0.35, "verdict_log": "동등"},
        # 바닥 근처 선형 TOST: 장비 정확도 폭 2 가 Δ 보다 커서 Δ' = 2 로 동등
        {**LINEAR, "cls_level": "바닥 근처", "verdict": "차이", "center": 1.5, "ci_low": 1.4, "ci_high": 1.6,
         "delta": 1.0, "accuracy_margin": 2.0, "verdict_with_accuracy": "동등"},
    )
    assert list(rescaled_verdicts(t, 1.0)) == ["동등", "미결", "동등", "동등", "동등"]
    assert list(rescaled_verdicts(t, 0.8)) == ["차이", "미결", "차이", "미결", "동등"]
    assert list(rescaled_verdicts(t, 1.2)) == ["동등", "동등", "동등", "동등", "동등"]
    assert list(rescaled_verdicts(t, 0.7)) == ["차이", "미결", "차이", "미결", "미결"]
    assert list(rescaled_verdicts(t, 0.8).index) == list(t.index)


def test_loq_zone_uses_loq_verdict_with_the_scaled_delta():
    loq = {"zone": "검출~정량", "route": R_LOQ, "cls_level": "바닥 아래", "por_median": 5.0, "LoQ": 10.0}
    t = rows(
        # DOE 구간 11~12 가 통째로 LoQ 위, 이동 구간 6~7 이 Δ 6.5 에 걸침 → 미결
        {**loq, "verdict": "미결", "center": 6.5, "ci_low": 6.0, "ci_high": 7.0, "delta": 6.5},
        # DOE 구간 9~11 이 LoQ 에 걸침 → Δ 와 무관하게 동등 (TOST 만 보면 Δ 3.6 에서 차이)
        {**loq, "verdict": "동등", "center": 5.0, "ci_low": 4.0, "ci_high": 6.0, "delta": 4.5},
    )
    assert list(rescaled_verdicts(t, 1.0)) == ["미결", "동등"]
    assert list(rescaled_verdicts(t, 0.8)) == ["차이", "동등"]
    assert list(rescaled_verdicts(t, 1.2)) == ["동등", "동등"]


def test_rows_that_cannot_be_rejudged_keep_their_verdict():
    t = rows(
        {**LINEAR, "verdict": "동등", "center": np.nan, "ci_low": 0.85, "ci_high": 0.95, "delta": 1.0},
        {**LINEAR, "verdict": "차이", "center": 0.9, "ci_low": 0.85, "ci_high": 0.95, "delta": 0.0},
        {**LINEAR, "zone": "die 부족", "verdict": "미결", "center": 0.0, "ci_low": -0.1, "ci_high": 0.1, "delta": 1.0},
        {**LINEAR, "route": R_LOG, "verdict": "미결", "center": 0.9, "ci_low": 0.5, "ci_high": 1.1, "delta": 1.0,
         "verdict_log": "동등"},
    )
    for s in (0.5, 0.8, 1.2, 2.0):
        assert list(rescaled_verdicts(t, s)) == ["동등", "차이", "미결", "동등"], s


def test_old_csv_without_route_or_numbers_keeps_stage_one_two():
    t = rows({"verdict": "미결", "zone": "정량"}, {"verdict": "판정 제외", "zone": "판정 제외"})
    assert list(rescaled_verdicts(t, 0.8)) == ["미결", "판정 제외"]
