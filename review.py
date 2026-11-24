"""판정을 바꾸지 않는 참고용 재확인 두 가지. LoQ 아래·근처 ITEM 과 log 로 판정한 ITEM 을 원데이터로 다시 보고
"확인 필요" 를 표시한다. 기준값은 시뮬레이션으로 정했다 (설계 1-10, 1-11, lab results Q1·Q2).

  LoQ 재확인  대상 = zone 검출한계 이하·검출~정량, status LoQ 근처
              확인 필요 = R1 (die 방향 부호검정, 배수가 1/1.3~1.3 밖) 또는 R3 (꼬리 die 수, 5% 이상), 둘 다 BH q < 0.05
              검출률 변화 (R2) 는 열로만 보여 준다
  log 재확인  대상 = status log 후보, verdict_basis log·log_physics, scale log·auto→log
              확인 필요 = L1 (기본 판정 차이가 log 로 최종 동등) 또는 log10 값에서 같은 꼬리 검사

    python review.py --input <items.csv> --out <폴더> --por <회차1> --por <회차2> ... --doe <DOE> [--key ...]
출력은 <폴더>/review/: loq_review.csv, log_review.csv, loq_review.png, log_review.png, items/<ITEM>.png.
표는 확인 필요 행을 근거가 센 순서로 맨 앞에 둔다. ITEM 그림은 재확인마다 그 순서로 --max-figures 개 (기본 100, 0 = 전부)를
여러 프로세스로 그린다 (DC_JOBS, 기본 CPU 수).
"""
from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullFormatter, NullLocator  # noqa: E402
from scipy import stats  # noqa: E402

from compare_metrics import safe_group_name  # noqa: E402
from explain import LOQ_ZONES, add_figure_note, fmt, pct  # noqa: E402
from fail_evidence import add_raw_args, load_wide_items, read_plain  # noqa: E402
from plot_verdicts import configure_font  # noqa: E402
from por_doe_compare import (  # noqa: E402
    AUTO_SCALES, MIN_DIE, SCALE_LOG, ST_LOG_CANDIDATE, ST_NEAR_LOQ, V_EXCLUDED, _status_parts, ci_median, dc_jobs,
    pool_map, tost,
)

DPI = 110
FLAG_Q = 0.05
RATIO_MIN = 1.3
TAIL_FRAC_MIN = 0.05
OUTLIER_SIGMAS = 5.0
LOG_BASES = ("log", "log_physics")
LOG_SCALES = (SCALE_LOG, AUTO_SCALES[SCALE_LOG])
REVIEW_DIR = "review"
ITEMS_DIR = "items"
MAX_FIGURES = 100       # 재확인 하나에서 ITEM 그림을 그릴 확인 필요 ITEM 수 (근거가 센 순서). 0 이면 전부
NUMERIC_COLS = ("n_die", "center", "ci_low", "ci_high", "delta", "por_median", "LoQ", "LoD", "sigma_die",
                "center_log", "ci_low_log", "ci_high_log", "delta_log", "decades", "log_fit")


# ---------------------------------------------------------------- 지표 (lab/review_metrics.py 그대로)

def sign_test(d: np.ndarray) -> dict:
    d = np.asarray(d, float)
    up, down = int((d > 0).sum()), int((d < 0).sum())
    p = float(stats.binomtest(up, up + down, 0.5).pvalue) if up + down else 1.0
    return {"n_up": up, "n_down": down, "dir_p": p}


def ratio_ci(Y: np.ndarray, z: np.ndarray) -> dict:
    ok = (Y > 0).all(axis=1) & (z > 0)
    n = int(ok.sum())
    out = {"ratio": np.nan, "ratio_lo": np.nan, "ratio_hi": np.nan, "n_ratio_die": n}
    if n < MIN_DIE:
        return out
    c, lo, hi = (10 ** v for v in ci_median(np.log10(z[ok] / Y[ok].mean(axis=1))))
    return {**out, "ratio": c, "ratio_lo": lo, "ratio_hi": hi}


def mcnemar_p(a: np.ndarray, b: np.ndarray) -> float:
    only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
    return float(stats.binomtest(only_b, only_a + only_b, 0.5).pvalue) if only_a + only_b else 1.0


def detection(Y: np.ndarray, z: np.ndarray, loq: float) -> dict:
    """DOE (one measurement) against each single POR run; p is the largest of the per-run McNemar p values."""
    doe = np.abs(z) >= loq
    runs = np.abs(Y) >= loq
    return {"det_rate_por": float(runs.mean()), "det_rate_doe": float(doe.mean()),
            "det_change": float(doe.mean() - runs.mean()),
            "det_p": max(mcnemar_p(runs[:, j], doe) for j in range(Y.shape[1]))}


def loo_scale(J: int) -> float:
    """POR 회차 하나 − 나머지 J − 1 회차 평균의 차에 곱하면 DOE − J 회차 평균의 차와 분산이 같아지는 배수
    √((1 + 1/J) / (1 + 1/(J − 1)))."""
    return float(np.sqrt((1 + 1 / J) / (1 + 1 / (J - 1))))


def _tail_parts(Y: np.ndarray, z: np.ndarray, k: float) -> tuple[np.ndarray, np.ndarray, float]:
    """(d = DOE - POR run mean, centred POR leave-one-run-out differences scaled to Var d, outlier limit)."""
    J = Y.shape[1]
    d = z - Y.mean(axis=1)
    loo = (Y - (Y.sum(axis=1, keepdims=True) - Y) / (J - 1)).ravel() * loo_scale(J)
    loo = loo - np.median(loo)
    return d, loo, k * 1.4826 * np.median(np.abs(loo))


def tail_dies(Y: np.ndarray, z: np.ndarray, k: float = OUTLIER_SIGMAS) -> np.ndarray:
    d, _, limit = _tail_parts(Y, z, k)
    return np.abs(d - np.median(d)) > limit


