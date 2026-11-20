"""compare_metrics.py: 계산 함수와 지표별 그림. 합성 데이터만 사용."""
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import compare_metrics as cm  # noqa: E402


def small():
    return pd.DataFrame({
        "ID": ["a", "b", "c", "d", "e", "f"],
        "por_median_before": [10.0, 20.0, -5.0, 0.0, 10.0, 10.0],
        "por_median_after": [10.0, 20.0, -5.0, 4.0, 10.0, 10.0],
        "sigma_die_before": [2.0, 1.0, 1.0, 0.0, 3.0, 1.0],
        "sigma_die_after": [1.0, 2.0, 1.0, 1.0, 0.0, 4.0],
        "sigma_run_before": [0.0, 1.0, 2.0, 0.0, 1.0, 1.0],
        "sigma_run_after": [0.0, 0.5, 2.0, 1.0, np.nan, 3.0],
        "verdict_before": ["x"] * 6,
        "verdict_after": ["x"] * 6,
    })


def synth(n=300, seed=0, center=True):
    rng = np.random.default_rng(seed)
    sd_b = rng.lognormal(0, 0.5, n)
    sr_b = rng.lognormal(-1, 0.5, n)
    df = pd.DataFrame({
        "ID": [f"I{i}" for i in range(n)],
        "por_median_before": rng.uniform(50, 150, n),
        "por_median_after": rng.uniform(50, 150, n),
        "sigma_die_before": sd_b,
        "sigma_die_after": sd_b * rng.lognormal(-0.2, 0.3, n),
        "sigma_run_before": sr_b,
        "sigma_run_after": sr_b * rng.lognormal(-0.1, 0.3, n),
        "verdict_before": "x",
        "verdict_after": "x",
        "group": rng.choice(list("ABCDE"), n),
    })
    df.loc[:4, "sigma_run_after"] = 0.0
    df.loc[:2, "sigma_run_before"] = 0.0
    if center:
        df["center_delta_before"] = rng.normal(0, 1, n)
        df["center_delta_after"] = rng.normal(0, 0.6, n)
    return df


def test_with_pct_from_median_and_existing_column():
    df = small()
    df["sigma_run_pct_after"] = [9.0] * 6  # 있는 열은 그대로
    d = cm.with_pct(df)
    assert d.loc[0, "sigma_die_pct_before"] == pytest.approx(20.0)
    assert d.loc[2, "sigma_run_pct_before"] == pytest.approx(40.0)  # |por_median| 사용
    assert math.isnan(d.loc[3, "sigma_die_pct_before"])  # median 0 → NaN
    assert (d["sigma_run_pct_after"] == 9.0).all()
    assert d.loc[1, "meas_precision_pct_before"] == pytest.approx(100 * math.hypot(1, 1) / 20)
    assert "meas_precision_pct_before" not in df.columns  # 원본은 그대로


def test_stability_row_medians():
    d = cm.with_pct(small())
    r = cm.stability_row(d)
    assert r["ITEM 수"] == 6
    exp = np.median([20.0, 5.0, 20.0, 30.0, 10.0])  # d 의 NaN 제외
    assert r["기존 σ_die% 중앙값"] == round(exp, 3)
    assert r["기존 σ_run=0 %"] == round(100 * 2 / 6, 1)
    mp = [100 * math.hypot(2, 0) / 10, 100 * math.hypot(1, 1) / 20, 100 * math.hypot(1, 2) / 5,
          100 * math.hypot(3, 1) / 10, 100 * math.hypot(1, 1) / 10]
    assert r["기존 측정정밀도% 중앙값"] == round(float(np.median(mp)), 3)
    assert r["기존 측정정밀도% 25%"] == round(float(pd.Series(mp).quantile(0.25)), 3)


def test_ratio_and_counts():
    df = small()
    r = cm.ratio(df, "sigma_die_ratio")
    assert r.tolist()[:3] == [0.5, 2.0, 1.0]
    assert math.isnan(r[3]) and math.isnan(r[4])  # 기존 0, 개선 0 → 제외
    c = cm.ratio_counts(r)
    assert (c["improved"], c["worse"], c["same"], c["excluded"]) == (1, 2, 1, 2)
    assert c["median"] == pytest.approx(1.5)

    rr = cm.ratio(df, "sigma_run_ratio")
    c = cm.ratio_counts(rr)
    # a: 둘 다 0 / d: 기존 0 / e: 개선 NaN
    assert c["both_zero"] == 1
    assert c["excluded"] == 2
    assert (c["improved"], c["worse"], c["same"]) == (1, 1, 1)


