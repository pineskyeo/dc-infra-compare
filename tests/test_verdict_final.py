"""WO-Z 3단계: verdict_final / verdict_basis 규칙과 소비처(summarize·fail_evidence·plot_verdicts) 선택. 합성 데이터만."""
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
    ST_LOG_CANDIDATE, ST_OK, ST_SIZE_JITTER, V_EXCLUDED, add_final_verdict, final_verdict,
)

CAND = f"{ST_SIZE_JITTER};{ST_LOG_CANDIDATE}"


@pytest.mark.parametrize("status, verdict, verdict_log, want", [
    (CAND, "차이", "동등", ("동등", "log")),                    # 비동등 + log 후보 + 값
    (CAND, "미결", "차이", ("차이", "log")),                    # 미결 + log 후보 + 값
    (CAND, "차이", np.nan, ("차이", "linear")),                 # log 후보 + NaN
    (CAND, "차이", "", ("차이", "linear")),                     # log 후보 + 빈칸
    (CAND, "미결", V_EXCLUDED, ("미결", "linear")),             # log 후보 + 판정 제외
    (CAND, "동등", "차이", ("동등", "linear")),                 # 선형 동등이면 log 후보여도 linear
    (ST_SIZE_JITTER, "차이", "동등", ("차이", "linear")),       # 비후보
    (ST_OK, "동등", "차이", ("동등", "linear")),                # 비후보
])
def test_final_verdict_rules(status, verdict, verdict_log, want):
    assert final_verdict(status, verdict, verdict_log) == want


@pytest.mark.parametrize("verdict, status, verdict_log, want", [
    ("동등", CAND, "미결", ("동등", "linear")),         # 선형 동등 × log 후보 O (verdict_log 미결이어도 동등)
    ("동등", ST_SIZE_JITTER, "미결", ("동등", "linear")),  # 선형 동등 × log 후보 X
    ("차이", CAND, "미결", ("미결", "log")),            # 선형 비동등 × log 후보 O → log 재판정
    ("차이", ST_SIZE_JITTER, "동등", ("차이", "linear")),  # 선형 비동등 × log 후보 X
])
def test_z3_linear_first_then_log_for_non_equiv_candidates(verdict, status, verdict_log, want):
    """선형 먼저, 동등이 아닌 log 후보만 log 로 재판정."""
    assert final_verdict(status, verdict, verdict_log) == want


def items_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "ITEM": ["A", "B", "C", "D"],
        "UNIT": ["V"] * 4,
        "zone": ["정량"] * 4,
        "verdict": ["차이", "동등", "미결", "동등"],
        "reason": ["r"] * 4,
        "status": [CAND, CAND, CAND, ST_OK],
        "verdict_log": ["동등", "차이", V_EXCLUDED, "차이"],
    })


def test_items_column_order_and_values():
    res = add_final_verdict(items_frame())
    cols = list(res.columns)
    i = cols.index("verdict")
    assert cols[i:i + 4] == ["verdict", "verdict_final", "verdict_basis", "reason"]
    assert list(res["verdict_final"]) == ["동등", "동등", "미결", "동등"]          # B: 선형 동등이면 log 후보여도 동등
    assert list(res["verdict_basis"]) == ["log", "linear", "linear", "linear"]
    assert list(res["verdict"]) == ["차이", "동등", "미결", "동등"]          # verdict·verdict_log 유지
    assert list(res["verdict_log"]) == ["동등", "차이", V_EXCLUDED, "차이"]


def test_summarize_not_equivalent_follows_verdict_final():
    d = add_final_verdict(items_frame())
    assert list(summarize.not_equivalent(d)["ITEM"]) == ["C"]
    old = items_frame().drop(columns=["verdict_log"])                     # 옛 CSV: verdict 로 대체
    assert list(summarize.not_equivalent(old)["ITEM"]) == ["A", "C"]


def test_fail_evidence_select_follows_verdict_final():
    d = add_final_verdict(items_frame())
    assert fe.select_items(d, []) == (["C"], [])
    old = items_frame()
    assert fe.select_items(old, []) == (["A", "C"], [])


def test_plot_verdicts_detail_selection_follows_verdict_final():
    d = add_final_verdict(items_frame())
    assert pv.select_detail_items(d) == ["C"]
    assert pv.select_detail_items(items_frame()) == ["A", "C"]
