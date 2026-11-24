"""LoQ 아래 ITEM 만 따로 본다 (참고용, 판정은 그대로). 세 가지를 사용자 데이터로 답한다.

  한계 영역을 전부 통과시켰나?   items.csv 만으로: LoQ 아래 ITEM 이 어떻게 동등이 됐나 (동등이 된 이유)
  진짜 변한 것을 놓치나?         POR 회차로 만든, 답을 아는 비교에 알려진 변화를 넣어 판정 코드를 그대로 돌린다
  안 변한 것을 걸리게 하나?      같은 비교에 변화를 넣지 않고 돌린다

    python loq_check.py --input <out>/A1/items.csv --out <out>/A1 --por r1/ --por r2/ --por r3/ --doe d/
    → <out>/A1/loq/: loq_items.csv, loq_levels.csv, loq_trials.csv, loq_curve.png, loq_reasons.png

만든 비교 하나 = ITEM 하나 × POR 회차 k 하나 × 수준 하나. 회차 k (x) 를 DOE 자리에, 나머지 J − 1 회차 (평균 m′) 를
POR 자리에 둔다. 판정과 재확인이 같은 DOE′ 를 본다.
  DOE′ = m′ + loo_scale(J) · (x − m′) + s              DOE′ − m′ 이 실제 DOE − J 회차 평균과 같은 분산
  알려진 변화 s = sgn · u · LoQ − POR 중앙값            참 DOE 수준이 LoQ 의 u 배
  신뢰구간 = ci_median(DOE′ − m′)                        = ci_median(s 없이) + s (부호검정 구간은 평행이동을 따라간다)
|s| ≤ Δ 인 (ITEM, 수준) 은 진짜 변화가 아니라 수준별 비율에서 뺀다 (변화 없음은 모두 센다).
판정은 items.csv 의 그 ITEM 행에서 center·ci_low·ci_high 만 바꿔 por_doe_compare.rescaled_verdicts(·, 1.0) 로 낸다
(Δ, LoQ, POR 중앙값, 판정 길은 그대로). 실행마다 OWN_FILES 를 지우고 다시 쓴다. 리포트(report.py)는 load() 로만 읽는다.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import review  # noqa: E402
from explain import add_figure_note  # noqa: E402
from fail_evidence import add_raw_args  # noqa: E402
from plot_verdicts import configure_font  # noqa: E402
from por_doe_compare import (  # noqa: E402
    JUDGED, LOQ_PASS_BELOW, LOQ_PASS_CROSS, LOQ_PASS_SHIFT, LOQ_ZONE_NAMES, MIN_DIE, R_ABS, R_EXCLUDED, R_LINEAR, R_LOQ,
    RESCALED, ST_NEAR_LOQ, _status_parts, _text, ci_median, loq_verdict, rescaled_verdicts, robust_sigma, route_method,
    tost,
)

LOQ_DIR = "loq"
ITEMS_CSV, LEVELS_CSV, TRIALS_CSV = "loq_items.csv", "loq_levels.csv", "loq_trials.csv"
CURVE_PNG, REASONS_PNG = "loq_curve.png", "loq_reasons.png"
WORKBOOK, WORKBOOK_ANON = "LoQ.xlsx", "LoQ_anon.xlsx"
OWN_FILES = (ITEMS_CSV, LEVELS_CSV, TRIALS_CSV, CURVE_PNG, REASONS_PNG)   # 리포트·엑셀은 report.py 가 다시 쓴다

NO_CHANGE = 0.0                                          # 수준 열에서 '변화 없음' (s = 0). 격자에 0 은 없다
GRID = tuple(round(0.1 * i, 1) for i in range(1, 31))    # 참 DOE 수준 ÷ LoQ
HEADLINE = (0.5, 0.8, 1.2, 1.5, 2.0)                     # 0.5·0.8 은 DOE 가 LoQ 아래, 1.2 이상은 위
LEVELS = (NO_CHANGE, *GRID)
REVIEW_LEVELS = (NO_CHANGE, *HEADLINE)
CAUGHT = ("차이", "미결")
TESTED = "예"
SIM_ROUTES = (R_LOQ, R_ABS, R_LINEAR, R_EXCLUDED)       # 3단계 판정 열을 items.csv 숫자만으로 다시 낼 수 있는 길
N_BOOT, SEED, BOOT_PCT = 2000, 0, (5.0, 95.0)

# 동등이 된 이유. 2단계 사유 상수 → 이유, 2단계는 차이·미결인데 판정 길이 동등을 주면 K_STAGE3
K_SHIFT, K_BELOW, K_CROSS, K_STAGE3 = "이동이 허용폭 안", "DOE 구간도 LoQ 아래", "DOE 구간이 LoQ에 걸침", "판정 길"
PASS_KINDS = {LOQ_PASS_SHIFT: K_SHIFT, LOQ_PASS_BELOW: K_BELOW, LOQ_PASS_CROSS: K_CROSS}
RULE_PASSES = (K_BELOW, K_CROSS, K_STAGE3)               # 보통 TOST 였다면 동등이 아님 (2단계 첫 줄이 보통 TOST)
KIND_ORDER = (K_SHIFT, K_BELOW, K_CROSS, K_STAGE3, "미결", "차이")
KIND_COLORS = {K_SHIFT: "#009E73", K_BELOW: "#0072B2", K_CROSS: "#56B4E9", K_STAGE3: "#CC79A7", "미결": "#E69F00",
               "차이": "#D55E00"}

ITEM_COLS = ["ITEM", "UNIT", "zone", "verdict_final", "pass_kind", "route", "verdict_tost", "por_loq", "doe_lo_loq",
             "doe_hi_loq", "review_flag", "review_ratio", "null_caught", "n_runs", "catch_level", "catch_ratio",
             "doe_noise_ratio", "tested", "why"]
MEASURES = {"final": "verdict_final", "rule": "verdict_rule", "tost": "verdict_tost", "review": "review_flag"}
LEVEL_COLS = ["level", "level_name", "n_items", "n_comparisons",
              *(f"caught_{m}{s}" for m in MEASURES for s in ("", "_lo", "_hi")), "diff_final", "diff_final_lo",
              "diff_final_hi"]
TRIAL_COLS = ["ITEM", "run", "level", "shift", "center", "ci_low", "ci_high", "verdict_final", "verdict_rule",
              "verdict_tost", "review_flag"]

CURVE_HOW_TO_READ = (
    "가로는 POR 회차 하나로 만든 DOE 의 참 수준 (LoQ 의 몇 배), 세로는 그 비교를 판정이 차이·미결로 잡은 비율이다. "
    "ITEM 마다 회차 비교를 모두 해 ITEM 별 비율을 내고 ITEM 끼리 평균했다. 수준마다 ITEM 의 허용폭 Δ 보다 큰 변화만 "
    "셌다 (그 ITEM 의 POR 수준 가까이는 변화가 아니라 뺀다). 진한 선이 실제 판정 (최종), 하늘색 점선이 "
    "3단계 판정 길 없이 2단계 LoQ 판정만, 회색 파선이 LoQ 규칙 없는 보통 TOST, 주황 점이 LoQ 재확인 (방향)이다. 왼쪽 "
    "회색 칸은 DOE 도 LoQ 아래라 판정 규칙상 동등인 곳이다. 맨 왼쪽 '변화 없음' 은 변화를 넣지 않은 비교라 여기서 잡힌 "
    "것은 오경보다. 띠는 ITEM 을 다시 뽑아 본 90% 범위다.")
REASONS_HOW_TO_READ = (
    "막대 하나가 구간 하나의 LoQ 아래 ITEM 전부다. 칸은 최종 판정과 동등이 된 이유다. 초록은 이동이 허용폭 안이라 LoQ "
    "규칙 없이도 동등, 파랑 두 칸은 LoQ 규칙 (DOE 구간이 LoQ 아래이거나 걸침) 으로 동등, 보라는 판정 길 (절대 허용폭 등) "
    "로 동등, 주황·빨강은 미결·차이다.")
METHOD_LINES = (
    "POR 회차 하나를 DOE 자리에, 나머지 회차를 POR 자리에 두고 판정 코드를 그대로 돌렸다. 회차 하나는 같은 조건을 다시 잰 "
    "것이라 '변화 없음' 의 답을 안다. 그 회차에 알려진 양을 더해 DOE 의 참 수준을 LoQ 의 0.1~3배로 옮기면 '변화 있음' 의 "
    "답을 안다. 허용폭 Δ, LoQ, POR 중앙값, 판정 길은 이 ITEM 의 판정 값 그대로 둔다. 회차 하나와 나머지 평균의 차는 실제 "
    "DOE − POR 평균과 흔들림이 같도록 배수를 곱했다. 판정과 재확인은 이렇게 만든 같은 DOE 를 본다.",
    "수준마다 ITEM 의 허용폭 Δ 보다 큰 변화만 셈. 참 수준이 그 ITEM 의 POR 수준에서 Δ 안이면 변화가 아니므로 그 수준의 "
    "비율에서 뺀다. 그래서 수준마다 ITEM 수가 다르다. 변화 없음은 모든 ITEM 을 센다.",
    "잡힘 = 최종 판정이 차이나 미결. ITEM 마다 회차 비교 J번 중 잡힌 비율을 내고 ITEM 끼리 평균한다. 범위는 ITEM 을 "
    f"{N_BOOT}번 다시 뽑아 본 90% 범위다.",
    "재확인 (방향) 은 실제 LoQ 재확인과 같은 부호검정·배수 기준 (q < 0.05, 배수 1/1.3~1.3 밖) 을 같은 수준·같은 회차의 "
    "ITEM 끼리 BH 보정해 적용했다. 꼬리 검사는 넣지 않았다.",
)
BIAS_LINES = (
    "POR 회차 하나는 lot·조건 차이가 없는 같은 조건이다. 실제 DOE 는 그런 차이가 더해지므로 실제 오경보는 여기 숫자 이상일 "
    "수 있다.",
    "Δ 와 LoQ 를 판정 값으로 고정했다. 실제로는 이 값도 흔들리므로 LoQ 의 1배 근처 숫자는 실제보다 좋게 나온다.",
    "모든 die 가 같은 양만큼 움직이는 변화는 가장 잡기 쉬운 변화다. 일부 die 만 바뀌는 변화는 여기서 시험하지 않았고 "
    "재확인의 꼬리 검사가 본다. 부분 변화의 잡힘은 여기 숫자보다 낮다.",
    "0 쪽으로 줄어드는 변화는 DOE 가 LoQ 아래에 머물러 규칙상 잡히지 않는다.",
    "한 ITEM 의 회차 비교는 같은 die 를 나눠 써 서로 닮는다. 그래서 범위는 ITEM 단위로 다시 뽑아 냈다.",
    "DOE 잡음 비 (doe_noise_ratio) 가 1 보다 큰 ITEM 은 실제 DOE 가 POR 회차보다 흔들려, 이 ITEM 의 잡힘 숫자가 실제보다 "
    "좋게 나온다.",
)


class Count(NamedTuple):
    """분모가 붙은 숫자. 리포트에 나가는 비율은 모두 이것의 text() 로 쓴다."""
    n: int
    k: int

    @property
    def rate(self) -> float:
        return self.k / self.n if self.n else math.nan

    def text(self, unit: str = "번") -> str:
        if not self.n:
            return f"0{unit}"
        r = 100 * self.k / self.n
        share = "1% 미만" if 0 < r < 0.5 else f"{r:.0f}%"
        return f"{self.n:,}{unit} 중 {self.k:,}{unit} ({share})"


# ---------------------------------------------------------------- 동등이 된 이유 (items.csv 만)

def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def in_zone(row: Mapping) -> bool:
    return _text(row.get("zone")) in LOQ_ZONE_NAMES and _text(row.get("verdict_final")) in JUDGED


def pass_kind(row: Mapping) -> str:
    final = _text(row.get("verdict_final"))
    if final != "동등":
        return final
    if _text(row.get("verdict")) != "동등":
        return K_STAGE3
    return PASS_KINDS.get(_text(row.get("reason")), _text(row.get("reason")))


def plain_tost(row: Mapping) -> str:
    c, lo, hi, delta = (_f(row.get(k)) for k in ("center", "ci_low", "ci_high", "delta"))
    return tost(c, lo, hi, delta)[0] if np.isfinite([c, lo, hi, delta]).all() and delta > 0 else ""


def ledger_frame(items: pd.DataFrame, rev: pd.DataFrame | None) -> pd.DataFrame:
    """LoQ 아래 ITEM (zone 이 LoQ zone, 최종 판정이 동등·차이·미결) 한 행씩: 동등이 된 이유, 보통 TOST, 수준 ÷ LoQ,
    실제 LoQ 재확인 결과. 판정·시험 열 밖의 items.csv 열 (verdict, reason, delta 등) 도 뒤에 남긴다."""
    rows = [r for r in items.to_dict("records") if in_zone(r)]
    flags = {} if rev is None else {str(r["ITEM"]): r for r in rev.to_dict("records")}
    out = []
    for r in rows:
        base, loq = _f(r.get("por_median")), _f(r.get("LoQ"))
        lo, hi = base + _f(r.get("ci_low")), base + _f(r.get("ci_high"))
        rv = flags.get(str(r["ITEM"]), {})
        out.append({**r, "pass_kind": pass_kind(r), "verdict_tost": plain_tost(r), "por_loq": base / loq,
                    "doe_lo_loq": lo / loq, "doe_hi_loq": hi / loq,
                    "review_flag": _flag(rv["flag"]) if "flag" in rv else math.nan,
                    "review_ratio": _f(rv.get("ratio")),
                    "review_rule": "·".join(name for col, name in (("flag_direction", "방향"), ("flag_tail", "꼬리"))
                                            if _flag(rv.get(col)))})
    return pd.DataFrame(out, columns=list(dict.fromkeys([*ITEM_COLS[:12], "review_rule", *items.columns])))


def _flag(v) -> bool:
    return str(v).strip().lower() == "true" if not isinstance(v, (bool, np.bool_)) else bool(v)


def _yes(v) -> bool:
    """재확인 열 값이 참인가 (빈 칸·NaN 은 아님)."""
    return isinstance(v, (bool, np.bool_)) and bool(v)


def n_near(items: pd.DataFrame) -> int:
    """정량 zone 의 'LoQ 근처' ITEM 수 (2단계 LoQ 판정을 타지 않아 한 줄로만 센다)."""
    return sum(_text(r.get("zone")) not in LOQ_ZONE_NAMES and ST_NEAR_LOQ in _status_parts(r.get("status"))
               for r in items.to_dict("records"))


# ---------------------------------------------------------------- 만든 비교

def shifts(row: Mapping, levels=LEVELS) -> np.ndarray:
    """수준마다 알려진 변화 s: 참 DOE 수준을 sgn · u · LoQ 로 (sgn 은 POR 중앙값 부호, 0 이면 +). 변화 없음은 0."""
    base, loq = _f(row.get("por_median")), _f(row.get("LoQ"))
    sgn = 1.0 if base == 0 else math.copysign(1.0, base)
    u = np.asarray(levels, float)
    return np.where(u == NO_CHANGE, 0.0, sgn * u * loq - base)


def counted(row: Mapping, levels=LEVELS) -> np.ndarray:
    """수준마다 비율에 세나: 변화 없음, 또는 넣은 변화가 이 ITEM 의 허용폭 Δ 보다 클 때."""
    return (np.asarray(levels, float) == NO_CHANGE) | (np.abs(shifts(row, levels)) > _f(row.get("delta")))


def untested_reason(row: Mapping, raw: tuple[np.ndarray, np.ndarray] | None) -> str:
    """시험할 수 없으면 그 이유 (쉬운 말), 할 수 있으면 ''."""
    if raw is None:
        return "원데이터에서 이 ITEM 을 찾지 못함"
    Y = raw[0]
    if Y.shape[1] < 2:
        return "POR 회차가 1개"
    if Y.shape[0] < MIN_DIE:
        return f"die {Y.shape[0]}개 (< {MIN_DIE})"
    route = _text(row.get("route"))
    if route not in SIM_ROUTES:
        return f"판정 길 '{route or '없음'}' 은 3단계를 원데이터로 다시 계산해야 해 시험하지 않음"
    nums = [_f(row.get(k)) for k in ("delta", "LoQ", "por_median")]
    if not (np.isfinite(nums).all() and nums[0] > 0 and nums[1] > 0) or _text(row.get("verdict")) not in JUDGED:
        return "Δ 나 LoQ 가 0 이거나 없어 판정 코드가 다시 판정하지 않음"
    return ""


def stale_route(row: Mapping, cis: np.ndarray) -> str:
    """rescaled_verdicts 는 판정 길 열이 동등·차이·미결이 아니거나 숫자가 없으면 원래 값을 그대로 둔다. 그러면 만든
    비교의 최종 판정이 실제 판정의 판정 길 값이 되므로, 모든 비교에서 그 열이 다시 판정되는지 본다. 안 되면 그 이유."""
    method = route_method(row)
    if method is None:
        return ""
    col = method[0]
    fn = RESCALED.get(col)
    ok = fn is not None and _text(row.get(col)) in JUDGED and all(
        fn({**row, "center": c, "ci_low": lo, "ci_high": hi}, 1.0) is not None for c, lo, hi in cis)
    return "" if ok else f"판정 길 '{_text(row.get('route'))}' 의 판정 ({col}) 을 다시 낼 수 없음"


def item_trials(row: Mapping, Y: np.ndarray, z: np.ndarray) -> tuple[pd.DataFrame, dict, str]:
    """ITEM 하나의 만든 비교 (회차 × 수준) 표, 재확인 지표 (BH 전), 시험 못 한 이유 ('' 이면 시험함)."""
    J = Y.shape[1]
    s, keep = shifts(row), counted(row)
    recs, rev, d0s = [], [], []
    for k in range(J):
        rest, x = np.delete(Y, k, axis=1), Y[:, k]
        m = rest.mean(axis=1)
        d0 = review.loo_scale(J) * (x - m)
        d0s.append(d0 - np.median(d0))
        c0, lo0, hi0 = ci_median(d0)
        for u, sh, ok in zip(LEVELS, s, keep):
            if ok:
                recs.append((k + 1, u, sh, c0 + sh, lo0 + sh, hi0 + sh))
            if u in REVIEW_LEVELS:      # BH 묶음은 세지 않는 수준의 ITEM 도 넣는다 (실제 재확인처럼 넓게)
                rev.append({"ITEM": row["ITEM"], "run": k + 1, "level": u, **review.sign_test(d0 + sh),
                            **review.ratio_ci(rest, m + d0 + sh)})
    t = pd.DataFrame(recs, columns=["run", "level", "shift", "center", "ci_low", "ci_high"])
    why = stale_route(row, t[["center", "ci_low", "ci_high"]].to_numpy())
    if why:
        return t.iloc[0:0], {}, why
    frame = pd.DataFrame([row] * len(t)).assign(center=t["center"].to_numpy(), ci_low=t["ci_low"].to_numpy(),
                                                ci_high=t["ci_high"].to_numpy())
    base, loq, delta = (_f(row.get(k)) for k in ("por_median", "LoQ", "delta"))
    t.insert(0, "ITEM", row["ITEM"])
    t["verdict_final"] = rescaled_verdicts(frame, 1.0).to_numpy()
    t["verdict_rule"] = [loq_verdict(c, lo, hi, delta, base, loq)[0] for c, lo, hi in
                         zip(t["center"], t["ci_low"], t["ci_high"])]
    t["verdict_tost"] = [tost(c, lo, hi, delta)[0] for c, lo, hi in zip(t["center"], t["ci_low"], t["ci_high"])]
    d = z - Y.mean(axis=1)
    noise = robust_sigma(np.concatenate(d0s))      # 회차마다 중앙값을 뺀다: 실제 d 의 MAD 에도 회차 이동은 빠져 있다
    extra = {"n_runs": J, "doe_noise_ratio": robust_sigma(d) / noise if noise > 0 else math.nan, "review": rev}
    return t, extra, ""


def review_flags(rows: list[dict]) -> pd.DataFrame:
    """만든 비교의 재확인 (방향만): 같은 (수준, 회차) 의 ITEM 끼리 BH 보정해 review.flag_loq 를 그대로 적용한다."""
    t = pd.DataFrame(rows).assign(tail_p=np.nan, tail_frac=np.nan).astype({"dir_p": float, "ratio": float})
    parts = [review.flag_loq(g) for _, g in t.groupby(["level", "run"], sort=False)]
    return pd.concat(parts)[["ITEM", "run", "level", "flag"]].rename(columns={"flag": "review_flag"})


def catch_level(caught_all: Mapping[float, bool]) -> float:
    """격자 수준 u 이상 모든 격자 수준에서 회차 비교가 모두 잡히는 가장 작은 u. 3.0 에서도 아니면 inf.
    caught_all 에 없는 수준 (넣은 변화가 Δ 이하라 세지 않은 수준) 은 건너뛴다."""
    level = math.inf
    for u in reversed(GRID):
        if u not in caught_all:
            continue
        if not caught_all[u]:
            break
        level = u
    return level


# ---------------------------------------------------------------- 표

def per_item_shares(trials: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """측정마다 ITEM × 수준 의 잡힌 비율 (그 ITEM 의 회차 비교 중). 세지 않은 (ITEM, 수준) 과 REVIEW_LEVELS 밖의
    재확인은 NaN."""
    t = trials.assign(**{f"_{m}": trials[c].isin(CAUGHT) for m, c in MEASURES.items() if m != "review"},
                      _review=trials["review_flag"].map(lambda v: np.nan if pd.isna(v) else float(v)),
                      _diff=trials["verdict_final"].eq("차이"))
    g = t.groupby(["ITEM", "level"], sort=False)
    return {m: g[f"_{m}"].mean().astype(float).unstack("level") for m in (*MEASURES, "diff")}


def levels_table(trials: pd.DataFrame, seed: int = SEED, n_boot: int = N_BOOT) -> pd.DataFrame:
    """loq_levels.csv. 수준 한 줄: 그 수준에서 센 ITEM 의 평균 잡힌 비율과 ITEM 을 다시 뽑은 90% 범위."""
    rows = {"level": list(LEVELS), "level_name": [level_name(u) for u in LEVELS]}
    if trials.empty:
        return pd.DataFrame(rows | {"n_items": 0, "n_comparisons": 0}).reindex(columns=LEVEL_COLS)
    shares = per_item_shares(trials)
    final = shares["final"].reindex(columns=list(LEVELS))
    n = len(final)
    rows["n_items"] = final.notna().sum().to_numpy()
    rows["n_comparisons"] = [int(trials["level"].eq(u).sum()) for u in LEVELS]
    idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n))
    weights = np.stack([np.bincount(i, minlength=n) for i in idx]).astype(float)
    with np.errstate(invalid="ignore"):
        for m in (*MEASURES, "diff"):
            name = "diff_final" if m == "diff" else f"caught_{m}"
            S = shares[m].reindex(index=final.index, columns=list(LEVELS)).to_numpy(float)
            ok = np.isfinite(S)
            S0 = np.where(ok, S, 0.0)
            rows[name] = S0.sum(axis=0) / ok.sum(axis=0)
            rows[f"{name}_lo"], rows[f"{name}_hi"] = np.percentile((weights @ S0) / (weights @ ok), BOOT_PCT, axis=0)
    return pd.DataFrame(rows)[LEVEL_COLS]


def level_name(u: float) -> str:
    return "변화 없음" if u == NO_CHANGE else f"{u:.1f}×LoQ"


def item_table(ledger: pd.DataFrame, trials: pd.DataFrame, extras: Mapping[str, dict],
               untested: Mapping[str, str]) -> pd.DataFrame:
    """loq_items.csv: 동등이 된 이유 + 시험 결과 + why. LoQ 규칙·판정 길로 동등인 ITEM 이 먼저, 그 안에서 재확인 확인
    필요 먼저, 그다음 잡히는 수준이 POR 의 몇 배인지 큰 순 (3배까지 다 잡히지 않는 inf 가 맨 앞)."""
    shares = per_item_shares(trials)["final"] if len(trials) else pd.DataFrame()
    rows = []
    for r in ledger.to_dict("records"):
        item = str(r["ITEM"])
        ex = extras.get(item)
        out = {**r, "tested": untested.get(item) or TESTED}
        if ex is not None and item in shares.index:
            s = shares.loc[item]
            J = ex["n_runs"]
            level = catch_level({u: s[u] >= 1.0 for u in GRID if math.isfinite(s.get(u, math.nan))})
            base, loq, lod = _f(r.get("por_median")), _f(r.get("LoQ")), _f(r.get("LoD"))
            out.update(null_caught=int(round(s[NO_CHANGE] * J)), n_runs=J, catch_level=level,
                       catch_ratio=level * loq / abs(base) if abs(base) >= lod else math.nan,
                       doe_noise_ratio=ex["doe_noise_ratio"])
        rows.append(out)
    t = pd.DataFrame(rows).reindex(columns=[*ITEM_COLS, "verdict", "delta", "LoQ", "review_rule"])
    t["why"] = [why(r) for r in t.to_dict("records")]
    rule = t["pass_kind"].isin(RULE_PASSES).to_numpy(bool)
    flagged = t["review_flag"].map(_yes).to_numpy(bool)
    order = np.lexsort((-t["catch_ratio"].astype(float).fillna(-1).to_numpy(), ~flagged, ~rule))
    return t.iloc[order][ITEM_COLS].reset_index(drop=True)


def _x(v: float) -> str:
    return f"{v:.2g}" if abs(v) < 10 else f"{v:.0f}"


def why(r: Mapping) -> str:
    """ITEM 하나를 쉬운 말 한두 문장으로: 어떻게 판정됐나, 시험에서 어디부터 잡히나, 재확인."""
    kind = _text(r.get("pass_kind"))
    span = f"POR {_x(_f(r.get('por_loq')))}×LoQ, DOE 구간 {_x(_f(r.get('doe_lo_loq')))}~{_x(_f(r.get('doe_hi_loq')))}×LoQ"
    head = {K_SHIFT: "이동이 허용폭 안이라 동등 (LoQ 규칙 없이도 동등)",
            K_BELOW: "DOE 구간도 LoQ 아래라 동등",
            K_CROSS: "DOE 구간이 LoQ 에 걸쳐 동등",
            K_STAGE3: f"2단계는 {_text(r.get('verdict'))}이지만 판정 길 '{_text(r.get('route'))}' 에서 동등"}.get(
        kind, f"최종 {kind}")
    if kind in RULE_PASSES and _text(r.get("verdict_tost")):
        head += f", 보통 TOST 였다면 {_text(r.get('verdict_tost'))}"
    parts = [f"{span}. {head}"]
    tested = _text(r.get("tested"))
    if tested != TESTED:
        parts.append(f"시험 못 함: {tested}")
    else:
        level, ratio, J = _f(r.get("catch_level")), _f(r.get("catch_ratio")), int(_f(r.get("n_runs")))
        if math.isinf(level):
            parts.append(f"시험에서 DOE 가 LoQ 의 3배까지 올라가도 회차 비교 {J}번이 다 잡히지는 않음 "
                         f"(허용폭 Δ 가 LoQ 의 {_x(_f(r.get('delta')) / _f(r.get('LoQ')))}배)")
        else:
            times = f" (POR 의 {_x(ratio)}배)" if math.isfinite(ratio) else ""
            parts.append(f"시험에서 DOE 가 LoQ 의 {level:.1f}배{times} 이상이면 회차 비교 {J}번이 모두 잡힘")
        caught = int(_f(r.get("null_caught")))
        if caught:
            parts.append(f"변화 없는 비교 {J}번 중 {caught}번이 잡힘")
    if _yes(r.get("review_flag")):
        ratio = _f(r.get("review_ratio"))
        rule = _text(r.get("review_rule"))
        size = f"DOE ÷ POR 약 {_x(ratio)}배" if math.isfinite(ratio) and "방향" in rule else ""
        parts.append(f"재확인 확인 필요 ({', '.join(x for x in (rule, size) if x) or '-'})")
    return ". ".join(parts) + "."


# ---------------------------------------------------------------- 실행

def _read_review(folder: Path) -> pd.DataFrame | None:
    path = folder / review.REVIEW_DIR / "loq_review.csv"
    return review.read_items(path) if path.is_file() else None


def simulate(ledger: pd.DataFrame, raw: review.Raw) -> tuple[pd.DataFrame, dict, dict]:
    """(만든 비교 표, ITEM → 시험 부가값, ITEM → 시험 못 한 이유)."""
    parts, extras, untested, rev = [], {}, {}, []
    for row in ledger.to_dict("records"):
        item = str(row["ITEM"])
        why_not = untested_reason(row, raw.get(item))
        if not why_not:
            t, ex, why_not = item_trials(row, *raw[item])
        if why_not:
            untested[item] = why_not
            continue
        parts.append(t)
        rev += ex.pop("review")
        extras[item] = ex
    if not parts:
        return pd.DataFrame(columns=TRIAL_COLS), extras, untested
    trials = pd.concat(parts, ignore_index=True).merge(review_flags(rev), on=["ITEM", "run", "level"], how="left")
    return trials[TRIAL_COLS], extras, untested


def run(items_csv: str | Path, raw_args: argparse.Namespace, out: str | Path) -> None:
    """<out>/loq/ 의 OWN_FILES 를 지우고 다시 쓴다. items.csv 와 판정 열은 읽기만 한다. 원데이터는 LoQ 아래 ITEM 만 읽는다."""
    items = review.read_items(items_csv)
    wanted = [str(r["ITEM"]) for r in items.to_dict("records") if in_zone(r)]
    build(out, items, review.load_raw(raw_args, wanted))


def build(out: str | Path, items: pd.DataFrame, raw: review.Raw) -> None:
    """run 의 원데이터를 읽은 뒤 부분 (raw: ITEM → (Y, z))."""
    out = Path(out)
    ledger = ledger_frame(items, _read_review(out))
    trials, extras, untested = simulate(ledger, raw)
    table = item_table(ledger, trials, extras, untested)
    levels = levels_table(trials)
    folder = out / LOQ_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for name in OWN_FILES:
        (folder / name).unlink(missing_ok=True)
    table.to_csv(folder / ITEMS_CSV, index=False, encoding="utf-8-sig")
    levels.to_csv(folder / LEVELS_CSV, index=False, encoding="utf-8-sig")
    trials[trials["level"].isin(REVIEW_LEVELS)].to_csv(folder / TRIALS_CSV, index=False, encoding="utf-8-sig")
    book = _book(out, items)
    configure_font()
    if book.check.n_items:
        plot_curve(levels, book, folder / CURVE_PNG)
    if len(table):
        plot_reasons(table, book, folder / REASONS_PNG)
    print(f"LoQ 점검: LoQ 아래 ITEM {len(ledger):,}개, 시험 {len(extras):,}개, 시험 못 함 {len(untested):,}개 → {folder}")
    for line in book.headline_lines():
        print(f"  {line}")


# ---------------------------------------------------------------- 읽기 (리포트용)

@dataclass(frozen=True)
class Ledger:
    n_total: int
    n_zone: int
    n_near: int
    final: dict[str, int]          # 동등·미결·차이
    passes: dict[str, int]         # 동등이 된 이유 (판정 길은 길 이름까지) → ITEM 수
    rule_pass: int                 # RULE_PASSES 로 동등
    rule_tost: dict[str, int]      # 그중 보통 TOST 판정 (차이·미결) → ITEM 수
    rule_flagged: int | None       # 그중 재확인 확인 필요 (review/loq_review.csv 가 없으면 None)


@dataclass(frozen=True)
class Check:
    n_items: int
    n_runs: int
    untested: dict[str, int]                        # 시험 못 한 이유 → ITEM 수
    caught: dict[str, dict[float, Count]]           # 측정 (final, rule, tost, review, diff) → 수준 → 비교 수 중 잡힘
    noise_ratio: float                              # doe_noise_ratio 중앙값 (시험한 ITEM)
    n_noisy: int                                    # doe_noise_ratio > 1 인 ITEM

    def at(self, measure: str, level: float) -> Count:
        return self.caught[measure].get(level, Count(0, 0))


@dataclass(frozen=True)
class LoqSummary:
    ledger: Ledger
    check: Check | None


def _ledger(items: pd.DataFrame, led: pd.DataFrame, has_review: bool) -> Ledger:
    kinds = led["pass_kind"].astype(str)
    passes = {}
    for k in KIND_ORDER[:4]:
        hit = led[kinds == k]
        if k == K_STAGE3:
            for route, n in hit["route"].astype(str).value_counts().items():
                passes[f"{K_STAGE3} ({route})"] = int(n)
        elif len(hit):
            passes[k] = len(hit)
    rule = led[kinds.isin(RULE_PASSES)]
    return Ledger(len(items), len(led), n_near(items),
                  {v: int(led["verdict_final"].eq(v).sum()) for v in ("동등", "미결", "차이")}, passes, len(rule),
                  {v: int(rule["verdict_tost"].eq(v).sum()) for v in CAUGHT},
                  int(rule["review_flag"].map(_yes).sum()) if has_review else None)


def _check(table: pd.DataFrame, levels: pd.DataFrame) -> Check:
    tested = table[table["tested"].astype(str) == TESTED]
    J = int(tested["n_runs"].max()) if len(tested) else 0
    caught = {}
    for m in (*MEASURES, "diff"):
        col = "diff_final" if m == "diff" else f"caught_{m}"
        caught[m] = {float(r["level"]): Count(int(r["n_comparisons"]), int(round(r[col] * r["n_comparisons"])))
                     for r in levels.to_dict("records") if math.isfinite(_f(r[col]))}
    ratio = tested["doe_noise_ratio"].astype(float)
    return Check(len(tested), J, table.loc[table["tested"].astype(str) != TESTED, "tested"].value_counts().to_dict(),
                 caught, float(ratio.median()) if ratio.notna().any() else math.nan, int((ratio > 1).sum()))


@dataclass(frozen=True)
class LoqBook:
    """리포트가 쓰는 전부. items: LoQ 아래 ITEM 한 행씩 (loq/ 가 있으면 시험 열까지), levels: loq_levels.csv."""
    folder: Path
    summary: LoqSummary
    items: pd.DataFrame
    levels: pd.DataFrame | None

    @property
    def check(self) -> Check | None:
        return self.summary.check

    @property
    def curve(self) -> Path:
        return self.folder / LOQ_DIR / CURVE_PNG

    @property
    def reasons(self) -> Path:
        return self.folder / LOQ_DIR / REASONS_PNG

    def check_line(self) -> str:
        c = self.check
        if c is None:
            return f"시험은 아직 없음 (dcc.py loq {self.folder.name})"
        if not c.n_items:
            return "시험할 수 있는 LoQ 아래 ITEM 이 없다."
        return (f"시험 (POR 회차로 만든 비교, ITEM {c.n_items:,}개): 변화 없음에서 판정이 잡은 비교 "
                f"{c.at('final', NO_CHANGE).text()} · DOE 0.8×LoQ 에서 판정 {c.at('final', 0.8).text()}, 재확인 "
                f"{c.at('review', 0.8).text()} · DOE 1.5×LoQ 에서 판정 {c.at('final', 1.5).text()}.")

    def headline_lines(self) -> list[str]:
        """한눈에 블록과 LoQ 리포트 첫 칸이 같이 쓰는 문장. 첫 줄은 ITEM 수, 둘째 줄은 LoQ 규칙 효과, 셋째 줄은 시험."""
        g = self.summary.ledger
        f = g.final
        lines = [f"LoQ 아래 ITEM {g.n_zone:,}개 (전체 {g.n_total:,}개 중): 동등 {f['동등']:,} · 미결 {f['미결']:,} · "
                 f"차이 {f['차이']:,}"]
        flagged = ("재확인 결과 없음" if g.rule_flagged is None
                   else f"그중 재확인 '확인 필요' {g.rule_flagged:,}개")
        lines.append(f"LoQ 규칙이 없었다면 차이 {g.rule_tost['차이']:,}개·미결 {g.rule_tost['미결']:,}개 → LoQ 규칙으로 동등. "
                     f"{flagged}.")
        lines.append(self.check_line())
        if g.n_near:
            lines.append(f"LoQ 근처 ITEM {g.n_near:,}개는 정량 구간이라 보통 판정을 탔고 여기서 세지 않았다.")
        return lines

    def answers(self) -> list[tuple[str, str]]:
        """세 질문과 숫자로 만든 답 (한두 문장)."""
        g, c = self.summary.ledger, self.check
        n_eq = g.final["동등"]
        q1 = (f"LoQ 아래 ITEM {Count(g.n_zone, n_eq).text('개')} 가 동등이다. 그중 {g.passes.get(K_SHIFT, 0):,}개는 "
              f"이동이 허용폭 안이라 LoQ 규칙 없이도 동등이고, {g.rule_pass:,}개가 LoQ 규칙이나 판정 길로 동등이 됐다.")
        if c is not None and c.n_items:
            q1 += (f" 만든 비교에서 DOE 를 LoQ 의 1.5배로 올리면 판정이 {c.at('final', 1.5).text()} 를 잡았다. "
                   "전부 통과시킨다면 이 비율은 0% 다.")
        if c is None or not c.n_items:
            q2 = q3 = self.check_line()
        else:
            q2 = (f"DOE 가 LoQ 위로 올라간 변화는 1.2×LoQ 에서 {c.at('final', 1.2).text()}, 2.0×LoQ 에서 "
                  f"{c.at('final', 2.0).text()} 를 판정이 잡았다. DOE 가 LoQ 아래에 머문 변화 (0.8×LoQ) 는 판정이 "
                  f"{c.at('final', 0.8).text()}, 재확인이 {c.at('review', 0.8).text()} 를 잡았다. LoQ 아래 변화는 판정 "
                  "규칙상 동등이고 재확인이 보는 곳이다.")
            rule, final = c.at("rule", 1.2), c.at("final", 1.2)
            if rule.rate - final.rate >= 0.05:
                q2 += (f" 1.2×LoQ 에서 2단계 LoQ 판정만 보면 {rule.text()} 다. 그 차이는 3단계 판정 길 (절대 허용폭 등) 이 "
                       "동등으로 둔 비교다.")
            q3 = (f"변화를 넣지 않은 비교에서 판정이 {c.at('final', NO_CHANGE).text()} 를 차이·미결로 걸었다. LoQ 규칙 "
                  f"없는 보통 TOST 였다면 {c.at('tost', NO_CHANGE).text()}, 재확인은 {c.at('review', NO_CHANGE).text()}. "
                  "실제 DOE 는 lot·조건 차이가 더해져 오경보가 이보다 많을 수 있다.")
        return [("한계 영역을 전부 통과시켰나?", q1), ("진짜 변한 것을 놓치나?", q2), ("안 변한 것을 걸리게 하나?", q3)]

    def sheets(self, label: Callable[[str], str], names: bool) -> list[tuple[str, pd.DataFrame, tuple[str, ...]]]:
        """엑셀 시트와 리포트 표 (이름, 표, 표 아래 메모). names=False 면 ITEM 이름 열을 빼고 ID 만."""
        out = [(SUMMARY, self._summary_table(), tuple(self.headline_lines())),
               (REASONS, self._reasons_table(), ("동등이 된 이유는 items.csv 의 판정 사유와 판정 길로 정했다.",))]
        if self.levels is not None:
            out.append((LEVELS_SHEET, self._levels_sheet(), (*METHOD_LINES, *BIAS_LINES)))
        out.append((ITEMS_SHEET, self._items_sheet(label, names), ("LoQ 규칙·판정 길로 동등인 ITEM 이 먼저, 그 안에서 "
                                                                   "재확인 확인 필요 먼저, 그다음 ×POR 큰 순.",)))
        return out

    def _summary_table(self) -> pd.DataFrame:
        g, c = self.summary.ledger, self.check
        rows = [("전체 ITEM", f"{g.n_total:,}"), ("LoQ 아래 ITEM", f"{g.n_zone:,}"),
                *((f"최종 {v}", f"{n:,}") for v, n in g.final.items()),
                *((f"동등 이유: {k}", f"{n:,}") for k, n in g.passes.items()),
                ("LoQ 규칙·판정 길로 동등", f"{g.rule_pass:,}"),
                *((f"그중 보통 TOST 였다면 {v}", f"{n:,}") for v, n in g.rule_tost.items()),
                ("그중 재확인 확인 필요", "-" if g.rule_flagged is None else f"{g.rule_flagged:,}"),
                ("LoQ 근처 (정량 구간, 따로 셈)", f"{g.n_near:,}")]
        if c is not None:
            rows += [("시험한 ITEM", f"{c.n_items:,}"), ("POR 회차 (ITEM 마다 비교 수)", f"{c.n_runs:,}"),
                     *((f"시험 못 함: {k}", f"{n:,}") for k, n in c.untested.items()),
                     *((f"{level_name(u)} 잡힘 ({MEASURE_NAMES[m]})", c.at(m, u).text())
                       for u, m in ((NO_CHANGE, "final"), (NO_CHANGE, "tost"), (NO_CHANGE, "review"), (0.8, "final"),
                                    (0.8, "review"), (1.2, "final"), (1.5, "final"), (2.0, "final"))),
                     ("DOE 잡음 비 중앙값", "-" if not math.isfinite(c.noise_ratio) else f"{c.noise_ratio:.2f}"),
                     ("DOE 잡음 비 > 1 인 ITEM", f"{c.n_noisy:,}")]
        return pd.DataFrame(rows, columns=["항목", "값"])

    def _reasons_table(self) -> pd.DataFrame:
        t = self.items
        zones = [z for z in LOQ_ZONE_NAMES if (t["zone"] == z).any()]
        rows = []
        for name, part in [*((z, t[t["zone"] == z]) for z in zones), ("전체", t)]:
            counts = part["pass_kind"].value_counts()
            rows.append({"구간": name, **{k: int(counts.get(k, 0)) for k in KIND_ORDER}, "합계": len(part)})
        return pd.DataFrame(rows, columns=["구간", *KIND_ORDER, "합계"])

    def _levels_sheet(self) -> pd.DataFrame:
        t = self.levels
        cols = {"수준": t["level_name"], "ITEM 수": t["n_items"], "비교 수": t["n_comparisons"]}
        for m, name in MEASURE_NAMES.items():
            col = "diff_final" if m == "diff" else f"caught_{m}"
            cols[f"{name} %"] = t[col].map(_pct)
            cols[f"{name} 90% 범위"] = [f"{_pct(a)}~{_pct(b)}" if math.isfinite(_f(a)) else "-"
                                       for a, b in zip(t[f"{col}_lo"], t[f"{col}_hi"])]
        return pd.DataFrame(cols)

    def _items_sheet(self, label: Callable[[str], str], names: bool) -> pd.DataFrame:
        t = self.items
        cols = {"ID": t["ITEM"].map(lambda i: label(str(i)))}
        if names:
            cols["ITEM"] = t["ITEM"]
        cols |= {"구간": t["zone"], "최종 판정": t["verdict_final"], "동등 이유": t["pass_kind"], "판정 길": t["route"],
                 "보통 TOST": t["verdict_tost"], "POR ×LoQ": t["por_loq"].map(_sig),
                 "DOE 구간 ×LoQ": [f"{_sig(a)}~{_sig(b)}" for a, b in zip(t["doe_lo_loq"], t["doe_hi_loq"])],
                 "재확인": t["review_flag"].map(lambda v: "확인 필요" if _yes(v) else ("-" if pd.isna(v) else "")),
                 "재확인 배수": t["review_ratio"].map(_sig)}
        if "tested" in t:
            cols |= {"변화 없음 잡힘": [f"{int(a)}/{int(b)}" if math.isfinite(_f(a)) else "-"
                                    for a, b in zip(t["null_caught"], t["n_runs"])],
                     "잡히는 수준 ×LoQ": t["catch_level"].map(_level),
                     "잡히는 수준 ×POR": t["catch_ratio"].map(_level),
                     "DOE 잡음 비": t["doe_noise_ratio"].map(_sig), "시험": t["tested"], "설명": t["why"]}
        return pd.DataFrame(cols).reset_index(drop=True)


SUMMARY, REASONS, LEVELS_SHEET, ITEMS_SHEET = "요약", "동등 이유", "시험(수준별)", "ITEM별"
MEASURE_NAMES = {"final": "판정", "rule": "2단계만", "tost": "보통 TOST", "review": "재확인", "diff": "판정 차이만"}
TIPS = {
    "수준": "만든 DOE 의 참 수준 (LoQ 의 몇 배). 변화 없음 = 회차 하나를 그대로 DOE 로 둔 비교",
    "ITEM 수": "그 수준에서 센 ITEM 수. ITEM 의 허용폭 Δ 보다 큰 변화만 셈 (변화 없음은 모든 ITEM)",
    "비교 수": "그 수준에서 센 회차 비교 수 (센 ITEM × POR 회차 수)",
    "판정 %": "최종 판정이 차이·미결인 비율 (ITEM 마다 회차 비교 중 비율, ITEM 끼리 평균)",
    "2단계만 %": "3단계 판정 길 없이 2단계 LoQ 판정만 본 잡힌 비율",
    "보통 TOST %": "LoQ 규칙 없이 같은 신뢰구간을 ±Δ 로 TOST 했을 때 차이·미결 비율",
    "재확인 %": "LoQ 재확인의 방향 기준 (BH q < 0.05, 배수 1/1.3~1.3 밖) 에 걸린 비율. 변화 없음과 머리 수준만",
    "판정 차이만 %": "최종 판정이 차이인 비율 (미결 뺌)",
    "동등 이유": "이동이 허용폭 안 = LoQ 규칙 없이도 동등, DOE 구간도 LoQ 아래·DOE 구간이 LoQ에 걸침 = LoQ 규칙으로 동등, "
               "판정 길 = 2단계는 차이·미결인데 3단계 판정 길이 동등",
    "보통 TOST": "LoQ 규칙 없이 같은 신뢰구간을 ±Δ 로 TOST 한 판정",
    "POR ×LoQ": "POR 중앙값 ÷ LoQ (부호 그대로)",
    "DOE 구간 ×LoQ": "(POR 중앙값 + 변화량 90% 신뢰구간) ÷ LoQ",
    "재확인": "실제 LoQ 재확인 (review/loq_review.csv) 의 확인 필요",
    "재확인 배수": "실제 LoQ 재확인의 DOE ÷ POR 배수 중앙값",
    "변화 없음 잡힘": "변화를 넣지 않은 회차 비교 중 판정이 차이·미결로 건 수 / 회차 수",
    "잡히는 수준 ×LoQ": "DOE 를 LoQ 의 이 배수 이상으로 올리면 회차 비교가 모두 잡힘. inf = 3배까지 아님",
    "잡히는 수준 ×POR": "같은 수준을 POR 중앙값의 배수로. POR 가 LoD 아래면 빈 칸",
    "DOE 잡음 비": "실제 DOE − POR 의 die 흔들림 ÷ 회차 비교의 die 흔들림. 1 보다 크면 이 ITEM 의 잡힘 숫자가 실제보다 좋게 나옴",
    "시험": "예, 또는 시험하지 못한 이유",
}


def _pct(v) -> str:
    x = _f(v)
    return f"{100 * x:.0f}%" if math.isfinite(x) else "-"


def _sig(v) -> str:
    x = _f(v)
    return f"{x:.3g}" if math.isfinite(x) else "-"


def _level(v) -> str:
    x = _f(v)
    return "inf" if math.isinf(x) else _sig(x)


def load(folder: str | Path) -> LoqBook:
    """<folder>/items.csv 로 동등이 된 이유를 세고, loq/ 가 있으면 시험 결과를, review/loq_review.csv 가 있으면 재확인
    결과를 더한다. loq/ 가 없으면 book.check 가 None."""
    folder = Path(folder)
    return _book(folder, review.read_items(folder / "items.csv"))


def _book(folder: Path, items: pd.DataFrame) -> LoqBook:
    rev = _read_review(folder)
    led = ledger_frame(items, rev)
    loq_dir = folder / LOQ_DIR
    table, levels, check = led, None, None
    if (loq_dir / ITEMS_CSV).is_file() and (loq_dir / LEVELS_CSV).is_file():
        tested = pd.read_csv(loq_dir / ITEMS_CSV, encoding="utf-8-sig", dtype={"ITEM": str, "tested": str},
                             keep_default_na=False, na_values=[""])
        levels = pd.read_csv(loq_dir / LEVELS_CSV, encoding="utf-8-sig")
        table = led.merge(tested[["ITEM", *(c for c in ITEM_COLS if c not in led.columns)]], on="ITEM", how="left")
        table = table.set_index("ITEM").loc[tested["ITEM"][tested["ITEM"].isin(table["ITEM"])]].reset_index()
        check = _check(table, levels)
    return LoqBook(folder, LoqSummary(_ledger(items, led, rev is not None), check), table, levels)


# ---------------------------------------------------------------- 그림 (ITEM 이름 없음)

DPI = 110


def curve_note(c: Check) -> str:
    return (f"변화 없음에서 판정이 잡은 비율 {_pct(c.at('final', NO_CHANGE).rate)} (보통 TOST "
            f"{_pct(c.at('tost', NO_CHANGE).rate)}). DOE 0.8×LoQ 에서 판정 {_pct(c.at('final', 0.8).rate)}, 재확인 "
            f"{_pct(c.at('review', 0.8).rate)}. DOE 1.5×LoQ 에서 판정 {_pct(c.at('final', 1.5).rate)}.")


def plot_curve(levels: pd.DataFrame, book: LoqBook, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5.2), layout="constrained")
    grid = levels[levels["level"] != NO_CHANGE]
    null = levels[levels["level"] == NO_CHANGE].iloc[0]
    x0 = -0.32
    ax.axvspan(0, 1, color="#eeeeee", zorder=0)
    ax.text(0.5, 103, "DOE가 LoQ 아래", ha="center", va="bottom", fontsize=9, color="#555555")
    ax.axvline(-0.13, color="#bbbbbb", lw=1)
    ax.fill_between(grid["level"], 100 * grid["caught_final_lo"], 100 * grid["caught_final_hi"], color="#0072B2",
                    alpha=0.15, lw=0)
    ax.plot(grid["level"], 100 * grid["caught_final"], color="#0072B2", lw=2.2, label="판정 (최종)")
    ax.plot(grid["level"], 100 * grid["caught_rule"], color="#56B4E9", lw=1.4, ls=":", label="2단계 LoQ 판정만")
    ax.plot(grid["level"], 100 * grid["caught_tost"], color="#777777", lw=1.6, ls="--", label="보통 TOST (LoQ 규칙 없음)")
    rv = grid[grid["level"].isin(HEADLINE)]
    ax.plot(rv["level"], 100 * rv["caught_review"], "o", color="#E69F00", ms=8, label="재확인 (방향)")
    marks = (("caught_final", "판정", "#0072B2", "s"), ("caught_tost", "보통 TOST", "#777777", "D"),
             ("caught_review", "재확인", "#E69F00", "o"))
    labels = []
    for dx, (col, name, color, marker) in zip((-0.07, 0.0, 0.07), marks):
        v = _f(null[col])
        if math.isfinite(v):
            ax.plot([x0 + dx], [100 * v], ls="none", marker=marker, ms=8, color=color, mec="white", mew=1.5)
            labels.append(f"{name} {_pct(v)}")
    ax.text(x0, 108, "\n".join(labels), ha="center", va="top", fontsize=8.5, color="#333333")
    ax.set_xlim(-0.5, 3.1)
    ax.set_ylim(-3, 112)
    ax.set_xticks([x0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0], ["변화\n없음", "0.5", "1", "1.5", "2", "2.5", "3"])
    ax.set_xlabel("만든 DOE 의 참 수준 (LoQ 의 몇 배)")
    ax.set_ylabel("잡힌 비율 (차이·미결, %)")
    ax.grid(axis="y", color="#e5e5e5")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    c = book.check
    ax.set_title(f"LoQ 아래 ITEM {c.n_items:,}개 × POR 회차 {c.n_runs}개로 만든 비교", fontsize=11, loc="left")
    add_figure_note(fig, CURVE_HOW_TO_READ, curve_note(c), dpi=DPI)
    return _save(fig, path)


def plot_reasons(table: pd.DataFrame, book: LoqBook, path: Path) -> Path:
    zones = [z for z in LOQ_ZONE_NAMES if (table["zone"] == z).any()]
    bars = [*((z, table[table["zone"] == z]) for z in zones), ("전체", table)]
    fig, ax = plt.subplots(figsize=(9, 1.3 + 0.55 * len(bars)), layout="constrained")
    for y, (name, part) in enumerate(reversed(bars)):
        counts = part["pass_kind"].value_counts()
        left = 0
        for k in KIND_ORDER:
            n = int(counts.get(k, 0))
            if not n:
                continue
            ax.barh(y, n, left=left, color=KIND_COLORS[k], edgecolor="white", linewidth=2, height=0.6)
            if n / max(len(table), 1) > 0.04:
                ax.text(left + n / 2, y, f"{n:,}", ha="center", va="center", fontsize=9, color="white")
            left += n
    ax.set_yticks(range(len(bars)), [name for name, _ in reversed(bars)])
    ax.set_xlabel("ITEM 수")
    ax.spines[["top", "right"]].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=KIND_COLORS[k]) for k in KIND_ORDER]
    fig.legend(handles, KIND_ORDER, loc="outside upper center", ncols=3, frameon=False, fontsize=9)
    add_figure_note(fig, REASONS_HOW_TO_READ, book.headline_lines()[1], dpi=DPI)
    return _save(fig, path)


def _save(fig, path: Path) -> Path:
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)
    return path


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LoQ 아래 ITEM 점검 (참고용, 판정은 그대로).")
    p.add_argument("--input", required=True, help="por_doe_compare.py 결과 items.csv")
    p.add_argument("--out", required=True, help="출력 폴더 (그 아래 loq/ 에 씀)")
    add_raw_args(p.add_argument_group("원데이터 (por_doe_compare.py 와 같은 인자)"))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not (args.por and args.doe):
        print("오류: 원데이터 --por 와 --doe 가 필요합니다.", file=sys.stderr)
        return 2
    run(args.input, args, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
