"""리팩터 전후 동일성과 공용 helper의 회귀 테스트."""
import csv
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from por_doe_compare import LOG_COLS, ci_median, ci_rank

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "examples" / "make_por3_data.py"
LEGACY = ROOT / "tests" / "_legacy_por_doe_compare.py"


def run_script(script: Path, args) -> subprocess.CompletedProcess:
    """repo 모듈을 찾을 수 있게 하여 CLI를 실제 subprocess로 실행한다."""
    env = os.environ.copy()
    old_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + old_pythonpath if old_pythonpath else "")
    return subprocess.run(
        [sys.executable, str(script), *[str(arg) for arg in args]],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def por3_data(tmp_path: Path) -> Path:
    data = tmp_path / "por3"
    run_script(GENERATOR, [data])
    return data


def compare_args(data: Path, out: Path) -> list:
    return [
        "--por", data / "por_run1",
        "--por", data / "por_run2",
        "--por", data / "por_run3",
        "--doe", data / "doe",
        "--r", "0.05",
        "--level", data / "level.csv",
        "--blank", data / "blank",
        "--blank-map", data / "blank_map.csv",
        "--key", "WAFERID,COORD_X_Y,ITEM",
        "--encoding", "auto",
        "--out", out,
    ]


def test_items_csv_is_byte_identical_to_frozen_legacy(por3_data: Path, tmp_path: Path):
    legacy_out = tmp_path / "legacy_out"
    refactored_out = tmp_path / "refactored_out"

    run_script(LEGACY, compare_args(por3_data, legacy_out))
    run_script(ROOT / "por_doe_compare.py", compare_args(por3_data, refactored_out))

    def rows(path: Path) -> list[list[str]]:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))

    new_rows = rows(refactored_out / "items.csv")
    assert new_rows[0][-len(LOG_COLS):] == LOG_COLS
    new_rows = [r[:-len(LOG_COLS)] for r in new_rows]
    status_cols = ["status", "por_gap_over_delta", "por_gap_over_noise",
                   "run_jitter_pct", "run_jitter_over_delta", "spearman_size_jitter",
                   "resolution_step", "resolution_over_delta", "fixed_share",
                   "decades", "skew_lin", "skew_log", "log_fit", "bimodality_log",
                   "mean_median_ratio",
                   "sigma_meas", "meas_precision_pct", "sigma_meas_over_delta"]
    assert new_rows[0][-len(status_cols):] == status_cols
    new_rows = [r[:-len(status_cols)] for r in new_rows]
    vi = new_rows[0].index("verdict") + 1          # WO-Z: verdict 뒤 verdict_final·verdict_basis 는 레거시에 없음
    assert new_rows[0][vi:vi + 2] == ["verdict_final", "verdict_basis"]
    new_rows = [r[:vi] + r[vi + 2:] for r in new_rows]
    legacy_rows = rows(legacy_out / "items.csv")
    header = new_rows[0]
    assert header == legacy_rows[0]

    # '판정 제외'는 레거시에 없던 판정이다. 그 행은 zone·verdict·reason만 달라도 되고, ORDER 때문에
    # 맨 뒤로 옮겨지므로 ITEM 기준으로 맞춰 비교한다. 나머지 행·열은 그대로 같아야 한다.
    # doe_center는 LoQ 분기에서만 채워지고 판정 제외는 그 전에 끝나 비며, verdict_no_blank는 blank 없이 다시 판정해도 판정 제외라 달라진다.
    col = {name: i for i, name in enumerate(header)}
    changed = (col["zone"], col["verdict"], col["reason"], col["doe_center"], col["verdict_no_blank"])
    new_by_item = {r[col["ITEM"]]: r for r in new_rows[1:]}
    legacy_by_item = {r[col["ITEM"]]: r for r in legacy_rows[1:]}
    assert len(new_by_item) == len(new_rows) - 1
    assert new_by_item.keys() == legacy_by_item.keys()

    excluded = sorted(item for item, r in new_by_item.items() if r[col["verdict"]] == "판정 제외")
    assert excluded == ["IOFF_STEP"]
    assert legacy_by_item["IOFF_STEP"][col["verdict"]] == "동등"
    assert new_by_item["IOFF_STEP"][col["doe_center"]] == ""
    assert new_by_item["IOFF_STEP"][col["verdict_no_blank"]] == "판정 제외"

    def without_changed(r: list[str]) -> list[str]:
        return [v for i, v in enumerate(r) if i not in changed]

    for item, new in new_by_item.items():
        legacy = legacy_by_item[item]
        if item in excluded:
            assert without_changed(new) == without_changed(legacy), item
        else:
            assert new == legacy, item

    kept = [r for r in new_rows[1:] if r[col["ITEM"]] not in excluded]
    assert kept == [r for r in legacy_rows[1:] if r[col["ITEM"]] not in excluded]


@pytest.mark.parametrize("n", [2, 3, 5, 9, 10, 11, 12, 29, 30, 31, 59, 60, 61, 62, 100])
def test_ci_rank_selects_ci_median_endpoints(n: int):
    d = np.random.default_rng(n).normal(size=n)
    sorted_d = np.sort(d)
    k = ci_rank(n)

    _, lo, hi = ci_median(d)

    assert lo == sorted_d[k]
    assert hi == sorted_d[n - 1 - k]


def test_existing_compare_and_summarize_clis_run(por3_data: Path, tmp_path: Path):
    out = tmp_path / "out"
    items = out / "items.csv"

    compared = run_script(ROOT / "por_doe_compare.py", compare_args(por3_data, out))
    assert compared.returncode == 0
    assert items.is_file()
    assert (out / "outlier_dies.csv").is_file()

    summarized = run_script(ROOT / "summarize.py", [items])
    assert summarized.returncode == 0
    assert (out / "summary.txt").is_file()
    assert (out / "item_map.csv").is_file()
