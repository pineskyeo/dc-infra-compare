"""items.csv로 ITEM 판정 요약 그림을 만들고, 필요하면 같은 판정 함수로 결과를 다시 계산한다.

요약·상세 그림에는 item_map의 실제 항목 이름을 사용하지 않는다. 상세 그림 파일명은
safe_item_name()을 거친 ITEM 코드만 사용해야 한다.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import re
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager, rcParams
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator, NullFormatter
from scipy import stats

from explain import BASIS_NAMES, add_figure_note
from infra_compare import load_blank, read_csv_auto, read_groups
from item_view import basis_numbers
from por_doe_compare import (
    ORDER, V_EXCLUDED, add_common_args, add_final_verdict, ci_rank, judge_item, load_levels, load_wide,
    verdict_col,
)

FONT_CANDIDATES = (
    "Apple SD Gothic Neo",
    "AppleGothic",
    "Malgun Gothic",
    "NanumGothic",
    "Noto Sans CJK KR",
    "Gothic A1",
)

CATEGORY_ORDER = (
    "차이",
    "미결-경계",
    "미결-해상도 부족",
    "미결-die 부족",
    "동등",
    "<LoQ 보고 일치",
)
CATEGORY_COLORS = {
    "차이": "#D55E00",
    "미결-경계": "#E69F00",
    "미결-해상도 부족": "#CC79A7",
    "미결-die 부족": "#7F7F7F",
    "동등": "#009E73",
    "<LoQ 보고 일치": "#0072B2",
}
TOOL_VERDICT_ORDER = ("차이", "미결", "동등")
TOOL_VERDICT_COLORS = {
    "차이": CATEGORY_COLORS["차이"],
    "미결": CATEGORY_COLORS["미결-경계"],
    "동등": CATEGORY_COLORS["동등"],
}

SUMMARY_TITLE = "ITEM 판정 요약"
SUMMARY_XLABEL = "차이 / Δ (가로선: 90% 신뢰구간, 점: 중심)"
SUMMARY_YLABEL = "ITEM (정렬: 판정 → center/Δ)"
PAGE_LEGEND_TITLE = "판정 개수 (이 장 / LoQ 패널)"
CLIPPED_LABEL = "x축 범위 밖 (끝에서 자름)"
# 판정 제외 ITEM(과 center/Δ가 유효하지 않은 예전 items.csv 행)은 요약 그림·LoQ 패널에 그리지 않는다.
EXCLUDED_NOTE = "판정 제외 {n}개 (요약 그림에서 뺌)"
NO_MAIN_ITEMS = "정량 zone ITEM 없음 (LoQ 미만은 summary_loq.png)"
LOQ_ZONES = ("검출한계 이하", "검출~정량")
NO_TOST_ZONES = ("die 부족",)   # TOST 없이 미결로 정해져 지도 좌표가 판정을 뜻하지 않는 zone
# 각 함수가 시작할 때 지우는 자기 그림(--out 기준 glob). 장 수가 줄거나 건너뛴 그림이 남지 않게 한다.
OWN_OUTPUTS = {
    "summary": ("summary_[0-9][0-9][0-9].png",),
    "dashboard": ("summary.png",),
    "group": ("summary_group_*.png",),
    "loq": ("summary_loq.png",),
    "detail": ("detail/*.png",),
}

# 판정 지도 summary.png (설계 1-1). 점 하나가 ITEM 하나: 최종 판정을 정한 TOST 의 이동과 신뢰구간 반폭을 그 허용폭으로
# 나눈 좌표. x 는 신뢰구간 가운데라 동등 |x| + y ≤ 1, 차이 |x| − y > 1 이 판정과 정확히 같다. 그 사이 미결.
MAP_TITLE = "ITEM 판정 지도"
MAP_XLABEL = "DOE가 움직인 양 ÷ 허용폭   (신뢰구간 가운데, 0 = 그대로, ±1 = 허용폭만큼)"
MAP_YLABEL = "측정이 흔들리는 정도 ÷ 허용폭   (90% 신뢰구간 반폭)"
# 세로축 위끝: 점 99%가 들어가게 (동등 삼각형 꼭대기 1 은 늘 보이게), 이보다 높으면 축 끝에 붙인다
MAP_YLIM_MIN, MAP_YLIM_MAX = 1.2, 3.0
MAP_SIZE_IN = (13.0, 8.0)
MAP_DRAW_ORDER = ("동등", "미결", "차이")
FLAGGED_VERDICTS = ("차이", "미결")
REGION_EQUAL = "같다 (동등)"
REGION_DIFF = ("DOE가 낮아졌다 (차이)", "DOE가 높아졌다 (차이)")
REGION_EDGE = "경계에 걸침 (미결)"
REGION_NOISY = "흔들려서 판단 불가 (미결)"
OPTION_EDGE_LABEL = "검은 테두리: 옵션(log·장비 정확도)이 정한 판정"
CLIP_LABEL = "삼각형: 축 밖 값을 축 끝에 붙임"
MAP_LOQ_NOTE = "LoQ 아래 ITEM {n:,}개는 summary_loq.png"
MAP_OFF_NOTE = "좌표가 없어 못 그린 ITEM {n:,}개 (die 부족 등)"
DIRECTION_TITLE = "어느 쪽으로 움직였나 (차이·미결)"
DIRECTION_LABELS = ("− 방향 (DOE가 낮음)", "+ 방향 (DOE가 높음)")
DIRECTION_NONE = "차이·미결 ITEM 없음"
MAP_HOW_TO_READ = (
    "점 하나가 ITEM 하나다. 가로는 DOE가 움직인 양을 허용폭으로 나눈 값이고, 세로는 측정이 흔들리는 정도(90% 신뢰구간 "
    "반폭)를 허용폭으로 나눈 값이다. 점이 가운데 아래 초록 삼각형에 모일수록 DOE가 POR과 같고, 좌우 주황 칸은 "
    "달라졌다, 그 사이와 위쪽은 미결이다. 위쪽 점은 측정이 흔들려 판단을 못 한 ITEM이다. 점 색은 최종 판정이고 칸과 "
    "늘 같다 (가로는 신뢰구간 가운데). log·장비 정확도 옵션이 정한 "
    "ITEM은 그 판정의 이동·신뢰구간·허용폭으로 놓았다.")
SKEW_P = 0.05            # 차이·미결의 +/− 개수 부호검정 p 가 이보다 작으면 "한쪽으로 몰림"
LOQ_REVIEW_CSV = Path("review") / "loq_review.csv"   # review.py 결과, items.csv 폴더 기준


def remove_own_outputs(out: Path, patterns) -> None:
    """지난 실행의 자기 출력 파일만 지운다(폴더·다른 파일은 그대로)."""
    for pat in patterns:
        for p in out.glob(pat):
            if p.is_file():
                p.unlink()
DEFAULT_XLIM = 3.0
LOQ_TITLE = "LoQ 아래 ITEM: DOE 값과 이동"
LOQ_XLABEL = "DOE 값 ÷ 정량 한계(LoQ)   (1 넘으면 DOE가 숫자로 보고됨)"
LOQ_YLABEL = "이동량 ÷ 허용폭   (1 넘으면 허용폭보다 크게 움직임)"
NO_LOQ_ITEMS = "해당 ITEM 없음"
NO_VALID_POINTS = "표시할 유효한 좌표 없음"
LOQ_FLAG_LABEL = "LoQ 재확인 '확인 필요' {n:,}"
LOQ_HOW_TO_READ = (
    "점 하나가 LoQ 아래 ITEM 하나다. 이 ITEM들은 POR 값이 정량 한계(LoQ) 아래라 숫자 대신 '<LoQ'로 보고하고, DOE도 "
    "LoQ 아래면 둘 다 '<LoQ'라 동등으로 본다. 오른쪽일수록 DOE 값이 LoQ 위로 올라가고, 위쪽일수록 이동이 허용폭보다 "
    "크다. 빨간 칸(오른쪽 위)은 DOE가 숫자로 보고되고 크게 움직인 곳이다. 주황 칸(왼쪽 위)은 둘 다 '<LoQ'라 동등이지만 "
    "실제로는 움직였을 수 있는 곳이다. 검은 마름모는 review.py LoQ 재확인이 die 방향이나 꼬리로 '확인 필요'라고 본 "
    "ITEM이다 (판정은 그대로, 이름은 review/loq_review.csv).")
# LoQ 패널은 두 축 모두 log. 범위 밖·0 이하·무한대 값은 축 끝에 다른 마커로 붙인다.
LOQ_AXIS_MIN = 1e-3
LOQ_AXIS_MAX = 1e3
LOQ_CLIPPED_NOTE = "축 끝 클리핑 {n}개 (0값 {zero}개 포함)"
# (x, y, 칸 이름): x>1 은 DOE 가 LoQ 위라 숫자로 보고, y>1 은 이동이 허용폭보다 큼.
LOQ_QUADRANT_NOTES = (
    (0.98, 0.98, "DOE가 숫자로 보고되고\n크게 움직임 (차이·미결)"),
    (0.02, 0.98, "둘 다 '<LoQ' 보고인데 크게 움직임\n(숨은 변화 가능, 판정은 동등)"),
    (0.98, 0.02, "DOE가 숫자로 보고되지만\n움직임은 허용폭 안"),
    (0.02, 0.02, "둘 다 '<LoQ' 보고,\n움직임도 허용폭 안"),
)
DETAIL_LEFT_TITLE = "POR 회차별 / DOE die 값"
DETAIL_RIGHT_TITLE = "d = DOE - POR 평균 (정렬)"
DETAIL_LEFT_YLABEL = "측정값"
DETAIL_RIGHT_XLABEL = "die 순번 (오름차순)"
DETAIL_RIGHT_YLABEL = "d = DOE - POR 평균"
DETAIL_BAR_LABEL = "die별 d"
DETAIL_CI_LABEL = "90% CI 순번 구간"
DETAIL_OUTLIER_LABEL = "튀는 die (judge mask)"
DETAIL_LOQ_LABEL = "LoQ (참고)"
DETAIL_POLICY_LABEL = "±Δ 정책"
DETAIL_TOTAL_LABEL = "±Δ 정책 + 회차"
DETAIL_RUN_BAND_LABEL = "회차 margin 누적"
DETAIL_LOQ_FOOTNOTE = "LoQ 선은 측정 수준 참고선입니다. 정량 zone이 아니면 값을 <LoQ로 보고합니다."

# 한글 렌더 테스트는 그림에 넣는 모든 고정 문자열을 이 목록에서 가져간다.
KOREAN_TEXTS = tuple(dict.fromkeys(
    CATEGORY_ORDER
    + TOOL_VERDICT_ORDER
    + (
        SUMMARY_TITLE,
        SUMMARY_XLABEL,
        SUMMARY_YLABEL,
        PAGE_LEGEND_TITLE,
        CLIPPED_LABEL,
        V_EXCLUDED,
        EXCLUDED_NOTE.format(n=1),
        NO_MAIN_ITEMS,
        MAP_TITLE,
        MAP_XLABEL,
        MAP_YLABEL,
        REGION_EQUAL,
        *REGION_DIFF,
        REGION_EDGE,
        REGION_NOISY,
        OPTION_EDGE_LABEL,
        CLIP_LABEL,
        MAP_LOQ_NOTE.format(n=1),
        MAP_OFF_NOTE.format(n=1),
        DIRECTION_TITLE,
        *DIRECTION_LABELS,
        DIRECTION_NONE,
        MAP_HOW_TO_READ,
        "최종 판정 (전체 ITEM 수)",
        "최종 판정 근거: 기본 판정 장비 정확도 옵션 물리 log 판정",
        LOQ_TITLE,
        LOQ_XLABEL,
        LOQ_YLABEL,
        LOQ_FLAG_LABEL.format(n=1),
        LOQ_HOW_TO_READ,
        "최종 판정",
        NO_LOQ_ITEMS,
        NO_VALID_POINTS,
        LOQ_CLIPPED_NOTE.format(n=3, zero=1),
        *(note for _, _, note in LOQ_QUADRANT_NOTES),
        DETAIL_LEFT_TITLE,
        DETAIL_RIGHT_TITLE,
        DETAIL_LEFT_YLABEL,
        DETAIL_RIGHT_XLABEL,
        DETAIL_RIGHT_YLABEL,
        DETAIL_BAR_LABEL,
        DETAIL_CI_LABEL,
        DETAIL_OUTLIER_LABEL,
        DETAIL_LOQ_LABEL,
        DETAIL_POLICY_LABEL,
        DETAIL_TOTAL_LABEL,
        DETAIL_RUN_BAND_LABEL,
        DETAIL_LOQ_FOOTNOTE,
        "정량",
        "검출한계 이하",
        "검출~정량",
        "die 부족",
    )
))


def configure_font(font_path: str | None = None) -> str | None:
    """한글 후보 폰트나 --font 폰트를 선택하고, 선택한 폰트 이름을 돌려준다."""
    rcParams["axes.unicode_minus"] = False
    if font_path:
        path = Path(font_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"폰트 파일이 없습니다: {path}")
        font_manager.fontManager.addfont(str(path))
        selected = font_manager.FontProperties(fname=str(path)).get_name()
    else:
        selected = None
        for candidate in FONT_CANDIDATES:
            try:
                font_manager.findfont(
                    font_manager.FontProperties(family=candidate),
                    fallback_to_default=False,
                )
            except ValueError:
                continue
            selected = candidate
            break

    if selected is None:
        warnings.warn(
            "한글 폰트 후보를 찾지 못했습니다. --font PATH로 한글 폰트를 지정하세요.",
            RuntimeWarning,
            stacklevel=2,
        )
        return None
    # matplotlib falls back per glyph only across the font.family list itself, so
    # the chosen font and DejaVu Sans must both be listed there (e.g. Greek Δ
    # comes from DejaVu Sans when the Korean font lacks it).
    rcParams["font.family"] = [selected, "DejaVu Sans"]
    rcParams["font.sans-serif"] = [selected, "DejaVu Sans"]
    return selected


def safe_item_name(item: object) -> str:
    """상세 그림 파일명에 쓸 수 있는, ITEM 코드에서만 만든 안전한 이름."""
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(item)).strip("._")
    return name or "ITEM"


def _positive_float(text: str) -> float:
    value = float(text)
    if not np.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("양수여야 합니다")
    return value


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items-csv", default="por_doe_out/items.csv", help="판정 결과 items.csv")
    summary = ap.add_mutually_exclusive_group()
    summary.add_argument("--summary", dest="summary", action="store_true", help="요약 그림 작성 (기본)")
    summary.add_argument("--no-summary", dest="summary", action="store_false", help="요약 그림 생략")
    ap.set_defaults(summary=True)
    ap.add_argument("--detail", action="store_true", help="ITEM별 상세 그림 작성 (기본 끔)")
    detail_selection = ap.add_mutually_exclusive_group()
    detail_selection.add_argument("--items", metavar="A,B", help="상세 그림을 그릴 ITEM 코드 (쉼표 구분)")
    detail_selection.add_argument("--all", action="store_true", help="모든 ITEM의 상세 그림 작성")
    ap.add_argument("--jobs", type=int, default=1, help="상세 그림 multiprocessing worker 수 (기본 1)")
    ap.add_argument("--out", default="por_doe_out/plots/", help="PNG output directory")
    ap.add_argument("--dpi", type=int, default=100, help="PNG 해상도 (기본 100)")
    ap.add_argument("--font", metavar="PATH", help="한글 폰트 파일 경로")
    ap.add_argument("--full", action="store_true",
                    help="summary.png에 더해 모든 정량 ITEM을 그린 summary_NNN.png도 작성 (--per-page)")
    ap.add_argument("--groups", metavar="FILE",
                    help="ITEM,group 두 열 파일. 주면 그룹마다 summary_group_<이름>.png도 작성 "
                         "(파일에 없는 ITEM은 '(그룹 없음)')")
    ap.add_argument("--per-page", type=int, default=1200, help="--full 요약 한 장의 최대 ITEM 수 (기본 1200)")
    ap.add_argument("--xlim", type=_positive_float, default=DEFAULT_XLIM, metavar="X",
                    help=f"요약 본 패널 x축 범위 ±X (차이/Δ, 기본 {DEFAULT_XLIM:g}). 밖은 끝에서 잘라 화살표로 표시")

    # 원시 데이터는 재계산/상세 그림에서만 필요하므로 요약 전용 실행에서는 선택 사항이다.
    add_common_args(ap)
    for action in ap._actions:
        if action.dest in {"por", "doe"}:
            action.required = False
    return ap


def _require_columns(df: pd.DataFrame, columns: set[str]) -> None:
    missing = sorted(columns - set(df.columns))
    if missing:
        raise ValueError(f"items.csv에 필요한 열이 없습니다: {', '.join(missing)}")


def _load_recompute_inputs(args: argparse.Namespace, purpose: str = "재계산"):
    """재계산과 상세 그림이 공유할 원시 데이터/level/blank 연결."""
    if not args.por or not args.doe:
        raise ValueError(f"{purpose}에는 --por(회차별)와 --doe가 필요합니다.")
    if len(args.por) < 2:
        raise ValueError("POR은 2회 이상 필요합니다 (--por를 회차마다 따로).")

    wide, por_cols, units = load_wide(args)
    blank = load_blank(args.blank, args.encoding) if args.blank else pd.DataFrame(columns=["BLANK_ITEM"])
    blank = blank.set_index("BLANK_ITEM")
    bmap = {}
    if args.blank_map:
        mp = read_csv_auto(Path(args.blank_map), args.encoding)
        mp.columns = [c.strip().upper() for c in mp.columns]
        bmap = dict(zip(mp["ITEM"], mp["BLANK_ITEM"]))
    levels = load_levels(args.level, args.encoding) if args.level else {}
    return wide, por_cols, units, levels, blank, bmap


def recompute(args: argparse.Namespace) -> pd.DataFrame:
    """load_wide + judge_item만으로 ITEM별 판정 결과를 다시 계산한다."""
    wide, por_cols, units, levels, blank, bmap = _load_recompute_inputs(args)
    rows = []
    for item, group in wide.groupby("ITEM", sort=False):
        result, _ = judge_item(item, group, por_cols, units, args.r, levels, blank, bmap)
        rows.append(result)
    first = ["ITEM", "UNIT", "zone", "verdict", "reason"]
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result = add_final_verdict(result[first + [c for c in result.columns if c not in first]])
    return result.sort_values(
        ["verdict", "ITEM"],
        key=lambda s: s.map(ORDER) if s.name == "verdict" else s,
    ).reset_index(drop=True)


def verdict_category(row: pd.Series) -> str:
    """도구 verdict/reason/zone을 요약 그림의 여섯 표시 범주 또는 '판정 제외'(그리지 않음)로 변환한다."""
    verdict = str(row["verdict"])
    reason = "" if pd.isna(row["reason"]) else str(row["reason"])
    zone = "" if pd.isna(row.get("zone", "")) else str(row.get("zone", ""))
    if verdict == V_EXCLUDED:
        return V_EXCLUDED
    if verdict == "차이":
        return "차이"
    if verdict == "동등":
        return "<LoQ 보고 일치" if "<LoQ 보고 일치" in reason else "동등"
    if verdict == "미결":
        if zone == "die 부족" or "die" in reason.lower():
            return "미결-die 부족"
        if "해상도 부족" in reason:
            return "미결-해상도 부족"
        if "경계" in reason:
            return "미결-경계"
        raise ValueError(f"알 수 없는 미결 사유입니다: {reason}")
    raise ValueError(f"알 수 없는 판정입니다: {verdict}")


def _normalized_summary(items: pd.DataFrame) -> pd.DataFrame:
    _require_columns(items, {"ITEM", "verdict", "reason", "center", "ci_low", "ci_high", "delta"})
    work = items.copy()
    work["_category"] = work.apply(verdict_category, axis=1)
    for column in ("center", "ci_low", "ci_high", "delta"):
        work[column] = pd.to_numeric(work[column], errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        work["_center"] = work["center"] / work["delta"]
        work["_low"] = work["ci_low"] / work["delta"]
        work["_high"] = work["ci_high"] / work["delta"]
    work["_valid"] = np.isfinite(work[["_center", "_low", "_high"]]).all(axis=1)
    work["_order"] = work["verdict"].map(ORDER)
    if work["_order"].isna().any():
        bad = sorted(work.loc[work["_order"].isna(), "verdict"].astype(str).unique())
        raise ValueError(f"알 수 없는 판정입니다: {', '.join(bad)}")
    return work.sort_values(
        ["_order", "_center", "ITEM"], kind="mergesort", na_position="last"
    ).reset_index(drop=True)


def _split_summary(items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """(본 패널 행, LoQ 미만 zone 행, 판정 제외 개수). 판정 제외 = verdict '판정 제외' 행 +
    (예전 items.csv 호환) 판정은 다른데 center/Δ가 유효하지 않은 본 패널 행. 어느 패널에도 넣지 않는다."""
    work = _normalized_summary(items)
    in_loq = work["zone"].isin(LOQ_ZONES) if "zone" in work else pd.Series(False, index=work.index)
    excluded = (work["_category"] == V_EXCLUDED) | (~in_loq & ~work["_valid"])
    main = work.loc[~in_loq & ~excluded].reset_index(drop=True)
    loq = work.loc[in_loq & ~excluded].reset_index(drop=True)
    return main, loq, int(excluded.sum())


def split_summary(items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """정렬한 요약 행을 (본 패널 행, LoQ 미만 zone 행)으로 나눈다. LoQ 미만 행은 summary_loq.png에만 그린다.
    판정 제외 행은 둘 다에서 뺀다."""
    main, loq, _ = _split_summary(items)
    return main, loq


def clip_summary(page: pd.DataFrame, xlim: float) -> pd.DataFrame:
    """유효한 행의 center/CI를 ±xlim으로 자른 좌표와, 왼쪽·오른쪽 끝에서 잘렸는지 표시를 더한다."""
    clipped = page.copy()
    valid = clipped["_valid"]
    clipped["_cut_low"] = valid & (clipped["_low"] < -xlim)
    clipped["_cut_high"] = valid & (clipped["_high"] > xlim)
    clipped["_center_in"] = valid & (clipped["_center"].abs() <= xlim)
    for column in ("_center", "_low", "_high"):
        clipped[f"{column}_x"] = clipped[column].clip(-xlim, xlim)
    return clipped


def summary_legend_labels(
    page: pd.DataFrame, loq: pd.DataFrame, clipped_count: int, xlim: float,
) -> list[str]:
    """판정 범주별 '이 장 / LoQ 패널' 개수와, 범위 밖으로 잘린 ITEM 개수 라벨."""
    page_counts = page["_category"].value_counts()
    loq_counts = loq["_category"].value_counts()
    labels = [
        f"{category}: {int(page_counts.get(category, 0)):,} / {int(loq_counts.get(category, 0)):,}"
        for category in CATEGORY_ORDER
    ]
    labels.append(f"{CLIPPED_LABEL} ±{xlim:g}: {clipped_count:,}")
    return labels


def _draw_ci_rows(
    ax, page: pd.DataFrame, xlim: float, key: str, colors: dict,
    slots: int | None = None, marker_scale: float = 1.0,
) -> None:
    """clip_summary()를 거친 행을 위에서부터 한 줄씩 CI 가로선 + 중심점으로 그리고 ±1 띠를 깐다.
    key 열 값으로 colors의 색을 고른다. slots를 주면 y축을 그 줄 수에 맞춰(위 정렬) 열끼리 눈금을 맞춘다."""
    count = len(page)
    slots = max(slots or count, 1)
    y = (slots - 1) - np.arange(count)
    for name, color in colors.items():
        in_group = (page[key] == name) & page["_valid"]
        mask = in_group.to_numpy()
        if not mask.any():
            continue
        ax.hlines(
            y[mask], page.loc[mask, "_low_x"], page.loc[mask, "_high_x"],
            color=color, linewidth=0.55, alpha=0.8, zorder=2,
        )
        center = (in_group & page["_center_in"]).to_numpy()
        ax.scatter(
            page.loc[center, "_center"], y[center], s=12 * marker_scale, color=color,
            edgecolors="white", linewidths=0.25, zorder=3,
        )
        for side, x, marker in (("_cut_low", -xlim, "<"), ("_cut_high", xlim, ">")):
            cut = (in_group & page[side]).to_numpy()
            if cut.any():
                ax.scatter(
                    np.full(int(cut.sum()), x), y[cut], s=14 * marker_scale, marker=marker,
                    color=color, linewidths=0, zorder=4, clip_on=False,
                )

    ax.axvspan(-1, 1, color="#0072B2", alpha=0.07, zorder=0)
    ax.axvline(-1, color="#666666", linewidth=0.7, linestyle="--", zorder=1)
    ax.axvline(1, color="#666666", linewidth=0.7, linestyle="--", zorder=1)
    ax.axvline(0, color="#999999", linewidth=0.5, zorder=1)
    ax.set_xlim(-xlim * 1.03, xlim * 1.03)
    ax.set_ylim(-1, slots)
    ax.set_yticks([])
    ax.tick_params(axis="y", length=0)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#DDDDDD", linewidth=0.5)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)


def plot_summary(
    items: pd.DataFrame, out: Path, dpi: int = 100, per_page: int = 1200, xlim: float = DEFAULT_XLIM,
) -> list[Path]:
    """정량 zone ITEM을 판정/center-delta 비율 순으로 정렬해 x축 ±xlim 고정 요약 PNG 여러 장으로 저장한다.
    LoQ 미만 zone ITEM은 여기서 빼고 plot_loq()에만 그린다."""
    if per_page < 1:
        raise ValueError("--per-page는 1 이상이어야 합니다.")
    if dpi < 1:
        raise ValueError("--dpi는 1 이상이어야 합니다.")
    if not np.isfinite(xlim) or xlim <= 0:
        raise ValueError("--xlim은 양수여야 합니다.")
    work, loq, omitted = _split_summary(items)
    excluded_note = EXCLUDED_NOTE.format(n=omitted) if omitted else ""
    if omitted:
        warnings.warn(excluded_note, RuntimeWarning, stacklevel=2)

    out.mkdir(parents=True, exist_ok=True)
    remove_own_outputs(out, OWN_OUTPUTS["summary"])
    pages = [work.iloc[start:start + per_page] for start in range(0, len(work), per_page)] or [work]
    paths = []
    for page_number, page in enumerate(pages, 1):
        count = len(page)
        page = clip_summary(page, xlim)
        height = max(3.5, min(30.0, 1.8 + 0.018 * max(count, 1)))
        fig, ax = plt.subplots(figsize=(10, height))
        try:
            _draw_ci_rows(ax, page, xlim, "_category", CATEGORY_COLORS)
            ax.set_xlabel(SUMMARY_XLABEL)
            ax.set_ylabel(SUMMARY_YLABEL)
            start = (page_number - 1) * per_page
            if count:
                ax.set_title(f"{SUMMARY_TITLE} ({start + 1}–{start + count} / {len(work)})")
            else:
                ax.set_title(SUMMARY_TITLE)
                ax.text(0.5, 0.5, NO_MAIN_ITEMS, transform=ax.transAxes, ha="center", va="center")

            clipped_count = int((page["_cut_low"] | page["_cut_high"]).sum())
            labels = summary_legend_labels(page, loq, clipped_count, xlim)
            handles = [
                Line2D(
                    [0], [0], color=CATEGORY_COLORS[category], marker="o", markersize=4,
                    linewidth=1.2, label=label,
                )
                for category, label in zip(CATEGORY_ORDER, labels)
            ]
            handles.append(Line2D(
                [0], [0], color="#555555", marker=">", markersize=5, linestyle="none", label=labels[-1],
            ))
            if excluded_note:
                handles.append(Line2D([0], [0], linestyle="none", label=excluded_note))
            ax.legend(handles=handles, title=PAGE_LEGEND_TITLE, loc="upper left", bbox_to_anchor=(1.01, 1.0))
            fig.subplots_adjust(left=0.09, right=0.79, top=0.97, bottom=max(0.025, 0.7 / height))
            path = out / f"summary_{page_number:03d}.png"
            fig.savefig(path, dpi=dpi, facecolor="white", bbox_inches="tight")
            paths.append(path)
        finally:
            plt.close(fig)
    return paths


def map_points(items: pd.DataFrame) -> pd.DataFrame:
    """ITEM 마다 최종 판정(verdict, 옛 CSV 면 verdict 열), 근거(basis), 최종 판정을 정한 숫자(item_view.basis_numbers:
    log 판정이면 log 열, 장비 정확도면 허용폭 max(Δ, 정확도 폭))의 이동·신뢰구간 반폭을 허용폭으로 나눈 지도 좌표 x, y
    (계산할 수 없으면 NaN), LoQ 아래 zone 인지."""
    _require_columns(items, {"ITEM", "verdict"})
    nums = [basis_numbers(r) for r in items.to_dict("records")]
    margin = np.array([b.margin for b in nums])
    zone = items["zone"].astype(str) if "zone" in items else pd.Series("", index=items.index)
    margin = np.where((margin > 0) & ~zone.isin(NO_TOST_ZONES).to_numpy(), margin, np.nan)
    center = np.array([b.center for b in nums])
    half = np.array([(b.ci_high - b.ci_low) / 2 for b in nums])
    mid = np.array([(b.ci_high + b.ci_low) / 2 for b in nums])
    return pd.DataFrame({
        "ITEM": items["ITEM"].astype(str), "verdict": verdict_col(items).astype(str).str.strip(),
        "basis": [b.name for b in nums], "center": center, "x": mid / margin, "y": half / margin,
        "loq_zone": zone.isin(LOQ_ZONES),
    }, index=items.index)


def direction_counts(points: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """차이·미결 ITEM 의 (− 방향 수, + 방향 수). 방향은 최종 판정을 정한 이동의 부호 (0·NaN 은 세지 않음)."""
    return {v: (int((points.loc[points["verdict"] == v, "center"] < 0).sum()),
                int((points.loc[points["verdict"] == v, "center"] > 0).sum())) for v in FLAGGED_VERDICTS}


def _count_line(points: pd.DataFrame) -> str:
    n = len(points)
    counts = points["verdict"].value_counts()
    eq = int(counts.get("동등", 0))
    share = f" ({100 * eq / n:.0f}%)" if n else ""
    verdicts = f"ITEM {n:,}개 · 동등 {eq:,}{share} · " + " · ".join(
        f"{v} {int(counts.get(v, 0)):,}" for v in ("미결", "차이", V_EXCLUDED))
    by_basis = points["basis"].value_counts()
    order = list(BASIS_NAMES)
    bases = " · ".join(f"{BASIS_NAMES.get(b, b)} {int(by_basis[b]):,}" for b in
                       sorted(by_basis.index, key=lambda b: (order.index(b) if b in order else len(order), b)))
    return f"{verdicts}\n최종 판정 근거: {bases}"


def map_this_run(points: pd.DataFrame) -> str:
    """판정 지도의 "이번 결과" 문장."""
    dirs = direction_counts(points)
    parts = []
    for verdict, (down, up) in dirs.items():
        n = int((points["verdict"] == verdict).sum())
        if n:
            parts.append(f"{verdict} {n:,}개 중 + 방향 {up:,}개, − 방향 {down:,}개.")
    down, up = (sum(d[i] for d in dirs.values()) for i in (0, 1))
    if up + down >= 5 and stats.binomtest(up, up + down, 0.5).pvalue < SKEW_P:
        parts.append(f"{'+' if up > down else '−'} 방향으로 몰려 있다. 한쪽으로 몰린 이동은 공정 변화일 수 있다.")
    elif up + down >= 5:
        parts.append("방향은 한쪽으로 몰리지 않았다.")
    elif up + down:
        parts.append("개수가 적어 한쪽으로 몰렸는지는 따지지 않았다.")
    else:
        parts.append("차이·미결 ITEM이 없다.")
    noisy = points["verdict"].eq("미결") & ~points["loq_zone"] & (points["y"] >= 1)
    if noisy.any():
        parts.append(f"미결 중 {int(noisy.sum()):,}개는 신뢰구간 반폭이 허용폭 이상이라 측정이 흔들려 판단하지 못했다.")
    n_option = int((points["basis"] != "linear").sum())
    if n_option:
        parts.append(f"옵션이 판정을 정한 ITEM {n_option:,}개는 검은 테두리다.")
    return " ".join(parts)


def _draw_regions(ax, xlim: float, ylim: float) -> None:
    ax.fill([-1, 1, 0], [0, 0, 1], color=TOOL_VERDICT_COLORS["동등"], alpha=0.10, lw=0, zorder=0)
    top = min(ylim * 1.03, xlim - 1)
    for side in (-1, 1):
        ax.fill([side, side * xlim * 1.03, side * xlim * 1.03, side * (1 + top)], [0, 0, top, top],
                color=TOOL_VERDICT_COLORS["차이"], alpha=0.08, lw=0, zorder=0)
    ys = np.array([0.0, ylim * 1.03])
    for side in (-1, 1):
        ax.plot(side * (1 - ys), ys, color="#666666", lw=0.8, ls="--", zorder=1)
        ax.plot(side * (1 + ys), ys, color="#666666", lw=0.8, ls="--", zorder=1)
    style = dict(ha="center", va="center", fontsize=10, color="#333333", zorder=1,
                 bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.5))
    ax.text(0, 0.3, REGION_EQUAL, **style)
    x_diff = 1 + 0.6 * (xlim - 1)
    for side, name in zip((-1, 1), REGION_DIFF):
        ax.text(side * x_diff, 0.15 * ylim, name.replace(" (", "\n("), **style)
        ax.text(side * 1.0, 0.45, REGION_EDGE.replace(" (", "\n("), **{**style, "fontsize": 8.5})
    ax.text(0, 0.9 * ylim, REGION_NOISY, **style)


def _draw_map(ax, points: pd.DataFrame, xlim: float) -> int:
    """정량 zone 의 판정된 ITEM 을 지도에 그린다. 그린 점 수를 돌려준다."""
    on = points.loc[~points["loq_zone"] & points["verdict"].isin(MAP_DRAW_ORDER)
                    & np.isfinite(points["x"]) & np.isfinite(points["y"])]
    ylim = float(np.clip(1.25 * on["y"].quantile(0.99), MAP_YLIM_MIN, MAP_YLIM_MAX)) if len(on) else MAP_YLIM_MIN
    x, y = on["x"].clip(-xlim, xlim), on["y"].clip(0, ylim)
    marker = np.where(on["x"] < -xlim, "<", np.where(on["x"] > xlim, ">", np.where(on["y"] > ylim, "^", "o")))
    option = (on["basis"] != "linear").to_numpy()
    size = 26 if len(on) < 500 else 12
    for verdict in MAP_DRAW_ORDER:
        for m in ("o", "<", ">", "^"):
            pick = ((on["verdict"] == verdict).to_numpy()) & (marker == m)
            if pick.any():
                ax.scatter(x[pick], y[pick], s=size * (1.6 if m != "o" else 1), marker=m,
                           color=TOOL_VERDICT_COLORS[verdict], alpha=0.85, clip_on=False, zorder=3,
                           edgecolors=np.where(option[pick], "black", "white"),
                           linewidths=np.where(option[pick], 0.9, 0.3))
    ax.set_xlim(-xlim * 1.03, xlim * 1.03)
    ax.set_ylim(0, ylim * 1.03)
    _draw_regions(ax, xlim, ylim)
    if on.empty:
        ax.text(0.5, 0.65, NO_MAIN_ITEMS, transform=ax.transAxes, ha="center", va="center", fontsize=11)
    ax.set_xlabel(MAP_XLABEL)
    ax.set_ylabel(MAP_YLABEL)
    ax.grid(color="#E6E6E6", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return len(on)


def _draw_directions(ax, points: pd.DataFrame) -> None:
    dirs = direction_counts(points)
    names = list(dirs)
    ypos = np.arange(len(names))[::-1]
    for i, (label, color) in enumerate(zip(DIRECTION_LABELS, ("#0072B2", "#D55E00"))):
        values = np.array([dirs[v][i] for v in names])
        bars = ax.barh(ypos, -values if i == 0 else values, color=color, alpha=0.8, height=0.6, label=label)
        ax.bar_label(bars, labels=[f"{v:,}" if v else "" for v in values], padding=3, fontsize=9)
    peak = max([max(d) for d in dirs.values()] + [1])
    ax.set_xlim(-peak * 1.35, peak * 1.35)
    ax.axvline(0, color="#555555", lw=0.8)
    ax.set_yticks(ypos, names)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4, integer=True, symmetric=True))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(v):g}"))
    ax.set_title(DIRECTION_TITLE, fontsize=10, loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=8, frameon=False)
    if not any(sum(d) for d in dirs.values()):
        ax.text(0.5, 0.5, DIRECTION_NONE, transform=ax.transAxes, ha="center", va="center")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def _map_legend(ax, points: pd.DataFrame, n_drawn: int) -> None:
    ax.set_axis_off()
    counts = points["verdict"].value_counts()
    handles = [Line2D([0], [0], marker="o", ls="none", color=TOOL_VERDICT_COLORS[v], mec="white", markersize=7,
                      label=f"{v} {int(counts.get(v, 0)):,}") for v in ("차이", "미결", "동등")]
    handles += [Line2D([0], [0], marker="o", ls="none", color="#BBBBBB", mec="black", mew=1.0, markersize=7,
                       label=OPTION_EDGE_LABEL),
                Line2D([0], [0], marker=">", ls="none", color="#888888", markersize=7, label=CLIP_LABEL)]
    n_loq = int((points["loq_zone"] & points["verdict"].isin(MAP_DRAW_ORDER)).sum())
    n_off = int(points["verdict"].isin(MAP_DRAW_ORDER).sum()) - n_loq - n_drawn
    notes = [MAP_LOQ_NOTE.format(n=n_loq) if n_loq else "", MAP_OFF_NOTE.format(n=n_off) if n_off else ""]
    handles += [Line2D([0], [0], ls="none", label=t) for t in notes if t]
    ax.legend(handles=handles, title="최종 판정 (전체 ITEM 수)", loc="upper left", fontsize=8.5, title_fontsize=9,
              frameon=False, alignment="left")


def plot_dashboard(
    items: pd.DataFrame, out: Path, dpi: int = 100, xlim: float = DEFAULT_XLIM,
    name: str = "summary.png", title_suffix: str = "",
) -> Path:
    """판정 지도 summary.png (설계 1-1): 맨 위 판정·근거 개수, 왼쪽 지도, 오른쪽 위 차이·미결의 방향, 오른쪽 범례,
    아래 읽는 법과 이번 결과. 그룹별 그림은 name(파일명)과 title_suffix(제목 뒤 그룹 이름)만 바꿔 같은 배치로 그린다."""
    if dpi < 1:
        raise ValueError("--dpi는 1 이상이어야 합니다.")
    if not np.isfinite(xlim) or xlim <= 0:
        raise ValueError("--xlim은 양수여야 합니다.")
    out.mkdir(parents=True, exist_ok=True)
    (out / name).unlink(missing_ok=True)
    points = map_points(items)
    width, height = MAP_SIZE_IN
    fig = plt.figure(figsize=(width, height))
    try:
        def box(left: float, bottom: float, w: float, h: float):
            return fig.add_axes([left / width, bottom / height, w / width, h / height])

        fig.suptitle(f"{MAP_TITLE}{title_suffix}", x=0.8 / width, ha="left", y=1 - 0.25 / height, fontsize=14,
                     weight="bold")
        fig.text(0.8 / width, 1 - 0.55 / height, _count_line(points), ha="left", va="top", fontsize=10.5,
                 linespacing=1.5)
        drawn = _draw_map(box(0.9, 0.7, 7.4, 5.9), points, xlim)
        _draw_directions(box(9.6, 4.4, 3.0, 2.0), points)
        _map_legend(box(9.0, 0.6, 3.8, 3.0), points, drawn)
        add_figure_note(fig, MAP_HOW_TO_READ, map_this_run(points), dpi=dpi)
        path = out / name
        fig.savefig(path, dpi=dpi, facecolor="white")
        return path
    finally:
        plt.close(fig)


NO_GROUP = "(그룹 없음)"
NO_GROUP_WARNING = "그룹 파일에 없는 ITEM {n:,}개 → '" + NO_GROUP + "' 그룹으로 그림"


def plot_group_dashboards(
    items: pd.DataFrame, groups: pd.DataFrame, out: Path, dpi: int = 100, xlim: float = DEFAULT_XLIM,
) -> list[Path]:
    """그룹마다 summary.png와 같은 배치의 summary_group_<안전한 이름>.png.
    그룹 파일에 없는 ITEM은 NO_GROUP 그룹으로 모은다. 안전한 이름이 겹치면 _2, _3을 붙인다."""
    mapping = dict(zip(groups["ITEM"], groups["group"].fillna(NO_GROUP)))
    group_of = items["ITEM"].astype(str).str.strip().map(mapping)
    missing = int(group_of.isna().sum())
    if missing:
        print(NO_GROUP_WARNING.format(n=missing))
    group_of = group_of.fillna(NO_GROUP)
    paths, used = [], set()
    for group in sorted(group_of.unique(), key=lambda g: (g == NO_GROUP, g)):
        base = f"summary_group_{safe_item_name(group)}"
        stem, k = base, 1
        while stem in used:
            k += 1
            stem = f"{base}_{k}"
        used.add(stem)
        rows = items.loc[group_of == group].reset_index(drop=True)
        paths.append(plot_dashboard(rows, out, dpi=dpi, xlim=xlim, name=f"{stem}.png", title_suffix=f" · {group}"))
    return paths


def _loq_points(items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """LoQ 패널 대상 행과, 축 범위로 자른 좌표(_x, _y)·_clipped·_zero를 붙인 그릴 행을 돌려준다.

    NaN 좌표(0/0, 빈 값)는 놓을 자리가 없어 경고 후 뺀다. 0 이하·무한대·범위 밖은 축 끝으로 자른다."""
    _require_columns(items, {"zone", "doe_center", "LoQ", "center", "delta", "verdict"})
    in_panel = items["zone"].isin(LOQ_ZONES) & (items["verdict"].astype(str) != V_EXCLUDED)
    selected = items.loc[in_panel].assign(verdict=verdict_col(items)[in_panel])     # 색은 최종 판정
    for column in ("doe_center", "LoQ", "center", "delta"):
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        selected["_x"] = selected["doe_center"].abs() / selected["LoQ"]
        # 이동 0 은 허용폭이 0 이어도 "안 움직임"이라 0/0 으로 버리지 않고 아래 끝에 놓는다
        selected["_y"] = np.where(selected["center"] == 0, 0.0, selected["center"].abs() / selected["delta"])
    valid = selected[["_x", "_y"]].notna().all(axis=1)
    invalid_count = int((~valid).sum())
    if invalid_count:
        warnings.warn(
            f"LoQ 패널 좌표가 유효하지 않아 제외한 ITEM {invalid_count}개",
            RuntimeWarning,
            stacklevel=3,
        )
    points = selected.loc[valid].copy()
    unknown = sorted(set(points["verdict"]) - set(TOOL_VERDICT_ORDER))
    if unknown:
        raise ValueError(f"알 수 없는 판정입니다: {', '.join(map(str, unknown))}")
    xy = points[["_x", "_y"]]
    points["_zero"] = (xy <= 0).any(axis=1)
    points["_clipped"] = ((xy < LOQ_AXIS_MIN) | (xy > LOQ_AXIS_MAX)).any(axis=1)
    points[["_x", "_y"]] = xy.clip(LOQ_AXIS_MIN, LOQ_AXIS_MAX)
    return selected, points


def draw_loq(ax, items: pd.DataFrame, flagged: frozenset[str] | None = None) -> dict:
    """주어진 Axes에 LoQ 아래 zone 의 DOE 값/LoQ 대 |이동|/Δ log-log 산점도를 그린다. 네 칸에 쉬운 이름을 붙이고,
    flagged(review.py LoQ 재확인 '확인 필요' ITEM)를 마름모로 겹쳐 그린다. None 이면 재확인 결과가 없는 것.
    반환: {"n": 그린 점, "clipped": 축 끝으로 자른 점, "zero": 그중 0 이하 값, "excluded": NaN이라 뺀 행,
    "flagged": 마름모로 그린 점, "hidden": 둘 다 <LoQ 인데 이동이 허용폭보다 큰 점}."""
    selected, points = _loq_points(items)
    n_clipped = int(points["_clipped"].sum())
    n_zero = int(points["_zero"].sum())

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(LOQ_AXIS_MIN, LOQ_AXIS_MAX)
    ax.set_ylim(LOQ_AXIS_MIN, LOQ_AXIS_MAX)
    # mathtext 눈금(10^-1)은 한글 폰트에 U+2212 글리프가 없어 깨진다. 일반 텍스트로 찍는다.
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        axis.set_minor_formatter(NullFormatter())
    ax.add_patch(Rectangle((1, 1), LOQ_AXIS_MAX - 1, LOQ_AXIS_MAX - 1, facecolor="#D55E00", alpha=0.10,
                           edgecolor="none", zorder=0))
    ax.add_patch(Rectangle((LOQ_AXIS_MIN, 1), 1 - LOQ_AXIS_MIN, LOQ_AXIS_MAX - 1, facecolor="#E69F00", alpha=0.10,
                           edgecolor="none", zorder=0))
    ax.axvline(1, color="#888888", linewidth=0.7, linestyle="--", zorder=1)
    ax.axhline(1, color="#888888", linewidth=0.7, linestyle="--", zorder=1)
    for verdict in TOOL_VERDICT_ORDER:
        group = points.loc[points["verdict"] == verdict]
        for clipped, marker in ((False, "o"), (True, "^")):
            part = group.loc[group["_clipped"] == clipped]
            if not part.empty:
                ax.scatter(part["_x"], part["_y"], s=36, marker=marker, color=TOOL_VERDICT_COLORS[verdict],
                           edgecolors="white", linewidths=0.7, alpha=0.9, zorder=3, clip_on=False)
    hit = points.loc[points["ITEM"].astype(str).isin(flagged or ())]
    ax.scatter(hit["_x"], hit["_y"], s=110, marker="D", facecolors="none", edgecolors="black", linewidths=1.2,
               zorder=4, clip_on=False)
    if selected.empty:
        ax.text(0.5, 0.5, NO_LOQ_ITEMS, transform=ax.transAxes, ha="center", va="center")
    elif points.empty:
        ax.text(0.5, 0.5, NO_VALID_POINTS, transform=ax.transAxes, ha="center", va="center")
    for x, y, note in LOQ_QUADRANT_NOTES:
        ax.text(x, y, note, transform=ax.transAxes, fontsize=8.5, color="#444444", zorder=2,
                ha="right" if x > 0.5 else "left", va="top" if y > 0.5 else "bottom",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.7, pad=1.5))

    counts = points["verdict"].value_counts()
    handles = [Line2D([0], [0], color=TOOL_VERDICT_COLORS[v], marker="o", linestyle="none", markersize=6,
                      label=f"{v}: {int(counts.get(v, 0)):,}") for v in TOOL_VERDICT_ORDER]
    if flagged is not None:
        handles.append(Line2D([0], [0], marker="D", mfc="none", mec="black", linestyle="none", markersize=7,
                              label=LOQ_FLAG_LABEL.format(n=len(hit))))
    handles.append(Line2D([0], [0], color="#555555", marker="^", linestyle="none", markersize=6,
                          label=LOQ_CLIPPED_NOTE.format(n=n_clipped, zero=n_zero)))
    ax.legend(handles=handles, title="최종 판정", loc="upper left", bbox_to_anchor=(1.01, 1.0))
    ax.set_title(LOQ_TITLE)
    ax.set_xlabel(LOQ_XLABEL)
    ax.set_ylabel(LOQ_YLABEL)
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#E2E2E2", linewidth=0.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return {
        "n": len(points),
        "clipped": n_clipped,
        "zero": n_zero,
        "excluded": len(selected) - len(points),
        "flagged": len(hit),
        "hidden": int(((points["_x"] < 1) & (points["_y"] > 1)).sum()),
        "by_verdict": {v: int(counts.get(v, 0)) for v in TOOL_VERDICT_ORDER},
    }




def loq_this_run(counts: dict, flagged: frozenset[str] | None) -> str:
    text = (f"LoQ 아래 ITEM {counts['n']:,}개: " + ", ".join(f"{k} {n:,}" for k, n in counts["by_verdict"].items())
            + f". 둘 다 '<LoQ'인데 허용폭보다 크게 움직인 ITEM {counts['hidden']:,}개."
            + (f" 좌표가 없어 못 그린 ITEM {counts['excluded']:,}개." if counts["excluded"] else ""))
    if flagged is None:
        return text + f" LoQ 재확인 결과({LOQ_REVIEW_CSV.as_posix()})가 없어 '확인 필요'는 표시하지 않았다."
    return text + f" LoQ 재확인 '확인 필요' {counts['flagged']:,}개 (마름모)."


def read_loq_flags(items_csv: Path) -> frozenset[str] | None:
    """items.csv 옆 review/loq_review.csv 의 '확인 필요'(flag True) ITEM. 파일이 없으면 None."""
    path = Path(items_csv).parent / LOQ_REVIEW_CSV
    if not path.is_file():
        return None
    table = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    return frozenset(table.loc[table["flag"].str.strip().str.lower() == "true", "ITEM"].str.strip())


def plot_loq(items: pd.DataFrame, out: Path, dpi: int = 100, flagged: frozenset[str] | None = None) -> Path:
    """LoQ 아래 zone 산점도(draw_loq)를 summary_loq.png로 저장한다. flagged 는 read_loq_flags 결과."""
    remove_own_outputs(out, OWN_OUTPUTS["loq"])
    if dpi < 1:
        raise ValueError("--dpi는 1 이상이어야 합니다.")
    fig, ax = plt.subplots(figsize=(10.5, 7))
    try:
        counts = draw_loq(ax, items, flagged)
        fig.subplots_adjust(left=0.09, right=0.70, top=0.93, bottom=0.10)
        add_figure_note(fig, LOQ_HOW_TO_READ, loq_this_run(counts, flagged), dpi=dpi)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "summary_loq.png"
        fig.savefig(path, dpi=dpi, facecolor="white")
        return path
    finally:
        plt.close(fig)


def select_detail_items(
    items: pd.DataFrame, item_arg: str | None = None, select_all: bool = False,
) -> list[str]:
    """상세 그림 대상 ITEM 코드를 기본(차이/미결), --items, --all 규칙으로 고른다."""
    _require_columns(items, {"ITEM", "verdict"})
    codes = items["ITEM"].astype(str).tolist()
    if select_all:
        return list(dict.fromkeys(codes))
    if item_arg is not None:
        requested = [part.strip() for part in item_arg.split(",")]
        if any(not code for code in requested):
            raise ValueError("--items는 비어 있지 않은 ITEM 코드를 쉼표로 구분해 주세요.")
        missing = sorted(set(requested) - set(codes))
        if missing:
            raise ValueError(f"items.csv에 없는 ITEM 코드입니다: {', '.join(missing)}")
        return list(dict.fromkeys(requested))
    selected = [
        code for code, verdict in zip(codes, verdict_col(items).astype(str))
        if verdict in {"차이", "미결"}
    ]
    return list(dict.fromkeys(selected))


def detail_text(res: dict, item: str | None = None) -> tuple[str, str]:
    """상세 그림 제목과 items.csv reason에 해당하는 판정 사유 문자열을 돌려준다."""
    code = item if item is not None else res.get("ITEM")
    title = f"ITEM {code} - {res['verdict']} ({res.get('zone', '')})"
    return title, str(res["reason"])


def _detail_worker_init(font_path: str | None) -> None:
    """spawn/fork 어느 쪽에서도 worker마다 Agg와 한글 폰트를 설정한다."""
    matplotlib.use("Agg", force=True)
    configure_font(font_path)


def _strip_offsets(n: int) -> np.ndarray:
    """난수 없이 고정한 strip 가로 오프셋."""
    if n < 2:
        return np.zeros(n)
    return np.linspace(-0.18, 0.18, n)


def _detail_worker(payload: dict) -> Path:
    """선택 ITEM 하나의 원시 die와 judge 결과만 받아 상세 PNG를 저장한다."""
    res = payload["res"]
    por = payload["por"]
    doe = payload["doe"]
    mask = payload["outlier"]
    por_cols = payload["por_cols"]
    n, n_por = por.shape
    title, reason = detail_text(res, payload["item"])
    path = payload["out"] / f"{safe_item_name(payload['item'])}.png"

    fig, (left, right) = plt.subplots(figsize=(14, 6.5), ncols=2)
    try:
        positions = np.arange(1, n_por + 2)
        values = [por[:, index] for index in range(n_por)] + [doe]
        series_colors = ["#0072B2"] * n_por + ["#009E73"]
        boxes = left.boxplot(
            values, positions=positions, widths=0.55, showfliers=False,
            patch_artist=True, medianprops={"color": "#333333", "linewidth": 1.2},
            whiskerprops={"color": "#777777"}, capprops={"color": "#777777"},
        )
        for box, color in zip(boxes["boxes"], series_colors):
            box.set_facecolor(color)
            box.set_alpha(0.12)
            box.set_edgecolor(color)
        for position, vals, color in zip(positions, values, series_colors):
            offsets = _strip_offsets(n)
            left.scatter(
                np.full(n, position) + offsets, vals, s=18, color=color,
                alpha=0.55, linewidths=0, zorder=3,
            )
            if mask.any():
                left.scatter(
                    np.full(int(mask.sum()), position) + offsets[mask], vals[mask],
                    s=58, facecolors="none", edgecolors="#D55E00", linewidths=1.2, zorder=4,
                )
        left.set_xticks(positions)
        left.set_xticklabels([*por_cols, "DOE"])
        left.set_title(DETAIL_LEFT_TITLE)
        unit = res.get("UNIT")
        unit = "" if unit is None or pd.isna(unit) else str(unit)
        left.set_ylabel(DETAIL_LEFT_YLABEL + (f" ({unit})" if unit else ""))
        left.legend(
            handles=[
                Line2D([0], [0], color="#0072B2", marker="o", linewidth=0, label="POR"),
                Line2D([0], [0], color="#009E73", marker="o", linewidth=0, label="DOE"),
                Line2D(
                    [0], [0], color="#D55E00", marker="o", markerfacecolor="none",
                    linewidth=0, label=f"{DETAIL_OUTLIER_LABEL}: {int(mask.sum())}",
                ),
            ],
            loc="upper left", fontsize=8,
        )

        d = doe - por.mean(axis=1)
        order = np.argsort(d, kind="mergesort")
        sorted_d = d[order]
        sorted_mask = mask[order]
        ranks = np.arange(1, n + 1)
        k = ci_rank(n)
        right.axvspan(
            k + 0.5, n - k + 0.5, color="#0072B2", alpha=0.09,
            label=f"{DETAIL_CI_LABEL} ({k + 1}-{n - k})", zorder=0,
        )
        right.bar(
            ranks, sorted_d, width=0.82, color="#56B4E9", alpha=0.85,
            label=DETAIL_BAR_LABEL, zorder=2,
        )
        if sorted_mask.any():
            right.scatter(
                ranks[sorted_mask], sorted_d[sorted_mask], s=58, facecolors="none",
                edgecolors="#D55E00", linewidths=1.2, label=DETAIL_OUTLIER_LABEL, zorder=4,
            )
        right.axhline(0, color="#999999", linewidth=0.6, zorder=1)

        policy = float(res["policy_margin"])
        run_margin = float(res["run_margin"])
        delta = float(res["delta"])
        right.axhspan(
            policy, policy + run_margin, color="#E69F00", alpha=0.12,
            label=DETAIL_RUN_BAND_LABEL, zorder=0,
        )
        right.axhspan(-policy - run_margin, -policy, color="#E69F00", alpha=0.12, zorder=0)
        for sign, label in ((-1, DETAIL_POLICY_LABEL), (1, "_nolegend_")):
            right.axhline(
                sign * policy, color="#666666", linewidth=1.0, linestyle="--", label=label,
            )
        for sign, label in ((-1, DETAIL_TOTAL_LABEL), (1, "_nolegend_")):
            right.axhline(
                sign * delta, color="#D55E00", linewidth=1.4, linestyle="-", label=label,
            )

        loq = float(res["LoQ"])
        if np.isfinite(loq):
            right.axhline(
                loq, color="#CC79A7", linewidth=1.1, linestyle=":", label=DETAIL_LOQ_LABEL,
            )
        right.set_xlim(0.5, n + 0.5)
        right.set_title(DETAIL_RIGHT_TITLE)
        right.set_xlabel(DETAIL_RIGHT_XLABEL)
        right.set_ylabel(DETAIL_RIGHT_YLABEL)
        right.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)

        for ax in (left, right):
            ax.set_axisbelow(True)
            ax.grid(axis="y", color="#E2E2E2", linewidth=0.5)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)

        fig.suptitle(title, fontsize=14)
        fig.text(0.06, 0.025, reason, fontsize=9, ha="left", wrap=True)
        below_quant = str(res["zone"]) != "정량"
        if below_quant:
            fig.text(0.06, 0.065, DETAIL_LOQ_FOOTNOTE, fontsize=9, ha="left", color="#555555")
        fig.subplots_adjust(
            left=0.06, right=0.82, top=0.86, bottom=0.20 if below_quant else 0.15, wspace=0.30,
        )
        fig.savefig(path, dpi=payload["dpi"], facecolor="white", bbox_inches="tight")
        return path
    finally:
        plt.close(fig)


def plot_details(items: pd.DataFrame, raw: tuple, args: argparse.Namespace) -> list[Path]:
    """선택 ITEM을 judge_item으로 판정하고 ITEM당 detail/<safe code>.png 한 장을 저장한다."""
    if args.dpi < 1:
        raise ValueError("--dpi는 1 이상이어야 합니다.")
    if args.jobs < 1:
        raise ValueError("--jobs는 1 이상이어야 합니다.")
    selected = select_detail_items(items, args.items, args.all)
    names = [safe_item_name(item) for item in selected]
    if len(set(names)) != len(names):
        raise ValueError("ITEM 코드를 파일시스템 안전 문자로 바꾼 이름이 중복됩니다.")
    out = Path(args.out) / "detail"
    remove_own_outputs(Path(args.out), OWN_OUTPUTS["detail"])
    if not selected:
        return []

    wide, por_cols, units, levels, blank, bmap = raw
    groups = {str(item): group for item, group in wide.groupby("ITEM", sort=False)}
    missing = [item for item in selected if item not in groups]
    if missing:
        raise ValueError(f"원시 데이터에서 찾지 못한 ITEM 코드입니다: {', '.join(missing)}")

    out.mkdir(parents=True, exist_ok=True)
    payloads = []
    for item in selected:
        group = groups[item]
        res, mask = judge_item(item, group, por_cols, units, args.r, levels, blank, bmap)
        payloads.append({
            "res": res,
            "item": item,
            "por": group[por_cols].to_numpy(float),
            "doe": group["DOE"].to_numpy(float),
            "outlier": np.asarray(mask, dtype=bool),
            "por_cols": por_cols,
            "out": out,
            "dpi": args.dpi,
        })

    if args.jobs == 1:
        _detail_worker_init(args.font)
        return [_detail_worker(payload) for payload in payloads]
    with mp.Pool(processes=args.jobs, initializer=_detail_worker_init, initargs=(args.font,)) as pool:
        return pool.map(_detail_worker, payloads)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    configure_font(args.font)
    if not args.summary and not args.detail:
        return
    items = pd.read_csv(args.items_csv, encoding="utf-8-sig")
    out = Path(args.out)
    paths = []
    if args.summary:
        # 그룹 수가 줄거나 --groups를 빼고 다시 돌린 경우 예전 그룹 그림이 남지 않게 먼저 지운다.
        remove_own_outputs(out, OWN_OUTPUTS["group"])
        paths.append(plot_dashboard(items, out, dpi=args.dpi, xlim=args.xlim))
        if args.groups:
            paths.extend(plot_group_dashboards(items, read_groups(args.groups), out, dpi=args.dpi, xlim=args.xlim))
        paths.append(plot_loq(items, out, dpi=args.dpi, flagged=read_loq_flags(Path(args.items_csv))))
        if args.full:
            paths.extend(plot_summary(items, out, dpi=args.dpi, per_page=args.per_page, xlim=args.xlim))
        else:
            # 예전 실행의 summary_NNN.png가 이번 결과처럼 보이지 않게 지운다.
            remove_own_outputs(out, OWN_OUTPUTS["summary"])
    if args.detail:
        raw = _load_recompute_inputs(args, "상세 그림")
        paths.extend(plot_details(items, raw, args))
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
