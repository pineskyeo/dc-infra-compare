"""WO-L 정정: 미결은 하나('미결')이고, 원인은 items.csv status 문자열을 그대로 옮겨 적기만 한다. 합성 데이터만."""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import compare_before_after as cba  # noqa: E402
import fail_evidence as fe  # noqa: E402

CAUSE = "조건 불안정;회차 흔들림"
BASE = {
    "reason": "경계", "DOE_mean": "101", "LoQ": "1", "sigma_die": "0.5", "sigma_run": "0.2", "status": "정상",
}
ROWS = [
    # 회차 차/Δ = 1.5, median_out/Δ = 1.0: 옛 기준이면 미결 하위 분류로 갈렸을 행 → 이제 그냥 미결
    dict(BASE, ITEM="BIG", verdict="미결", por_median="98", POR1_mean="100", POR2_mean="103",
         center="1", ci_low="-1", ci_high="3", delta="2", status=CAUSE),
    dict(BASE, ITEM="PEND", verdict="미결", por_median="100.5", POR1_mean="100", POR2_mean="101",
         center="0", ci_low="-1", ci_high="1", delta="2"),
    dict(BASE, ITEM="DIFF", verdict="차이", por_median="100.5", POR1_mean="100", POR2_mean="101",
         center="4", ci_low="3", ci_high="5", delta="2"),
    dict(BASE, ITEM="DIFFN", verdict="차이", por_median="100.5", POR1_mean="100", POR2_mean="101",
         center="-4", ci_low="-5", ci_high="-3", delta="2", status="회차 흔들림"),
]
EXPECTED = {"BIG": "미결", "PEND": "미결", "DIFF": "차이", "DIFFN": "차이"}


def _frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    return df[["ITEM"] + [c for c in df.columns if c != "ITEM"]]  # 헤더는 ITEM으로 시작해야 한다


@pytest.fixture()
def items_csv(tmp_path: Path) -> Path:
    path = tmp_path / "items.csv"
    _frame(ROWS).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _fe_table(path: Path) -> pd.DataFrame:
    return fe.evidence_table(fe.read_table(path)).set_index("ID")


def _cba_table(path: Path) -> pd.DataFrame:
    return cba.evidence_table(cba.read_result(path)).set_index("ID")


def test_pending_is_single_label(items_csv):
    t, ev = _fe_table(items_csv), _cba_table(items_csv)
    assert t.at["BIG", "por_gap_over_delta"] == pytest.approx(1.5)
    assert t.at["BIG", "median_out_over_delta"] == pytest.approx(1.0)
    assert ev.at["BIG", "por_gap_over_delta"] == pytest.approx(1.5)
    assert ev.at["BIG", "median_out_over_delta"] == pytest.approx(1.0)
    assert t.at["BIG", "judgement"] == "미결" == fe.J_PEND
    assert ev.at["BIG", "group"] == "미결" == cba.J_PEND
    assert set(t["judgement"]) == {"차이", "미결"}
    assert set(ev["group"]) == {"차이", "미결"}
    assert fe.PLOT_ORDER == ("차이", "미결")
    assert cba.GROUP_ORDER == ("차이", "미결")


def test_fail_evidence_and_compare_agree(items_csv):
    t, ev = _fe_table(items_csv), _cba_table(items_csv)
    assert t["judgement"].to_dict() == EXPECTED
    assert ev["group"].to_dict() == EXPECTED
    assert (t["note"] == "").all()  # verdict와 CI 규칙이 같은 합성 행이라 불일치 없음


TEXT_SUFFIXES = {".py", ".md", ".html", ".js", ".json", ".csv", ".txt"}


def test_no_old_pending_labels():
    # 이 파일 자신에 걸리지 않게 이어 붙여 만든다.
    banned = ("기준 " + "흔들림", "미결-" + "정상", "미결-" + "조건 불안정")
    hits = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if path.suffix not in TEXT_SUFFIXES or not path.is_file():
            continue
        if any(p.startswith(".") or p == "__pycache__" for p in rel.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits += [f"{rel}: {w}" for w in banned if w in text]
    assert not hits, hits


def test_status_cause_copied_verbatim(items_csv, tmp_path: Path):
    fe_out = tmp_path / "fe"
    assert fe.main(["--input", str(items_csv), "--out", str(fe_out)]) == 0
    fe_csv = pd.read_csv(fe_out / "fail_evidence.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    fe_status = dict(zip(fe_csv["ITEM"], fe_csv["status"]))
    assert fe_status["BIG"] == CAUSE
    assert fe_status["DIFFN"] == "회차 흔들림"

    ev_out = tmp_path / "ev"
    assert cba.main(["evidence", str(items_csv), "-o", str(ev_out)]) == 0
    ev_csv = pd.read_csv(ev_out / "evidence.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    cols = list(ev_csv.columns)
    assert cols[cols.index("status") + 1] == "judgment"
    by_item = ev_csv.set_index("ITEM")
    assert by_item.at["BIG", "status"] == CAUSE
    assert f"원인(status): {CAUSE}" in by_item.at["BIG", "judgment"]
    assert "원인(status)" not in by_item.at["PEND", "judgment"]  # status '정상'은 덧붙이지 않음
    assert by_item.at["PEND", "judgment"].startswith("미결")


def test_compare_status_blank_without_column(tmp_path: Path):
    path = tmp_path / "old.csv"
    _frame(ROWS).drop(columns=["status"]).to_csv(path, index=False)
    ev = _cba_table(path)
    assert (ev["status"] == "").all()
    assert not ev["judgment"].str.contains("원인").any()
