"""기존·개선 비교 폴더(<조합>/compare/)를 사람이 읽는 표로 바꾼다: 결론 한 문장, 범위 한 줄, 시트(이름, 표, 메모).

report.py 의 compare/report.html 과 엑셀 compare/비교.xlsx 가 같은 시트를 쓴다. 숫자 계산은 compare_before_after·
group_summary 가 이미 한 것(overview.csv, group_summary.csv, compare.csv 의 *_ratio 열)을 읽어 고르고 줄 세우기만 한다.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import group_summary
from compare_metrics import BETTER, EQUIV, NOT_EQUIV, RATIO_KPIS, SAME, TREND_BAND, WORSE

WORKBOOK = "비교.xlsx"
WORKBOOK_ANON = "비교_anon.xlsx"
SUMMARY, GROUPS, VERDICTS, ITEMS, WORSENED, LEVELS = "요약", "그룹별", "판정 변화", "ITEM별", "나빠진 ITEM", "그룹×LEVEL"
TOTAL = "전체"

RULE = (f"판단: 비(ITEM마다 개선÷기존을 구한 값의 중앙값)가 {1 - TREND_BAND:.1f} 미만이면 {BETTER}, "
        f"{1 + TREND_BAND:.1f} 초과면 {WORSE}, 그 사이는 {SAME} (±{TREND_BAND:.0%}). 동등 아닌 ITEM 수도 개수 비(개선÷기존)로 같은 기준. "
        "기존 값이 0이거나 빈 ITEM은 비에서 뺀다 (비에서 뺀 ITEM 열). 그룹의 판단은 측정 정밀도 비로 정한다.")
LEVELS_NOTE = ("그룹 × LEVEL 은 기존·개선 결과 폴더 둘 다 stability/group_levels.csv 가 있을 때 만든다 "
               "(판정할 때 level 파일과 groups 파일을 준 결과).")
LEVELS_SOURCE = "칸마다 그 결과의 모든 ITEM 으로 낸 측정 정밀도 중앙값 (각 결과 폴더의 stability/group_levels.csv)."
VERDICT_ORDER = ("차이", "미결", EQUIV, "판정 제외")
SHIFTS = ("동등이 됨", "동등에서 벗어남", "바뀜", "그대로")

TIPS = {
    "지표": "낮을수록 좋은 흔들림 지표와 동등 아닌 ITEM 수",
    "기존": "기존 결과의 ITEM 중앙값 (% 지표) 또는 개수",
    "개선": "개선 결과의 ITEM 중앙값 (% 지표) 또는 개수",
    "변화": "개선 − 기존 (% 지표는 %p)",
    "비": "ITEM 마다 개선 ÷ 기존을 구한 값의 중앙값. 1보다 작으면 좋아짐",
    "좋아진 ITEM %": (f"비가 {1 - TREND_BAND:.1f} 미만인 ITEM 비율 (ITEM 하나하나에 같은 ±{TREND_BAND:.0%} 기준). "
                     "동등 아닌 ITEM 수 줄은 기존에 동등 아니던 ITEM 중 동등이 된 비율"),
    "판단": RULE,
    "비에 쓴 ITEM": "비를 계산한 ITEM 수",
    "비에서 뺀 ITEM": "기존 값이 0이거나 빈 칸이라 비를 계산하지 못한 ITEM 수",
    "가장 좋아진 것": f"네 흔들림 지표 중 비가 가장 작은 것. 그 비도 {1 - TREND_BAND:.1f} 이상이면 빈 칸",
    "변화 종류": "동등이 됨 = 기존 동등 아님 → 개선 동등, 동등에서 벗어남 = 그 반대",
    "정렬 의심": "같은 ITEM 인데 POR 중앙값이 20% 넘게 달라 다른 ITEM 일 수 있음 (비교에는 포함)",
}


@dataclass(frozen=True)
class Compared:
    """compare/ 폴더 한 벌. groups·levels 는 그룹 파일로 비교했을 때만."""
    scope: dict
    overview: pd.DataFrame
    rows: pd.DataFrame
    groups: pd.DataFrame | None
    levels: pd.DataFrame | None

    @property
    def grouped(self) -> bool:
        return bool(self.scope["grouped"])


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype={"ITEM": str, "ID": str, "group": str, "그룹": str,
                                                         "level": str})


def _flag(v) -> bool:
    return str(v).strip().lower() in ("true", "1")


def load(folder: Path) -> Compared:
    folder = Path(folder)
    scope = _read(folder / "scope.csv").iloc[0].to_dict()
    for k in ("grouped", "misaligned_included"):
        scope[k] = _flag(scope[k])
    gs = folder / group_summary.OUT_DIR / "group_summary.csv"
    lv = folder / "group_levels.csv"
    grouped = scope["grouped"]
    return Compared(scope, _read(folder / "overview.csv"), _read(folder / "compare.csv"),
                    _read(gs) if grouped and gs.is_file() else None,
                    _read(lv) if grouped and lv.is_file() else None)


def _finite(v) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _sig(v, digits: int = 3):
    return float(f"{float(v):.{digits}g}") if _finite(v) else math.nan


def _r3(v):
    return round(float(v), 3) if _finite(v) else math.nan


def scope_line(scope: dict) -> str:
    s = scope
    one_side = int(s["n_only_before"]) + int(s["n_only_after"])
    parts = [f"기존 {int(s['n_before']):,}개 · 개선 {int(s['n_after']):,}개 중 둘 다 있는 ITEM {int(s['n_matched']):,}개"
             + (f" (한쪽에만 있는 {one_side:,}개는 뺌)" if one_side else "")]
    if s["grouped"] and int(s["n_ungrouped"]):
        parts.append(f"그룹 파일에 없는 ITEM {int(s['n_ungrouped']):,}개는 비교에서 뺌")
    parts.append(f"비교 {int(s['n_compared']):,}개")
    if int(s["n_verdict_excluded"]):
        parts.append(f"판정 제외 {int(s['n_verdict_excluded']):,}개는 지표에서 뺌")
    if int(s["n_misaligned"]):
        parts.append(f"정렬 의심 {int(s['n_misaligned']):,}개 {'포함' if s['misaligned_included'] else '뺌'}")
    return " · ".join(parts)


def _group_rows(c: Compared) -> pd.DataFrame:
    g = c.groups[c.groups["그룹"] != TOTAL]
    return g.sort_values("측정 정밀도 비 중앙값(개선/기존)", kind="mergesort", na_position="last")


def conclusion(c: Compared) -> str:
    """'측정 정밀도 39% 좋아짐 · 그룹 8개 중 6개 좋아짐 (가장 큰 IOFF 0.42배) · 나빠짐 RON · 동등 아님 12→8개'."""
    ov = c.overview.set_index("kpi")
    prec = ov.loc[RATIO_KPIS[0].key]
    r = float(prec["ratio_median"])
    if not _finite(r):
        head = "측정 정밀도 비교할 ITEM 없음"
    elif prec["trend"] == BETTER:
        head = f"측정 정밀도 {(1 - r) * 100:.0f}% {BETTER}"
    elif prec["trend"] == WORSE:
        head = f"측정 정밀도 {(r - 1) * 100:.0f}% {WORSE}"
    else:
        head = f"측정 정밀도 {SAME} ({r:.2f}배)"
    parts = [head]
    if c.groups is not None:
        g = _group_rows(c)
        good = g[g["판단"] == BETTER]
        text = f"그룹 {len(g)}개 중 {len(good)}개 {BETTER}"
        if len(good):
            best = good.iloc[0]
            text += f" (가장 큰 {best['그룹']} {float(best['측정 정밀도 비 중앙값(개선/기존)']):.2f}배)"
        parts.append(text)
        bad = g.loc[g["판단"] == WORSE, "그룹"].tolist()
        if bad:
            parts.append(f"{WORSE} {', '.join(bad)}")
    ne = ov.loc[NOT_EQUIV]
    parts.append(f"동등 아님 {int(ne['before']):,}→{int(ne['after']):,}개")
    return " · ".join(parts)


def summary_table(c: Compared) -> pd.DataFrame:
    rows = []
    for r in c.overview.to_dict("records"):
        is_count = r["kpi"] == NOT_EQUIV
        rows.append({"지표": r["name"] if is_count else f"{r['name']} % 중앙값",
                     "기존": r["before"] if is_count else _sig(r["before"]),
                     "개선": r["after"] if is_count else _sig(r["after"]),
                     "변화": r["change"] if is_count else _sig(r["change"]),
                     "비": _r3(r["ratio_median"]),
                     "좋아진 ITEM %": round(float(r["improved_pct"]), 1) if _finite(r["improved_pct"]) else math.nan,
                     "판단": r["trend"] if isinstance(r["trend"], str) else "",
                     "비에 쓴 ITEM": math.nan if is_count else int(r["n_ratio"]),
                     "비에서 뺀 ITEM": math.nan if is_count else int(r["n_skipped"])})
    return pd.DataFrame(rows)


GROUP_COLS = {      # 시트 열 ← group_summary.csv 열
    "그룹": "그룹", "ITEM 수": "ITEM 수",
    "측정 정밀도 기존 %": "측정 정밀도% 기존 중앙값", "측정 정밀도 개선 %": "측정 정밀도% 개선 중앙값",
    "측정 정밀도 비": "측정 정밀도 비 중앙값(개선/기존)", "좋아진 ITEM %": "측정 정밀도 좋아진 %",
    "σ_die 비": "σ_die 비 중앙값(개선/기존)", "σ_run 비": "σ_run 비 중앙값(개선/기존)",
    "90% 구간 폭 비": "90% 구간 폭 비 중앙값(개선/기존)",
    "동등 아님 기존": "기존 동등 아님", "동등 아님 개선": "개선 동등 아님",
    "판단": "판단", "가장 좋아진 것": "가장 좋아진 것",
}


def groups_table(c: Compared) -> pd.DataFrame:
    total = c.groups[c.groups["그룹"] == TOTAL]
    t = pd.concat([total, _group_rows(c)], ignore_index=True)
    return pd.DataFrame({new: t[old] for new, old in GROUP_COLS.items()}).fillna({"판단": "", "가장 좋아진 것": ""})


def _in_scope(c: Compared) -> pd.DataFrame:
    rows = c.rows
    if not c.scope["misaligned_included"]:
        rows = rows[~rows["misaligned"].map(_flag)]
    return rows


def _shift(before: str, after: str) -> str:
    if before == after:
        return SHIFTS[3]
    if after == EQUIV:
        return SHIFTS[0]
    return SHIFTS[1] if before == EQUIV else SHIFTS[2]


def verdicts_table(c: Compared) -> pd.DataFrame:
    rows = _in_scope(c)
    b, a = rows["verdict_before"].fillna("").astype(str), rows["verdict_after"].fillna("").astype(str)
    key = pd.DataFrame({"기존 판정": b, "개선 판정": a})
    t = key.value_counts().rename(TOTAL).reset_index()
    if c.grouped:
        by = pd.crosstab([b.rename("기존 판정"), a.rename("개선 판정")], rows["group"]).reset_index()
        t = t.merge(by, on=["기존 판정", "개선 판정"], how="left")
    t.insert(2, "변화 종류", [_shift(x, y) for x, y in zip(t["기존 판정"], t["개선 판정"])])

    def rank(v):
        return VERDICT_ORDER.index(v) if v in VERDICT_ORDER else len(VERDICT_ORDER)
    order = sorted(range(len(t)), key=lambda i: (SHIFTS.index(t["변화 종류"][i]), -t[TOTAL][i],
                                                  rank(t["기존 판정"][i]), rank(t["개선 판정"][i])))
    return t.iloc[order].reset_index(drop=True)


def _item_frame(rows: pd.DataFrame, id_of: Callable[[str], str], names: bool, grouped: bool) -> dict:
    cols = {"ID": rows["ITEM"].map(id_of)}
    if names:
        cols["ITEM"] = rows["ITEM"]
    if grouped:
        cols["그룹"] = rows["group"]
    return cols


def items_table(c: Compared, id_of: Callable[[str], str], names: bool) -> pd.DataFrame:
    rows = c.rows.sort_values("group", kind="mergesort") if c.grouped else c.rows
    cols = _item_frame(rows, id_of, names, c.grouped)
    cols |= {"기존 판정": rows["verdict_before"].fillna(""), "개선 판정": rows["verdict_after"].fillna("")}
    for k in RATIO_KPIS:
        cols[f"{k.name} 기존 %"] = rows[f"{k.value}_before"].map(lambda v: _sig(v, 4))
        cols[f"{k.name} 개선 %"] = rows[f"{k.value}_after"].map(lambda v: _sig(v, 4))
        cols[f"{k.name} 비"] = rows[f"{k.key}_ratio"].map(_r3)
    cols["정렬 의심"] = rows["misaligned"].map(lambda v: "예" if _flag(v) else "")
    return pd.DataFrame(cols).reset_index(drop=True)


def worsened_table(c: Compared, id_of: Callable[[str], str], names: bool) -> pd.DataFrame:
    """측정 정밀도 비가 나빠짐 기준(1 + TREND_BAND)을 넘는 ITEM, 비 큰 순. 판정 제외는 뺀다."""
    rows = _in_scope(c)
    rows = rows[~(rows["verdict_before"].eq("판정 제외") | rows["verdict_after"].eq("판정 제외"))]
    key = f"{RATIO_KPIS[0].key}_ratio"
    rows = rows[rows[key] > 1 + TREND_BAND].sort_values(key, ascending=False, kind="mergesort")
    prec = RATIO_KPIS[0]
    cols = _item_frame(rows, id_of, names, c.grouped)
    cols |= {"측정 정밀도 기존 %": rows[f"{prec.value}_before"].map(_sig),
             "측정 정밀도 개선 %": rows[f"{prec.value}_after"].map(_sig),
             "측정 정밀도 비": rows[key].map(_r3)}
    for k in RATIO_KPIS[1:3]:
        cols[f"{k.name} 비"] = rows[f"{k.key}_ratio"].map(_r3)
    cols |= {"기존 판정": rows["verdict_before"].fillna(""), "개선 판정": rows["verdict_after"].fillna("")}
    return pd.DataFrame(cols).reset_index(drop=True)


def levels_table(c: Compared) -> pd.DataFrame:
    t = c.levels
    return pd.DataFrame({"그룹": t["group"], "LEVEL": t["level"], "기존 ITEM 수": t["n_items_before"],
                         "개선 ITEM 수": t["n_items_after"], "측정 정밀도 기존 %": t["before"].map(_sig),
                         "측정 정밀도 개선 %": t["after"].map(_sig), "비": t["ratio"].map(_r3)})


def sheets(c: Compared, id_of: Callable[[str], str], names: bool) -> list[tuple[str, pd.DataFrame, tuple[str, ...]]]:
    """엑셀 시트와 리포트 표 (이름, 표, 표 아래 메모). names=False 면 실제 ITEM 이름 열을 뺀다 (ID 만)."""
    out = [(SUMMARY, summary_table(c), (conclusion(c), scope_line(c.scope), RULE))]
    if c.groups is not None:
        out.append((GROUPS, groups_table(c), ("측정 정밀도 비가 작은(많이 좋아진) 그룹부터. 맨 위는 전체.",)))
    out += [(VERDICTS, verdicts_table(c), ("ITEM 수. 판정 제외도 센다.",)),
            (ITEMS, items_table(c, id_of, names), ("비교한 ITEM 전부. % 는 POR 중앙값 대비.",)),
            (WORSENED, worsened_table(c, id_of, names),
             (f"측정 정밀도 비가 {1 + TREND_BAND:.1f} 넘는 ITEM, 비 큰 순. 판정 제외는 뺐다.",))]
    if c.levels is not None:
        out.append((LEVELS, levels_table(c), (LEVELS_SOURCE,)))
    return out
