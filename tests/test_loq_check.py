"""loq_check.py: LoQ 아래 ITEM 점검. 합성 ITEM 으로 동등이 된 이유, 답을 아는 비교의 잡힘, 판정 불변, 시험 못 함."""
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import loq_check
import report
from por_doe_compare import add_final_verdict, judge_item, loq_verdict, tost

ROOT = Path(__file__).resolve().parents[1]
POR = ["POR1", "POR2", "POR3"]


def judged(name: str, Y: np.ndarray, z: np.ndarray, route: str = "LoQ 판정") -> dict:
    """por_doe_compare 판정 그대로 (judge_item + add_final_verdict) 의 items.csv 한 행."""
    g = pd.DataFrame(Y, columns=POR[:Y.shape[1]]).assign(DOE=z)
    res, _ = judge_item(name, g, POR[:Y.shape[1]], {name: "A"}, 0.05, {}, pd.DataFrame(), {})
    row = {**res, "scale": "item", "route": route, "cls_level": "바닥 아래", "cls_resolution": "연속"}
    return add_final_verdict(pd.DataFrame([row])).iloc[0].to_dict()


def floor_item(rng, n: int = 61, J: int = 3, mu: float = 6.0):
    """바닥 잡음 σ 1 (LoQ 10), die 값 lognormal 0.15 dec, 회차 offset 0.1. DOE 는 변화 없음 (tests/test_review.py 와 같은 꼴)."""
    x = mu * 10 ** (0.15 * rng.standard_normal(n))
    off = 0.1 * rng.standard_normal(J + 1)
    return x[:, None] + off[:J] + rng.standard_normal((n, J)), x + off[J] + rng.standard_normal(n)


