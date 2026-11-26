"""새 브라우저 리포트의 상대 경로, chunk, 익명 출력과 원데이터 값을 검사한다."""
import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import golden_cases as gc  # noqa: E402
import item_view  # noqa: E402
import por_doe_compare  # noqa: E402

ECHARTS_SHA256 = "bf4a223524e40b77c304bec67e1222cf551f14880cf42c69dc046558e11c07b1"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("report_v2_pages")
    data = base / "por3"
    gc.make_por3(data)
    out = base / "out"
    common = [*(a for k in (1, 2, 3) for a in ("--por", data / f"por_run{k}")), "--doe", data / "doe",
              "--level", data / "level.csv", "--blank", data / "blank", "--blank-map", data / "blank_map.csv"]
    gc._run([ROOT / "por_doe_compare.py", *common, "--out", out])
    gc._run([ROOT / "raw_stats.py", *common, "--out", out])
    gc._run([ROOT / "loq_check.py", "--input", out / "items.csv", "--out", out, *common])
    gc._run([ROOT / "report_v2.py", out, *common])
    gc._run([ROOT / "report_v2.py", out, *common, "--anon"])
    return {"base": base, "out": out, "common": common,
            "items": pd.read_csv(out / "items.csv", encoding="utf-8-sig"),
            "table": pd.read_csv(out / "report" / "table.csv", encoding="utf-8-sig")}


def read_assignment(path: Path, name: str):
    text = path.read_text(encoding="utf-8").strip()
    prefix = f"window.{name} = "
    assert text.startswith(prefix) and text.endswith(";"), path
    return json.loads(text[len(prefix):-1])


def test_pages_assets_and_all_html_references_are_local(built):
    folder = built["out"] / "report"
    expected = ["index.html", "table.html", "analysis.html", "assets/report.js", "assets/report.css",
                "assets/echarts.min.js", "assets/echarts.LICENSE.txt", "assets/echarts.NOTICE.txt",
                "data/table.js", "data/index.js"]
    for relative in expected:
        assert (folder / relative).is_file(), relative
    for page in ("index.html", "table.html", "analysis.html"):
        text = (folder / page).read_text(encoding="utf-8")
        for ref in re.findall(r"(?:src|href)=\"([^\"]+)\"", text):
            target = ref.split("#", 1)[0]
            if not target:
                continue
            assert not target.startswith(("http:", "https:", "//", "/")), (page, ref)
            assert not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target), (page, ref)
            assert (folder / target).is_file(), (page, ref)


def test_chunk_names_counts_and_index_cover_every_key_exactly_once(built):
    folder = built["out"] / "report"
    index = read_assignment(folder / "data" / "index.js", "__dcIndex")
    chunks = sorted((folder / "data" / "chunks").iterdir())
    assert all(re.fullmatch(r"c\d{5}\.js", path.name) for path in chunks)
    assert len(chunks) == math.ceil(len(built["items"]) / 100)
    assert set(index) == {str(row) for row in built["table"]["row"]}
    seen = {}
    for path in chunks:
        keys = re.findall(r"window\.__dcItem\[\"([^\"]+)\"\] =", path.read_text(encoding="utf-8"))
        for key in keys:
            assert key not in seen, (key, seen.get(key), path.name)
            seen[key] = path.name
    assert set(seen) == set(index)
    for key, chunk_number in index.items():
        assert seen[key] == f"c{chunk_number:05d}.js"


def test_table_js_matches_items_rows_and_table_csv_columns(built):
    payload = read_assignment(built["out"] / "report" / "data" / "table.js", "__dcTable")
    assert len(payload["rows"]) == len(built["items"])
    assert payload["cols"] == list(built["table"].columns)
    assert payload["meta"]["n_items"] == len(built["items"])
    assert payload["meta"]["chunk_size"] == 100
    assert payload["meta"]["chunks"] is True


def test_anon_has_no_real_item_or_blank_name_in_text_outputs(built):
    folder = built["out"] / "report_anon"
    names = set(built["items"]["ITEM"].dropna()) | set(built["items"]["blank_item"].dropna())
    for path in folder.rglob("*"):
        if not path.is_file() or path.suffix not in {".html", ".js", ".csv", ".json"}:
            continue
        if path.parent == folder / "assets" and path.name.startswith("echarts."):
            continue
        text = path.read_text(encoding="utf-8-sig")
        assert not [name for name in names if str(name) in text], path.relative_to(folder)


def test_vendor_and_copied_echarts_have_expected_sha256(built):
    source = ROOT / "assets" / "report" / "vendor" / "echarts.min.js"
    copied = built["out"] / "report" / "assets" / "echarts.min.js"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ECHARTS_SHA256
    assert hashlib.sha256(copied.read_bytes()).hexdigest() == ECHARTS_SHA256


def test_without_raw_args_succeeds_with_table_and_empty_index(built):
    out = built["base"] / "without_raw"
    out.mkdir()
    shutil.copyfile(built["out"] / "items.csv", out / "items.csv")
    shutil.copyfile(built["out"] / "raw_stats.csv", out / "raw_stats.csv")
    gc._run([ROOT / "report_v2.py", out])
    payload = read_assignment(out / "report" / "data" / "table.js", "__dcTable")
    assert len(payload["rows"]) == len(built["items"])
    assert payload["meta"]["chunks"] is False
    assert payload["meta"]["img_rows"] == []
    assert payload["meta"]["log_bases"] == list(item_view.LOG_BASES)
    assert read_assignment(out / "report" / "data" / "index.js", "__dcIndex") == {}


