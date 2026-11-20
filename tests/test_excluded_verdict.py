"""verdict '판정 제외' (통계를 낼 수 없는 ITEM) 테스트. 합성 데이터만."""
import sys

import numpy as np
import pandas as pd
import pytest

import summarize
from por_doe_compare import MIN_DIE, ORDER, V_EXCLUDED, item_status, judge

R_POLICY = 0.05


def normal_data(seed: int = 0, n: int = 200) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return 100 + rng.normal(0, 1, (n, 3)), 100 + rng.normal(0, 1, n)


def test_all_zero_is_excluded():
    Y, z = np.zeros((200, 3)), np.zeros(200)
    res, _ = judge(Y, z, R_POLICY)
    assert res["delta"] == 0
    assert res["verdict"] == V_EXCLUDED and res["zone"] == V_EXCLUDED
    assert res["reason"] == f"{V_EXCLUDED}: die 산포 0 (σ_die=0)"


def test_nan_center_is_excluded():
    # DOE에 NaN die 하나 → d = z − R에 NaN → np.median(d) = NaN → center NaN (CI 양끝은 정렬상 유한)
    Y, z = normal_data()
    z[0] = np.nan
    res, _ = judge(Y, z, R_POLICY)
    assert np.isnan(res["center"])
    assert res["verdict"] == V_EXCLUDED
    assert "중심·신뢰구간 계산 불가 (center)" in res["reason"]
    assert np.isfinite(res["delta"]) and res["delta"] > 0


def test_all_same_value_is_excluded():
    Y, z = np.full((200, 3), 400.0), np.full(200, 400.0)
    res, _ = judge(Y, z, R_POLICY)
    assert res["delta"] > 0 and res["sigma_die"] == 0 and res["sigma_run"] == 0
    assert res["verdict"] == V_EXCLUDED
    assert res["reason"] == f"{V_EXCLUDED}: die 산포 0 (σ_die=0)"
    assert res["center"] == 0 and res["por_median"] == 400.0     # out 값은 그대로 채움


def test_majority_flat_is_excluded():
    Y, z = normal_data()
    Y[:120], z[:120] = 100.0, 100.0      # die 60%가 회차마다 같은 값 → 회차 차의 MAD도 0이라 σ_die = 0
    res, _ = judge(Y, z, R_POLICY)
    assert res["sigma_die"] == 0
    assert res["verdict"] == V_EXCLUDED
    assert res["reason"] == f"{V_EXCLUDED}: die 산포 0 (σ_die=0)"     # 둘 다면 σ_die 문구
    assert "산포 0" in item_status(Y, z, res["delta"])["status"].split(";")


def test_minority_flat_keeps_normal_verdict():
    Y, z = normal_data()
    Y[:80], z[:80] = 100.0, 100.0        # die 40%가 같은 값
    res, _ = judge(Y, z, R_POLICY)
    assert res["verdict"] != V_EXCLUDED
    assert res["zone"] == "정량"


def test_few_dies_still_undecided():
    n = MIN_DIE - 1
    Y, z = np.zeros((n, 3)), np.zeros(n)
    res, _ = judge(Y, z, R_POLICY)
    assert res["verdict"] == "미결" and res["zone"] == "die 부족"


def test_order_puts_excluded_last():
    s = pd.Series([V_EXCLUDED, "동등", "차이", "미결"], name="verdict")
    assert s.sort_values(key=lambda v: v.map(ORDER)).iloc[-1] == V_EXCLUDED


def test_summarize_counts_excluded(tmp_path, monkeypatch, capsys):
    base = {"UNIT": "A", "n_die": 200, "POR1_mean": 1.0, "POR2_mean": 1.0, "DOE_mean": 1.0, "por_median": 1.0,
            "center": 0.0, "ci_low": 0.0, "ci_high": 0.0, "delta": 0.05, "n_outlier_die": 0,
            "run_margin": 0.0, "policy_margin": 0.05, "limit_source": "POR 반복", "sigma_die": 0.0,
            "ttest": "유의차 없음", "por_ttest_sig": "0/1"}
    rows = [
        {**base, "ITEM": "VT1", "zone": "정량", "verdict": "동등", "reason": "90% 신뢰구간이 ±Δ 안"},
        {**base, "ITEM": "VT2", "zone": V_EXCLUDED, "verdict": V_EXCLUDED,
         "reason": f"{V_EXCLUDED}: Δ가 0 이하이거나 유효하지 않음 (Δ=0); "
                   f"{V_EXCLUDED}: 모든 die가 같은 값 (σ_die=0, σ_run=0, 고정값 100%)"},
        {**base, "ITEM": "VT3", "zone": V_EXCLUDED, "verdict": V_EXCLUDED,
         "reason": f"{V_EXCLUDED}: 모든 die가 같은 값 (σ_die=0, σ_run=0, 고정값 100%)"},
    ]
    path = tmp_path / "items.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(sys, "argv", ["summarize.py", str(path)])
    summarize.main()
    out = capsys.readouterr().out
    assert f"{V_EXCLUDED} ITEM: 2 (모든 die가 같은 값 2, Δ가 0 이하이거나 유효하지 않음 1)" in out
    table = out.split("== 구간 x 판정")[1].split("==")[0]
    assert V_EXCLUDED in table
    assert "== 동등 아닌 사유" not in out     # 판정 제외만 있으면 사유 표가 없음