def build(folder: Path, rows: list[dict], raw: dict) -> loq_check.LoqBook:
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "items.csv", index=False, encoding="utf-8-sig")
    items = pd.read_csv(folder / "items.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    loq_check.build(folder, items, raw)
    return loq_check.load(folder)


@pytest.fixture(scope="module")
def population(tmp_path_factory):
    """SAME: POR 0.55×LoQ 근처 30개, LOW: POR 0.15×LoQ 근처 20개. 모두 DOE 가 변하지 않았다."""
    rng = np.random.default_rng(7)
    raw = {f"SAME_{i:02d}": floor_item(rng) for i in range(30)}
    raw |= {f"LOW_{i:02d}": floor_item(rng, mu=1.5) for i in range(20)}
    rows = [judged(k, *v) for k, v in raw.items()]
    folder = tmp_path_factory.mktemp("loq")
    return build(folder, rows, raw), folder


def trials_share(folder: Path, prefix: str, level: float, col: str) -> float:
    t = pd.read_csv(folder / "loq" / loq_check.TRIALS_CSV, encoding="utf-8-sig")
    t = t[t["ITEM"].str.startswith(prefix) & np.isclose(t["level"], level)]
    hit = t[col].astype(str).isin(loq_check.CAUGHT) if col.startswith("verdict") else t[col].astype(str).eq("True")
    return float(hit.mean())


def level_row(book: loq_check.LoqBook, level: float) -> pd.Series:
    return book.levels.set_index("level").loc[level]


def test_population_is_below_loq_and_all_tested(population):
    book, _ = population
    assert book.summary.ledger.n_zone == 50
    assert book.check.n_items == 50 and book.check.n_runs == 3 and not book.check.untested


def test_no_change_is_rarely_flagged_but_plain_tost_flags_it(population):
    book, folder = population
    assert trials_share(folder, "SAME_", 0.0, "verdict_final") <= 0.01
    null = level_row(book, loq_check.NO_CHANGE)
    assert null["caught_final"] <= 0.01
    assert null["caught_tost"] >= null["caught_final"] + 0.2, "LoQ 규칙이 막는 오경보가 보여야 함"
    assert book.check.at("final", loq_check.NO_CHANGE).n == 150


def test_change_well_above_loq_is_caught(population):
    book, _ = population
    assert level_row(book, 2.0)["caught_final"] >= 0.99
    assert level_row(book, 1.5)["caught_final"] >= 0.99


def test_change_that_stays_below_loq_passes_and_is_shown_by_tost_and_review(population):
    _, folder = population
    assert trials_share(folder, "LOW_", 0.5, "verdict_final") <= 0.05, "×3 이어도 DOE 가 LoQ 아래면 판정은 동등"
    assert trials_share(folder, "LOW_", 0.5, "verdict_tost") >= 0.9
    assert trials_share(folder, "LOW_", 0.5, "review_flag") >= 0.9


def test_levels_have_denominators_and_ranges(population):
    book, folder = population
    t = book.levels.set_index("level")
    assert list(t.index) == list(loq_check.LEVELS)
    items = pd.read_csv(folder / "items.csv", encoding="utf-8-sig")
    base, loq, delta = (items[c].to_numpy(float) for c in ("por_median", "LoQ", "delta"))
    for u in loq_check.GRID:
        real = int((np.abs(np.sign(base) * u * loq - base) > delta).sum())
        assert t.loc[u, "n_items"] == real, f"{u}×LoQ: 허용폭 Δ 보다 큰 변화만 센다"
        assert t.loc[u, "n_comparisons"] == 3 * real
    assert t.loc[loq_check.NO_CHANGE, "n_items"] == 50 and t.loc[loq_check.NO_CHANGE, "n_comparisons"] == 150
    assert t["n_items"].min() < 50, "POR 수준 근처 수준에서 빠지는 ITEM 이 있어야 시험이 된다"
    t = t.reset_index()
    assert (t["caught_final_lo"] <= t["caught_final"] + 1e-12).all()
    assert (t["caught_final"] <= t["caught_final_hi"] + 1e-12).all()
    review_rows = t["level"].isin(loq_check.REVIEW_LEVELS)
    assert t.loc[review_rows, "caught_review"].notna().all() and t.loc[~review_rows, "caught_review"].isna().all()


def test_trials_hold_only_changes_larger_than_delta(population):
    _, folder = population
    t = pd.read_csv(folder / "loq" / loq_check.TRIALS_CSV, encoding="utf-8-sig")
    delta = pd.read_csv(folder / "items.csv", encoding="utf-8-sig").set_index("ITEM")["delta"]
    moved = t[t["level"] != loq_check.NO_CHANGE]
    assert (moved["shift"].abs() > moved["ITEM"].map(delta)).all()
    assert len(t[t["level"] == loq_check.NO_CHANGE]) == 150


def test_shift_moves_true_level_to_signed_target(tmp_path):
    """음수 POR: 참 DOE 수준이 −u·LoQ 로 간다 (s = −u·LoQ − base). 0 중심 POR 은 + 쪽 (sgn = +1)."""
    rng = np.random.default_rng(13)
    Y, z = floor_item(rng)
    Y, z = -Y, -z
    row = judged("NEG", Y, z)
    assert row["por_median"] < 0 and row["zone"] in ("검출한계 이하", "검출~정량")
    u = 1.5
    s = loq_check.shifts(row, (u,))[0]
    assert s == pytest.approx(-u * row["LoQ"] - row["por_median"])
    build(tmp_path / "A1", [row], {"NEG": (Y, z)})
    t = pd.read_csv(tmp_path / "A1" / "loq" / loq_check.TRIALS_CSV, encoding="utf-8-sig")
    at = t[np.isclose(t["level"], u)]
    level = (row["por_median"] + at["center"]) / row["LoQ"]
    assert np.allclose(level, -u, atol=0.15), level.tolist()
    assert ((row["por_median"] + at["ci_high"]) < -row["LoQ"]).all()
    assert at["verdict_final"].isin(loq_check.CAUGHT).all()
    zero = {"por_median": 0.0, "LoQ": 10.0}
    assert list(loq_check.shifts(zero, (0.0, 0.5, 2.0))) == [0.0, 5.0, 20.0]


def test_item_threshold_and_why(population):
    book, _ = population
    t = book.items.set_index("ITEM")
    same = t.loc["SAME_00"]
    assert same["tested"] == loq_check.TESTED and 1.0 <= same["catch_level"] <= 1.3
    assert same["catch_ratio"] == pytest.approx(same["catch_level"] / abs(same["por_loq"]))
    assert "회차 비교 3번이 모두 잡힘" in same["why"]


def test_rerun_is_deterministic(population, tmp_path):
    book, folder = population
    before = {p.name: p.read_bytes() for p in (folder / "loq").glob("*.csv")}
    items = pd.read_csv(folder / "items.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    rng = np.random.default_rng(7)
    raw = {f"SAME_{i:02d}": floor_item(rng) for i in range(30)}
    raw |= {f"LOW_{i:02d}": floor_item(rng, mu=1.5) for i in range(20)}
    loq_check.build(folder, items, raw)
    assert {p.name: p.read_bytes() for p in (folder / "loq").glob("*.csv")} == before


def test_items_csv_untouched(tmp_path):
    rng = np.random.default_rng(3)
    raw = {f"SAME_{i:02d}": floor_item(rng) for i in range(5)}
    folder = tmp_path / "A1"
    folder.mkdir()
    pd.DataFrame([judged(k, *v) for k, v in raw.items()]).to_csv(folder / "items.csv", index=False,
                                                                 encoding="utf-8-sig")
    digest = hashlib.sha256((folder / "items.csv").read_bytes()).hexdigest()
    items = pd.read_csv(folder / "items.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    copy = items.copy()
    loq_check.build(folder, items, raw)
    assert hashlib.sha256((folder / "items.csv").read_bytes()).hexdigest() == digest
    pd.testing.assert_frame_equal(items, copy)


def hand_row(name: str, lo: float, hi: float, **extra) -> dict:
    """POR 중앙값 3, LoQ 10, Δ 2 (SOP 2단계 그림용 예). 2단계 판정은 loq_verdict 그대로."""
    base, loq, delta, c = 3.0, 10.0, 2.0, (lo + hi) / 2
    verdict, reason = loq_verdict(c, lo, hi, delta, base, loq)
    return {"ITEM": name, "UNIT": "A", "zone": "검출~정량", "verdict": verdict, "reason": reason, "center": c,
            "ci_low": lo, "ci_high": hi, "delta": delta, "por_median": base, "LoQ": loq, "LoD": 3.29,
            "route": "LoQ 판정", "cls_level": "바닥 아래", **extra}


def test_ledger_finds_each_pass_kind():
    rows = [hand_row("P_SHIFT", -1.5, 1.5), hand_row("P_BELOW", 2.5, 5.5), hand_row("P_CROSS", 6, 9),
            hand_row("P_ABS", 9, 12, route="절대 허용폭", cls_level="0 중심", abs_delta=20.0,
                     verdict_abs=tost(10.5, 9, 12, 20.0)[0]),
            hand_row("P_DIFF", 9, 12), {**hand_row("OTHER", 0, 1), "zone": "정량"}]
    items = add_final_verdict(pd.DataFrame(rows))
    led = loq_check.ledger_frame(items, None).set_index("ITEM")
    assert "OTHER" not in led.index
    assert led["pass_kind"].to_dict() == {"P_SHIFT": loq_check.K_SHIFT, "P_BELOW": loq_check.K_BELOW,
                                          "P_CROSS": loq_check.K_CROSS, "P_ABS": loq_check.K_STAGE3, "P_DIFF": "차이"}
    assert led.loc["P_ABS", "verdict"] == "차이" and led.loc["P_ABS", "verdict_final"] == "동등"
    assert set(led.loc[["P_BELOW", "P_CROSS", "P_ABS"], "verdict_tost"]) <= {"차이", "미결"}
    assert led.loc["P_SHIFT", "verdict_tost"] == "동등"
    assert led.loc["P_BELOW", "doe_hi_loq"] == pytest.approx(0.85)


def test_summary_names_stage3_route_and_counts_rule_passes(tmp_path):
    rows = [hand_row("P_SHIFT", -1.5, 1.5), hand_row("P_BELOW", 2.5, 5.5),
            hand_row("P_ABS", 9, 12, route="절대 허용폭", cls_level="0 중심", abs_delta=20.0, verdict_abs="동등")]
    folder = tmp_path / "A1"
    folder.mkdir()
    add_final_verdict(pd.DataFrame(rows)).to_csv(folder / "items.csv", index=False, encoding="utf-8-sig")
    book = loq_check.load(folder)
    g = book.summary.ledger
    assert book.check is None
    assert g.passes == {loq_check.K_SHIFT: 1, loq_check.K_BELOW: 1, "판정 길 (절대 허용폭)": 1}
    assert g.rule_pass == 2 and g.rule_flagged is None
    assert book.headline_lines()[0] == "LoQ 아래 ITEM 3개 (전체 3개 중): 동등 3 · 미결 0 · 차이 0"
    assert "시험은 아직 없음 (dcc.py loq A1)" in book.headline_lines()


def test_route_that_cannot_be_rejudged_is_untested(tmp_path):
    """rescaled_verdicts 는 다시 판정 못 하는 판정 길 열을 원래 값으로 둔다. 그런 ITEM 은 시험 못 함이어야 한다."""
    rng = np.random.default_rng(5)
    raw = {name: floor_item(rng) for name in ("OK", "ABS_STALE", "ABS_OK", "LOG_ROUTE")}
    rows = [judged("OK", *raw["OK"]),
            {**judged("ABS_STALE", *raw["ABS_STALE"], route="절대 허용폭"), "cls_level": "0 중심", "abs_delta": "",
             "verdict_abs": "판정 제외"},
            {**judged("ABS_OK", *raw["ABS_OK"], route="절대 허용폭"), "cls_level": "0 중심", "abs_delta": 10.0,
             "verdict_abs": "동등"},
            judged("LOG_ROUTE", *raw["LOG_ROUTE"], route="log TOST")]
    book = build(tmp_path / "A1", rows, raw)
    t = book.items.set_index("ITEM")
    assert t.loc["OK", "tested"] == loq_check.TESTED
    assert t.loc["ABS_OK", "tested"] == loq_check.TESTED
    assert "verdict_abs" in t.loc["ABS_STALE", "tested"] and "다시 낼 수 없음" in t.loc["ABS_STALE", "tested"]
    assert "log TOST" in t.loc["LOG_ROUTE", "tested"]
    assert book.check.n_items == 2 and sum(book.check.untested.values()) == 2
    trials = pd.read_csv(tmp_path / "A1" / "loq" / loq_check.TRIALS_CSV, encoding="utf-8-sig")
    assert set(trials["ITEM"]) == {"OK", "ABS_OK"}


def test_abs_route_trials_use_abs_tolerance(tmp_path):
    """절대 허용폭 길: 2단계가 차이여도 ±abs_delta 안이면 최종 동등. abs_delta = LoQ 면 1.5×LoQ 도 다 잡히지는 않는다."""
    rng = np.random.default_rng(11)
    Y, z = floor_item(rng)
    row = {**judged("ABS", Y, z, route="절대 허용폭"), "cls_level": "0 중심"}
    row |= {"abs_delta": row["LoQ"], "verdict_abs": tost(row["center"], row["ci_low"], row["ci_high"], row["LoQ"])[0]}
    build(tmp_path / "A1", [row], {"ABS": (Y, z)})
    t = pd.read_csv(tmp_path / "A1" / "loq" / loq_check.TRIALS_CSV, encoding="utf-8-sig")
    at = t[np.isclose(t["level"], 1.2)]
    assert (at["verdict_rule"] == "차이").all() and (at["verdict_final"] == "동등").all()


def visible(path: Path) -> str:
    return re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "", path.read_text(encoding="utf-8"))


def xlsx_text(path: Path) -> tuple[list[str], str]:
    with zipfile.ZipFile(path) as z:
        sheets = re.findall(r'<sheet name="([^"]+)"', z.read("xl/workbook.xml").decode())
        body = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
    return sheets, body


def test_reports_render_the_same_book(population, tmp_path):
    book, folder = population
    out = tmp_path / "A1"
    shutil.copytree(folder, out)
    written = report.write_reports(out)
    assert out / "loq" / "report.html" in written
    judge = visible(out / "report.html").split('id="kpi"')[1].split("</details>")[0]
    assert "LoQ 요약" in judge and book.headline_lines()[0] in judge and 'href="loq/report.html"' in judge
    page = visible(out / "loq" / "report.html")
    for title in ("한 줄 답", "동등이 된 이유", "시험 결과 (POR 회차로 만든 비교)", "LoQ 규칙으로 동등이 된 ITEM",
                  "LoQ 확인 필요", "방법과 한계", "한계 영역을 전부 통과시켰나?"):
        assert title in page, title
    assert html.escape(book.headline_lines()[2]) in page
    rule = book.items.loc[book.items["pass_kind"].isin(loq_check.RULE_PASSES), "ITEM"]
    assert len(rule) and all(f"<td>{item}</td>" in page for item in rule)
    sheets, body = xlsx_text(out / "loq" / loq_check.WORKBOOK)
    assert sheets == [loq_check.SUMMARY, loq_check.REASONS, loq_check.LEVELS_SHEET, loq_check.ITEMS_SHEET]
    assert all(item in body for item in book.items["ITEM"])


def test_anonymous_loq_report_has_no_item_names(population, tmp_path):
    _, folder = population
    out = tmp_path / "A1"
    shutil.copytree(folder, out)
    assert report.main([str(out), "--anon"]) == 0
    page = visible(out / "loq" / "report_anon.html")
    assert re.search(r"<td>ITEM\d{4}</td>", page)
    assert not re.search(r"(SAME|LOW)_\d\d", page)
    assert not re.search(r"(SAME|LOW)_\d\d", visible(out / "report_anon.html"))
    _, body = xlsx_text(out / "loq" / loq_check.WORKBOOK_ANON)
    assert not re.search(r"(SAME|LOW)_\d\d", body)


def test_judge_block_says_check_has_not_run(tmp_path):
    rows = [hand_row("P_BELOW", 2.5, 5.5)]
    folder = tmp_path / "B7"
    folder.mkdir()
    add_final_verdict(pd.DataFrame(rows)).to_csv(folder / "items.csv", index=False, encoding="utf-8-sig")
    written = report.write_reports(folder)
    assert written == [folder / "report.html"]
    assert "시험은 아직 없음 (dcc.py loq B7)" in visible(folder / "report.html")


def test_dcc_loq_runs_check_once_and_writes_both_reports(tmp_path):
    data = tmp_path / "por3"
    run_py(ROOT / "examples" / "make_por3_data.py", data)
    por = "\n      ".join(str(data / f"por_run{k}") for k in (1, 2, 3))
    cfg = tmp_path / "combos.ini"
    cfg.write_text(f"[A1]\npor = {por}\ndoe = {data / 'doe'}\nout = {tmp_path / 'out'}\n", encoding="utf-8")
    proc = run_py(ROOT / "dcc.py", "loq", "A1", "--anon", "--config", cfg)
    assert proc.stdout.count("] loq_check") == 1, proc.stdout
    loq = tmp_path / "out" / "A1" / "loq"
    assert (loq / "report_anon.html").is_file() and (loq / loq_check.WORKBOOK_ANON).is_file()
    proc = run_py(ROOT / "dcc.py", "loq", "A1", "--config", cfg)
    assert "por_doe_compare" not in proc.stdout
    assert (loq / "report.html").is_file() and (loq / "report_anon.html").is_file()
    assert {p.name for p in loq.glob("*.csv")} == {loq_check.ITEMS_CSV, loq_check.LEVELS_CSV, loq_check.TRIALS_CSV}


def run_py(*args) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    proc = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, env=env, capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    return proc


def test_no_loq_items_still_writes_empty_outputs(tmp_path):
    folder = tmp_path / "A1"
    folder.mkdir()
    items = add_final_verdict(pd.DataFrame([{**hand_row("Q1", -1, 1), "zone": "정량"}]))
    items.to_csv(folder / "items.csv", index=False, encoding="utf-8-sig")
    loq_check.build(folder, pd.read_csv(folder / "items.csv", dtype=str, keep_default_na=False), {})
    book = loq_check.load(folder)
    assert book.summary.ledger.n_zone == 0 and book.check.n_items == 0
    assert "시험할 수 있는 LoQ 아래 ITEM 이 없다." in book.headline_lines()
    assert folder / "loq" / "report.html" in report.write_reports(folder)
