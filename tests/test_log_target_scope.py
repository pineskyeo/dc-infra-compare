"""WO-U-A2: log 열 대상 확대(0 없고 부호 하나인 모든 ITEM), log 진단 대상(흔들림 status + verdict≠verdict_log),
sigma_run_clipped 열. 합성 데이터만, seed 고정."""
import math
import subprocess
import sys
import types
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import fail_evidence as fe  # noqa: E402
import log_compare as lc  # noqa: E402
import por_doe_compare as pdc  # noqa: E402
from por_doe_compare import LOG_COLS, V_EXCLUDED  # noqa: E402

R = 0.05
POR = ["POR1", "POR2", "POR3"]
LOG_NUM = [c for c in LOG_COLS if c not in ("verdict_log", "log_reason", "ci_half_over_delta", "below_linear_loq")]
JITTER = {pdc.ST_SIZE_JITTER, pdc.ST_SIZE_JITTER_POS}


def lognormal_data(seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    """die 200개, 크기 1e-12~1e-6, 크기와 무관한 곱셈 흔들림 (ρ≈0)."""
    rng = np.random.default_rng(seed)
    size = 10 ** rng.uniform(-12, -6, 200)
    return size[:, None] * 10 ** rng.normal(0, 0.01, (200, 3)), size * 10 ** rng.normal(0, 0.01, 200)


def size_jitter_data(seed: int = 12) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    size = 10 ** np.linspace(-12, -6, 40)
    half = np.linspace(0.4, 0.02, 40) * (1 + 0.1 * rng.random(40))
    return size[:, None] * 10 ** (half[:, None] * np.array([1.0, 0.0, -1.0])), size.copy()


def far_data(seed: int = 13) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return 100 + rng.normal(0, 1, (30, 3)), 101 + rng.normal(0, 1, 30)


def mixed_sign_data(seed: int = 14) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1, (30, 3)), rng.normal(0, 1, 30)


def zero_value_data() -> tuple[np.ndarray, np.ndarray]:
    Y, z = lognormal_data()
    Y[3, 1] = 0.0
    return Y, z


def no_run_shift_data(seed: int = 15) -> tuple[np.ndarray, np.ndarray]:
    """회차 공통 이동 0: die별 편차(행 합 0)를 ± 짝으로 넣어 회차별 편차 중앙값이 모두 0 → 뺀 값 < 0."""
    rng = np.random.default_rng(seed)
    e = rng.normal(0, 1, (20, 3))
    dev = e - e.mean(axis=1, keepdims=True)
    base = 50 + rng.normal(0, 3, 40)
    Y = base[:, None] + np.vstack([dev, -dev])
    return Y, base + rng.normal(0, 1, 40)


