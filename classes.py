"""ITEM 분류 보기 (참고, 판정 불변): items.csv 의 분류 열(classify.py)을 세고 그림으로 그린다. dcc classes 가 부른다.

  python classes.py --input items.csv --out DIR [--groups ITEM,group 파일] [원데이터 인자 (por_doe_compare 와 같음)]

DIR 에 쓴다:
  counts.csv                   분류 축(cls_*)과 판정 길(route)의 값마다 ITEM 수. 전체, --groups 를 주면 그룹마다
  items_by_route.csv           ITEM 마다 판정 길, 그 길의 참고 결과, 분류 값 (판정 길 순서)
  classes.png                  축마다 막대 그림
  examples/<판정 길>/<ITEM>.png  판정 길마다 ITEM 3개까지 ITEM 한 장 그림 (원데이터 --por, --doe 를 줄 때만)
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

from classify import AXES, CLS_COLS, RESULT_COLS, ROUTE_NAMES, ROUTE_TITLE, route_counts
from compare_metrics import safe_group_name
from infra_compare import read_groups
from por_doe_compare import ORDER, pool_map

GROUP_ALL = "전체"
UNGROUPED = "미지정"
SEP = ";"
EXAMPLES_DIR = "examples"
EXAMPLES_PER_ROUTE = 3
COUNT_COLS = ["group", "axis", "value", "n_items", "share"]
# (열, 그림 제목, 규칙에 적힌 값 순서)
AXIS_VIEW = [(a.column, a.title, a.known) for a in AXES] + [("route", ROUTE_TITLE, ROUTE_NAMES)]


def read_items(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = [c for c in (*CLS_COLS, "route") if c not in df.columns]
    if missing:
        raise SystemExit(f"{path}: 분류 열이 없습니다 ({', '.join(missing)}). 판정(dcc judge)을 다시 실행하세요")
    return df


def value_counts(values: pd.Series, known: tuple[str, ...]) -> list[tuple[str, int]]:
    """';' 로 이은 값은 하나씩 센다. 순서: known (0개도), 그다음 나온 값을 많은 순서로."""
    parts = values.str.split(SEP).explode().str.strip()
    n = parts[parts != ""].value_counts()
    extra = sorted((v for v in n.index if v not in known), key=lambda v: (-n[v], v))
    return [(v, int(n.get(v, 0))) for v in (*known, *extra)]


def counts(items: pd.DataFrame, groups: pd.Series | None) -> pd.DataFrame:
    """COUNT_COLS. 전체, 그리고 groups(ITEM 행마다 그룹 이름)가 있으면 그룹마다 (미지정은 맨 끝)."""
    parts = [(GROUP_ALL, items)]
    if groups is not None:
        names = sorted(groups.unique(), key=lambda g: (g == UNGROUPED, g))
        parts += [(g, items[groups == g]) for g in names]
    rows = [{"group": g, "axis": col, "value": v, "n_items": n, "share": n / len(part) if len(part) else math.nan}
            for g, part in parts for col, _, known in AXIS_VIEW for v, n in value_counts(part[col], known)]
    return pd.DataFrame(rows, columns=COUNT_COLS)


def by_route(items: pd.DataFrame, groups: pd.Series | None) -> pd.DataFrame:
    """판정 길 순서, 그 안은 ITEM 이름 순서."""
    head = ["route", "ID", "ITEM"] + (["group"] if groups is not None else []) + ["verdict_final"]
    t = items.assign(group=groups) if groups is not None else items
    rank = {name: i for i, name in enumerate(ROUTE_NAMES)}
    t = t.assign(_r=t["route"].map(rank)).sort_values(["_r", "ITEM"], kind="stable")
    return t[head + list(RESULT_COLS) + list(CLS_COLS)].reset_index(drop=True)


def pick_examples(items: pd.DataFrame) -> dict[str, list[str]]:
    """판정 길마다 ITEM 을 EXAMPLES_PER_ROUTE 개까지: 최종 판정(차이, 미결, 동등, 판정 제외 순)마다 이름이 가장 앞선
    ITEM 하나씩 먼저, 모자라면 나머지를 이름 순서로."""
    out = {}
    for route in ROUTE_NAMES:
        t = items[items["route"] == route]
        t = t.assign(_v=t["verdict_final"].map(ORDER).fillna(len(ORDER))).sort_values(["_v", "ITEM"], kind="stable")
        firsts = t.drop_duplicates("_v")["ITEM"].tolist()
        rest = sorted(set(t["ITEM"]) - set(firsts))
        if len(t):
            out[route] = (firsts + rest)[:EXAMPLES_PER_ROUTE]
    return out


HOW_TO_READ = ("막대 하나가 그 분류 값의 ITEM 수다. 분류는 POR 값만 보고 정했고 판정은 바꾸지 않았다. 분포 모양과 판정할 수 "
               "있나는 한 ITEM 이 값 여러 개에 들 수 있다. 판정 길은 위에서부터 처음 맞는 것: 제외 → 한계 비교 → 절대 허용폭 "
               "→ LoQ 판정 → log TOST → 선형 TOST. 자세한 뜻은 열 사전(cls_*, route)에 있다.")


def takeaway(items: pd.DataFrame) -> str:
    return (f"ITEM {len(items):,}개의 판정 길: {route_counts(items['route'])}. "
            "최종 판정(verdict_final)은 이 분류와 무관하게 그대로다.")


def plot(items: pd.DataFrame, path: Path) -> None:
    from compare_metrics import set_font        # Agg 백엔드를 정한다 (pyplot 보다 먼저)
    import matplotlib.pyplot as plt

    from explain import add_figure_note

    set_font()
    n_cols = 3
    n_rows = math.ceil(len(AXIS_VIEW) / n_cols)
    views = [(col, title, value_counts(items[col], known)) for col, title, known in AXIS_VIEW]
    tallest = max(len(c) for _, _, c in views)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, n_rows * (0.32 * tallest + 1.2)), layout="constrained")
    top = max(1, max(n for _, _, c in views for _, n in c))
    for ax, (col, title, cnt) in zip(axes.flat, views):
        labels, values = [v for v, _ in cnt], [n for _, n in cnt]
        color = "#c8463d" if col == "route" else "#4a7fb5"
        ax.barh(range(len(cnt)), values, color=color, height=0.7)
        for i, n in enumerate(values):
            ax.text(n + top * 0.01, i, f"{n:,}", va="center", fontsize=8)
        ax.set_yticks(range(len(cnt)), labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, top * 1.15)
        ax.set_title(f"{title} ({col})", fontsize=10, loc="left")
        ax.tick_params(axis="x", labelsize=8)
    for ax in list(axes.flat)[len(views):]:
        ax.set_axis_off()
    fig.suptitle(f"ITEM 분류 (참고, ITEM {len(items):,}개)", fontsize=12)
    add_figure_note(fig, HOW_TO_READ, takeaway(items))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _plot_example(rows: pd.DataFrame, row: dict, path: Path) -> None:
    from item_view import plot_item_view
    plot_item_view(rows, row, path)


def remove_examples(folder: Path) -> None:
    """지난 실행의 examples/<판정 길>/*.png 와 빈 폴더를 지운다 (다른 파일은 그대로)."""
    if not folder.is_dir():
        return
    for png in folder.glob("*/*.png"):
        png.unlink()
    for sub in [*folder.iterdir(), folder]:
        if sub.is_dir() and not any(sub.iterdir()):
            sub.rmdir()


