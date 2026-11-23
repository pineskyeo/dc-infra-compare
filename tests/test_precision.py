"""측정 정밀도 열(sigma_meas, meas_precision_pct, sigma_meas_over_delta) 테스트. 합성 데이터만."""
import csv
import math
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import fail_evidence
from por_doe_compare import LOG_COLS, PRECISION_COLS, STATUS_COLS, meas_precision

ROOT = Path(__file__).resolve().parents[1]
SYNTH_TSV = ROOT / "tests" / "data" / "fail_evidence_synth.tsv"


def test_sigma_meas_is_root_sum_of_squares():
    assert meas_precision(3, 4, 100, 10)["sigma_meas"] == pytest.approx(5)


def test_meas_precision_pct():
    assert meas_precision(3, 4, 100, 10)["meas_precision_pct"] == pytest.approx(5)
    assert meas_precision(3, 4, -100, 10)["meas_precision_pct"] == pytest.approx(5)
    assert math.isnan(meas_precision(3, 4, 0, 10)["meas_precision_pct"])
    assert math.isnan(meas_precision(3, 4, float("nan"), 10)["meas_precision_pct"])


def test_sigma_meas_over_delta():
    assert meas_precision(3, 4, 100, 10)["sigma_meas_over_delta"] == pytest.approx(0.5)
    assert math.isnan(meas_precision(3, 4, 100, 0)["sigma_meas_over_delta"])
    assert math.isnan(meas_precision(3, 4, 100, float("nan"))["sigma_meas_over_delta"])


def test_nan_sigma_gives_nan():
    r = meas_precision(float("nan"), 4, 100, 10)
    assert all(math.isnan(r[k]) for k in PRECISION_COLS)


def test_fail_evidence_copies_precision_columns(tmp_path: Path):
    src = fail_evidence.read_table(SYNTH_TSV)
    n = len(src)
    sm = [f"{0.5 + 0.1 * i:.4g}" for i in range(n)]
    pct = [f"{1.5 * i:.4g}" if i % 2 else "" for i in range(n)]
    over = [f"{0.01 * i:.4g}" if i % 3 else "" for i in range(n)]
    src = src.assign(sigma_meas=sm, meas_precision_pct=pct, sigma_meas_over_delta=over)
    inp = tmp_path / "with_precision.tsv"
    src.to_csv(inp, sep="\t", index=False)

    assert fail_evidence.main(["--input", str(inp), "--out", str(tmp_path / "out")]) == 0
    out = pd.read_csv(tmp_path / "out" / "fail_evidence.csv", encoding="utf-8-sig",
                      dtype=str, keep_default_na=False)
    want = [c for c in STATUS_COLS if c != "por_gap_over_delta"] + PRECISION_COLS
    assert list(out.columns[-len(want):]) == want
    assert out["sigma_meas"].tolist() == sm
    assert out["meas_precision_pct"].tolist() == pct
    assert out["sigma_meas_over_delta"].tolist() == over


def run_script(script: Path, args) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run([sys.executable, str(script), *[str(a) for a in args]],
                          cwd=ROOT, env=env, check=True, capture_output=True, text=True)


def test_compare_cli_writes_precision_columns(tmp_path: Path):
    data, out = tmp_path / "por3", tmp_path / "out"
    run_script(ROOT / "examples" / "make_por3_data.py", [data])
    run_script(ROOT / "por_doe_compare.py", [
        "--por", data / "por_run1", "--por", data / "por_run2", "--por", data / "por_run3",
        "--doe", data / "doe", "--out", out,
    ])
    with open(out / "items.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    assert set(LOG_COLS + STATUS_COLS + PRECISION_COLS) <= set(header)     # 순서는 test_items_columns
    assert len(rows) > 1
    i_die, i_run, i_meas = (header.index(c) for c in ("sigma_die", "sigma_run", "sigma_meas"))
    checked = 0
    for r in rows[1:]:
        if r[i_die] == "" or r[i_run] == "":
            assert r[i_meas] == ""
            continue
        expected = math.hypot(float(r[i_die]), float(r[i_run]))
        assert float(r[i_meas]) == pytest.approx(expected, rel=1e-9, abs=1e-12)
        checked += 1
    assert checked > 0
