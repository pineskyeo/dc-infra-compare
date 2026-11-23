"""WO-SP 1단계: DC_JOBS 병렬(pool_map)과 sigma_rep_log 벡터 경로. 값·출력 불변. 합성 데이터만."""
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import por_doe_compare as pdc

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "examples" / "make_por3_data.py"
COMPARE = ROOT / "por_doe_compare.py"


def square(x):
    return x * x


def sigma_rep_log_list(L: np.ndarray) -> float:
    """기존 리스트 경로 (WO-SP 이전 구현 그대로)."""
    sds = [float(np.std(v, ddof=1)) for v in (row[np.isfinite(row)] for row in L) if v.size >= 2]
    return float(np.median(sds)) if sds else np.nan


def test_dc_jobs_unset_is_cpu_count(monkeypatch):
    monkeypatch.delenv("DC_JOBS", raising=False)
    assert pdc.dc_jobs() == (os.cpu_count() or 1)


def test_dc_jobs_empty_is_cpu_count(monkeypatch):
    monkeypatch.setenv("DC_JOBS", "")
    assert pdc.dc_jobs() == (os.cpu_count() or 1)


@pytest.mark.parametrize("raw, want", [("1", 1), ("0", 1), ("-2", 1), ("abc", 1), ("3", 3)])
def test_dc_jobs_values(monkeypatch, raw, want):
    monkeypatch.setenv("DC_JOBS", raw)
    assert pdc.dc_jobs() == want


def test_pool_map_serial_equals_parallel_and_keeps_order():
    args = [(i,) for i in range(37, -1, -1)]
    serial = pdc.pool_map(square, args, jobs=1)
    assert serial == [i * i for i in range(37, -1, -1)]
    assert pdc.pool_map(square, args, jobs=2) == serial


def test_pool_map_empty_and_single():
    assert pdc.pool_map(square, [], jobs=4) == []
    assert pdc.pool_map(square, [(5,)], jobs=4) == [25]


def test_sigma_rep_log_vector_path_matches_list():
    rng = np.random.default_rng(3)
    L = rng.normal(-9, 0.5, (200, 3))
    assert np.isclose(pdc.sigma_rep_log(L), sigma_rep_log_list(L), rtol=1e-12, atol=0)


def test_sigma_rep_log_with_nan_matches_list():
    rng = np.random.default_rng(4)
    L = rng.normal(-9, 0.5, (50, 3))
    L[0, 1] = np.nan
    L[1, :2] = np.nan            # 유한값 1개 die 는 빠진다
    L[2, :] = -np.inf
    assert pdc.sigma_rep_log(L) == sigma_rep_log_list(L)


def test_sigma_rep_log_nan_cases():
    assert math.isnan(pdc.sigma_rep_log(np.ones((10, 1))))        # 회차 1개
    assert math.isnan(pdc.sigma_rep_log(np.empty((0, 3))))        # die 0개
    assert math.isnan(pdc.sigma_rep_log(np.full((5, 3), np.nan)))


def run_script(script: Path, args, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """test_run_all.run_script 와 같은 방식."""
    env = os.environ.copy()
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + old if old else "")
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, str(script), *[str(a) for a in args]],
                          cwd=ROOT, env=env, check=False, capture_output=True, text=True)


def test_main_outputs_same_for_jobs_1_and_2(tmp_path: Path):
    data = tmp_path / "por3"
    gen = run_script(GENERATOR, [data])
    assert gen.returncode == 0, gen.stderr
    outs = {}
    for jobs in ("1", "2"):
        out = tmp_path / f"out_j{jobs}"
        args = ["--por", data / "por_run1", "--por", data / "por_run2", "--por", data / "por_run3",
                "--doe", data / "doe", "--r", "0.05", "--level", data / "level.csv",
                "--blank", data / "blank", "--blank-map", data / "blank_map.csv", "--out", out]
        p = run_script(COMPARE, args, {"DC_JOBS": jobs})
        assert p.returncode == 0, p.stderr
        outs[jobs] = out
    for name in ("items.csv", "outlier_dies.csv"):
        assert (outs["1"] / name).read_bytes() == (outs["2"] / name).read_bytes(), name
    assert len(pd.read_csv(outs["1"] / "outlier_dies.csv")) > 0     # 튀는 die 경로도 지나갔는지


# ---------------------------------------------------------------- WO-SP 2단계: fail_evidence ITEM 병렬

FE_DIES = ["1_1", "2_2", "3_3", "4_4"]
FE_LOG_COLS = {"center": "0.5", "ci_low": "0.3", "ci_high": "0.7", "delta": "0.4",
               "center_log": "0.05", "ci_low_log": "0.01", "ci_high_log": "0.09", "delta_log": "0.1",
               "spearman_size_jitter": "-0.8", "spearman_size_jitter_log": "-0.1", "log_reason": ""}


