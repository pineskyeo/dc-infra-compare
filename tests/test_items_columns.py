"""items.csv 열: ID 맨 앞, 판정 묶음 다음, COLUMN_GROUPS 순서, 뺀 열 없음. 옛 items.csv(ID 없음, 뺀 열 있음)도 계속 읽힌다."""
import csv
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from por_doe_compare import COLUMN_GROUPS, anon_ids, order_columns

ROOT = Path(__file__).resolve().parents[1]
REMOVED = ()
OLD_FIRST = ["ITEM", "UNIT", "zone", "verdict", "reason"]


def run(script: str, *args) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, str(ROOT / script), *map(str, args)], cwd=ROOT, env=env,
                          check=True, capture_output=True, text=True)


def header(path: Path) -> list[str]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


@pytest.fixture(scope="module")
def judged(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("cols")
    data = base / "por3"
    run("examples/make_por3_data.py", data)
    out = base / "new"
    run("por_doe_compare.py", "--por", data / "por_run1", "--por", data / "por_run2", "--por", data / "por_run3",
        "--doe", data / "doe", "--level", data / "level.csv", "--blank", data / "blank",
        "--blank-map", data / "blank_map.csv", "--out", out)
    return out / "items.csv"


def old_format(items: Path, dest: Path) -> Path:
    """ID 없이 ITEM 이 맨 앞이고 뺀 열이 아직 있는, 이 변경 전 모양의 items.csv."""
    df = pd.read_csv(items, dtype=str, keep_default_na=False).drop(columns="ID")
    for c in REMOVED:
        df[c] = "0.1"
    df = df[OLD_FIRST + [c for c in df.columns if c not in OLD_FIRST]]
    dest.mkdir(parents=True, exist_ok=True)
    df.to_csv(dest / "items.csv", index=False, encoding="utf-8-sig")
    return dest / "items.csv"


def test_header_is_id_then_verdicts_then_groups(judged: Path):
    cols = header(judged)
    assert cols[:3] == ["ID", "ITEM", "UNIT"]
    verdicts = dict(COLUMN_GROUPS)["verdicts"]
    assert cols[3:3 + len(verdicts)] == list(verdicts)
    assert cols == order_columns(cols)
    assert len(cols) == len(set(cols))
    listed = {e for _, g in COLUMN_GROUPS for e in g if isinstance(e, str)}
    assert [c for c in cols if c not in listed and not c.endswith("_mean")] == []


def test_unlisted_column_goes_last_in_original_order():
    assert order_columns(["zz", "ITEM", "POR2_mean", "aa", "POR1_mean", "ID"]) == \
        ["ID", "ITEM", "POR2_mean", "POR1_mean", "zz", "aa"]


def test_removed_columns_absent(judged: Path):
    assert set(REMOVED).isdisjoint(header(judged))


def test_id_equals_summarize_and_is_not_doubled(judged: Path, tmp_path: Path):
    before = pd.read_csv(judged, dtype=str, keep_default_na=False)
    assert before["ID"].tolist() == anon_ids(before["ITEM"])[1].tolist()
    copy = tmp_path / "items.csv"
    copy.write_bytes(judged.read_bytes())
    run("summarize.py", copy)
    after = pd.read_csv(copy, dtype=str, keep_default_na=False)
    assert header(copy) == header(judged)
    assert after["ID"].tolist() == before["ID"].tolist()
    mp = pd.read_csv(tmp_path / "item_map.csv", dtype=str)
    assert dict(zip(mp["ITEM"], mp["ID"])) == dict(zip(before["ITEM"], before["ID"]))


def test_summarize_old_file_gets_same_id_and_map(judged: Path, tmp_path: Path):
    old = old_format(judged, tmp_path / "old")
    run("summarize.py", old)
    got = pd.read_csv(old, dtype=str, keep_default_na=False)
    assert list(got.columns[:2]) == ["ID", "ITEM"]
    assert list(got.columns).count("ID") == 1
    new = pd.read_csv(judged, dtype=str, keep_default_na=False)
    assert dict(zip(got["ITEM"], got["ID"])) == dict(zip(new["ITEM"], new["ID"]))


def test_fail_evidence_same_for_old_and_new(judged: Path, tmp_path: Path):
    old = old_format(judged, tmp_path / "old")
    run("fail_evidence.py", "--input", judged, "--out", tmp_path / "fe_new")
    run("fail_evidence.py", "--input", old, "--out", tmp_path / "fe_old")
    fe_new = pd.read_csv(tmp_path / "fe_new" / "fail_evidence.csv", dtype=str, keep_default_na=False)
    fe_old = pd.read_csv(tmp_path / "fe_old" / "fail_evidence.csv", dtype=str, keep_default_na=False)
    assert len(fe_new) > 0
    items = pd.read_csv(judged, dtype=str, keep_default_na=False)
    assert fe_new["ID"].tolist() == fe_new["ITEM"].map(dict(zip(items["ITEM"], items["ID"]))).tolist()
    pd.testing.assert_frame_equal(fe_new.drop(columns="ID"), fe_old)


def test_plot_verdicts_summary_reads_old_and_new(judged: Path, tmp_path: Path):
    old = old_format(judged, tmp_path / "old")
    for name, src in (("new", judged), ("old", old)):
        run("plot_verdicts.py", "--items-csv", src, "--summary", "--out", tmp_path / f"plots_{name}")
    files = lambda d: sorted(p.name for p in d.iterdir())
    assert files(tmp_path / "plots_new") == files(tmp_path / "plots_old") != []


def test_compare_before_after_matches_old_with_new(judged: Path, tmp_path: Path):
    old = old_format(judged, tmp_path / "old")
    run("compare_before_after.py", "compare", old, judged, "-o", tmp_path / "cmp")
    c = pd.read_csv(tmp_path / "cmp" / "compare.csv", dtype=str, keep_default_na=False)
    items = pd.read_csv(judged, dtype=str, keep_default_na=False)
    assert sorted(c["ITEM"]) == sorted(items["ITEM"])
    assert dict(zip(c["ITEM"], c["ID"])) == dict(zip(items["ITEM"], items["ID"]))
    assert set(c["presence"]) == {"matched"}
