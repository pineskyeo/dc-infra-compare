"""측정 안정도: 같은 die를 POR로 다시 쟀을 때 얼마나 같게 나오나 (참고, 판정에 안 씀).

DOE는 한 번만 재므로 반복 안정도는 POR 회차로만 본다. por_doe_compare 가 items.csv 를 쓴 뒤 이미 읽은 wide 표로
부른다 (원데이터를 다시 읽지 않음). 결과는 <out>/stability/:

  overall.csv     한 행: ITEM 수, 판정력 구간별 비율, rsd_pct·ci_half_over_delta 중앙값과 P90, 상태별·잡음 모양별 ITEM 수
  groups.csv      같은 것을 그룹마다 (--groups 를 줄 때만, 아니면 지난 실행 것을 지운다)
  dies.csv        die 위치마다: 점수 = ITEM 마다 (그 die 의 POR 회차 범위 ÷ 그 ITEM 의 중앙 범위) 의 ITEM 중앙값,
                  그 비가 3을 넘는 ITEM 비율, 흔들리는 die 표시, outlier_dies.csv 에 나온 횟수 (DOE 쪽 튐)
  group_levels.csv  그룹 × LEVEL 마다 (--level 을 줄 때만, 아니면 지난 실행 것을 지운다): 판정력 구간 비율,
                  측정 정밀도 % 중앙값·P90. group_levels.png 는 같은 줄로 판정력 막대와 ITEM 별 측정 정밀도 점
  runs.csv        POR 회차마다: 점수 = ITEM 마다 median_die(회차 − 다른 회차 평균) ÷ sigma_die 의 ITEM 중앙값.
                  가장 큰 |점수| 회차 하나만, 0.25 이상이고 POR 3회 이상, ITEM 100개 이상일 때 밀린 회차로 본다
  stability.png   판정력 막대, 그룹 막대, 웨이퍼별 die 점수 지도, 회차 점수 막대

문턱값은 시뮬레이션으로 정했다 (설계 lab/results.md Q3).
"""
from __future__ import annotations

import math
import multiprocessing
from pathlib import Path

import numpy as np
import pandas as pd

from por_doe_compare import (JUDGEABILITY_BANDS, NOISE_BEND, NOISE_PATTERNS, ST_FLAT, ST_NEAR_LOQ, ST_RESOLUTION,
                             ST_RUN_JITTER, ST_UNSTABLE, parse_level)

DIR = "stability"
DPI = 150
UNGROUPED = "미지정"                 # group_summary 와 같은 이름
DIE_FRAC_RATIO = 3.0                 # die 회차 범위가 ITEM 중앙 범위의 이 배수를 넘으면 그 ITEM 에서 튐
DIE_SCORE_MIN = 1.5                  # 흔들리는 die: 점수 ≥ 이 값
DIE_FRAC_MIN = 0.2                   #   또는 튀는 ITEM 비율 ≥ 이 값
RUN_SCORE_MIN = 0.25                 # 밀린 회차: 가장 큰 |점수| ≥ 이 값
RUN_MIN_RUNS = 3                     # POR 2회면 두 점수가 거울상이라 어느 회차인지 못 정함
RUN_MIN_ITEMS = 100                  # ITEM 30개 정도면 회차 이동과 ITEM별 회차 잡음을 못 가름
NO_BAND = "판정력 없음"
BAND_COLS = {name: col for (_, name), col in
             zip(JUDGEABILITY_BANDS, ("share_stable", "share_caution", "share_unstable"))} | {"": "share_no_band"}
FLAG_COLS = {ST_RUN_JITTER: "n_run_jitter", ST_UNSTABLE: "n_condition_unstable", ST_RESOLUTION: "n_low_resolution",
             ST_FLAT: "n_flat", ST_NEAR_LOQ: "n_near_loq"}
NOISE_COUNT_COLS = dict(zip(NOISE_PATTERNS, ("n_noise_unknown", "n_noise_constant", "n_noise_proportional",
                                            "n_noise_widening_up", "n_noise_widening_down", "n_noise_between")))
