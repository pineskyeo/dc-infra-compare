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
    CATEGORY_ORDER, KOREAN_TEXTS, LOQ_AXIS_MAX, LOQ_AXIS_MIN, NO_GROUP, build_parser, clip_summary,
    configure_font, detail_text, direction_counts, draw_loq, main, map_points, map_this_run, plot_dashboard,
    plot_loq, plot_summary, read_loq_flags, recompute, safe_item_name, split_summary, summary_legend_labels,
    verdict_category, V_EXCLUDED,
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
    for name in ("summary.png", "summary_loq.png"):
        path = plots / name
        assert path.is_file(), f"만들어지지 않은 그림: {path}"
        assert path.stat().st_size > 0
    assert not list(plots.glob("summary_[0-9][0-9][0-9].png"))


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


def png_size(path: Path) -> tuple[int, int]:
    """PNG IHDR에서 (가로, 세로) 픽셀."""
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def dashboard_frame(n: int = 2000) -> pd.DataFrame:
    """정량 ITEM n개(대부분 차이/미결, 일부 범위 밖)와 LoQ 미만 2개, 판정 제외 1개."""
    rows = []
    for i in range(n):
        verdict = ("차이", "미결", "차이", "미결", "동등")[i % 5]
        reason = {"차이": "shift", "미결": "경계 (신뢰구간이 Δ에 걸침)", "동등": "90% 신뢰구간이 ±Δ 안"}[verdict]
        center = (i % 97) / 10 - 4.8
        rows.append({
            "ITEM": f"Q{i:05d}", "zone": "정량", "verdict": verdict, "reason": reason,
            "center": center, "ci_low": center - 0.5, "ci_high": center + 0.5, "delta": 1.0,
            "doe_center": 10.0, "LoQ": 1.0,
        })
    rows += [
        {"ITEM": "L1", "zone": "검출~정량", "verdict": "동등", "reason": "<LoQ 보고 일치",
         "center": 0.1, "ci_low": 0.0, "ci_high": 0.2, "delta": 1.0, "doe_center": 0.5, "LoQ": 1.0},
        {"ITEM": "L2", "zone": "검출한계 이하", "verdict": "차이", "reason": "shift",
         "center": 3.0, "ci_low": 2.0, "ci_high": 4.0, "delta": 1.0, "doe_center": 0.1, "LoQ": 1.0},
        {"ITEM": "X1", "zone": "정량", "verdict": V_EXCLUDED, "reason": "통계 불가",
         "center": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "delta": 1.0,
         "doe_center": 1.0, "LoQ": 1.0},
    ]
    return pd.DataFrame(rows)


def test_plot_dashboard_writes_one_map_png(tmp_path: Path):
    frame = dashboard_frame(2000)
    path = plot_dashboard(frame, tmp_path, dpi=40)
    assert path == tmp_path / "summary.png"
    assert [p.name for p in tmp_path.iterdir()] == ["summary.png"]
    width_px, height_px = png_size(path)
    assert width_px == 13 * 40 and height_px > 8 * 40      # 아래 읽는 법·이번 결과 만큼 늘어남

    # LoQ 행·차이/미결 행이 없어도 그린다.
    quiet = summary_frame().loc[lambda f: f["zone"] == "정량"].assign(verdict="동등", reason="안")
    assert plot_dashboard(quiet, tmp_path / "quiet", dpi=40).stat().st_size > 0


def map_frame() -> pd.DataFrame:
    """최종 판정 근거가 다른 정량 ITEM 넷 (옵션 열 포함)과 LoQ 아래 하나."""
    nan = float("nan")
    return pd.DataFrame({
        "ITEM": ["LIN", "LOG", "ACC", "OLD_BLANK", "FLOOR"],
        "zone": ["정량", "정량", "정량", "정량", "검출한계 이하"],
        "verdict": ["차이", "차이", "미결", "미결", "동등"],
        "verdict_final": ["차이", "동등", "동등", "미결", "동등"],
        "verdict_basis": ["linear", "log", "accuracy", "", "linear"],
        "center": [3.0, 3.0, 1.0, -1.0, 0.0],
        "ci_low": [2.0, 2.0, 0.0, -2.0, 0.0],
        "ci_high": [4.0, 4.0, 2.0, 0.0, 0.0],
        "delta": [1.0, 1.0, 1.0, 1.0, 1.0],
        "accuracy_margin": [nan, nan, 4.0, nan, nan],
        "center_log": [nan, 0.1, nan, nan, nan],
        "ci_low_log": [nan, 0.05, nan, nan, nan],
        "ci_high_log": [nan, 0.25, nan, nan, nan],
        "delta_log": [nan, 0.5, nan, nan, nan],
    })


