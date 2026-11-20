"""회차 흔들림·작을수록 흔들림 상태와 그 열(JITTER_COLS) 테스트. 합성 데이터만."""
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import fail_evidence
import run_all
from por_doe_compare import JITTER_COLS, item_status

ROOT = Path(__file__).resolve().parents[1]
SYNTH_TSV = ROOT / "tests" / "data" / "fail_evidence_synth.tsv"


def parts(s: str) -> list[str]:
    return s.split(";") if s else []


def run_jitter_data() -> tuple[np.ndarray, np.ndarray]:
    """die 50개, 모든 die가 회차마다 ×(1, 1.3, 0.7)로 흔들림."""
    base = 1e-3 * np.arange(1, 51)
    return base[:, None] * np.array([1.0, 1.3, 0.7]), base.copy()


def size_jitter_data(seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """die 40개, 크기 1e-12~1e-6. 작은 die일수록 log 범위가 큼."""
    rng = np.random.default_rng(seed)
    size = 10 ** np.linspace(-12, -6, 40)
    half = np.linspace(0.4, 0.02, 40) * (1 + 0.1 * rng.random(40))     # log10 범위의 절반
    Y = size[:, None] * 10 ** (half[:, None] * np.array([1.0, 0.0, -1.0]))
    return Y, size.copy()


def log_normal_data(seed: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """die 200개, 크기 log 고르게, 크기와 무관한 작은 곱셈 흔들림."""
    rng = np.random.default_rng(seed)
    size = 10 ** rng.uniform(-12, -6, 200)
    Y = size[:, None] * 10 ** rng.normal(0, 0.01, (200, 3))
    return Y, size * 10 ** rng.normal(0, 0.01, 200)


def test_all_dies_jitter_is_run_jitter():
    Y, z = run_jitter_data()
    st = item_status(Y, z, 1e-4)
    assert "회차 흔들림" in parts(st["status"])
    assert re.search(r"회차 흔들림 \d+% \(\d+\.\dΔ\)", st["status_detail"])
    assert st["run_jitter_pct"] == pytest.approx(60.0)
    assert st["run_jitter_over_delta"] >= 1


def test_smaller_die_jitters_more():
    Y, z = size_jitter_data()
    st = item_status(Y, z, 1.0)
    assert "작을수록 흔들림" in parts(st["status"])
    assert "회차 흔들림" not in parts(st["status"])
    assert st["spearman_size_jitter"] <= -0.5
    detail = parts(st["status_detail"])[parts(st["status"]).index("작을수록 흔들림")]
    assert detail.startswith("ρ −")


def test_size_jitter_needs_min_die():
    Y, z = size_jitter_data()
    st = item_status(Y[::5], z[::5], 1.0)       # die 8개
    assert st["spearman_size_jitter"] <= -0.5
    assert "작을수록 흔들림" not in parts(st["status"])


def test_normal_log_data_has_neither():
    Y, z = log_normal_data()
    st = item_status(Y, z, 1.0)
    names = parts(st["status"])
    assert "회차 흔들림" not in names and "작을수록 흔들림" not in names
    assert math.isfinite(st["spearman_size_jitter"])
    assert math.isfinite(st["run_jitter_pct"])


def test_one_por_round_gives_nan():
    Y, z = run_jitter_data()
    st = item_status(Y[:, :1], z, 1e-4)
    assert all(math.isnan(st[c]) for c in JITTER_COLS)
    names = parts(st["status"])
    assert "회차 흔들림" not in names and "작을수록 흔들림" not in names


@pytest.mark.parametrize("delta", [float("nan"), 0.0])
def test_no_delta_records_columns_without_run_jitter(delta):
    Y, z = log_normal_data()
    Y = Y * np.array([1.0, 1.3, 0.7])      # 흔들림이 커도 Δ 없으면 상태는 안 붙음
    st = item_status(Y, z, delta)
    assert math.isfinite(st["run_jitter_pct"])
    assert math.isfinite(st["spearman_size_jitter"])
    assert math.isnan(st["run_jitter_over_delta"])
    assert "회차 흔들림" not in parts(st["status"])


def test_zero_dies_skipped_in_size_jitter():
    Y, z = size_jitter_data()
    Y[:3, 1] = 0.0
    st = item_status(Y, z, 1.0)
    assert math.isfinite(st["spearman_size_jitter"])


def test_fail_evidence_copies_jitter_columns(tmp_path: Path):
    src = fail_evidence.read_table(SYNTH_TSV)
    n = len(src)
    cols = {"run_jitter_pct": [f"{1.5 * i:.4g}" for i in range(n)],
            "run_jitter_over_delta": [f"{0.1 * i:.4g}" if i % 2 else "" for i in range(n)],
            "spearman_size_jitter": [f"{-0.01 * i:.4g}" if i % 3 else "" for i in range(n)]}
    inp = tmp_path / "with_jitter.tsv"
    src.assign(**cols).to_csv(inp, sep="\t", index=False)

    assert fail_evidence.main(["--input", str(inp), "--out", str(tmp_path / "out")]) == 0
    out = pd.read_csv(tmp_path / "out" / "fail_evidence.csv", encoding="utf-8-sig",
                      dtype=str, keep_default_na=False)
    assert list(out.columns[-7:-4]) == JITTER_COLS
    for c, v in cols.items():
        assert out[c].tolist() == v


def test_outlier_k_option_removed(tmp_path: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    p = subprocess.run([sys.executable, str(ROOT / "por_doe_compare.py"), "--por", "a", "--por", "b",
                        "--doe", "c", "--outlier-k", "3", "--out", str(tmp_path / "out")],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    assert p.returncode == 2
    assert "--outlier-k" in p.stderr
    with pytest.raises(SystemExit):
        run_all.build_parser().parse_args(["--por", "a", "--doe", "c", "--outlier-k", "3"])