def tail_test(Y: np.ndarray, z: np.ndarray, k: float = OUTLIER_SIGMAS) -> dict:
    """Dies with |d - median d| beyond k robust sigma of the POR leave-one-run-out differences. The DOE count is
    tested against the POR differences' own count: exact conditional binomial, one-sided."""
    if Y.shape[1] < 2:
        return {"tail_p": np.nan, "tail_frac": np.nan, "tail_n_doe": np.nan, "tail_n_por": np.nan}
    n = len(z)
    d, loo, limit = _tail_parts(Y, z, k)
    k_doe, k_por = int((np.abs(d - np.median(d)) > limit).sum()), int((np.abs(loo) > limit).sum())
    p = float(stats.binomtest(k_doe, k_doe + k_por, n / (n + loo.size), "greater").pvalue) if k_doe + k_por else 1.0
    return {"tail_p": p, "tail_frac": k_doe / n, "tail_n_doe": k_doe, "tail_n_por": k_por}


def _log_ok(Y: np.ndarray, z: np.ndarray) -> bool:
    return bool(np.isfinite(np.log10(np.abs(np.concatenate([Y.ravel(), z])))).all())


def loq_review_item(Y: np.ndarray, z: np.ndarray, res: Mapping) -> dict:
    Y, z = np.asarray(Y, float), np.asarray(z, float)
    loq, s_die = float(res["LoQ"]), float(res["sigma_die"])
    return {**sign_test(z - Y.mean(axis=1)), **ratio_ci(Y, z), **detection(Y, z, loq), **tail_test(Y, z),
            "verdict_tost": tost(res["center"], res["ci_low"], res["ci_high"], res["delta"])[0],
            "loq_source_ratio": loq / (10 * s_die) if s_die > 0 else np.inf}


def log_row_terms(res: Mapping) -> dict:
    """log 재확인 중 원데이터 없이 items.csv 한 행에서 나오는 값 (L1 포함)."""
    med, c_log = float(res["por_median"]), float(res.get("center_log", np.nan))
    return {"shift_pct": 100 * float(res["center"]) / abs(med) if med else np.nan,
            "shift_log_pct": 100 * (10 ** c_log - 1),
            "log_overrode_diff": res.get("verdict") == "차이" and res.get("verdict_final") == "동등"
            and res.get("verdict_basis") in LOG_BASES}


def log_review_item(Y: np.ndarray, z: np.ndarray, res: Mapping) -> dict:
    """res is an items.csv row: judge + log_columns + verdict_final/verdict_basis."""
    Y, z = np.asarray(Y, float), np.asarray(z, float)
    tail = tail_test(np.log10(np.abs(Y)), np.log10(np.abs(z))) if _log_ok(Y, z) else {"tail_p": np.nan,
                                                                                    "tail_frac": np.nan}
    return {**log_row_terms(res), **tail}


def bh_adjust(p) -> np.ndarray:
    p = np.asarray(p, float)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m:
        order = np.argsort(p[ok])
        ranked = p[ok][order] * m / np.arange(1, m + 1)
        q_ok = np.empty(m)
        q_ok[order] = np.minimum(1.0, np.minimum.accumulate(ranked[::-1])[::-1])
        q[ok] = q_ok
    return q


def flag_loq(rows: pd.DataFrame, q: float = FLAG_Q, ratio_min: float = RATIO_MIN,
             tail_min: float = TAIL_FRAC_MIN) -> pd.DataFrame:
    out = rows.copy()
    out["dir_q"], out["tail_q"] = bh_adjust(out["dir_p"]), bh_adjust(out["tail_p"])
    r = out["ratio"]
    out["flag_direction"] = (out["dir_q"] < q) & ((r > ratio_min) | (r < 1 / ratio_min))
    out["flag_tail"] = (out["tail_q"] < q) & (out["tail_frac"] >= tail_min)
    out["flag"] = out["flag_direction"] | out["flag_tail"]
    return out


def flag_log(rows: pd.DataFrame, q: float = FLAG_Q, tail_min: float = TAIL_FRAC_MIN) -> pd.DataFrame:
    out = rows.copy()
    out["tail_q"] = bh_adjust(out["tail_p"])
    out["flag_tail"] = (out["tail_q"] < q) & (out["tail_frac"] >= tail_min)
    out["flag"] = out["log_overrode_diff"].astype(bool) | out["flag_tail"]
    return out


def strongest_first(table: pd.DataFrame) -> pd.DataFrame:
    """확인 필요 행을 근거가 센 순서로 맨 앞에 둔다: log 가 차이를 동등으로 바꾼 ITEM, 걸린 규칙의 q 가 작은 ITEM,
    꼬리 die 비율이 큰 ITEM 순. 확인 필요가 아닌 행은 그 뒤에 원래 순서로."""
    flag = table["flag"].astype(bool).to_numpy()
    q = np.ones(len(table))
    for rule, col in (("flag_direction", "dir_q"), ("flag_tail", "tail_q")):
        if rule in table:
            hit = table[rule].astype(bool).to_numpy()
            q = np.where(hit, np.fmin(q, table[col].to_numpy(float)), q)
    l1 = table["log_overrode_diff"].astype(bool).to_numpy() if "log_overrode_diff" in table else np.zeros(len(table), bool)
    tail = np.nan_to_num(table["tail_frac"].to_numpy(float)) if "tail_frac" in table else np.zeros(len(table))
    first = np.lexsort((-tail, np.nan_to_num(q, nan=1.0), ~l1))
    first = first[flag[first]]
    return table.iloc[np.r_[first, np.flatnonzero(~flag)]].reset_index(drop=True)


# ---------------------------------------------------------------- 쉬운 말

def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def times(v: float, digits: int = 2) -> str:
    """배수 유효숫자 digits 자리 ("2.0", "0.50", "12"). 100 이상은 정수."""
    return f"{v:,.0f}" if v >= 100 else f"{v:#.{digits}g}".rstrip(".")


