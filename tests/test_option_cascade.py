"""LoQ 근처 태그와 장비 정확도 판정, 그룹 scale (--groups·--scales) 과 그것이 판정 길에 주는 영향. 합성 데이터만, seed 고정."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import por_doe_compare as pdc
from por_doe_compare import (AUTO_COLS, R_LINEAR, ST_NEAR_LOQ, ItemInfo, add_final_verdict, item_scales, item_status,
                             judge, near_loq)

ROOT = Path(__file__).resolve().parents[1]
POR = ["POR1", "POR2", "POR3"]


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
    d = add_final_verdict(pd.DataFrame([{**near, "route": R_LINEAR, "cls_level": "바닥 근처"}]))
    assert (d.loc[0, "verdict_final"], d.loc[0, "verdict_basis"]) == ("동등", "accuracy")

    far = judged_row(3.0)
    assert far["por_median"] / far["LoQ"] > 2.5
    assert ST_NEAR_LOQ not in far["status"].split(";")
    assert (far["verdict"], far["verdict_with_accuracy"]) == ("미결", "동등"), far["reason"]
    d = add_final_verdict(pd.DataFrame([{**far, "route": R_LINEAR, "cls_level": "정량"}]))
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
    plain = tmp_path / "plain"
    assert run_compare(por3, plain).returncode == 0
    before = pd.read_csv(plain / "items.csv")
    # 분류의 척도(cls_scale)와 판정 길(route)은 scales 표를 따르게 되어 있다 (classify.py)
    assert dict(zip(items["ITEM"], items["cls_scale"]))["VT_SAME"] == "log"
    assert dict(zip(items["ITEM"], items["route"]))["VT_SAME"] == "log TOST"
    # 표가 바꾸는 것은 척도와 판정 길, 그리고 그 길이 정하는 최종 판정뿐이다 (1·2단계 판정과 다른 열은 그대로)
    by_table = ["scale", "cls_scale", "route", "verdict_final", "verdict_basis", "verdict_final_log_run", "route_note",
                "verdict_abs", "abs_delta"]
    pd.testing.assert_frame_equal(items.drop(columns=by_table), before.drop(columns=by_table))
    moved = items.set_index("ITEM").loc[lambda t: t["verdict"] != "동등"]
    assert (moved.loc[moved["route"] == "log TOST", "verdict_basis"].isin(["log", "linear"])).all()
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