LEVEL_NONE = "LEVEL 없음"
GROUP_LEVELS_PNG = "group_levels.png"
PRECISION = "meas_precision_pct"
GROUP_LEVEL_COLS = ["group", "level", "n_items", *BAND_COLS.values(), f"{PRECISION}_median", f"{PRECISION}_p90"]
COORD_RE = r"^\s*(-?\d+)\s*[_,]\s*(-?\d+)\s*$"
MAX_MAPS = 12
MAP_COLS = 3


def summary_row(items: pd.DataFrame) -> dict:
    """items (items.csv 행들) 의 판정력 구간 비율, 정밀도·판정력 분포, 상태별 ITEM 수, 잡음 모양별 ITEM 수
    (꺾임은 이름과 따로 n_noise_bend 에 센다)."""
    band = items["judgeability"].fillna("")
    pattern = items["noise_pattern"].fillna("")
    kinds = pattern.str.removesuffix(NOISE_BEND).value_counts()
    flags = items["status"].fillna("").str.split(";").explode().value_counts()
    rsd, ratio = (pd.to_numeric(items[c], errors="coerce") for c in ("rsd_pct", "ci_half_over_delta"))
    return {"n_items": len(items), **{col: float((band == name).mean()) for name, col in BAND_COLS.items()},
            "rsd_pct_median": rsd.median(), "rsd_pct_p90": rsd.quantile(0.9),
            "ci_half_over_delta_median": ratio.median(), "ci_half_over_delta_p90": ratio.quantile(0.9),
            **{col: int(flags.get(name, 0)) for name, col in FLAG_COLS.items()},
            **{col: int(kinds.get(name, 0)) for name, col in NOISE_COUNT_COLS.items()},
            "n_noise_bend": int(pattern.str.endswith(NOISE_BEND).sum())}