def test_meas_precision_ratio_uses_pct():
    r = cm.ratio(small(), "meas_precision_ratio")
    assert r[1] == pytest.approx(math.hypot(2, 0.5) / math.hypot(1, 1))


def test_worst_items_order():
    w = cm.worst_items(small(), "sigma_die_ratio", top=10)
    assert list(w.columns) == ["ID", "before", "after", "ratio"]
    assert w["ID"].tolist() == ["f", "b"]
    assert w["ratio"].tolist() == [4.0, 2.0]
    assert len(cm.worst_items(small(), "sigma_die_ratio", top=1)) == 1


def test_safe_group_name():
    assert cm.safe_group_name("그룹 A/1") == "그룹_A_1"
    assert cm.safe_group_name("x-y_z") == "x-y_z"
    assert cm.safe_group_name("../..") == "_____"
    assert cm.safe_group_name("") == "_"
    assert cm.safe_group_name("  ") == "_"


def test_log_clip_counts():
    vals = list(range(1, 101)) + [0, -1, np.nan]
    v, (lo, hi), n_clip, n_ex = cm.log_clip(vals)
    assert n_ex == 3
    assert n_clip == 2  # 1 과 100 이 1–99% 밖
    assert len(v) == 100
    p1, p99 = np.percentile(np.arange(1, 101), [1, 99])
    assert v.min() == pytest.approx(p1) and v.max() == pytest.approx(p99)
    assert lo < p1 and hi > p99


def test_draw_all_writes_six(tmp_path):
    paths = cm.draw_all(synth(), tmp_path)
    names = sorted(p.name for p in paths)
    assert names == sorted(f"{n}.png" for n in cm.METRICS)
    assert len(names) == 6
    assert sorted(p.name for p in tmp_path.iterdir()) == names


def test_draw_all_skips_center_delta(tmp_path, capsys):
    paths = cm.draw_all(synth(center=False), tmp_path)
    assert len(paths) == 5
    assert not (tmp_path / "verdict_center_delta.png").exists()
    assert "verdict_center_delta" in capsys.readouterr().out


def test_plot_ratio_log_x(tmp_path, monkeypatch):
    seen = {}
    real_save = cm._save

    def spy(fig, path):
        seen["scale"] = fig.axes[0].get_xscale()
        return real_save(fig, path)

    monkeypatch.setattr(cm, "_save", spy)
    p = cm.plot_ratio(synth(), "sigma_die_ratio", tmp_path / "r.png")
    assert p.exists()
    assert seen["scale"] == "log"


def test_plot_ratio_hexbin_large(tmp_path):
    assert cm.plot_ratio(synth(n=2500), "sigma_run_ratio", tmp_path / "h.png").exists()


@pytest.mark.parametrize("n, metric", [(300, "sigma_die_ratio"), (2500, "sigma_run_ratio")])
def test_plot_ratio_scatter_has_numeric_log_ticks(tmp_path, monkeypatch, n, metric):
    seen = {}
    real_save = cm._save

    def spy(fig, path):
        seen["ax2"] = fig.axes[1]  # 오른쪽 산점도/hexbin 패널
        return real_save(fig, path)

    monkeypatch.setattr(cm, "_save", spy)
    cm.plot_ratio(synth(n=n), metric, tmp_path / "t.png")
    ax2 = seen["ax2"]
    assert ax2.get_xscale() == "log" and ax2.get_yscale() == "log"
    for axis in (ax2.xaxis, ax2.yaxis):
        labels = [t.get_text() for t in axis.get_ticklabels() if t.get_text()]
        assert len(labels) >= 2
        assert all("$" not in s for s in labels)  # mathtext 아님


def test_plot_verdict_clip_count_in_title(tmp_path, monkeypatch):
    df = synth()
    df.loc[0, "center_delta_after"] = 50.0
    df.loc[1, "center_delta_before"] = -50.0
    allv = np.concatenate([df["center_delta_before"].to_numpy(), df["center_delta_after"].to_numpy()])
    plo, phi = np.percentile(allv, [1, 99])
    n_clip = int(((allv < plo) | (allv > phi)).sum())
    assert n_clip >= 2
    seen = {}
    real_save = cm._save

    def spy(fig, path):
        seen["title"] = fig.axes[0].get_title()
        return real_save(fig, path)

    monkeypatch.setattr(cm, "_save", spy)
    cm.plot_verdict_center_delta(df, tmp_path / "v.png")
    assert f"1~99% 밖 경계로 붙임 {n_clip}" in seen["title"]


def test_plot_group_compare(tmp_path):
    df = synth()
    for m in ("sigma_die_ratio", "stability_meas_precision_pct", "verdict_center_delta"):
        assert cm.plot_group_compare(df, "group", m, tmp_path / f"{m}.png").exists()
