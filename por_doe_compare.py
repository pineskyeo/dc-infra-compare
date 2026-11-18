"""POR 여러 회(같은 die 재측정) + DOE 1회로 ITEM별 동등성을 판정한다. t-test도 같이 낸다.

모든 기준은 실행 전에 정해지는 값이고, 데이터를 보고 바뀌는 문턱값은 없다.

흔들림 (POR 회차 반복, NIST e-Handbook 2.4.4의 die·회차 분리를 robust 통계로)
  sigma_die : 같은 die를 다시 잰 1회 측정 흔들림. 이웃 회차 차이의 robust σ / √2
  sigma_run : 회차마다 전체가 같이 움직이는 크기 (컨택 상태, 온도 등). 회차별 중앙값으로
  튀는 die가 있어도 부풀지 않는다. 비교용 분산분석 값은 sigma_die_anova, sigma_run_anova 열.

구간 (Currie / IUPAC): LoD = 3.29 σ, LoQ = 10 σ, |POR 중앙값| 기준
  σ = max(sigma_die, 분해능 / √12). 분해능 = 측정값 사이의 가장 작은 간격 (계단값, GUM F.2.2.1)
  UNIT 열은 판정에 쓰지 않는다 (결과 표시용으로만 옮긴다).
  --level ITEM,LEVEL (실제 측정값 자릿수, 예 10fA = 10~100 fA)이 있으면 P9001A Per-pin SMU 사양을 ITEM 단위로 바꿔 쓴다.
  level.csv 열: ITEM, LEVEL, CALCVAL(파일 값 = 원측정값 × CALCVAL), DERIVED(Y = 여러 측정을 조합·추출한 변형 값).
  변형 값: 장비 사양·blank 안 씀.  CALCVAL 있음: 실제 값 = |POR 중앙값| / CALCVAL로 정확히 환산, blank 사용.
  CALCVAL 없음: 실제 값 = 자릿수 상한 10L로 보수적 환산, blank 안 씀.  분해능 하한은 항상, 정확도 하한은 --accuracy 일 때.
  --blank 를 주면 blank 한계(|μ| + 3.29 SD, |μ| + 10 SD)가 더 클 때 그쪽을 씀 (하한). blank는 원측정값이라
  level.csv 에서 변형이 아니고 CALCVAL이 있는 ITEM에만 × CALCVAL 해서 쓴다.

두 구간 모두 같은 TOST 규칙. 비교하는 양만 다르다.
  정량 (|POR| ≥ LoQ)  : die별 d = DOE − POR 회차 평균
                         허용폭 Δ = r × |POR 중앙값| + t(0.95, J−1) × √(1 + 1/J) × sigma_run
  LoQ 미만             : die별 "|값| ≥ LoQ" 여부(0/1). d = DOE 여부 − POR 회차 평균 여부
                         허용폭 Δ = det_margin + t(0.95, J−1) × √(1 + 1/J) × sigma_run(여부)
  t(0.95, J−1) × √(1 + 1/J) × sigma_run : 같은 프로그램으로 다시 재도 생기는 회차 간 차이 (DOE 1회 vs POR J회 평균의
  90% 예측구간 한쪽). sigma_run 의 자유도가 J − 1이라 t를 쓴다 (J = 3: 2.92, J = 5: 2.13).
  LoQ 미만은 값을 "<LoQ"로 보고하므로(IUPAC), 넘는 비율의 신뢰구간이 통째로 ±Δ 밖이고 die 중심 이동(값 척도,
  Hodges–Lehmann)도 POR 회차 흔들림 예측구간(r × |POR| + t × √(1 + 1/J) × sigma_run) 밖일 때만 차이. 그 밖은 동등.
  TOST 그대로의 판정은 verdict_tost_low 열. --strict-low-tost 면 TOST 그대로 판정.

90% 신뢰구간 (shift)
  hl   (기본): Hodges–Lehmann 추정 + Wilcoxon 부호순위 신뢰구간. 분포 가정 없음, 튀는 die에 강함
  mean       : 평균 + t 신뢰구간 (NIST 7.3.1.1)
  LoQ 미만의 0/1 비교는 항상 mean (비율 차이)

판정: 신뢰구간이 ±Δ 안 → 동등 / 통째로 밖 → 차이 / 걸침 → 미결 (해상도 부족: 신뢰구간 반폭 ≥ Δ, 그 외 경계)
t-test (NIST 7.3.1.1): 평균 d가 0인지. 참고용이며 판정에 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from infra_compare import blank_limits, load_blank, load_side, read_csv_auto

Z90 = 1.645
K_LOD, K_LOQ = 3.29, 10.0
MIN_DIE = 10
OUTLIER_K = 5.0
ORDER = {"차이": 0, "미결": 1, "동등": 2}
# Keysight P9001A Per-pin SMU (P9001 Data sheet p.6-7 측정 분해능·측정 정확도, Programming Reference Table 2-19/2-22
# auto range 상한). measure_i/measure_v 를 auto range(range=0)로 쓰면 값이 들어가는 가장 작은 range를 쓴다.
# 행: (공칭 range, auto range 상한, 측정 분해능, a = 읽음 비율, b = range 비율, c = 절대값)
# 정확도 ±(a × |값| + b × range + c). 사양의 Vo(출력 전압)·Rres×Io 항은 알 수 없어 0으로 둔다 (정확도를 작게 잡는 쪽).
I_RANGES = [
    (10e-12, 11.5e-12, 0.1e-15, 0.04, 0.05, 0.5e-12),
    (100e-12, 115e-12, 1e-15, 0.01, 0.01, 3e-12),
    (1e-9, 1.15e-9, 1e-15, 0.01, 0.001, 3e-12),
    (10e-9, 11.5e-9, 10e-15, 0.01, 0.001, 3e-12),
    (100e-9, 115e-9, 100e-15, 0.002, 0.0005, 0.0),
    (1e-6, 1.15e-6, 1e-12, 0.002, 0.0005, 0.0),
    (10e-6, 11.5e-6, 10e-12, 0.001, 0.0005, 0.0),
    (100e-6, 115e-6, 100e-12, 0.001, 0.0005, 0.0),
    (1e-3, 1.15e-3, 1e-9, 0.001, 0.0005, 0.0),
    (10e-3, 11.5e-3, 10e-9, 0.001, 0.0005, 0.0),
    (100e-3, 115e-3, 100e-9, 0.001, 0.0005, 0.0),
]
V_RANGES = [
    (2.0, 2.2, 2e-6, 0.0004, 0.0004, 0.0),
    (10.0, 10.0, 10e-6, 0.0004, 0.0004, 0.0),
    (20.0, 22.0, 1e-3, np.nan, np.nan, np.nan),     # 10 V 넘으면 Shared SMU. 정확도는 표에 넣지 않음
    (40.0, 44.0, 2e-3, np.nan, np.nan, np.nan),
    (100.0, 100.0, 5e-3, np.nan, np.nan, np.nan),
]
PREFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6}
LEVEL_RE = re.compile(r"^\s*([0-9.]+)\s*([fpnuµmkKM]?)\s*(A|V|F|HZ)\s*$", re.I)
SI = [(1e-15, "f"), (1e-12, "p"), (1e-9, "n"), (1e-6, "u"), (1e-3, "m"), (1.0, "")]


@dataclass(frozen=True)
class ItemInfo:
    """level.csv 한 줄. 실제 측정값 |값|의 자릿수가 [L, 10L), 측정 종류 kind (A, V, F, Hz).
    calcval: 파일 값 = 원측정값 × CALCVAL (모르면 None). derived: 여러 측정을 조합·추출한 값이라 원측정값의 배율이 아님."""
    L: float
    kind: str
    calcval: float | None
    derived: bool


def parse_level(text) -> tuple[float, str] | None:
    """'10fA' → (1e-14, 'A'). 실제 측정값 |값|이 [L, 10L) 자릿수라는 뜻."""
    m = LEVEL_RE.match(str(text))
    if not m:
        return None
    kind = {"a": "A", "v": "V", "f": "F", "hz": "Hz"}[m[3].lower()]
    return float(m[1]) * PREFIX[m[2]], kind


def smu_row(kind: str, phys: float):
    for row in {"A": I_RANGES, "V": V_RANGES}.get(kind, []):
        if phys <= row[1]:
            return row
    return None


def range_name(row, kind: str) -> str:
    if row is None:
        return ""
    f, pre = max(((f, p) for f, p in SI if f <= row[0] * 1.0001), default=(1.0, ""))
    return f"{row[0] / f:g}{pre}{kind}"


def spec_terms(info: ItemInfo | None, level: float, doe_level: float) -> dict:
    """장비 사양을 ITEM 단위로 바꾼다. 변형 값은 원측정값의 배율이 아니라 쓰지 않는다.
    CALCVAL이 있으면 실제 값 = level / CALCVAL 로 정확히, 없으면 실제 값 = 자릿수 상한 10L (허용폭을 가장 작게 잡는 쪽)."""
    if info is None:
        return {}
    kind = info.kind
    if level <= 0 and not info.derived:
        return {"level_kind": kind, "spec_status": "POR 값 0: 환산 불가"}
    if info.derived:
        return {"level_kind": kind, "spec_status": "변형: 장비 사양 미적용"}
    if info.calcval:
        k = abs(info.calcval)        # 부호를 뒤집는 CALCVAL(음수)도 크기 환산은 절댓값으로
        phys = level / k
        # 자릿수 경계 근처(9.6 nA를 10nA로 적은 경우)는 auto range가 겹치는 1.15배까지 일치로 본다
        check = ("일치" if info.L / 1.15 <= phys < 11.5 * info.L
                 else f"불일치 (CALCVAL로 본 실제 값 {phys:.3g}, LEVEL {info.L:.3g}~{10 * info.L:.3g})")
        status = "CALCVAL로 환산"
    else:
        phys = 10 * info.L
        k = level / phys
        check, status = "", "자릿수 상한으로 환산"
    phys_d = phys * doe_level / level
    rp, rd = smu_row(kind, phys), smu_row(kind, phys_d)
    out = {"level_kind": kind, "spec_status": status, "level_check": check,
           "range_por": range_name(rp, kind), "range_doe": range_name(rd, kind),
           "range_changed": bool(rp and rd and rp[0] != rd[0])}
    if rp:
        out["spec_resolution"] = rp[2] * k
    if rp and rd and np.isfinite(rp[3]) and np.isfinite(rd[3]):
        u_p = rp[3] * phys + rp[4] * rp[0] + rp[5]
        u_d = rd[3] * phys_d + rd[4] * rd[0] + rd[5]
        # 두 측정이 각자 사양 정확도 안에 있을 때 생길 수 있는 차이 (균일분포 → 표준불확도 U/√3, GUM 4.3.7)
        out["accuracy_margin"] = Z90 * np.sqrt((u_p ** 2 + u_d ** 2) / 3) * k
    return out


def robust_sigma(x: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def run_anova(Y: np.ndarray) -> tuple[float, float]:
    """die × 회차 이원분산분석 (상호작용 없음). (sigma_die, sigma_run)."""
    n, J = Y.shape
    g = Y.mean()
    die_m, run_m = Y.mean(axis=1), Y.mean(axis=0)
    resid = Y - die_m[:, None] - run_m[None, :] + g
    ms_e = float((resid ** 2).sum() / ((n - 1) * (J - 1)))
    ms_run = float(n * ((run_m - g) ** 2).sum() / (J - 1))
    return float(np.sqrt(ms_e)), float(np.sqrt(max(0.0, (ms_run - ms_e) / n)))


def robust_noise(Y: np.ndarray) -> tuple[float, float]:
    """튀는 die에 끌려가지 않는 (sigma_die, sigma_run).
    sigma_die: 이웃 회차 차이(2−1, 3−2 …)를 회차쌍마다 중앙값으로 맞춘 뒤 모아서 robust σ / √2
    sigma_run: die별 평균을 뺀 값의 회차별 중앙값들의 분산에서 die 잡음 몫((π/2) sigma_die² / n)을 뺀 것"""
    n, J = Y.shape
    dd = []
    for k in range(J - 1):
        x = Y[:, k + 1] - Y[:, k]
        dd.append(x - np.median(x))
    s_die = robust_sigma(np.concatenate(dd)) / np.sqrt(2)
    r = np.median(Y - Y.mean(axis=1, keepdims=True), axis=0)
    s_run = float(np.sqrt(max(0.0, r.var(ddof=1) - (np.pi / 2) * s_die ** 2 / n)))
    return s_die, s_run


def run_factor(J: int) -> float:
    """DOE 1회가 POR J회 평균과 같은 프로그램 안에서 다를 수 있는 폭의 배수 (90% 예측구간 한쪽).
    sigma_run 은 회차 J개로 추정해서 자유도가 J − 1뿐이라 1.645 대신 t(0.95, J − 1)를 쓴다 (J = 3이면 2.92)."""
    return float(stats.t.ppf(0.95, J - 1) * np.sqrt(1 + 1 / J))


def paired_t_p(d: np.ndarray) -> float:
    s = d.std(ddof=1)
    if s == 0:
        return 1.0 if d.mean() == 0 else 0.0
    t = d.mean() / (s / np.sqrt(len(d)))
    return float(2 * stats.t.sf(abs(t), len(d) - 1))


def ci_mean(d: np.ndarray) -> tuple[float, float, float]:
    n = len(d)
    c = float(d.mean())
    h = float(stats.t.ppf(0.95, n - 1) * d.std(ddof=1) / np.sqrt(n))
    return c, c - h, c + h


def ci_hl(d: np.ndarray) -> tuple[float, float, float]:
    """Hodges–Lehmann 추정과 Wilcoxon 부호순위 90% 신뢰구간 (정규 근사 임계값, Hollander & Wolfe)."""
    n = len(d)
    i, j = np.triu_indices(n)
    w = np.sort((d[i] + d[j]) / 2)
    k = int(np.floor(n * (n + 1) / 4 - Z90 * np.sqrt(n * (n + 1) * (2 * n + 1) / 24)))
    k = max(k, 0)
    return float(np.median(w)), float(w[k]), float(w[len(w) - 1 - k])


def tost(center: float, lo: float, hi: float, delta: float, fmt=lambda v: f"{v:+.4g}") -> tuple[str, str]:
    h = (hi - lo) / 2
    if -delta <= lo and hi <= delta:
        return "동등", "90% 신뢰구간이 ±Δ 안"
    if lo > delta or hi < -delta:
        return "차이", f"shift {fmt(center)}가 ±Δ({abs(delta):.4g}) 밖"
    if h >= delta:
        return "미결", "해상도 부족 (신뢰구간 반폭 ≥ Δ)"
    return "미결", "경계 (신뢰구간이 Δ에 걸침)"


def judge(Y: np.ndarray, z: np.ndarray, a: argparse.Namespace,
          blank_lim: tuple[float, float] | None = None, info: ItemInfo | None = None) -> tuple[dict, np.ndarray]:
    """blank_lim = blank 원측정값으로 구한 (LoD, LoQ). blank는 실제 측정값(A, V)이고 결과 값은 가공됐을 수 있어서
    변형이 아니고 CALCVAL(파일 값 = 원측정값 × CALCVAL)이 있는 ITEM만 ITEM 단위로 바꿔 쓴다.
    변형 값은 blank와 같은 양이 아니고, CALCVAL이 없으면 단위를 맞출 수 없다. (결과, 튀는 die 표시)"""
    n, J = Y.shape
    R = Y.mean(axis=1)
    level = abs(float(np.median(R)))
    s_die, s_run = robust_noise(Y)
    s_die_anova, s_run_anova = run_anova(Y)
    vals = np.unique(np.concatenate([Y.ravel(), z]))
    sp = spec_terms(info, level, abs(float(np.median(z))))
    cands = [(s_die, "POR 반복"),
             (float(np.diff(vals).min()) / np.sqrt(12) if len(vals) > 1 else 0.0, "데이터 분해능"),
             (sp.get("spec_resolution", 0.0) / np.sqrt(12), "장비 분해능")]
    s_lim, src = max(cands, key=lambda t: t[0])
    lod, loq = K_LOD * s_lim, K_LOQ * s_lim
    blank_info = {}
    if blank_lim:
        if info is None:
            blank_info = {"blank_status": "level.csv 없음: 미적용"}
        elif info.derived:
            blank_info = {"blank_status": "변형: 미적용"}
        elif not info.calcval:
            blank_info = {"blank_status": "CALCVAL 없음: 미적용"}
        else:
            k = abs(info.calcval)
            b_lod, b_loq = blank_lim[0] * k, blank_lim[1] * k
            blank_info = {"blank_status": "적용", "blank_LoD_item": b_lod, "blank_LoQ_item": b_loq}
            if b_loq > loq:
                lod, loq, src = max(lod, b_lod), b_loq, "blank"
    d = z - R
    rs = robust_sigma(d)
    outlier = np.abs(d - np.median(d)) > OUTLIER_K * rs if rs > 0 else np.zeros(n, bool)
    p_t = paired_t_p(d)
    por_pairs = [paired_t_p(Y[:, j] - Y[:, i]) for i in range(J) for j in range(i + 1, J)]
    out = {
        "n_die": n, "n_por_runs": J, "por_median": float(np.median(R)), "doe_median": float(np.median(z)),
        "sigma_die": s_die, "sigma_run": s_run, "sigma_run_df": J - 1,
        "sigma_die_anova": s_die_anova, "sigma_run_anova": s_run_anova, "LoD": lod, "LoQ": loq, "limit_source": src,
        "mean_d": float(d.mean()), "median_d": float(np.median(d)), "sd_d": float(d.std(ddof=1)),
        "robust_sigma_d": rs, "n_outlier_die": int(outlier.sum()),
        "ttest_p": p_t, "ttest": "유의차" if p_t < 0.05 else "유의차 없음",
        "por_ttest_sig": f"{sum(p < 0.05 for p in por_pairs)}/{len(por_pairs)}",
        **{f"POR{k + 1}_mean": float(Y[:, k].mean()) for k in range(J)}, "DOE_mean": float(z.mean()), **sp,
        **blank_info,
    }
    if n < MIN_DIE:
        return {**out, "zone": "die 부족", "verdict": "미결", "reason": f"die {n}개 (< {MIN_DIE})"}, outlier

    if level < loq:
        zone = "검출한계 이하" if level < lod else "검출~정량"
        I, D = (np.abs(Y) >= loq).astype(float), (np.abs(z) >= loq).astype(float)
        _, s_run_det = run_anova(I)
        e = D - I.mean(axis=1)
        center, lo, hi = ci_mean(e) if e.std() > 0 else (float(e.mean()),) * 3
        run_term = run_factor(J) * s_run_det
        delta = a.det_margin + run_term
        v, why = tost(center, lo, hi, delta, fmt=lambda x: f"{x:+.0%}p")
        por_det = I.mean(axis=0)
        out.update(zone=zone, method="TOST LoQ 넘는 die 비율", policy_margin=a.det_margin, run_margin=run_term,
                   delta=delta, center=center, ci_low=lo, ci_high=hi, h=(hi - lo) / 2, sigma_run_det=s_run_det,
                   **{f"POR{k + 1}_det": float(por_det[k]) for k in range(J)}, DOE_det=float(D.mean()),
                   doe_det_outside_por=bool(D.mean() > por_det.max() or D.mean() < por_det.min()),
                   verdict_tost_low=v)
        if "range_doe" in out:
            out.update(range_doe="", range_changed=None)   # 바닥 값은 DOE/POR 비가 의미 없어 range를 정하지 않음
        # 같은 비교를 값 척도로도 한다. die 61개의 중심(Hodges–Lehmann)은 개별 값보다 훨씬 정밀하고, 문턱(LoQ) 근처에서
        # 중심이 조금만 움직여도 넘는 비율은 크게 바뀌므로, 비율만 보면 POR 회차 흔들림보다 작은 이동도 차이로 보인다.
        vc, vlo, vhi = ci_hl(d) if d.std() > 0 else (float(d.mean()),) * 3
        v_delta = a.r * level + run_factor(J) * s_run
        v_out = vlo > v_delta or vhi < -v_delta
        out.update(value_center=vc, value_ci_low=vlo, value_ci_high=vhi, value_delta=v_delta,
                   value_beyond_run=bool(v_out))
        if a.strict_low_tost:
            return {**out, "verdict": v, "reason": f"LoQ 넘는 die 비율: {why}"}, outlier
        if v == "차이" and v_out:
            return {**out, "verdict": "차이", "reason": f"LoQ 넘는 die 비율: {why}, 중심 이동도 POR 회차 흔들림 밖"}, outlier
        # LoQ 미만 값은 숫자가 아니라 "<LoQ"로 보고한다 (IUPAC). 차이는 넘는 비율과 중심 이동이 둘 다 POR 회차 흔들림을
        # 넘을 때만. 그 밖은 보고가 같다고 본다.
        note = "비율은 다르지만 중심 이동이 POR 회차 흔들림 안" if v == "차이" else f"TOST: {why}"
        return {**out, "verdict": "동등", "reason": f"<LoQ 보고 일치 ({note})"}, outlier

    policy = a.r * level
    run_term = run_factor(J) * s_run
    delta, delta_src = policy + run_term, "정책 + 회차"
    center, lo, hi = (ci_hl(d) if a.estimator == "hl" else ci_mean(d)) if d.std() > 0 else (float(d.mean()),) * 3
    v0, _ = tost(center, lo, hi, delta)
    if a.accuracy and sp.get("accuracy_margin", 0.0) > delta:
        delta, delta_src = sp["accuracy_margin"], "장비 정확도"
    v, why = tost(center, lo, hi, delta)
    out.update(zone="정량", method=f"TOST {'Hodges–Lehmann' if a.estimator == 'hl' else '평균'}",
               policy_margin=policy, run_margin=run_term, delta=delta, delta_source=delta_src,
               verdict_no_accuracy=v0, center=center, ci_low=lo, ci_high=hi,
               h=(hi - lo) / 2, rel_shift=center / level if level else np.nan)
    return {**out, "verdict": v, "reason": why}, outlier


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--por", nargs="+", action="append", required=True,
                    help="POR 1회분 (파일이나 폴더). 회차마다 --por 를 따로 씀: --por run1/ --por run2/ --por run3/")
    ap.add_argument("--doe", nargs="+", required=True, help="DOE 1회분 (파일이나 폴더)")
    ap.add_argument("--r", type=float, default=0.05, help="정량 구간 허용폭 = r × |POR| (기본 0.05)")
    ap.add_argument("--det-margin", type=float, default=0.05,
                    help="LoQ 미만 구간 허용폭: LoQ 넘는 die 비율 차이 (기본 0.05 = 5%%p)")
    ap.add_argument("--strict-low-tost", action="store_true",
                    help="LoQ 미만도 동등을 증명해야 동등 (기본: 차이 증거가 없으면 '<LoQ 보고 일치'로 동등)")
    ap.add_argument("--estimator", choices=["hl", "mean"], default="hl",
                    help="정량 구간 신뢰구간: hl = Hodges–Lehmann/Wilcoxon (기본), mean = 평균/t")
    ap.add_argument("--level", help="CSV ITEM,LEVEL[,CALCVAL][,DERIVED]. LEVEL = 실제 측정값 자릿수 (예: 10fA = 10~100 fA, "
                                    "100nA, 10uV). CALCVAL = 파일 값 / 원측정값. DERIVED = Y면 변형(조합·추출) 값이라 "
                                    "장비 사양과 blank를 쓰지 않음. blank는 변형 아님 + CALCVAL 있는 ITEM에만")
    ap.add_argument("--accuracy", action="store_true",
                    help="--level 이 있는 A·V ITEM에서 정량 구간 허용폭 하한으로 장비 사양 정확도를 씀")
    ap.add_argument("--blank", nargs="*", default=[],
                    help="blank 데이터 (infra_compare.py 와 같은 형식). LoD·LoQ 하한으로만 씀")
    ap.add_argument("--blank-map", help="CSV ITEM,BLANK_ITEM. 없으면 같은 이름끼리 연결")
    ap.add_argument("--key", default="WAFERID,COORD_X_Y,ITEM")
    ap.add_argument("--encoding", default="auto")
    ap.add_argument("--out", default="por_doe_out")
    a = ap.parse_args()
    if len(a.por) < 2:
        sys.exit("POR은 2회 이상 필요합니다 (--por 를 회차마다 따로)")
    key = a.key.split(",")
    die_cols = [k for k in key if k != "ITEM"]

    runs, units = [], {}   # UNIT은 결과 표시용으로만 옮긴다. 판정에는 쓰지 않는다
    for i, paths in enumerate(a.por):
        df = load_side(paths, f"POR{i + 1}", a.encoding)
        if i == 0:
            units = df.groupby("ITEM")["UNIT"].first().to_dict()
        runs.append(df.groupby(key)["DATA"].median().rename(f"POR{i + 1}"))
    doe = load_side(a.doe, "DOE", a.encoding).groupby(key)["DATA"].median().rename("DOE")
    wide = pd.concat(runs + [doe], axis=1, join="inner").reset_index()
    por_cols = [f"POR{i + 1}" for i in range(len(a.por))]
    print(f"POR {len(por_cols)}회 + DOE, 모든 회차에 있는 die·ITEM {len(wide):,}개, ITEM {wide['ITEM'].nunique():,}개")

    blank = load_blank(a.blank, a.encoding) if a.blank else pd.DataFrame(columns=["BLANK_ITEM"])
    bmap = {}
    if a.blank_map:
        mp = read_csv_auto(Path(a.blank_map), a.encoding)
        mp.columns = [c.strip().upper() for c in mp.columns]
        bmap = dict(zip(mp["ITEM"], mp["BLANK_ITEM"]))
    blank = blank.set_index("BLANK_ITEM")

    levels = {}
    if a.level:
        lv = read_csv_auto(Path(a.level), a.encoding)
        lv.columns = [c.strip().upper() for c in lv.columns]
        lv = lv.rename(columns={"SCALE": "CALCVAL", "변형": "DERIVED"})
        cv = pd.to_numeric(lv["CALCVAL"], errors="coerce") if "CALCVAL" in lv else pd.Series(np.nan, index=lv.index)
        dv = (lv["DERIVED"].astype(str).str.strip().str.upper().isin({"Y", "YES", "1", "TRUE", "O", "변형"})
              if "DERIVED" in lv else pd.Series(False, index=lv.index))
        bad = []
        for it, txt, c, der in zip(lv["ITEM"].astype(str).str.strip(), lv["LEVEL"], cv, dv):
            parsed = parse_level(txt)
            if parsed or der:
                L, kind = parsed or (np.nan, "")
                levels[it] = ItemInfo(L, kind, float(c) if np.isfinite(c) and c != 0 else None, bool(der))
            else:
                bad.append(f"{it}={txt}")
        info_all = list(levels.values())
        kinds = pd.Series([i.kind for i in info_all if i.kind]).value_counts().to_dict()
        print(f"LEVEL 표: ITEM {len(levels):,}개 {kinds}" + (f", 읽지 못한 행 {len(bad)}개: {bad[:5]}" if bad else ""))
        print(f"  변형 {sum(i.derived for i in info_all):,}개, 변형 아님 + CALCVAL 있음 "
              f"{sum(not i.derived and bool(i.calcval) for i in info_all):,}개, 변형 아님 + CALCVAL 없음 "
              f"{sum(not i.derived and not i.calcval for i in info_all):,}개")
        no_spec = {k: n for k, n in kinds.items() if k not in ("A", "V")}
        if no_spec:
            print(f"  {no_spec}: 장비 사양을 아직 넣지 않아 LEVEL만 기록")
    elif a.accuracy:
        sys.exit("--accuracy 는 --level 이 필요합니다")

    rows, outl = [], []
    for item, g in wide.groupby("ITEM", sort=False):
        Y, z = g[por_cols].to_numpy(float), g["DOE"].to_numpy(float)
        bitem = bmap.get(item, item)
        extra, lim = {}, None
        if bitem in blank.index:
            lim3 = blank_limits(blank.loc[bitem])
            if lim3:
                lim = lim3[1:]
                extra = {"blank_item": bitem, "blank_LoD_raw": lim[0], "blank_LoQ_raw": lim[1]}
        res, mask = judge(Y, z, a, lim, levels.get(item))
        if lim:
            base, _ = judge(Y, z, a, None, levels.get(item))
            extra.update(verdict_no_blank=base["verdict"], zone_no_blank=base["zone"])
        rows.append({"ITEM": item, "UNIT": units.get(item), **res, **extra})
        if mask.any():
            outl.append(g.loc[mask, die_cols + ["ITEM"] + por_cols + ["DOE"]])
    res = pd.DataFrame(rows)
    res = res.sort_values(["verdict", "ITEM"], key=lambda s: s.map(ORDER) if s.name == "verdict" else s)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "items.csv", index=False, encoding="utf-8-sig")
    od = pd.concat(outl) if outl else pd.DataFrame(columns=die_cols + ["ITEM"])
    od.to_csv(out / "outlier_dies.csv", index=False, encoding="utf-8-sig")

    print(f"\n판정 (정량 ±{a.r:.0%}, LoQ 미만 ±{a.det_margin:.0%}p, 각각 + 회차 흔들림, 신뢰구간 {a.estimator})")
    print(pd.crosstab(res["zone"], res["verdict"], margins=True, margins_name="합계").to_string())
    q = res[res["zone"] == "정량"]
    if len(q):
        print("\n정량 구간: t-test vs TOST")
        print(pd.crosstab(q["ttest"], q["verdict"], margins=True, margins_name="합계").to_string())
        n_por = int((q["por_ttest_sig"].str.split("/").str[0].astype(int) > 0).sum())
        print(f"\nPOR끼리 t-test에서도 유의차가 나온 ITEM: {n_por:,} / {len(q):,}"
              f"  (같은 프로그램인데 t-test가 '차이'라고 한 수)")
    if "verdict_no_blank" in res:
        hb = res[res["verdict_no_blank"].notna()]
        print(f"\nblank 연결 ITEM {len(hb):,}개: {hb['blank_status'].value_counts().to_dict()}, "
              f"blank가 한계를 정한 ITEM {int((hb['limit_source'] == 'blank').sum()):,}개")
        print("blank 없이 → blank 하한 적용 (행: 없이, 열: 적용)")
        print(pd.crosstab(hb["verdict_no_blank"], hb["verdict"], margins=True, margins_name="합계").to_string())
    if a.accuracy and len(q):
        print(f"\n장비 정확도 하한: 적용 가능 {int(q['accuracy_margin'].notna().sum()):,}개, "
              f"허용폭을 정한 ITEM {int((q['delta_source'] == '장비 정확도').sum()):,}개")
        print("정확도 없이 → 적용 (행: 없이, 열: 적용)")
        print(pd.crosstab(q["verdict_no_accuracy"], q["verdict"], margins=True, margins_name="합계").to_string())
    if "level_check" in res and res["level_check"].astype(str).str.startswith("불일치").any():
        n = int(res["level_check"].astype(str).str.startswith("불일치").sum())
        print(f"\n경고: CALCVAL로 환산한 실제 값이 LEVEL 자릿수와 다른 ITEM {n}개 (level_check 열). CALCVAL이나 LEVEL을 확인하세요")
    if "range_changed" in res:
        nb = res[res["verdict"] != "동등"]
        print(f"\nPOR과 DOE의 auto range가 다른 ITEM: 전체 {int(res['range_changed'].eq(True).sum())}개, "
              f"동등이 아닌 ITEM 중 {int(nb['range_changed'].eq(True).sum())}개")
    rs = res[res["verdict"] != "동등"]["reason"].str.replace(r"shift .*가", "shift가", regex=True).value_counts()
    if len(rs):
        print("\n동등이 아닌 사유")
        print(rs.to_string())
    print(f"\n결과: {out / 'items.csv'}, {out / 'outlier_dies.csv'}")


if __name__ == "__main__":
    main()
