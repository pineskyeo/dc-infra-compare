"""+@ 옵션 cascade (log → accuracy → log_physics), LoQ 근처 태그, 그룹 scale (--groups·--scales). 합성 데이터만, seed 고정."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import por_doe_compare as pdc
from por_doe_compare import (AUTO_COLS, ST_LOG_CANDIDATE, ST_NEAR_LOQ, ItemInfo, add_final_verdict, final_verdict,
                             item_scales, item_status, judge, judge_item, near_loq)

ROOT = Path(__file__).resolve().parents[1]
POR = ["POR1", "POR2", "POR3"]
MARGIN = {"accuracy_margin": 1.0}
PHYSICS = {"scale": "log", "decades": 1.75, "log_fit": 0.05}


def row(verdict: str = "미결", **cols) -> dict:
    return {"verdict": verdict, "status": "", "scale": "item", **cols}


def eligible(r: dict) -> list[str]:
    return [o.basis for o in pdc.OPTIONS if o.eligible(r)]


@pytest.mark.parametrize("verdict_log, verdict_acc, want", [
    ("미결", "동등", ("동등", "accuracy")),
    ("동등", "미결", ("동등", "log")),
    ("동등", "동등", ("동등", "log")),
    ("차이", "미결", ("차이", "log")),
    ("미결", "차이", ("미결", "log")),
])
def test_cascade_log_then_accuracy(verdict_log, verdict_acc, want):
    r = row(status=f"{ST_LOG_CANDIDATE};{ST_NEAR_LOQ}", verdict_log=verdict_log, verdict_with_accuracy=verdict_acc,
            **MARGIN)
    assert eligible(r) == ["log", "accuracy"]
    assert final_verdict(r) == want


@pytest.mark.parametrize("base", ["미결", "차이"])
def test_only_accuracy_eligible_and_not_equal_keeps_base(base):
    r = row(base, status=ST_NEAR_LOQ, verdict_log="동등", verdict_with_accuracy="차이", **MARGIN)
    assert eligible(r) == ["accuracy"]
    assert final_verdict(r) == (base, "linear")


def test_accuracy_needs_margin_and_tag():
    assert final_verdict(row(status=ST_NEAR_LOQ, verdict_with_accuracy="동등")) == ("미결", "linear")
    assert final_verdict(row(verdict_with_accuracy="동등", **MARGIN)) == ("미결", "linear")


def test_physics_log_comes_after_accuracy():
    near = {"status": ST_NEAR_LOQ, **MARGIN, **PHYSICS}
    assert eligible(row(**near)) == ["accuracy", "log_physics"]
    assert final_verdict(row(**near, verdict_with_accuracy="동등", verdict_log="차이")) == ("동등", "accuracy")
    assert final_verdict(row(**near, verdict_with_accuracy="미결", verdict_log="동등")) == ("동등", "log_physics")
    assert final_verdict(row(**near, verdict_with_accuracy="미결", verdict_log="차이")) == ("차이", "log_physics")


def test_equal_and_excluded_base_are_final():
    near = {"status": ST_NEAR_LOQ, **MARGIN, **PHYSICS}
    assert final_verdict(row("동등", **near, verdict_log="차이")) == ("동등", "linear")
    assert final_verdict(row(pdc.V_EXCLUDED, **near, verdict_log="동등", verdict_with_accuracy="동등")) == \
        (pdc.V_EXCLUDED, "linear")


@pytest.mark.parametrize("scale, decades, log_fit, basis", [
    ("log", 1.75, 0.05, "log_physics"),
    ("log", 1.75, -0.05, None),
    ("log", 0.05, 0.05, None),
    ("linear", 1.75, 0.5, None),
    ("auto→linear", 1.75, 0.5, None),
    ("auto→log", 1.75, 0.05, "log"),
    ("auto→log", 1.75, -0.05, None),
    ("auto→log", 0.05, 0.5, None),
])
def test_log_option_eligibility_follows_scale(scale, decades, log_fit, basis):
    # status 에 'log 후보' 가 있어도 scale 이 item 이 아니면 그룹 scale 과 decades·log_fit 만 본다
    r = row(scale=scale, decades=decades, log_fit=log_fit, status=ST_LOG_CANDIDATE, verdict_log="동등")
    assert eligible(r) == ([basis] if basis else [])
    assert final_verdict(r) == (("동등", basis) if basis else ("미결", "linear"))


def test_item_scale_keeps_log_candidate_rule():
    assert final_verdict(row(status=ST_LOG_CANDIDATE, verdict_log="동등")) == ("동등", "log")
    assert final_verdict(row(decades=1.75, log_fit=0.05, verdict_log="동등")) == ("미결", "linear")


def test_old_items_csv_without_scale_and_text_values():
    d = pd.DataFrame({"ITEM": ["old", "new"], "verdict": ["차이", "차이"], "status": [ST_LOG_CANDIDATE, ""],
                      "verdict_log": ["동등", "동등"]}, dtype=str)
    d = add_final_verdict(d)
    assert list(zip(d["verdict_final"], d["verdict_basis"])) == [("동등", "log"), ("차이", "linear")]
    d = pd.DataFrame({"ITEM": ["x"], "verdict": ["미결"], "status": [""], "scale": ["log"], "decades": ["1.75"],
                      "log_fit": ["0.05"], "verdict_log": ["동등"], "verdict_with_accuracy": [""]}, dtype=str)
    assert add_final_verdict(d).loc[0, "verdict_basis"] == "log_physics"


def test_near_loq_band():
    assert near_loq(1.5, 1.0, 0.05) and near_loq(-1.5, 1.0, 0.05) and near_loq(1.0, 1.0, 0.05)
    assert not near_loq(3.0, 1.0, 0.05)
    assert not near_loq(2.0, 1.0, 0.05)        # LoQ / (10 r) = 2 LoQ 는 밖
    assert not near_loq(0.5, 1.0, 0.05)
    assert not near_loq(1.5, np.nan, 0.05)


def boundary_item(ratio: float, seed: int = 11) -> tuple[np.ndarray, np.ndarray, dict]:
    """POR 중앙값 ≈ 1, σ_die = 1 / (10 ratio) 라 |POR| ≈ ratio × LoQ. DOE 를 Δ 만큼 옮겨 기본 판정이 경계 미결."""
    rng = np.random.default_rng(seed)
    sigma = 1 / (10 * ratio)
    Y = 1 + rng.normal(0, sigma, (400, 3))
    z = 1 + rng.normal(0, sigma, 400)
    # CALCVAL 1000: 원측정값 1 mV 라 2 V range 정확도 폭이 ITEM 단위로 ≈ 1.07, Δ 보다 훨씬 크다
    levels = {"IT": ItemInfo(1e-3, "V", 1000.0, False)}
    return Y, z + judge(Y, z, 0.05)[0]["delta"], levels


def judged_row(ratio: float) -> dict:
    Y, z, levels = boundary_item(ratio)
    g = pd.DataFrame(Y, columns=POR).assign(DOE=z)
    blank = pd.DataFrame(columns=["BLANK_ITEM"]).set_index("BLANK_ITEM")
    return pdc.judge_item("IT", g, POR, {}, 0.05, levels, blank, {})[0]


def test_equipment_option_only_near_loq():
    near = judged_row(1.5)
    assert 1.3 < near["por_median"] / near["LoQ"] < 1.7
    assert ST_NEAR_LOQ in near["status"].split(";")
    assert (near["verdict"], near["verdict_with_accuracy"]) == ("미결", "동등"), near["reason"]
    d = add_final_verdict(pd.DataFrame([{**near, "scale": "item"}]))
    assert (d.loc[0, "verdict_final"], d.loc[0, "verdict_basis"]) == ("동등", "accuracy")

    far = judged_row(3.0)
    assert far["por_median"] / far["LoQ"] > 2.5
    assert ST_NEAR_LOQ not in far["status"].split(";")
    assert (far["verdict"], far["verdict_with_accuracy"]) == ("미결", "동등"), far["reason"]
    d = add_final_verdict(pd.DataFrame([{**far, "scale": "item"}]))
    assert (d.loc[0, "verdict_final"], d.loc[0, "verdict_basis"]) == ("미결", "linear")


def test_below_loq_is_not_tagged():
    rng = np.random.default_rng(12)
    Y, z = 0.2 + rng.normal(0, 0.1, (200, 3)), 0.2 + rng.normal(0, 0.1, 200)
    res, _ = judge(Y, z, 0.05)
    assert abs(res["por_median"]) < res["LoQ"]
    assert ST_NEAR_LOQ not in item_status(Y, z, res["delta"], res["LoQ"], 0.05)["status"].split(";")


def shape_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "ITEM": ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "C1", "C2", "C3", "D1", "E1", "X1"],
        "decades": [1.5, 1.2, 0.3, np.nan, 1.5, 0.2, 0.1, 1.5, 1.5, 1.5, 1.2, 1.5, 1.5],
        "log_fit": [0.05, 0.02, -0.01, 0.9, 0.3, 0.3, 0.3, -0.1, -0.2, 0.3, 0.05, 0.5, 0.5],
    })


GROUPS = {"A1": "A", "A2": "A", "A3": "A", "A4": "A", "B1": "B", "B2": "B", "B3": "B",
          "C1": "C", "C2": "C", "C3": "C", "D1": "D", "E1": "E"}


def test_auto_decides_once_per_group():
    scale, auto = item_scales(shape_frame(), GROUPS, {"D": "log", "E": "linear", "C": "auto"})
    assert dict(zip(shape_frame()["ITEM"], scale)) == {
        **dict.fromkeys(["A1", "A2", "A3", "A4"], "auto→log"),
        **dict.fromkeys(["B1", "B2", "B3", "C1", "C2", "C3"], "auto→linear"),
        "D1": "log", "E1": "linear", "X1": "item"}
    assert list(auto.columns) == AUTO_COLS
    got = auto.set_index("group")
    assert list(got.index) == ["A", "B", "C"]
    assert got.loc["A"].tolist() == ["log", 3, 2, pytest.approx(0.02)]          # NaN decades 인 A4 는 세지 않음
    assert got.loc["B"].tolist() == ["linear", 3, 1, pytest.approx(0.3)]         # decades ≥ 1 이 절반 이하
    assert got.loc["C"].tolist() == ["linear", 3, 3, pytest.approx(-0.1)]        # log_fit 중앙값 ≤ 0


def test_auto_group_uses_group_decision_for_eligibility():
    d = shape_frame()
    d["scale"], _ = item_scales(d, GROUPS, {"D": "log", "E": "linear"})
    d = add_final_verdict(d.assign(verdict="미결", status="", verdict_log="동등"))
    assert dict(zip(d["ITEM"], d["verdict_basis"])) == {
        "A1": "log", "A2": "log", "A3": "linear", "A4": "linear",
        **dict.fromkeys(["B1", "B2", "B3", "C1", "C2", "C3", "E1", "X1"], "linear"), "D1": "log_physics"}


def run_compare(data: Path, out: Path, *extra) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, str(ROOT / "por_doe_compare.py"),
                           "--por", str(data / "por_run1"), "--por", str(data / "por_run2"),
                           "--por", str(data / "por_run3"), "--doe", str(data / "doe"),
                           "--level", str(data / "level.csv"), "--out", str(out), *map(str, extra)],
                          cwd=ROOT, env=env, check=False, capture_output=True, text=True)


@pytest.fixture(scope="module")
def por3(tmp_path_factory) -> Path:
    data = tmp_path_factory.mktemp("scales") / "por3"
    subprocess.run([sys.executable, str(ROOT / "examples" / "make_por3_data.py"), str(data)], check=True,
                   capture_output=True)
    (data / "groups.csv").write_text("ITEM,group\nVT_SAME,VT\nVT_SHIFT,VT\nVT_NOISY_DOE,VT\nRON_CONTACT,RON\n"
                                     "IOFF_FLOOR,IOFF\nIOFF_LEAK,IOFF\n", encoding="utf-8")
    (data / "scales.csv").write_text("group,scale\nVT,log\nRON,Linear\n", encoding="utf-8")
    return data


def test_no_scales_is_today(por3: Path, tmp_path: Path):
    plain, grouped = tmp_path / "plain", tmp_path / "grouped"
    assert run_compare(por3, plain).returncode == 0
    assert run_compare(por3, grouped, "--groups", por3 / "groups.csv").returncode == 0
    assert (plain / "items.csv").read_bytes() == (grouped / "items.csv").read_bytes()
    items = pd.read_csv(plain / "items.csv")
    assert set(items["scale"]) == {"item"}
    assert not (plain / pdc.SCALES_AUTO_CSV).exists()


def test_scales_file_sets_scale_and_writes_auto(por3: Path, tmp_path: Path):
    out = tmp_path / "out"
    proc = run_compare(por3, out, "--groups", por3 / "groups.csv", "--scales", por3 / "scales.csv")
    assert proc.returncode == 0, proc.stderr
    items = pd.read_csv(out / "items.csv")
    scale = dict(zip(items["ITEM"], items["scale"]))
    assert {k: scale[k] for k in ("VT_SAME", "VT_SHIFT", "RON_CONTACT", "IOFF_FLOOR", "ION_OUTLIER")} == {
        "VT_SAME": "log", "VT_SHIFT": "log", "RON_CONTACT": "linear", "IOFF_FLOOR": "auto→linear",
        "ION_OUTLIER": "item"}
    auto = pd.read_csv(out / pdc.SCALES_AUTO_CSV)
    assert list(auto.columns) == AUTO_COLS and auto["group"].tolist() == ["IOFF"]
    assert auto.loc[0, "decision"] == "linear"
    # 이 데이터의 VT 는 decades < 1 이라 log 그룹이어도 판정은 --scales 없을 때와 같다
    plain = tmp_path / "plain"
    assert run_compare(por3, plain).returncode == 0
    before = pd.read_csv(plain / "items.csv")
    # 분류의 척도(cls_scale)와 판정 길(route)은 scales 표를 따르게 되어 있다 (classify.py)
    assert dict(zip(items["ITEM"], items["cls_scale"]))["VT_SAME"] == "log"
    assert dict(zip(items["ITEM"], items["route"]))["VT_SAME"] == "log TOST"
    by_table = ["scale", "cls_scale", "route", "verdict_typed", "typed_basis", "verdict_typed_log_run"]
    pd.testing.assert_frame_equal(items.drop(columns=by_table), before.drop(columns=by_table))
    # 같은 --out 에 --scales 없이 다시 돌리면 지난 결정 파일이 남지 않는다
    assert run_compare(por3, out).returncode == 0
    assert not (out / pdc.SCALES_AUTO_CSV).exists()


def test_bad_scale_value_and_scales_without_groups_stop(por3: Path, tmp_path: Path):
    bad = tmp_path / "bad.csv"
    bad.write_text("group,scale\nVT,loglog\n", encoding="utf-8")
    proc = run_compare(por3, tmp_path / "o1", "--groups", por3 / "groups.csv", "--scales", bad)
    assert proc.returncode != 0 and "log, linear, auto" in proc.stderr
    proc = run_compare(por3, tmp_path / "o2", "--scales", por3 / "scales.csv")
    assert proc.returncode != 0 and "--groups" in proc.stderr
