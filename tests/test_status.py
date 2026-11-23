"""item_status(데이터 상태 열)와 fail_evidence의 상태 열 전달 테스트. 합성 데이터만."""
import csv
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import fail_evidence
from por_doe_compare import LOG_COLS, PRECISION_COLS, STATUS_COLS, item_status

ROOT = Path(__file__).resolve().parents[1]
SYNTH_TSV = ROOT / "tests" / "data" / "fail_evidence_synth.tsv"
DELTA = 5.0


def normal_data(seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """die 200개 × 회차 3, 값 100 ± 정규잡음 1."""
    rng = np.random.default_rng(seed)
    return 100 + rng.normal(0, 1, (200, 3)), 100 + rng.normal(0, 1, 200)


def parts(s: str) -> list[str]:
    return s.split(";") if s else []


def test_fixed_value_is_flat():
    Y, z = np.full((200, 3), 400.0), np.full(200, 400.0)
    st = item_status(Y, z, DELTA)
    assert "산포 0" in parts(st["status"])


def test_run_shift_is_unstable():
    Y, z = normal_data()
    Y[:, 2] += 2 * DELTA
    st = item_status(Y, z, DELTA)
    assert "조건 불안정" in parts(st["status"])
    assert 1.5 <= st["por_gap_over_delta"] <= 2.5


def test_coarse_resolution():
    Y, z = normal_data()
    st = item_status(np.round(Y), np.round(z), DELTA)
    assert "분해능 부족" in parts(st["status"])


def test_normal_data_is_ok():
    Y, z = normal_data()
    st = item_status(Y, z, DELTA)
    assert st["status"] == "정상"


def test_two_statuses_are_joined_in_same_order():
    Y, z = normal_data()
    Y[:, 2] += 2 * DELTA
    st = item_status(np.round(Y), np.round(z), DELTA)
    # 3회차만 2Δ 밀리면 die별 회차 범위도 ≈ 2Δ라 회차 흔들림도 같이 붙는다
    assert parts(st["status"]) == ["조건 불안정", "회차 흔들림", "분해능 부족"]
    assert st["resolution_step"] == 1.0 and st["resolution_over_delta"] == 1.0 / DELTA


def test_delta_nan_skips_delta_checks():
    Y, z = normal_data()
    Y[:, 2] += 2 * DELTA
    st = item_status(np.round(Y), np.round(z), float("nan"))
    assert "조건 불안정" not in parts(st["status"])
    assert "분해능 부족" not in parts(st["status"])


def test_mean_median_ratio():
    # R = 회차 평균 = [1, 2, 6] → (3 − 2) / 2 = 0.5
    Y = np.array([[1.0, 1.0], [2.0, 2.0], [6.0, 6.0]])
    assert item_status(Y, np.array([1.0, 2.0, 6.0]), 1.0)["mean_median_ratio"] == 0.5
    Y0 = np.array([[-1.0, -1.0], [0.0, 0.0], [5.0, 5.0]])
    assert math.isnan(item_status(Y0, np.array([1.0, 2.0, 3.0]), 1.0)["mean_median_ratio"])


def read_out(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def test_fail_evidence_copies_status_columns(tmp_path: Path):
    src = fail_evidence.read_table(SYNTH_TSV)
    n = len(src)
    status = ["정상" if i % 2 else "조건 불안정;분해능 부족" for i in range(n)]
    share = ["" if i % 2 else "0.75" for i in range(n)]
    ratio = [f"{0.001 * i:.4g}" if i % 3 else "" for i in range(n)]
    src = src.assign(status=status, fixed_share=share, mean_median_ratio=ratio)
    inp = tmp_path / "with_status.tsv"
    src.to_csv(inp, sep="\t", index=False)

    assert fail_evidence.main(["--input", str(inp), "--out", str(tmp_path / "out")]) == 0
    out = read_out(tmp_path / "out" / "fail_evidence.csv")
    assert list(out.columns[-len(fail_evidence.STATUS_COLUMNS) - 3:-3]) == list(fail_evidence.STATUS_COLUMNS)
    assert out["status"].tolist() == status
    assert out["fixed_share"].tolist() == share
    assert out["mean_median_ratio"].tolist() == ratio


def test_fail_evidence_without_status_columns(tmp_path: Path):
    assert fail_evidence.main(["--input", str(SYNTH_TSV), "--out", str(tmp_path / "out")]) == 0
    out = read_out(tmp_path / "out" / "fail_evidence.csv")
    assert list(out.columns[-len(fail_evidence.STATUS_COLUMNS) - 3:-3]) == list(fail_evidence.STATUS_COLUMNS)
    for c in fail_evidence.STATUS_COLUMNS:
        assert (out[c] == "").all()


def run_script(script: Path, args) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run([sys.executable, str(script), *[str(a) for a in args]],
                          cwd=ROOT, env=env, check=True, capture_output=True, text=True)


def test_compare_cli_writes_status_columns(tmp_path: Path):
    data, out = tmp_path / "por3", tmp_path / "out"
    run_script(ROOT / "examples" / "make_por3_data.py", [data])
    run_script(ROOT / "por_doe_compare.py", [
        "--por", data / "por_run1", "--por", data / "por_run2", "--por", data / "por_run3",
        "--doe", data / "doe", "--out", out,
    ])
    with open(out / "items.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    assert set(LOG_COLS + STATUS_COLS) <= set(header)     # 순서는 test_items_columns
    assert len(rows) > 1
    assert all(r[header.index("status")] for r in rows[1:])
