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
     --level 의 A·V ITEM 장비 정확도 폭(accuracy_margin, GUM 4.3.7)은 기본 판정에 쓰지 않는다.
       Δ' = max(Δ, accuracy_margin) 의 TOST 판정을 verdict_with_accuracy 에 남기고 (정량 zone 만),
       LoQ 근처 ITEM 에서만 accuracy 옵션(5)이 쓴다. 그 밖은 참고
   정량 (|POR| ≥ LoQ): 신뢰구간이 ±Δ 안 → 동등, 통째로 밖 → 차이, 걸침 → 미결
   LoQ 미만: 값은 "<LoQ"로 보고한다 (IUPAC). DOE 수준 구간 = POR 수준 중앙값 + [ci_low, ci_high] (loq_verdict).
     신뢰구간이 ±Δ 안 → 동등. DOE 구간이 통째로 LoQ 이상이 아니면 (LoQ 미만이거나 LoQ 에 걸침) → 동등
     ("<LoQ 보고 일치"). DOE 구간이 통째로 LoQ 이상이고 신뢰구간이 통째로 ±Δ 밖 → 차이 (보고가 숫자로 바뀜),
     ±Δ 에 걸침 → 미결
   판정 제외: 판정할 것이 없는 ITEM. 맞는 원인 모두를 아래 순서로 '; ' 구분해 reason에 적는다 (EXCLUSION_CAUSES)
     (1) 중심·신뢰구간 NaN/inf
     (2) 회차 0값: POR 회차나 DOE 하나가 die 절반 넘게 정확히 0인데 다른 쪽 하나라도 절반 넘게 0이 아님 (이름을 적음)
     (3) 모든 값 같음: POR·DOE 값이 하나뿐
     (4) die 산포 0 (sigma_die = 0 또는 고정값 비율 > 50%, status '산포 0'과 같은 비율): 정량 zone 이고
         데이터가 거칠 때만 (분해능 step ≥ 0.1 Δ, status '분해능 부족'과 같은 검사, 또는 계산 불가).
         그 밖은 그대로 TOST (신뢰구간이 한 점이어도 된다)
     (5) POR 중앙값 0이고 sigma_run 0: 정량 zone 일 때만, 곧 LoQ 가 0이거나 유효하지 않을 때만
     LoQ 미만이면 (4)(5)는 보지 않고 LoQ 판정으로 간다. 그 밖은 zone 판정: LoQ 미만은 Δ와 무관하게 판정하고,
     정량은 Δ가 0 이하·NaN일 때만 판정 제외

4. 참고 (판정에 안 씀): t-test (NIST 7.3.1.1), POR 회차끼리 t-test, 튀는 die (|d − 중앙값| > 5 robust σ),
   ITEM 분류와 판정 길 (classify.py, CLASS_COLS. POR 값만 본다. --abs-tol 은 절대 허용폭 참고 판정에만)

5. 최종 판정 verdict_final (final_verdict): 위 판정(verdict, 1·2단계)이 동등이면 그대로. 아니면 3단계로 ITEM 의
   판정 길(route, classify.py 가 POR 값만 보고 정함)의 판정 (ROUTE_METHODS): 한계 비교 verdict_limit, 절대 허용폭
   verdict_abs, log TOST verdict_log (Δ_log = log10(1 + r) + sigma_rep_log), 선형 TOST 이고 cls_level 바닥 근처면
   verdict_with_accuracy (Δ' = max(Δ, accuracy_margin)). 그 판정이 동등·차이·미결이 아니면 (판정 제외·빈 칸, 제외·LoQ 판정
   길) 1·2단계 판정. verdict_basis = 정한 방법 (linear, loq, log, accuracy, abs, limit).
   verdict_final_log_run (참고): log TOST 길에 verdict_log_run (Δ_log_run = log10(1 + r) + t·√(1+1/J)·sigma_run_log).
   허용폭 민감도 (rescaled_verdicts, 장표의 믿을 근거): 허용폭을 모두 s 배로 바꿔 1·2단계·판정 길 열을 다시 판정한
   최종 판정. 한계 비교 verdict_limit 은 die 가 있어야 해 그대로
   scale (--groups ITEM,group 과 --scales group,scale): 표의 log·linear 는 그대로, 표에 없거나 auto 인 그룹은 이번 실행의
   그 그룹 ITEM 으로 정한다 (auto→log·auto→linear, scales_auto.csv). classify 의 cls_scale 이 표의 log·linear 를 따른다
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from infra_compare import blank_limits, load_blank, load_side, read_csv_auto, read_groups, read_pairs

Z90 = 1.645
Z95 = -float(stats.norm.ppf(0.025))     # scipy theilslopes 와 같은 값
K_LOD, K_LOQ = 3.29, 10.0
MIN_DIE = 10
OUTLIER_K = 5.0
RUN_JITTER_OVER_DELTA = 1.0     # 회차 흔들림: die별 회차 범위 중앙값 ≥ 이 배수 × Δ
SIZE_JITTER_RHO = -0.5          # 작을수록 흔들림: Spearman ρ(크기, log 범위) ≤ 이 값
SIZE_JITTER_RHO_POS = 0.5       # 클수록 흔들림: Spearman ρ(크기, log 범위) ≥ 이 값
SIZE_JITTER_MIN_DIE = 10
LOG_DECADES_MIN = 1.0           # log 후보: decades ≥ 이 값 그리고 log_fit > LOG_FIT_MIN
LOG_FIT_MIN = 0.1               # log 후보: log_fit > 이 값 (|skew_lin| − |skew_log|, log 쪽이 이만큼은 더 대칭이어야)
LOG_FIT_MIN_SCALE = 0.0         # scale log·auto→log ITEM 과 auto 그룹 결정: log_fit > 이 값 (그룹이 log 라 문턱을 낮춤)
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
# 참고 열 (판정에 안 씀). 문턱값은 시뮬레이션으로 정함 (설계 lab/results.md Q2, Q3)
LOQ_REF_COLS = ["loq_ratio", "rsd_pct", "resolution_pct"]
NOISE_COLS = ["noise_slope", "noise_slope_lo", "noise_slope_hi", "noise_slope_low", "noise_slope_high", "noise_pattern"]
SHAPE_REF_COLS = ["spread_robust", *NOISE_COLS]
NOISE_SPREAD_MIN = 0.3          # 잡음 모양: spread_robust 가 이만큼은 넓어야 기울기를 읽는다 (lab Q2)
NOISE_MIN_DIE = 10              # 잡음 모양: 평균·SD 가 양수인 die 수 하한
NOISE_BEND_MIN = 0.7            # 꺾임: 아래 절반과 위 절반 기울기 차 > 이 값
NP_UNKNOWN, NP_CONSTANT, NP_PROPORTIONAL = "판별 불가", "일정", "비례"
NP_UP, NP_DOWN, NP_BETWEEN = "위로 갈수록 벌어짐", "아래로 갈수록 벌어짐", "사이"
NOISE_PATTERNS = (NP_UNKNOWN, NP_CONSTANT, NP_PROPORTIONAL, NP_UP, NP_DOWN, NP_BETWEEN)
NOISE_BEND = " (꺾임)"
SPREAD_IQR_FACTOR = 3.45        # 정규분포에서 3.45 × IQR = P1~P99 폭
# 판정력 = ci_half_over_delta 구간 (위 끝 포함). 같은 ITEM 이 동등으로 나올 확률 98%, 61%, 8% (lab Q3)
JUDGEABILITY_BANDS = ((0.5, "안정"), (0.8, "주의"), (np.inf, "불안정"))
LOG_COLS = ["verdict_log", "center_log", "ci_low_log", "ci_high_log", "delta_log", "ci_half_over_delta",
            "ci_half_over_delta_log", "log_reason",      # 0 없고 부호 하나인 ITEM 참고용
            "sigma_die_log", "sigma_run_log",            # 분석용, 판정에 안 씀
            "sigma_rep_log"]                             # log 판정의 회차 항