def ratio_text(r: Mapping) -> str:
    """'약 2.0배 (1.7~2.4배)'. 구간 양 끝이 두 자리로 같아 보이면 세 자리."""
    digits = 3 if times(r["ratio_lo"]) == times(r["ratio_hi"]) else 2
    c, lo, hi = (times(r[k], digits) for k in ("ratio", "ratio_lo", "ratio_hi"))
    return f"약 {c}배 ({lo}~{hi}배)"


def _share(k, n) -> str:
    return f"{100 * k / n:.0f}%" if n else "-"


def _tail_sentence(r: Mapping, n: int, where: str = "") -> str:
    k, k_por = _f(r.get("tail_n_doe")), _f(r.get("tail_n_por"))
    if not np.isfinite(k):
        return ""
    return (f"{where}die {int(k)}개({_share(k, n)})가 POR 회차끼리의 차이로는 드물 만큼 크게 벗어났다 "
            f"(POR 쪽 같은 벗어남 {int(k_por)}개).")


def _place(r: Mapping) -> str:
    return {"검출한계 이하": "검출 한계(LoD) 아래", "검출~정량": "정량 한계(LoQ) 아래"}.get(r.get("zone"),
                                                                                "정량 한계(LoQ) 근처")


def why_loq(r: Mapping) -> str:
    if not np.isfinite(_f(r.get("dir_p"))):
        return "원데이터에서 이 ITEM 을 찾지 못해 계산하지 못했다."
    n = int(_f(r.get("n_die_raw")))
    up, down = int(r["n_up"]), int(r["n_down"])
    move = f"die {n}개 중 {up}개가 증가" if up >= down else f"die {n}개 중 {down}개가 감소"
    has_ratio = np.isfinite(_f(r.get("ratio")))
    if has_ratio:
        move += f", {ratio_text(r)}"
    if r.get("flag"):
        rules = [s for s, on in (("방향", r.get("flag_direction")), ("꼬리", r.get("flag_tail"))) if on]
        tail = _tail_sentence(r, n) if r.get("flag_tail") else ""
        return " ".join(s for s in (f"확인 필요({', '.join(rules)}). {_place(r)}지만 {move}.", tail) if s)
    if not _f(r.get("dir_q")) < FLAG_Q:
        return f"{_place(r)}. {move}. 방향과 꼬리 모두 뚜렷하지 않다."
    if has_ratio:
        return f"{_place(r)}. {move}. 방향은 한쪽으로 몰렸지만 배수가 {times(RATIO_MIN)}배 안이라 확인 필요는 아니다."
    return (f"{_place(r)}. {move}. 방향은 한쪽으로 몰렸지만 POR·DOE 가 모두 양수인 die 가 {int(r['n_ratio_die'])}개라 "
            "배수를 잴 수 없어 방향 기준에 넣지 않았다.")


def _shift_text(r: Mapping, what: str, suffix: str) -> str:
    """'값 대비 +6.6% (+5.5% ~ +12.5%), 허용폭 ±5.0%'. 열 값이 이미 % 라 pct(x, 100) 은 x 를 그대로 % 로 쓴다."""
    c, lo, hi, d = (r.get(f"{k}{suffix}_pct") for k in ("shift", "ci_low", "ci_high", "delta"))
    return f"{what} {pct(c, 100)} ({pct(lo, 100)} ~ {pct(hi, 100)}), 허용폭 ±{abs(_f(d)):.1f}%"


def why_log(r: Mapping) -> str:
    lin = _shift_text(r, "선형으로는 값 대비", "")
    log = (_shift_text(r, "log 로는 배율", "_log") if np.isfinite(_f(r.get("shift_log_pct")))
           else "log 판정은 없다 (값에 0 이 있거나 부호가 섞임)")
    n = int(_f(r.get("n_die_raw"))) if np.isfinite(_f(r.get("n_die_raw"))) else 0
    if not n:
        return f"원데이터에서 이 ITEM 을 찾지 못해 꼬리는 계산하지 못했다. {lin}. {log}."
    no_tail = "" if np.isfinite(_f(r.get("tail_p"))) else " log 꼬리 검사는 하지 못했다 (값에 0 이 있거나 POR 회차가 1개)."
    if not r.get("flag"):
        return f"{lin}. {log}. log 가 기본 판정을 바꾸지 않았고 꼬리도 뚜렷하지 않다.{no_tail}"
    parts = ["확인 필요."]
    if r.get("log_overrode_diff"):
        parts.append(f"기본 판정은 차이다. {lin}. {log}라서 최종 판정이 동등이 됐다.")
    else:
        parts.append(f"{lin}. {log}.")
    if r.get("flag_tail"):
        parts.append(_tail_sentence(r, n, "log 값에서 "))
    return " ".join(parts) + no_tail


# ---------------------------------------------------------------- 두 재확인

def _loq_target(row: Mapping) -> bool:
    return row.get("zone") in LOQ_ZONES or (ST_NEAR_LOQ in _status_parts(row.get("status"))
                                            and row.get("verdict") != V_EXCLUDED)


def _log_target(row: Mapping) -> bool:
    if row.get("verdict") == V_EXCLUDED:
        return False
    return (ST_LOG_CANDIDATE in _status_parts(row.get("status")) or row.get("verdict_basis") in LOG_BASES
            or row.get("scale") in LOG_SCALES)


def _loq_extra(row: Mapping) -> dict:
    por, loq = _f(row.get("por_median")), _f(row.get("LoQ"))
    return {"loq_ratio": abs(por) / loq if loq > 0 else np.nan}


def _pct_of(x, base) -> float:
    return 100 * _f(x) / abs(base) if base else np.nan


