"""측정 안정도 (stability.py): 흔들리는 die, 밀린 POR 회차, 전체·그룹 표, 지난 groups.csv 지우기 (합성 데이터)."""
import numpy as np
import pandas as pd
import pytest

import stability
from por_doe_compare import judge_item

DIE_COLS = ["WAFERID", "COORD_X_Y"]
COORDS = [f"{x}_{y}" for x in range(8) for y in range(8)][:61]
NOISY = ["W01 0_3", "W01 4_4", "W01 7_0"]
NO_BLANK = pd.DataFrame(columns=["BLANK_ITEM"]).set_index("BLANK_ITEM")


def make_wide(n_items: int, J: int, seed: int, noisy=(), run_shift: float = 0.0) -> tuple[pd.DataFrame, list[str]]:
    """ITEM 마다 die 61개, die 간 산포 5, 반복 잡음 1. noisy die 는 반복 잡음 5배, POR1 은 run_shift 만큼 밀림."""
    rng = np.random.default_rng(seed)
    level = 100 + rng.normal(0, 5, (n_items, len(COORDS), 1))
    noise = rng.normal(0, 1, (n_items, len(COORDS), J + 1))
    rows = [i for i, c in enumerate(COORDS) if f"W01 {c}" in noisy]
    noise[:, rows, :] *= 5
    vals = level + noise
    vals[:, :, 0] += run_shift
    por_cols = [f"POR{j + 1}" for j in range(J)]
    wide = pd.DataFrame(vals.reshape(-1, J + 1), columns=[*por_cols, "DOE"])
    wide.insert(0, "ITEM", np.repeat([f"I{i:03d}" for i in range(n_items)], len(COORDS)))
    wide.insert(0, "COORD_X_Y", np.tile(COORDS, n_items))
    wide.insert(0, "WAFERID", "W01")
    return wide, por_cols


def judged(wide: pd.DataFrame, por_cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame([judge_item(item, g, por_cols, {}, 0.05, {}, NO_BLANK, {})[0]
                         for item, g in wide.groupby("ITEM", sort=False)])


def run_write(tmp_path, wide, por_cols, outliers=None, group_of=None, level_of=None) -> dict[str, pd.DataFrame]:
    outliers = pd.DataFrame(columns=DIE_COLS + ["ITEM"]) if outliers is None else outliers
    stability.write(tmp_path, judged(wide, por_cols), wide, por_cols, DIE_COLS, outliers, group_of,
                    level_of=level_of, r=0.05)
    return {p.stem: pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False) for p in tmp_path.glob("*.csv")}


def flagged_dies(dies: pd.DataFrame) -> set[str]:
    return set((dies["WAFERID"] + " " + dies["COORD_X_Y"])[dies["flagged"].astype(str) == "True"])


def test_planted_noisy_dies_are_flagged_and_doe_outliers_counted(tmp_path):
    wide, por_cols = make_wide(200, 3, seed=1, noisy=NOISY)
    outliers = pd.DataFrame({"WAFERID": ["W01"] * 3, "COORD_X_Y": ["5_5", "5_5", "0_3"],
                             "ITEM": ["I001", "I002", "I003"]})
    t = run_write(tmp_path, wide, por_cols, outliers)
    dies = t["dies"]
    assert flagged_dies(dies) == set(NOISY)
    assert (dies.loc[dies["flagged"].astype(str) == "True", "score"].astype(float) >= stability.DIE_SCORE_MIN).all()
    assert len(dies) == 61 and (dies["n_items"].astype(int) == 200).all()
    count = dict(zip(dies["COORD_X_Y"], dies["n_doe_outlier"].astype(int)))
    assert count["5_5"] == 2 and count["0_3"] == 1 and sum(count.values()) == 3
    assert (tmp_path / "stability.png").stat().st_size > 10_000


def test_no_die_flagged_without_planted_noise(tmp_path):
    wide, por_cols = make_wide(200, 3, seed=2)
    assert flagged_dies(run_write(tmp_path, wide, por_cols)["dies"]) == set()


def test_run_shifted_one_sigma_is_the_only_flagged_run_with_three_runs(tmp_path):
    wide, por_cols = make_wide(200, 3, seed=3, run_shift=1.0)
    runs = run_write(tmp_path, wide, por_cols)["runs"]
    assert runs.loc[runs["flagged"].astype(str) == "True", "run"].tolist() == ["POR1"]
    assert float(runs.loc[0, "score"]) == pytest.approx(1.0, abs=0.15)
    assert runs.loc[0, "note"] == "" and all(runs.loc[1:, "note"].str.startswith("가장 크게 벗어난 회차가 아님"))


