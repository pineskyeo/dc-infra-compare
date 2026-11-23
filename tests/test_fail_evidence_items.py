"""WO-P (a)(b): fail_evidence ITEM별 폴더(items/<유형>_<ID>/summary.csv·raw.csv·item_view.png·evidence.csv), items_index.csv, 표식 기반 지우기. 합성 데이터만."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fail_evidence as fe  # noqa: E402
import item_view  # noqa: E402
from compare_metrics import safe_group_name  # noqa: E402
from infra_compare import MEASURE_COLS  # noqa: E402
from por_doe_compare import ST_OK, ST_RUN_JITTER, ST_SIZE_JITTER, ST_SIZE_JITTER_POS, ST_UNSTABLE, V_EXCLUDED  # noqa: E402

ITEMS = [
    # ITEM, verdict, status
    ("A1", "차이", ST_OK),
    ("A2", "미결", f"{ST_RUN_JITTER};{ST_UNSTABLE}"),
    ("A3", "동등", ST_OK),
    ("A4", V_EXCLUDED, ST_OK),
    ("A5", "미결", ""),
]
DIES = ["1_1", "2_2", "3_3"]
# 회차별 die 값: ITEM -> (POR1, POR2, DOE) 각 die 순서
VALUES = {
    "A1": ([1.0, 2.0, 3.0], [1.2, 2.2, 3.4], [2.0, 3.0, 4.0]),
    "A2": ([10.0, 11.0, 12.0], [10.5, 11.0, 12.5], [10.0, 10.0, 10.0]),
    "A3": ([5.0, 5.0, 5.0], [5.0, 5.0, 5.0], [5.0, 5.0, 5.0]),
}


def _items_csv(tmp_path: Path) -> Path:
    path = tmp_path / "items.csv"
    pd.DataFrame([{"ITEM": i, "UNIT": "A", "verdict": v, "reason": "r", "status": s, "extra_col": f"x{i}"}
                  for i, v, s in ITEMS]).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _dcnormal(path: Path, k: int) -> Path:
    """k: 0,1 = POR 회차, 2 = DOE."""
    lines = ["#HeaderStart", "WAFERID=W1", "#HeaderEnd", "#MeasureDataStart", ",".join(MEASURE_COLS)]
    for item, runs in VALUES.items():
        for die, v in zip(DIES, runs[k]):
            row = dict.fromkeys(MEASURE_COLS, "")
            row.update(COORD_X_Y=die, ITEM=item, UNIT="[A]", DATA=str(v))
            lines.append(",".join(row[c] for c in MEASURE_COLS))
    lines += ["#MeasureDataEnd", "[EOF]"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _raw_args(tmp_path: Path) -> list[str]:
    p1, p2, d = (_dcnormal(tmp_path / f"{n}.result", k) for k, n in enumerate(("por1", "por2", "doe")))
    blank = tmp_path / "blank.csv"
    blank.write_text("ITEM,SIGMA0\nA1,0.01\n", encoding="utf-8")
    return ["--por", str(p1), "--por", str(p2), "--doe", str(d), "--blank", str(blank),
            "--key", "WAFERID,COORD_X_Y,ITEM", "--encoding", "auto"]


def _index(out: Path) -> pd.DataFrame:
    return pd.read_csv(out / fe.ITEMS_INDEX, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def _folder(out: Path, typ: str, item: str) -> Path:
    return out / fe.ITEMS_DIR / safe_group_name(f"{typ}_{item}")


def test_item_type_priority():
    assert fe.item_type(f"{ST_RUN_JITTER};{ST_UNSTABLE}", "미결") == ST_UNSTABLE
    assert fe.item_type(f"{ST_SIZE_JITTER};{ST_RUN_JITTER}", "차이") == ST_RUN_JITTER
    assert fe.item_type(ST_OK, "차이") == "차이"
    assert fe.item_type("", "미결") == "미결"
    assert fe.item_type("새 상태", "미결") == "새 상태"          # 표에 없는 이름도 그대로 대표
    assert fe.STATUS_PRIORITY.index(ST_UNSTABLE) < fe.STATUS_PRIORITY.index(ST_RUN_JITTER)


def test_folders_summary_and_raw(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out), *_raw_args(tmp_path)]) == 0

    a1, a2, a5 = _folder(out, "차이", "A1"), _folder(out, ST_UNSTABLE, "A2"), _folder(out, "미결", "A5")
    for f in (a1, a2, a5):
        assert (f / "summary.csv").is_file(), f
        assert (f / "raw.csv").is_file(), f

    s = pd.read_csv(a1 / "summary.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert list(s.columns) == ["ITEM", "UNIT", "verdict", "reason", "status", "extra_col"]
    assert s.loc[0, "extra_col"] == "xA1"

    raw = pd.read_csv(a1 / "raw.csv", encoding="utf-8-sig")
    assert list(raw["COORD_X_Y"]) == DIES
    assert {"WAFERID", "ITEM", "POR1", "POR2", "DOE", "blank_item", "blank_sigma0", "d", "por_range"} <= set(raw.columns)
    assert raw["d"].tolist() == pytest.approx([2.0 - 1.1, 3.0 - 2.1, 4.0 - 3.2])
    assert raw["por_range"].tolist() == pytest.approx([0.2, 0.2, 0.4])
    assert raw["blank_sigma0"].tolist() == pytest.approx([0.01] * 3)

    # A5 는 원데이터에 없어 머리줄만
    assert pd.read_csv(a5 / "raw.csv", encoding="utf-8-sig").empty
    assert fe.NO_RAW_MSG not in (out / "summary.txt").read_text(encoding="utf-8")


def test_excluded_and_equal_have_no_folder(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out)]) == 0
    folders = sorted(p.name for p in (out / fe.ITEMS_DIR).iterdir() if p.is_dir())
    assert folders == sorted(safe_group_name(n) for n in ("차이_A1", f"{ST_UNSTABLE}_A2", "미결_A5"))


def test_items_index_contents(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out)]) == 0
    idx = _index(out)
    assert list(idx.columns) == list(fe.INDEX_COLUMNS)
    assert idx.to_dict("records") == [
        {"ID": "A1", "유형": "차이", "verdict": "차이", "status": ST_OK,
         "폴더": f"items/{safe_group_name('차이_A1')}", "log_target": "False"},
        {"ID": "A2", "유형": ST_UNSTABLE, "verdict": "미결", "status": f"{ST_RUN_JITTER};{ST_UNSTABLE}",
         "폴더": f"items/{safe_group_name(f'{ST_UNSTABLE}_A2')}", "log_target": "False"},
        {"ID": "A5", "유형": "미결", "verdict": "미결", "status": "",
         "폴더": f"items/{safe_group_name('미결_A5')}", "log_target": "False"},
    ]
    for rel in idx["폴더"]:
        assert (out / rel).is_dir()


def test_no_raw_writes_summary_only(tmp_path, capsys):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out)]) == 0
    f = _folder(out, "차이", "A1")
    assert sorted(p.name for p in f.iterdir()) == ["summary.csv"]
    assert fe.NO_RAW_MSG in capsys.readouterr().out
    assert fe.NO_RAW_MSG in (out / "summary.txt").read_text(encoding="utf-8")


def test_por_without_doe_is_error(tmp_path):
    p1 = _dcnormal(tmp_path / "por1.result", 0)
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(tmp_path / "o"), "--por", str(p1)]) == 2


def test_compare_columns_prefixed(tmp_path):
    cmp = tmp_path / "compare.csv"
    pd.DataFrame({"ITEM": ["A1", "Z9"], "verdict_before": ["동등", "동등"], "verdict_after": ["차이", "동등"]}).to_csv(
        cmp, index=False, encoding="utf-8-sig")
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out), "--compare", str(cmp)]) == 0
    s1 = pd.read_csv(_folder(out, "차이", "A1") / "summary.csv", encoding="utf-8-sig", dtype=str)
    assert s1.loc[0, "cmp_verdict_after"] == "차이" and s1.loc[0, "cmp_ITEM"] == "A1"
    s5 = pd.read_csv(_folder(out, "미결", "A5") / "summary.csv", encoding="utf-8-sig", dtype=str)
    assert not any(c.startswith(fe.CMP_PREFIX) for c in s5.columns)


def test_items_option_adds_folders(tmp_path, capsys):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out), "--items", "A3", "NOPE"]) == 0
    assert list(_index(out)["ID"]) == ["A1", "A2", "A3", "A5"]
    assert _folder(out, "동등", "A3").is_dir()
    assert "NOPE" in capsys.readouterr().out


# ---------------------------------------------------------------- WO-Z3: --items 익명 ID

ANON = {"A1": "X01", "A2": "X02", "A3": "X03", "A4": "X04", "A5": "A3"}   # A5 의 익명 ID 는 실제 이름 A3 와 겹침


def _anon_items_csv(tmp_path: Path) -> Path:
    """summarize.py 처럼 ITEM 옆에 익명 ID 열이 있는 items.csv."""
    path = tmp_path / "items.csv"
    pd.DataFrame([{"ITEM": i, "ID": ANON[i], "UNIT": "A", "verdict": v, "reason": "r", "status": s}
                  for i, v, s in ITEMS]).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def test_z3_items_by_anon_id_with_raw(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(VALUES, "A4", ([7.0, 8.0, 9.0], [7.1, 8.1, 9.1], [7.5, 8.5, 9.5]))
    out = tmp_path / "out"
    assert fe.main(["--input", str(_anon_items_csv(tmp_path)), "--out", str(out), *_raw_args(tmp_path),
                    "--items", "X03,X04"]) == 0
    assert list(_index(out)["ID"]) == ["A1", "A2", "A3", "A4", "A5"]          # items_index 는 실제 ITEM
    assert _folder(out, "동등", "A3").is_dir()
    a4 = _folder(out, fe.item_type(ST_OK, V_EXCLUDED), "A4")                  # 판정 제외 ITEM 도 익명 ID 로
    for name in ("summary.csv", "raw.csv", fe.ITEM_VIEW_PNG):
        assert (a4 / name).is_file(), name
    assert pd.read_csv(a4 / "raw.csv", encoding="utf-8-sig")["POR1"].tolist() == pytest.approx([7.0, 8.0, 9.0])
    assert "입력에 없는 ID" not in capsys.readouterr().out


def test_z3_items_mixed_real_and_anon_and_unknown(tmp_path, capsys):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_anon_items_csv(tmp_path)), "--out", str(out),
                    "--items", "A4", "X03", "NOPE,X99"]) == 0
    assert list(_index(out)["ID"]) == ["A1", "A2", "A3", "A4", "A5"]
    printed = [ln for ln in capsys.readouterr().out.splitlines() if "입력에 없는 ID" in ln]
    assert printed == ["입력에 없는 ID: NOPE, X99"]


def test_z3_real_name_wins_over_anon_id(tmp_path):
    plain = fe.read_plain(_anon_items_csv(tmp_path))
    assert fe.select_items(plain, ["A3"]) == (["A1", "A2", "A3", "A5"], [])   # 'A3' = 실제 A3 (A5 의 익명 ID 아님)
    assert fe.select_items(plain, ["X04", "X9"]) == (["A1", "A2", "A4", "A5"], ["X9"])


# ---------------------------------------------------------------- --only

def test_only_two_items_real_and_anon(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(VALUES, "A4", ([7.0, 8.0, 9.0], [7.1, 8.1, 9.1], [7.5, 8.5, 9.5]))
    out = tmp_path / "out"
    assert fe.main(["--input", str(_anon_items_csv(tmp_path)), "--out", str(out), *_raw_args(tmp_path),
                    "--only", "A4,X03", "NOPE"]) == 0
    folders = sorted(p.name for p in (out / fe.ITEMS_DIR).iterdir() if p.is_dir())
    a3, a4 = _folder(out, "동등", "A3"), _folder(out, fe.item_type(ST_OK, V_EXCLUDED), "A4")
    assert folders == sorted([a3.name, a4.name])                                # 차이·미결 기본 대상 없음
    for f, item in ((a3, "A3"), (a4, "A4")):
        for name in ("summary.csv", "raw.csv", fe.ITEM_VIEW_PNG):
            assert (f / name).is_file(), (f, name)
        assert set(pd.read_csv(f / "raw.csv", encoding="utf-8-sig")["ITEM"]) == {item}
    assert list(_index(out)["ID"]) == ["A3", "A4"]
    ev = pd.read_csv(out / "fail_evidence.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert list(ev["ITEM"]) == ["A3", "A4"] and list(ev["ID"]) == ["X03", "X04"]
    assert "입력에 없는 ID: NOPE" in capsys.readouterr().out


def test_only_read_side_returns_only_given_items(tmp_path):
    from infra_compare import load_side
    p = _dcnormal(tmp_path / "por1.result", 0)
    got = fe.read_side_items([str(p)], "POR1", "auto", ["A1", "A3"])
    assert set(got["ITEM"]) == {"A1", "A3"}
    full = load_side([str(p)], "POR1", "auto")
    want = full[full["ITEM"].astype(str).isin({"A1", "A3"})].reset_index(drop=True)
    pd.testing.assert_frame_equal(got, want)


def test_only_load_wide_items_matches_full_filter(tmp_path):
    a = fe.parse_args(["--input", "x", "--out", "y", *_raw_args(tmp_path)])
    got, por_cols = fe.load_wide_items(a, ["A2"])
    full, full_cols, _ = fe.load_wide(a)
    want = full[full["ITEM"].astype(str) == "A2"].reset_index(drop=True)
    assert por_cols == full_cols
    pd.testing.assert_frame_equal(got, want)


def test_only_and_items_together_is_error(tmp_path):
    with pytest.raises(SystemExit) as e:
        fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(tmp_path / "o"), "--only", "A1", "--items", "A3"])
    assert e.value.code == 2


def test_rerun_with_marker_rebuilds(tmp_path):
    src = _items_csv(tmp_path)
    out = tmp_path / "out"
    assert fe.main(["--input", str(src), "--out", str(out), "--items", "A3"]) == 0
    items = out / fe.ITEMS_DIR
    assert (items / fe.ITEMS_MARKER).is_file()
    a3 = _folder(out, "동등", "A3")
    (a3 / "left.txt").write_text("old", encoding="utf-8")
    (out / "notes.txt").write_text("user", encoding="utf-8")

    assert fe.main(["--input", str(src), "--out", str(out)]) == 0
    assert not a3.exists()
    assert (items / fe.ITEMS_MARKER).is_file()
    assert sorted(p.name for p in items.iterdir() if p.is_dir()) == sorted(
        safe_group_name(n) for n in ("차이_A1", f"{ST_UNSTABLE}_A2", "미결_A5"))
    assert (out / "notes.txt").is_file()


def test_no_marker_with_user_files_stops(tmp_path, capsys):
    out = tmp_path / "out"
    items = out / fe.ITEMS_DIR
    (items / "mine").mkdir(parents=True)
    (items / "mine" / "keep.txt").write_text("user", encoding="utf-8")
    (items / "old.png").write_bytes(b"png")
    (out / "fail_evidence.csv").write_text("old", encoding="utf-8")

    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out)]) != 0
    assert fe.ITEMS_MARKER in capsys.readouterr().err
    assert (items / "mine" / "keep.txt").read_text(encoding="utf-8") == "user"
    assert (items / "old.png").is_file()
    assert not (items / fe.ITEMS_MARKER).exists()
    assert (out / "fail_evidence.csv").read_text(encoding="utf-8") == "old"   # 다른 출력도 건드리지 않음
    assert not (out / fe.ITEMS_INDEX).exists()


def test_item_view_and_evidence_written_with_raw(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out), *_raw_args(tmp_path)]) == 0
    for f in (_folder(out, "차이", "A1"), _folder(out, ST_UNSTABLE, "A2")):
        png = f / fe.ITEM_VIEW_PNG
        assert png.is_file() and png.stat().st_size > 0, f
        assert (f / fe.EVIDENCE_CSV).is_file(), f
        assert not (f / "drill.png").exists(), f
    a5 = _folder(out, "미결", "A5")                                    # 원데이터 행이 없으면 그림·근거 표 없음
    assert not (a5 / fe.ITEM_VIEW_PNG).exists() and not (a5 / fe.EVIDENCE_CSV).exists()


def test_no_raw_no_item_view(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out)]) == 0
    assert not list((out / fe.ITEMS_DIR).rglob(fe.ITEM_VIEW_PNG))
    assert not list((out / fe.ITEMS_DIR).rglob(fe.EVIDENCE_CSV))


def _die_rows(**coords) -> pd.DataFrame:
    n = 6
    rows = pd.DataFrame({"ITEM": ["Z"] * n, "POR1": [1.0, 1.1, 0.9, 1.2, 1.0, 0.8],
                         "POR2": [1.1, 1.0, 1.0, 1.1, 0.9, 0.9], "DOE": [1.5, 1.6, 1.4, 1.7, 1.5, 1.3],
                         "blank_sigma0": [0.02] * n, **coords})
    rows["d"] = rows["DOE"] - rows[["POR1", "POR2"]].mean(axis=1)
    return rows


SUMMARY = {"ITEM": "Z", "verdict": "차이", "status": ST_OK, "center": "0.5", "ci_low": "0.4", "ci_high": "0.6",
           "delta": "0.3", "LoQ": "0.2", "LoD": "0.066"}


@pytest.mark.parametrize("coords", [
    {"COORD_X_Y": ["0_0", "1_0", "0_1", "1_1", "-1_0", "0_-1"]},
    {"X": [0, 1, 0, 1, -1, 0], "Y": [0, 0, 1, 1, 0, -1]},
    {},
])
def test_plot_item_view_with_and_without_coords(tmp_path, coords):
    rows = _die_rows(**coords)
    assert (item_view.die_xy(rows) is not None) == bool(coords)
    png = item_view.plot_item_view(rows, SUMMARY, tmp_path / fe.ITEM_VIEW_PNG)
    assert png.is_file() and png.stat().st_size > 0


def test_plot_item_view_without_blank_or_limits(tmp_path):
    rows = _die_rows().drop(columns="blank_sigma0")
    png = item_view.plot_item_view(rows, {"verdict": "미결"}, tmp_path / fe.ITEM_VIEW_PNG)
    assert png.is_file()


def test_empty_items_dir_without_marker_is_used(tmp_path):
    out = tmp_path / "out"
    (out / fe.ITEMS_DIR).mkdir(parents=True)
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out)]) == 0
    assert (out / fe.ITEMS_DIR / fe.ITEMS_MARKER).is_file()


# ---------------------------------------------------------------- WO-P (c): status별 패널

def _status_png(folder: Path, name: str) -> Path:
    return folder / fe.STATUS_PNG.format(safe_group_name(name))


def test_status_panels_two_statuses_in_main(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out), *_raw_args(tmp_path)]) == 0
    a2 = _folder(out, ST_UNSTABLE, "A2")
    pngs = sorted(p.name for p in a2.glob("status_*.png"))
    assert pngs == sorted(_status_png(a2, n).name for n in (ST_RUN_JITTER, ST_UNSTABLE))
    assert not list(_folder(out, "차이", "A1").glob("status_*.png"))      # 정상은 패널 없음


@pytest.mark.parametrize("status", [
    f"{ST_RUN_JITTER};{ST_UNSTABLE}",
    f"{ST_SIZE_JITTER};{fe.ST_RESOLUTION}",
    f"{fe.ST_FLAT};{ST_OK}",
])
def test_status_panels_each_kind(tmp_path, status):
    rows = _die_rows().assign(blank_offset=0.0)
    s = {**SUMMARY, "status": status, "por_gap_over_delta": "1.4", "por_gap_over_noise": "5",
         "spearman_size_jitter": "-0.8"}
    paths = fe.plot_status_panels(rows, s, "Z", status, tmp_path)
    names = [n for n in status.split(";") if n != ST_OK]
    assert paths == [_status_png(tmp_path, n) for n in names]
    assert all(p.is_file() and p.stat().st_size > 0 for p in paths)


def test_status_panels_missing_summary_values(tmp_path):
    status = ";".join(fe.STATUS_PANELS)
    paths = fe.plot_status_panels(_die_rows(), {"verdict": "미결"}, "Z", status, tmp_path)
    assert len(paths) == len(fe.STATUS_PANELS) and all(p.is_file() for p in paths)


def test_status_panels_unknown_status_warns(tmp_path, capsys):
    assert fe.plot_status_panels(_die_rows(), SUMMARY, "Z", "새 상태", tmp_path) == []
    assert not list(tmp_path.glob("status_*.png"))
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "새 상태" in ln]
    assert len(lines) == 1 and "경고" in lines[0]


def test_no_raw_no_status_png(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_items_csv(tmp_path)), "--out", str(out)]) == 0
    assert not list((out / fe.ITEMS_DIR).rglob("status_*.png"))


# ---------------------------------------------------------------- WO-S S3: log_diag.png

LOG_ITEMS = [
    # ITEM, verdict, status, verdict_log
    ("A1", "차이", ST_SIZE_JITTER, "동등"),
    ("A2", "미결", ST_RUN_JITTER, "미결"),
    ("A3", "동등", f"{ST_OK};{ST_SIZE_JITTER}", "동등"),
]
LOG_COLS = {"center": "0.5", "ci_low": "0.3", "ci_high": "0.7", "delta": "0.4",
            "center_log": "0.05", "ci_low_log": "0.01", "ci_high_log": "0.09", "delta_log": "0.1",
            "spearman_size_jitter": "-0.8", "spearman_size_jitter_log": "-0.1", "log_reason": ""}


def _log_items_csv(tmp_path: Path, with_log: bool = True) -> Path:
    path = tmp_path / "items.csv"
    rows = []
    for i, v, s, vl in LOG_ITEMS:
        r = {"ITEM": i, "UNIT": "A", "verdict": v, "reason": "r", "status": s, **LOG_COLS, "verdict_log": vl}
        if not with_log:
            r = {k: x for k, x in r.items() if not k.endswith("_log") and k != "log_reason"}
        rows.append(r)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def test_t7_size_jitter_diff_item_gets_log_diag(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_log_items_csv(tmp_path)), "--out", str(out), *_raw_args(tmp_path)]) == 0
    f = _folder(out, ST_SIZE_JITTER, "A1")
    assert (f / fe.LOG_DIAG_PNG).is_file()
    assert (f / fe.ITEM_VIEW_PNG).is_file() and (f / "raw.csv").is_file()
    assert not (_folder(out, ST_RUN_JITTER, "A2") / fe.LOG_DIAG_PNG).exists()


def test_t7b_equal_target_gets_summary_raw_and_log_diag_only(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_log_items_csv(tmp_path)), "--out", str(out), *_raw_args(tmp_path)]) == 0
    f = _folder(out, ST_SIZE_JITTER, "A3")
    assert sorted(p.name for p in f.iterdir()) == sorted(["summary.csv", "raw.csv", fe.LOG_DIAG_PNG])


def test_t7b_equal_target_without_raw_summary_only(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_log_items_csv(tmp_path)), "--out", str(out)]) == 0
    f = _folder(out, ST_SIZE_JITTER, "A3")
    assert [p.name for p in f.iterdir()] == ["summary.csv"]


def test_t7c_items_index_log_target(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_log_items_csv(tmp_path)), "--out", str(out)]) == 0
    idx = _index(out)
    assert "log_target" in idx.columns
    assert dict(zip(idx["ID"], idx["log_target"])) == {"A1": "True", "A2": "False", "A3": "True"}
    for rel in idx["폴더"]:
        assert (out / rel).is_dir()
    # 클수록 흔들림 이름도 대상
    assert fe.is_log_target(f"{ST_OK};{ST_SIZE_JITTER_POS}")
    assert not fe.is_log_target(ST_RUN_JITTER)


def test_t7d_input_without_log_columns(tmp_path):
    out = tmp_path / "out"
    assert fe.main(["--input", str(_log_items_csv(tmp_path, with_log=False)), "--out", str(out),
                    *_raw_args(tmp_path)]) == 0
    assert (_folder(out, ST_SIZE_JITTER, "A1") / fe.LOG_DIAG_PNG).is_file()
    assert (_folder(out, ST_SIZE_JITTER, "A3") / fe.LOG_DIAG_PNG).is_file()


def test_t7d_plot_log_diag_zero_values_and_empty_summary(tmp_path):
    rows = _die_rows()
    rows.loc[0, "POR1"] = 0.0
    assert fe.plot_log_diag(rows, {}, "Z", tmp_path / "a.png").is_file()
    assert fe.plot_log_diag(_die_rows(), {**SUMMARY, "log_reason": "음수 있음"}, "Z", tmp_path / "b.png").is_file()
