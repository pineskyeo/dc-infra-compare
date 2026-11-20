"""같은 --out에 다시 돌려도 지난 실행의 그림이 남지 않고, 사용자 파일은 그대로인지 확인한다(합성 데이터)."""
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import compare_before_after as cba  # noqa: E402
import fail_evidence as fe  # noqa: E402
from plot_verdicts import plot_summary  # noqa: E402

DATA = ROOT / "tests" / "data"


def _subset_tsv(src: Path, dst: Path, keep_ids) -> Path:
    df = pd.read_csv(src, sep="\t", dtype=str, keep_default_na=False, comment="#")
    df[df["ID"].isin(set(keep_ids))].to_csv(dst, sep="\t", index=False)
    return dst


def _plotted_ids(path: Path) -> list[str]:
    table = fe.evidence_table(fe.read_table(path))
    rows = table[table["judgement"].isin(fe.PLOT_ORDER)]
    return [r["ID"] for r in rows.to_dict("records") if math.isfinite(r["delta_pct"])]


def test_fail_evidence_rerun_leaves_only_current_item_pngs(tmp_path):
    src = DATA / "fail_evidence_synth.tsv"
    first_ids = _plotted_ids(src)
    assert len(first_ids) >= 3
    out = tmp_path / "out"
    assert fe.main(["--input", str(src), "--out", str(out)]) == 0
    assert len(list((out / "items").glob("*.png"))) == len(first_ids)
    (out / "notes.txt").write_text("user", encoding="utf-8")
    (out / "items" / "notes.txt").write_text("user", encoding="utf-8")

    small = _subset_tsv(src, tmp_path / "small.tsv", first_ids[:2])
    second_ids = _plotted_ids(small)
    assert 0 < len(second_ids) < len(first_ids)
    assert fe.main(["--input", str(small), "--out", str(out)]) == 0
    assert sorted(p.stem for p in (out / "items").glob("*.png")) == sorted(fe.safe_name(i) for i in second_ids)
    assert (out / "forest.png").is_file()
    assert (out / "notes.txt").is_file() and (out / "items" / "notes.txt").is_file()


def _summary_frame(n: int) -> pd.DataFrame:
    return pd.DataFrame({
        "ITEM": [f"Q{i:02d}" for i in range(n)],
        "zone": ["정량"] * n,
        "verdict": ["동등"] * n,
        "reason": ["90% 신뢰구간이 ±Δ 안"] * n,
        "center": [0.1] * n,
        "ci_low": [-0.2] * n,
        "ci_high": [0.3] * n,
        "delta": [1.0] * n,
    })


def test_plot_summary_rerun_removes_extra_pages(tmp_path):
    out = tmp_path / "plots"
    first = plot_summary(_summary_frame(5), out, dpi=40, per_page=2)
    assert len(first) == 3
    (out / "notes.txt").write_text("user", encoding="utf-8")

    second = plot_summary(_summary_frame(2), out, dpi=40, per_page=2)
    assert [p.name for p in second] == ["summary_001.png"]
    assert sorted(p.name for p in out.glob("summary_*.png")) == ["summary_001.png"]
    assert (out / "notes.txt").is_file()


def test_compare_evidence_rerun_leaves_only_current_strips(tmp_path):
    src = DATA / "compare_ba_before.tsv"
    out = tmp_path / "ev"
    ev1 = cba.run_evidence(str(src), str(out))
    first_ids = list(dict.fromkeys(ev1["ID"]))
    assert len(first_ids) >= 3
    assert len(list(out.glob("strip_*.png"))) == len(first_ids)
    (out / "notes.txt").write_text("user", encoding="utf-8")

    small = _subset_tsv(src, tmp_path / "small.tsv", first_ids[:2])
    ev2 = cba.run_evidence(str(small), str(out))
    second_ids = set(ev2["ID"])
    assert 0 < len(second_ids) < len(first_ids)
    assert len(list(out.glob("strip_*.png"))) == len(second_ids)
    assert (out / "notes.txt").is_file()


def test_compare_rerun_removes_old_named_outputs(tmp_path):
    out = tmp_path / "cmp"
    out.mkdir()
    old = ("sigma_die_paired.png", "sigma_run_paired.png", "scatter_before_after.png")
    for name in old:
        (out / name).write_bytes(b"old")
    (out / "notes.txt").write_text("user", encoding="utf-8")

    cba.run_compare(str(DATA / "compare_ba_before.tsv"), str(DATA / "compare_ba_after.tsv"), str(out))
    assert not any((out / name).exists() for name in old)
    assert (out / "sigma_die_ratio.png").is_file()
    assert (out / "notes.txt").is_file()
