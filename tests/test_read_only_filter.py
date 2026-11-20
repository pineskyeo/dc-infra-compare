"""WO-SP2: read_dcnormal(items=...) 가 처음부터 지정 ITEM 줄만 읽어도 전체 읽기 후 거른 것과 같은지. 합성 데이터만."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fail_evidence as fe  # noqa: E402
import test_fail_evidence_items as tfe  # noqa: E402  (합성 items.csv·DCNORMAL 헬퍼 재사용)
from infra_compare import MEASURE_COLS, load_side, read_dcnormal  # noqa: E402


def _row(item: str, die: str, data: str, **kw) -> str:
    row = dict.fromkeys(MEASURE_COLS, "")
    row.update(COORD_X_Y=die, ITEM=item, UNIT="[V]", DATA=data, **kw)
    return ",".join(row[c] for c in MEASURE_COLS)


def _write(path: Path) -> Path:
    """헤더 블록 여러 값, 따옴표 줄, 열 수 틀린 줄, 숫자 아닌 DATA, ITEM 이름이 다른 칸에도 나오는 줄을 섞은 합성 파일."""
    lines = ["#FileFormatInformationStart", "FILEFORMAT=DCNORMAL", "#FileFormatInformationEnd",
             "#HeaderStart", 'LOTID="L0"', "WAFERID=W7", "EQPID=E1", "STARTDATETIME=2000/01/01 00:00:00",
             "#HeaderEnd", "#MeasureDataStart", ",".join(MEASURE_COLS)]
    for d in range(4):
        die = f"{d}_{d}"
        lines += [_row("P1", die, f"{1.5 + d}"), _row("P2", die, f"{-2.25 * d}"), _row("Q9", die, "3.0")]
    lines.append(_row("P1", "9_9", "NaNtext"))                       # 숫자 아닌 DATA
    lines.append(_row("Q9", "8_8", "4.0", POINT_NAME="P1"))          # 다른 칸에 지정 이름
    lines.append(_row("P2", "7_7", "5.0", POINT_NAME='"a,b"'))       # 따옴표 줄(지정 ITEM)
    lines.append(_row("Q9", "6_6", "6.0", POINT_NAME='"c,d"'))       # 따옴표 줄(다른 ITEM)
    lines.append("P1,1,2")                                           # 열 개수 틀림
    lines.append('"x,y",P1')                                         # 열 개수 틀림(따옴표)
    lines += ["#MeasureDataEnd", "[EOF]"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _filtered(df: pd.DataFrame, keep: set[str]) -> pd.DataFrame:
    return df[df["ITEM"].isin(keep)].reset_index(drop=True)


@pytest.mark.parametrize("keep", [{"P1"}, {"P1", "P2"}, {"P2", "Q9"}])
def test_items_equals_full_then_filter(tmp_path, keep, capsys):
    path = _write(tmp_path / "a.result")
    full = read_dcnormal(path, "auto")
    warn_full = capsys.readouterr().err
    got = read_dcnormal(path, "auto", items=keep)
    warn_got = capsys.readouterr().err
    assert len(got) > 0
    pd.testing.assert_frame_equal(got.reset_index(drop=True), _filtered(full, keep))
    assert warn_got == warn_full and "2개 제외" in warn_full           # 열 개수 경고는 전체 기준
    assert got["LOTID"].iloc[0] == "L0" and got["STARTDATETIME"].iloc[0] == "2000/01/01 00:00:00"


def test_items_none_same_as_default(tmp_path):
    path = _write(tmp_path / "a.result")
    pd.testing.assert_frame_equal(read_dcnormal(path, "auto", items=None), read_dcnormal(path, "auto"))
    pd.testing.assert_frame_equal(load_side([str(path)], "X", "auto", None), load_side([str(path)], "X", "auto"))


def test_load_side_items_equals_full_filter(tmp_path):
    a, b = _write(tmp_path / "a.result"), _write(tmp_path / "b.result")
    full = load_side([str(a), str(b)], "X", "auto")
    got = load_side([str(a), str(b)], "X", "auto", {"P2"})
    pd.testing.assert_frame_equal(got.reset_index(drop=True), _filtered(full, {"P2"}))


def test_unknown_items_give_empty_frame(tmp_path):
    path = _write(tmp_path / "a.result")
    full = read_dcnormal(path, "auto")
    got = read_dcnormal(path, "auto", items={"NOPE"})
    assert got.empty
    assert list(got.columns) == list(full.columns)
    assert got["DATA"].dtype == full["DATA"].dtype and got["LINE"].dtype == full["LINE"].dtype


def test_read_side_items_mixed_files_keeps_dtypes(tmp_path):
    """지정 ITEM 이 없는 파일이 섞여도 열·dtype 은 전체 읽기 후 거른 것과 같다."""
    a = _write(tmp_path / "a.result")
    b = tfe._dcnormal(tmp_path / "b.result", 0)                      # P1 없는 파일
    got = fe.read_side_items([str(a), str(b)], "POR1", "auto", ["P1"])
    full = load_side([str(a), str(b)], "POR1", "auto")
    pd.testing.assert_frame_equal(got, _filtered(full, {"P1"}))


def test_bad_header_still_raises(tmp_path):
    path = tmp_path / "bad.result"
    path.write_text("#MeasureDataStart\nA,B,C\n1,2,3\n#MeasureDataEnd\n", encoding="utf-8")
    with pytest.raises(ValueError, match="15열"):
        read_dcnormal(path, "auto", items={"A"})


def test_only_unknown_ids_error_unchanged(tmp_path, capsys):
    out = tmp_path / "out"
    rc = fe.main(["--input", str(tfe._anon_items_csv(tmp_path)), "--out", str(out), *tfe._raw_args(tmp_path),
                  "--only", "NOPE", "X99"])
    assert rc == 2
    assert "입력에 없는 ID: NOPE, X99" in capsys.readouterr().err


def test_only_raw_csv_same_as_full_read(tmp_path, monkeypatch):
    """--only 2 ITEM 의 raw.csv 가 전체 읽기 후 거른 경로(load_wide)와 같은 내용."""
    monkeypatch.setitem(tfe.VALUES, "A4", ([7.0, 8.0, 9.0], [7.1, 8.1, 9.1], [7.5, 8.5, 9.5]))
    raw_args = tfe._raw_args(tmp_path)
    out = tmp_path / "out"
    assert fe.main(["--input", str(tfe._anon_items_csv(tmp_path)), "--out", str(out), *raw_args,
                    "--only", "A4,X03"]) == 0
    a = fe.parse_args(["--input", "x", "--out", "y", *raw_args])
    want = fe.load_raw(a, ["A3", "A4"], only=False)
    for typ, item in (("동등", "A3"), (fe.item_type(tfe.ST_OK, tfe.V_EXCLUDED), "A4")):
        got = pd.read_csv(tfe._folder(out, typ, item) / "raw.csv", encoding="utf-8-sig")
        exp = want[want["ITEM"] == item].reset_index(drop=True)
        assert list(got.columns) == list(exp.columns)
        pd.testing.assert_frame_equal(got[["COORD_X_Y", "ITEM"]], exp[["COORD_X_Y", "ITEM"]].astype(str))
        for c in ("POR1", "POR2", "DOE", "d", "por_range"):
            assert got[c].tolist() == pytest.approx(exp[c].astype(float).tolist())
