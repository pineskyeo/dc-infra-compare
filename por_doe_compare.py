"""POR 여러 회(같은 die 재측정) + DOE 1회로 ITEM별 t-test와 TOST를 같이 낸다.

흔들림 (POR 회차 × die 이원분산분석, NIST e-Handbook 2.4.4)
  sigma_die : 같은 회차 안 die별 1회 측정 흔들림 (잔차)
  sigma_run : 회차마다 전체 평균이 같이 움직이는 크기 (컨택 상태, 온도 등)

구간 (Currie / IUPAC): LoD = 3.29 sigma_die, LoQ = 10 sigma_die, |POR 중앙값| 기준
  LoQ 미만 : 숫자 비교 안 함. die별 |값| ≥ LoQ 여부를 DOE와 POR 1회차로 McNemar 비교
  LoQ 이상 : t-test와 TOST

d = DOE − POR 회차 평균 (die별)
  t-test (NIST 7.3.1.1): t = mean(d) / (sd(d)/√n), 양측 p
  TOST  : 90% 신뢰구간이 ±Δ 안이면 동등
          Δ = 정책 허용폭 + 1.645 × √(1 + 1/J) × sigma_run
          정책 허용폭 = 스펙 폭 × spec_frac (SPECLOW·SPECHIGH 있을 때), 없으면 r × |POR 중앙값|
          튀는 die가 있으면 (sd / robust σ > robust_ratio) 중앙값과 robust σ로 신뢰구간 (NIST 1.3.5.6)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from infra_compare import load_side, mcnemar_p

Z90 = 1.645
MEDIAN_SE = 1.2533
K_LOD, K_LOQ = 3.29, 10.0
MIN_DIE = 10
MISMATCH_MAX = 0.05
ORDER = {"차이": 0, "미결": 1, "동등": 2}


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
    return np.sqrt(ms_e), np.sqrt(max(0.0, (ms_run - ms_e) / n))


def paired_t_p(d: np.ndarray) -> float:
    s = d.std(ddof=1)
    if s == 0:
        return 1.0 if d.mean() == 0 else 0.0
    t = d.mean() / (s / np.sqrt(len(d)))
    return float(2 * stats.t.sf(abs(t), len(d) - 1))


def judge(Y: np.ndarray, z: np.ndarray, spec: tuple[float, float] | None, a: argparse.Namespace) -> dict:
    n, J = Y.shape
    R = Y.mean(axis=1)
    level = abs(float(np.median(R)))
    s_die, s_run = run_anova(Y)
    lod, loq = K_LOD * s_die, K_LOQ * s_die
    d = z - R
    p_t = paired_t_p(d)
    por_pairs = [paired_t_p(Y[:, j] - Y[:, i]) for i in range(J) for j in range(i + 1, J)]
    out = {
        "n_die": n, "n_por_runs": J, "por_median": float(np.median(R)), "doe_median": float(np.median(z)),
        "sigma_die": s_die, "sigma_run": s_run, "sigma_run_df": J - 1, "LoD": lod, "LoQ": loq,
        "mean_d": float(d.mean()), "median_d": float(np.median(d)), "sd_d": float(d.std(ddof=1)),
        "robust_sigma_d": robust_sigma(d),
        "ttest_p": p_t, "ttest": "유의차" if p_t < 0.05 else "유의차 없음",
        "por_ttest_sig": f"{sum(p < 0.05 for p in por_pairs)}/{len(por_pairs)}",
    }
    if n < MIN_DIE:
        return {**out, "zone": "die 부족", "verdict": "미결", "reason": f"die {n}개 (< {MIN_DIE})"}

    if level < loq:
        zone = "검출한계 이하" if level < lod else "검출~정량"
        doe_on, por_on = np.abs(z) >= loq, np.abs(Y[:, 0]) >= loq
        b, c = int((por_on & ~doe_on).sum()), int((~por_on & doe_on).sum())
        p = mcnemar_p(b, c)
        net = (c - b) / n
        base_on = np.abs(Y[:, 1]) >= loq
        out.update(zone=zone, method="McNemar (LoQ 넘는 die)", only_por_die=b, only_doe_die=c, mcnemar_p=p,
                   por_mcnemar_p=mcnemar_p(int((por_on & ~base_on).sum()), int((~por_on & base_on).sum())))
        if p < 0.05 and abs(net) > MISMATCH_MAX:
            return {**out, "verdict": "차이", "reason": f"{'DOE' if net > 0 else 'POR'}만 LoQ 넘는 die {abs(net):.0%} 더 많음"}
        return {**out, "verdict": "동등", "reason": "LoQ 넘는 die 일치"}

    if spec:
        policy, policy_src = a.spec_frac * (spec[1] - spec[0]), f"스펙 폭 × {a.spec_frac:g}"
    else:
        policy, policy_src = a.r * level, f"|POR| × {a.r:g}"
    run_term = Z90 * np.sqrt(1 + 1 / J) * s_run
    delta = policy + run_term
    sd, rs = out["sd_d"], out["robust_sigma_d"]
    if rs > 0 and sd > a.robust_ratio * rs:
        center, h, method = out["median_d"], Z90 * MEDIAN_SE * rs / np.sqrt(n), "TOST 중앙값·robust σ (튀는 die)"
    else:
        center, h, method = out["mean_d"], stats.t.ppf(0.95, n - 1) * sd / np.sqrt(n), "TOST 평균·표준편차"
    lo, hi = center - h, center + h
    out.update(zone="정량", method=method, policy_margin=policy, policy_source=policy_src, run_margin=run_term,
               delta=delta, ci_low=lo, ci_high=hi, h=h)
    if -delta <= lo and hi <= delta:
        v, why = "동등", "90% 신뢰구간이 ±Δ 안"
    elif h >= delta:
        v, why = "미결", "해상도 부족 (신뢰구간 폭 ≥ Δ)"
    elif lo > delta or hi < -delta:
        v, why = "차이", f"shift {center:+.4g}가 ±Δ({delta:.4g}) 밖"
    else:
        v, why = "미결", "경계 (신뢰구간이 Δ에 걸침)"
    return {**out, "verdict": v, "reason": why}


def to_spec(df: pd.DataFrame) -> dict[str, tuple[float, float]]:
    s = df[["ITEM", "SPECLOW", "SPECHIGH"]].copy()
    s["SPECLOW"] = pd.to_numeric(s["SPECLOW"], errors="coerce")
    s["SPECHIGH"] = pd.to_numeric(s["SPECHIGH"], errors="coerce")
    s = s.dropna().drop_duplicates("ITEM")
    s = s[s["SPECHIGH"] > s["SPECLOW"]]
    return {r.ITEM: (r.SPECLOW, r.SPECHIGH) for r in s.itertuples()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--por", nargs="+", action="append", required=True,
                    help="POR 1회분 (파일이나 폴더). 회차마다 --por 를 따로 씀: --por run1/ --por run2/ --por run3/")
    ap.add_argument("--doe", nargs="+", required=True, help="DOE 1회분 (파일이나 폴더)")
    ap.add_argument("--r", type=float, default=0.05, help="스펙 없을 때 허용폭 = r × |POR| (기본 0.05)")
    ap.add_argument("--spec-frac", type=float, default=0.10, help="스펙 있을 때 허용폭 = 스펙 폭 × 이 값 (기본 0.10)")
    ap.add_argument("--no-spec", action="store_true", help="스펙이 있어도 r × |POR| 사용")
    ap.add_argument("--robust-ratio", type=float, default=1.3,
                    help="sd / robust σ 가 이 값보다 크면 중앙값·robust σ 사용 (기본 1.3)")
    ap.add_argument("--key", default="WAFERID,COORD_X_Y,ITEM")
    ap.add_argument("--encoding", default="auto")
    ap.add_argument("--out", default="por_doe_out")
    a = ap.parse_args()
    if len(a.por) < 2:
        sys.exit("POR은 2회 이상 필요합니다 (--por 를 회차마다 따로)")
    key = a.key.split(",")

    runs, spec = [], {}
    for i, paths in enumerate(a.por):
        df = load_side(paths, f"POR{i + 1}", a.encoding)
        if i == 0 and not a.no_spec:
            spec = to_spec(df)
        runs.append(df.groupby(key)["DATA"].median().rename(f"POR{i + 1}"))
    doe = load_side(a.doe, "DOE", a.encoding).groupby(key)["DATA"].median().rename("DOE")
    wide = pd.concat(runs + [doe], axis=1, join="inner").reset_index()
    por_cols = [f"POR{i + 1}" for i in range(len(a.por))]
    print(f"POR {len(por_cols)}회 + DOE, 모든 회차에 있는 die·ITEM {len(wide):,}개, ITEM {wide['ITEM'].nunique():,}개")

    rows = []
    for item, g in wide.groupby("ITEM", sort=False):
        res = judge(g[por_cols].to_numpy(float), g["DOE"].to_numpy(float), spec.get(item), a)
        rows.append({"ITEM": item, **res})
    res = pd.DataFrame(rows)
    res = res.sort_values(["verdict", "ITEM"], key=lambda s: s.map(ORDER) if s.name == "verdict" else s)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "items.csv", index=False, encoding="utf-8-sig")

    print(f"\n판정 (스펙 없으면 ±{a.r:.0%}, 스펙 있으면 스펙 폭의 {a.spec_frac:.0%}, + 회차 평균 흔들림)")
    print(pd.crosstab(res["zone"], res["verdict"], margins=True, margins_name="합계").to_string())
    q = res[res["zone"] == "정량"]
    if len(q):
        print("\n정량 구간: t-test vs TOST")
        print(pd.crosstab(q["ttest"], q["verdict"], margins=True, margins_name="합계").to_string())
        n_por = int((q["por_ttest_sig"].str.split("/").str[0].astype(int) > 0).sum())
        print(f"\nPOR끼리 t-test에서도 유의차가 나온 ITEM: {n_por:,} / {len(q):,}"
              f"  (같은 프로그램인데 t-test가 '차이'라고 한 수)")
    rs = res[res["verdict"] != "동등"]["reason"].value_counts()
    if len(rs):
        print("\n동등이 아닌 사유")
        print(rs.to_string())
    print(f"\n결과: {out / 'items.csv'}")


if __name__ == "__main__":
    main()
