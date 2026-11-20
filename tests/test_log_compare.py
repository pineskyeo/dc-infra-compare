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
        ["H", "정상", "동등", "판정 제외", 0.1, 5.0],              # verdict_log 판정 제외는 대상 아님
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


FIT_COLS = COLS + ["log_fit", "decades"]


def fit_rows():
    # A·E: 같은 log_fit, 다른 target_status, 둘 다 안 바뀜.  A·D: 같은 log_fit·status, D 만 바뀜.
    return [
        ["A", NEG, "동등", "동등", 0.5, 0.3, 0.8, 2.5],
        ["B", POS, "차이", "동등", 2.0, 0.8, -0.5, 1.0],
        ["C", NEG, "동등", "동등", 1.0, 0.9, np.nan, np.nan],
        ["D", NEG, "동등", "미결", 0.4, 0.6, 0.8, 3.0],
        ["E", POS, "미결", "미결", 1.5, 3.0, 0.8, 0.7],
        ["H", "정상", "동등", "동등", 0.1, 5.0, 9.0, 9.0],   # 대상 아님 (norm 범위에 안 들어가야 함)
    ]


def write_fit_items(tmp_path, rows):
    p = tmp_path / "items.csv"
    pd.DataFrame(rows, columns=FIT_COLS).to_csv(p, index=False, encoding="utf-8-sig")
    return p


def run_capture(monkeypatch, p, out):
    figs = []
    monkeypatch.setattr(lc, "_save", lambda fig, path: figs.append(fig))
    r = lc.run(p, out)
    fig = figs[0]
    fig.canvas.draw()
    ax = fig.axes[0]
    by_item = {}
    xy = {(round(x, 9), round(y, 9)): it for it, x, y in
          pd.read_csv(out / "log_compare.csv", encoding="utf-8-sig")[["ITEM", lc.X_COL, lc.Y_COL]].itertuples(index=False)}
    for coll in ax.collections:
        for x, y in coll.get_offsets():
            by_item[xy[(round(float(x), 9), round(float(y), 9))]] = coll
    return r, fig, by_item


def test_csv_log_fit_decades_from_items(tmp_path):
    p = write_fit_items(tmp_path, fit_rows())
    lc.run(p, tmp_path)
    t = pd.read_csv(tmp_path / "log_compare.csv", encoding="utf-8-sig")
    assert list(t.columns)[-3:] == ["changed", "log_fit", "decades"]
    src = {r[0]: (r[6], r[7]) for r in fit_rows()}
    for it, lf, dec in t[["ITEM", "log_fit", "decades"]].itertuples(index=False):
        np.testing.assert_equal((lf, dec), src[it])


def test_csv_log_fit_decades_nan_when_missing(tmp_path):
    lc.run(write_items(tmp_path, sample_rows()), tmp_path)
    t = pd.read_csv(tmp_path / "log_compare.csv", encoding="utf-8-sig")
    assert t["log_fit"].isna().all() and t["decades"].isna().all()


def test_plot_color_is_log_fit_twoslope(tmp_path, monkeypatch):
    from matplotlib.colors import TwoSlopeNorm, to_rgba
    _, fig, by = run_capture(monkeypatch, write_fit_items(tmp_path, fit_rows()), tmp_path)
    for it in "ABDE":
        coll = by[it]
        assert coll.get_array() is not None
        assert coll.get_cmap().name == lc.CMAP
        n = coll.norm
        assert isinstance(n, TwoSlopeNorm)
        assert (n.vcenter, n.vmin, n.vmax) == (0.0, -0.8, 0.8)
    # NaN 점은 회색으로 따로 (컬러맵 없이)
    nan_coll = by["C"]
    assert nan_coll.get_array() is None
    assert all(nan_coll is not by[it] for it in "ABDE")
    assert np.allclose(nan_coll.get_facecolors()[0][:3], to_rgba(lc.C_NAN)[:3])
    # colorbar 라벨
    assert any(a.get_ylabel() == "log_fit" for a in fig.axes[1:])


def test_plot_marker_by_changed(tmp_path, monkeypatch):
    _, _, by = run_capture(monkeypatch, write_fit_items(tmp_path, fit_rows()), tmp_path)
    va = by["A"].get_paths()[0].vertices        # 같음
    vd = by["D"].get_paths()[0].vertices        # 바뀜
    assert va.shape != vd.shape or not np.allclose(va, vd)


def test_plot_target_status_by_edge_not_color(tmp_path, monkeypatch):
    _, _, by = run_capture(monkeypatch, write_fit_items(tmp_path, fit_rows()), tmp_path)
    a, e = by["A"], by["E"]
    assert a is not e
    assert np.allclose(a.get_facecolors()[0], e.get_facecolors()[0])
    sty = lambda c: (float(c.get_linewidths()[0]), float(c.get_sizes()[0]))
    assert sty(a) != sty(e)


def test_plot_fit_one_sided_or_all_nan(tmp_path, monkeypatch):
    rows = [r[:6] + [abs(r[6]) if r[6] == r[6] else r[6], r[7]] for r in fit_rows()]   # 양수만
    r, _, by = run_capture(monkeypatch, write_fit_items(tmp_path, rows), tmp_path / "pos")
    assert r["n"] == 5 and by["A"].norm.vmin < 0 < by["A"].norm.vmax
    rows = [r[:6] + [np.nan, np.nan] for r in fit_rows()]
    r, _, by = run_capture(monkeypatch, write_fit_items(tmp_path, rows), tmp_path / "nan")
    assert r["n"] == 5 and all(c.get_array() is None for c in by.values())
    rows = [r[:6] + [0.0, 1.0] for r in fit_rows()]
    r, _, by = run_capture(monkeypatch, write_fit_items(tmp_path, rows), tmp_path / "zero")
    assert (by["A"].norm.vmin, by["A"].norm.vmax) == (-lc.FIT_DEFAULT_RANGE, lc.FIT_DEFAULT_RANGE)


def test_legend_edge_labels_prefixed(tmp_path, monkeypatch):
    """target_status 테두리 범례 줄은 '테두리: ' 로 시작 (X 마커 = 판정 바뀜 과 구분). CSV 값은 그대로."""
    rows = sample_rows() + [["K", "정상", "동등", "차이", 0.3, 0.2]]      # verdict≠verdict_log 로만 대상
    _, fig, _ = run_capture(monkeypatch, write_items(tmp_path, rows), tmp_path)
    labels = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
    assert labels[0].startswith("판정 같음") and labels[1].startswith("판정 바뀜")
    assert labels[-1].startswith("log_fit 없음")        # sample_rows 엔 log_fit 열이 없음
    edge = labels[2:-1]
    assert edge == ["테두리: " + k for k in (lc.ST_SIZE_JITTER, lc.ST_SIZE_JITTER_POS, "둘 다", lc.VERDICT_DIFF)]
    ts = set(pd.read_csv(tmp_path / "log_compare.csv", encoding="utf-8-sig")["target_status"])
    assert lc.VERDICT_DIFF in ts and not any(str(s).startswith("테두리") for s in ts)


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