def _log_extra(row: Mapping) -> dict:
    med = _f(row.get("por_median"))
    out = {**log_row_terms(row), "ci_low_pct": _pct_of(row.get("ci_low"), med),
           "ci_high_pct": _pct_of(row.get("ci_high"), med), "delta_pct": _pct_of(row.get("delta"), med)}
    for k in ("ci_low", "ci_high", "delta"):
        out[f"{k}_log_pct"] = 100 * (10 ** _f(row.get(f"{k}_log")) - 1)
    return out


@dataclass(frozen=True)
class Review:
    name: str                                       # loq · log
    target: Callable[[Mapping], bool]               # items.csv 한 행 → 대상인지
    measure: Callable[[np.ndarray, np.ndarray, Mapping], dict]
    extra: Callable[[Mapping], dict]                # 원데이터 없이 items.csv 행에서 나오는 열
    flag: Callable[[pd.DataFrame], pd.DataFrame]
    why: Callable[[Mapping], str]
    space: Callable[[np.ndarray], np.ndarray]       # 꼬리 검사를 하는 값 (그림 d 칸)
    copy_cols: tuple[str, ...]                      # items.csv 에서 옮겨 적는 열
    cols: tuple[str, ...]                           # 결과 열 (copy_cols 뒤)


REVIEWS = {
    "loq": Review(
        "loq", _loq_target, loq_review_item, _loq_extra, flag_loq, why_loq, lambda v: v,
        ("ITEM", "UNIT", "zone", "verdict_final", "verdict", "n_die", "por_median", "LoQ", "LoD", "center", "delta"),
        ("loq_ratio", "n_die_raw", "n_up", "n_down", "dir_p", "dir_q", "ratio", "ratio_lo", "ratio_hi", "n_ratio_die",
         "det_rate_por", "det_rate_doe", "det_change", "det_p", "tail_n_doe", "tail_n_por", "tail_frac", "tail_p",
         "tail_q", "verdict_tost", "loq_source_ratio", "flag_direction", "flag_tail", "flag", "why")),
    "log": Review(
        "log", _log_target, log_review_item, _log_extra, flag_log, why_log, lambda v: np.log10(np.abs(v)),
        ("ITEM", "UNIT", "scale", "verdict_final", "verdict_basis", "verdict", "verdict_log", "status", "decades",
         "log_fit", "n_die", "por_median"),
        ("n_die_raw", "shift_pct", "ci_low_pct", "ci_high_pct", "delta_pct", "shift_log_pct", "ci_low_log_pct",
         "ci_high_log_pct", "delta_log_pct", "log_overrode_diff", "tail_n_doe", "tail_n_por", "tail_frac", "tail_p",
         "tail_q", "flag_tail", "flag", "why")),
}

Raw = dict[str, tuple[np.ndarray, np.ndarray]]      # ITEM → (Y: die × POR 회차, z: DOE)


def review_table(review: Review, items: pd.DataFrame, raw: Raw) -> pd.DataFrame:
    """대상 ITEM 한 행씩: items.csv 열 + 지표 + BH q + flag + why. BH 는 이 표 전체 (한 실행의 대상 ITEM) 안에서."""
    rows = []
    for row in items.to_dict("records"):
        if not review.target(row):
            continue
        Y, z = raw.get(str(row["ITEM"]), (None, None))
        metrics = {} if Y is None else {"n_die_raw": len(z), **review.measure(Y, z, row)}
        rows.append({**{c: row.get(c, "") for c in review.copy_cols}, **review.extra(row), **metrics})
    table = pd.DataFrame(rows, columns=[*review.copy_cols, *review.cols])
    # 행이 없거나 원데이터가 없는 ITEM 뿐이면 object 열이라 BH·비교 전에 float 로
    table = review.flag(table.astype({c: float for c in ("dir_p", "tail_p", "tail_frac", "ratio") if c in table}))
    table["why"] = [review.why(r) for r in table.to_dict("records")]
    return strongest_first(table[[*review.copy_cols, *review.cols]])


def read_items(path: str | Path) -> pd.DataFrame:
    items = read_plain(path)
    for c in NUMERIC_COLS:
        if c in items:
            items[c] = pd.to_numeric(items[c], errors="coerce")
    return items


def load_raw(raw_args: argparse.Namespace, wanted: list[str]) -> Raw:
    if not wanted:
        return {}
    wide, por_cols = load_wide_items(raw_args, wanted)
    return {str(item): (g[por_cols].to_numpy(float), g["DOE"].to_numpy(float))
            for item, g in wide.groupby("ITEM", sort=False)}


# ---------------------------------------------------------------- 그림

FLAG_COLOR, OK_COLOR, POR_GREY, POR1_COLOR = "#d62728", "#8c9db5", "#bbbbbb", "#1f77b4"
VERDICT_COLORS = {"동등": "#2ca02c", "미결": "#1f77b4", "차이": "#d62728"}
AX_MIN, AX_MAX = 1e-3, 1e3
QUADRANTS = (   # (x, y, 이름): x > 1 이면 DOE 가 LoQ 위, y > 1 이면 이동이 허용폭보다 큼
    (0.98, 0.98, "DOE가 LoQ 위로 올라가고\n크게 움직임"),
    (0.02, 0.98, "둘 다 LoQ 아래라 '같다'로 보고되지만\n크게 움직임 (가려질 수 있는 곳)"),
    (0.98, 0.02, "DOE가 LoQ 위지만\n움직임은 허용폭 안"),
    (0.02, 0.02, "둘 다 LoQ 아래,\n움직임도 허용폭 안"),
)
MAX_LABELS = 20
LOQ_MAP_HOW_TO_READ = (
    "점 하나가 ITEM 하나다. 오른쪽일수록 DOE 값이 정량 한계(LoQ) 위로 올라가고, 위쪽일수록 이동이 허용폭보다 크다. "
    "주황 칸(왼쪽 위)은 둘 다 '<LoQ'로 보고되어 판정은 동등이지만 실제로는 움직였을 수 있는 곳이다. "
    "빨간 마름모는 die 대부분이 같은 방향으로 움직였거나(방향) 일부 die만 크게 벗어난(꼬리) ITEM이다. "
    "축 밖 값은 축 끝에 붙였다.")