def test_map_points_place_each_item_by_the_tost_that_set_its_final_verdict():
    points = map_points(map_frame()).set_index("ITEM")
    assert points.loc["LIN", ["x", "y"]].tolist() == [3.0, 1.0]
    assert points.loc["LOG", ["x", "y"]].tolist() == pytest.approx([0.2, 0.2])   # log 열, 허용폭 delta_log
    assert points.loc["ACC", ["x", "y"]].tolist() == [0.25, 0.25]                # 허용폭 max(delta, 정확도 폭)
    assert points.loc["OLD_BLANK", "basis"] == "linear"
    assert points.loc["LOG", "verdict"] == "동등" and bool(points.loc["FLOOR", "loq_zone"])
    for item in ("LOG", "ACC"):       # 최종 판정의 좌표라 색(최종 판정)과 칸이 맞는다
        x, y = points.loc[item, ["x", "y"]]
        assert abs(x) + y < 1


def test_map_this_run_counts_directions_and_flags_one_sided_moves():
    rows = pd.DataFrame({"ITEM": [f"D{i}" for i in range(10)], "zone": "정량", "verdict": "차이",
                         "center": [1.0] * 9 + [-1.0], "ci_low": 0.5, "ci_high": 1.5, "delta": 0.4})
    points = map_points(rows)
    assert direction_counts(points) == {"차이": (1, 9), "미결": (0, 0)}
    text = map_this_run(points)
    assert "차이 10개 중 + 방향 9개, − 방향 1개." in text and "+ 방향으로 몰려 있다" in text

    even = map_points(rows.assign(center=[1.0, -1.0] * 5))
    assert "몰리지 않았다" in map_this_run(even)
    assert "개수가 적어" in map_this_run(map_points(rows.head(4)))
    assert "옵션이 판정을 정한 ITEM 2개" in map_this_run(map_points(map_frame()))


def test_main_writes_summary_pages_only_with_full(tmp_path: Path):
    csv = tmp_path / "items.csv"
    dashboard_frame(50).to_csv(csv, index=False, encoding="utf-8-sig")
    plots = tmp_path / "plots"
    plots.mkdir()
    (plots / "summary_007.png").write_bytes(b"stale")
    base = ["--items-csv", str(csv), "--out", str(plots), "--dpi", "40"]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        main(base)
        assert sorted(p.name for p in plots.glob("summary*.png")) == ["summary.png", "summary_loq.png"]

        main([*base, "--full", "--per-page", "30"])
        assert sorted(p.name for p in plots.glob("summary*.png")) == [
            "summary.png", "summary_001.png", "summary_002.png", "summary_loq.png",
        ]

        main(base)
        assert not list(plots.glob("summary_[0-9][0-9][0-9].png"))


