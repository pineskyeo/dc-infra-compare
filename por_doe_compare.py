"""POR 여러 회(같은 die 재측정) + DOE 1회로 ITEM별 동등 / 차이 / 미결 / 판정 제외를 판정한다.

기준은 실행 전에 정하는 값(허용폭 r)뿐이고, 데이터를 보고 바뀌는 문턱값은 없다. UNIT, SPEC 열은 판정에 쓰지 않는다.

1. 흔들림 (POR 회차 반복, NIST e-Handbook 2.4.4의 die·회차 분리를 robust 통계로)
   sigma_die : 같은 die를 다시 잰 1회 측정 흔들림. 이웃 회차 차이를 회차쌍마다 중앙값으로 맞춘 뒤 robust σ / √2
   sigma_run : 회차마다 전체가 같이 움직이는 크기 (컨택 상태, 온도 등). 회차별 중앙값으로

2. LoQ (Currie / IUPAC): LoD = 3.29 σ, LoQ = 10 σ. σ = 아래 중 가장 큰 것
   sigma_die / 데이터 분해능 / √12 (GUM F.2.2.1) / 장비 분해능 / √12 (--level) / blank (--blank, CALCVAL 있는 ITEM)

3. 판정. die별 d = DOE − POR 회차 평균, shift = d의 중앙값, 90% 신뢰구간 = 부호검정 (Hollander & Wolfe)
   허용폭 Δ = r × |POR 중앙값| + t(0.95, J−1) × √(1 + 1/J) × sigma_run
     뒤쪽은 DOE 1회가 POR J회 평균에서 같은 프로그램 안에서도 벗어날 수 있는 폭 (90% 예측구간 한쪽)
     --level 의 A·V ITEM은 장비 정확도로 구한 폭이 더 크면 그쪽 (GUM 4.3.7)
   정량 (|POR| ≥ LoQ): 신뢰구간이 ±Δ 안 → 동등, 통째로 밖 → 차이, 걸침 → 미결
   LoQ 미만: 값은 "<LoQ"로 보고한다 (IUPAC). 신뢰구간이 통째로 ±Δ 밖이고 DOE 중심(POR 중앙값 + shift)이
     LoQ 이상이라 보고가 달라질 때만 차이, 그 밖은 동등 ("<LoQ 보고 일치")
   판정 제외: 통계를 낼 수 없는 ITEM. 맞는 원인 모두를 아래 순서로 '; ' 구분해 reason에 적는다
     (1) 중심·신뢰구간 NaN/inf (2) die 산포 0: sigma_die = 0 또는 고정값 비율 > 50% (status '산포 0'과 같은 비율)
     (3) POR 중앙값 0이고 sigma_run 0. 그 밖은 zone 판정: LoQ 미만은 Δ와 무관하게 판정하고,
     정량은 장비 정확도 대체 후 최종 Δ가 0 이하·NaN일 때만 판정 제외

4. 참고 (판정에 안 씀): t-test (NIST 7.3.1.1), POR 회차끼리 t-test, 튀는 die (|d − 중앙값| > 5 robust σ)
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
RUN_JITTER_OVER_DELTA = 1.0     # 회차 흔들림: die별 회차 범위 중앙값 ≥ 이 배수 × Δ
SIZE_JITTER_RHO = -0.5          # 작을수록 흔들림: Spearman ρ(크기, log 범위) ≤ 이 값
SIZE_JITTER_RHO_POS = 0.5       # 클수록 흔들림: Spearman ρ(크기, log 범위) ≥ 이 값
SIZE_JITTER_MIN_DIE = 10
LOG_DECADES_MIN = 1.0           # log 후보: decades ≥ 이 값 그리고 log_fit > LOG_FIT_MIN
LOG_FIT_MIN = 0.1               # log 후보: log_fit > 이 값 (|skew_lin| − |skew_log|, log 쪽이 이만큼은 더 대칭이어야)
BIMODAL_BC_MIN = 5 / 9          # 두 덩어리: bimodality_log > 이 값 (균일분포 BC = 5/9 ≈ 0.555). 기준값 추천(검토 필요)
BIMODAL_MIN_DIE = 10            # 두 덩어리: POR 회차평균이 유한한 die ≥ 이 수, Open 코드(|x| ≥ 1E+90) die는 세지 않음. 기준값 추천(검토 필요)
JITTER_COLS = ["run_jitter_pct", "run_jitter_over_delta", "spearman_size_jitter"]
GAP_COLS = ["por_gap_over_delta", "por_gap_over_noise"]
RESOLUTION_COLS = ["resolution_step", "resolution_over_delta"]
# status 바로 뒤 지표 묶음: 조건 불안정 → 회차 흔들림 → 크기-흔들림 → 분해능 부족 → 산포 0
METRIC_COLS = GAP_COLS + JITTER_COLS + RESOLUTION_COLS + ["fixed_share"]
SHAPE_EXCLUDE_ABS = 1e90        # 분포 모양(SHAPE_COLS) 계산에서만 |x| ≥ 이 값(Open 코드 등)을 뺀다
# 분포 모양 묶음 (지표 묶음 끝). decades = log10(P99|x|/P1|x|), skew_lin·skew_log = Bowley(사분위) 왜도, 범위 −1~1
SHAPE_COLS = ["decades", "skew_lin", "skew_log", "log_fit", "bimodality_log"]
STATUS_COLS = ["status", *METRIC_COLS, *SHAPE_COLS, "mean_median_ratio"]
PRECISION_COLS = ["sigma_meas", "meas_precision_pct", "sigma_meas_over_delta"]
LOG_COLS = ["verdict_log", "center_log", "ci_low_log", "ci_high_log", "delta_log", "ci_half_over_delta",
            "ci_half_over_delta_log", "spearman_size_jitter_log", "log_reason",     # 0 없고 부호 하나인 ITEM 참고용
            "sigma_die_log", "sigma_run_log", "below_linear_loq", "policy_margin_log",   # 분석용, 판정에 안 씀
            "sigma_rep_log"]                                                             # log 판정의 회차 항
POR_GAP_NOISE_K = 3             # 조건 불안정: 짝지은 회차 차 ≥ 이 배수 × 회차 중앙값 차의 표준오차
ST_OK, ST_UNSTABLE, ST_RESOLUTION, ST_FLAT = "정상", "조건 불안정", "분해능 부족", "산포 0"
ST_RUN_JITTER, ST_SIZE_JITTER, ST_SIZE_JITTER_POS = "회차 흔들림", "작을수록 흔들림", "클수록 흔들림"
ST_LOG_CANDIDATE, ST_BIMODAL = "log 후보", "두 덩어리"     # 분포 모양 (SHAPE_COLS)
ST_SETUP_ERROR = "조건 설정 오류"     # 예약 값. 판정에 필요한 입력이 없어 지금은 쓰지 않음
V_EXCLUDED = "판정 제외"
ORDER = {"차이": 0, "미결": 1, "동등": 2, V_EXCLUDED: 3}

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
    """level.csv 한 줄. 원측정값 |값|의 자릿수 [L, 10L), 측정 종류 kind (A, V, F, Hz).
    calcval: 파일 값 = 원측정값 × CALCVAL (모르면 None). derived: 여러 측정을 조합·추출한 값이라 원측정값의 배율이 아님."""
    L: float
    kind: str
    calcval: float | None
    derived: bool


def parse_level(text) -> tuple[float, str] | None:
    """'10fA' → (1e-14, 'A')."""
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
    CALCVAL이 있으면 실제 값 = level / |CALCVAL|, 없으면 실제 값 = 자릿수 상한 10L (허용폭을 가장 작게 잡는 쪽)."""
    if info is None:
        return {}
    if info.derived:
        return {"spec_status": "변형: 장비 사양 미적용"}
    if level <= 0:
        return {"spec_status": "POR 값 0: 환산 불가"}
    if info.calcval:
        k = abs(info.calcval)
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
    rp, rd = smu_row(info.kind, phys), smu_row(info.kind, phys_d)
    out = {"spec_status": status, "level_check": check,
           "range_por": range_name(rp, info.kind), "range_doe": range_name(rd, info.kind)}
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


