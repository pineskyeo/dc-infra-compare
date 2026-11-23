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
REMOVED_COLS = ("rel_shift",)       # 레거시 열 중 items.csv 에서 뺀 열


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


def test_items_csv_matches_frozen_legacy_by_column_name(por3_data: Path, tmp_path: Path):
    legacy_out = tmp_path / "legacy_out"
    refactored_out = tmp_path / "refactored_out"

    run_script(LEGACY, compare_args(por3_data, legacy_out))
    run_script(ROOT / "por_doe_compare.py", compare_args(por3_data, refactored_out))

    def rows(path: Path) -> list[dict[str, str]]:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    new_rows = rows(refactored_out / "items.csv")
    legacy_rows = [{("verdict_with_accuracy" if k == "verdict_no_accuracy" else k): v for k, v in r.items()}
                   for r in rows(legacy_out / "items.csv")]
    # 열은 이름으로 맞춘다 (순서는 COLUMN_GROUPS). 레거시에 없던 열은 비교에서 뺀다.
    # 결정 4: 장비 정확도 폭은 판정에 안 쓰고 verdict_no_accuracy 자리에 verdict_with_accuracy (참고 판정)
    status_cols = ["status", "por_gap_over_delta", "por_gap_over_noise",
                   "run_jitter_pct", "run_jitter_over_delta", "spearman_size_jitter",
                   "resolution_step", "resolution_over_delta", "fixed_share",
                   "decades", "skew_lin", "skew_log", "log_fit", "bimodality_log",
                   "mean_median_ratio",
                   "sigma_meas", "meas_precision_pct", "sigma_meas_over_delta"]
    added = {"ID", "verdict_final", "verdict_basis", "scale", *LOG_COLS, *status_cols}
    assert set(new_rows[0]) == (set(legacy_rows[0]) - set(REMOVED_COLS)) | added
    for r in new_rows:
        for c in added:
            r.pop(c)
    for r in legacy_rows:
        for c in REMOVED_COLS:
            r.pop(c)

    # 행은 ORDER 로 정렬이 바뀔 수 있어 ITEM 기준으로 맞춰 비교한다.
    accuracy_changed = ("verdict", "reason", "delta", "delta_source", "verdict_with_accuracy")
    new_by_item = {r["ITEM"]: r for r in new_rows}
    legacy_by_item = {r["ITEM"]: r for r in legacy_rows}
    assert len(new_by_item) == len(new_rows)
    assert new_by_item.keys() == legacy_by_item.keys()

    # σ_die = 0 인 IOFF_STEP 은 blank 하한으로 LoQ 미만이라 판정 제외가 아니고 레거시와 같다 (판정 제외 규칙 4·6)
    assert not [item for item, r in new_by_item.items() if r["verdict"] == "판정 제외"]

    widened = sorted(item for item, r in legacy_by_item.items() if r["delta_source"] == "장비 정확도")
    assert widened == ["VOS_OFFSET"]
    vos_new, vos_old = new_by_item["VOS_OFFSET"], legacy_by_item["VOS_OFFSET"]
    assert (vos_old["verdict"], vos_new["verdict"]) == ("동등", "차이")
    assert vos_new["delta_source"] == "정책 + 회차"
    assert vos_new["verdict_with_accuracy"] == "동등"

    def without(r: dict[str, str], cols) -> dict[str, str]:
        return {k: v for k, v in r.items() if k not in cols}

    for item, new in new_by_item.items():
        legacy = legacy_by_item[item]
        if item in widened:
            assert without(new, accuracy_changed) == without(legacy, accuracy_changed), item
        else:
            acc = {"verdict_with_accuracy"}
            assert without(new, acc) == without(legacy, acc), item
            # 정확도 폭이 Δ보다 작던 ITEM의 참고 판정은 옛 verdict_no_accuracy 와 같고, 폭이 없으면 빈 칸
            want = legacy["verdict_with_accuracy"] if new["accuracy_margin"] else ""
            assert new["verdict_with_accuracy"] == want, item


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
