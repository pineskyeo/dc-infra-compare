import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import log_compare as lc  # noqa: E402

NEG, POS = "작을수록 흔들림", "클수록 흔들림"
COLS = ["ITEM", "status", "verdict", "verdict_log", "ci_half_over_delta", "ci_half_over_delta_log"]


def write_items(tmp_path, rows):
    p = tmp_path / "items.csv"
    pd.DataFrame(rows, columns=COLS).to_csv(p, index=False, encoding="utf-8-sig")
    return p


def sample_rows():
    return [
        # 대상: 아래(y<x) 3, 위(y>x) 2
        ["A", NEG, "동등", "동등", 0.5, 0.3],
        ["B", f"정상;{POS}", "차이", "동등", 2.0, 0.8],          # changed
        ["C", f"{NEG}; {POS}", "미결", "미결", 1.0, 0.9],         # 두 사유
        ["D", NEG, "동등", "미결", 0.4, 0.6],                    # changed
        ["E", POS, "미결", "미결", 1.5, 3.0],
        # 대상이지만 제외 (NaN, ≤0)
        ["F", NEG, "동등", "동등", np.nan, 0.5],
        ["G", POS, "동등", "차이", 0.5, 0.0],
        # 대상 아님
        ["H", "정상", "동등", "차이", 0.1, 5.0],
        ["I", "회차 흔들림", "동등", "동등", 0.2, 0.1],
        ["J", np.nan, "동등", "동등", 0.2, 0.1],
    ]


def test_outputs_and_counts(tmp_path):
    p = write_items(tmp_path, sample_rows())
    out = tmp_path / "out"
    r = lc.run(p, out)
    assert (out / "log_compare.png").stat().st_size > 0
    assert (out / "log_compare.csv").exists()
    assert r["n"] == 5
    assert r["below"] == 3
    assert r["above"] == 2
    assert r["changed"] == 2
    assert r["excluded"] == 2


def test_csv_columns_and_target_status(tmp_path):
    p = write_items(tmp_path, sample_rows())
    lc.run(p, tmp_path)
    t = pd.read_csv(tmp_path / "log_compare.csv", encoding="utf-8-sig")
    assert list(t.columns) == lc.CSV_COLS
    assert set(t["ITEM"]) == set("ABCDEFG")
    ts = dict(zip(t["ITEM"], t["target_status"]))
    assert ts["A"] == NEG
    assert ts["B"] == POS
    assert ts["C"] == f"{NEG}; {POS}"
    ch = dict(zip(t["ITEM"], t["changed"]))
    assert ch["B"] and ch["D"] and ch["G"]
    assert not ch["A"] and not ch["C"]


def test_nan_rows_excluded_from_plot_only(tmp_path):
    rows = [["A", NEG, "동등", "동등", 0.5, 0.3],
            ["B", NEG, "동등", "동등", np.nan, 0.3],
            ["C", POS, "동등", "동등", 0.5, -1.0]]
    r = lc.run(write_items(tmp_path, rows), tmp_path)
    assert (r["n"], r["below"], r["above"], r["excluded"]) == (1, 1, 0, 2)
    assert len(pd.read_csv(tmp_path / "log_compare.csv", encoding="utf-8-sig")) == 3


def test_no_targets(tmp_path):
    rows = [["H", "정상", "동등", "동등", 0.1, 0.2]]
    r = lc.run(write_items(tmp_path, rows), tmp_path)
    assert r == {"n": 0, "below": 0, "above": 0, "changed": 0, "excluded": 0}
    assert (tmp_path / "log_compare.png").stat().st_size > 0
    t = pd.read_csv(tmp_path / "log_compare.csv", encoding="utf-8-sig")
    assert list(t.columns) == lc.CSV_COLS
    assert t.empty


def test_default_out_and_keeps_other_files(tmp_path):
    p = write_items(tmp_path, sample_rows())
    other = tmp_path / "summary.png"
    other.write_bytes(b"keep")
    (tmp_path / "log_compare.csv").write_text("old", encoding="utf-8")
    lc.main([str(p)])
    assert other.read_bytes() == b"keep"
    assert p.exists()
    assert (tmp_path / "log_compare.png").exists()
    assert (tmp_path / "log_compare.csv").read_text(encoding="utf-8-sig").startswith("ITEM,")
