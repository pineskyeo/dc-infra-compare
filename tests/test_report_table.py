"""report_v2.py 데이터: 표 행, judged_by, delta_pct, 요약, 익명 출력과 items.csv 불변."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import golden_cases as gc  # noqa: E402
import loq_check  # noqa: E402
import por_doe_compare  # noqa: E402
import report_v2  # noqa: E402
from explain import BASIS_NAMES, LOQ_ZONES  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("report_table")
    data = base / "por3"
    gc.make_por3(data)
    out = base / "out"
    common = [*(a for k in (1, 2, 3) for a in ("--por", data / f"por_run{k}")), "--doe", data / "doe",
              "--level", data / "level.csv", "--blank", data / "blank", "--blank-map", data / "blank_map.csv"]
    gc._run([ROOT / "por_doe_compare.py", *common, "--out", out])
    items_before = (out / "items.csv").read_bytes()
    gc._run([ROOT / "raw_stats.py", *common, "--out", out])
    gc._run([ROOT / "loq_check.py", "--input", out / "items.csv", "--out", out, *common])
    gc._run([ROOT / "report_v2.py", out])
    gc._run([ROOT / "report_v2.py", out, "--anon"])
    return {"out": out, "items_before": items_before,
            "items": pd.read_csv(out / "items.csv", encoding="utf-8-sig"),
            "table": pd.read_csv(out / "report" / "table.csv", encoding="utf-8-sig")}


def expected_judged_by(row):
    final = str(row["verdict_final"])
    if final == "판정 제외":
        return final
    basis = BASIS_NAMES.get(str(row["verdict_basis"]), str(row["verdict_basis"]))
    if final in ("차이", "미결") or row["zone"] not in LOQ_ZONES:
        return basis
    kind = loq_check.pass_kind(row)
    if kind == loq_check.K_SHIFT:
        return "TOST"
    if kind in loq_check.RULE_PASSES:
        return "LoQ 규칙"
    if kind == loq_check.K_STAGE3:
        return f"판정 길({basis})"
    return basis


def test_table_preserves_items_rows_and_judged_by_mapping(built):
    items, table = built["items"], built["table"]
    assert len(table) == len(items)
    assert table["row"].tolist() == list(range(1, len(items) + 1))
    assert table["ITEM"].tolist() == items["ITEM"].tolist()
    assert {"IOFF_FLOOR", "IOFF_LEAK"} <= set(table["ITEM"])
    expected = [expected_judged_by(row) for row in items.to_dict("records")]
    assert table["judged_by"].tolist() == expected


def test_delta_pct_copied_rule_and_zero_por_median(built):
    for _, row in built["table"].dropna(subset=["delta_pct"]).iterrows():
        assert row["delta_pct"] == pytest.approx(100 * row["delta"] / abs(row["por_median"]))
    small = pd.DataFrame([{"ITEM": "ZERO", "zone": "정량", "verdict_final": "동등", "verdict_basis": "linear",
                           "delta": 2.0, "por_median": 0.0}])
    made = report_v2.make_table(small, pd.DataFrame(columns=["ITEM"]))
    assert math.isnan(made.loc[0, "delta_pct"])


def _meas_item(item="A", center=0.06, ci=(0.02, 0.10), delta=0.04):
    return {"ITEM": item, "zone": "정량", "verdict_final": "동등", "verdict_basis": "linear",
            "center": center, "ci_low": ci[0], "ci_high": ci[1], "delta": delta, "por_median": 1.0}


def _meas_table(rows, levels):
    return report_v2.make_table(pd.DataFrame(rows), pd.DataFrame(columns=["ITEM"]), levels=levels)


def test_meas_columns_divide_by_positive_calcval():
    lv = {"A": por_doe_compare.ItemInfo(1.0, "V", 2.0, False)}
    t = _meas_table([_meas_item()], lv).iloc[0]
    assert t["calcval"] == pytest.approx(2.0)
    assert t["center_meas"] == pytest.approx(0.03)
    assert t["ci_low_meas"] == pytest.approx(0.01)
    assert t["ci_high_meas"] == pytest.approx(0.05)
    assert t["delta_meas"] == pytest.approx(0.02)
    assert t["meas_note"] == ""


def test_meas_columns_negative_calcval_flips_and_resorts_ci():
    lv = {"A": por_doe_compare.ItemInfo(1.0, "V", -1.0, False)}
    t = _meas_table([_meas_item()], lv).iloc[0]
    assert t["center_meas"] == pytest.approx(-0.06)
    assert t["ci_low_meas"] == pytest.approx(-0.10)
    assert t["ci_high_meas"] == pytest.approx(-0.02)
    assert t["delta_meas"] == pytest.approx(0.04)
    assert t["meas_note"] == ""


def test_meas_columns_empty_without_calcval():
    lv = {"A": por_doe_compare.ItemInfo(1.0, "V", None, False)}
    t = _meas_table([_meas_item()], lv).iloc[0]
    assert math.isnan(t["calcval"])
    for col in ("center_meas", "ci_low_meas", "ci_high_meas", "delta_meas"):
        assert math.isnan(t[col])
    assert t["meas_note"] == "CALCVAL 없음"


def test_meas_columns_empty_for_derived_item_but_keep_calcval():
    lv = {"A": por_doe_compare.ItemInfo(1.0, "V", 3.0, True)}
    t = _meas_table([_meas_item()], lv).iloc[0]
    assert t["calcval"] == pytest.approx(3.0)
    for col in ("center_meas", "ci_low_meas", "ci_high_meas", "delta_meas"):
        assert math.isnan(t[col])
    assert t["meas_note"] == "변형(DERIVED=Y)"


def test_meas_columns_without_levels_keep_six_columns_and_note():
    made = _meas_table([_meas_item()], None)
    for col in ("calcval", "center_meas", "meas_note", "ci_low_meas", "ci_high_meas", "delta_meas"):
        assert col in made.columns
    t = made.iloc[0]
    assert math.isnan(t["calcval"])
    assert math.isnan(t["center_meas"])
    assert t["meas_note"] == "--level 없음"


def test_meas_note_when_item_missing_from_levels():
    lv = {"OTHER": por_doe_compare.ItemInfo(1.0, "V", 2.0, False)}
    t = _meas_table([_meas_item()], lv).iloc[0]
    assert math.isnan(t["delta_meas"])
    assert t["meas_note"] == "level.csv에 ITEM 없음"


def test_meas_columns_order_follows_table_layout():
    lv = {"A": por_doe_compare.ItemInfo(1.0, "V", 2.0, False)}
    cols = list(_meas_table([_meas_item()], lv).columns)
    assert cols.index("calcval") == cols.index("center") + 1
    assert cols.index("center_meas") == cols.index("center") + 2
    assert cols.index("meas_note") == cols.index("center") + 3
    assert cols.index("ci_low_meas") == cols.index("ci_high") + 1
    assert cols.index("ci_high_meas") == cols.index("ci_high") + 2
    assert cols.index("delta_meas") == cols.index("delta") + 1


@pytest.mark.parametrize("verdicts,overall", [
    (["동등", "차이", "미결"], "차이"),
    (["동등", "미결"], "미결"),
    (["동등", "판정 제외"], "동등"),
    (["판정 제외"], "판정 없음"),
])
def test_summarize_overall(verdicts, overall):
    table = pd.DataFrame({"verdict_final": verdicts, "zone": ["정량"] * len(verdicts)})
    summary = report_v2.summarize(table)
    assert summary["overall"] == overall
    assert summary["verdict_counts"]["판정 제외"] == verdicts.count("판정 제외")
    assert summary["overall_rule"] == report_v2.OVERALL_RULE


def test_anon_outputs_have_no_real_item_names_and_json_has_nulls(built):
    folder = built["out"] / "report_anon"
    texts = {name: (folder / name).read_text(encoding="utf-8-sig") for name in ("table.csv", "table.json", "summary.json")}
    for name in built["items"]["ITEM"]:
        assert all(name not in text for text in texts.values()), name
    payload = json.loads(texts["table.json"])
    assert payload["cols"][0] == "row" and len(payload["rows"]) == len(built["items"])
    assert any(value is None for row in payload["rows"] for value in row)
    assert json.loads(texts["summary.json"])["overall"] in {"동등", "미결", "차이", "판정 없음"}


def test_raw_stats_and_report_v2_do_not_change_items_csv(built):
    assert (built["out"] / "items.csv").read_bytes() == built["items_before"]
