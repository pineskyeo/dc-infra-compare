"""POR 여러 회(같은 die 재측정) + DOE 1회로 ITEM별 동등 / 차이 / 미결을 판정한다.

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
    (100.0, 115.0, 5e-3, np.nan, np.nan, np.nan),
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


def robust_noise(Y: np.ndarray) -> tuple[float, float]:
    """(sigma_die, sigma_run). sigma_run 은 회차별 중앙값들의 분산에서 die 잡음 몫((π/2) sigma_die² / n)을 뺀 것."""
    n, J = Y.shape
    dd = [Y[:, k + 1] - Y[:, k] for k in range(J - 1)]
    s_die = robust_sigma(np.concatenate([x - np.median(x) for x in dd])) / np.sqrt(2)
    r = np.median(Y - Y.mean(axis=1, keepdims=True), axis=0)
    s_run = float(np.sqrt(max(0.0, r.var(ddof=1) - (np.pi / 2) * s_die ** 2 / n)))
    return s_die, s_run


def run_factor(J: int) -> float:
    """sigma_run 은 회차 J개로 추정해 자유도가 J − 1이라 1.645 대신 t(0.95, J − 1) (J = 3이면 2.92)."""
    return float(stats.t.ppf(0.95, J - 1) * np.sqrt(1 + 1 / J))


def paired_t_p(d: np.ndarray) -> float:
    s = d.std(ddof=1)
    if s == 0:
        return 1.0 if d.mean() == 0 else 0.0
    return float(2 * stats.t.sf(abs(d.mean() / (s / np.sqrt(len(d)))), len(d) - 1))


def ci_median(d: np.ndarray) -> tuple[float, float, float]:
    """중앙값과 부호검정 90% 신뢰구간. 튀는 die의 개수만 영향을 주고 크기는 영향이 없다."""
    if d.std() == 0:
        return (float(d.mean()),) * 3
    n = len(d)
    x = np.sort(d)
    k = int(stats.binom.ppf(0.05, n, 0.5))
    if stats.binom.cdf(k, n, 0.5) > 0.05:
        k -= 1
    k = max(k, 0)
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
    """사유에서 숫자를 빼고 종류만 남긴다 (표로 세기 위해)."""
    return (reason.astype(str)
            .str.replace(r"^shift .*밖$", "shift가 ±Δ 밖", regex=True)
            .str.replace(r"^DOE 중심 .*밖$", "LoQ 미만: DOE 중심 ≥ LoQ이고 이동이 ±Δ 밖", regex=True))


def judge(Y: np.ndarray, z: np.ndarray, r: float, blank_lim=None, info: ItemInfo | None = None) -> tuple[dict, np.ndarray]:
    """ITEM 하나 판정. (결과, 튀는 die 표시)"""
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
    policy, run_term = r * level, run_factor(J) * s_run
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
    v, why = tost(center, lo, hi, delta)
    out.update(zone="정량", delta=delta, delta_source=src_d, verdict_no_accuracy=v0,
               rel_shift=center / level if level else np.nan)
    return {**out, "verdict": v, "reason": why}, outlier


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
        Y, z = g[por_cols].to_numpy(float), g["DOE"].to_numpy(float)
        info, lim, extra = levels.get(item), None, {}
        bitem = bmap.get(item, item)
        if bitem in blank.index:
            lim3 = blank_limits(blank.loc[bitem])
            if lim3:
                lim = lim3[1:]
                extra["blank_item"] = bitem
        res, mask = judge(Y, z, a.r, lim, info)
        if lim:
            extra["verdict_no_blank"] = judge(Y, z, a.r, None, info)[0]["verdict"]
        rows.append({"ITEM": item, "UNIT": units.get(item), **res, **extra})
        if mask.any():
            outl.append(g.loc[mask, die_cols + ["ITEM"] + por_cols + ["DOE"]])

    first = ["ITEM", "UNIT", "zone", "verdict", "reason"]
    res = pd.DataFrame(rows)
    res = res[first + [c for c in res.columns if c not in first]]
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
