"""items.csv로 ITEM 판정 요약 그림을 만들고, 필요하면 같은 판정 함수로 결과를 다시 계산한다.

요약 그림에는 item_map의 실제 항목 이름을 사용하지 않는다. 상세 그림을 추가할 때에도
파일명은 safe_item_name()을 거친 ITEM 코드만 사용해야 한다.
"""
from __future__ import annotations

import argparse
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
from matplotlib.patches import Patch, Rectangle

from infra_compare import load_blank, read_csv_auto
from por_doe_compare import ORDER, add_common_args, judge_item, load_levels, load_wide

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
PAGE_LEGEND_TITLE = "장별 판정 개수"
LOQ_TITLE = "LoQ 미만: DOE 중심과 이동"
LOQ_XLABEL = "|DOE 중심| / LoQ"
LOQ_YLABEL = "|center| / Δ"
LOQ_FOOTNOTE = "도구의 차이 규칙: CI가 통째로 ±Δ 밖(lo > Δ 또는 hi < -Δ); |center|/Δ ≥ 1이 아님."
NO_LOQ_ITEMS = "해당 ITEM 없음"
NO_VALID_POINTS = "표시할 유효한 좌표 없음"

# 한글 렌더 테스트는 그림에 넣는 모든 고정 문자열을 이 목록에서 가져간다.
KOREAN_TEXTS = tuple(dict.fromkeys(
    CATEGORY_ORDER
    + TOOL_VERDICT_ORDER
    + (
        SUMMARY_TITLE,
        SUMMARY_XLABEL,
        SUMMARY_YLABEL,
        PAGE_LEGEND_TITLE,
        LOQ_TITLE,
        LOQ_XLABEL,
        LOQ_YLABEL,
        "차이 영역",
        "도구 판정",
        LOQ_FOOTNOTE,
        NO_LOQ_ITEMS,
        NO_VALID_POINTS,
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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items-csv", default="por_doe_out/items.csv", help="판정 결과 items.csv")
    summary = ap.add_mutually_exclusive_group()
    summary.add_argument("--summary", dest="summary", action="store_true", help="요약 그림 작성 (기본)")
    summary.add_argument("--no-summary", dest="summary", action="store_false", help="요약 그림 생략")
    ap.set_defaults(summary=True)
    ap.add_argument("--out", default="por_doe_out/plots/", help="PNG output directory")
    ap.add_argument("--dpi", type=int, default=100, help="PNG 해상도 (기본 100)")
    ap.add_argument("--font", metavar="PATH", help="한글 폰트 파일 경로")
    ap.add_argument("--per-page", type=int, default=1200, help="요약 한 장의 최대 ITEM 수 (기본 1200)")

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


def _load_recompute_inputs(args: argparse.Namespace):
    """재계산과 이후 상세 그림이 공유할 원시 데이터/level/blank 연결."""
    if not args.por or not args.doe:
        raise ValueError("재계산에는 --por(회차별)와 --doe가 필요합니다.")
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
    result = result[first + [c for c in result.columns if c not in first]]
    return result.sort_values(
        ["verdict", "ITEM"],
        key=lambda s: s.map(ORDER) if s.name == "verdict" else s,
    ).reset_index(drop=True)


def verdict_category(row: pd.Series) -> str:
    """도구 verdict/reason/zone을 요약 그림의 여섯 표시 범주로 변환한다."""
    verdict = str(row["verdict"])
    reason = "" if pd.isna(row["reason"]) else str(row["reason"])
    zone = "" if pd.isna(row.get("zone", "")) else str(row.get("zone", ""))
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


def plot_summary(items: pd.DataFrame, out: Path, dpi: int = 100, per_page: int = 1200) -> list[Path]:
    """전체 ITEM을 판정/center-delta 비율 순으로 정렬해 여러 요약 PNG로 저장한다."""
    if per_page < 1:
        raise ValueError("--per-page는 1 이상이어야 합니다.")
    if dpi < 1:
        raise ValueError("--dpi는 1 이상이어야 합니다.")
    work = _normalized_summary(items)
    omitted = int((~work["_valid"]).sum())
    if omitted:
        warnings.warn(
            f"delta가 0이거나 유효하지 않아 요약에서 제외한 ITEM {omitted}개",
            RuntimeWarning,
            stacklevel=2,
        )

    out.mkdir(parents=True, exist_ok=True)
    pages = [work.iloc[start:start + per_page] for start in range(0, len(work), per_page)] or [work]
    paths = []
    for page_number, page in enumerate(pages, 1):
        count = len(page)
        height = max(3.5, min(30.0, 1.8 + 0.018 * max(count, 1)))
        fig, ax = plt.subplots(figsize=(10, height))
        try:
            y = np.arange(count)[::-1]
            for category in CATEGORY_ORDER:
                mask = ((page["_category"] == category) & page["_valid"]).to_numpy()
                if not mask.any():
                    continue
                color = CATEGORY_COLORS[category]
                ax.hlines(
                    y[mask], page.loc[mask, "_low"], page.loc[mask, "_high"],
                    color=color, linewidth=0.55, alpha=0.8, zorder=2,
                )
                ax.scatter(
                    page.loc[mask, "_center"], y[mask], s=12, color=color,
                    edgecolors="white", linewidths=0.25, zorder=3,
                )

            ax.axvspan(-1, 1, color="#0072B2", alpha=0.07, zorder=0)
            ax.axvline(-1, color="#666666", linewidth=0.7, linestyle="--", zorder=1)
            ax.axvline(1, color="#666666", linewidth=0.7, linestyle="--", zorder=1)
            ax.axvline(0, color="#999999", linewidth=0.5, zorder=1)
            valid_low = page.loc[page["_valid"], "_low"].to_numpy(float)
            valid_high = page.loc[page["_valid"], "_high"].to_numpy(float)
            xmin = min(-1.25, float(valid_low.min()) * 1.05) if len(valid_low) else -1.5
            xmax = max(1.25, float(valid_high.max()) * 1.05) if len(valid_high) else 1.5
            ax.set_xlim(xmin, xmax)
            ax.set_ylim(-1, max(count, 1))
            ax.set_yticks([])
            ax.tick_params(axis="y", length=0)
            ax.set_xlabel(SUMMARY_XLABEL)
            ax.set_ylabel(SUMMARY_YLABEL)
            start = (page_number - 1) * per_page
            ax.set_title(f"{SUMMARY_TITLE} ({start + 1}–{start + count} / {len(work)})")
            ax.set_axisbelow(True)
            ax.grid(axis="x", color="#DDDDDD", linewidth=0.5)
            for spine in ("top", "right", "left"):
                ax.spines[spine].set_visible(False)

            counts = page["_category"].value_counts()
            handles = [
                Line2D(
                    [0], [0], color=CATEGORY_COLORS[category], marker="o", markersize=4,
                    linewidth=1.2, label=f"{category}: {int(counts.get(category, 0)):,}",
                )
                for category in CATEGORY_ORDER
            ]
            ax.legend(handles=handles, title=PAGE_LEGEND_TITLE, loc="upper left", bbox_to_anchor=(1.01, 1.0))
            fig.subplots_adjust(left=0.09, right=0.79, top=0.97, bottom=max(0.025, 0.7 / height))
            path = out / f"summary_{page_number:03d}.png"
            fig.savefig(path, dpi=dpi, facecolor="white", bbox_inches="tight")
            paths.append(path)
        finally:
            plt.close(fig)
    return paths


def plot_loq(items: pd.DataFrame, out: Path, dpi: int = 100) -> Path:
    """LoQ 미만 zone의 DOE 중심/LoQ와 center/delta 산점도를 저장한다."""
    _require_columns(items, {"zone", "doe_center", "LoQ", "center", "delta", "verdict"})
    if dpi < 1:
        raise ValueError("--dpi는 1 이상이어야 합니다.")
    selected = items.loc[items["zone"].isin(["검출한계 이하", "검출~정량"])].copy()
    for column in ("doe_center", "LoQ", "center", "delta"):
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        selected["_x"] = selected["doe_center"].abs() / selected["LoQ"]
        selected["_y"] = selected["center"].abs() / selected["delta"]
    valid = np.isfinite(selected[["_x", "_y"]]).all(axis=1)
    invalid_count = int((~valid).sum())
    if invalid_count:
        warnings.warn(
            f"LoQ 패널 좌표가 유효하지 않아 제외한 ITEM {invalid_count}개",
            RuntimeWarning,
            stacklevel=2,
        )
    points = selected.loc[valid]
    unknown = sorted(set(points["verdict"]) - set(TOOL_VERDICT_ORDER))
    if unknown:
        raise ValueError(f"알 수 없는 판정입니다: {', '.join(map(str, unknown))}")

    out.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    try:
        xmax = max(1.25, float(points["_x"].max()) * 1.05) if len(points) else 1.5
        ymax = max(1.25, float(points["_y"].max()) * 1.05) if len(points) else 1.5
        ax.set_xlim(0, xmax)
        ax.set_ylim(0, ymax)
        ax.add_patch(Rectangle(
            (1, 1), xmax - 1, ymax - 1, facecolor="#D55E00", alpha=0.10,
            edgecolor="none", zorder=0,
        ))
        ax.axvline(1, color="#777777", linewidth=0.8, linestyle="--", zorder=1)
        ax.axhline(1, color="#777777", linewidth=0.8, linestyle="--", zorder=1)
        for verdict in TOOL_VERDICT_ORDER:
            group = points.loc[points["verdict"] == verdict]
            if group.empty:
                continue
            ax.scatter(
                group["_x"], group["_y"], s=36, label=verdict,
                color=TOOL_VERDICT_COLORS[verdict], edgecolors="white", linewidths=0.7,
                alpha=0.9, zorder=3,
            )
        if selected.empty:
            ax.text(0.5, 0.5, NO_LOQ_ITEMS, transform=ax.transAxes, ha="center", va="center")
        elif points.empty:
            ax.text(0.5, 0.5, NO_VALID_POINTS, transform=ax.transAxes, ha="center", va="center")

        handles = [Patch(facecolor="#D55E00", alpha=0.10, label="차이 영역")]
        counts = points["verdict"].value_counts()
        handles.extend(
            Line2D(
                [0], [0], color=TOOL_VERDICT_COLORS[verdict], marker="o", linestyle="none",
                markersize=6, label=f"{verdict}: {int(counts.get(verdict, 0)):,}",
            )
            for verdict in TOOL_VERDICT_ORDER
        )
        ax.legend(handles=handles, title="도구 판정", loc="upper left", bbox_to_anchor=(1.01, 1.0))
        ax.set_title(LOQ_TITLE)
        ax.set_xlabel(LOQ_XLABEL)
        ax.set_ylabel(LOQ_YLABEL)
        ax.set_axisbelow(True)
        ax.grid(color="#E2E2E2", linewidth=0.5)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        fig.text(0.08, 0.025, LOQ_FOOTNOTE, fontsize=9, ha="left")
        fig.subplots_adjust(left=0.10, right=0.75, top=0.90, bottom=0.18)
        path = out / "summary_loq.png"
        fig.savefig(path, dpi=dpi, facecolor="white", bbox_inches="tight")
        return path
    finally:
        plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    configure_font(args.font)
    if not args.summary:
        return
    items = pd.read_csv(args.items_csv, encoding="utf-8-sig")
    out = Path(args.out)
    paths = plot_summary(items, out, dpi=args.dpi, per_page=args.per_page)
    paths.append(plot_loq(items, out, dpi=args.dpi))
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