def _fe_items():
    """(ITEM, verdict, status, verdict_log, 원데이터 있음). 차이·미결, log 대상, log 만(동등), 원데이터 없음, 판정 제외."""
    return [
        ("B1", "차이", pdc.ST_OK, "차이", True),
        ("B2", "미결", f"{pdc.ST_RUN_JITTER};{pdc.ST_UNSTABLE}", "미결", True),
        ("B3", "차이", pdc.ST_SIZE_JITTER, "동등", True),           # item_view + status + log_diag
        ("B4", "동등", f"{pdc.ST_OK};{pdc.ST_SIZE_JITTER_POS}", "동등", True),   # log 만
        ("B5", "미결", "", "미결", False),                             # raw.csv 머리줄만
        ("B6", "동등", pdc.ST_OK, "동등", True),                        # 폴더 없음
        ("B7", pdc.V_EXCLUDED, pdc.ST_OK, "", True),
        ("B8", "차이", pdc.ST_UNSTABLE, "차이", True),
        ("B9", "미결", pdc.ST_SIZE_JITTER, "미결", True),
    ]


def _fe_inputs(tmp_path: Path) -> list[str]:
    from infra_compare import MEASURE_COLS

    items = _fe_items()
    path = tmp_path / "items.csv"
    pd.DataFrame([{"ITEM": i, "UNIT": "A", "verdict": v, "reason": "r", "status": s, **FE_LOG_COLS, "verdict_log": vl}
                  for i, v, s, vl, _ in items]).to_csv(path, index=False, encoding="utf-8-sig")
    rng = np.random.default_rng(7)
    args = []
    for k, name in enumerate(("por1", "por2", "doe")):
        lines = ["#HeaderStart", "WAFERID=W1", "#HeaderEnd", "#MeasureDataStart", ",".join(MEASURE_COLS)]
        for n, (item, *_, has_raw) in enumerate(items):
            if not has_raw:
                continue
            for die in FE_DIES:
                v = 10.0 ** (n - 3) * (1 + 0.2 * k + rng.uniform(0, 0.3))
                row = dict.fromkeys(MEASURE_COLS, "")
                row.update(COORD_X_Y=die, ITEM=item, UNIT="[A]", DATA=repr(v))
                lines.append(",".join(row[c] for c in MEASURE_COLS))
        lines += ["#MeasureDataEnd", "[EOF]"]
        f = tmp_path / f"{name}.result"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        args += ["--doe" if name == "doe" else "--por", str(f)]
    blank = tmp_path / "blank.csv"
    blank.write_text("ITEM,SIGMA0\nB1,0.01\nB3,0.001\n", encoding="utf-8")
    return ["--input", str(path), *args, "--blank", str(blank),
            "--key", "WAFERID,COORD_X_Y,ITEM", "--encoding", "auto"]


def _tree_digest(root: Path) -> dict[str, str]:
    import hashlib
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_fail_evidence_outputs_same_for_jobs_1_and_2(tmp_path: Path, monkeypatch):
    import fail_evidence as fe

    args = _fe_inputs(tmp_path)
    digests = {}
    for jobs in ("1", "2"):
        monkeypatch.setenv("DC_JOBS", jobs)
        out = tmp_path / f"fe_j{jobs}"
        assert fe.main([*args, "--out", str(out)]) == 0
        digests[jobs] = _tree_digest(out)
    files = set(digests["1"])
    assert files == set(digests["2"])
    for name in ("fail_evidence.csv", "summary.txt", "forest.png", fe.ITEMS_INDEX):
        assert name in files, name
    assert sum(n.endswith(fe.ITEM_VIEW_PNG) for n in files) >= 4
    assert sum(n.endswith(fe.LOG_DIAG_PNG) for n in files) >= 3      # B3·B9(log 대상) + B4(log 만)
    assert any(n.endswith("raw.csv") and "B5" in n for n in files)
    assert digests["1"] == digests["2"]
    assert not fe._SHARED                                             # main 이 끝나면 비운다


def test_split_raw_matches_mask():
    import fail_evidence as fe

    raw = pd.DataFrame({"COORD_X_Y": ["a", "b", "c", "d", "e"], "ITEM": ["X", 7, "X", "Y", 7],
                        "POR1": [1.0, 2.0, 3.0, 4.0, 5.0], "n": [1, 2, 3, 4, 5]}, index=[10, 3, 8, 1, 0])
    parts = fe._split_raw(raw, ["X", "7", "Y", "Z"])
    for i in ("X", "7", "Y", "Z"):
        want = raw[raw["ITEM"].astype(str) == i]
        pd.testing.assert_frame_equal(parts[i], want)
        assert parts[i].to_csv(index=False) == want.to_csv(index=False)