def _noise_parts(Y: np.ndarray) -> tuple[float, float]:
    """(sigma_die, sigma_run² 추정값). 추정값은 회차별 중앙값들의 분산 − (π/2) sigma_die² / n 이라 0 이하일 수 있다."""
    n, J = Y.shape
    dd = [Y[:, k + 1] - Y[:, k] for k in range(J - 1)]
    s_die = robust_sigma(np.concatenate([x - np.median(x) for x in dd])) / np.sqrt(2)
    r = np.median(Y - Y.mean(axis=1, keepdims=True), axis=0)
    return s_die, r.var(ddof=1) - (np.pi / 2) * s_die ** 2 / n


def robust_noise(Y: np.ndarray) -> tuple[float, float]:
    """(sigma_die, sigma_run). sigma_run 은 회차별 중앙값들의 분산에서 die 잡음 몫((π/2) sigma_die² / n)을 뺀 것."""
    s_die, v = _noise_parts(Y)
    return s_die, float(np.sqrt(max(0.0, v)))


def run_factor(J: int) -> float:
    """sigma_run 은 회차 J개로 추정해 자유도가 J − 1이라 1.645 대신 t(0.95, J − 1) (J = 3이면 2.92)."""
    return float(stats.t.ppf(0.95, J - 1) * np.sqrt(1 + 1 / J))


def _jitter(Y: np.ndarray, delta: float) -> tuple[dict, int]:
    """die별 POR 회차 흔들림 열(JITTER_COLS)과 작을수록 흔들림 검사에 쓴 die 수. 계산할 수 없으면 NaN.
    run_jitter_pct = 100 × 중앙값(회차 범위 / |회차 평균|), run_jitter_over_delta = 중앙값(회차 범위) / Δ,
    spearman_size_jitter = Spearman ρ(log10|회차 평균|, log10|값|의 회차 범위). 0값 있는 die는 ρ에서 뺌."""
    out = dict.fromkeys(JITTER_COLS, np.nan)
    if Y.ndim != 2 or Y.shape[1] < 2:
        return out, 0
    Y = Y[np.isfinite(Y).all(axis=1)]
    m, rng = Y.mean(axis=1), Y.max(axis=1) - Y.min(axis=1)
    keep = m != 0
    if keep.any():
        out["run_jitter_pct"] = float(100 * np.median(rng[keep] / np.abs(m[keep])))
        if delta > 0 and np.isfinite(delta):
            out["run_jitter_over_delta"] = float(np.median(rng[keep]) / delta)
    ok = (Y != 0).all(axis=1) & keep
    n = int(ok.sum())
    if n >= 3:
        x, lg = np.log10(np.abs(m[ok])), np.log10(np.abs(Y[ok]))
        out["spearman_size_jitter"] = _size_rho(x, lg.max(axis=1) - lg.min(axis=1))
    return out, n


