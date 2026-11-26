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
