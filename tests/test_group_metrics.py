"""group_summary.py: 그룹 분할 그림(compare_metrics 사용). 합성 데이터(tests/data/compare_ba_*.tsv)만 사용."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import compare_metrics  # noqa: E402
import group_summary  # noqa: E402
from compare_before_after import main as compare_main  # noqa: E402

DATA = Path(__file__).parent / "data"
BEFORE = DATA / "compare_ba_before.tsv"
AFTER = DATA / "compare_ba_after.tsv"
OLD_PNGS = ("ratio_hist.png", "density_die.png", "group_panel.png", "stability_panel.png")
# 모든 ITEM(공통 A1~A5, 기존에만 B1, 개선에만 C1)을 덮는다
GROUPS = {"SYNTH_A1": "G1", "SYNTH_A2": "G1", "SYNTH_A3": "G2", "SYNTH_A4": "G2", "SYNTH_A5": "G2",
          "SYNTH_B1": "G1", "SYNTH_C1": "G2"}


@pytest.fixture
def cmp_dir(tmp_path):
    return tmp_path / "cmp"


def _run(monkeypatch, cmp_dir: Path, out: Path, groups: dict) -> Path:
    """그룹 파일로 compare 를 다시 돌리고 (그룹은 compare.csv 의 group 열) group_summary 를 out 에 쓴다."""
    gfile = out.parent / f"{out.name}_groups.csv"
    gfile.write_text("ITEM,group\n" + "".join(f"{k},{v}\n" for k, v in groups.items()), encoding="utf-8")
    assert compare_main(["compare", str(BEFORE), str(AFTER), "-o", str(cmp_dir), "--groups", str(gfile)]) == 0
    group_summary.main(["--compare", str(cmp_dir / "compare.csv"), "--out", str(out)])
    return out


def test_old_figures_gone_new_figures_written(tmp_path, monkeypatch, cmp_dir):
    out = _run(monkeypatch, cmp_dir, tmp_path / "gs", GROUPS)
    for name in OLD_PNGS:
        assert not (out / name).exists()
    assert (out / "sigma_die_ratio.png").is_file()
    assert (out / "stability_sigma_die_pct.png").is_file()
    for g in ("G1", "G2"):
        assert (out / g / "sigma_die_ratio.png").is_file()
    for csv in ("group_summary.csv", "verdict_by_group.csv", "stability_by_group.csv"):
        assert (out / csv).is_file()


def test_overall_stability_matches_compare(tmp_path, monkeypatch, cmp_dir):
    out = _run(monkeypatch, cmp_dir, tmp_path / "gs", GROUPS)
    overall = pd.read_csv(cmp_dir / "stability_overall.csv", encoding="utf-8-sig")
    st = pd.read_csv(out / "stability_by_group.csv", encoding="utf-8-sig")
    st = st[st["그룹"] == "전체"].reset_index(drop=True)
    common = [c for c in overall.columns if c in st.columns]
    assert len(common) == len(overall.columns)
    pd.testing.assert_frame_equal(overall[common], st[common], check_dtype=False)


def test_safe_name_collision_gets_suffix(tmp_path, monkeypatch, cmp_dir):
    groups = {k: ("G 1" if v == "G1" else "G/1") for k, v in GROUPS.items()}
    assert compare_metrics.safe_group_name("G 1") == compare_metrics.safe_group_name("G/1") == "G_1"
    out = _run(monkeypatch, cmp_dir, tmp_path / "gs", groups)
    dirs = pd.read_csv(out / "group_dirs.csv", encoding="utf-8-sig")
    assert dict(zip(dirs["그룹"], dirs["폴더"])) == {"G 1": "G_1", "G/1": "G_1_2"}
    assert (out / "G_1" / "sigma_die_ratio.png").is_file()
    assert (out / "G_1_2" / "sigma_die_ratio.png").is_file()


def test_rerun_removes_own_outputs_keeps_user_files(tmp_path, monkeypatch, cmp_dir):
    out = tmp_path / "gs"
    first = dict(GROUPS, SYNTH_A1="OLD")
    _run(monkeypatch, cmp_dir, out, first)
    assert (out / "OLD" / "sigma_die_ratio.png").is_file()
    (out / "ratio_hist.png").write_bytes(b"old")  # 예전 버전이 남긴 그림
    (out / "note.txt").write_text("keep", encoding="utf-8")
    (out / "G1" / "memo.txt").write_text("keep", encoding="utf-8")

    _run(monkeypatch, cmp_dir, out, GROUPS)
    assert not (out / "ratio_hist.png").exists()
    assert not (out / "OLD").exists()  # 자기 그림만 있던 폴더는 비어서 지워짐
    assert (out / "note.txt").read_text(encoding="utf-8") == "keep"
    assert (out / "G1" / "memo.txt").read_text(encoding="utf-8") == "keep"
    assert (out / "G1" / "sigma_die_ratio.png").is_file()
    dirs = pd.read_csv(out / "group_dirs.csv", encoding="utf-8-sig")
    assert "OLD" not in set(dirs["그룹"])