LOG_MAP_HOW_TO_READ = (
    "한 줄이 ITEM 하나다. 왼쪽은 선형 판정, 오른쪽은 log 판정이다. 점은 이동량, 검은 선은 90% 신뢰구간, 회색 띠는 "
    "같다고 보는 허용폭이고, 점 색은 각 판정이다. 검은 선이 회색 띠 안에 다 들어가면 동등이다. 빨간 ◆ 이름은 "
    "선형으로 차이인데 log 로 동등이 됐거나, log 값에서 일부 die만 크게 벗어난 '확인 필요' ITEM이다.")
ITEM_HOW_TO_READ = (
    "① 회차별 die 값 (파랑 POR1, 회색 POR2.., 검정 DOE, 주황 점선 LoD·파선 LoQ). "
    "② die별 변화량을 작은 순으로 늘어놓은 것, 회색 띠는 POR 회차끼리 다시 잴 때의 흔들림 5배다. "
    "③④ 가로는 같은 die 의 POR1, 세로는 DOE(검정)와 다른 POR 회차(회색)이고 선형 축과 log 축으로 그린다. "
    "회색이 대각선 y = x 에 붙어 있으면 다시 재도 같은 값이라 측정이 안정적이다. 검정이 회색보다 대각선에서 멀수록 DOE 가 "
    "변한 것이다. log 축에서 작은 값 쪽만 휘면 몇 배가 아니라 일정한 양이 더해진 변화다. 빨간 테두리는 크게 벗어난 같은 die 다.")
MAX_LOG_ROWS = 40
FOREST_SPAN = 4.0
FOREST_MIN_PCT = 20.0


def _plain_log_ticks(ax) -> None:
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        axis.set_minor_formatter(NullFormatter())


def plot_loq_map(table: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9.5, 7))
    x = (table["por_median"] + table["center"]).abs() / table["LoQ"]
    y = (table["center"].abs() / table["delta"]).where(table["center"] != 0, 0.0)
    pts = pd.DataFrame({"x": x, "y": y, "flag": table["flag"].astype(bool), "ITEM": table["ITEM"],
                        "q": table[["dir_q", "tail_q"]].min(axis=1)}).dropna(subset=["x", "y"])
    pts[["x", "y"]] = pts[["x", "y"]].clip(AX_MIN, AX_MAX)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(AX_MIN, AX_MAX)
    ax.set_ylim(AX_MIN, AX_MAX)
    _plain_log_ticks(ax)
    ax.add_patch(Rectangle((AX_MIN, 1), 1 - AX_MIN, AX_MAX - 1, facecolor="#ff7f0e", alpha=0.10, edgecolor="none"))
    ax.axvline(1, color="#888888", lw=0.8, ls="--")
    ax.axhline(1, color="#888888", lw=0.8, ls="--")
    for qx, qy, name in QUADRANTS:
        ax.text(qx, qy, name, transform=ax.transAxes, fontsize=8.5, color="#444444",
                ha="right" if qx > 0.5 else "left", va="top" if qy > 0.5 else "bottom")
    ok, hit = pts[~pts["flag"]], pts[pts["flag"]]
    ax.scatter(ok["x"], ok["y"], s=22, color=OK_COLOR, edgecolors="white", lw=0.5, zorder=3, clip_on=False)
    ax.scatter(hit["x"], hit["y"], s=70, marker="D", color=FLAG_COLOR, edgecolors="black", lw=0.6, zorder=4,
               clip_on=False)
    for _, r in hit.nsmallest(MAX_LABELS, "q").iterrows():
        ax.annotate(str(r["ITEM"]), (r["x"], r["y"]), xytext=(5, 4), textcoords="offset points", fontsize=7.5,
                    color=FLAG_COLOR, zorder=5)
    if pts.empty:
        ax.text(0.5, 0.5, "해당 ITEM 없음", transform=ax.transAxes, ha="center", va="center")
    ax.legend(handles=[
        Line2D([0], [0], marker="D", color=FLAG_COLOR, mec="black", ls="none", label=f"확인 필요 {len(hit):,}"),
        Line2D([0], [0], marker="o", color=OK_COLOR, ls="none", label=f"뚜렷한 변화 없음 {len(ok):,}")],
        loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9)
    ax.set_xlabel("DOE 수준\n(DOE 값 ÷ LoQ, 1 넘으면 숫자로 보고)")
    ax.set_ylabel("정규화 변화량 크기\n(|이동| ÷ 허용폭)")
    ax.set_title("LoQ 아래·근처 ITEM 재확인 (판정은 그대로)")
    ax.grid(which="major", color="#e2e2e2", lw=0.5)
    fig.tight_layout()
    n_dir, n_tail = int(table["flag_direction"].sum()), int(table["flag_tail"].sum())
    add_figure_note(
        fig, LOQ_MAP_HOW_TO_READ,
        f"대상 ITEM {len(table):,}개 중 확인 필요 {len(hit):,}개 (방향 {n_dir:,}, 꼬리 {n_tail:,}). 판정은 바꾸지 않았다.", dpi=DPI)
    return _save(fig, path)


