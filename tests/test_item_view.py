"""ITEM 한 장 보기 (item_view.png), 근거 표 (evidence.csv), forest 글자 칸. 합성 데이터 두 벌을 판정하고 fail_evidence 를 돌린다:
por3 (--level --blank --groups --scales: 차이·미결·LoQ zone·accuracy) 와 truth (--groups --scales: log 판정)."""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fail_evidence as fe  # noqa: E402
import golden_cases as gc  # noqa: E402
from item_view import basis_numbers  # noqa: E402
from por_doe_compare import ci_rank  # noqa: E402

CASES = {c.name: c for c in gc.CASES}
# 판정 묶음 → (fail_evidence --only ITEM, 그 ITEM 의 verdict_basis)
PICKS = {
    # scales 표가 VT 그룹을 log 로 정해 VT ITEM 은 판정 길이 log TOST, IOFF_LEAK 은 LoQ 판정, VOS_OFFSET 은 절대 허용폭
    "por3_level_blank_scales": {"VT_SHIFT": "log", "VT_NOISY_DOE": "log", "IOFF_LEAK": "loq",
                                "VOS_OFFSET": "abs"},
    "truth_scales": {"I00013": "log"},
}
# fail_evidence 원데이터 인자 (판정 인자에서 --groups·--scales 를 뺀 것)
RAW_ARGS = {"por3_level_blank_scales": gc._por3_lb, "truth_scales": gc._truth}


@pytest.fixture(scope="module")
def runs(tmp_path_factory) -> dict[str, tuple[Path, Path]]:
    """판정 묶음 → (items.csv, fail_evidence --out)."""
    base = tmp_path_factory.mktemp("item_view")
    data = gc.build_data(base / "data", ["por3", "truth"])
    out = {}
    for name, picks in PICKS.items():
        case = CASES[name]
        gc.run_case(case, data[case.data], base / name)
        items = base / name / "items.csv"
        args = [str(a) for a in RAW_ARGS[name](data[case.data])]
        fe_out = base / f"fe_{name}"
        assert fe.main(["--input", str(items), "--out", str(fe_out), "--only", ",".join(picks), *args]) == 0
        out[name] = (items, fe_out)
    return out


def _folders(fe_out: Path) -> dict[str, Path]:
    index = pd.read_csv(fe_out / fe.ITEMS_INDEX, encoding="utf-8-sig", dtype=str)
    return {i: fe_out / f for i, f in zip(index["ITEM"], index["폴더"])}


def _items(items_csv: Path) -> pd.DataFrame:
    return pd.read_csv(items_csv, encoding="utf-8-sig").set_index("ITEM")


@pytest.mark.parametrize("name", list(PICKS))
def test_folder_has_item_view_and_evidence_not_drill(runs, name):
    folders = _folders(runs[name][1])
    assert set(folders) == set(PICKS[name])
    for item, folder in folders.items():
        assert (folder / "item_view.png").stat().st_size > 0, item
        assert (folder / "evidence.csv").is_file(), item
        assert not (folder / "drill.png").exists(), item


@pytest.mark.parametrize("name", list(PICKS))
def test_evidence_ci_is_the_rank_k_order_statistic_of_raw_d(runs, name):
    items_csv, fe_out = runs[name]
    judged = _items(items_csv)
    for item, folder in _folders(fe_out).items():
        ev = pd.read_csv(folder / "evidence.csv", encoding="utf-8-sig").iloc[0]
        raw = pd.read_csv(folder / "raw.csv", encoding="utf-8-sig")
        por = raw[[c for c in raw.columns if c.startswith("POR")]].to_numpy(float)
        doe = raw["DOE"].to_numpy(float)
        log = PICKS[name][item] == "log"
        d = np.log10(np.abs(doe)) - np.log10(np.abs(por)).mean(axis=1) if log else doe - por.mean(axis=1)
        x = np.sort(d)
        n = len(d)
        k = ci_rank(n) + 1
        suffix = "_log" if log else ""
        assert ev["verdict_basis"] == PICKS[name][item] and ev["d_scale"] == ("log" if log else "linear"), item
        assert ev["n_die"] == n and ev["ci_rank_k"] == k, item
        assert ev["ci_low"] == pytest.approx(x[k - 1], rel=1e-9, abs=1e-15), item
        assert ev["ci_high"] == pytest.approx(x[n - k], rel=1e-9, abs=1e-15), item
        assert ev["ci_low"] == pytest.approx(judged.at[item, "ci_low" + suffix], rel=1e-9, abs=1e-15), item
        assert ev["ci_high"] == pytest.approx(judged.at[item, "ci_high" + suffix], rel=1e-9, abs=1e-15), item
        assert ev["ci_low_d"] == pytest.approx(x[k - 1], rel=1e-9, abs=1e-15), item
        labels = raw["COORD_X_Y"].astype(str).to_numpy()
        assert d[labels == ev["ci_low_die"]][0] == pytest.approx(x[k - 1], rel=1e-9, abs=1e-15), item
        assert d[labels == ev["ci_high_die"]][0] == pytest.approx(x[n - k], rel=1e-9, abs=1e-15), item
        assert (ev["n_d_pos"], ev["n_d_neg"], ev["n_d_zero"]) == ((d > 0).sum(), (d < 0).sum(), (d == 0).sum())
        assert ev["n_outlier_die"] == judged.at[item, "n_outlier_die"], item


