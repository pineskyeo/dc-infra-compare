"""WO-T: status 지표 열 분리 (숫자 문구 열 제거). 합성 데이터만."""
import csv
import importlib.util
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import fail_evidence
from por_doe_compare import (LOG_COLS, METRIC_COLS, PRECISION_COLS, ST_BIMODAL, ST_LOG_CANDIDATE, ST_OK, STATUS_COLS,
                             ExclusionFacts, excluded_reason, item_status)

ROOT = Path(__file__).resolve().parents[1]
SYNTH_TSV = ROOT / "tests" / "data" / "fail_evidence_synth.tsv"
METRICS = ["por_gap_over_delta", "por_gap_over_noise", "run_jitter_pct", "run_jitter_over_delta",
           "spearman_size_jitter", "resolution_step", "resolution_over_delta", "fixed_share"]


def run_script(script: Path, args) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run([sys.executable, str(script), *[str(a) for a in args]],
                          cwd=ROOT, env=env, check=True, capture_output=True, text=True)


@pytest.fixture(scope="module")
def items_header(tmp_path_factory) -> list[str]:
    tmp = tmp_path_factory.mktemp("wot")
    data, out = tmp / "por3", tmp / "out"
    run_script(ROOT / "examples" / "make_por3_data.py", [data])
    run_script(ROOT / "por_doe_compare.py", [
        "--por", data / "por_run1", "--por", data / "por_run2", "--por", data / "por_run3",
        "--doe", data / "doe", "--out", out,
    ])
    with open(out / "items.csv", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def normal_data(seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return 100 + rng.normal(0, 1, (200, 3)), 100 + rng.normal(0, 1, 200)


def no_detail(cols) -> bool:
    return not any(str(c).endswith("_detail") for c in cols)


# v1
def test_v1_no_detail_column(items_header):
    assert no_detail(items_header)
    assert no_detail(item_status(*normal_data(), 5.0))
    assert no_detail(fail_evidence.STATUS_COLUMNS)


# v2
def test_v2_metrics_follow_status(items_header):
    assert METRIC_COLS == METRICS
    i = items_header.index(METRICS[0])          # 데이터 상태 묶음 (COLUMN_GROUPS)
    assert items_header[i:i + len(METRICS)] == METRICS
    assert set(LOG_COLS + STATUS_COLS + PRECISION_COLS) <= set(items_header)
    st = item_status(*normal_data(), 5.0)
    assert list(st) == STATUS_COLS


# v3
def test_v3_resolution_and_fixed_share_values():
    Y, z = normal_data()
    st = item_status(np.round(Y), np.round(z), 5.0)
    assert st["resolution_step"] == 1.0
    assert st["resolution_over_delta"] == pytest.approx(0.2)
    assert "분해능 부족" in st["status"].split(";")

    # Δ 없음: step 은 채우고 step/Δ 는 NaN, 분해능 부족 없음
    st = item_status(np.round(Y), np.round(z), float("nan"))
    assert st["resolution_step"] == 1.0 and math.isnan(st["resolution_over_delta"])
    st = item_status(np.round(Y), np.round(z), 0.0)
    assert st["resolution_step"] == 1.0 and math.isnan(st["resolution_over_delta"])

    # 분해능 부족이 안 붙어도 지표는 채움
    st = item_status(Y, z, 5.0)
    assert st["status"] == "정상"
    assert 0 < st["resolution_step"] < 0.5 and st["resolution_over_delta"] == st["resolution_step"] / 5.0
    assert st["fixed_share"] == pytest.approx(1 / 200)

    # 고유값 하나: step 계산 불가 → NaN, fixed_share = 1
    st = item_status(np.full((10, 3), 4.0), np.full(10, 4.0), 1.0)
    assert math.isnan(st["resolution_step"]) and math.isnan(st["resolution_over_delta"])
    assert st["fixed_share"] == 1.0 and "산포 0" in st["status"].split(";")

    # POR 회차 평균 R 은 10개 중 3개 같음, DOE z 는 10개 중 7개 같음 → 큰 쪽 0.7
    R = np.array([1.0, 1.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    Y = np.column_stack([R - 0.25, R + 0.25])
    z = np.array([9.0] * 7 + [1.0, 2.0, 3.0])
    st = item_status(Y, z, 100.0)
    assert st["fixed_share"] == pytest.approx(0.7)
    assert "산포 0" in st["status"].split(";")
    # 판정 제외 reason 의 '고정값 NN%' 는 fixed_share 와 같은 값 (정량 zone, step 0.25 ≥ 0.1 Δ 라 거친 데이터)
    why = excluded_reason(ExclusionFacts(Y, z, 1.0, 0.5, 1.5, 0.3, 0.1, float(np.median(R)), 1.0, 0.0, ()))
    assert f"고정값 {round(100 * st['fixed_share'])}%" in why


# v4: 수정 전 item_status 와 status 이름이 같은지. 합성 데이터.
def _cases() -> dict[str, tuple[np.ndarray, np.ndarray, float]]:
    Y, z = normal_data()
    Ys = Y.copy()
    Ys[:, 2] += 10.0
    rng = np.random.default_rng(3)
    size = 10 ** rng.uniform(0, 3, 200)
    Yj = size[:, None] * (1 + rng.normal(0, 0.3, (200, 3)) / np.sqrt(size)[:, None])
    return {
        "normal": (Y, z, 5.0),
        "shift_round": (np.round(Ys), np.round(z), 5.0),
        "shift_nan_delta": (np.round(Ys), np.round(z), float("nan")),
        "flat": (np.full((50, 3), 7.0), np.full(50, 7.0), 1.0),
        "size_jitter": (Yj, size.copy(), 1.0),
        "run_jitter": (Y, z, 0.5),
        "one_run": (Y[:, :1], z, 5.0),
    }


BEFORE_WOT = "5920b43"      # WO-T 직전 커밋 (숫자 문구 열이 있던 판)


@pytest.fixture(scope="module")
def old_item_status(tmp_path_factory):
    try:
        src = subprocess.run(["git", "show", f"{BEFORE_WOT}:por_doe_compare.py"], cwd=ROOT,
                             check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip(f"git 으로 {BEFORE_WOT} 를 읽을 수 없음")
    path = tmp_path_factory.mktemp("before_wot") / "por_doe_compare_before_wot.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("por_doe_compare_before_wot", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.item_status


def without_shape(status: str) -> str:
    """WO-U 분포 모양 status(log 후보·두 덩어리)를 뺀 status. 다 빠지면 정상."""
    names = [s for s in status.split(";") if s not in (ST_LOG_CANDIDATE, ST_BIMODAL, ST_OK)]
    return ";".join(names) or ST_OK


@pytest.mark.parametrize("name", list(_cases()))
def test_v4_status_names_unchanged(name, old_item_status):
    Y, z, d = _cases()[name]
    assert without_shape(item_status(Y, z, d)["status"]) == old_item_status(Y, z, d)["status"]


def test_v4_known_names():
    Y, z, d = _cases()["shift_round"]
    assert item_status(Y, z, d)["status"] == "조건 불안정;회차 흔들림;분해능 부족"
    assert item_status(*_cases()["normal"])["status"] == "정상"


# v5
def test_v5_fail_evidence_output(tmp_path: Path):
    src = fail_evidence.read_table(SYNTH_TSV)
    n = len(src)
    vals = {c: [f"{0.1 * (i + k):.4g}" if i % 2 else "" for i in range(n)] for k, c in enumerate(METRICS)}
    src = src.assign(status=["정상" if i % 2 else "분해능 부족;산포 0" for i in range(n)], **vals)
    inp = tmp_path / "in.tsv"
    src.to_csv(inp, sep="\t", index=False)

    assert fail_evidence.main(["--input", str(inp), "--out", str(tmp_path / "out")]) == 0
    out = pd.read_csv(tmp_path / "out" / "fail_evidence.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert no_detail(out.columns)
    cols = list(out.columns)
    i = cols.index("status")
    want = [c for c in METRICS if c != "por_gap_over_delta"]      # 이 파일이 따로 계산하는 열
    assert cols[i + 1:i + 1 + len(want)] == want
    assert cols[-len(PRECISION_COLS):] == PRECISION_COLS
    for c in ("resolution_step", "resolution_over_delta", "fixed_share", "run_jitter_pct"):
        assert out[c].tolist() == vals[c]
