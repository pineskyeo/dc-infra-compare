"""ITEM 분류와 판정 길 (참고, 판정에 안 씀). verdict_final 은 그대로다.

ITEM 마다 POR 값만 보고 (DOE 는 보지 않는다) 종류를 정하고, 종류에 맞는 판정 길(route)을 고른다.
분류 축은 AXES 한 표에 있다. 축마다 (값, 조건) 규칙을 위에서부터 보고 처음 맞는 값을 쓴다 (cls_shape 만 맞는 값을 모두
';' 로 잇는다). 판정 길은 ROUTES 표에서 처음 맞는 것이다: 제외 → 한계 비교 → 절대 허용폭 → LoQ 판정 → log TOST → 선형 TOST.

  cls_valid       정상 / POR 만으로 본 판정 제외 원인 (EXCLUSION_CAUSES, 괄호 속 값 뺌) / die 부족
  cls_sign        부호 섞임 / 0 포함 / 양수만 / 음수만 (Open 코드 |x| ≥ 1E+90 는 뺌)
  cls_level       0 중심 (부호 섞임이고 |POR 중앙값| < LoQ) / 바닥 아래 (< LoQ) / 바닥 근처 (LoQ 근처) / 정량.
                  LoQ 는 POR 값만으로 다시 구한다 (판정의 LoQ 는 DOE 값의 분해능도 본다)
  cls_resolution  계단 (POR 값 분해능 step ≥ 0.1 Δ) / 연속
  cls_shape       두 덩어리 / 튀는 die / 한계에 걸림, 없으면 한 덩어리
  cls_noise       noise_pattern 그대로
  cls_scale       scales 표의 log·linear, 표가 없거나 auto 면 분류기 (spread_robust ≥ 0.3 이고 noise_slope ≥ 0.7 → log,
                  spread_robust < 0.3 이거나 기울기를 못 구하면 판별 불가, 그 밖은 linear)
  cls_run         회차 밀림 / 조건 불안정 / 회차 흔들림 / 안정

유형별 판정 (참고, verdict_typed): 1·2단계 = 기본 판정 verdict (선형 TOST, LoQ 아래는 <LoQ 보고 일치) 이 동등이면 그대로.
  아니면 3단계 = 판정 길의 판정: 한계 비교 verdict_limit, 절대 허용폭 verdict_abs, log TOST verdict_log, LoQ 판정 verdict,
  선형 TOST 는 바닥 근처면 verdict_with_accuracy (없으면 verdict), 아니면 verdict. 그 판정이 동등·차이·미결이 아니면
  (판정 제외·빈 칸: 절대 허용폭 값이 없는 등, 제외 길) 지금 판정 verdict_final 을 그대로 둔다 (log·장비 정확도 옵션 포함).
  verdict_typed_log_run 은 log TOST 길에 verdict_log_run (고친 log 허용폭) 을 쓴 것.

판정 길 참고 결과 (그 길의 ITEM 만 채운다):
  절대 허용폭  --abs-tol 파일 (group,abs_delta) 의 Δ 로 같은 신뢰구간(center, ci_low, ci_high)을 TOST → verdict_abs
  한계 비교    한계(POR 최댓값·최솟값에 붙은 값, Open 코드)에 걸린 die 비율 POR (회차 평균) 대 DOE, 정확 McNemar p,
               두 쪽 모두 한계 밖인 die 로 TOST → verdict_limit
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from scipy import stats

from infra_compare import read_pairs
from por_doe_compare import (CLASS_COLS, EXCLUSION_CAUSES, JUDGED, K_LOQ, MIN_DIE, NOISE_SPREAD_MIN,
                             NP_UNKNOWN, OUTLIER_K, SCALE_LINEAR, SCALE_LOG, SHAPE_EXCLUDE_ABS, ST_BIMODAL,
                             ST_RUN_JITTER, ST_UNSTABLE, V_EXCLUDED, ExclusionFacts, ci_median, limit_sigma, near_loq,
                             por_sides, robust_sigma, tost, zero_sides)

LIMIT_SHARE_MIN = 0.05       # 한계에 걸림: POR 값 중 최댓값(또는 최솟값)에 붙은 값이 이 비율 이상
LIMIT_POR_HALF = 0.5         # McNemar 에서 POR die 가 한계에 있다고 보는 회차 비율
SCALE_SLOPE_LOG = 0.7        # cls_scale 분류기: noise_slope ≥ 이 값이면 log (lab Q2, 거짓 log 1.4%)
RESOLUTION_STEP_MIN = 0.1    # 계단: POR 값 분해능 step ≥ 이 배수 × Δ (status 분해능 부족과 같은 배수)

V_OK, V_DIE_SHORT = "정상", "die 부족"
SIGN_MIXED, SIGN_ZERO, SIGN_POS, SIGN_NEG, SIGN_NONE = "부호 섞임", "0 포함", "양수만", "음수만", "값 없음"
LEVEL_ZERO, LEVEL_BELOW, LEVEL_NEAR, LEVEL_QUANT = "0 중심", "바닥 아래", "바닥 근처", "정량"
RES_STEP, RES_CONT = "계단", "연속"
SHAPE_BIMODAL, SHAPE_OUTLIER, SHAPE_LIMIT, SHAPE_ONE = "두 덩어리", "튀는 die", "한계에 걸림", "한 덩어리"
SCALE_UNKNOWN = "판별 불가"
RUN_SHIFT, RUN_UNSTABLE, RUN_JITTER, RUN_OK = "회차 밀림", "조건 불안정", "회차 흔들림", "안정"
R_EXCLUDED, R_LIMIT, R_ABS, R_LOQ, R_LOG, R_LINEAR = "제외", "한계 비교", "절대 허용폭", "LoQ 판정", "log TOST", "선형 TOST"


@dataclass(frozen=True)
class Facts:
    """분류가 보는 값. 분류 축은 POR 값과 판정 결과의 POR 쪽 값만 쓴다. limit 은 한계 비교 참고 결과 (DOE 도 씀)."""
    n_die: int
    causes: tuple[str, ...]      # POR 만으로 본 판정 제외 원인
    has_pos: bool
    has_neg: bool
    has_zero: bool
    por_median: float
    loq: float                   # POR 값만으로 구한 LoQ
    r: float
    step: float                  # POR 값 고유값 이웃 차의 최솟값
    delta: float
    bimodal: bool                # status 두 덩어리 (POR die 평균의 log 분포)
    n_outlier: int               # 한계 밖 POR die 평균이 중앙값에서 OUTLIER_K × robust σ 넘게 떨어진 die 수
    at_limit: bool
    noise_pattern: str
    spread: float
    noise_slope: float
    status: frozenset[str]
    table_scale: str = ""        # scales 표의 log·linear (ITEM 그룹이 표에 있을 때), 아니면 ""
    run_shift: bool = False      # 이 ITEM 이 밀린 POR 회차를 따라 움직임
    limit: Mapping | None = None


def _always(f: Facts) -> bool:
    return True


@dataclass(frozen=True)
class Axis:
    column: str
    title: str                   # 그림의 쉬운 이름
    rules: tuple[tuple[str | Callable[[Facts], str], Callable[[Facts], bool]], ...]     # (값, 조건)
    multi: bool = False          # 맞는 값 모두를 ';' 로. 하나도 없으면 default
    default: str = ""

    def value(self, f: Facts) -> str:
        hits = (v(f) if callable(v) else v for v, ok in self.rules if ok(f))
        if self.multi:
            return ";".join(hits) or self.default
        return next(hits)

    @property
    def known(self) -> tuple[str, ...]:
        """규칙에 적힌 값 (표 순서). 그림·counts.csv 순서에 쓴다."""
        return tuple(v for v, _ in self.rules if isinstance(v, str)) + ((self.default,) if self.default else ())


def _mixed(f: Facts) -> bool:
    return f.has_pos and f.has_neg


def _below(f: Facts) -> bool:
    return abs(f.por_median) < f.loq


AXES: tuple[Axis, ...] = (
    Axis("cls_valid", "판정할 수 있나", (
        (V_DIE_SHORT, lambda f: f.n_die < MIN_DIE),
        (lambda f: ";".join(f.causes), lambda f: bool(f.causes)),
        (V_OK, _always))),
    Axis("cls_sign", "값의 부호", (
        (SIGN_MIXED, _mixed),
        (SIGN_ZERO, lambda f: f.has_zero),
        (SIGN_POS, lambda f: f.has_pos),
        (SIGN_NEG, lambda f: f.has_neg),
        (SIGN_NONE, _always))),
    Axis("cls_level", "값의 높이 (LoQ 대비)", (
        (LEVEL_ZERO, lambda f: _mixed(f) and _below(f)),
        (LEVEL_BELOW, _below),
        (LEVEL_NEAR, lambda f: near_loq(f.por_median, f.loq, f.r)),
        (LEVEL_QUANT, _always))),
    Axis("cls_resolution", "값이 계단인가", (
        (RES_STEP, lambda f: f.step >= RESOLUTION_STEP_MIN * f.delta),
        (RES_CONT, _always))),
    Axis("cls_shape", "분포 모양", (
        (SHAPE_BIMODAL, lambda f: f.bimodal),
        (SHAPE_OUTLIER, lambda f: f.n_outlier > 0),
        (SHAPE_LIMIT, lambda f: f.at_limit)), multi=True, default=SHAPE_ONE),
    Axis("cls_noise", "잡음 모양", (
        (lambda f: f.noise_pattern or NP_UNKNOWN, _always),)),
    Axis("cls_scale", "척도", (
        (lambda f: f.table_scale, lambda f: bool(f.table_scale)),
        (SCALE_UNKNOWN, lambda f: not (f.spread >= NOISE_SPREAD_MIN and np.isfinite(f.noise_slope))),
        (SCALE_LOG, lambda f: f.noise_slope >= SCALE_SLOPE_LOG),
        (SCALE_LINEAR, _always))),
    Axis("cls_run", "POR 회차", (
        (RUN_SHIFT, lambda f: f.run_shift),
        (RUN_UNSTABLE, lambda f: ST_UNSTABLE in f.status),
        (RUN_JITTER, lambda f: ST_RUN_JITTER in f.status),
        (RUN_OK, _always))),
)

ROUTE_TITLE = "판정 길"
# 판정 길. 위에서부터 처음 맞는 것. c 는 분류 값 (AXES 열 → 값)
ROUTES: tuple[tuple[str, Callable[[Mapping[str, str]], bool]], ...] = (
    (R_EXCLUDED, lambda c: c["cls_valid"] != V_OK),
    (R_LIMIT, lambda c: SHAPE_LIMIT in c["cls_shape"].split(";")),
    (R_ABS, lambda c: c["cls_level"] == LEVEL_ZERO
     or (c["cls_resolution"] == RES_STEP and c["cls_level"] in (LEVEL_QUANT, LEVEL_NEAR))),
    (R_LOQ, lambda c: c["cls_level"] == LEVEL_BELOW),
    (R_LOG, lambda c: c["cls_scale"] == SCALE_LOG and c["cls_sign"] in (SIGN_POS, SIGN_NEG)),
    (R_LINEAR, lambda c: True),
)
ROUTE_NAMES = tuple(name for name, _ in ROUTES)
CLS_COLS = tuple(a.column for a in AXES)
RESULT_COLS = CLASS_COLS[len(CLS_COLS) + 1:]       # route 뒤 참고 결과 열


B_BASE, B_ACCURACY, B_KEEP = "1·2단계 동등", "선형 TOST · 장비 정확도", "지금 판정 (판정 길이 판정 못 함)"


def typed_verdict(row: Mapping, log_col: str = "verdict_log") -> tuple[str, str]:
    """(verdict_typed, typed_basis). row 는 판정 열 + 분류 열 + 판정 길 참고 결과. 규칙은 모듈 설명의 유형별 판정."""
    if str(row.get("verdict", "")) == "동등":
        return "동등", B_BASE
    route = row.get("route")
    near = [("verdict_with_accuracy", B_ACCURACY)] if row.get("cls_level") == LEVEL_NEAR else []
    tries = {R_LIMIT: [("verdict_limit", R_LIMIT)], R_ABS: [("verdict_abs", R_ABS)], R_LOG: [(log_col, R_LOG)],
             R_LOQ: [("verdict", R_LOQ)], R_LINEAR: [*near, ("verdict", R_LINEAR)]}.get(route, [])
    for col, basis in tries:
        v = row.get(col)
        if isinstance(v, str) and v in JUDGED:
            return v, basis
    return str(row.get("verdict_final", row.get("verdict", ""))), B_KEEP


def classify(f: Facts) -> dict[str, str]:
    """AXES 값과 route."""
    c = {a.column: a.value(f) for a in AXES}
    c["route"] = next(name for name, hit in ROUTES if hit(c))
    return c


# ---------------------------------------------------------------- ITEM 하나의 사실 (판정 작업자에서)

def _open(v: np.ndarray) -> np.ndarray:
    """Open 코드 등 (|x| ≥ 1E+90, NaN·inf 포함)."""
    return ~(np.abs(v) < SHAPE_EXCLUDE_ABS)


def limit_bounds(Y: np.ndarray) -> tuple[float, float]:
    """(아래 한계, 위 한계). Open 코드를 뺀 POR 값 중 최솟값·최댓값에 붙은 값이 LIMIT_SHARE_MIN 이상이면 그 값,
    아니면 −inf·+inf."""
    x = Y[~_open(Y)]
    if x.size == 0:
        return -np.inf, np.inf
    lo, hi = float(x.min()), float(x.max())
    return (lo if (x == lo).mean() >= LIMIT_SHARE_MIN else -np.inf,
            hi if (x == hi).mean() >= LIMIT_SHARE_MIN else np.inf)


def at_limit(v: np.ndarray, bounds: tuple[float, float]) -> np.ndarray:
    """한계에 걸린 값: Open 코드이거나 아래 한계 이하·위 한계 이상."""
    return _open(v) | (v <= bounds[0]) | (v >= bounds[1])


def _por_causes(Y: np.ndarray, res: Mapping, loq: float) -> tuple[str, ...]:
    """POR 만으로 본 판정 제외 원인. DOE 자리에 POR 값 전부를 넣어 같은 원인 표(EXCLUSION_CAUSES)를 쓰고,
    중심·신뢰구간은 POR die 평균의 중앙값과 부호검정 구간이다."""
    center, lo, hi = ci_median(Y.mean(axis=1))
    facts = ExclusionFacts(Y, Y.ravel(), center, lo, hi, res["sigma_die"], res["sigma_run"], res["por_median"],
                           res["delta"], loq, zero_sides(por_sides(Y)))
    found = (cause(facts) for cause in EXCLUSION_CAUSES)
    return tuple(re.sub(r" \([^)]*\)", "", c) for c in found if c)


def por_loq(Y: np.ndarray, res: Mapping) -> float:
    """판정의 LoQ 와 같은 식을 POR 값만으로: K_LOQ × max(sigma_die, POR 값 분해능 / √12, 장비 분해능 / √12),
    blank LoQ 가 더 크면 그 값."""
    loq = K_LOQ * limit_sigma(res["sigma_die"], np.unique(Y), res.get("spec_resolution", 0.0))[0]
    blank = float(res.get("blank_LoQ_item", np.nan))
    return blank if blank > loq else loq


def _n_outlier(v: np.ndarray) -> int:
    """POR die 평균 v 가 몸통에서 OUTLIER_K × robust σ 넘게 떨어진 die 수. 부호가 하나이고 0 이 없으면 log10|값| 에서 본다.
    v 는 한계 밖 die 만 (한계에 몰린 값이 robust σ 를 줄이지 않게)."""
    if v.size and ((v > 0).all() or (v < 0).all()):
        v = np.log10(np.abs(v))
    rs = robust_sigma(v) if v.size else 0.0
    return int((np.abs(v - np.median(v)) > OUTLIER_K * rs).sum()) if rs > 0 else 0


def por_facts(Y: np.ndarray, res: Mapping, r: float) -> Facts:
    """분류 사실. Y = die × POR 회차 값, res = judge_item 결과 행 (POR 쪽 값만 읽는다: sigma_die, sigma_run,
    por_median, delta, spec_resolution, blank_LoQ_item, status 의 두 덩어리·회차 흔들림·조건 불안정, noise_pattern,
    spread_robust, noise_slope). DOE 값은 받지 않는다."""
    Y = np.asarray(Y, float)
    loq = por_loq(Y, res)
    vals = np.unique(Y)
    x = Y[~_open(Y)]
    status = frozenset(p.strip() for p in str(res.get("status", "")).split(";"))
    bounds = limit_bounds(Y)
    off = ~at_limit(Y, bounds).any(axis=1)
    return Facts(
        n_die=Y.shape[0], causes=_por_causes(Y, res, loq),
        has_pos=bool((x > 0).any()), has_neg=bool((x < 0).any()), has_zero=bool((x == 0).any()),
        por_median=float(res["por_median"]), loq=loq, r=r,
        step=float(np.diff(vals).min()) if vals.size > 1 else np.nan, delta=float(res["delta"]),
        bimodal=ST_BIMODAL in status, n_outlier=_n_outlier(Y[off].mean(axis=1)),
        at_limit=bool(not off.all()),
        noise_pattern=str(res.get("noise_pattern", "") or ""), spread=float(res.get("spread_robust", np.nan)),
        noise_slope=float(res.get("noise_slope", np.nan)), status=status)


def limit_compare(Y: np.ndarray, z: np.ndarray, delta: float) -> dict:
    """한계 비교 참고 결과. POR die 의 한계 비율 = 한계에 걸린 회차 비율, limit_share_por 는 그 die 평균 (= 회차마다
    한계 die 비율의 평균). limit_p = 정확 McNemar (POR 은 회차 절반 이상 한계면 한계): 엇갈린 die 중 한쪽 수의
    양측 이항검정 p, 엇갈린 die 가 없으면 1. verdict_limit = POR 모든 회차와 DOE 가 모두 한계 밖인 die 의
    d = DOE − POR 회차 평균으로 중앙값 TOST (Δ = 판정의 Δ). 그런 die 가 MIN_DIE 개 미만이면 미결."""
    bounds = limit_bounds(Y)
    por_at, doe_at = at_limit(Y, bounds), at_limit(z, bounds)
    die_share = por_at.mean(axis=1)
    por_bin = die_share >= LIMIT_POR_HALF
    b, c = int((por_bin & ~doe_at).sum()), int((~por_bin & doe_at).sum())
    p = float(stats.binomtest(min(b, c), b + c, 0.5).pvalue) if b + c else 1.0
    off = ~por_at.any(axis=1) & ~doe_at
    n_off = int(off.sum())
    out = {"limit_share_por": float(die_share.mean()), "limit_share_doe": float(doe_at.mean()), "limit_p": p}
    if n_off < MIN_DIE:
        return {**out, "verdict_limit": "미결", "route_note": f"한계 밖 die {n_off}개 (< {MIN_DIE})"}
    if not delta > 0:
        return {**out, "verdict_limit": V_EXCLUDED, "route_note": f"Δ가 0 이하이거나 유효하지 않음 (Δ={delta:.4g})"}
    center, lo, hi = ci_median(z[off] - Y[off].mean(axis=1))
    verdict, why = tost(center, lo, hi, delta)
    return {**out, "verdict_limit": verdict, "route_note": f"한계 밖 die {n_off}개: {why}"}


def item_facts(Y: np.ndarray, z: np.ndarray, res: Mapping, r: float) -> Facts:
    """por_facts, 그리고 한계에 걸린 ITEM 이면 limit_compare 결과를 limit 에 붙인다."""
    f = por_facts(Y, res, r)
    return replace(f, limit=limit_compare(np.asarray(Y, float), np.asarray(z, float), f.delta)) if f.at_limit else f


# ---------------------------------------------------------------- items.csv 열 (판정 뒤)

def read_abs_tol(path) -> dict[str, float]:
    """group,abs_delta 파일 → 그룹 → abs_delta. 숫자가 아니거나 0 이하면 종료."""
    t = read_pairs(path, ("group", "abs_delta"))
    value = pd.to_numeric(t["abs_delta"], errors="coerce")
    bad = t.loc[~(value > 0), "group"].tolist()
    if bad:
        raise SystemExit(f"{path}: abs_delta 는 0보다 큰 숫자여야 합니다 (그룹 {', '.join(map(str, bad[:5]))})")
    return dict(zip(t["group"], value.astype(float)))


def abs_result(row: Mapping, group: str | None, abs_tol: Mapping[str, float] | None) -> dict:
    """절대 허용폭 참고 판정: 판정의 신뢰구간 (center, ci_low, ci_high) 을 Δ = abs_delta 로 TOST."""
    if abs_tol is None:
        return {"route_note": "--abs-tol 파일 없음"}
    if group is None:
        return {"route_note": "ITEM 그룹 없음 (--groups 에 없음)"}
    if group not in abs_tol:
        return {"route_note": f"--abs-tol 에 그룹 {group} 없음"}
    d = abs_tol[group]
    center, lo, hi = (float(row.get(k, np.nan)) for k in ("center", "ci_low", "ci_high"))
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return {"abs_delta": d, "route_note": "신뢰구간 없음"}
    verdict, why = tost(center, lo, hi, d)
    return {"abs_delta": d, "verdict_abs": verdict, "route_note": why}


def shifted_items(wide: pd.DataFrame, por_cols: list[str], sigma_die: pd.Series) -> set[str]:
    """밀린 POR 회차(stability runs.csv 의 flagged)를 따라 움직인 ITEM: 그 회차의 ITEM 점수가 회차 점수와 부호가 같고
    |점수| ≥ RUN_SCORE_MIN. 밀린 회차가 없으면 빈 집합."""
    import stability
    per_item = stability.item_run_scores(wide, por_cols, sigma_die)
    runs = stability.run_table(per_item, por_cols)
    hit = runs[runs["flagged"]]
    if hit.empty:
        return set()
    run, score = hit["run"].iloc[0], float(hit["score"].iloc[0])
    col = per_item[run]
    return set(per_item.index[(np.sign(col) == np.sign(score)) & (col.abs() >= stability.RUN_SCORE_MIN)])


def add_columns(res: pd.DataFrame, facts: Mapping[str, Facts], wide: pd.DataFrame, por_cols: list[str],
                group_of: Mapping[str, str] | None, abs_tol: Mapping[str, float] | None) -> pd.DataFrame:
    """res (판정 결과, scale 열 있음) 끝에 CLASS_COLS 를 붙인다. 판정 열은 건드리지 않는다."""
    shifted = shifted_items(wide, por_cols, res.set_index("ITEM")["sigma_die"].astype(float))
    rows = []
    for row in res.to_dict("records"):
        item = row["ITEM"]
        scale = str(row.get("scale", ""))
        f = replace(facts[item], table_scale=scale if scale in (SCALE_LOG, SCALE_LINEAR) else "",
                    run_shift=item in shifted)
        c = classify(f)
        out = {**dict.fromkeys(RESULT_COLS, np.nan), "route_note": ""}
        if c["route"] == R_ABS:
            out.update(abs_result(row, (group_of or {}).get(str(item).strip()), abs_tol))
        elif c["route"] == R_LIMIT and f.limit is not None:
            out.update(f.limit)
        full = {**row, **c, **out}
        out["verdict_typed"], out["typed_basis"] = typed_verdict(full)
        out["verdict_typed_log_run"] = typed_verdict(full, "verdict_log_run")[0]
        rows.append({**c, **out})
    return pd.concat([res.reset_index(drop=True), pd.DataFrame(rows, columns=list(CLASS_COLS))], axis=1)


def route_counts(route: pd.Series) -> str:
    """판정 길별 ITEM 수 ("제외 1, 한계 비교 0, ...")."""
    n = route.value_counts()
    return ", ".join(f"{name} {int(n.get(name, 0)):,}" for name in ROUTE_NAMES)


def takeaway(res: pd.DataFrame) -> str:
    return f"ITEM 분류 (참고, 판정 불변) 판정 길: {route_counts(res['route'])}"