def write_groups(path: Path, mapping: dict) -> Path:
    lines = ["ITEM,group", *(f"{item},{group}" for item, group in mapping.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_main_groups_writes_one_dashboard_per_group_and_cleans_up(tmp_path: Path, capsys):
    frame = dashboard_frame(30)
    csv = tmp_path / "items.csv"
    frame.to_csv(csv, index=False, encoding="utf-8-sig")
    plots = tmp_path / "plots"
    base = ["--items-csv", str(csv), "--out", str(plots), "--dpi", "30"]
    names = ("G1", "그룹 B", "C/D")
    every = {item: names[i % 3] for i, item in enumerate(frame["ITEM"])}
    expected = ["summary_group_B.png", "summary_group_C_D.png", "summary_group_G1.png"]

    def group_pngs():
        return sorted(p.name for p in plots.glob("summary_group_*.png"))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        main([*base, "--groups", str(write_groups(tmp_path / "all.csv", every))])
        assert group_pngs() == expected
        assert "그룹 없음" not in capsys.readouterr().out

        # 그룹 파일에 없는 ITEM(L1, L2, X1) → '(그룹 없음)' 한 장 + 경고 한 줄.
        partial = {k: v for k, v in every.items() if k.startswith("Q")}
        main([*base, "--groups", str(write_groups(tmp_path / "partial.csv", partial))])
        no_group = f"summary_group_{safe_item_name(NO_GROUP)}.png"
        assert group_pngs() == sorted([*expected, no_group])
        warning_lines = [line for line in capsys.readouterr().out.splitlines() if NO_GROUP in line]
        assert len(warning_lines) == 1 and "3개" in warning_lines[0]

        # --groups 없이 다시 돌리면 예전 그룹 그림이 남지 않는다.
        main(base)
        assert group_pngs() == []
        assert (plots / "summary.png").is_file()


def loq_frame() -> pd.DataFrame:
    """LoQ 미만 zone 4개(범위 안 1, x 범위 위 1, y 범위 아래 1, center 0 1)와 정량 1개."""
    return pd.DataFrame({
        "ITEM": ["L_IN", "L_X_HIGH", "L_Y_LOW", "L_ZERO", "Q_SKIP"],
        "zone": ["검출~정량", "검출~정량", "검출한계 이하", "검출한계 이하", "정량"],
        "verdict": ["동등", "차이", "미결", "동등", "동등"],
        "doe_center": [2.0, 5000.0, -0.5, 0.5, 1.0],
        "LoQ": [1.0, 1.0, 1.0, 1.0, 1.0],
        "center": [0.5, 3.0, -1e-5, 0.0, 0.1],
        "delta": [1.0, 1.0, 1.0, 1.0, 1.0],
    })


def test_draw_loq_uses_log_axes_and_counts_clipped_points():
    fig, ax = plt.subplots()
    try:
        counts = draw_loq(ax, loq_frame())
        assert ax.get_xscale() == "log" and ax.get_yscale() == "log"
        assert ax.get_xlim() == pytest.approx((LOQ_AXIS_MIN, LOQ_AXIS_MAX))
        assert ax.get_ylim() == pytest.approx((LOQ_AXIS_MIN, LOQ_AXIS_MAX))
        assert ax.get_legend() is not None
    finally:
        plt.close(fig)
    assert {k: counts[k] for k in ("n", "clipped", "zero", "excluded", "flagged")} == {
        "n": 4, "clipped": 3, "zero": 1, "excluded": 0, "flagged": 0}


def test_loq_review_flags_are_marked_only_when_review_exists(tmp_path: Path):
    items_csv = tmp_path / "items.csv"
    loq_frame().to_csv(items_csv, index=False, encoding="utf-8-sig")
    assert read_loq_flags(items_csv) is None
    (tmp_path / "review").mkdir()
    pd.DataFrame({"ITEM": ["L_IN", "L_X_HIGH", "Q_SKIP"], "flag": [True, False, True]}).to_csv(
        tmp_path / "review" / "loq_review.csv", index=False, encoding="utf-8-sig")
    flags = read_loq_flags(items_csv)
    assert flags == {"L_IN", "Q_SKIP"}

    fig, ax = plt.subplots()
    try:
        counts = draw_loq(ax, loq_frame(), flags)
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
    finally:
        plt.close(fig)
    assert counts["flagged"] == 1       # Q_SKIP 은 정량 zone 이라 이 그림에 없다
    assert "LoQ 재확인 '확인 필요' 1" in labels

    path = plot_loq(loq_frame(), tmp_path / "plots", dpi=60, flagged=flags)
    assert path.name == "summary_loq.png" and path.stat().st_size > 0


def test_draw_loq_major_tick_labels_are_plain_text():
    fig, ax = plt.subplots()
    try:
        draw_loq(ax, loq_frame())
        fig.canvas.draw()
        for axis in (ax.xaxis, ax.yaxis):
            labels = [t.get_text() for t in axis.get_majorticklabels() if t.get_text()]
            assert labels, "major tick labels must exist on log axes"
            for text in labels:
                assert "−" not in text, text
                assert "$" not in text, text
            assert "1" in labels and "0.1" in labels, labels
    finally:
        plt.close(fig)


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
    # 상세 그림은 최종 판정(verdict_final)을 따른다. accuracy 옵션으로 동등이 된 LoQ 근처 ITEM 은 빠진다
    expected = items.loc[items["verdict_final"].isin(["차이", "미결"]), "ITEM"].astype(str)
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
