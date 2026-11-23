"""ITEM 분류(classify.py)와 dcc classes: 합성 ITEM 마다 분류 축 값과 판정 길, 판정 길 참고 결과, 판정 불변."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import classify
import por_doe_compare as pdc

ROOT = Path(__file__).resolve().parents[1]
N = 61
R = 0.05
NO_BLANK = pd.DataFrame(columns=["BLANK_ITEM"]).set_index("BLANK_ITEM")


def judged(Y, z, item="X") -> dict:
    """judge_item 결과 행 (판정과 같은 경로)."""
    Y, z = np.asarray(Y, float), np.asarray(z, float)
    g = pd.DataFrame(Y, columns=[f"POR{k + 1}" for k in range(Y.shape[1])]).assign(DOE=z)
    return pdc.judge_item(item, g, list(g.columns[:-1]), {}, R, {}, NO_BLANK, {})[0]


def facts(Y, z=None) -> classify.Facts:
    Y = np.asarray(Y, float)
    z = Y[:, 0] if z is None else np.asarray(z, float)
    return classify.item_facts(Y, z, judged(Y, z), R)


def classes(Y, z=None, **table) -> dict:
    from dataclasses import replace
    return classify.classify(replace(facts(Y, z), **table))


def runs(level, die_sd, rep_sd, n=N, seed=0, J=3):
    rng = np.random.default_rng(seed)
    die = level + rng.normal(0, die_sd, n)
    return np.column_stack([die + rng.normal(0, rep_sd, n) for _ in range(J)])


def lognormal_runs(decades=0.5, rep=0.01, n=N, seed=1):
    rng = np.random.default_rng(seed)
    die = 10 ** rng.normal(-9, decades, n)
    return np.column_stack([die * 10 ** rng.normal(0, rep, n) for _ in range(3)])


PLAIN = runs(1.0, 0.003, 0.002)


def test_plain_item_is_continuous_quantitative_linear():
    c = classes(PLAIN)
    assert c == {"cls_valid": "정상", "cls_sign": "양수만", "cls_level": "정량", "cls_resolution": "연속",
                 "cls_shape": "한 덩어리", "cls_noise": c["cls_noise"], "cls_scale": "판별 불가", "cls_run": "안정",
                 "route": "선형 TOST"}


def test_classification_never_reads_doe():
    """DOE 를 아무리 바꿔도 (0, 부호 반대, 한계 밖, die 몇 개만) 분류 값은 같다."""
    for Y in (PLAIN, lognormal_runs(), runs(0.0, 0.0, 1.0)):
        base = classes(Y)
        for z in (np.zeros(N), -Y[:, 0] * 7, Y[:, 0] * 1e3, np.where(np.arange(N) < 5, 9.9e99, Y[:, 1])):
            assert classes(Y, z) == base


def test_valid_die_short_and_por_only_causes():
    assert classes(PLAIN[:6])["cls_valid"] == "die 부족"
    zero_run = PLAIN.copy()
    zero_run[:, 1] = 0.0
    c = classes(zero_run)
    assert "회차 0값" in c["cls_valid"].split(";") and c["route"] == "제외"
    same = np.full((N, 3), 2.0)
    assert set(classes(same)["cls_valid"].split(";")) >= {"모든 값 같음"}
    assert classes(PLAIN[:6])["route"] == "제외"


def test_sign_values():
    assert classes(-PLAIN)["cls_sign"] == "음수만"
    with_zero = PLAIN.copy()
    with_zero[:3] = 0.0
    assert classes(with_zero)["cls_sign"] == "0 포함"
    assert classes(runs(0.0, 0.0, 1.0))["cls_sign"] == "부호 섞임"
    opened = PLAIN.copy()
    opened[0, 0] = 9.9e99
    assert classes(opened)["cls_sign"] == "양수만"


def test_level_values_and_their_routes():
    floor = classes(runs(0.0, 0.0, 1.0))
    assert (floor["cls_level"], floor["route"]) == ("0 중심", "절대 허용폭")
    below = classes(runs(2.0, 0.0, 0.3))         # LoQ ≈ 10 × 0.3 = 3 > 2
    assert (below["cls_sign"], below["cls_level"], below["route"]) == ("양수만", "바닥 아래", "LoQ 판정")
    near = classes(runs(4.5, 0.0, 0.3))           # 3 ≤ 4.5 < 3 / (10 × 0.05) = 6
    assert near["cls_level"] == "바닥 근처"
    assert classes(PLAIN)["cls_level"] == "정량"


def test_step_values_route_to_absolute_tolerance():
    vt = np.round(runs(0.45, 0.02, 0.008) / 0.01) * 0.01      # 10 mV 계단, Δ ≈ 0.0225 V
    c = classes(vt)
    assert (c["cls_resolution"], c["cls_level"], c["route"]) == ("계단", "정량", "절대 허용폭")
    assert classes(PLAIN)["cls_resolution"] == "연속"


def test_step_below_loq_stays_on_loq_route():
    c = classes(np.round(runs(2.0, 0.0, 0.3) / 0.5) * 0.5)
    assert (c["cls_resolution"], c["cls_level"], c["route"]) == ("계단", "바닥 아래", "LoQ 판정")


def test_shape_two_lumps_outlier_and_limit():
    rng = np.random.default_rng(3)
    two = np.where(np.arange(N) % 2 == 0, 1e-9, 1e-7)[:, None] * 10 ** rng.normal(0, 0.02, (N, 3))
    assert "두 덩어리" in classes(two)["cls_shape"].split(";")
    spiky = PLAIN.copy()
    spiky[[4, 9]] *= 10
    assert "튀는 die" in classes(spiky)["cls_shape"].split(";")      # status 두 덩어리도 같이 켜진다 (lab Q2)
    clipped = np.minimum(runs(1.0, 0.05, 0.005), 1.02)
    c = classes(clipped)
    assert (c["cls_shape"], c["route"]) == ("한계에 걸림", "한계 비교")
    opened = PLAIN.copy()
    opened[7, :] = 9.9e99
    assert "한계에 걸림" in classes(opened)["cls_shape"].split(";")
    assert classes(PLAIN)["cls_shape"] == "한 덩어리"


def test_scale_classifier_and_table():
    log_item = classes(lognormal_runs())
    assert (log_item["cls_scale"], log_item["route"]) == ("log", "log TOST")
    rng = np.random.default_rng(5)
    die = 10 ** rng.normal(-9, 0.5, N)
    additive = np.column_stack([die + rng.normal(0, 2e-12, N) for _ in range(3)])
    assert classes(additive)["cls_scale"] == "linear"
    assert classes(PLAIN)["cls_scale"] == "판별 불가"
    assert classes(lognormal_runs(), table_scale="linear")["cls_scale"] == "linear"
    assert classes(PLAIN, table_scale="log")["route"] == "log TOST"
    assert classes(runs(0.0, 0.0, 1.0), table_scale="log")["route"] != "log TOST"     # 부호 섞임은 log 불가


def test_run_values():
    assert classes(runs(1.0, 0.003, 0.05))["cls_run"] == "회차 흔들림"
    # 판정의 Δ 에 회차 항이 들어가 status 조건 불안정은 judge_item 으로는 거의 안 켜진다. 표의 규칙만 본다
    unstable = frozenset({"조건 불안정", "회차 흔들림"})
    assert classes(PLAIN, status=unstable)["cls_run"] == "조건 불안정"
    assert classes(PLAIN, status=unstable, run_shift=True)["cls_run"] == "회차 밀림"
    assert classes(PLAIN)["cls_run"] == "안정"


def test_limit_compare_same_and_moved():
    Y = np.minimum(runs(1.0, 0.05, 0.005, seed=8), 1.02)
    same = classify.limit_compare(Y, Y[:, 0], 0.05)
    assert same["limit_share_por"] == pytest.approx(same["limit_share_doe"], abs=0.05)
    assert same["limit_p"] >= 0.5 and same["verdict_limit"] == "동등"
    moved = classify.limit_compare(Y, np.full(N, 1.02), 0.05)
    assert moved["limit_share_doe"] == 1.0 and moved["limit_p"] < 0.001
    assert moved["verdict_limit"] == "미결" and "한계 밖 die 0개" in moved["route_note"]


def test_shifted_items_follow_flagged_run():
    rng = np.random.default_rng(9)
    items = [f"I{i:03d}" for i in range(120)]
    rows = []
    for it in items:
        base = rng.normal(1.0, 0.1, 30)
        Y = base[:, None] + rng.normal(0, 0.01, (30, 3))
        Y[:, 1] += 0.01          # POR2 를 sigma_die 만큼 민다
        rows.append(pd.DataFrame(Y, columns=["POR1", "POR2", "POR3"]).assign(ITEM=it))
    wide = pd.concat(rows, ignore_index=True)
    sigma = pd.Series(0.01, index=items)
    hit = classify.shifted_items(wide, ["POR1", "POR2", "POR3"], sigma)
    assert len(hit) > 100
    wide["POR2"] -= 0.01
    assert classify.shifted_items(wide, ["POR1", "POR2", "POR3"], sigma) == set()


def test_add_columns_abs_route_reference():
    rows, fx = [], {}
    for name, (Y, z) in {"VT_STEP": (np.round(runs(0.45, 0.02, 0.008) / 0.01) * 0.01, None),
                         "FLOOR": (runs(0.0, 0.0, 1.0), None), "PLAIN": (PLAIN, None)}.items():
        z = Y[:, 0] if z is None else z
        res = judged(Y, z, name)
        rows.append(res)
        fx[name] = classify.item_facts(Y, z, res, R)
    res = pdc.add_final_verdict(pd.DataFrame(rows).assign(scale="item"))
    wide = pd.concat([pd.DataFrame(PLAIN, columns=["POR1", "POR2", "POR3"]).assign(ITEM=n) for n in fx])
    out = classify.add_columns(res, fx, wide, ["POR1", "POR2", "POR3"], {"VT_STEP": "VT", "FLOOR": "IOFF"},
                               {"VT": 0.05})
    by = out.set_index("ITEM")
    assert list(out.columns[-len(pdc.CLASS_COLS):]) == list(pdc.CLASS_COLS)
    assert by.loc["VT_STEP", "route"] == "절대 허용폭"
    assert (by.loc["VT_STEP", "verdict_abs"], by.loc["VT_STEP", "abs_delta"]) == ("동등", 0.05)
    assert by.loc["FLOOR", "route"] == "절대 허용폭" and pd.isna(by.loc["FLOOR", "verdict_abs"])
    assert by.loc["FLOOR", "route_note"] == "--abs-tol 에 그룹 IOFF 없음"
    assert by.loc["PLAIN", "route"] == "선형 TOST" and pd.isna(by.loc["PLAIN", "verdict_abs"])
    assert (out["verdict_final"] == res["verdict_final"]).all()
    none = classify.add_columns(res, fx, wide, ["POR1", "POR2", "POR3"], None, None).set_index("ITEM")
    assert none.loc["VT_STEP", "route_note"] == "--abs-tol 파일 없음"


def test_read_abs_tol_rejects_non_positive(tmp_path):
    good = tmp_path / "abs.csv"
    good.write_text("group,abs_delta\nVT,0.01\nIOFF,5e-12\n", encoding="utf-8")
    assert classify.read_abs_tol(good) == {"VT": 0.01, "IOFF": 5e-12}
    bad = tmp_path / "bad.csv"
    bad.write_text("group,abs_delta\nVT,0\nRON,x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="VT, RON"):
        classify.read_abs_tol(bad)


def test_class_columns_match_column_order():
    assert classify.CLS_COLS + ("route",) + classify.RESULT_COLS == pdc.CLASS_COLS


def _run(*args, cwd=ROOT) -> subprocess.CompletedProcess:
    env = {**os.environ, "OMP_NUM_THREADS": "1", "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, "-B", *map(str, args)], cwd=cwd, env=env, capture_output=True, text=True)


@pytest.fixture(scope="module")
def dcc_classes(tmp_path_factory):
    base = tmp_path_factory.mktemp("classes")
    data = base / "por3"
    assert _run(ROOT / "examples" / "make_por3_data.py", data).returncode == 0
    (data / "groups.csv").write_text("ITEM,group\nVOS_OFFSET,VOS\nIOFF_FLOOR,IOFF\nVT_SAME,VT\n", encoding="utf-8")
    (data / "abs.csv").write_text("group,abs_delta\nVOS,1e-5\nIOFF,1e-11\n", encoding="utf-8")
    (base / "combos.ini").write_text(f"""\
