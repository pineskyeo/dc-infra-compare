"""POR 여러 회(같은 die 재측정) + DOE 1회로 ITEM별 동등성을 판정한다. t-test도 같이 낸다.

모든 기준은 실행 전에 정해지는 값이고, 데이터를 보고 바뀌는 문턱값은 없다.

흔들림 (POR 회차 × die 이원분산분석, NIST e-Handbook 2.4.4)
  sigma_die : 같은 회차 안 die별 1회 측정 흔들림 (잔차)
  sigma_run : 회차마다 전체가 같이 움직이는 크기 (컨택 상태, 온도 등)

구간 (Currie / IUPAC): LoD = 3.29 σ, LoQ = 10 σ, |POR 중앙값| 기준
  σ = max(sigma_die, 분해능 / √12). 분해능 = 측정값 사이의 가장 작은 간격 (계단값, GUM F.2.2.1)
  --blank 를 주면 blank 한계(|μ| + 3.29 SD, |μ| + 10 SD)가 더 클 때 그쪽을 씀 (하한).

두 구간 모두 같은 TOST 규칙. 비교하는 양만 다르다.
  정량 (|POR| ≥ LoQ)  : die별 d = DOE − POR 회차 평균
                         허용폭 Δ = r × |POR 중앙값| + 1.645 × √(1 + 1/J) × sigma_run
  LoQ 미만             : die별 "|값| ≥ LoQ" 여부(0/1). d = DOE 여부 − POR 회차 평균 여부
                         허용폭 Δ = det_margin + 1.645 × √(1 + 1/J) × sigma_run(여부)
  1.645 × √(1 + 1/J) × sigma_run : 같은 프로그램으로 다시 재도 생기는 회차 간 차이 (DOE 1회 vs POR J회 평균)

90% 신뢰구간 (shift)
  hl   (기본): Hodges–Lehmann 추정 + Wilcoxon 부호순위 신뢰구간. 분포 가정 없음, 튀는 die에 강함
  mean       : 평균 + t 신뢰구간 (NIST 7.3.1.1)
  LoQ 미만의 0/1 비교는 항상 mean (비율 차이)

판정: 신뢰구간이 ±Δ 안 → 동등 / 통째로 밖 → 차이 / 걸침 → 미결 (해상도 부족: 신뢰구간 반폭 ≥ Δ, 그 외 경계)
t-test (NIST 7.3.1.1): 평균 d가 0인지. 참고용이며 판정에 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import sys
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
          blank_lim: tuple[float, float] | None = None) -> tuple[dict, np.ndarray]:
    """blank_lim = blank로 구한 (LoD, LoQ). 반복으로 구한 한계보다 크면 그쪽을 쓴다. (결과, 튀는 die 표시)"""
    n, J = Y.shape
    R = Y.mean(axis=1)
    level = abs(float(np.median(R)))
    s_die, s_run = run_anova(Y)
    vals = np.unique(np.concatenate([Y.ravel(), z]))
    s_res = float(np.diff(vals).min()) / np.sqrt(12) if len(vals) > 1 else 0.0
    s_lim, src = (s_die, "POR 반복") if s_die >= s_res else (s_res, "분해능")
    lod, loq = K_LOD * s_lim, K_LOQ * s_lim
    if blank_lim and blank_lim[1] > loq:
        lod, loq, src = max(lod, blank_lim[0]), blank_lim[1], "blank"
    d = z - R
    rs = robust_sigma(d)
    outlier = np.abs(d - np.median(d)) > OUTLIER_K * rs if rs > 0 else np.zeros(n, bool)
    p_t = paired_t_p(d)
    por_pairs = [paired_t_p(Y[:, j] - Y[:, i]) for i in range(J) for j in range(i + 1, J)]
    out = {
        "n_die": n, "n_por_runs": J, "por_median": float(np.median(R)), "doe_median": float(np.median(z)),
        "sigma_die": s_die, "sigma_run": s_run, "sigma_run_df": J - 1, "LoD": lod, "LoQ": loq, "limit_source": src,
        "mean_d": float(d.mean()), "median_d": float(np.median(d)), "sd_d": float(d.std(ddof=1)),
        "robust_sigma_d": rs, "n_outlier_die": int(outlier.sum()),
        "ttest_p": p_t, "ttest": "유의차" if p_t < 0.05 else "유의차 없음",
        "por_ttest_sig": f"{sum(p < 0.05 for p in por_pairs)}/{len(por_pairs)}",
        **{f"POR{k + 1}_mean": float(Y[:, k].mean()) for k in range(J)}, "DOE_mean": float(z.mean()),
    }
    if n < MIN_DIE:
        return {**out, "zone": "die 부족", "verdict": "미결", "reason": f"die {n}개 (< {MIN_DIE})"}, outlier

    if level < loq:
        zone = "검출한계 이하" if level < lod else "검출~정량"
        I, D = (np.abs(Y) >= loq).astype(float), (np.abs(z) >= loq).astype(float)
        _, s_run_det = run_anova(I)
        e = D - I.mean(axis=1)
        center, lo, hi = ci_mean(e) if e.std() > 0 else (float(e.mean()),) * 3
        run_term = Z90 * np.sqrt(1 + 1 / J) * s_run_det
        delta = a.det_margin + run_term
        v, why = tost(center, lo, hi, delta, fmt=lambda x: f"{x:+.0%}p")
        out.update(zone=zone, method="TOST LoQ 넘는 die 비율", policy_margin=a.det_margin, run_margin=run_term,
                   delta=delta, center=center, ci_low=lo, ci_high=hi, h=(hi - lo) / 2, sigma_run_det=s_run_det,
                   **{f"POR{k + 1}_det": float(I[:, k].mean()) for k in range(J)}, DOE_det=float(D.mean()))
        return {**out, "verdict": v, "reason": f"LoQ 넘는 die 비율: {why}"}, outlier

    policy = a.r * level
    run_term = Z90 * np.sqrt(1 + 1 / J) * s_run
    delta = policy + run_term
    center, lo, hi = (ci_hl(d) if a.estimator == "hl" else ci_mean(d)) if d.std() > 0 else (float(d.mean()),) * 3
    v, why = tost(center, lo, hi, delta)
    out.update(zone="정량", method=f"TOST {'Hodges–Lehmann' if a.estimator == 'hl' else '평균'}",
               policy_margin=policy, run_margin=run_term, delta=delta, center=center, ci_low=lo, ci_high=hi,
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
    ap.add_argument("--estimator", choices=["hl", "mean"], default="hl",
                    help="정량 구간 신뢰구간: hl = Hodges–Lehmann/Wilcoxon (기본), mean = 평균/t")
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

    runs, units = [], {}
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

    rows, outl = [], []
    for item, g in wide.groupby("ITEM", sort=False):
        Y, z = g[por_cols].to_numpy(float), g["DOE"].to_numpy(float)
        bitem = bmap.get(item, item)
        extra, lim = {}, None
        if bitem in blank.index:
            lim3 = blank_limits(blank.loc[bitem])
            if lim3:
                lim = lim3[1:]
                bu = blank.loc[bitem].get("blank_unit")
                extra = {"blank_item": bitem, "blank_LoD": lim[0], "blank_LoQ": lim[1],
                         "blank_unit_mismatch": bool(pd.notna(bu) and bu != units.get(item))}
        res, mask = judge(Y, z, a, lim)
        if lim:
            base, _ = judge(Y, z, a)
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
        print(f"\nblank 연결 ITEM {len(hb):,}개 중 blank가 한계를 정한 ITEM {int((hb['limit_source'] == 'blank').sum()):,}개")
        print("blank 없이 → blank 하한 적용 (행: 없이, 열: 적용)")
        print(pd.crosstab(hb["verdict_no_blank"], hb["verdict"], margins=True, margins_name="합계").to_string())
        n_bad = int(hb["blank_unit_mismatch"].sum())
        if n_bad:
            print(f"경고: blank 단위가 ITEM 단위와 다른 ITEM {n_bad}개 (blank_unit_mismatch 열)")
    rs = res[res["verdict"] != "동등"]["reason"].str.replace(r"shift .*가", "shift가", regex=True).value_counts()
    if len(rs):
        print("\n동등이 아닌 사유")
        print(rs.to_string())
    print(f"\n결과: {out / 'items.csv'}, {out / 'outlier_dies.csv'}")


if __name__ == "__main__":
    main()