def test_two_runs_cannot_name_the_shifted_run(tmp_path):
    wide, por_cols = make_wide(200, 2, seed=4, run_shift=1.0)
    runs = run_write(tmp_path, wide, por_cols)["runs"]
    assert (runs["flagged"].astype(str) == "False").all()
    assert all(runs["note"].str.contains("POR 2회는"))


def test_too_few_items_gives_a_note_not_a_flag(tmp_path):
    wide, por_cols = make_wide(30, 3, seed=5, run_shift=1.0)
    runs = run_write(tmp_path, wide, por_cols)["runs"]
    assert (runs["flagged"].astype(str) == "False").all()
    assert all(runs["note"].str.contains(f"< {stability.RUN_MIN_ITEMS}"))


def test_overall_and_groups_count_bands_and_status_flags(tmp_path):
    items = pd.DataFrame({"ITEM": ["A", "B", "C", "D"], "judgeability": ["안정", "안정", "불안정", ""],
                          "rsd_pct": [1.0, 2.0, 3.0, np.nan], "ci_half_over_delta": [0.1, 0.2, 0.9, np.nan],
                          "status": ["정상", "회차 흔들림;LoQ 근처", "회차 흔들림", "산포 0"],
                          "noise_pattern": ["비례", "사이 (꺾임)", "비례 (꺾임)", "판별 불가"]})
    row = stability.overall(items).iloc[0]
    assert (row["n_items"], row["share_stable"], row["share_caution"], row["share_unstable"],
            row["share_no_band"]) == (4, 0.5, 0.0, 0.25, 0.25)
    assert row["rsd_pct_median"] == 2.0 and row["ci_half_over_delta_median"] == 0.2
    assert (row["n_run_jitter"], row["n_near_loq"], row["n_flat"], row["n_low_resolution"]) == (2, 1, 1, 0)
    assert (row["n_noise_proportional"], row["n_noise_between"], row["n_noise_unknown"], row["n_noise_constant"],
            row["n_noise_bend"]) == (2, 1, 1, 0, 2)
    groups = stability.by_group(items, {"A": "g1", "C": "g1", "B": "g0"})
    assert groups["group"].tolist() == ["g0", "g1", stability.UNGROUPED]
    assert groups["n_items"].tolist() == [1, 2, 1]


def test_rerun_without_groups_removes_old_groups_csv(tmp_path):
    wide, por_cols = make_wide(20, 3, seed=6)
    run_write(tmp_path, wide, por_cols, group_of={"I000": "g"})
    assert (tmp_path / "groups.csv").is_file()
    run_write(tmp_path, wide, por_cols)
    assert not (tmp_path / "groups.csv").exists()


def test_level_name_and_order():
    from por_doe_compare import ItemInfo, level_name
    assert [level_name(ItemInfo(L, k, None, False)) for L, k in ((1e-8, "A"), (0.1, "V"), (1e-14, "A"))] == [
        "10nA", "100mV", "10fA"]
    assert level_name(ItemInfo(float("nan"), "", None, True)) == ""
    assert sorted(["100mV", "LEVEL 없음", "1uA", "10nA"], key=stability.level_order) == [
        "10nA", "1uA", "100mV", "LEVEL 없음"]


def test_group_levels_split_bands_and_precision_by_group_and_level(tmp_path):
    wide, por_cols = make_wide(8, 3, seed=11)
    items = [f"I{i:03d}" for i in range(8)]
    level_of = dict(zip(items, ["1uA", "10nA", "1uA", "10nA", "100mV", "100mV", "1uA", ""]))
    group_of = {it: "A" if i < 4 else "B" for i, it in enumerate(items[:6])}
    t = run_write(tmp_path, wide, por_cols, group_of=group_of, level_of=level_of)["group_levels"]
    assert list(zip(t["group"], t["level"], t["n_items"])) == [
        ("A", "10nA", 2), ("A", "1uA", 2), ("B", "100mV", 2), ("미지정", "1uA", 1), ("미지정", "LEVEL 없음", 1)]
    shares = t[["share_stable", "share_caution", "share_unstable", "share_no_band"]].astype(float).sum(axis=1)
    assert np.allclose(shares, 1)
    med, p90 = (t[c].astype(float) for c in ("meas_precision_pct_median", "meas_precision_pct_p90"))
    assert (med > 0).all() and (med <= p90 + 1e-12).all()
    assert (tmp_path / "group_levels.png").is_file()


def test_rerun_without_level_removes_old_group_levels(tmp_path):
    wide, por_cols = make_wide(4, 2, seed=3)
    run_write(tmp_path, wide, por_cols, level_of={"I000": "10nA"})
    assert (tmp_path / "group_levels.csv").is_file() and (tmp_path / "group_levels.png").is_file()
    assert "group_levels" not in run_write(tmp_path, wide, por_cols)
    assert not (tmp_path / "group_levels.png").exists()