def run_shift_data(seed: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """회차 공통 이동 −5, 0, +5 (die 잡음 0.1) → 회차 분산이 die 잡음 몫보다 훨씬 큼."""
    rng = np.random.default_rng(seed)
    base = 50 + rng.normal(0, 3, 40)
    Y = base[:, None] + np.array([-5.0, 0.0, 5.0]) + rng.normal(0, 0.1, (40, 3))
    return Y, base + rng.normal(0, 0.1, 40)


def run_item(mod, Y: np.ndarray, z: np.ndarray) -> dict:
    g = pd.DataFrame(Y, columns=POR).assign(DOE=z)
    blank = pd.DataFrame(columns=["BLANK_ITEM"]).set_index("BLANK_ITEM")
    return mod.judge_item("IT", g, POR, {"IT": "A"}, R, {}, blank, {})[0]


def load_head_module() -> types.ModuleType:
    src = subprocess.run(["git", "show", "HEAD:por_doe_compare.py"], cwd=REPO, check=True,
                         capture_output=True, text=True).stdout
    name = "por_doe_compare_head_x3"
    mod = types.ModuleType(name)
    mod.__file__ = str(REPO / "por_doe_compare.py")
    sys.modules[name] = mod
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


def test_x1_lognormal_non_jitter_fills_log_columns():
    row = run_item(pdc, *lognormal_data())
    assert not JITTER & set(row["status"].split(";"))
    assert row["verdict_log"] in {"동등", "차이", "미결"}
    for c in LOG_NUM:
        assert np.isfinite(row[c]), c
    assert row["policy_margin_log"] == pytest.approx(math.log10(1 + R), rel=1e-12)
    assert row["log_reason"]


@pytest.mark.parametrize("data, why", [(zero_value_data, "0값 있음"), (mixed_sign_data, "부호 섞임")])
def test_x2_zero_or_mixed_sign_excluded(data, why):
    row = run_item(pdc, *data())
    assert row["verdict_log"] == V_EXCLUDED
    assert why in row["log_reason"]
    for c in LOG_NUM:
        assert math.isnan(row[c]), c


@pytest.mark.parametrize("data", [lognormal_data, size_jitter_data, far_data, mixed_sign_data, zero_value_data,
                                  no_run_shift_data, run_shift_data])
def test_x3_linear_verdict_unchanged_from_head(data):
    old = load_head_module()
    Y, z = data()
    a, b = run_item(pdc, Y, z), run_item(old, Y, z)
    for c in ("verdict", "reason", "zone", "delta", "sigma_die", "sigma_run", "center", "status"):
        va, vb = a[c], b[c]
        assert va == vb or (isinstance(vb, float) and math.isnan(va) and math.isnan(vb)), c


def test_x4_items_index_log_target_verdict_differs(tmp_path):
    rows = [  # ITEM, verdict, status, verdict_log
        ("B1", "차이", pdc.ST_OK, "동등"),          # 다름 → 대상
        ("B2", "미결", pdc.ST_OK, "미결"),          # 같음
        ("B3", "차이", pdc.ST_OK, V_EXCLUDED),      # verdict_log 판정 제외 → 아님
        ("B4", "미결", pdc.ST_OK, ""),              # verdict_log 빈칸 → 아님
        ("B5", "동등", pdc.ST_OK, "차이"),          # 다름 → 대상 (차이·미결 아니어도 폴더)
        ("B6", "동등", pdc.ST_OK, "동등"),          # 대상 아님, 폴더 없음
    ]
    path = tmp_path / "items.csv"
    pd.DataFrame([{"ITEM": i, "UNIT": "A", "verdict": v, "reason": "r", "status": s, "verdict_log": vl}
                  for i, v, s, vl in rows]).to_csv(path, index=False, encoding="utf-8-sig")
    out = tmp_path / "out"
    assert fe.main(["--input", str(path), "--out", str(out)]) == 0
    idx = pd.read_csv(out / fe.ITEMS_INDEX, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert dict(zip(idx["ID"], idx["log_target"])) == {
        "B1": "True", "B2": "False", "B3": "False", "B4": "False", "B5": "True"}
    assert bool(pdc.is_log_target(pdc.ST_OK, "차이", "동등"))
    assert not bool(pdc.is_log_target(pdc.ST_OK, "차이", np.nan))
    assert bool(pdc.is_log_target(pdc.ST_SIZE_JITTER_POS))


def test_x4b_log_compare_verdict_diff_target(tmp_path):
    path = tmp_path / "items.csv"
    pd.DataFrame([
        ["J1", pdc.ST_SIZE_JITTER, "동등", "동등", 0.5, 0.3],
        ["D1", pdc.ST_OK, "차이", "동등", 2.0, 0.8],
        ["N1", pdc.ST_OK, "차이", V_EXCLUDED, 2.0, 0.8],
        ["N2", pdc.ST_OK, "동등", "동등", 0.5, 0.4],
    ], columns=["ITEM", "status", "verdict", "verdict_log", lc.X_COL, lc.Y_COL]).to_csv(
        path, index=False, encoding="utf-8-sig")
    r = lc.run(path, tmp_path)
    t = pd.read_csv(tmp_path / lc.CSV_NAME, encoding="utf-8-sig")
    assert dict(zip(t["ITEM"], t["target_status"])) == {"J1": pdc.ST_SIZE_JITTER, "D1": lc.VERDICT_DIFF}
    assert r["n"] == 2 and r["changed"] == 1
    assert lc.VERDICT_DIFF in lc.MARKER and len(set(lc.MARKER.values())) == len(lc.MARKER)


def test_x5_no_run_shift_clipped_true():
    Y, z = no_run_shift_data()
    assert bool(pdc.sigma_run_clipped(Y))
    row = run_item(pdc, Y, z)
    assert bool(row["sigma_run_clipped"])
    assert row["sigma_run"] == 0.0


def test_x6_large_run_shift_clipped_false():
    Y, z = run_shift_data()
    row = run_item(pdc, Y, z)
    assert not bool(row["sigma_run_clipped"])
    assert row["sigma_run"] > 1


def test_x6b_not_computable_blank():
    assert math.isnan(pdc.sigma_run_clipped(np.ones((10, 1))))


def test_x7_column_right_after_sigma_run():
    row = run_item(pdc, *far_data())
    keys = list(row)
    assert keys[keys.index("sigma_run") + 1] == "sigma_run_clipped"
    assert "sigma_run_clipped" not in pdc.STATUS_COLS + pdc.LOG_COLS