def chunk_item(folder: Path, key: str):
    index = read_assignment(folder / "data" / "index.js", "__dcIndex")
    path = folder / "data" / "chunks" / f"c{index[key]:05d}.js"
    prefix = f'window.__dcItem["{key}"] = '
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            assert line.endswith(";")
            return json.loads(line[len(prefix):-1])
    raise AssertionError(f"{key} not in {path}")


def test_two_chunk_items_have_load_wide_values(built):
    parser = argparse.ArgumentParser()
    por_doe_compare.add_common_args(parser)
    args = parser.parse_args([str(value) for value in built["common"]])
    wide, por_cols, _ = por_doe_compare.load_wide(args)
    folder = built["out"] / "report"
    for item in wide["ITEM"].drop_duplicates().iloc[:2]:
        key = str(built["table"].loc[built["table"]["ITEM"] == item, "row"].iloc[0])
        actual = chunk_item(folder, key)
        assert actual["cols"] == [*por_cols, "DOE"]
        expected_group = wide[wide["ITEM"] == item]
        expected = expected_group[[*por_cols, "DOE"]].to_numpy()
        assert len(actual["v"]) == len(expected)
        assert len(actual["die"]) == len(expected)
        for actual_values, expected_values in zip(actual["v"], expected):
            assert len(actual_values) == len(expected_values)
            for actual_value, expected_value in zip(actual_values, expected_values):
                if pd.isna(expected_value):
                    assert actual_value is None
                else:
                    assert actual_value == pytest.approx(expected_value)


def test_chunk_die_evidence_reproduces_items_rank_ci(built):
    checked = 0
    folder = built["out"] / "report"
    for position, item_row in built["items"].iterrows():
        if str(item_row["verdict_basis"]) == "limit":
            continue
        key = str(built["table"].iloc[position]["row"])
        chunk = chunk_item(folder, key)
        if len(chunk["die"]) < 2:
            continue
        rows = pd.DataFrame(chunk["die"], columns=["WAFERID", "COORD_X_Y"])
        for c, col in enumerate(chunk["cols"]):
            rows[col] = [values[c] for values in chunk["v"]]
        evidence = item_view.die_evidence(rows, item_row)
        assert evidence.n >= 2, key
        ordered = np.sort(evidence.d)
        k = evidence.k
        suffix = "_log" if str(item_row["verdict_basis"]) in item_view.LOG_BASES else ""
        low = item_row["ci_low" + suffix]
        high = item_row["ci_high" + suffix]
        assert ordered[k - 1] == pytest.approx(low, rel=1e-9, abs=1e-15), key
        assert ordered[evidence.n - k] == pytest.approx(high, rel=1e-9, abs=1e-15), key
        lo, hi = ordered[k - 1], ordered[evidence.n - k]
        assert ((lo <= evidence.d) & (evidence.d <= hi)).sum() >= evidence.n - 2 * k + 2, key
        assert low <= item_row["center" + suffix] <= high, key
        checked += 1
    assert checked > 0


@pytest.fixture(scope="module")
def image_modes(built):
    folders = {}
    for mode in ("fail+pending", "none"):
        out = built["base"] / ("images_" + mode.replace("+", "_"))
        out.mkdir()
        shutil.copyfile(built["out"] / "items.csv", out / "items.csv")
        shutil.copyfile(built["out"] / "raw_stats.csv", out / "raw_stats.csv")
        gc._run([ROOT / "report_v2.py", out, *built["common"], "--images", mode])
        folders[mode] = out / "report"
    return folders


def png_files(folder: Path):
    image_dir = folder / "img"
    return sorted(image_dir.glob("*.png")) if image_dir.exists() else []


def test_static_image_modes_counts_names_and_no_data_urls(built, image_modes):
    verdicts = built["table"]["verdict_final"].astype(str)
    cases = ((built["out"] / "report", int((verdicts == "차이").sum())),
             (image_modes["fail+pending"], int(verdicts.isin(["차이", "미결"]).sum())),
             (image_modes["none"], 0))
    for folder, expected in cases:
        files = png_files(folder)
        assert len(files) == expected, folder
        assert all(re.fullmatch(r"i\d{5}\.png", path.name) for path in files)
        if expected == 0:
            assert not (folder / "img").exists() or not any((folder / "img").iterdir())
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix in {".html", ".js"} and not path.name.startswith("echarts."):
                assert "data:image" not in path.read_text(encoding="utf-8"), path.relative_to(folder)


def test_table_meta_log_bases_and_img_rows_match_files(built):
    for name in ("report", "report_anon"):
        folder = built["out"] / name
        meta = read_assignment(folder / "data" / "table.js", "__dcTable")["meta"]
        assert meta["log_bases"] == list(item_view.LOG_BASES)
        assert meta["img_rows"] == [int(path.stem[1:]) for path in png_files(folder)]


def test_anon_static_image_names_do_not_contain_item_names(built):
    folder = built["out"] / "report_anon"
    assert png_files(folder), "기본 fail 실행은 차이 ITEM의 익명 PNG를 만들어야 한다"
    assert all(re.fullmatch(r"i\d{5}\.png", path.name) for path in png_files(folder))