def test_evidence_margins(runs):
    items_csv, fe_out = runs["por3_level_blank_scales"]
    judged = _items(items_csv)
    folders = _folders(fe_out)
    vos = pd.read_csv(folders["VOS_OFFSET"] / "evidence.csv", encoding="utf-8-sig").iloc[0]
    assert vos["verdict_basis"] == "abs" and math.isnan(vos["accuracy_margin"])
    assert vos["abs_delta"] == pytest.approx(judged.at["VOS_OFFSET", "abs_delta"])
    assert vos["delta"] == pytest.approx(vos["policy_margin"] + vos["run_margin"])
    shift = pd.read_csv(folders["VT_SHIFT"] / "evidence.csv", encoding="utf-8-sig").iloc[0]
    assert math.isnan(shift["accuracy_margin"]) and math.isnan(shift["abs_delta"])   # 그 판정이 아니면 빈 칸
    assert shift["por_over_loq"] == pytest.approx(abs(judged.at["VT_SHIFT", "por_median"]) / judged.at["VT_SHIFT", "LoQ"])
    leak = pd.read_csv(folders["IOFF_LEAK"] / "evidence.csv", encoding="utf-8-sig").iloc[0]
    assert leak["n_outlier_die"] == 20 and len(leak["outlier_dies"].split("; ")) == 20


def _forest(items_csv: Path) -> pd.DataFrame:
    return fe.forest_rows(fe.read_table(items_csv)).set_index("ITEM")


def test_forest_cells_match_item_rows(runs):
    items_csv = runs["por3_level_blank_scales"][0]
    judged = _items(items_csv)
    rows = _forest(items_csv)
    assert set(rows.index) == set(judged.index[judged["verdict_final"].isin(["차이", "미결"])])
    assert "VOS_OFFSET" not in rows.index                              # verdict 차이, verdict_final 동등
    assert list(rows["verdict_final"]) == sorted(rows["verdict_final"], key=["차이", "미결"].index)
    for item in rows.index:
        j, r = judged.loc[item], rows.loc[item]
        if basis_numbers(j.to_dict()).log:
            continue                                                      # log 판정 행은 아래 log 테스트가 본다
        margin = basis_numbers(j.to_dict()).margin
        por = abs(j["por_median"])
        assert r["이동"].endswith("%") and float(r["이동"][:-1]) == pytest.approx(100 * j["center"] / por, rel=0.05)
        assert float(r["허용폭"].lstrip("±")[:-1]) == pytest.approx(100 * margin / por, rel=0.05)
        assert r["center"] == pytest.approx(j["center"] / margin)
        assert r["ci_low"] == pytest.approx(j["ci_low"] / margin)
        assert r["ci_high"] == pytest.approx(j["ci_high"] / margin)
    assert rows.at["VT_SHIFT", "이동"] == "+6.6%" and rows.at["VT_SHIFT", "허용폭"].startswith("±")
    assert "허용폭 밖" in rows.at["VT_SHIFT", "판정 이유"]


def test_forest_log_item_uses_log_columns(runs):
    items_csv = runs["truth_scales"][0]
    j = _items(items_csv).loc["I00013"]
    r = _forest(items_csv).loc["I00013"]
    assert r["center"] == pytest.approx(j["center_log"] / j["delta_log"])
    assert float(r["이동"][:-1]) == pytest.approx(100 * (10 ** j["center_log"] - 1), rel=0.01)
    assert float(r["허용폭"].lstrip("±")[:-1]) == pytest.approx(100 * (10 ** j["delta_log"] - 1), rel=0.01)
    assert r["판정 이유"].startswith("log 값")