# 참고: 회차 항을 선형처럼 t·√(1+1/J)·sigma_run_log 로 둔 log 판정 (log 허용폭 결정용)
LOG_RUN_COLS = ["verdict_log_run", "delta_log_run"]
POR_MEAN_RE = re.compile(r"POR\d+_mean")
# ITEM 분류와 판정 길 (classify.py, 참고, 판정에 안 씀). classify.AXES 열 순서 + route + 판정 길 참고 결과
CLASS_COLS = ("cls_valid", "cls_sign", "cls_level", "cls_resolution", "cls_shape", "cls_noise", "cls_scale", "cls_run",
              "route", "verdict_abs", "abs_delta", "verdict_limit", "limit_share_por", "limit_share_doe", "limit_p",
              "route_note")
# items.csv 열 순서의 유일한 출처: 묶음 순서대로, 묶음 안은 적힌 순서. POR_MEAN_RE 는 맞는 열을 원래 순서로.
# 표에 없는 열은 맨 끝에 원래 순서로 붙는다.
COLUMN_GROUPS: tuple[tuple[str, tuple[str | re.Pattern, ...]], ...] = (
    ("identity", ("ID", "ITEM", "UNIT")),
    ("verdicts", ("verdict_final", "verdict_basis", "verdict_final_log_run", "scale", "verdict", "verdict_log",
                  "verdict_log_run", "verdict_with_accuracy",
                  "verdict_no_blank", "zone", "reason", "log_reason", "status")),
    ("TOST", ("n_die", "center", "ci_low", "ci_high", "delta", "policy_margin", "run_margin", "delta_source",
              "ci_half_over_delta")),
    ("LoQ", ("por_median", "doe_center", "LoQ", "LoD", "limit_source", *LOQ_REF_COLS)),
    ("values", (POR_MEAN_RE, "DOE_mean")),
    ("noise", ("sigma_die", "sigma_run", *PRECISION_COLS, "n_outlier_die", "judgeability")),
    ("data state", tuple(METRIC_COLS)),
    ("shape", (*SHAPE_COLS, "mean_median_ratio", *SHAPE_REF_COLS)),
    ("log", ("center_log", "ci_low_log", "ci_high_log", "delta_log", "delta_log_run", "ci_half_over_delta_log",
             "sigma_rep_log",
             "sigma_die_log", "sigma_run_log")),
    ("reference", ("ttest", "ttest_p", "por_ttest_sig",
                   "spec_status", "level_check", "range_por", "range_doe", "spec_resolution", "accuracy_margin",
                   "blank_item", "blank_status", "blank_LoQ_item")),
    ("classes", CLASS_COLS),
)
FAMILY_REGEX = r"^([A-Za-z]+)"


def order_columns(cols) -> list[str]:
    """COLUMN_GROUPS 순서로 cols 를 늘어놓는다. 표에 없는 열은 끝에 원래 순서로."""
    cols = list(cols)
    out = []
    for _, group in COLUMN_GROUPS:
        for entry in group:
            out += [c for c in cols if (c == entry if isinstance(entry, str) else entry.fullmatch(c))]
    return out + [c for c in cols if c not in out]


def anon_ids(items: pd.Series, family_regex: str = FAMILY_REGEX,
             keep_family: bool = False) -> tuple[pd.Series, pd.Series]:
    """(FAMILY, ID). FAMILY = ITEM 에서 family_regex 첫 묶음 (못 뽑으면 '?'), keep_family 가 아니면 항목군 이름
    순서의 F01, F02, ... ID = FAMILY + '_I' + ITEM 이름 순서 번호 4자리. 같은 ITEM 목록이면 실행마다 같다."""
    names = items.astype(str)
    fam = names.str.extract(family_regex, expand=False).fillna("?")
    if not keep_family:
        fam = fam.map({f: f"F{i + 1:02d}" for i, f in enumerate(sorted(fam.unique()))})
    no = {it: i + 1 for i, it in enumerate(sorted(names))}
    return fam, fam + "_" + names.map(lambda it: f"I{no[it]:04d}")