def _forest(ax, rows: pd.DataFrame, center: str, lo: str, hi: str, d_lo: pd.Series, d_hi: pd.Series,
            verdict: str, title: str, xlabel: str) -> None:
    # 한 ITEM 의 큰 이동이 나머지를 눌러 버리지 않게 축은 허용폭의 FOREST_SPAN 배까지만, 밖의 점은 끝에 화살표로
    span = min(np.nanmax(np.abs(np.r_[rows[lo], rows[hi], d_lo, d_hi, 1.0])),
               max(FOREST_SPAN * np.nanmax(np.abs(np.r_[d_lo, d_hi, 1.0])), FOREST_MIN_PCT))
    edge = 1.04 * span
    ypos = np.arange(len(rows))[::-1]
    for yy, (_, r), a, b in zip(ypos, rows.iterrows(), d_lo, d_hi):
        ax.add_patch(Rectangle((a, yy - 0.32), b - a, 0.64, facecolor="#dddddd", edgecolor="none", zorder=1))
        ax.plot([r[lo], r[hi]], [yy, yy], color="#333333", lw=1.4, zorder=2)
        c = r[center]
        out = abs(c) > edge
        ax.scatter([np.clip(c, -edge, edge)], [yy], s=40 if out else 28, marker=(">" if c > 0 else "<") if out else "o",
                   color=VERDICT_COLORS.get(r[verdict], "#7f7f7f"), zorder=3, clip_on=False)
    ax.axvline(0, color="#888888", lw=0.8)
    ax.set_xlim(-1.08 * span, 1.08 * span)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", color="#e8e8e8", lw=0.5)


def plot_log_map(table: pd.DataFrame, path: Path) -> Path:
    rows = (table.assign(_f=~table["flag"].astype(bool), _s=-table["shift_log_pct"].abs())
            .sort_values(["_f", "_s"]).head(MAX_LOG_ROWS))
    fig, axes = plt.subplots(1, 2, figsize=(12, 1.6 + 0.3 * max(len(rows), 3)), sharey=True)
    if rows.empty:
        for ax in axes:
            ax.text(0.5, 0.5, "해당 ITEM 없음", transform=ax.transAxes, ha="center", va="center")
    else:
        dl = rows["delta_pct"].abs()
        _forest(axes[0], rows, "shift_pct", "ci_low_pct", "ci_high_pct", -dl, dl, "verdict",
                "선형 변화", "POR 대비 %\n(이동 ÷ |POR 중앙값|, 회색 = 허용폭)")
        dlog = np.log10(1 + rows["delta_log_pct"] / 100)
        _forest(axes[1], rows, "shift_log_pct", "ci_low_log_pct", "ci_high_log_pct", 100 * (10 ** -dlog - 1),
                rows["delta_log_pct"], "verdict_log", "log 변화", "배율 변화 %\n(DOE ÷ POR − 1, 회색 = 허용폭)")
        ypos = np.arange(len(rows))[::-1]
        axes[0].set_yticks(ypos)
        axes[0].set_yticklabels([("◆ " if f else "") + str(i) for i, f in zip(rows["ITEM"], rows["flag"])],
                                fontsize=8)
        for label, f in zip(axes[0].get_yticklabels(), rows["flag"]):
            label.set_color(FLAG_COLOR if f else "#222222")
        axes[0].set_ylim(-0.7, len(rows) - 0.3)
    axes[1].legend(handles=[Line2D([0], [0], marker="o", color=c, ls="none", label=v)
                            for v, c in VERDICT_COLORS.items()], title="판정", fontsize=8,
                   loc="upper left", bbox_to_anchor=(1.01, 1.0))
    fig.suptitle("log 판정 재확인: 선형과 log 를 나란히 (판정은 그대로)")
    fig.tight_layout()
    n_l1, n_tail, n = int(table["log_overrode_diff"].sum()), int(table["flag_tail"].sum()), len(table)
    more = f" 그림에는 확인 필요 먼저, 이동이 큰 순서로 {MAX_LOG_ROWS}개만 그렸다." if n > MAX_LOG_ROWS else ""
    add_figure_note(
        fig, LOG_MAP_HOW_TO_READ,
        f"대상 ITEM {n:,}개 중 확인 필요 {int(table['flag'].sum()):,}개 (log 가 차이를 동등으로 바꿈 {n_l1:,}, "
        f"꼬리 {n_tail:,}). 판정은 바꾸지 않았다.{more}", dpi=DPI)
    return _save(fig, path)


def _value_scale(ax, values: np.ndarray, lod: float, unit: str, axis: str = "y") -> None:
    """양수만이면 log 축, 0 이나 음수가 섞이면 symlog (선형 구간 = LoD, 없으면 가장 작은 |값|)."""
    setter = ax.set_yscale if axis == "y" else ax.set_xscale
    target = ax.yaxis if axis == "y" else ax.xaxis
    v = values[np.isfinite(values)]
    if v.size and (v > 0).all():
        setter("log")
    else:
        nz = np.abs(v[v != 0])
        lt = lod if lod > 0 else (nz.min() if nz.size else 1.0)
        setter("symlog", linthresh=lt)
        top = np.abs(v).max() if v.size else lt
        decades = 10.0 ** np.arange(np.floor(np.log10(lt)), np.ceil(np.log10(max(top, lt))) + 1)
        ticks = np.r_[-decades, 0.0, decades]
        if axis == "x":         # 좁은 칸의 가로축에서 ±LoD 눈금 글자가 0 과 겹치지 않게
            ticks = ticks[(ticks == 0) | (np.abs(ticks) > 1.5 * lt)]
        target.set_ticks(ticks[(ticks >= v.min() - lt) & (ticks <= v.max() + lt)] if v.size else ticks)
    target.set_major_formatter(FuncFormatter(lambda t, _: fmt(t, unit)))
    target.set_minor_locator(NullLocator())


def _limit_lines(ax, row: Mapping, axis: str = "y") -> None:
    for key, style in (("LoD", ":"), ("LoQ", "--")):
        v = _f(row.get(key))
        if np.isfinite(v) and v > 0:
            (ax.axhline if axis == "y" else ax.axvline)(v, color="#ff7f0e", lw=1, ls=style, label=key)