EXCLUDED_REASON = f"{V_EXCLUDED}: Δ가 0 이하이거나 유효하지 않음 (Δ=0)"


def summary_frame_with_excluded() -> pd.DataFrame:
    """정량 2개, LoQ 미만 1개, 판정 제외 1개(Δ=0)."""
    return pd.DataFrame({
        "ITEM": ["Q_IN", "Q_HIGH", "L_FLOOR", "X_FLAT"],
        "zone": ["정량", "정량", "검출한계 이하", V_EXCLUDED],
        "verdict": ["동등", "차이", "동등", V_EXCLUDED],
        "reason": ["90% 신뢰구간이 ±Δ 안", "shift +5가 ±Δ(1) 밖",
                   "<LoQ 보고 일치 (이동이 ±Δ 안)", EXCLUDED_REASON],
        "center": [0.1, 5.0, 0.0, 0.0],
        "ci_low": [-0.2, 4.0, -0.1, 0.0],
        "ci_high": [0.3, 6.0, 0.1, 0.0],
        "delta": [1.0, 1.0, 1.0, 0.0],
        "doe_center": [10.0, 10.0, 0.5, 400.0],
        "LoQ": [1.0, 1.0, 1.0, 1.0],
    })


def test_verdict_category_excluded():
    from plot_verdicts import CATEGORY_ORDER, verdict_category
    row = pd.Series({"verdict": V_EXCLUDED, "reason": EXCLUDED_REASON, "zone": V_EXCLUDED})
    assert verdict_category(row) == V_EXCLUDED
    assert V_EXCLUDED not in CATEGORY_ORDER     # 요약 그림에는 그리지 않음


def test_split_and_plots_skip_excluded(tmp_path):
    from plot_verdicts import plot_loq, plot_summary, select_detail_items, split_summary
    frame = summary_frame_with_excluded()
    main, loq = split_summary(frame)
    assert set(main["ITEM"]) == {"Q_IN", "Q_HIGH"}
    assert set(loq["ITEM"]) == {"L_FLOOR"}

    with pytest.warns(RuntimeWarning, match="판정 제외 1개") as record:
        paths = plot_summary(frame, tmp_path / "plots", dpi=60)
    assert [p.name for p in paths] == ["summary_001.png"] and paths[0].stat().st_size > 0
    assert any("판정 제외 1개 (요약 그림에서 뺌)" in str(w.message) for w in record)

    loq_path = plot_loq(frame, tmp_path / "plots", dpi=60)
    assert loq_path.stat().st_size > 0
    assert select_detail_items(frame) == ["Q_HIGH"]


def test_fail_evidence_excluded_judgement(tmp_path):
    import fail_evidence as fe
    df = pd.DataFrame({
        "ID": ["EQ1", "X_FLAT"],
        "verdict": ["동등", V_EXCLUDED],
        "por_median": ["1", "400"], "DOE_mean": ["1", "400"], "POR1_mean": ["1", "400"],
        "POR2_mean": ["1", "400"], "center": ["0", "0"], "ci_low": ["0", "0"],
        "ci_high": ["0", "0"], "delta": ["0.05", "0"], "LoQ": ["0.1", "0.1"],
    })
    table = fe.evidence_table(df).set_index("ID")
    assert table.at["X_FLAT", "judgement"] == fe.J_EXCL == V_EXCLUDED
    assert table.at["EQ1", "judgement"] == fe.J_SKIP
    text = fe.summary_text(table.reset_index())
    assert f"  {V_EXCLUDED}: 1\n" in text
    assert f"  {fe.J_SKIP}: 1\n" in text
    assert fe.plot_forest(table.reset_index(), tmp_path / "forest.png").stat().st_size > 0


# ---- compare_before_after / group_summary: 판정 제외는 σ 집계에서 빼고 따로 셈 ----
from pathlib import Path  # noqa: E402

CMP_DATA = Path(__file__).parent / "data"
CMP_BEFORE = CMP_DATA / "compare_ba_before.tsv"
CMP_AFTER = CMP_DATA / "compare_ba_after.tsv"
EXCL_LINE = f"- {V_EXCLUDED} (기존 또는 개선, σ 집계에서 뺌)"


