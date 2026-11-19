"""판정 요약 그림, 한글 폰트, 재계산 결과의 회귀 테스트."""
import math
import os
import re
import subprocess
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

# plot_verdicts selects Agg before pyplot is imported.
from plot_verdicts import (
    CATEGORY_ORDER, KOREAN_TEXTS, build_parser, clip_summary, configure_font, detail_text,
    plot_summary, recompute, safe_item_name, split_summary, summary_legend_labels,
    verdict_category,
)
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "examples" / "make_por3_data.py"


def run_script(script: Path, args) -> subprocess.CompletedProcess:
    """test_refactor.py와 같은 방식으로 repo 모듈을 찾게 하여 CLI를 실행한다."""
    env = os.environ.copy()
    old_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + old_pythonpath if old_pythonpath else "")
    return subprocess.run(
        [sys.executable, str(script), *[str(arg) for arg in args]],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def raw_args(data: Path) -> list:
    return [
        "--por", data / "por_run1",
        "--por", data / "por_run2",
        "--por", data / "por_run3",
        "--doe", data / "doe",
        "--r", "0.05",
        "--level", data / "level.csv",
        "--blank", data / "blank",
        "--blank-map", data / "blank_map.csv",
        "--key", "WAFERID,COORD_X_Y,ITEM",
        "--encoding", "auto",
    ]


@pytest.fixture
def por3_results(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "por3"
    out = tmp_path / "out"
    run_script(GENERATOR, [data])
    run_script(ROOT / "por_doe_compare.py", [*raw_args(data), "--out", out])
    return data, out / "items.csv"


def same_float(expected: float, actual: float) -> bool:
    if pd.isna(expected) and pd.isna(actual):
        return True
    if repr(float(expected)) == repr(float(actual)):
        return True
    return math.isclose(float(expected), float(actual), rel_tol=1e-12, abs_tol=0.0)


def test_recompute_matches_every_items_csv_result(por3_results: tuple[Path, Path]):
    data, items_csv = por3_results
    args = build_parser().parse_args([str(arg) for arg in raw_args(data)])
    actual = recompute(args).set_index("ITEM")
    expected = pd.read_csv(items_csv, encoding="utf-8-sig").set_index("ITEM")

    assert set(actual.index) == set(expected.index)
    assert not actual.index.duplicated().any()
    mismatches = []
    for item in expected.index:
        for column in ("center", "ci_low", "ci_high", "delta"):
            if not same_float(expected.at[item, column], actual.at[item, column]):
                mismatches.append(
                    f"{item} {column}: items.csv={expected.at[item, column]!r}, "
                    f"recompute={actual.at[item, column]!r}"
                )
        for column in ("verdict", "reason"):
            if expected.at[item, column] != actual.at[item, column]:
                mismatches.append(
                    f"{item} {column}: items.csv={expected.at[item, column]!r}, "
                    f"recompute={actual.at[item, column]!r}"
                )

    assert not mismatches, "\n".join(mismatches)


def test_summary_and_loq_pngs_are_written(por3_results: tuple[Path, Path], tmp_path: Path):
    _, items_csv = por3_results
    plots = tmp_path / "plots"

    completed = run_script(ROOT / "plot_verdicts.py", [
        "--items-csv", items_csv,
        "--out", plots,
        "--dpi", "80",
    ])

    assert completed.returncode == 0
    for name in ("summary_001.png", "summary_loq.png"):
        path = plots / name
        assert path.is_file(), f"만들어지지 않은 그림: {path}"
        assert path.stat().st_size > 0


def test_noisy_doe_item_is_undecided_for_resolution(por3_results: tuple[Path, Path]):
    _, items_csv = por3_results
    items = pd.read_csv(items_csv, encoding="utf-8-sig").set_index("ITEM")
    row = items.loc["VT_NOISY_DOE"]

    assert row["zone"] == "정량"
    assert row["verdict"] == "미결"
    assert "해상도 부족" in row["reason"]
    assert (row["ci_high"] - row["ci_low"]) / 2 >= row["delta"]
    assert verdict_category(row) == "미결-해상도 부족"


def summary_frame() -> pd.DataFrame:
    """정량 3개(하나는 +쪽, 하나는 -쪽 범위 밖)와 LoQ 미만 zone 2개."""
    return pd.DataFrame({
        "ITEM": ["Q_IN", "Q_HIGH", "Q_LOW", "L_FLOOR", "L_MID"],
        "zone": ["정량", "정량", "정량", "검출한계 이하", "검출~정량"],
        "verdict": ["동등", "차이", "미결", "동등", "동등"],
        "reason": [
            "90% 신뢰구간이 ±Δ 안", "shift +5가 ±Δ(1) 밖", "경계 (신뢰구간이 Δ에 걸침)",
            "<LoQ 보고 일치 (이동이 ±Δ 안)", "<LoQ 보고 일치 (이동이 ±Δ 안)",
        ],
        "center": [0.1, 5.0, -0.5, 0.0, 0.2],
        "ci_low": [-0.2, 4.0, -4.0, -0.1, 0.1],
        "ci_high": [0.3, 6.0, 0.5, 0.1, 0.3],
        "delta": [1.0, 1.0, 1.0, 1.0, 1.0],
    })


def test_split_summary_keeps_loq_zone_items_out_of_main_panel():
    main, loq = split_summary(summary_frame())

    assert set(main["ITEM"]) == {"Q_IN", "Q_HIGH", "Q_LOW"}
    assert set(loq["ITEM"]) == {"L_FLOOR", "L_MID"}


def test_clip_summary_marks_items_beyond_xlim_and_legend_counts_both_panels():
    main, loq = split_summary(summary_frame())
    clipped = clip_summary(main, 3.0).set_index("ITEM")

    assert bool(clipped.at["Q_HIGH", "_cut_high"]) and not bool(clipped.at["Q_HIGH", "_center_in"])
    assert clipped.at["Q_HIGH", "_low_x"] == 3.0 and clipped.at["Q_HIGH", "_high_x"] == 3.0
    assert bool(clipped.at["Q_LOW", "_cut_low"]) and bool(clipped.at["Q_LOW", "_center_in"])
    assert clipped.at["Q_LOW", "_low_x"] == -3.0
    assert not (clipped.loc["Q_IN", ["_cut_low", "_cut_high"]].any())
    cut = int((clipped["_cut_low"] | clipped["_cut_high"]).sum())
    assert cut == 2

    labels = summary_legend_labels(main, loq, cut, 3.0)
    by_category = dict(zip(CATEGORY_ORDER, labels))
    assert by_category["차이"].endswith(": 1 / 0")
    assert by_category["미결-경계"].endswith(": 1 / 0")
    assert by_category["동등"].endswith(": 1 / 0")
    assert by_category["<LoQ 보고 일치"].endswith(": 0 / 2")
    assert labels[-1].endswith("±3: 2")


def test_xlim_option_defaults_to_three_and_rejects_non_positive():
    assert build_parser().parse_args([]).xlim == 3.0
    assert build_parser().parse_args(["--xlim", "5"]).xlim == 5.0
    for bad in ("0", "-2", "nan"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--xlim", bad])


def test_plot_summary_writes_pngs_with_custom_xlim_and_without_main_items(tmp_path: Path):
    frame = summary_frame()
    paths = plot_summary(frame, tmp_path / "mixed", dpi=60, xlim=2.0)
    assert [path.name for path in paths] == ["summary_001.png"]

    loq_only = frame.loc[frame["zone"] != "정량"]
    paths = plot_summary(loq_only, tmp_path / "loq_only", dpi=60)
    assert len(paths) == 1 and paths[0].stat().st_size > 0

    with pytest.raises(ValueError):
        plot_summary(frame, tmp_path / "bad", xlim=0)


def assert_detail_pngs(plots: Path, expected_items) -> None:
    expected = {safe_item_name(item) for item in expected_items}
    paths = list((plots / "detail").glob("*.png"))
    assert {path.stem for path in paths} == expected
    assert len(paths) == len(expected)
    for path in paths:
        assert path.stat().st_size > 0, f"빈 상세 그림: {path}"


def test_detail_default_writes_exactly_difference_and_undecided_items(
    por3_results: tuple[Path, Path], tmp_path: Path,
):
    data, items_csv = por3_results
    items = pd.read_csv(items_csv, encoding="utf-8-sig")
    expected = items.loc[items["verdict"].isin(["차이", "미결"]), "ITEM"].astype(str)
    assert not expected.empty
    plots = tmp_path / "plots"

    run_script(ROOT / "plot_verdicts.py", [
        "--items-csv", items_csv, "--no-summary", "--detail",
        "--out", plots, "--dpi", "80", *raw_args(data),
    ])

    assert_detail_pngs(plots, expected)


def test_detail_items_writes_only_requested_codes(
    por3_results: tuple[Path, Path], tmp_path: Path,
):
    data, items_csv = por3_results
    requested = ["VT_SHIFT", "VT_SAME"]
    plots = tmp_path / "plots"

    run_script(ROOT / "plot_verdicts.py", [
        "--items-csv", items_csv, "--no-summary", "--detail",
        "--items", ",".join(requested), "--out", plots, "--dpi", "80", *raw_args(data),
    ])

    assert_detail_pngs(plots, requested)


def test_detail_all_jobs_two_writes_one_png_per_item(
    por3_results: tuple[Path, Path], tmp_path: Path,
):
    data, items_csv = por3_results
    items = pd.read_csv(items_csv, encoding="utf-8-sig")
    plots = tmp_path / "plots"

    run_script(ROOT / "plot_verdicts.py", [
        "--items-csv", items_csv, "--no-summary", "--detail", "--all", "--jobs", "2",
        "--out", plots, "--dpi", "80", *raw_args(data),
    ])

    assert_detail_pngs(plots, items["ITEM"].astype(str))


def test_detail_reason_text_equals_items_csv_reason(por3_results: tuple[Path, Path]):
    data, items_csv = por3_results
    args = build_parser().parse_args([str(arg) for arg in raw_args(data)])
    actual = recompute(args).set_index("ITEM")
    expected = pd.read_csv(items_csv, encoding="utf-8-sig").set_index("ITEM")

    for item, row in actual.iterrows():
        title, reason = detail_text(row.to_dict(), str(item))
        assert str(item) in title
        assert reason == expected.at[item, "reason"]


def test_chosen_font_renders_all_korean_labels_without_glyph_warnings(tmp_path: Path):
    selected = configure_font()
    if selected is None:
        pytest.skip("한글 후보 폰트가 없어 한글 글리프 렌더링 검사를 생략함")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig = plt.figure(figsize=(12, 10))
        try:
            for index, label in enumerate(KOREAN_TEXTS):
                fig.text(0.02, 0.98 - index / (len(KOREAN_TEXTS) + 1), label, fontsize=12)
            fig.canvas.draw()
            fig.savefig(tmp_path / "korean_font_check.png", dpi=100)
        finally:
            plt.close(fig)

    glyph_warnings = [
        str(w.message)
        for w in caught
        if "missing from font" in str(w.message).lower()
        or re.search(r"Glyph .* missing", str(w.message), re.IGNORECASE)
    ]
    assert not glyph_warnings, f"선택 폰트 {selected!r}의 한글 글리프 경고: {glyph_warnings}"