def _por_vs_doe(ax, Y: np.ndarray, z: np.ndarray, tail: np.ndarray, row: Mapping, unit: str, log: bool) -> None:
    """가로는 같은 die 의 POR1, 세로는 DOE (검정) 와 다른 POR 회차 (회색). 회색은 다시 잴 때의 흔들림이라 DOE 와 견줄 기준이다.
    두 축 범위를 같게 하고 정사각형으로 그려 y = x 가 45° 대각선이 되게 한다.
    log 면 _value_scale (양수만 log, 0·음수 섞이면 symlog), 아니면 선형 축."""
    J = Y.shape[1]
    for j in range(1, J):
        ax.scatter(Y[:, 0], Y[:, j], s=12, color=POR_GREY, zorder=2)
    ax.scatter(Y[:, 0], z, s=12, color="#444444", zorder=3)
    if tail.any():
        ax.scatter(Y[tail, 0], z[tail], s=46, facecolor="none", edgecolor=FLAG_COLOR, lw=1.4, zorder=4)
    allv = np.r_[Y.ravel(), z]
    allv = allv[np.isfinite(allv)]
    lo, hi = (allv.min(), allv.max()) if allv.size else (0.0, 1.0)
    if log:
        for a in ("x", "y"):
            _value_scale(ax, allv, _f(row.get("LoD")), unit, a)
        if allv.size and (allv > 0).all():
            lims = (lo / 1.3, hi * 1.3)
        else:
            lims = (lo * 1.3 if lo < 0 else -abs(hi) * 0.05, hi * 1.3 if hi > 0 else abs(lo) * 0.05)
        grid = np.geomspace(*lims, 200) if lims[0] > 0 else np.linspace(*lims, 400)
    else:
        pad = 0.05 * (hi - lo) if hi > lo else (abs(hi) * 0.1 or 1.0)
        lims = (lo - pad, hi + pad)
        grid = np.linspace(*lims, 2)
        for target in (ax.xaxis, ax.yaxis):
            target.set_major_formatter(FuncFormatter(lambda t, _: fmt(t, unit)))
    ax.plot(grid, grid, color="#555555", lw=0.9, ls="-")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    _limit_lines(ax, row, "x")
    _limit_lines(ax, row, "y")
    ax.set_xlabel("POR1 (같은 die)")
    ax.set_ylabel("DOE · POR2..")
    ax.set_title("POR1 대 DOE · " + ("log" if log else "선형"))


ITEM_PANEL_IN = 3.4     # ITEM 그림 한 칸 (정사각형) 의 폭, 인치. 네 칸이 한 줄
ITEM_LEGEND = (
    Line2D([0], [0], marker="o", color=POR1_COLOR, ls="none", ms=5, label="POR1"),
    Line2D([0], [0], marker="o", color=POR_GREY, ls="none", ms=5, label="POR2.."),
    Line2D([0], [0], marker="o", color="#444444", ls="none", ms=5, label="DOE"),
    Line2D([0], [0], marker="o", mfc="none", mec=FLAG_COLOR, mew=1.4, ls="none", ms=8, label="크게 벗어난 die"),
    Line2D([0], [0], color="#ff7f0e", lw=1, ls=":", label="LoD"),
    Line2D([0], [0], color="#ff7f0e", lw=1, ls="--", label="LoQ"),
    Line2D([0], [0], color="#555555", lw=0.9, label="y = x (같음)"),
    Rectangle((0, 0), 1, 1, facecolor="#dddddd", label="회차 흔들림 × 5"),
)


def plot_item(item: str, Y: np.ndarray, z: np.ndarray, row: Mapping, review: Review, rec: Mapping,
              path: Path) -> Path:
    """한 줄 네 칸: 회차별 die 값, die별 변화량, POR1 대 DOE 선형, POR1 대 DOE log. 제목과 범례는 그림 위 한 블록 (suptitle 과 바깥 범례가 겹치지 않게)."""
    J, unit = Y.shape[1], str(row.get("UNIT") or "")
    tail = tail_dies(review.space(Y), review.space(z)) if J >= 2 and (review.name == "loq" or _log_ok(Y, z)) \
        else np.zeros(len(z), bool)
    with plt.rc_context({"axes.titlesize": 11, "axes.labelsize": 9.5, "xtick.labelsize": 8.5,
                         "ytick.labelsize": 8.5}):
        fig, axes = plt.subplots(1, 4, figsize=(4 * ITEM_PANEL_IN, ITEM_PANEL_IN + 1.1), layout="constrained")
        for ax in axes:
            ax.set_box_aspect(1)
        rng = np.random.default_rng(0)
        ax = axes[0]
        for j in range(J + 1):
            v = Y[:, j] if j < J else z
            xs = j + rng.uniform(-0.18, 0.18, len(v))
            ax.scatter(xs, v, s=12, color=POR1_COLOR if j == 0 else POR_GREY if j < J else "#444444", zorder=2)
            if j == J and tail.any():
                ax.scatter(xs[tail], v[tail], s=46, facecolor="none", edgecolor=FLAG_COLOR, lw=1.4, zorder=3)
        _value_scale(ax, np.r_[Y.ravel(), z], _f(row.get("LoD")), unit)
        _limit_lines(ax, row)
        ax.set_xticks(range(J + 1))
        ax.set_xticklabels([f"POR{j + 1}" for j in range(J)] + ["DOE"])
        ax.set_title("회차별 die 값")

        ax = axes[1]
        if J >= 2 and (review.name == "loq" or _log_ok(Y, z)):
            d, _, limit = _tail_parts(review.space(Y), review.space(z), OUTLIER_SIGMAS)
            order = np.argsort(d)
            ax.scatter(np.arange(len(d)), d[order], s=12, color=np.where(tail[order], FLAG_COLOR, "#444444"), zorder=3)
            m = np.median(d)
            ax.axhspan(m - limit, m + limit, color="#dddddd", zorder=1)
            ax.axhline(0, color="#888888", lw=0.8)
            if review.name == "loq":
                ax.yaxis.set_major_formatter(FuncFormatter(lambda t, _: fmt(t, unit)))
        ax.set_xlabel("die (작은 순)")
        ax.set_ylabel("변화량\n(DOE − POR 평균)" if review.name == "loq"
                      else "log 변화량\n(log10|DOE| − log10|POR| 평균)")
        ax.set_title("die별 변화량")
        note = (f"↑ {int(rec['n_up'])} · ↓ {int(rec['n_down'])}"
                + (f" · {times(rec['ratio'])}배" if np.isfinite(_f(rec.get("ratio"))) else "")) \
            if review.name == "loq" else \
            f"선형 {pct(rec.get('shift_pct'), 100)} · log {pct(rec.get('shift_log_pct'), 100)}"
        ax.text(0.03, 0.96, note, transform=ax.transAxes, ha="left", va="top", fontsize=8.5,
                bbox=dict(facecolor="white", edgecolor="#cccccc", boxstyle="round,pad=0.3"))

        _por_vs_doe(axes[2], Y, z, tail, row, unit, log=False)
        _por_vs_doe(axes[3], Y, z, tail, row, unit, log=True)
        final = row.get("verdict_final") or row.get("verdict")
        title = f"{item} · 판정 {final} (그대로) · {'LoQ' if review.name == 'loq' else 'log'} 재확인 확인 필요"
        fig.legend(handles=list(ITEM_LEGEND), loc="outside upper center", ncols=len(ITEM_LEGEND), fontsize=8.5,
                   frameon=False, title=title, title_fontsize=12)
        add_figure_note(fig, ITEM_HOW_TO_READ, rec["why"], dpi=DPI)
    return _save(fig, path)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- 실행

