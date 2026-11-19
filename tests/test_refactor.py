"""리팩터 전후 동일성과 공용 helper의 회귀 테스트."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from por_doe_compare import ci_median, ci_rank

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

    assert (refactored_out / "items.csv").read_bytes() == (legacy_out / "items.csv").read_bytes()


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