def _after_with_a2_excluded(tmp_path) -> Path:
    """개선 쪽 SYNTH_A2(σ_die 12→5, 하락)만 판정 제외로 바꾼 합성 표."""
    text = CMP_AFTER.read_text(encoding="utf-8")
    old = "SYNTH_A2\t정량\t미결\t경계"
    assert old in text
    path = tmp_path / "after_excl.tsv"
    path.write_text(text.replace(old, f"SYNTH_A2\t{V_EXCLUDED}\t{V_EXCLUDED}\t{EXCLUDED_REASON}"), encoding="utf-8")
    return path


def _compare(tmp_path, after: Path, name: str) -> Path:
    from compare_before_after import main as compare_main
    out = tmp_path / name
    assert compare_main(["compare", str(CMP_BEFORE), str(after), "-o", str(out)]) == 0
    return out


def test_compare_excluded_left_out_of_sigma_counts(tmp_path):
    out = _compare(tmp_path, _after_with_a2_excluded(tmp_path), "cmp_excl")
    text = (out / "summary.txt").read_text(encoding="utf-8")
    assert f"{EXCL_LINE}: 1  (SYNTH_A2)" in text
    # 공통 5개 중 σ_die 하락 4개(A1·A2·A4·A5) → A2를 빼면 3/4
    assert "σ 변화 (공통 전체, 정렬 의심 포함 4건)" in text
    assert "- σ_die 하락: 3/4" in text
    # 판정 전이 표에는 남음 (미결→판정 제외)
    trans = text.split("판정 전이")[1]
    assert V_EXCLUDED in trans
    # compare.csv 행은 그대로
    df = pd.read_csv(out / "compare.csv", encoding="utf-8-sig").set_index("ITEM")
    assert df.loc["SYNTH_A2", "verdict_after"] == V_EXCLUDED
    assert df.loc["SYNTH_A2", "presence"] == "matched"


def test_compare_without_excluded_has_no_line(tmp_path):
    out = _compare(tmp_path, CMP_AFTER, "cmp_plain")
    text = (out / "summary.txt").read_text(encoding="utf-8")
    assert V_EXCLUDED not in text
    assert "- σ_die 하락: 4/5" in text


def test_compare_excluded_id_list_truncated():
    from compare_before_after import _id_list
    ids = [f"X{i}" for i in range(13)]
    assert _id_list(ids) == ", ".join(ids[:10]) + " 외 3개"
    assert _id_list(ids[:2]) == "X0, X1"


def _group_summary(monkeypatch, cmp_dir: Path, name: str) -> Path:
    import group_summary
    groups = cmp_dir / "groups.csv"
    groups.write_text(
        "ITEM,group\nSYNTH_A1,G1\nSYNTH_A2,G1\nSYNTH_A3,G2\nSYNTH_A4,G2\nSYNTH_A5,G2\n",
        encoding="utf-8",
    )
    out = cmp_dir.parent / name
    monkeypatch.setattr(sys, "argv", [
        "group_summary.py", "--compare", str(cmp_dir / "compare.csv"), "--groups", str(groups), "--out", str(out),
    ])
    group_summary.main()
    return out


def test_group_summary_excluded_column(tmp_path, monkeypatch, capsys):
    cmp_dir = _compare(tmp_path, _after_with_a2_excluded(tmp_path), "cmp_excl")
    capsys.readouterr()
    out = _group_summary(monkeypatch, cmp_dir, "gs_excl")
    printed = capsys.readouterr().out
    assert f"분석 ITEM: 4개 (정렬 의심 포함), {V_EXCLUDED} 1개 뺌" in printed
    tab = pd.read_csv(out / "group_summary.csv", encoding="utf-8-sig").set_index("그룹")
    assert tab.loc["전체", V_EXCLUDED] == 1
    assert tab.loc["G1", V_EXCLUDED] == 1 and tab.loc["G2", V_EXCLUDED] == 0
    assert tab.loc["G1", "ITEM 수"] == 1 and tab.loc["전체", "ITEM 수"] == 4
    assert tab.loc["전체", "제외(짝 없음)"] == 2     # B1·C1만, 판정 제외는 따로
    vt = pd.read_csv(out / "verdict_by_group.csv", encoding="utf-8-sig", index_col=0)
    assert vt.loc["G1", f"미결→{V_EXCLUDED}"] == 1
    st = pd.read_csv(out / "stability_by_group.csv", encoding="utf-8-sig").set_index("그룹")
    assert st.loc["전체", "ITEM 수"] == 4


def test_group_summary_without_excluded_has_no_column(tmp_path, monkeypatch, capsys):
    cmp_dir = _compare(tmp_path, CMP_AFTER, "cmp_plain")
    capsys.readouterr()
    out = _group_summary(monkeypatch, cmp_dir, "gs_plain")
    printed = capsys.readouterr().out
    assert "분석 ITEM: 5개 (정렬 의심 포함)\n" in printed
    tab = pd.read_csv(out / "group_summary.csv", encoding="utf-8-sig")
    assert V_EXCLUDED not in tab.columns