OWN_FILES = ("loq_review.csv", "log_review.csv", "loq_review.png", "log_review.png")


def _clear(review_dir: Path) -> None:
    for name in OWN_FILES:
        (review_dir / name).unlink(missing_ok=True)
    for p in (review_dir / ITEMS_DIR).glob("*.png"):
        p.unlink()


def _plot_task(item: str, Y: np.ndarray, z: np.ndarray, row: Mapping, name: str, rec: Mapping, path: Path) -> None:
    plot_item(item, Y, z, row, REVIEWS[name], rec, path)


def run_reviews(items_csv: str | Path, raw_args: argparse.Namespace, out: str | Path,
                max_figures: int = MAX_FIGURES) -> dict[str, pd.DataFrame]:
    """두 재확인을 돌려 <out>/review/ 에 쓴다. 판정 열은 읽기만 한다. {'loq': 표, 'log': 표} 를 돌려준다.
    ITEM 그림은 재확인마다 확인 필요 ITEM 을 근거가 센 순서로 max_figures 개까지 (0 이면 전부), 여러 프로세스로 그린다."""
    items = read_items(items_csv)
    review_dir = Path(out) / REVIEW_DIR
    review_dir.mkdir(parents=True, exist_ok=True)
    _clear(review_dir)
    rows = items.to_dict("records")
    wanted = list(dict.fromkeys(str(r["ITEM"]) for r in rows if any(rv.target(r) for rv in REVIEWS.values())))
    took = {"start": time.perf_counter()}
    raw = load_raw(raw_args, wanted)
    took["원데이터"] = time.perf_counter()
    tables = {name: review_table(rv, items, raw) for name, rv in REVIEWS.items()}
    took["지표"] = time.perf_counter()
    for name, t in tables.items():
        t.to_csv(review_dir / f"{name}_review.csv", index=False, encoding="utf-8-sig")
    configure_font()
    plot_loq_map(tables["loq"], review_dir / "loq_review.png")
    plot_log_map(tables["log"], review_dir / "log_review.png")
    took["요약 그림"] = time.perf_counter()
    by_item = {str(r["ITEM"]): r for r in rows}
    tasks, drawn, capped = [], set(), False
    for name, t in tables.items():     # LoQ 재확인이 먼저: 둘 다 확인 필요면 원래 값 단위 그림을 남긴다
        picked = 0
        for rec in t[t["flag"].astype(bool)].to_dict("records"):
            item = str(rec["ITEM"])
            if item in drawn or item not in raw:
                continue
            if max_figures and picked >= max_figures:
                capped = True
                break
            drawn.add(item)
            picked += 1
            tasks.append((item, *raw[item], by_item[item], name, rec,
                          review_dir / ITEMS_DIR / f"{safe_group_name(item)}.png"))
    if tasks:
        print(f"확인 필요 ITEM 그림 {len(tasks):,}장 그리는 중 (작업 {min(dc_jobs(), len(tasks))}개)", flush=True)
        pool_map(_plot_task, tasks)
    took["ITEM 그림"] = time.perf_counter()
    for name, t in tables.items():
        print(f"{name} 재확인: 대상 {len(t):,}개, 확인 필요 {int(t['flag'].sum()):,}개")
    if capped:
        print(f"ITEM 그림은 재확인마다 근거가 센 {max_figures:,}개까지만 그렸다 (전부: --max-figures 0)")
    marks = list(took.items())
    print("걸린 시간: " + ", ".join(f"{name} {t - prev:.1f}초" for (_, prev), (name, t) in zip(marks, marks[1:])))
    return tables


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LoQ·log 판정 재확인 (참고용, 판정은 그대로).")
    p.add_argument("--input", required=True, help="por_doe_compare.py 결과 items.csv")
    p.add_argument("--out", required=True, help="출력 폴더 (그 아래 review/ 에 씀)")
    p.add_argument("--max-figures", type=int, default=MAX_FIGURES,
                   help=f"재확인마다 ITEM 그림을 그릴 확인 필요 ITEM 수, 근거가 센 순서 (기본 {MAX_FIGURES}, 0 = 전부)")
    add_raw_args(p.add_argument_group("원데이터 (por_doe_compare.py 와 같은 인자)"))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not (args.por and args.doe):
        print("오류: 원데이터 --por 와 --doe 가 필요합니다.", file=sys.stderr)
        return 2
    run_reviews(args.input, args, args.out, args.max_figures)
    return 0


if __name__ == "__main__":
    sys.exit(main())