def _size_rho(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman ρ(크기 x, 흔들림 y). 어느 한쪽이 모두 같으면 NaN."""
    return float(stats.spearmanr(x, y)[0]) if np.ptp(x) > 0 and np.ptp(y) > 0 else np.nan


def _mode_share(v: np.ndarray) -> float:
    return float(np.unique(v, return_counts=True)[1].max() / v.size)


def flat_share(R: np.ndarray, z: np.ndarray) -> float:
    """고정값 비율: POR die 평균 R 과 DOE z 중 한 값이 차지하는 비율이 큰 쪽. status 산포 0 과 판정 제외가 같이 씀."""
    return max(_mode_share(R), _mode_share(z))


def _skew(v: np.ndarray) -> float:
    """Bowley(사분위) 왜도, 범위 −1~1: (Q3 + Q1 − 2·Q2) / (Q3 − Q1), Q = np.percentile 25/50/75.
    n < 3 이거나 IQR(Q3 − Q1)이 0이면 NaN."""
    if v.size < 3:
        return np.nan
    q1, q2, q3 = np.percentile(v, [25, 50, 75])
    return float((q3 + q1 - 2 * q2) / (q3 - q1)) if q3 > q1 else np.nan


def bimodality_coef(v: np.ndarray) -> float:
    """BC = (g² + 1) / (k + 3(n−1)² / ((n−2)(n−3))). g = 표본 왜도, k = 표본 초과 첨도 (둘 다 보정식, scipy bias=False).
    n < 4 이거나 값이 모두 같으면 NaN."""
    n = v.size
    if n < 4 or np.ptp(v) == 0:
        return np.nan
    g, k = float(stats.skew(v, bias=False)), float(stats.kurtosis(v, fisher=True, bias=False))
    return (g ** 2 + 1) / (k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))


def shape_cols(x: np.ndarray) -> dict:
    """SHAPE_COLS. x = die별 POR 회차평균. 유한하고 |x| < SHAPE_EXCLUDE_ABS 인 값만 씀 (Open 코드 등은 여기서만 뺌).
    decades = log10(P99|x| / P1|x|) (np.percentile 기본 linear 보간), skew_lin = Bowley(사분위) 왜도(x),
    skew_log = Bowley(사분위) 왜도(log10|x|) — 둘 다 범위 −1~1, IQR 0 이면 NaN (_skew).
    log_fit = |skew_lin| − |skew_log| (양수면 log 쪽이 더 대칭), bimodality_log = log10|x| 의 bimodality_coef.
    뺀 뒤의 x에 0이 있거나 부호가 섞이면 log 쪽(decades, skew_log, log_fit, bimodality_log)은 NaN."""
    x = x[np.isfinite(x) & (np.abs(x) < SHAPE_EXCLUDE_ABS)]
    out = dict.fromkeys(SHAPE_COLS, np.nan)
    if x.size == 0:
        return out
    out["skew_lin"] = _skew(x)
    if (x == 0).any() or ((x > 0).any() and (x < 0).any()):
        return out
    lg = np.log10(np.abs(x))
    p1, p99 = np.percentile(lg, [1, 99])      # log10 은 단조라 log10(P99|x|/P1|x|) 와 같음
    out["decades"] = float(p99 - p1)
    out["skew_log"] = _skew(lg)
    out["log_fit"] = abs(out["skew_lin"]) - abs(out["skew_log"])
    out["bimodality_log"] = bimodality_coef(lg)
    return out


def item_status(Y: np.ndarray, z: np.ndarray, delta: float) -> dict:
    """판정과 별개인 데이터 상태. 해당하는 이름을 모두 ';'로 잇고, 판단에 쓴 값을 METRIC_COLS 로 같이 돌려준다.
    지표는 status 여부와 무관하게 계산할 수 있으면 채우고 못 하면 NaN.
    resolution_step = 값(POR 전 회차·DOE) 고유값 간 최소 차, resolution_over_delta = step / Δ,
    fixed_share = flat_share(R, z) (산포 0·판정 제외 '고정값 NN%'와 같은 값).
    Y: die × 회차 POR 값, z: DOE die 값, delta: 그 ITEM의 최종 Δ.
    Δ ≤ 0 또는 NaN이면 조건 불안정·회차 흔들림·분해능 부족은 건너뜀. 회차 흔들림·작을수록 흔들림은 POR 회차만 씀
    (POR 1회면 JITTER_COLS 모두 NaN).
    조건 불안정은 짝지은 회차 차: die별 회차 평균을 뺀 값의 회차별 중앙값 rr, gap = max(rr) − min(rr).
    se = 1.2533 · sigma_die · √2 / √n (n = die 수, 두 중앙값 차의 표준오차). gap ≥ Δ 이고 gap ≥ POR_GAP_NOISE_K · se 일 때
    (se가 0이거나 유한하지 않으면 gap ≥ Δ 만). GAP_COLS: por_gap_over_delta = gap / Δ, por_gap_over_noise = gap / se,
    계산할 수 없으면 NaN (POR 1회면 둘 다 NaN, 조건 불안정 없음). 작을수록·클수록 흔들림은 0값 없는 die가 SIZE_JITTER_MIN_DIE개 이상일 때만.
    분포 모양 SHAPE_COLS = shape_cols(die별 POR 회차평균). log 후보: decades ≥ LOG_DECADES_MIN 그리고 log_fit > LOG_FIT_MIN.
    두 덩어리: bimodality_log > BIMODAL_BC_MIN 그리고 die ≥ BIMODAL_MIN_DIE (Open 코드(|x| ≥ 1E+90) die는 세지 않음). 판정(judge)과 다른 status는 바꾸지 않는다."""
    Y, z = np.asarray(Y, float), np.asarray(z, float)
    R = Y.mean(axis=1)
    has_delta = bool(delta > 0)     # NaN도 False
    names = []

    gap_cols = dict.fromkeys(GAP_COLS, np.nan)
    if Y.ndim == 2 and Y.shape[1] > 1:
        rr = np.median(Y - Y.mean(axis=1, keepdims=True), axis=0)
        gap = float(rr.max() - rr.min())
        se = 1.2533 * robust_noise(Y)[0] * np.sqrt(2) / np.sqrt(Y.shape[0])
        noisy = bool(np.isfinite(se) and se > 0)
        if has_delta and np.isfinite(delta):
            gap_cols["por_gap_over_delta"] = gap / delta
        if noisy:
            gap_cols["por_gap_over_noise"] = gap / se
        if has_delta and gap >= delta and (not noisy or gap >= POR_GAP_NOISE_K * se):
            names.append(ST_UNSTABLE)

    jit, n_size = _jitter(Y, delta)
    over, rho = jit["run_jitter_over_delta"], jit["spearman_size_jitter"]
    if over >= RUN_JITTER_OVER_DELTA:      # NaN이면 False
        names.append(ST_RUN_JITTER)
    if rho <= SIZE_JITTER_RHO and n_size >= SIZE_JITTER_MIN_DIE:
        names.append(ST_SIZE_JITTER)
    if rho >= SIZE_JITTER_RHO_POS and n_size >= SIZE_JITTER_MIN_DIE:
        names.append(ST_SIZE_JITTER_POS)

    res_cols = dict.fromkeys(RESOLUTION_COLS, np.nan)
    vals = np.unique(np.concatenate([Y.ravel(), z]))
    if vals.size > 1:
        step = float(np.diff(vals).min())
        res_cols["resolution_step"] = step
        if has_delta:
            res_cols["resolution_over_delta"] = step / delta
            if step >= 0.1 * delta:
                names.append(ST_RESOLUTION)

    s_die = robust_noise(Y)[0] if Y.shape[1] > 1 else np.nan      # POR 1회면 die 잡음을 못 구함
    share = flat_share(R, z)
    if s_die == 0 or share > 0.5:
        names.append(ST_FLAT)

    shape = shape_cols(R)
    if shape["decades"] >= LOG_DECADES_MIN and shape["log_fit"] > LOG_FIT_MIN:      # NaN이면 False
        names.append(ST_LOG_CANDIDATE)
    n_shape = int((np.isfinite(R) & (np.abs(R) < SHAPE_EXCLUDE_ABS)).sum())
    if shape["bimodality_log"] > BIMODAL_BC_MIN and n_shape >= BIMODAL_MIN_DIE:
        names.append(ST_BIMODAL)

    med = float(np.median(R))
    return {"status": ";".join(names) or ST_OK, **gap_cols, **jit, **res_cols, "fixed_share": share, **shape,
            "mean_median_ratio": (float(R.mean()) - med) / abs(med) if med != 0 else np.nan}


def meas_precision(sigma_die: float, sigma_run: float, por_median: float, delta: float) -> dict:
    """측정 정밀도 (작을수록 좋음). die 간 산포와 회차 산포는 서로 독립이라 분산이 더해진다.
    por_median 또는 delta가 0·NaN이면 해당 비율은 NaN."""
    s = float(np.hypot(float(sigma_die), float(sigma_run)))     # 입력 NaN이면 NaN
    med, d = float(por_median), float(delta)
    return {"sigma_meas": s,
            "meas_precision_pct": 100 * s / abs(med) if med != 0 and not np.isnan(med) else np.nan,
            "sigma_meas_over_delta": s / d if d != 0 and not np.isnan(d) else np.nan}


def paired_t_p(d: np.ndarray) -> float:
    s = d.std(ddof=1)
    if s == 0:
        return 1.0 if d.mean() == 0 else 0.0
    return float(2 * stats.t.sf(abs(d.mean() / (s / np.sqrt(len(d)))), len(d) - 1))


def ci_rank(n: int) -> int:
    """부호검정 90% 신뢰구간의 0-based 아래 순번. 구간은 1-based로 (k+1)~(n-k)."""
    k = int(stats.binom.ppf(0.05, n, 0.5))
    if stats.binom.cdf(k, n, 0.5) > 0.05:
        k -= 1
    return max(k, 0)


def ci_median(d: np.ndarray) -> tuple[float, float, float]:
    """중앙값과 부호검정 90% 신뢰구간. 튀는 die의 개수만 영향을 주고 크기는 영향이 없다."""
    if d.std() == 0:
        return (float(d.mean()),) * 3
    n = len(d)
    x = np.sort(d)
    k = ci_rank(n)
    return float(np.median(d)), float(x[k]), float(x[n - 1 - k])


def tost(center: float, lo: float, hi: float, delta: float) -> tuple[str, str]:
    if -delta <= lo and hi <= delta:
        return "동등", "90% 신뢰구간이 ±Δ 안"
    if lo > delta or hi < -delta:
        return "차이", f"shift {center:+.4g}가 ±Δ({abs(delta):.4g}) 밖"
    if (hi - lo) / 2 >= delta:
        return "미결", "해상도 부족 (신뢰구간 반폭 ≥ Δ)"
    return "미결", "경계 (신뢰구간이 Δ에 걸침)"


def reason_group(reason: pd.Series) -> pd.Series:
    """사유에서 숫자를 빼고 종류만 남긴다 (표로 세기 위해). 판정 제외 사유는 괄호 속 값을 뺀다."""
    s = (reason.astype(str)
         .str.replace(r"^shift .*밖$", "shift가 ±Δ 밖", regex=True)
         .str.replace(r"^DOE 중심 .*밖$", "LoQ 미만: DOE 중심 ≥ LoQ이고 이동이 ±Δ 밖", regex=True))
    return s.where(~s.str.startswith(V_EXCLUDED), s.str.replace(r" \([^)]*\)", "", regex=True))


def excluded_reason(center: float, lo: float, hi: float, s_die: float, s_run: float,
                    por_median: float, R: np.ndarray, z: np.ndarray) -> str | None:
    """zone 판정 전에 보는 판정 제외 사유 (없으면 None). 맞는 원인 모두, (1) 중심·CI NaN/inf
    (2) die 산포 0 (3) 중앙값 0·σ_run 0 순서로 '; ' 구분.
    첫 원인만 "판정 제외: " 로 시작. die 산포 0은 σ_die=0이면 그 문구, 아니면 고정값 비율 문구 하나.
    Δ 검사는 여기서 하지 않음: LoQ zone은 Δ와 무관하고, 정량 zone은 accuracy_margin 대체 후 최종 Δ로 judge가 본다."""
    causes = []
    bad = [k for k, v in (("center", center), ("ci_low", lo), ("ci_high", hi)) if not np.isfinite(v)]
    if bad:
        causes.append(f"중심·신뢰구간 계산 불가 ({', '.join(bad)})")
    share = flat_share(R, z)        # items.csv fixed_share 와 같은 값
    if s_die == 0:
        causes.append("die 산포 0 (σ_die=0)")
    elif share > 0.5:
        causes.append(f"die 산포 0 (고정값 {round(100 * share)}%)")
    if por_median == 0 and s_run == 0:
        causes.append("고정값 (중앙값 0·σ_run 0)")
    return f"{V_EXCLUDED}: {'; '.join(causes)}" if causes else None


def judge(Y: np.ndarray, z: np.ndarray, r: float, blank_lim=None, info: ItemInfo | None = None,
          run_term: float | None = None) -> tuple[dict, np.ndarray]:
    """ITEM 하나 판정. (결과, 튀는 die 표시)
    run_term 이 None 이면 회차 항 = t(0.95, J−1) × √(1 + 1/J) × sigma_run, 값을 주면 Δ = r × level + run_term."""
    n, J = Y.shape
    R = Y.mean(axis=1)
    level = abs(float(np.median(R)))
    s_die, s_run = robust_noise(Y)
    vals = np.unique(np.concatenate([Y.ravel(), z]))
    sp = spec_terms(info, level, abs(float(np.median(z))))
    s_lim, src = max([(s_die, "POR 반복"),
                      (float(np.diff(vals).min()) / np.sqrt(12) if len(vals) > 1 else 0.0, "데이터 분해능"),
                      (sp.get("spec_resolution", 0.0) / np.sqrt(12), "장비 분해능")], key=lambda t: t[0])
    lod, loq = K_LOD * s_lim, K_LOQ * s_lim
    bl = {}
    if blank_lim:
        # blank는 원측정값이라 변형이 아니고 CALCVAL이 있는 ITEM만 × |CALCVAL| 로 ITEM 단위로 바꿔 쓴다
        if info is None:
            bl["blank_status"] = "level.csv 없음: 미적용"
        elif info.derived:
            bl["blank_status"] = "변형: 미적용"
        elif not info.calcval:
            bl["blank_status"] = "CALCVAL 없음: 미적용"
        else:
            b_lod, b_loq = blank_lim[0] * abs(info.calcval), blank_lim[1] * abs(info.calcval)
            bl.update(blank_status="적용", blank_LoQ_item=b_loq)
            if b_loq > loq:
                lod, loq, src = max(lod, b_lod), b_loq, "blank"
    d = z - R
    rs = robust_sigma(d)
    outlier = np.abs(d - np.median(d)) > OUTLIER_K * rs if rs > 0 else np.zeros(n, bool)
    p_t = paired_t_p(d)
    por_pairs = [paired_t_p(Y[:, j] - Y[:, i]) for i in range(J) for j in range(i + 1, J)]
    center, lo, hi = ci_median(d)
    policy = r * level
    if run_term is None:
        run_term = run_factor(J) * s_run
    delta = policy + run_term
    out = {
        "n_die": n, "por_median": float(np.median(R)),
        **{f"POR{k + 1}_mean": float(Y[:, k].mean()) for k in range(J)}, "DOE_mean": float(z.mean()),
        "center": center, "ci_low": lo, "ci_high": hi, "delta": delta,
        "policy_margin": policy, "run_margin": run_term, "sigma_die": s_die, "sigma_run": s_run,
        "LoQ": loq, "LoD": lod, "limit_source": src, "n_outlier_die": int(outlier.sum()),
        "ttest": "유의차" if p_t < 0.05 else "유의차 없음", "ttest_p": p_t,
        "por_ttest_sig": f"{sum(p < 0.05 for p in por_pairs)}/{len(por_pairs)}",
        **sp, **bl,
    }
    if n < MIN_DIE:
        return {**out, "zone": "die 부족", "verdict": "미결", "reason": f"die {n}개 (< {MIN_DIE})"}, outlier
    why = excluded_reason(center, lo, hi, s_die, s_run, out["por_median"], R, z)
    if why:
        return {**out, "zone": V_EXCLUDED, "verdict": V_EXCLUDED, "reason": why}, outlier

    if level < loq:
        zone = "검출한계 이하" if level < lod else "검출~정량"
        doe_c = float(np.median(R)) + center
        out.update(zone=zone, doe_center=doe_c, range_doe="")   # 바닥 값은 DOE/POR 비가 의미 없어 DOE range를 정하지 않음
        if (lo > delta or hi < -delta) and abs(doe_c) >= loq:
            return {**out, "verdict": "차이",
                    "reason": f"DOE 중심 {doe_c:.4g}가 LoQ({loq:.4g}) 이상이고 이동 {center:+.4g}가 ±Δ({delta:.4g}) 밖"}, outlier
        note = "DOE 중심도 LoQ 미만" if (lo > delta or hi < -delta) else "이동이 ±Δ 안"
        return {**out, "verdict": "동등", "reason": f"<LoQ 보고 일치 ({note})"}, outlier

    v0, _ = tost(center, lo, hi, delta)
    src_d = "정책 + 회차"
    if sp.get("accuracy_margin", 0.0) > delta:
        delta, src_d = sp["accuracy_margin"], "장비 정확도"
    out.update(zone="정량", delta=delta, delta_source=src_d, verdict_no_accuracy=v0,
               rel_shift=center / level if level else np.nan)
    if not np.isfinite(delta) or delta <= 0:
        return {**out, "zone": V_EXCLUDED, "verdict": V_EXCLUDED,
                "reason": f"{V_EXCLUDED}: 최종 Δ가 0 이하이거나 유효하지 않음 (Δ={delta:.4g}, 출처 {src_d})"}, outlier
    v, why = tost(center, lo, hi, delta)
    return {**out, "verdict": v, "reason": why}, outlier


def judge_log(Y: np.ndarray, z: np.ndarray, r: float) -> dict:
    """log 판정 (log형 ITEM의 판정). 같은 judge() 에 L = log10|Y|, w = log10|z| 를 넣는다. 값에 0 이 없고 부호가 하나일 때만 부른다.
    정책 허용폭: 선형의 r × |POR| 는 log 공간에서 더하는 폭 log10(1 + r) 이다. judge 는 r × level
    (level = |중앙값(die별 L 회차 평균)|) 로 곱하므로 r_log = log10(1 + r) / level 을 넘겨 policy_margin = log10(1 + r) 이
    되게 한다 (level 0 이면 policy 0). ASSUMED: 'log10(1+r) 로 넘김' 을 judge 의 곱셈 뒤 정책 폭이 log10(1+r) 이 되도록 해석.
    Δ_log = log10(1 + r) + sigma_rep_log (t·√(1 + 1/J) 배수 없음). sigma_rep_log 은 sigma_rep_log() 참고.
    sigma_run(L) (웨이퍼 공통 회차 이동) 은 결과의 sigma_run 에 남지만 Δ_log 에는 안 쓴다.
    blank_lim·info(LoQ 하한·장비 분해능·장비 정확도)는 원측정값 단위라 넘기지 않는다 (None).
    ASSUMED: LoQ 는 judge 가 L 에서 구한 값을 그대로 쓴다 (|L| < LoQ_log 면 log 판정도 '<LoQ' 쪽으로 감)."""
    L, w = np.log10(np.abs(Y)), np.log10(np.abs(z))
    level = abs(float(np.median(L.mean(axis=1))))
    r_log = float(np.log10(1 + r)) / level if level > 0 else 0.0
    rep = sigma_rep_log(L)
    return {**judge(L, w, r_log, None, None, run_term=rep)[0], "sigma_rep_log": rep}


def sigma_rep_log(L: np.ndarray) -> float:
    """die별 log 회차 흔들림: median over die of std(die 의 L 회차값, ddof=1). L = log10|Y| (die × 회차).
    die 안에서 유한한 회차 값이 2개 미만인 die 는 빼고, 남는 die 가 없으면 NaN."""
    sds = [float(np.std(v, ddof=1)) for v in (row[np.isfinite(row)] for row in L) if v.size >= 2]
    return float(np.median(sds)) if sds else np.nan


def _ci_half_over_delta(res: dict) -> float:
    lo, hi, delta = (float(res.get(k, np.nan)) for k in ("ci_low", "ci_high", "delta"))
    return (hi - lo) / 2 / delta if np.isfinite(delta) and delta > 0 else np.nan


def log_columns(Y: np.ndarray, z: np.ndarray, r: float, res: dict) -> dict:
    """LOG_COLS. 모든 ITEM (status 무관): POR·DOE 값에 0 이 없고 부호가 하나면 log 판정 값을 채운다.
    0 이 있거나 부호가 섞이면 verdict_log 판정 제외, log_reason 에 사유, log 숫자 열 NaN.
    spearman_size_jitter_log = Spearman ρ(log10|회차 평균|, die별 log10|값| 회차 범위), _jitter 와 같은 _size_rho.
    log_reason 은 log 판정이 된 ITEM 이면 judge_log 의 reason (ASSUMED).
    분석용 열 (판정에 안 씀): sigma_*_log 는 judge_log 결과의 sigma_die·sigma_run, verdict_log 가 판정 제외면 NaN.
    sigma_run_log (웨이퍼 공통 회차 이동) 은 판정에 안 씀.
    policy_margin_log = log10(1 + r), log 판정이 된 ITEM 만. below_linear_loq 는 모든 ITEM:
    선형 DOE 중심 |POR 중앙값 + center| < 선형 LoQ (judge 의 LoQ zone 비교와 같은 값), LoQ·중심이 NaN 이면 NaN.
    sigma_rep_log = verdict_log 의 회차 항 (Δ_log = log10(1 + r) + sigma_rep_log), log 판정이 된 ITEM 만
    (0값·부호 섞임이면 NaN)."""
    out = {**dict.fromkeys(LOG_COLS, np.nan), "log_reason": ""}
    loq = float(res.get("LoQ", np.nan))
    doe_c = float(res.get("por_median", np.nan)) + float(res.get("center", np.nan))
    if np.isfinite(loq) and np.isfinite(doe_c):
        out["below_linear_loq"] = bool(abs(doe_c) < loq)
    out["ci_half_over_delta"] = _ci_half_over_delta(res)
    vals = np.concatenate([Y.ravel(), z])
    causes = [c for c, bad in (("0값 있음", (vals == 0).any()),
                               ("부호 섞임", (vals > 0).any() and (vals < 0).any())) if bad]
    if causes:
        return {**out, "verdict_log": V_EXCLUDED, "log_reason": "; ".join(causes)}
    lr = judge_log(Y, z, r)
    L = np.log10(np.abs(Y))
    ok = np.isfinite(L).all(axis=1)
    rho = (_size_rho(np.log10(np.abs(Y[ok].mean(axis=1))), np.ptp(L[ok], axis=1))
           if Y.shape[1] > 1 and ok.sum() >= 3 else np.nan)
    return {**out, "verdict_log": lr["verdict"], "center_log": lr["center"], "ci_low_log": lr["ci_low"],
            "ci_high_log": lr["ci_high"], "delta_log": lr["delta"], "ci_half_over_delta_log": _ci_half_over_delta(lr),
            "spearman_size_jitter_log": rho, "log_reason": lr["reason"],
            **({} if lr["verdict"] == V_EXCLUDED else {"sigma_die_log": lr["sigma_die"], "sigma_run_log": lr["sigma_run"]}),
            "policy_margin_log": float(np.log10(1 + r)), "sigma_rep_log": lr["sigma_rep_log"]}


LOG_TARGET_STATUSES = (ST_SIZE_JITTER, ST_SIZE_JITTER_POS)


def _text(v) -> str:
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()


def log_target_statuses(status) -> list[str]:
    """status(';' 구분)에 들어 있는 LOG_TARGET_STATUSES (LOG_TARGET_STATUSES 순서)."""
    parts = {p.strip() for p in _text(status).split(";")}
    return [s for s in LOG_TARGET_STATUSES if s in parts]


def verdict_log_differs(verdict, verdict_log) -> bool:
    """verdict 와 verdict_log 가 둘 다 값이 있고 다르면 True. verdict_log 가 판정 제외·빈칸이면 False."""
    v, vl = _text(verdict), _text(verdict_log)
    return bool(v and vl and vl != V_EXCLUDED and v != vl)


def is_log_target(status, verdict=None, verdict_log=None) -> bool:
    """log 진단 대상 (fail_evidence log_diag.png, log_compare): status 에 작을수록·클수록 흔들림이 있거나
    verdict ≠ verdict_log (verdict_log_differs)."""
    return bool(log_target_statuses(status)) or verdict_log_differs(verdict, verdict_log)


def final_verdict(status, verdict, verdict_log) -> tuple[str, str]:
    """최종 판정 (verdict_final, verdict_basis).

    선형 먼저, 동등이 아닌 log 후보만 log 로 재판정.
    - verdict 가 '동등'이면 (verdict, 'linear') — log 와 무관.
    - 동등이 아니고 status(';' 구분)에 ST_LOG_CANDIDATE('log 후보')가 있고 verdict_log 에 값이 있고
      (NaN·빈칸 아님) V_EXCLUDED('판정 제외')가 아니면 (verdict_log, 'log').
    - 그 밖은 (verdict, 'linear').
    """
    if _text(verdict) == "동등":
        return verdict, "linear"
    vl = _text(verdict_log)
    if ST_LOG_CANDIDATE in {p.strip() for p in _text(status).split(";")} and vl and vl != V_EXCLUDED:
        return vl, "log"
    return verdict, "linear"


def add_final_verdict(res: pd.DataFrame) -> pd.DataFrame:
    """res 에 verdict_final·verdict_basis 열을 verdict 바로 뒤에 넣어 돌려준다."""
    vl = res["verdict_log"] if "verdict_log" in res else pd.Series(np.nan, index=res.index)
    st = res["status"] if "status" in res else pd.Series("", index=res.index)
    fb = [final_verdict(s, v, l) for s, v, l in zip(st, res["verdict"], vl)]
    res = res.drop(columns=["verdict_final", "verdict_basis"], errors="ignore")
    at = res.columns.get_loc("verdict") + 1
    res.insert(at, "verdict_final", [f for f, _ in fb])
    res.insert(at + 1, "verdict_basis", [b for _, b in fb])
    return res


def verdict_col(df: pd.DataFrame) -> pd.Series:
    """판정 소비처가 쓸 판정 값: verdict_final, 열이 없는 옛 CSV 면 verdict."""
    return df["verdict_final"] if "verdict_final" in df else df["verdict"]


def load_levels(path: str, encoding: str) -> dict[str, ItemInfo]:
    lv = read_csv_auto(Path(path), encoding)
    lv.columns = [c.strip().upper() for c in lv.columns]
    lv = lv.rename(columns={"SCALE": "CALCVAL", "변형": "DERIVED"})
    cv = pd.to_numeric(lv["CALCVAL"], errors="coerce") if "CALCVAL" in lv else pd.Series(np.nan, index=lv.index)
    dv = (lv["DERIVED"].astype(str).str.strip().str.upper().isin({"Y", "YES", "1", "TRUE", "O", "변형"})
          if "DERIVED" in lv else pd.Series(False, index=lv.index))
    levels, bad = {}, []
    for it, txt, c, der in zip(lv["ITEM"].astype(str).str.strip(), lv["LEVEL"], cv, dv):
        parsed = parse_level(txt)
        if parsed or der:
            L, kind = parsed or (np.nan, "")
            levels[it] = ItemInfo(L, kind, float(c) if np.isfinite(c) and c != 0 else None, bool(der))
        else:
            bad.append(f"{it}={txt}")
    info = list(levels.values())
    print(f"item_info: ITEM {len(levels):,}개 (변형 {sum(i.derived for i in info):,}, CALCVAL 있음 "
          f"{sum(not i.derived and bool(i.calcval) for i in info):,}, CALCVAL 없음 "
          f"{sum(not i.derived and not i.calcval for i in info):,})" + (f", 읽지 못한 행 {len(bad)}개: {bad[:5]}" if bad else ""))
    return levels


def add_common_args(ap: argparse.ArgumentParser) -> None:
    """POR/DOE 판정에 공통으로 쓰는 명령행 인자를 등록한다."""
    ap.add_argument("--por", nargs="+", action="append", required=True,
                    help="POR 1회분 (파일이나 폴더). 회차마다 --por 를 따로: --por run1/ --por run2/ --por run3/")
    ap.add_argument("--doe", nargs="+", required=True, help="DOE 1회분 (파일이나 폴더)")
    ap.add_argument("--r", type=float, default=0.05, help="허용폭 = r × |POR| + POR 회차 흔들림 (기본 0.05)")
    ap.add_argument("--level", help="item_info CSV: ITEM,LEVEL,CALCVAL,DERIVED. 장비 분해능·정확도와 blank 환산에 씀")
    ap.add_argument("--blank", nargs="*", default=[], help="blank 데이터 (README 'blank 넣기'). LoQ 하한으로만 씀")
    ap.add_argument("--blank-map", help="CSV ITEM,BLANK_ITEM. 없으면 같은 이름끼리 연결")
    ap.add_argument("--key", default="WAFERID,COORD_X_Y,ITEM")
    ap.add_argument("--encoding", default="auto")


def load_wide(a: argparse.Namespace) -> tuple[pd.DataFrame, list[str], dict]:
    """POR 회차별·DOE 중앙값을 die/ITEM 키로 맞춘 wide 표와 POR 열, UNIT을 돌려준다."""
    key = a.key.split(",")
    runs, units = [], {}
    for i, paths in enumerate(a.por):
        df = load_side(paths, f"POR{i + 1}", a.encoding)
        if i == 0:
            units = df.groupby("ITEM")["UNIT"].first().to_dict()      # 표시용
        runs.append(df.groupby(key)["DATA"].median().rename(f"POR{i + 1}"))
    doe = load_side(a.doe, "DOE", a.encoding).groupby(key)["DATA"].median().rename("DOE")
    wide = pd.concat(runs + [doe], axis=1, join="inner").reset_index()
    por_cols = [f"POR{i + 1}" for i in range(len(a.por))]
    print(f"POR {len(por_cols)}회 + DOE, 모든 회차에 있는 die·ITEM {len(wide):,}개, ITEM {wide['ITEM'].nunique():,}개")
    return wide, por_cols, units


def judge_item(item: str, g: pd.DataFrame, por_cols: list[str], units: dict, r: float,
               levels: dict[str, ItemInfo], blank: pd.DataFrame, bmap: dict) -> tuple[dict, np.ndarray]:
    """ITEM 하나에 level/blank를 연결해 판정하고, 결과 행(끝에 데이터 상태 열)과 튀는 die 표시를 돌려준다."""
    Y, z = g[por_cols].to_numpy(float), g["DOE"].to_numpy(float)
    info, lim, extra = levels.get(item), None, {}
    bitem = bmap.get(item, item)
    if bitem in blank.index:
        lim3 = blank_limits(blank.loc[bitem])
        if lim3:
            lim = lim3[1:]
            extra["blank_item"] = bitem
    res, mask = judge(Y, z, r, lim, info)
    if lim:
        extra["verdict_no_blank"] = judge(Y, z, r, None, info)[0]["verdict"]
    status = item_status(Y, z, res["delta"])
    prec = meas_precision(*(res.get(k, np.nan) for k in ("sigma_die", "sigma_run", "por_median", "delta")))
    logs = log_columns(Y, z, r, res)
    return {"ITEM": item, "UNIT": units.get(item), **res, **extra, **status, **prec, **logs}, mask


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--por", nargs="+", action="append", required=True,
                    help="POR 1회분 (파일이나 폴더). 회차마다 --por 를 따로: --por run1/ --por run2/ --por run3/")
    ap.add_argument("--doe", nargs="+", required=True, help="DOE 1회분 (파일이나 폴더)")
    ap.add_argument("--r", type=float, default=0.05, help="허용폭 = r × |POR| + POR 회차 흔들림 (기본 0.05)")
    ap.add_argument("--level", help="item_info CSV: ITEM,LEVEL,CALCVAL,DERIVED. 장비 분해능·정확도와 blank 환산에 씀")
    ap.add_argument("--blank", nargs="*", default=[], help="blank 데이터 (README 'blank 넣기'). LoQ 하한으로만 씀")
    ap.add_argument("--blank-map", help="CSV ITEM,BLANK_ITEM. 없으면 같은 이름끼리 연결")
    ap.add_argument("--key", default="WAFERID,COORD_X_Y,ITEM")
    ap.add_argument("--encoding", default="auto")
    ap.add_argument("--out", default="por_doe_out")
    a = ap.parse_args()
    if len(a.por) < 2:
        sys.exit("POR은 2회 이상 필요합니다 (--por 를 회차마다 따로)")
    key = a.key.split(",")
    die_cols = [k for k in key if k != "ITEM"]

    wide, por_cols, units = load_wide(a)

    blank = load_blank(a.blank, a.encoding) if a.blank else pd.DataFrame(columns=["BLANK_ITEM"])
    blank = blank.set_index("BLANK_ITEM")
    bmap = {}
    if a.blank_map:
        mp = read_csv_auto(Path(a.blank_map), a.encoding)
        mp.columns = [c.strip().upper() for c in mp.columns]
        bmap = dict(zip(mp["ITEM"], mp["BLANK_ITEM"]))
    levels = load_levels(a.level, a.encoding) if a.level else {}

    rows, outl = [], []
    for item, g in wide.groupby("ITEM", sort=False):
        res, mask = judge_item(item, g, por_cols, units, a.r, levels, blank, bmap)
        rows.append(res)
        if mask.any():
            outl.append(g.loc[mask, die_cols + ["ITEM"] + por_cols + ["DOE"]])

    first = ["ITEM", "UNIT", "zone", "verdict", "reason"]
    res = pd.DataFrame(rows)
    tail = STATUS_COLS + PRECISION_COLS + LOG_COLS
    res = res[first + [c for c in res.columns if c not in first + tail] + tail]
    res = add_final_verdict(res)
    res = res.sort_values(["verdict", "ITEM"], key=lambda s: s.map(ORDER) if s.name == "verdict" else s)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "items.csv", index=False, encoding="utf-8-sig")
    (pd.concat(outl) if outl else pd.DataFrame(columns=die_cols + ["ITEM"])).to_csv(
        out / "outlier_dies.csv", index=False, encoding="utf-8-sig")

    print(f"\n판정 (허용폭 ±{a.r:.0%} + POR 회차 흔들림, 중앙값 TOST, LoQ 미만은 '<LoQ 보고 일치')")
    print(pd.crosstab(res["zone"], res["verdict"], margins=True, margins_name="합계").to_string())
    bad = reason_group(res.loc[res["verdict"] != "동등", "reason"]).value_counts()
    if len(bad):
        print("\n동등이 아닌 사유")
        print(bad.to_string())
    n_lv = int(res.get("level_check", pd.Series(dtype=str)).astype(str).str.startswith("불일치").sum())
    if n_lv:
        print(f"\n경고: CALCVAL로 환산한 실제 값이 LEVEL 자릿수와 다른 ITEM {n_lv}개 (level_check 열)")
    print(f"\n결과: {out / 'items.csv'}, {out / 'outlier_dies.csv'}  →  요약: python summarize.py {out / 'items.csv'}")


if __name__ == "__main__":
    main()
