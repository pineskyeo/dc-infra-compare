"""기본 판정 뒤 +@ 옵션 재판정 (log 옵션, OPTIONS 레지스트리). 합성 데이터만, seed 고정."""
import numpy as np
import pandas as pd
import pytest

import por_doe_compare as pdc
from por_doe_compare import ST_LOG_CANDIDATE, ST_OK, V_EXCLUDED, Option, add_final_verdict, final_verdict

R = 0.05
POR = ["POR1", "POR2", "POR3"]
SCALES = (1e-3, 1.0, 1e3)


def near_one_data(doe_factor: float, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """die 61개, 중앙값 0.9853, 0.1~10배로 퍼진 log형 (log 후보), 곱셈 회차 흔들림 0.008 dex."""
    rng = np.random.default_rng(seed)
    size = 0.9853 * 10 ** np.linspace(-1, 1, 61)
    Y = size[:, None] * 10 ** rng.normal(0, 0.008, (61, 3))
    z = doe_factor * size * 10 ** rng.normal(0, 0.008, 61)
    return Y, z


def wide_data(doe_factor: float, seed: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """die 80개, 1e-12~1e-6 에 log 균등, 회차 흔들림 0.03 dex."""
    rng = np.random.default_rng(seed)
    size = 10 ** rng.uniform(-12, -6, 80)
    Y = size[:, None] * 10 ** rng.normal(0, 0.03, (80, 3))
    z = doe_factor * size * 10 ** rng.normal(0, 0.03, 80)
    return Y, z


def run_item(Y: np.ndarray, z: np.ndarray, r: float = R) -> dict:
    g = pd.DataFrame(Y, columns=POR).assign(DOE=z)
    blank = pd.DataFrame(columns=["BLANK_ITEM"]).set_index("BLANK_ITEM")
    return pdc.judge_item("IT", g, POR, {}, r, {}, blank, {})[0]


def final(row: dict) -> tuple[str, str]:
    d = add_final_verdict(pd.DataFrame([row]))
    return d.loc[0, "verdict_final"], d.loc[0, "verdict_basis"]


CASES = [(near_one_data, 1.15), (near_one_data, 1.0), (wide_data, 1.15), (wide_data, 1.01)]


@pytest.mark.parametrize("data, factor", CASES)
def test_log_verdict_does_not_depend_on_unit(data, factor):
    Y, z = data(factor)
    rows = [run_item(Y * s, z * s) for s in SCALES]
    assert all(ST_LOG_CANDIDATE in row["status"].split(";") for row in rows)
    assert len({row["verdict_log"] for row in rows}) == 1, [row["verdict_log"] for row in rows]
    assert len({final(row) for row in rows}) == 1, [final(row) for row in rows]


def test_near_one_times_1_15_is_difference_in_every_unit():
    # 0.9853 kΩ, 985.3 Ω, 0.0009853 MΩ: DOE 가 15% 크면 log10(1.15) = 0.061 > Δ_log 라 어느 단위에서도 차이
    Y, z = near_one_data(1.15)
    for s in SCALES:
        row = run_item(Y * s, z * s)
        assert row["verdict_log"] == "차이", (s, row["log_reason"])
        assert final(row) == ("차이", "log"), s


@pytest.mark.parametrize("data, factor", CASES)
def test_log_option_has_no_loq_zone_or_reason(data, factor):
    Y, z = data(factor)
    for s in SCALES:
        lr = pdc.judge_log(Y * s, z * s, R)
        assert "zone" not in lr and "doe_center" not in lr
        assert "LoQ" not in lr["reason"]
        assert "LoQ" not in run_item(Y * s, z * s)["log_reason"]


def test_excluded_base_is_final_even_for_log_candidate():
    row = {"status": ST_LOG_CANDIDATE, "verdict": V_EXCLUDED, "verdict_log": "동등"}
    assert final_verdict(row) == (V_EXCLUDED, "linear")
    d = add_final_verdict(pd.DataFrame({"ITEM": ["A"], "zone": [V_EXCLUDED], "verdict": [V_EXCLUDED],
                                        "reason": ["x"], "status": [ST_LOG_CANDIDATE], "verdict_log": ["차이"]}))
    assert (d.loc[0, "verdict_final"], d.loc[0, "verdict_basis"]) == (V_EXCLUDED, "linear")


ST_TEST = "시험 옵션"


def extra_option(replaces: bool) -> Option:
    return Option("test", "verdict_test", lambda row: ST_TEST in str(row.get("status")).split(";"), replaces,
                  lambda Y, z, r, res: {"verdict_test": "미결"})


def test_appended_option_order_and_eligibility(monkeypatch):
    # 규칙 4: 동등을 주는 첫 대상 옵션, 없으면 replaces 인 대상 옵션 (log 가 앞), 없으면 기본 판정
    monkeypatch.setattr(pdc, "OPTIONS", (*pdc.OPTIONS, extra_option(replaces=True)))
    both = f"{ST_LOG_CANDIDATE};{ST_TEST}"
    d = add_final_verdict(pd.DataFrame({
        "ITEM": ["both", "second", "second_after_log_excluded", "log_not_equal", "equal", "excluded", "none"],
        "verdict": ["차이", "차이", "차이", "차이", "동등", V_EXCLUDED, "미결"],
        "status": [both, ST_TEST, both, both, both, both, ST_OK],
        "verdict_log": ["동등", "동등", V_EXCLUDED, "미결", "차이", "동등", "동등"],
        "verdict_test": ["차이", "동등", "미결", "동등", "차이", "동등", "동등"],
    }))
    got = list(zip(d["verdict_final"], d["verdict_basis"]))
    assert got == [("동등", "log"), ("동등", "test"), ("미결", "test"), ("동등", "test"),
                   ("동등", "linear"), (V_EXCLUDED, "linear"), ("미결", "linear")]


def test_option_that_does_not_replace_changes_only_to_equal(monkeypatch):
    monkeypatch.setattr(pdc, "OPTIONS", (extra_option(replaces=False),))
    d = add_final_verdict(pd.DataFrame({"ITEM": ["a", "b"], "verdict": ["미결", "미결"], "status": [ST_TEST] * 2,
                                        "verdict_test": ["차이", "동등"]}))
    assert list(zip(d["verdict_final"], d["verdict_basis"])) == [("미결", "linear"), ("동등", "test")]


def test_option_columns_reach_judge_item(monkeypatch):
    monkeypatch.setattr(pdc, "OPTIONS", (*pdc.OPTIONS, extra_option(replaces=True)))
    row = run_item(*wide_data(1.15))
    assert list(row)[-len(pdc.LOG_COLS) - 1:] == [*pdc.LOG_COLS, "verdict_test"]
    assert row["verdict_test"] == "미결"