def overall(items: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([summary_row(items)])


def by_group(items: pd.DataFrame, group_of: dict[str, str]) -> pd.DataFrame:
    """그룹마다 summary_row. 그룹 파일에 없는 ITEM 은 UNGROUPED, 그 행은 맨 끝."""
    group = items["ITEM"].astype(str).str.strip().map(group_of).fillna(UNGROUPED)
    names = sorted(group.unique(), key=lambda g: (g == UNGROUPED, g))
    return pd.DataFrame([{"group": g, **summary_row(items[group == g])} for g in names])


def die_scores(wide: pd.DataFrame, por_cols: list[str], die_cols: list[str], outliers: pd.DataFrame) -> pd.DataFrame:
    """die 위치마다 score, share_over_3x, n_items, flagged, n_doe_outlier. 회차 범위 중앙값이 0인 ITEM 은 안 센다."""
    rng = wide[por_cols].max(axis=1) - wide[por_cols].min(axis=1)
    med = rng.groupby(wide["ITEM"]).transform("median")
    ratio = (rng / med).where(med > 0)
    g = wide[die_cols].assign(ratio=ratio, over=(ratio > DIE_FRAC_RATIO).where(ratio.notna())).groupby(die_cols)
    out = pd.DataFrame({"score": g["ratio"].median(), "share_over_3x": g["over"].mean(), "n_items": g["ratio"].count()})
    out["flagged"] = (out["score"] >= DIE_SCORE_MIN) | (out["share_over_3x"] >= DIE_FRAC_MIN)
    out["n_doe_outlier"] = outliers.groupby(die_cols).size().reindex(out.index, fill_value=0).astype(int)
    return out.reset_index().sort_values(["flagged", "score"], ascending=False, ignore_index=True)


def run_scores(wide: pd.DataFrame, por_cols: list[str], sigma_die: pd.Series) -> pd.DataFrame:
    """POR 회차마다 score, n_items, flagged, note. sigma_die 는 ITEM → items.csv sigma_die (0 이하·NaN ITEM 은 뺀다).
    회차 하나를 s 만큼 밀면 다른 회차 점수도 −s/(J−1) 움직이므로 가장 큰 |점수| 회차 하나만 볼 수 있다.
    note 는 밀린 회차로 보지 않은 첫 사유, 밀린 회차면 빈 칸."""
    J = len(por_cols)
    Y = wide[por_cols].to_numpy(float)
    dev = Y - (Y.sum(axis=1, keepdims=True) - Y) / (J - 1)
    per_item = pd.DataFrame(dev, columns=por_cols).groupby(wide["ITEM"].to_numpy()).median()
    s = sigma_die.reindex(per_item.index)
    per_item = per_item[s > 0].div(s[s > 0], axis=0)
    n = len(per_item)
    score = per_item.median() if n else pd.Series(np.nan, index=por_cols)
    top = score.abs().idxmax() if score.notna().any() else None

    def note(run: str) -> str:
        reasons = ((J < RUN_MIN_RUNS, f"POR {J}회는 두 회차 점수가 서로 거울상이라 밀린 회차를 정할 수 없음"),
                   (n < RUN_MIN_ITEMS, f"ITEM {n}개 (< {RUN_MIN_ITEMS})라 회차 이동과 잡음을 가를 수 없음"),
                   (run != top, f"가장 크게 벗어난 회차가 아님 ({top})"),
                   (not abs(score[run]) >= RUN_SCORE_MIN, f"|점수| {abs(score[run]):.2f} < {RUN_SCORE_MIN}"))
        return next((text for hit, text in reasons if hit), "")

    notes = [note(r) for r in por_cols]
    return pd.DataFrame({"run": por_cols, "score": score.to_numpy(), "n_items": n,
                         "flagged": [not t for t in notes], "note": notes})


def die_xy(dies: pd.DataFrame, die_cols: list[str]) -> pd.DataFrame:
    """wafer, x, y. WAFERID 가 없으면 한 장. 좌표 열 하나가 'x_y' 꼴이 아니면 웨이퍼마다 나온 순서로 격자에 놓는다."""
    wafer = dies["WAFERID"].astype(str) if "WAFERID" in die_cols else pd.Series("", index=dies.index)
    coord = [c for c in die_cols if c != "WAFERID"]
    xy = dies[coord[0]].astype(str).str.extract(COORD_RE).astype(float) if len(coord) == 1 else None
    if xy is None or xy.isna().any().any():
        i = wafer.groupby(wafer).cumcount()
        w = math.ceil(math.sqrt(wafer.value_counts().max()))
        xy = pd.DataFrame({0: i % w, 1: -(i // w)}, index=dies.index).astype(float)
    return pd.DataFrame({"wafer": wafer, "x": xy[0], "y": xy[1]})


def level_order(level: str) -> tuple:
    """LEVEL 이름 정렬 열쇠: 측정 종류(A, F, Hz, V) 다음 자릿수 오름차순, 읽지 못한 이름과 LEVEL 없음은 맨 끝."""
    parsed = parse_level(level)
    return (0, parsed[1], parsed[0], level) if parsed else (1, "", math.inf, level)


def group_level_points(items: pd.DataFrame, group_of: dict[str, str] | None, level_of: dict[str, str]) -> pd.DataFrame:
    """ITEM 마다 group, level, judgeability, meas_precision_pct. 그룹 파일에 없으면 UNGROUPED, LEVEL 이 없으면 LEVEL_NONE."""
    names = items["ITEM"].astype(str).str.strip()
    level = names.map(level_of).fillna("").astype(str)
    return pd.DataFrame({"group": names.map(group_of or {}).fillna(UNGROUPED).to_numpy(),
                         "level": level.where(level != "", LEVEL_NONE).to_numpy(),
                         "judgeability": items["judgeability"].fillna("").to_numpy(),
                         PRECISION: pd.to_numeric(items[PRECISION], errors="coerce").to_numpy()})


def by_group_level(points: pd.DataFrame) -> pd.DataFrame:
    """(그룹, LEVEL) 마다 ITEM 수, 판정력 구간 비율, 측정 정밀도 % 중앙값·P90. 그룹 이름순 (미지정 맨 끝), 그 안은 level_order."""
    keys = sorted(set(zip(points["group"], points["level"])), key=lambda k: (k[0] == UNGROUPED, k[0], level_order(k[1])))
    rows = []
    for g, lv in keys:
        sub = points[(points["group"] == g) & (points["level"] == lv)]
        prec = sub[PRECISION]
        rows.append({"group": g, "level": lv, "n_items": len(sub),
                     **{col: float((sub["judgeability"] == name).mean()) for name, col in BAND_COLS.items()},
                     f"{PRECISION}_median": prec.median(), f"{PRECISION}_p90": prec.quantile(0.9)})
    return pd.DataFrame(rows, columns=GROUP_LEVEL_COLS)


def write(out: Path, items: pd.DataFrame, wide: pd.DataFrame, por_cols: list[str], die_cols: list[str],
          outliers: pd.DataFrame, group_of: dict[str, str] | None, plotter: Plotter | None = None,
          level_of: dict[str, str] | None = None, r: float | None = None) -> dict[str, pd.DataFrame]:
    """out 폴더에 CSV 와 stability.png 를 쓰고 표들을 돌려준다. plotter 를 주면 그림은 그 프로세스가 그린다.
    level_of (ITEM → LEVEL 이름) 를 주면 group_levels.csv 와 group_levels.png 도 쓴다 (r = 허용폭, 정밀도 그림의 기준선)."""
    out.mkdir(parents=True, exist_ok=True)
    tables = {"overall": overall(items),
              "dies": die_scores(wide, por_cols, die_cols, outliers),
              "runs": run_scores(wide, por_cols, items.set_index("ITEM")["sigma_die"].astype(float))}
    if group_of is None:
        (out / "groups.csv").unlink(missing_ok=True)       # 지난 --groups 실행의 표가 이번 결과처럼 보이지 않게
    else:
        tables["groups"] = by_group(items, group_of)
    points = None
    if level_of:
        points = group_level_points(items, group_of, level_of)
        tables["group_levels"] = by_group_level(points)
    else:
        for stale in ("group_levels.csv", GROUP_LEVELS_PNG):      # 지난 --level 실행의 결과가 이번 것처럼 보이지 않게
            (out / stale).unlink(missing_ok=True)
    for name, t in tables.items():
        t.to_csv(out / f"{name}.csv", index=False, encoding="utf-8-sig")
    job = (out / "stability.png", tables, die_cols, points, r)
    if plotter is None:
        plot(*job)
    else:
        plotter.plot(job)
    return tables


def _warm_and_plot(conn) -> None:
    from compare_metrics import set_font        # Agg 백엔드를 정한다 (pyplot 보다 먼저)
    import matplotlib.pyplot as plt

    set_font()
    fig = plt.figure()
    fig.text(0, 0, "가")
    fig.canvas.draw()
    plt.close(fig)
    try:
        job = conn.recv()
    except EOFError:
        return
    plot(*job)


class Plotter:
    """그림 그리는 프로세스 하나. matplotlib 읽기와 한글 글꼴 읽기(약 0.3초)를 판정하는 동안 미리 해 둔다.
    판정 작업자를 fork 하기 전에 만든다 (스레드 없이). fork 를 못 쓰는 플랫폼이면 start() 가 None.
    plot 전에 예외로 끝나면 daemon 이라 인터프리터가 끝낼 때 같이 끝난다."""

    def __init__(self, proc, conn):
        self.proc, self.conn = proc, conn

    @classmethod
    def start(cls) -> Plotter | None:
        try:
            ctx = multiprocessing.get_context("fork")
        except ValueError:
            return None
        recv, send = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=_warm_and_plot, args=(recv,), daemon=True)
        proc.start()
        recv.close()
        return cls(proc, send)

    def plot(self, job) -> None:
        self.conn.send(job)
        self.conn.close()
        self.proc.join()
        if self.proc.exitcode:
            raise RuntimeError(f"stability.png 그리기 실패 (exit {self.proc.exitcode})")


def _die_name(row: pd.Series, die_cols: list[str]) -> str:
    return " ".join(str(row[c]) for c in die_cols)


def takeaway(tables: dict[str, pd.DataFrame], die_cols: list[str]) -> str:
    o = tables["overall"].iloc[0]
    bands = ", ".join(f"{name} {o[col]:.0%}" for (_, name), col in zip(JUDGEABILITY_BANDS, BAND_COLS.values()))
    text = f"ITEM {int(o['n_items']):,}개 중 {bands}. 정밀도(rsd_pct) 중앙값 {o['rsd_pct_median']:.3g}%."
    dies = tables["dies"]
    bad = dies[dies["flagged"]]
    if len(bad):
        names = ", ".join(_die_name(r, die_cols) for _, r in bad.head(5).iterrows())
        text += f" 흔들리는 die {len(bad)}개 ({names}{' 등' if len(bad) > 5 else ''})."
    else:
        text += f" 흔들리는 die 없음 (die {len(dies)}개)."
    runs = tables["runs"]
    hit = runs[runs["flagged"]]
    if len(hit):
        r = hit.iloc[0]
        text += f" {r['run']} 회차가 통째로 밀림 (점수 {r['score']:+.2f})."
    else:
        why = runs.loc[runs["note"].str.startswith("|점수|"), "note"]
        text += f" 밀린 POR 회차 없음 ({why.iloc[0] if len(why) else runs['note'].iloc[0]})."
    return text


HOW_TO_READ = ("막대는 ITEM 판정력 (신뢰구간 반폭 ÷ 허용폭: 0.5 이하 안정, 0.8 이하 주의, 그 위 불안정). 지도 색은 die 점수 "
               "(POR 회차 범위가 보통의 몇 배, 1이 보통), 빨간 테두리는 흔들리는 die (프로빙 의심), 숫자는 DOE에서 튄 "
               "ITEM 수. 회차 막대는 다른 회차 평균과의 차이 (σ_die), ±0.25 밖의 가장 큰 회차 하나만 밀린 회차로 본다.")
BAND_COLORS = ("#4c9a5f", "#e0a33a", "#c8463d", "#b8b8b8")


def _band_bars(ax, rows: pd.DataFrame, labels: list[str]) -> None:
    left = np.zeros(len(rows))
    names = [name for _, name in JUDGEABILITY_BANDS] + [NO_BAND]
    for name, col, color in zip(names, BAND_COLS.values(), BAND_COLORS):
        share = rows[col].to_numpy(float)
        ax.barh(range(len(rows)), share, left=left, color=color, label=name, height=0.7)
        for i, (x0, w) in enumerate(zip(left, share)):
            if w >= 0.06:
                ax.text(x0 + w / 2, i, f"{w:.0%}", ha="center", va="center", fontsize=8, color="white")
        left += share
    ax.set_yticks(range(len(rows)), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")


def _die_map(ax, dies: pd.DataFrame, norm, cmap, title: str) -> None:
    from matplotlib.collections import PatchCollection
    from matplotlib.patches import Rectangle

    cells = [Rectangle((x - 0.45, y - 0.45), 0.9, 0.9) for x, y in zip(dies["x"], dies["y"])]
    flagged = dies["flagged"].to_numpy(bool)
    colors = [cmap(norm(s)) if np.isfinite(s) else (0.9, 0.9, 0.9, 1) for s in dies["score"]]
    ax.add_collection(PatchCollection(cells, facecolors=colors, edgecolors=np.where(flagged, "#d62020", "#999999"),
                                      linewidths=np.where(flagged, 2.4, 0.4)))
    for x, y, k in zip(dies["x"], dies["y"], dies["n_doe_outlier"]):
        if k:
            ax.text(x, y, str(k), ha="center", va="center", fontsize=7)
    ax.set_xlim(dies["x"].min() - 1, dies["x"].max() + 1)
    ax.set_ylim(dies["y"].min() - 1, dies["y"].max() + 1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{title} · 흔들리는 die {int(flagged.sum())}개", fontsize=9)


def plot(path: Path, tables: dict[str, pd.DataFrame], die_cols: list[str], points: pd.DataFrame | None = None,
         r: float | None = None) -> None:
    from compare_metrics import set_font        # Agg 백엔드를 정한다 (pyplot 보다 먼저)
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    from explain import add_figure_note

    set_font()
    groups = tables.get("groups")
    dies = pd.concat([tables["dies"], die_xy(tables["dies"], die_cols)], axis=1)
    order = dies.groupby("wafer")["flagged"].sum().sort_values(ascending=False, kind="stable")
    wafers = order.index[:MAX_MAPS].tolist()
    map_rows = math.ceil(len(wafers) / MAP_COLS)
    n_groups = 0 if groups is None else len(groups)
    heights = [1.3] + ([0.35 * n_groups + 0.6] if n_groups else []) + [3.2] * map_rows
    fig = plt.figure(figsize=(12, sum(heights) + 0.9), layout="constrained")
    grid = fig.add_gridspec(len(heights), 6, height_ratios=heights)

    ax = fig.add_subplot(grid[0, :4])
    o = tables["overall"]
    _band_bars(ax, o, [f"전체 ({int(o['n_items'].iloc[0]):,})"])
    ax.legend(ncols=4, loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=8, frameon=False)
    ax.set_title("ITEM 판정력 (측정이 같다/다르다를 가를 만큼 안정한가)", fontsize=10, pad=22)

    ax = fig.add_subplot(grid[0, 4:])
    runs = tables["runs"]
    ax.bar(runs["run"], runs["score"], color=np.where(runs["flagged"], "#c8463d", "#7a8fa6"))
    lim = max(0.5, float(np.nanmax(np.abs(runs["score"]))) * 1.3) if runs["score"].notna().any() else 0.5
    for s in (-RUN_SCORE_MIN, RUN_SCORE_MIN):
        ax.axhline(s, color="#888888", lw=0.8, ls="--")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylim(-lim, lim)
    ax.set_ylabel("다른 회차 대비 (σ_die)", fontsize=8)
    ax.set_title(f"POR 회차 점수 (ITEM {int(runs['n_items'].iloc[0]):,}개)", fontsize=10)

    row = 1
    if n_groups:
        ax = fig.add_subplot(grid[row, :])
        _band_bars(ax, groups, [f"{g} ({n:,})" for g, n in zip(groups["group"], groups["n_items"])])
        ax.set_title("그룹별 판정력", fontsize=10)
        row += 1

    finite = dies["score"].dropna()
    norm = Normalize(0, max(3.0, float(finite.max())) if len(finite) else 3.0)
    cmap = plt.get_cmap("YlOrRd")
    span = 6 // MAP_COLS
    for i, w in enumerate(wafers):
        ax = fig.add_subplot(grid[row + i // MAP_COLS, (i % MAP_COLS) * span:(i % MAP_COLS + 1) * span])
        _die_map(ax, dies[dies["wafer"] == w], norm, cmap, f"웨이퍼 {w}" if w else "die 위치")
    more = f" (웨이퍼 {len(order)}장 중 흔들리는 die가 많은 {len(wafers)}장)" if len(order) > len(wafers) else ""
    if wafers:
        fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=fig.axes[-len(wafers):], shrink=0.6,
                     label=f"die 점수 (1 = 보통){more}")
    add_figure_note(fig, HOW_TO_READ, takeaway(tables, die_cols), dpi=DPI)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    if points is not None:
        plot_group_levels(path.with_name(GROUP_LEVELS_PNG), tables["group_levels"], points, r)


LEVEL_HOW_TO_READ = (
    "한 줄이 그룹 하나의 LEVEL(level.csv 의 측정 자릿수) 하나이고 괄호는 ITEM 수다. 왼쪽 막대는 판정력 비율(신뢰구간 반폭 ÷ "
    "허용폭: 0.5 이하 안정, 0.8 이하 주의, 그 위 불안정)이다. 오른쪽 점은 ITEM 하나의 측정 정밀도 %(log 축)이고 점 색은 "
    "그 ITEM 의 판정력, 검은 세로 막대는 그 줄의 중앙값이다. 같은 그룹 안에서 LEVEL 이 낮을수록 정밀도 % 가 커지고 "
    "불안정이 늘면 측정 스케일(분해능·range)이 판정력을 깎는 것이다.")


def _level_names(table: pd.DataFrame) -> list[str]:
    one = table["group"].nunique() == 1
    return [lv if one else f"{g} · {lv}" for g, lv in zip(table["group"], table["level"])]


def _pct(v: float) -> str:
    return f"{v:,.0f}%" if v >= 100 else f"{v:.3g}%"


def group_level_takeaway(table: pd.DataFrame, points: pd.DataFrame) -> str:
    names, n = _level_names(table), table["n_items"].to_numpy(int)
    worst = int(np.argmax(table["share_unstable"].to_numpy(float)))
    text = (f"그룹 × LEVEL {len(table):,}줄. 불안정 비율이 가장 큰 줄은 {names[worst]} "
            f"(ITEM {n[worst]:,}개 중 {table['share_unstable'].iloc[worst]:.0%}).")
    med = table[f"{PRECISION}_median"].to_numpy(float)
    if np.isfinite(med).any():
        i = int(np.nanargmax(med))
        text += f" 측정 정밀도 중앙값이 가장 큰 줄은 {names[i]} ({_pct(med[i])})."
    x = points[PRECISION].to_numpy(float)
    skipped = int((~(np.isfinite(x) & (x > 0))).sum())
    return text + (f" 측정 정밀도가 0·빈 칸이라 점을 못 찍은 ITEM {skipped:,}개." if skipped else "")


def plot_group_levels(path: Path, table: pd.DataFrame, points: pd.DataFrame, r: float | None) -> None:
    """왼쪽 = (그룹, LEVEL) 줄마다 판정력 구간 막대, 오른쪽 = 같은 줄에 ITEM 별 측정 정밀도 % 점 (log 축) 과 중앙값."""
    import matplotlib.pyplot as plt

    from explain import add_figure_note

    n = len(table)
    fig, (ax_b, ax_p) = plt.subplots(1, 2, figsize=(13, 1.8 + 0.34 * n), sharey=True, layout="constrained",
                                     gridspec_kw={"width_ratios": [1, 1.3]})
    _band_bars(ax_b, table, [f"{name} ({k:,})" for name, k in zip(_level_names(table), table["n_items"])])
    ax_b.legend(ncols=4, loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=8, frameon=False)
    ax_b.set_title("판정력", fontsize=10, pad=22)

    row = {k: i for i, k in enumerate(zip(table["group"], table["level"]))}
    y = np.array([row[k] for k in zip(points["group"], points["level"])], float)
    x = points[PRECISION].to_numpy(float)
    ok = np.isfinite(x) & (x > 0)
    names = [name for _, name in JUDGEABILITY_BANDS]
    color = points["judgeability"].map(dict(zip(names, BAND_COLORS))).fillna(BAND_COLORS[-1]).to_numpy()
    jitter = np.random.default_rng(0).uniform(-0.25, 0.25, len(y))
    if ok.any():
        med = table[f"{PRECISION}_median"].to_numpy(float)
        m = np.isfinite(med) & (med > 0)
        ax_p.scatter(med[m], np.arange(n)[m], marker="|", s=300, color="black", linewidths=2, zorder=2, label="중앙값")
        ax_p.scatter(x[ok], (y + jitter)[ok], s=18, c=color[ok], edgecolors="white", linewidths=0.4, zorder=3)
        if r:
            ax_p.axvline(100 * r, color="#555555", ls="--", lw=1, label=f"허용폭 r {r:.0%}")
        ax_p.set_xscale("log")
        ax_p.xaxis.set_major_formatter(lambda v, _: f"{v:g}%")
        ax_p.legend(ncols=2, loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=8, frameon=False)
        ax_p.grid(axis="x", alpha=0.3)
    else:
        ax_p.text(0.5, 0.5, "측정 정밀도 값 없음", transform=ax_p.transAxes, ha="center", va="center")
    ax_p.set_xlabel("측정 정밀도 % (σ_meas ÷ |POR 중앙값|, 작을수록 좋음)", fontsize=9)
    ax_p.set_title("측정 정밀도 % (점 = ITEM, 색 = 판정력)", fontsize=10, pad=22)
    for i in range(1, n):
        if table["group"].iloc[i] != table["group"].iloc[i - 1]:
            for ax in (ax_b, ax_p):
                ax.axhline(i - 0.5, color="#666666", lw=0.8)
    add_figure_note(fig, LEVEL_HOW_TO_READ, group_level_takeaway(table, points), dpi=DPI)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
