"""열 사전(columns_doc.py, docs/columns/*.csv): 모든 명령이 쓰는 모든 CSV 열이 사전에 있다. 패턴과 BOM 읽기."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import columns_doc
from columns_doc import ColumnDoc, OUTPUTS

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd: Path = ROOT) -> None:
    env = {**os.environ, "OMP_NUM_THREADS": "1",
           "PYTHONPATH": str(ROOT) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")}
    proc = subprocess.run([sys.executable, "-B", *map(str, args)], cwd=cwd, env=env, capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 0, f"{args}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"


def make_outputs(base: Path) -> list[Path]:
    """합성 데이터로 dcc judge·item·classes·group --before 와 run_all --before --groups 를 돌린다. 출력 폴더 목록."""
    data = base / "por3"
    run(ROOT / "examples" / "make_por3_data.py", data)
    (data / "groups.csv").write_text("ITEM,group\nVT_SAME,VT\nVT_SHIFT,VT\nVT_NOISY_DOE,VT\nRON_CONTACT,RON\n"
                                     "IOFF_FLOOR,IOFF\nIOFF_LEAK,IOFF\n", encoding="utf-8")
    (data / "scales.csv").write_text("group,scale\nVT,log\nRON,linear\n", encoding="utf-8")
    (base / "combos.ini").write_text(f"""\
[A1]
por = {data / "por_run1"}
      {data / "por_run2"}
      {data / "por_run3"}
doe = {data / "doe"}
level = {data / "level.csv"}
blank = {data / "blank"}
blank_map = {data / "blank_map.csv"}
groups = {data / "groups.csv"}
scales = {data / "scales.csv"}
out = {base / "dcc"}
""", encoding="utf-8")
    config = ["--config", base / "combos.ini"]
    run(ROOT / "dcc.py", "judge", "A1", *config)
    run(ROOT / "raw_stats.py", *(a for i in (1, 2, 3) for a in ("--por", data / f"por_run{i}")),
        "--doe", data / "doe", "--level", data / "level.csv", "--blank", data / "blank",
        "--blank-map", data / "blank_map.csv", "--out", base / "dcc" / "A1")
    run(ROOT / "report_v2.py", base / "dcc" / "A1")
    run(ROOT / "dcc.py", "item", "A1", "VT_SHIFT,VT_SAME,IOFF_LEAK,VT_NOISY_DOE", *config)
    run(ROOT / "dcc.py", "classes", "A1", *config)
    shutil.copytree(base / "dcc" / "A1", base / "before_run")     # stability/group_levels.csv 도 같이 (그룹 × LEVEL)
    before = base / "before_run" / "items.csv"
    run(ROOT / "dcc.py", "group", "A1", "--before", before, *config)
    run(ROOT / "review.py", "--input", base / "dcc" / "A1" / "items.csv", "--out", base / "dcc" / "A1",
        *(a for i in (1, 2, 3) for a in ("--por", data / f"por_run{i}")), "--doe", data / "doe")
    run(ROOT / "run_all.py", "--por", data / "por_run1", "--por", data / "por_run2", "--por", data / "por_run3",
        "--doe", data / "doe", "--level", data / "level.csv", "--blank", data / "blank",
        "--blank-map", data / "blank_map.csv", "--groups", data / "groups.csv", "--before", before,
        "--out", base / "run_all")
    return [base / "dcc" / "A1", base / "run_all"]


@pytest.fixture(scope="module")
def out_dirs(tmp_path_factory) -> list[Path]:
    return make_outputs(tmp_path_factory.mktemp("columns"))


def test_every_output_kind_is_produced(out_dirs):
    kinds = {k for d in out_dirs for k in columns_doc.produced(d)}
    assert kinds == {o.kind for o in OUTPUTS}


def test_every_produced_column_is_documented(out_dirs):
    for d in out_dirs:
        assert columns_doc.undocumented(d) == {}, f"{d}: python columns_doc.py --add {d} 로 행을 더하고 설명을 채우세요"


def test_every_doc_file_exists_with_header():
    for o in OUTPUTS:
        path = columns_doc.DOCS_DIR / f"{o.doc}.csv"
        assert path.read_bytes().startswith(b"\xef\xbb\xbfcolumn,"), path
        assert columns_doc.read_doc(path), path


def test_new_column_is_reported_as_undocumented(out_dirs, tmp_path):
    out = tmp_path / "out"
    shutil.copytree(out_dirs[0], out)
    text = (out / "items.csv").read_text(encoding="utf-8-sig").split("\n", 1)
    (out / "items.csv").write_text(text[0] + ",new_metric\n" + text[1], encoding="utf-8-sig")
    assert columns_doc.undocumented(out) == {"items.csv": ["new_metric"]}


def test_numbered_pattern():
    doc = ColumnDoc("POR{k}_mean")
    assert doc.matches("POR1_mean") and doc.matches("POR12_mean")
    assert not doc.matches("POR_mean") and not doc.matches("PORx_mean") and not doc.matches("POR1_mean2")
    assert ColumnDoc("{verdict}→{verdict}").matches("판정 제외→동등")
    assert not ColumnDoc("{verdict}→{verdict}").matches("동등→좋음")
    assert ColumnDoc("a.b(c)").matches("a.b(c)") and not ColumnDoc("a.b(c)").matches("axb(c)")


def test_doc_for_prefers_exact_row_and_falls_back_to_pattern():
    assert columns_doc.doc_for("items.csv", "POR3_mean").column == "POR{k}_mean"
    assert columns_doc.doc_for("items.csv", "verdict").column == "verdict"
    assert columns_doc.doc_for("items/*/summary.csv", "verdict").column == "verdict"
    assert columns_doc.doc_for("items.csv", "no_such_column") is None
    with pytest.raises(KeyError):
        columns_doc.doc_for("nope.csv", "verdict")


def test_reads_bom_and_excel_cp949(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_bytes("column,쉬운이름,뜻,수식,볼것\r\ncenter,이동량,\"DOE − POR, 중앙값\",,\r\n".encode("utf-8-sig"))
    cp = tmp_path / "cp.csv"
    cp.write_bytes("column,쉬운이름,뜻,수식,볼것\r\ncenter,이동량\r\n".encode("cp949"))
    assert columns_doc.read_doc(bom) == [ColumnDoc("center", "이동량", "DOE − POR, 중앙값")]
    assert columns_doc.read_doc(cp) == [ColumnDoc("center", "이동량")]
    bad = tmp_path / "bad.csv"
    bad.write_text("col,name\n", encoding="utf-8")
    with pytest.raises(ValueError, match="첫 줄"):
        columns_doc.read_doc(bad)


def test_write_then_read_round_trip(tmp_path):
    docs = [ColumnDoc("a", "에이", "뜻, 쉼표", "x = \"y\"", "볼 것\n두 줄")]
    path = tmp_path / "x.csv"
    columns_doc.write_doc(path, docs)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert columns_doc.read_doc(path) == docs
