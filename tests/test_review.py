"""review.py: LoQ·log 재확인. 합성 ITEM 으로 확인 필요 규칙, lab 함수와 같은 값, 판정 불변, 출력 파일."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import review
from explain import LOQ_ZONES
from por_doe_compare import add_final_verdict, judge_item

ROOT = Path(__file__).resolve().parents[1]
LAB = Path("/Users/pinesky/workspace/dc-infra-compare-design/lab")
POR = ["POR1", "POR2", "POR3"]
L1_SEED = 25      # lognormal 0.4 dec, 반복 0.03 dec, DOE ×1.08: 기본 판정 차이 → log 로 최종 동등


def judged(name: str, Y: np.ndarray, z: np.ndarray) -> dict:
    """por_doe_compare 판정 그대로 (judge_item + add_final_verdict) 의 items.csv 한 행."""
    g = pd.DataFrame(Y, columns=POR[:Y.shape[1]]).assign(DOE=z)
    res, _ = judge_item(name, g, POR[:Y.shape[1]], {name: "A"}, 0.05, {}, pd.DataFrame(), {})
    return add_final_verdict(pd.DataFrame([{**res, "scale": "item"}])).iloc[0].to_dict()


def floor_item(rng, change, n: int = 61, J: int = 3, mu: float = 6.0):
    """lab sim_loq.make_item: 바닥 잡음 σ 1 (LoQ 10), die 값 lognormal 0.15 dec, 회차 offset 0.1."""
    x = mu * 10 ** (0.15 * rng.standard_normal(n))
    off = 0.1 * rng.standard_normal(J + 1)
    return x[:, None] + off[:J] + rng.standard_normal((n, J)), change(x, rng) + off[J] + rng.standard_normal(n)


def tail20(x, rng):
    out = x.copy()
    out[rng.choice(len(x), int(round(0.2 * len(x))), replace=False)] *= 10
    return out


def lognormal_item(seed: int):
    rng = np.random.default_rng(seed)
    x = 1e-9 * 10 ** (0.4 * rng.standard_normal(61))
    return x[:, None] * 10 ** (0.03 * rng.standard_normal((61, 3))), 1.08 * x * 10 ** (0.03 * rng.standard_normal(61))


@pytest.fixture(scope="module")
def loq_population():
    rng = np.random.default_rng(7)
    raw = {f"SAME_{i:02d}": floor_item(rng, lambda x, r: x) for i in range(30)}
    raw["DOUBLED"] = floor_item(rng, lambda x, r: 2 * x, mu=3.0)     # ×2 여도 DOE 가 LoQ 아래: 기본 판정 동등
    raw["TAIL20"] = floor_item(rng, tail20)
    items = pd.DataFrame([judged(k, *v) for k, v in raw.items()])
    return items, raw


@pytest.fixture(scope="module")
def l1_item():
    Y, z = lognormal_item(L1_SEED)
    row = judged("LEAK_L1", Y, z)
    return pd.DataFrame([row]), {"LEAK_L1": (Y, z)}


def test_population_is_below_loq(loq_population):
    items, _ = loq_population
    assert items["zone"].isin(LOQ_ZONES).all(), items["zone"].value_counts()


def test_loq_flags_doubled_by_direction_and_tail_by_tail_not_same(loq_population):
    items, raw = loq_population
    t = review.review_table(review.REVIEWS["loq"], items, raw).set_index("ITEM")
    assert items.set_index("ITEM").loc["DOUBLED", "verdict_final"] == "동등"
    assert t.loc["DOUBLED", "flag_direction"] and t.loc["DOUBLED", "flag"]
    assert t.loc["TAIL20", "flag_tail"] and t.loc["TAIL20", "flag"]
    same = t.loc[t.index.str.startswith("SAME_")]
    assert not same["flag"].any(), same.loc[same["flag"], ["dir_q", "ratio", "tail_q"]]
    assert t.loc["DOUBLED", "why"].startswith("확인 필요(방향).")
    assert "배 (" in t.loc["DOUBLED", "why"] and "die 61개 중" in t.loc["DOUBLED", "why"]
    assert "크게 벗어났다" in t.loc["TAIL20", "why"]


def test_review_never_changes_verdicts(loq_population):
    items, raw = loq_population
    before = items.copy()
    t = review.review_table(review.REVIEWS["loq"], items, raw).set_index("ITEM")
    pd.testing.assert_frame_equal(items, before)
    assert (t["verdict_final"] == before.set_index("ITEM").loc[t.index, "verdict_final"]).all()


def test_log_flag_l1_when_log_turns_diff_into_equal(l1_item):
    items, raw = l1_item
    row = items.iloc[0]
    assert (row["verdict"], row["verdict_final"], row["verdict_basis"]) == ("차이", "동등", "log")
    t = review.review_table(review.REVIEWS["log"], items, raw).iloc[0]
    assert t["log_overrode_diff"] and t["flag"]
    assert "기본 판정은 차이다." in t["why"] and "최종 판정이 동등" in t["why"]


def test_log_flag_tail_on_log_values():
    rng = np.random.default_rng(3)
    raw, rows = {}, []
    for i in range(20):
        x = 1e-9 * 10 ** (0.35 * rng.standard_normal(61))
        Y = x[:, None] * 10 ** (0.03 * rng.standard_normal((61, 3)))
        z = x * 10 ** (0.03 * rng.standard_normal(61))
        if i == 0:
            z[rng.choice(61, 12, replace=False)] *= 10
        name = "LEAK_TAIL" if i == 0 else f"LEAK_{i:02d}"
        raw[name] = (Y, z)
        rows.append({**judged(name, Y, z), "scale": "log"})
    t = review.review_table(review.REVIEWS["log"], pd.DataFrame(rows), raw).set_index("ITEM")
    assert t.loc["LEAK_TAIL", "flag_tail"]
    assert not t.drop(index="LEAK_TAIL")["flag"].any()


@pytest.fixture(scope="module")
def lab():
    if not (LAB / "review_metrics.py").is_file():
        pytest.skip("lab review_metrics.py 없음")
    sys.path.insert(0, str(LAB))
    try:
        import review_metrics
    finally:
        sys.path.remove(str(LAB))
    return review_metrics


def assert_same(ours: dict, theirs: dict):
    for k, v in theirs.items():
        if k == "ratio_text":
            continue
        if isinstance(v, (float, np.floating)) and np.isnan(v):
            assert np.isnan(ours[k]), k
        else:
            assert ours[k] == v, k


def test_metrics_and_flags_match_lab(lab, loq_population, l1_item):
    items, raw = loq_population
    for row in items.to_dict("records"):
        assert_same(review.loq_review_item(*raw[row["ITEM"]], row), lab.loq_review_item(*raw[row["ITEM"]], row))
    ours = review.review_table(review.REVIEWS["loq"], items, raw).set_index("ITEM").loc[items["ITEM"]]
    theirs = lab.flag_loq(pd.DataFrame([lab.loq_review_item(*raw[i], r) for i, r in
                                        zip(items["ITEM"], items.to_dict("records"))]))
    for c in ("dir_q", "tail_q", "flag_direction", "flag_tail", "flag"):
        np.testing.assert_array_equal(ours[c].to_numpy(), theirs[c].to_numpy(), err_msg=c)
    litems, lraw = l1_item
    row = litems.iloc[0].to_dict()
    assert_same(review.log_review_item(*lraw["LEAK_L1"], row), lab.log_review_item(*lraw["LEAK_L1"], row))
    p = np.array([0.001, 0.2, np.nan, 0.03, 0.5])
    np.testing.assert_array_equal(review.bh_adjust(p), lab.bh_adjust(p))


def _run(*args):
    env = {**os.environ, "OMP_NUM_THREADS": "1"}
    done = subprocess.run([sys.executable, "-B", *map(str, args)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-3000:]
    return done.stdout


def test_cli_writes_review_outputs_and_leaves_items_csv_alone(tmp_path):
    data, out = tmp_path / "por3", tmp_path / "out"
    _run(ROOT / "examples" / "make_por3_data.py", data)
    raw_args = [a for i in (1, 2, 3) for a in ("--por", data / f"por_run{i}")] + ["--doe", data / "doe"]
    _run(ROOT / "por_doe_compare.py", *raw_args, "--out", out)
    items_csv = out / "items.csv"
    digest = hashlib.sha256(items_csv.read_bytes()).hexdigest()
    stale = out / "review" / "items" / "OLD.png"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"")
    _run(ROOT / "review.py", "--input", items_csv, "--out", out, *raw_args)
    assert hashlib.sha256(items_csv.read_bytes()).hexdigest() == digest
    rv = out / "review"
    for name in ("loq_review.csv", "log_review.csv", "loq_review.png", "log_review.png"):
        assert (rv / name).is_file(), name
    loq = pd.read_csv(rv / "loq_review.csv", encoding="utf-8-sig")
    assert loq.set_index("ITEM").loc["IOFF_LEAK", "flag_tail"]
    flagged = set(loq.loc[loq["flag"], "ITEM"]) | set(pd.read_csv(rv / "log_review.csv").query("flag")["ITEM"])
    assert {p.stem for p in (rv / "items").glob("*.png")} == flagged


def test_l1_needs_no_raw_data(l1_item):
    items, _ = l1_item
    t = review.review_table(review.REVIEWS["log"], items, {}).iloc[0]
    assert t["flag"] and not t["flag_tail"] and "꼬리는 계산하지 못했다" in t["why"]


def test_no_target_items_still_writes_header_and_maps(tmp_path):
    items = pd.DataFrame([{"ITEM": "VT", "zone": "정량", "status": "정상", "verdict": "동등", "scale": "item"}])
    for name, rv in review.REVIEWS.items():
        t = review.review_table(rv, items, {})
        assert t.empty and list(t.columns) == [*rv.copy_cols, *rv.cols]
        (review.plot_loq_map if name == "loq" else review.plot_log_map)(t, tmp_path / f"{name}.png")
        assert (tmp_path / f"{name}.png").stat().st_size > 0


def test_flagged_rows_come_first_strongest_evidence_first():
    t = pd.DataFrame({"ITEM": list("ABCDE"), "flag": [False, True, True, True, False],
                      "flag_direction": [False, True, False, True, False], "flag_tail": [False, False, True, True, False],
                      "dir_q": [0.001, 0.04, 0.5, 0.01, 0.9], "tail_q": [0.5, 0.5, 0.001, 0.02, 0.9],
                      "tail_frac": [0.0, 0.0, 0.10, 0.20, 0.0]})
    assert list(review.strongest_first(t)["ITEM"]) == ["C", "D", "B", "A", "E"]
    log = pd.DataFrame({"ITEM": list("XYZ"), "flag": [True, True, True], "log_overrode_diff": [False, True, False],
                        "flag_tail": [True, False, True], "tail_q": [0.01, np.nan, 0.001], "tail_frac": [0.1, np.nan, 0.1]})
    assert list(review.strongest_first(log)["ITEM"]) == ["Y", "Z", "X"]


def test_max_figures_draws_only_the_strongest_flagged_items(tmp_path):
    data, out = tmp_path / "por3", tmp_path / "out"
    _run(ROOT / "examples" / "make_por3_data.py", data)
    raw_args = [a for i in (1, 2, 3) for a in ("--por", data / f"por_run{i}")] + ["--doe", data / "doe"]
    _run(ROOT / "por_doe_compare.py", *raw_args, "--out", out)
    stdout = _run(ROOT / "review.py", "--input", out / "items.csv", "--out", out, "--max-figures", "1", *raw_args)
    rv = out / "review"
    loq = pd.read_csv(rv / "loq_review.csv", encoding="utf-8-sig")
    flagged = loq[loq["flag"]]
    assert list(flagged.index) == list(range(len(flagged)))
    drawn = {p.stem for p in (rv / "items").glob("*.png")}
    assert flagged["ITEM"].iloc[0] in drawn and len(drawn) <= 2
    if len(flagged) > 1:
        assert "근거가 센 1개까지만" in stdout