def write_examples(items: pd.DataFrame, a: argparse.Namespace, folder: Path) -> list[Path]:
    from fail_evidence import load_raw

    chosen = pick_examples(items)
    names = [i for v in chosen.values() for i in v]
    if not names:
        return []
    raw = load_raw(a, names, only=True)
    by_item = dict(list(raw.groupby(raw["ITEM"].astype(str), sort=False)))
    first = items.drop_duplicates("ITEM").set_index("ITEM")
    jobs = []
    for route, its in chosen.items():
        sub = folder / safe_group_name(route)
        sub.mkdir(parents=True, exist_ok=True)
        for it in its:
            if it in by_item:
                jobs.append((by_item[it], {"ITEM": it, **first.loc[it].to_dict()}, sub / f"{safe_group_name(it)}.png"))
    pool_map(_plot_example, jobs)
    return [p for _, _, p in jobs]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    from fail_evidence import add_raw_args

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, help="por_doe_compare.py 결과 items.csv")
    p.add_argument("--out", required=True, help="출력 폴더")
    p.add_argument("--groups", help="ITEM,group 파일. 주면 counts.csv 를 그룹마다도 센다")
    add_raw_args(p.add_argument_group("원데이터 (주면 판정 길마다 예시 ITEM 그림)"))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    if bool(a.por) != bool(a.doe):
        print("오류: 원데이터는 --por 와 --doe 를 같이 주어야 합니다.", file=sys.stderr)
        return 2
    items = read_items(Path(a.input))
    groups = None
    if a.groups:
        g = read_groups(a.groups)
        groups = items["ITEM"].str.strip().map(dict(zip(g["ITEM"], g["group"]))).fillna(UNGROUPED)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    counts(items, groups).to_csv(out / "counts.csv", index=False, encoding="utf-8-sig")
    by_route(items, groups).to_csv(out / "items_by_route.csv", index=False, encoding="utf-8-sig")
    plot(items, out / "classes.png")
    remove_examples(out / EXAMPLES_DIR)
    examples = write_examples(items, a, out / EXAMPLES_DIR) if a.por else []
    print(takeaway(items))
    print(f"결과: {out / 'counts.csv'}, {out / 'items_by_route.csv'}, {out / 'classes.png'}"
          + (f", 예시 그림 {len(examples)}장 ({out / EXAMPLES_DIR})" if a.por else " (원데이터가 없어 예시 그림 없음)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
