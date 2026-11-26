"""raw_stats.py: 원데이터 전체 집계, 경계 조건, DCNORMAL 명령행."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import golden_cases as gc  # noqa: E402
import raw_stats as rs  # noqa: E402


def frame(values, item="A") -> pd.DataFrame:
    return pd.DataFrame({"ITEM": [item] * len(values), "DATA": values,
                         "COORD_X_Y": [f"{i // 2}_{i % 2}" for i in range(len(values))]})


def test_matches_direct_numpy_with_duplicate_and_run_only_die():
    por_values = [[1.0, 2.0, 2.0, 8.0], [2.0, 3.0, 4.0], [0.0, 1.0, 5.0]]
    doe_values = [2.0, 4.0, 8.0]
    table = rs.raw_stats([frame(v) for v in por_values], frame(doe_values))
    assert table["ITEM"].tolist() == ["A"]
    row = table.iloc[0]
    for k, values in enumerate(por_values, 1):
        ref, doe = np.array(values), np.array(doe_values)
        assert row[f"n_raw_POR{k}"] == len(values)  # POR1 의 중복 행과 이 회차에만 있는 die 포함
        assert row[f"median_raw_POR{k}"] == np.median(ref)
        assert row[f"sd_raw_POR{k}"] == pytest.approx(np.std(ref, ddof=1), rel=1e-12)
        assert row[f"med_shift_POR{k}"] == pytest.approx(
            abs(np.median(ref) - np.median(doe)) / np.std(ref, ddof=1), rel=1e-12)
        assert row[f"sigma_ratio_POR{k}"] == pytest.approx(np.std(doe, ddof=1) / np.std(ref, ddof=1), rel=1e-12)


def test_doe_outlier_changes_ratio_and_raw_counts_include_all_rows():
    por = frame([1.0, 2.0, 2.0, 1e90, "bad"])  # 다른 회차에 없는 die, 중복, Open 코드, 숫자 아님
    doe = frame([2.0, 3.0])
    before = rs.raw_stats([por], doe).iloc[0]
    after = rs.raw_stats([por], frame([2.0, 3.0, 100 * np.std([1.0, 2.0, 2.0, 1e90], ddof=1)])).iloc[0]
    assert (before["n_raw_POR1"], before["n_nonnum_POR1"]) == (4, 1)
    assert after["n_raw_DOE"] == 3
    assert after["sd_raw_DOE"] != before["sd_raw_DOE"]
    assert after["sigma_ratio_POR1"] != before["sigma_ratio_POR1"]


def test_edge_rules_first_match_and_zero_doe_is_valid():
    por = pd.concat([frame([1.0], "N_ONE"), frame([1.0, 1.0], "ZERO_REF"),
                     frame([1.0, 2.0], "ZERO_DOE"), frame([1.0, np.inf], "INF")], ignore_index=True)
    doe = pd.concat([frame([1.0, 2.0], "N_ONE"), frame([1.0, 2.0], "ZERO_REF"),
                     frame([2.0, 2.0], "ZERO_DOE"), frame([1.0, 2.0], "INF")], ignore_index=True)
    rows = rs.raw_stats([por], doe).set_index("ITEM")
    for item, note in [("N_ONE", "n<2"), ("ZERO_REF", "σ_ref=0"), ("INF", "비유한 값")]:
        assert rows.loc[item, "raw_note_POR1"] == note
        assert np.isnan(rows.loc[item, "med_shift_POR1"])
        assert np.isnan(rows.loc[item, "sigma_ratio_POR1"])
    assert rows.loc["ZERO_DOE", "sigma_ratio_POR1"] == 0
    assert rows.loc["ZERO_DOE", "raw_note_POR1"] == ""
    assert np.isfinite(rows.loc["ZERO_DOE", "med_shift_POR1"])


def test_ms3_limit_is_three_ref_sd_and_pct_uses_ref_median():
    por_values = [1.0, 2.0, 4.0, 8.0]
    row = rs.raw_stats([frame(por_values)], frame([2.0, 3.0])).iloc[0]
    sd = np.std(por_values, ddof=1)
    assert row["ms3_limit_POR1"] == pytest.approx(3 * sd, rel=1e-12)
    assert row["ms3_limit_pct_POR1"] == pytest.approx(3 * sd / abs(np.median(por_values)) * 100, rel=1e-12)
    assert row["raw_note_POR1"] == ""


def test_median_ref_zero_blanks_pct_and_adds_note():
    ref_values = [-1.0, 0.0, 1.0]
    rows = rs.raw_stats([frame(ref_values)], frame([2.0, 3.0])).set_index("ITEM")
    assert rows.loc["A", "ms3_limit_POR1"] == pytest.approx(3 * np.std(ref_values, ddof=1), rel=1e-12)
    assert np.isnan(rows.loc["A", "ms3_limit_pct_POR1"])
    assert rows.loc["A", "raw_note_POR1"] == "median_ref=0 (ms3 % 없음)"


def test_median_ref_zero_note_joins_after_existing_reason():
    rows = rs.raw_stats([frame([-1.0, 0.0, 1.0])], frame([2.0])).set_index("ITEM")
    assert rows.loc["A", "raw_note_POR1"] == "n<2; median_ref=0 (ms3 % 없음)"
    assert rows.loc["A", "ms3_limit_POR1"] == pytest.approx(3 * np.std([-1.0, 0.0, 1.0], ddof=1), rel=1e-12)
    assert np.isnan(rows.loc["A", "ms3_limit_pct_POR1"])


def test_zero_ref_sd_gives_zero_ms3_limit():
    row = rs.raw_stats([frame([1.0, 1.0, 1.0])], frame([1.0, 2.0])).iloc[0]
    assert row["ms3_limit_POR1"] == 0.0
    assert row["ms3_limit_pct_POR1"] == 0.0
    assert row["raw_note_POR1"] == "σ_ref=0"


def test_short_or_nonfinite_ref_gives_blank_ms3_limit_and_pct():
    por = pd.concat([frame([1.0], "ONE"), frame([1.0, np.inf], "INF")], ignore_index=True)
    doe = pd.concat([frame([1.0, 2.0], "ONE"), frame([1.0, 2.0], "INF")], ignore_index=True)
    rows = rs.raw_stats([por], doe).set_index("ITEM")
    for item in ("ONE", "INF"):
        assert np.isnan(rows.loc[item, "ms3_limit_POR1"])
        assert np.isnan(rows.loc[item, "ms3_limit_pct_POR1"])


def test_ms3_columns_sit_between_sigma_ratio_and_raw_note():
    cols = rs.column_names(1)
    start = cols.index("med_shift_POR1")
    assert cols[start:start + 5] == ["med_shift_POR1", "sigma_ratio_POR1",
                                     "ms3_limit_POR1", "ms3_limit_pct_POR1", "raw_note_POR1"]


def test_cli_reads_dcnormal_and_accepts_common_args(tmp_path):
    data = tmp_path / "por3"
    gc.make_por3(data)
    out = tmp_path / "out"
    gc._run([ROOT / "raw_stats.py",
             *(a for k in (1, 2, 3) for a in ("--por", data / f"por_run{k}")), "--doe", data / "doe",
             "--r", "0.05", "--level", data / "level.csv", "--blank", data / "blank",
             "--blank-map", data / "blank_map.csv", "--key", "WAFERID,COORD_X_Y,ITEM", "--encoding", "auto",
             "--out", out])
    table = pd.read_csv(out / "raw_stats.csv", encoding="utf-8-sig")
    assert (out / "raw_stats.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert table["ITEM"].tolist() == sorted(table["ITEM"])
    assert {"med_shift_POR3", "sigma_ratio_POR3", "raw_note_POR3"} <= set(table.columns)
    assert (table["n_raw_DOE"] > 0).all()