def dc_jobs() -> int:
    """병렬 작업 수: 환경변수 DC_JOBS. 없거나 비었으면 os.cpu_count() or 1, 숫자가 아니거나 1 미만이면 1."""
    raw = os.environ.get("DC_JOBS", "").strip()
    if not raw:
        return os.cpu_count() or 1
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def pool_map(fn, args_list, jobs: int | None = None) -> list:
    """[fn(*a) for a in args_list] 와 같은 결과를 같은 순서로 돌려준다.
    jobs(기본 dc_jobs()) ≤ 1 이거나 일이 1개 이하면 직렬, 아니면 fork Pool.starmap(입력 순서 유지).
    fork 를 못 쓰는 플랫폼이면 직렬. fn 은 자식 프로세스로 넘어가므로 모듈 최상위 함수여야 한다.
    matplotlib 백엔드는 건드리지 않는다."""
    args_list = list(args_list)
    jobs = dc_jobs() if jobs is None else jobs
    if jobs <= 1 or len(args_list) <= 1:
        return [fn(*a) for a in args_list]
    try:
        ctx = multiprocessing.get_context("fork")
    except ValueError:
        return [fn(*a) for a in args_list]
    with ctx.Pool(processes=min(jobs, len(args_list))) as pool:
        return pool.starmap(fn, args_list, chunksize=max(1, len(args_list) // (jobs * 4)))


POR_GAP_NOISE_K = 3            # 조건 불안정: 짝지은 회차 차 ≥ 이 배수 × 회차 중앙값 차의 표준오차
ST_OK, ST_UNSTABLE, ST_RESOLUTION, ST_FLAT = "정상", "조건 불안정", "분해능 부족", "산포 0"
ST_RUN_JITTER, ST_SIZE_JITTER, ST_SIZE_JITTER_POS = "회차 흔들림", "작을수록 흔들림", "클수록 흔들림"
ST_LOG_CANDIDATE, ST_BIMODAL = "log 후보", "두 덩어리"     # 분포 모양 (SHAPE_COLS)
ST_NEAR_LOQ = "LoQ 근처"      # LoQ ≤ |POR 중앙값| < LoQ / (10 r): 1회 측정 잡음(LoQ/10)이 허용폭 r × |POR| 보다 큼
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


def level_name(info: ItemInfo) -> str:
    """LEVEL 을 단위 접두어로 다시 쓴 이름 ('10 nA' → '10nA'). 읽지 못한 LEVEL (변형 ITEM) 이면 빈 칸."""
    if not np.isfinite(info.L) or info.L <= 0:
        return ""
    f, pre = max(((f, p) for f, p in SI if f <= info.L * 1.0001), default=(1.0, ""))
    return f"{info.L / f:g}{pre}{info.kind}"


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


def near_loq(por_median: float, loq: float, r: float) -> bool:
    """LoQ ≤ |POR 중앙값| < LoQ / (10 r). r ≤ 0 이면 위쪽 끝이 없다. 값이 NaN 이면 False."""
    upper = loq / (10 * r) if r > 0 else np.inf
    return bool(loq <= abs(por_median) < upper)


def item_status(Y: np.ndarray, z: np.ndarray, delta: float, loq: float = np.nan, r: float = np.nan) -> dict:
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
    두 덩어리: bimodality_log > BIMODAL_BC_MIN 그리고 die ≥ BIMODAL_MIN_DIE (Open 코드(|x| ≥ 1E+90) die는 세지 않음).
    LoQ 근처: near_loq(POR 중앙값, loq, r). loq·r 를 안 주면 (NaN) 보지 않는다. 판정(judge)과 다른 status는 바꾸지 않는다."""
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
    if near_loq(med, loq, r):
        names.append(ST_NEAR_LOQ)
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


def _pct_of_median(x: float, por_median: float) -> float:
    return 100 * x / abs(por_median) if por_median != 0 and np.isfinite(por_median) else np.nan


def loq_ref(por_median: float, loq: float, resolution_step: float) -> dict:
    """LOQ_REF_COLS. LoQ = K_LOQ × σ 라서 rsd_pct = 100 × σ / |POR 중앙값| (1회 측정 상대 정밀도).
    % 열은 por_median 이 0·NaN 이면 NaN, loq_ratio 는 LoQ 가 0 이하·NaN 이면 NaN."""
    return {"loq_ratio": abs(por_median) / loq if loq > 0 else np.nan,
            "rsd_pct": _pct_of_median(loq / K_LOQ, por_median),
            "resolution_pct": _pct_of_median(resolution_step, por_median)}


def spread_robust(x: np.ndarray) -> float:
    """SPREAD_IQR_FACTOR × IQR(log10|x|), 0 이 아닌 유한한 x 로 (4개 미만이면 NaN). 몇 die 만 튀어도 거의 안 변한다."""
    lg = np.log10(np.abs(x[np.isfinite(x) & (x != 0)]))
    if lg.size < 4:
        return np.nan
    q1, q3 = np.percentile(lg, [25, 75])
    return float(SPREAD_IQR_FACTOR * (q3 - q1))


def _tie_term(v: np.ndarray) -> float:
    c = np.unique(v, return_counts=True)[1]
    return float((c * (c - 1) * (2 * c + 5)).sum())


def _pair_slopes(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    dx, dy = x[:, None] - x, y[:, None] - y
    pair = np.triu(dx != 0, k=1)
    return dy[pair] / dx[pair] + 0.0       # −0.0 → 0.0: 같은 값끼리 정렬 순서가 바뀌어도 결과 글자가 같게


def theil_sen(x: np.ndarray, y: np.ndarray, interval: bool = True) -> tuple[float, float, float]:
    """(기울기, 95% 구간 아래, 위). scipy.stats.theilslopes 와 같은 값 (구간은 Sen 1968 식 2.6), 절편 계산 없이.
    x 가 모두 같거나 점이 3개 미만이면 NaN. interval=False 면 구간은 NaN (계산 안 함)."""
    if x.size < 3 or np.ptp(x) == 0:
        return np.nan, np.nan, np.nan
    if not interval:
        return float(np.median(_pair_slopes(x, y))), np.nan, np.nan
    slopes = np.sort(_pair_slopes(x, y))
    n, nt = x.size, slopes.size
    slope = float((slopes[(nt - 1) // 2] + slopes[nt // 2]) / 2)        # np.median 과 같은 값
    var = (n * (n - 1) * (2 * n + 5) - _tie_term(x) - _tie_term(y)) / 18
    if var < 0:
        return slope, np.nan, np.nan
    half = Z95 * np.sqrt(var)
    lo, hi = max(int(np.round((nt - half) / 2)) - 1, 0), min(int(np.round((nt + half) / 2)), nt - 1)
    return slope, float(slopes[lo]), float(slopes[hi])


def noise_pattern(spread: float, n_die: int, lo: float, hi: float, low: float, high: float) -> str:
    """잡음 크기가 값에 따라 어떻게 바뀌나 (NOISE_PATTERNS). 기울기 구간 [lo, hi] 가 0·1 을 어디에 두는지로 정한다.
    0 과 1 을 둘 다 품으면 어느 쪽인지 못 정해 판별 불가. 판별된 것만 아래·위 절반 기울기 차로 꺾임을 붙인다."""
    if not (spread >= NOISE_SPREAD_MIN and n_die >= NOISE_MIN_DIE and np.isfinite(lo) and np.isfinite(hi)):
        return NP_UNKNOWN
    has0, has1 = lo <= 0 <= hi, lo <= 1 <= hi
    rules = ((has0 and has1, NP_UNKNOWN), (has0, NP_CONSTANT), (has1, NP_PROPORTIONAL),
             (lo > 1, NP_UP), (hi < 0, NP_DOWN), (True, NP_BETWEEN))
    name = next(n for hit, n in rules if hit)
    bend = name != NP_UNKNOWN and abs(low - high) > NOISE_BEND_MIN      # NaN 이면 False
    return name + (NOISE_BEND if bend else "")


def noise_cols(Y: np.ndarray, spread: float) -> dict:
    """NOISE_COLS. log10(die별 POR 회차 SD) 를 log10(die별 POR 회차 평균) 에 대해 Theil-Sen 으로 맞춘 기울기.
    0 근처면 잡음 크기가 값과 무관 (선형 척도), 1 근처면 값에 비례 (log 척도). 평균·SD 가 양수인 die 만 쓴다
    (값이 음수인 ITEM 은 NaN). noise_slope_lo·hi 는 95% 구간, noise_slope_low·high 는 평균이 die 중앙값 아래·위인
    die 로만 맞춘 기울기. spread 는 spread_robust."""
    m, sd = Y.mean(axis=1), Y.std(axis=1, ddof=1)
    ok = (m > 0) & (sd > 0)
    x, y = np.log10(m[ok]), np.log10(sd[ok])
    slope, lo, hi = theil_sen(x, y)
    mid = np.median(x) if x.size else np.nan
    low, high = (theil_sen(x[side], y[side], interval=False)[0] for side in (x < mid, x > mid))
    return {"noise_slope": slope, "noise_slope_lo": lo, "noise_slope_hi": hi, "noise_slope_low": low,
            "noise_slope_high": high, "noise_pattern": noise_pattern(spread, int(ok.sum()), lo, hi, low, high)}


def judgeability(ci_half_over_delta: float) -> str:
    """JUDGEABILITY_BANDS 이름. NaN 이면 빈 문자열."""
    if not np.isfinite(ci_half_over_delta):
        return ""
    return next(name for upper, name in JUDGEABILITY_BANDS if ci_half_over_delta <= upper)


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


LOQ_BELOW, LOQ_ABOVE, LOQ_CROSS = "LoQ 미만", "LoQ 이상", "LoQ 에 걸침"


def loq_side(lo: float, hi: float, loq: float) -> str:
    """구간 [lo, hi] 이 |값| < LoQ 안에 통째로 있나 (LOQ_BELOW), 통째로 |값| ≥ LoQ 쪽에 있나 (LOQ_ABOVE), 걸치나."""
    if -loq < lo and hi < loq:
        return LOQ_BELOW
    return LOQ_ABOVE if lo >= loq or hi <= -loq else LOQ_CROSS


def loq_verdict(center: float, lo: float, hi: float, delta: float, base: float, loq: float) -> tuple[str, str]:
    """2단계 LoQ 판정 (|POR 중앙값| < LoQ). DOE 수준 구간 = base (POR 수준 중앙값) + [lo, hi]."""
    shift = tost(center, lo, hi, delta)[0]
    a, b = base + lo, base + hi
    side = loq_side(a, b, loq)
    span = f"DOE 구간 {a:.4g}~{b:.4g}"
    if shift == "동등":
        return "동등", "<LoQ 보고 일치 (이동이 ±Δ 안)"
    if side == LOQ_BELOW:
        return "동등", "<LoQ 보고 일치 (DOE 구간도 LoQ 미만)"
    if side == LOQ_CROSS:
        return "동등", "<LoQ 보고 일치 (DOE 구간이 LoQ에 걸침)"
    if shift == "차이":
        return "차이", f"{span}가 LoQ({loq:.4g}) 이상이고 이동 {center:+.4g}가 ±Δ({delta:.4g}) 밖"
    return "미결", f"{span}가 LoQ({loq:.4g}) 이상이지만 이동 구간이 ±Δ({delta:.4g})에 걸침"


def reason_group(reason: pd.Series) -> pd.Series:
    """사유에서 숫자를 빼고 종류만 남긴다 (표로 세기 위해). 판정 제외 사유는 괄호 속 값을 뺀다."""
    s = (reason.astype(str)
         .str.replace(r"^shift .*밖$", "shift가 ±Δ 밖", regex=True)
         .str.replace(r"^DOE 구간 .*밖$", "LoQ 미만: DOE 구간 ≥ LoQ이고 이동이 ±Δ 밖", regex=True)
         .str.replace(r"^DOE 구간 .*±Δ\([^)]*\)에 걸침$", "LoQ 미만: DOE 구간 ≥ LoQ, 이동이 ±Δ에 걸침", regex=True))
    return s.where(~s.str.startswith(V_EXCLUDED), s.str.replace(r" \([^)]*\)", "", regex=True))


@dataclass(frozen=True)
class ExclusionFacts:
    """판정 제외 원인 표(EXCLUSION_CAUSES)가 보는 값. Y·z 는 판정하는 값 (log 판정이면 log10|값|),
    zero_sides 는 원값에서 본 회차 0값 (zero_value_sides). LoQ 가 없는 log 판정은 por_median·loq 를 NaN 으로 둔다."""
    Y: np.ndarray
    z: np.ndarray
    center: float
    ci_low: float
    ci_high: float
    sigma_die: float
    sigma_run: float
    por_median: float
    delta: float
    loq: float
    zero_sides: tuple[str, ...]

    @property
    def quant(self) -> bool:
        """정량 zone (|POR 중앙값| ≥ LoQ). judge 의 zone 판정과 같은 비교라 NaN 이면 정량."""
        return not abs(self.por_median) < self.loq


def por_sides(Y: np.ndarray) -> list[tuple[str, np.ndarray]]:
    return [(f"POR{k + 1}", Y[:, k]) for k in range(Y.shape[1])]


def zero_sides(sides: list[tuple[str, np.ndarray]]) -> tuple[str, ...]:
    """die 절반 넘게 정확히 0인 쪽 이름. 다른 쪽 하나라도 die 절반 넘게 0이 아닐 때만, 아니면 ()."""
    zero = [name for name, v in sides if (v == 0).mean() > 0.5]
    return tuple(zero) if any((v != 0).mean() > 0.5 for _, v in sides) else ()


def zero_value_sides(Y: np.ndarray, z: np.ndarray) -> tuple[str, ...]:
    """die 절반 넘게 정확히 0인 POR 회차·DOE 이름 (zero_sides)."""
    return zero_sides(por_sides(Y) + [("DOE", z)])


def _cause_ci(f: ExclusionFacts) -> str | None:
    bad = [k for k, v in (("center", f.center), ("ci_low", f.ci_low), ("ci_high", f.ci_high)) if not np.isfinite(v)]
    return f"중심·신뢰구간 계산 불가 ({', '.join(bad)})" if bad else None


def _cause_zero_sides(f: ExclusionFacts) -> str | None:
    return f"회차 0값 ({', '.join(f.zero_sides)})" if f.zero_sides else None


def _cause_all_same(f: ExclusionFacts) -> str | None:
    return "모든 값 같음" if np.unique(np.concatenate([f.Y.ravel(), f.z])).size == 1 else None


def _cause_flat(f: ExclusionFacts) -> str | None:
    """정량 zone 에서 데이터가 Δ에 비해 거칠 때만 (분해능 step ≥ 0.1 Δ, status '분해능 부족'과 같은 검사, 또는 계산 불가)."""
    if not f.quant:
        return None
    vals = np.unique(np.concatenate([f.Y.ravel(), f.z]))
    step = float(np.diff(vals).min()) if vals.size > 1 else np.nan
    if step < 0.1 * f.delta:        # NaN 이면 False → 거친 쪽
        return None
    if f.sigma_die == 0:
        return "die 산포 0 (σ_die=0)"
    share = flat_share(f.Y.mean(axis=1), f.z)        # items.csv fixed_share 와 같은 값
    return f"die 산포 0 (고정값 {round(100 * share)}%)" if share > 0.5 else None


def _cause_median_zero(f: ExclusionFacts) -> str | None:
    """정량 zone 에서만: 중앙값 0이 정량이면 LoQ 가 0이거나 유효하지 않다는 뜻."""
    return "고정값 (중앙값 0·σ_run 0)" if f.quant and f.por_median == 0 and f.sigma_run == 0 else None


# 판정 제외 원인. 순서가 reason 에 적는 순서
EXCLUSION_CAUSES: tuple[Callable[[ExclusionFacts], str | None], ...] = (
    _cause_ci, _cause_zero_sides, _cause_all_same, _cause_flat, _cause_median_zero)


def excluded_reason(f: ExclusionFacts) -> str | None:
    """zone 판정 전에 보는 판정 제외 사유 (없으면 None). EXCLUSION_CAUSES 중 맞는 원인 모두를 순서대로 '; ' 구분,
    첫 원인만 "판정 제외: " 로 시작. 정량 Δ 검사는 여기서 하지 않음: judge 가 정량 zone 에서 본다."""
    causes = [c for c in (cause(f) for cause in EXCLUSION_CAUSES) if c]
    return f"{V_EXCLUDED}: {'; '.join(causes)}" if causes else None


def _verdict_with_accuracy(center: float, lo: float, hi: float, delta: float, margin: float) -> str | float:
    """Δ' = max(Δ, accuracy_margin) 의 TOST 판정. accuracy 옵션(LoQ 근처 ITEM)이 쓰고 그 밖은 참고. margin 이 없으면 NaN."""
    if not np.isfinite(margin):
        return np.nan
    d = float(np.fmax(delta, margin))
    return tost(center, lo, hi, d)[0] if d > 0 else V_EXCLUDED


def limit_sigma(s_die: float, vals: np.ndarray, spec_resolution: float) -> tuple[float, str]:
    """LoD·LoQ 의 σ 와 출처: POR 반복 sigma_die, 데이터 분해능 / √12, 장비 분해능 / √12 중 가장 큰 것.
    vals 는 정렬된 고유값 (데이터 분해능 = 이웃 차의 최솟값, 값이 하나면 0)."""
    return max([(s_die, "POR 반복"),
                (float(np.diff(vals).min()) / np.sqrt(12) if len(vals) > 1 else 0.0, "데이터 분해능"),
                (spec_resolution / np.sqrt(12), "장비 분해능")], key=lambda t: t[0])


def judge(Y: np.ndarray, z: np.ndarray, r: float, blank_lim=None,
          info: ItemInfo | None = None) -> tuple[dict, np.ndarray]:
    """ITEM 하나 판정. (결과, 튀는 die 표시)"""
    n, J = Y.shape
    R = Y.mean(axis=1)
    level = abs(float(np.median(R)))
    s_die, s_run = robust_noise(Y)
    vals = np.unique(np.concatenate([Y.ravel(), z]))
    sp = spec_terms(info, level, abs(float(np.median(z))))
    s_lim, src = limit_sigma(s_die, vals, sp.get("spec_resolution", 0.0))
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
    why = excluded_reason(ExclusionFacts(Y, z, center, lo, hi, s_die, s_run, out["por_median"], delta, loq,
                                         zero_value_sides(Y, z)))
    if why:
        return {**out, "zone": V_EXCLUDED, "verdict": V_EXCLUDED, "reason": why}, outlier

    if level < loq:
        zone = "검출한계 이하" if level < lod else "검출~정량"
        base = float(np.median(R))
        out.update(zone=zone, doe_center=base + center, range_doe="")   # 바닥 값은 DOE/POR 비가 의미 없어 DOE range를 정하지 않음
        verdict, why = loq_verdict(center, lo, hi, delta, base, loq)
        return {**out, "verdict": verdict, "reason": why}, outlier

    src_d = "정책 + 회차"
    out.update(zone="정량", delta_source=src_d, verdict_with_accuracy=_verdict_with_accuracy(
                   center, lo, hi, delta, sp.get("accuracy_margin", np.nan)))
    if not np.isfinite(delta) or delta <= 0:
        return {**out, "zone": V_EXCLUDED, "verdict": V_EXCLUDED,
                "reason": f"{V_EXCLUDED}: 최종 Δ가 0 이하이거나 유효하지 않음 (Δ={delta:.4g}, 출처 {src_d})"}, outlier
    v, why = tost(center, lo, hi, delta)
    return {**out, "verdict": v, "reason": why}, outlier


def judge_log(Y: np.ndarray, z: np.ndarray, r: float) -> dict:
    """log 판정: L = log10|Y|, w = log10|z| 에서 TOST 만 한다. 값에 0 이 없고 부호가 하나일 때만 부른다.
    die별 d = w − L 회차 평균, 중앙값과 부호검정 90% CI (ci_median). Δ_log = log10(1 + r) + sigma_rep_log
    (t·√(1 + 1/J) 배수 없음). LoQ zone 은 없다: log 값이 0 근처라는 것은 그 단위에서 1 근처라는 뜻일 뿐이라
    단위를 바꾸면 달라진다. blank·장비 사양은 원측정값 단위라 쓰지 않는다.
    die < MIN_DIE 면 미결, excluded_reason (LoQ 가 없어 정량 zone 으로 봄, 중앙값 0 원인 없음) 이나 Δ_log ≤ 0·NaN 이면
    판정 제외.
    참고 판정 verdict_run: 같은 구간을 delta_run = log10(1 + r) + run_factor(J) × sigma_run (선형 Δ 와 같은 꼴) 로 본다.
    sigma_rep_log 는 die 반복 잡음까지 세어 구간 폭과 두 번 들어가므로 이 값과 비교해 고를 수 있게 둔다."""
    L, w = np.log10(np.abs(Y)), np.log10(np.abs(z))
    R = L.mean(axis=1)
    s_die, s_run = robust_noise(L)
    center, lo, hi = ci_median(w - R)
    rep = sigma_rep_log(L)
    policy = float(np.log10(1 + r))
    delta = policy + rep
    delta_run = policy + run_factor(L.shape[1]) * s_run
    out = {"center": center, "ci_low": lo, "ci_high": hi, "delta": delta, "policy_margin": policy,
           "run_margin": rep, "sigma_die": s_die, "sigma_run": s_run, "sigma_rep_log": rep, "delta_run": delta_run,
           "verdict_run": tost(center, lo, hi, delta_run)[0] if np.isfinite(delta_run) and delta_run > 0 else V_EXCLUDED}
    if len(w) < MIN_DIE:
        return {**out, "verdict": "미결", "verdict_run": "미결", "reason": f"die {len(w)}개 (< {MIN_DIE})"}
    why = excluded_reason(ExclusionFacts(L, w, center, lo, hi, s_die, s_run, np.nan, delta, np.nan,
                                         zero_value_sides(Y, z)))
    if why:
        return {**out, "verdict": V_EXCLUDED, "verdict_run": V_EXCLUDED, "reason": why}
    if not np.isfinite(delta) or delta <= 0:
        return {**out, "verdict": V_EXCLUDED, "verdict_run": V_EXCLUDED,
                "reason": f"{V_EXCLUDED}: 최종 Δ가 0 이하이거나 유효하지 않음 (Δ_log={delta:.4g})"}
    v, why = tost(center, lo, hi, delta)
    return {**out, "verdict": v, "reason": why}


def sigma_rep_log(L: np.ndarray) -> float:
    """die별 log 회차 흔들림: median over die of std(die 의 L 회차값, ddof=1). L = log10|Y| (die × 회차).
    die 안에서 유한한 회차 값이 2개 미만인 die 는 빼고, 남는 die 가 없으면 NaN.
    L 이 전부 유한하고 회차가 2개 이상이면 행렬 한 번에 std(axis=1) (빠른 경로, die 0개면 NaN).
    아니면 die 마다 유한한 값만 골라 std 하는 리스트 경로. 두 경로의 값은 같다."""
    if L.ndim == 2 and L.shape[1] >= 2 and np.isfinite(L).all():
        return float(np.median(np.std(L, axis=1, ddof=1))) if L.shape[0] else np.nan
    sds =[float(np.std(v, ddof=1)) for v in (row[np.isfinite(row)] for row in L) if v.size >= 2]
    return float(np.median(sds)) if sds else np.nan


def _ci_half_over_delta(res: dict) -> float:
    lo, hi, delta = (float(res.get(k, np.nan)) for k in ("ci_low", "ci_high", "delta"))
    return (hi - lo) / 2 / delta if np.isfinite(delta) and delta > 0 else np.nan


def log_columns(Y: np.ndarray, z: np.ndarray, r: float, res: dict) -> dict:
    """LOG_COLS 와 LOG_RUN_COLS. 모든 ITEM (status 무관): POR·DOE 값에 0 이 없고 부호가 하나면 log 판정 값을 채운다.
    0 이 있거나 부호가 섞이면 verdict_log 판정 제외, log_reason 에 사유, log 숫자 열 NaN.
    log_reason 은 log 판정이 된 ITEM 이면 judge_log 의 reason.
    분석용 열 (판정에 안 씀): sigma_*_log 는 judge_log 결과의 sigma_die·sigma_run, verdict_log 가 판정 제외면 NaN.
    sigma_run_log (웨이퍼 공통 회차 이동) 은 판정에 안 씀.
    sigma_rep_log = verdict_log 의 회차 항 (Δ_log = log10(1 + r) + sigma_rep_log), log 판정이 된 ITEM 만
    (0값·부호 섞임이면 NaN)."""
    out = {**dict.fromkeys([*LOG_RUN_COLS, *LOG_COLS], np.nan), "log_reason": ""}
    out["ci_half_over_delta"] = _ci_half_over_delta(res)
    vals = np.concatenate([Y.ravel(), z])
    causes = [c for c, bad in (("0값 있음", (vals == 0).any()),
                               ("부호 섞임", (vals > 0).any() and (vals < 0).any())) if bad]
    if causes:
        return {**out, "verdict_log": V_EXCLUDED, "verdict_log_run": V_EXCLUDED, "log_reason": "; ".join(causes)}
    lr = judge_log(Y, z, r)
    return {**out, "verdict_log": lr["verdict"], "center_log": lr["center"], "ci_low_log": lr["ci_low"],
            "ci_high_log": lr["ci_high"], "delta_log": lr["delta"], "ci_half_over_delta_log": _ci_half_over_delta(lr),
            "log_reason": lr["reason"],
            **({} if lr["verdict"] == V_EXCLUDED else {"sigma_die_log": lr["sigma_die"], "sigma_run_log": lr["sigma_run"]}),
            "sigma_rep_log": lr["sigma_rep_log"], "verdict_log_run": lr["verdict_run"], "delta_log_run": lr["delta_run"]}


LOG_TARGET_STATUSES = (ST_SIZE_JITTER, ST_SIZE_JITTER_POS)


def _text(v) -> str:
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()


def _status_parts(status) -> set[str]:
    return {p.strip() for p in _text(status).split(";")}


def log_target_statuses(status) -> list[str]:
    """status(';' 구분)에 들어 있는 LOG_TARGET_STATUSES (LOG_TARGET_STATUSES 순서)."""
    parts = _status_parts(status)
    return [s for s in LOG_TARGET_STATUSES if s in parts]


def verdict_log_differs(verdict, verdict_log) -> bool:
    """verdict 와 verdict_log 가 둘 다 값이 있고 다르면 True. verdict_log 가 판정 제외·빈칸이면 False."""
    v, vl = _text(verdict), _text(verdict_log)
    return bool(v and vl and vl != V_EXCLUDED and v != vl)


def is_log_target(status, verdict=None, verdict_log=None) -> bool:
    """log 진단 대상 (fail_evidence log_diag.png): status 에 작을수록·클수록 흔들림이 있거나
    verdict ≠ verdict_log (verdict_log_differs)."""
    return bool(log_target_statuses(status)) or verdict_log_differs(verdict, verdict_log)


SCALE_ITEM, SCALE_LOG, SCALE_LINEAR, SCALE_AUTO = "item", "log", "linear", "auto"
AUTO_SCALES = {SCALE_LOG: "auto→log", SCALE_LINEAR: "auto→linear"}       # auto 그룹 결정 → items.csv scale 값


def _num(row: Mapping, key: str) -> float:
    try:
        return float(row.get(key))
    except (TypeError, ValueError):
        return np.nan


# 판정 길 (route). classify.py 가 ITEM 마다 POR 값만 보고 정하고, 최종 판정 3단계가 길마다 아래 판정 열을 쓴다
R_EXCLUDED, R_LIMIT, R_ABS, R_LOQ, R_LOG, R_LINEAR = "제외", "한계 비교", "절대 허용폭", "LoQ 판정", "log TOST", "선형 TOST"
LEVEL_NEAR = "바닥 근처"            # classify cls_level: LoQ 근처
LOQ_ZONE_NAMES = ("검출한계 이하", "검출~정량")
JUDGED = ("동등", "차이", "미결")


def route_method(row: Mapping, log_col: str = "verdict_log") -> tuple[str, str] | None:
    """3단계에서 이 ITEM 의 판정 길이 쓰는 (판정 열, verdict_basis). 쓸 열이 없는 길 (제외, LoQ 판정, 선형 TOST) 은 None."""
    route = _text(row.get("route"))
    if route == R_LINEAR:
        return ("verdict_with_accuracy", "accuracy") if _text(row.get("cls_level")) == LEVEL_NEAR else None
    return {R_LIMIT: ("verdict_limit", "limit"), R_ABS: ("verdict_abs", "abs"), R_LOG: (log_col, "log")}.get(route)


def final_verdict(row: Mapping, log_col: str = "verdict_log") -> tuple[str, str]:
    """최종 판정 (verdict_final, verdict_basis). row 는 items.csv 한 행 (verdict, zone, route, cls_level, 판정 길 열).
    1·2단계 판정 verdict 가 동등이면 그대로. 아니면 판정 길의 판정이 동등·차이·미결이면 그것, 아니면 verdict.
    route 가 없는 옛 items.csv 는 verdict 그대로."""
    verdict = _text(row.get("verdict"))
    stage = "loq" if _text(row.get("zone")) in LOQ_ZONE_NAMES else "linear"
    method = None if verdict == "동등" else route_method(row, log_col)
    v = _text(row.get(method[0])) if method else ""
    return (v, method[1]) if v in JUDGED else (verdict, stage)


def add_final_verdict(res: pd.DataFrame) -> pd.DataFrame:
    """res 에 verdict_final·verdict_basis 열을 verdict 바로 뒤에 넣어 돌려준다. 없는 열은 빈 칸으로 본다 (옛 CSV).
    verdict_log_run 열이 있으면 verdict_final_log_run (log TOST 길이 verdict_log_run 을 쓸 때의 최종 판정, 참고용) 도 넣는다."""
    rows = res.to_dict("records")
    fb = [final_verdict(row) for row in rows]
    res = res.drop(columns=["verdict_final", "verdict_basis", "verdict_final_log_run"], errors="ignore")
    at = res.columns.get_loc("verdict") + 1
    res.insert(at, "verdict_final", [f for f, _ in fb])
    res.insert(at + 1, "verdict_basis", [b for _, b in fb])
    if "verdict_log_run" in res:
        res.insert(at + 2, "verdict_final_log_run", [final_verdict(row, "verdict_log_run")[0] for row in rows])
    return res


CI_COLS, LOG_CI_COLS = ("center", "ci_low", "ci_high"), ("center_log", "ci_low_log", "ci_high_log")


def _scaled_tost(row: Mapping, cols: tuple[str, str, str], delta: float, scale: float) -> str | None:
    c, lo, hi = (_num(row, k) for k in cols)
    return tost(c, lo, hi, delta * scale)[0] if np.isfinite([c, lo, hi, delta]).all() and delta > 0 else None


def _scaled_stage12(row: Mapping, scale: float) -> str | None:
    zone, delta = _text(row.get("zone")), _num(row, "delta")
    if zone == "정량":
        return _scaled_tost(row, CI_COLS, delta, scale)
    nums = [_num(row, k) for k in (*CI_COLS, "por_median", "LoQ")]
    if zone in LOQ_ZONE_NAMES and np.isfinite([*nums, delta]).all() and delta > 0:
        c, lo, hi, base, loq = nums
        return loq_verdict(c, lo, hi, delta * scale, base, loq)[0]
    return None


# 허용폭을 바꿔 다시 판정하는 열. verdict_limit 은 한계 밖 die 로 구간을 다시 내야 해 items.csv 만으로는 못 한다
RESCALED: dict[str, Callable[[Mapping, float], str | None]] = {
    "verdict": _scaled_stage12,
    "verdict_log": lambda r, s: _scaled_tost(r, LOG_CI_COLS, _num(r, "delta_log"), s),
    "verdict_abs": lambda r, s: _scaled_tost(r, CI_COLS, _num(r, "abs_delta"), s),
    "verdict_with_accuracy": lambda r, s: _scaled_tost(
        r, CI_COLS, float(np.fmax(_num(r, "delta"), _num(r, "accuracy_margin"))), s),
}


def rescaled_verdicts(items: pd.DataFrame, scale: float) -> pd.Series:
    """허용폭을 모두 scale 배로 바꿨을 때의 최종 판정 (행마다, final_verdict). RESCALED 의 열을 원래 판정이
    동등·차이·미결이고 숫자가 유한할 때만 다시 판정한다. 열이 없거나 숫자가 NaN 이면 그 열은 원래 판정."""
    def rejudge(row: dict) -> str:
        new = {col: fn(row, scale) for col, fn in RESCALED.items() if _text(row.get(col)) in JUDGED}
        return final_verdict({**row, **{k: v for k, v in new.items() if v}})[0]
    return pd.Series([rejudge(r) for r in items.to_dict("records")], index=items.index, name="verdict_final",
                     dtype=object)


AUTO_COLS = ["group", "decision", "n_items", "n_decades_ge_1", "median_log_fit"]
SCALES_AUTO_CSV = "scales_auto.csv"


def read_scales(path) -> dict[str, str]:
    """group,scale 파일 → 그룹 → log·linear·auto. 다른 scale 값이 있으면 종료."""
    t = read_pairs(path, ("group", "scale"))
    t["scale"] = t["scale"].fillna("").str.lower()
    bad = t.loc[~t["scale"].isin((SCALE_LOG, SCALE_LINEAR, SCALE_AUTO)), "group"].tolist()
    if bad:
        sys.exit(f"{path}: scale 은 log, linear, auto 중 하나여야 합니다 (그룹 {', '.join(bad[:5])})")
    return dict(zip(t["group"], t["scale"]))


def auto_decision(decades, log_fit) -> dict:
    """auto 그룹 하나의 결정 (AUTO_COLS 의 group 뒤). n_items = decades·log_fit 이 둘 다 유한한 ITEM 수.
    그중 decades ≥ LOG_DECADES_MIN 이 절반 넘고 그 n_items 개의 log_fit 중앙값 > LOG_FIT_MIN_SCALE 이면 log, 아니면 linear."""
    d, f = np.asarray(decades, float), np.asarray(log_fit, float)
    ok = np.isfinite(d) & np.isfinite(f)
    n, wide = int(ok.sum()), int((d[ok] >= LOG_DECADES_MIN).sum())
    med = float(np.median(f[ok])) if n else np.nan
    return {"decision": SCALE_LOG if wide > n / 2 and med > LOG_FIT_MIN_SCALE else SCALE_LINEAR,
            "n_items": n, "n_decades_ge_1": wide, "median_log_fit": med}


def item_scales(res: pd.DataFrame, groups: dict[str, str], scales: dict[str, str]) -> tuple[pd.Series, pd.DataFrame]:
    """(ITEM 마다 scale, auto 그룹 결정 표 AUTO_COLS). 그룹이 없는 ITEM 은 item, scales 에 없는 그룹은 auto."""
    group = res["ITEM"].astype(str).str.strip().map(groups)
    table = {g: scales.get(g, SCALE_AUTO) for g in group.dropna().unique()}
    auto = pd.DataFrame([{"group": g, **auto_decision(res.loc[group == g, "decades"], res.loc[group == g, "log_fit"])}
                         for g in sorted(table) if table[g] == SCALE_AUTO], columns=AUTO_COLS)
    table.update({g: AUTO_SCALES[d] for g, d in zip(auto["group"], auto["decision"])})
    return group.map(table).fillna(SCALE_ITEM), auto


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
    status = item_status(Y, z, res["delta"], res["LoQ"], r)
    prec = meas_precision(*(res.get(k, np.nan) for k in ("sigma_die", "sigma_run", "por_median", "delta")))
    opts = log_columns(Y, z, r, res)
    spread = spread_robust(Y.mean(axis=1))
    ref = {**loq_ref(res["por_median"], res["LoQ"], status["resolution_step"]), "spread_robust": spread,
           **noise_cols(Y, spread), "judgeability": judgeability(_ci_half_over_delta(res))}
    return {"ITEM": item, "UNIT": units.get(item), **res, **extra, **ref, **status, **prec, **opts}, mask


def _judge_group(item: str, g: pd.DataFrame, por_cols: list[str], units: dict, r: float,
                 levels: dict[str, ItemInfo], blank: pd.DataFrame, bmap: dict,
                 die_cols: list[str]):
    """pool_map 용 최상위 함수: judge_item 결과 행, 튀는 die 표(없으면 None), 분류 사실 (classify.item_facts)."""
    import classify
    res, mask = judge_item(item, g, por_cols, units, r, levels, blank, bmap)
    facts = classify.item_facts(g[por_cols].to_numpy(float), g["DOE"].to_numpy(float), res, r)
    return res, (g.loc[mask, die_cols + ["ITEM"] + por_cols + ["DOE"]] if mask.any() else None), facts


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
    ap.add_argument("--groups", help="ITEM,group 파일. --scales 와 같이 쓰고, 주면 stability/groups.csv 도 쓴다")
    ap.add_argument("--scales", help="group,scale 파일 (scale = log, linear, auto). 그룹마다 log 옵션 대상을 정한다. "
                                     "표에 없는 그룹은 auto, 결정은 scales_auto.csv")
    ap.add_argument("--abs-tol", help="group,abs_delta 파일 (ITEM 단위의 절대 허용폭). 판정 길이 절대 허용폭인 ITEM 의 "
                                      "참고 판정 verdict_abs 에 쓴다 (판정은 그대로). --groups 가 필요")
    ap.add_argument("--out", default="por_doe_out")
    a = ap.parse_args()
    if len(a.por) < 2:
        sys.exit("POR은 2회 이상 필요합니다 (--por 를 회차마다 따로)")
    if a.scales and not a.groups:
        sys.exit("--scales 에는 --groups (ITEM,group 파일) 가 필요합니다")
    if a.abs_tol and not a.groups:
        sys.exit("--abs-tol 에는 --groups (ITEM,group 파일) 가 필요합니다")
    import classify
    abs_tol = classify.read_abs_tol(a.abs_tol) if a.abs_tol else None
    key = a.key.split(",")
    die_cols = [k for k in key if k != "ITEM"]
    import stability        # stability 가 이 모듈의 상수를 쓰므로 여기서 부른다
    plotter = stability.Plotter.start()

    wide, por_cols, units = load_wide(a)

    blank = load_blank(a.blank, a.encoding) if a.blank else pd.DataFrame(columns=["BLANK_ITEM"])
    blank = blank.set_index("BLANK_ITEM")
    bmap = {}
    if a.blank_map:
        mp = read_csv_auto(Path(a.blank_map), a.encoding)
        mp.columns = [c.strip().upper() for c in mp.columns]
        bmap = dict(zip(mp["ITEM"], mp["BLANK_ITEM"]))
    levels = load_levels(a.level, a.encoding) if a.level else {}

    tasks = [(item, g, por_cols, units, a.r, levels, blank, bmap, die_cols)
             for item, g in wide.groupby("ITEM", sort=False)]
    results = pool_map(_judge_group, tasks)
    rows = [res for res, _, _ in results]
    outl = [o for _, o, _ in results if o is not None]
    facts = {res["ITEM"]: f for res, _, f in results}

    res = pd.DataFrame(rows)
    auto = None
    groups = read_groups(a.groups) if a.groups else None
    group_of = None if groups is None else dict(zip(groups["ITEM"], groups["group"]))
    if a.scales:
        res["scale"], auto = item_scales(res, group_of, read_scales(a.scales))
    else:
        res["scale"] = SCALE_ITEM
    res = add_final_verdict(classify.add_columns(res, facts, wide, por_cols, group_of, abs_tol))
    res.insert(0, "ID", anon_ids(res["ITEM"])[1])
    res = res[order_columns(res.columns)]
    res = res.sort_values(["verdict", "ITEM"], key=lambda s: s.map(ORDER) if s.name == "verdict" else s)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "items.csv", index=False, encoding="utf-8-sig")
    outliers = pd.concat(outl) if outl else pd.DataFrame(columns=die_cols + ["ITEM"])
    outliers.to_csv(out / "outlier_dies.csv", index=False, encoding="utf-8-sig")
    if auto is None:
        (out / SCALES_AUTO_CSV).unlink(missing_ok=True)     # 지난 --scales 실행의 결정이 이번 결과처럼 보이지 않게
    else:
        auto.to_csv(out / SCALES_AUTO_CSV, index=False, encoding="utf-8-sig")

    print(f"\n판정 (허용폭 ±{a.r:.0%} + POR 회차 흔들림, 중앙값 TOST, LoQ 미만은 '<LoQ 보고 일치')")
    print(pd.crosstab(res["zone"], res["verdict"], margins=True, margins_name="합계").to_string())
    print("\n최종 판정 (1·2단계 동등은 그대로, 아니면 판정 길의 판정: 한계 비교, 절대 허용폭, log TOST, "
          "바닥 근처는 Δ' = max(Δ, 장비 정확도 폭))")
    print(pd.crosstab([res["route"], res["verdict_basis"]], res["verdict_final"], margins=True,
                      margins_name="합계").to_string())
    changed = res["verdict_final"] != res["verdict_final_log_run"]
    print(f"\n참고: log 허용폭을 선형처럼 (log10(1+r) + t·√(1+1/J)·sigma_run_log) 두면 최종 판정이 바뀌는 ITEM {int(changed.sum())}개 "
          "(verdict_final → verdict_final_log_run)")
    if changed.any():
        print(pd.crosstab(res.loc[changed, "verdict_final"], res.loc[changed, "verdict_final_log_run"]).to_string())
    if auto is not None:
        print("\nscale (--scales)")
        print(res["scale"].value_counts().to_string())
        if len(auto):
            print(f"auto 그룹 결정 ({out / SCALES_AUTO_CSV}, 확인 후 scales 파일에 옮겨 적을 수 있음)")
            print(auto.to_string(index=False))
    print(f"\n{classify.takeaway(res)}")
    bad = reason_group(res.loc[res["verdict"] != "동등", "reason"]).value_counts()
    if len(bad):
        print("\n동등이 아닌 사유")
        print(bad.to_string())
    n_lv = int(res.get("level_check", pd.Series(dtype=str)).astype(str).str.startswith("불일치").sum())
    if n_lv:
        print(f"\n경고: CALCVAL로 환산한 실제 값이 LEVEL 자릿수와 다른 ITEM {n_lv}개 (level_check 열)")
    level_of = {it: level_name(info) for it, info in levels.items()}
    stab = stability.write(out / stability.DIR, res, wide, por_cols, die_cols, outliers, group_of, plotter,
                           level_of=level_of or None, r=a.r)
    print(f"\n측정 안정도 ({out / stability.DIR}): {stability.takeaway(stab, die_cols)}")
    print(f"\n결과: {out / 'items.csv'}, {out / 'outlier_dies.csv'}  →  요약: python summarize.py {out / 'items.csv'}")


if __name__ == "__main__":
    main()
