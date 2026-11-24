"""SOP 예제 따라가기 데이터 (docs/sop/examples/journeys.py) 가 판정 도구 결과와 같은지."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs" / "sop" / "examples" / "journeys.py"
sys.path.insert(0, str(SCRIPT.parent))

import journeys  # noqa: E402
import por_doe_compare as pdc  # noqa: E402

PATHS = {
    "linear": {"verdict": "동등", "basis": "linear", "route": "선형 TOST", "zone": "정량", "stage1": "동등"},
    "shift": {"verdict": "차이", "basis": "linear", "route": "선형 TOST", "zone": "정량", "stage1": "차이"},
    "log": {"basis": "log", "route": "log TOST", "zone": "정량", "cls": {"scale": "log"}},
    "loq": {"basis": "loq", "route": "LoQ 판정", "cls": {"level": "바닥 아래"}},
    "zero": {"basis": "abs", "route": "절대 허용폭", "cls": {"level": "0 중심", "sign": "부호 섞임"}},
    "step": {"basis": "abs", "route": "절대 허용폭", "cls": {"resolution": "계단"}},
}
ITEM_KEYS = {
    "step2": ("sigma_die", "sigma_run", "sigma_meas", "meas_precision_pct"),
    "step3": ("por_median", "LoD", "LoQ", "loq_ratio"),
    "step4": ("center", "ci_low", "ci_high"),
    "step5": ("policy_margin", "run_margin", "delta", "delta_log", "abs_delta", "accuracy_margin", "resolution_step"),
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return journeys.build(tmp_path_factory.mktemp("journeys"))


@pytest.fixture(scope="module")
def committed():
    return json.loads(journeys.JSON_PATH.read_text(encoding="utf-8"))


def test_check_passes():
    done = subprocess.run([sys.executable, "-B", str(SCRIPT), "--check"], capture_output=True, text=True,
                          env={**os.environ, "OMP_NUM_THREADS": "1"})
    assert done.returncode == 0, done.stdout + done.stderr


def test_js_is_same_object_as_json(committed):
    js = journeys.JS_PATH.read_text(encoding="utf-8")
    assert js.startswith(journeys.JS_HEAD) and js.endswith(journeys.JS_TAIL)
    assert json.loads(js[len(journeys.JS_HEAD):-len(journeys.JS_TAIL)]) == committed


def test_every_type_present_in_order(committed):
    assert committed["order"] == list(PATHS)
    assert set(committed["types"]) == set(PATHS)


@pytest.mark.parametrize("key", list(PATHS))
def test_numbers_equal_items_row(built, key):
    data, items = built
    t = data["types"][key]
    row = items.loc[t["item"]]
    for step, keys in ITEM_KEYS.items():
        for k in keys:
            assert t[step][k] == journeys.num(row.get(k)), (step, k)
    assert t["n_die"] == row["n_die"] == len(t["raw"]["die"])
    assert (t["final"]["verdict"], t["final"]["basis"], t["final"]["route"]) == (
        row["verdict_final"], row["verdict_basis"], row["route"])
    assert t["step3"]["zone"] == row["zone"]
    assert t["step3"]["cls"] == {c.removeprefix("cls_"): journeys.text(row[c]) for c in journeys.CLS_COLS}
    assert t["step5"]["t_factor"] == journeys.num(pdc.run_factor(t["J"]))


@pytest.mark.parametrize("key", list(PATHS))
def test_type_takes_intended_path(committed, key):
    t, want = committed["types"][key], PATHS[key]
    s6 = t["step6"]
    assert t["final"]["basis"] == s6["final"]["basis"] == want["basis"]
    assert t["final"]["route"] == t["step3"]["route"] == want["route"]
    assert t["final"]["verdict"] == s6["final"]["verdict"] == want.get("verdict", t["final"]["verdict"])
    for axis, value in want.get("cls", {}).items():
        assert t["step3"]["cls"][axis] == value, axis
    if "zone" in want:
        assert t["step3"]["zone"] == want["zone"]
    if "stage1" in want:
        assert s6["stage1"]["verdict"] == want["stage1"]
    loq_zone = t["step3"]["zone"] in pdc.LOQ_ZONE_NAMES
    assert (s6["stage2"] is not None) == loq_zone
    early = (s6["stage2"] or s6["stage1"])["verdict"]
    assert (s6["stage3"] is not None) == (early != "동등")
    if want["basis"] not in ("linear", "loq"):
        assert early != "동등" and s6["stage3"]["verdict"] == t["final"]["verdict"]
    assert (t["step7"]["cause"] is None) == (t["final"]["verdict"] == "동등")


def test_loq_example_shows_report_rule(committed):
    t = committed["types"]["loq"]
    s3, s4 = t["step3"], t["step4"]
    assert abs(s3["por_median"]) < s3["LoQ"]
    assert s3["por_median"] + s4["ci_low"] < s3["LoQ"]           # DOE 구간이 통째로 LoQ 이상은 아님
    assert t["step6"]["stage2"]["reason"].startswith("<LoQ 보고 일치")


def test_step_example_uses_value_gap(committed):
    s5 = committed["types"]["step"]["step5"]
    assert s5["resolution_step"] > s5["delta"]
    assert s5["used"]["value"] == s5["abs_delta"] == s5["resolution_step"]


@pytest.mark.parametrize("key", list(PATHS))
def test_d_is_doe_minus_por_mean(committed, key):
    raw = committed["types"][key]["raw"]
    por, doe, d = (np.array(raw[k], float) for k in ("por", "doe", "d"))
    assert por.shape == (len(raw["die"]), committed["types"][key]["J"])
    np.testing.assert_allclose(d, doe - por.mean(axis=1), rtol=1e-4, atol=1e-5 * np.abs(doe).max())


@pytest.mark.parametrize("key", list(PATHS))
def test_ci_is_sorted_d_at_rank_k(committed, key):
    t = committed["types"][key]
    d = sorted(t["raw"]["d"])
    k, n = t["step4"]["ci_rank_k"], len(d)
    assert k == pdc.ci_rank(n) + 1
    assert (d[k - 1], d[n - k]) == (t["step4"]["ci_low"], t["step4"]["ci_high"])