[A1]
por = {data / "por_run1"}
      {data / "por_run2"}
      {data / "por_run3"}
doe = {data / "doe"}
groups = {data / "groups.csv"}
abs_tol = {data / "abs.csv"}
out = {base / "out"}
""", encoding="utf-8")
    proc = _run(ROOT / "dcc.py", "classes", "A1", "--config", base / "combos.ini")
    assert proc.returncode == 0, proc.stderr[-3000:]
    return base / "out" / "A1"


def test_dcc_classes_writes_counts_list_figure_and_examples(dcc_classes):
    out = dcc_classes / "classes"
    items = pd.read_csv(dcc_classes / "items.csv")
    counts = pd.read_csv(out / "counts.csv")
    total = counts[(counts["group"] == "전체") & (counts["axis"] == "route")].set_index("value")["n_items"]
    assert total.sum() == len(items)
    assert total.to_dict() == items["route"].value_counts().reindex(total.index, fill_value=0).to_dict()
    assert {"VOS", "IOFF", "VT", "미지정"} <= set(counts["group"])
    listed = pd.read_csv(out / "items_by_route.csv")
    assert sorted(listed["ITEM"]) == sorted(items["ITEM"])
    assert list(listed["route"]) == sorted(listed["route"], key=classify.ROUTE_NAMES.index)
    vos = items.set_index("ITEM").loc["VOS_OFFSET"]
    assert vos["route"] == "절대 허용폭" and vos["verdict_abs"] == "동등" and vos["abs_delta"] == 1e-5
    assert (out / "classes.png").stat().st_size > 10_000
    pngs = sorted(out.glob("examples/*/*.png"))
    per_route = items["route"].value_counts().clip(upper=3)
    assert len(pngs) == per_route.sum()


def test_por_doe_compare_abs_tol_needs_groups(tmp_path):
    abs_file = tmp_path / "abs.csv"
    abs_file.write_text("group,abs_delta\nVT,0.01\n", encoding="utf-8")
    proc = _run(ROOT / "por_doe_compare.py", "--por", tmp_path, "--por", tmp_path, "--doe", tmp_path,
                "--abs-tol", abs_file)
    assert proc.returncode != 0 and "--abs-tol 에는 --groups" in proc.stderr
