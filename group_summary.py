#!/usr/bin/env python3
"""compare.csv(기존 vs 개선)를 ITEM 그룹별로 요약한다.

사용법:
  python group_summary.py --compare <compare.csv> --groups <그룹.csv> --out <폴더>

그룹 파일: 첫 열 ITEM, 둘째 열 그룹 (쉼표 또는 탭, 헤더 있어도 없어도 됨)
그룹 파일에 없는 ITEM은 '미지정' 그룹으로 들어간다.

출력:
  group_summary.csv   그룹별 표 (맨 위 '전체' 행)
  verdict_by_group.csv 그룹별 판정 변화 표
  stability_by_group.csv 그룹별 안정성 (기존끼리·개선끼리 σ%, 측정정밀도%, 순위)
  <지표>.png          지표마다 그룹 비교 (가로 상자그림, 점선=전체 중앙값)
  <그룹 폴더>/<지표>.png 그룹마다 compare 와 같은 지표별 그림
  group_dirs.csv      그룹 이름 → 폴더 이름 (같은 폴더 이름이 겹치면 _2, _3)
지표 이름은 compare_metrics.METRICS.
사용하는 행: presence=matched 인 행 전부 (정렬 의심 포함). --exclude-misaligned 를 주면 정렬 의심은 뺀다.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import compare_metrics
from infra_compare import read_groups

UNGROUPED = "미지정"
V_EXCLUDED = "판정 제외"  # por_doe_compare.V_EXCLUDED와 같은 값 (scipy 의존 없이 단독 실행되게 로컬로 둠)
# 실행 시작 때 지우는 자기 출력(--out 기준 glob). 건너뛴 그림이나 없어진 그룹 폴더의 그림이 남지 않게 한다.
OWN_OUTPUTS = (
    "ratio_hist.png", "density_die.png", "group_panel.png", "stability_panel.png",  # 예전 이름
    *(f"{m}.png" for m in compare_metrics.METRICS),
    "group_dirs.csv",
    *(f"*/{m}.png" for m in compare_metrics.METRICS),
)


def remove_own_outputs(out, patterns):
    """지난 실행의 자기 출력 파일만 지우고, 그래서 비게 된 하위 폴더만 rmdir 한다(다른 파일은 그대로)."""
    parents = set()
    for pat in patterns:
        for p in out.glob(pat):
            if p.is_file():
                p.unlink()
                parents.add(p.parent)
    for d in parents:
        if d != out and not any(d.iterdir()):
            d.rmdir()


def group_dirs(names):
    """그룹 이름 → 폴더 이름. safe_group_name 이 겹치면 뒤에 _2, _3 …"""
    taken, dirs = set(), {}
    for n in names:
        base = compare_metrics.safe_group_name(n)
        s, k = base, 1
        while s in taken:
            k += 1
            s = f"{base}_{k}"
        taken.add(s)
        dirs[n] = s
    return dirs


def read_table(path):
    p = Path(path)
    sep = "\t" if p.suffix.lower() in (".tsv", ".txt") else ","
    return pd.read_csv(p, sep=sep, encoding="utf-8-sig")


def as_bool(s):
    return s.astype(str).str.strip().str.lower().isin(("true", "1", "yes"))


def summarize(d):
    die_ok = d["sigma_die_before"].gt(0) & d["sigma_die_after"].notna()
    ratio = (d["sigma_die_after"] / d["sigma_die_before"])[die_ok]
    run_both0 = d["sigma_run_before"].eq(0) & d["sigma_run_after"].eq(0)
    run_cmp = ~run_both0 & d["sigma_run_before"].notna() & d["sigma_run_after"].notna()
    die_down = d["sigma_die_after"] < d["sigma_die_before"]
    run_down = d["sigma_run_after"] < d["sigma_run_before"]
    run_up = d["sigma_run_after"] > d["sigma_run_before"]
    n = len(d)
    nb = int((d["verdict_before"] != "동등").sum())
    na = int((d["verdict_after"] != "동등").sum())
    return {
        "ITEM 수": n,
        "σ_die 비 중앙값(개선/기존)": round(float(ratio.median()), 3) if len(ratio) else np.nan,
        "σ_die 감소 %": round(100 * die_down.mean(), 1) if n else np.nan,
        "σ_run 감소 %(비교 가능 중)": round(100 * run_down[run_cmp].mean(), 1) if run_cmp.any() else np.nan,
        "σ_run 증가 건수": int(run_up.sum()),
        "σ_run 둘 다 0 건수": int(run_both0.sum()),
        "둘 다 감소 건수": int((die_down & run_down).sum()),
        "기존 동등 아님": nb,
        "개선 동등 아님": na,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compare", required=True, help="compare_before_after.py compare가 만든 compare.csv")
    ap.add_argument("--groups", required=True, help="ITEM,그룹 두 열 파일")
    ap.add_argument("--out", default="group_out", help="출력 폴더")
    ap.add_argument("--exclude-misaligned", action="store_true",
                    help="정렬 의심(POR 중앙값 상대차 > 20%%) ITEM을 뺀다 (기본: 포함)")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    remove_own_outputs(out, OWN_OUTPUTS)

    c = read_table(a.compare)
    if "ITEM" not in c.columns and "ID" in c.columns:
        c = c.rename(columns={"ID": "ITEM"})
    need = ["ITEM", "presence", "misaligned", "sigma_die_before", "sigma_die_after",
            "sigma_run_before", "sigma_run_after", "verdict_before", "verdict_after"]
    miss = [k for k in need if k not in c.columns]
    if miss:
        sys.exit(f"compare.csv에 열이 없습니다: {miss}")
    c["ITEM"] = c["ITEM"].astype(str).str.strip()
    for k in need[3:7]:
        c[k] = pd.to_numeric(c[k], errors="coerce")
    for side in ("before", "after"):   # 판정 집계는 최종 판정 (verdict_final_*), 없는 옛 CSV 면 verdict_*
        k = f"verdict_{side}"
        c[k] = c.get(f"verdict_final_{side}", c[k]).fillna("").astype(str).str.strip()

    g = read_groups(a.groups)
    total = len(c)
    # ITEM 이름 맞추기: 그대로 먼저, 안 맞으면 앞의 'F31_' 같은 접두어를 떼고 다시
    def bare(x):
        return x.str.replace(r"^F\d+_", "", regex=True).str.upper()
    exact = dict(zip(g["ITEM"], g["group"]))
    loose = dict(zip(bare(g["ITEM"]), g["group"]))
    c["group"] = c["ITEM"].map(exact)
    miss_mask = c["group"].isna()
    c.loc[miss_mask, "group"] = bare(c.loc[miss_mask, "ITEM"]).map(loose)
    n_exact = int((~miss_mask).sum()); n_loose = int(c["group"].notna().sum()) - n_exact
    print(f"그룹 매칭: 이름 그대로 {n_exact}개, 접두어(F..._) 떼고 {n_loose}개, 못 찾음 {int(c['group'].isna().sum())}개")
    if c["group"].isna().all():
        print("예) compare.csv ITEM:", list(c["ITEM"].head(3)), " / 그룹 파일 ITEM:", list(g["ITEM"].head(3)))
    c["group"] = c["group"].fillna(UNGROUPED)
    keep = c["presence"].astype(str).str.strip() == "matched"
    if a.exclude_misaligned:
        keep &= ~as_bool(c["misaligned"])
    scoped = c[keep].copy()  # 판정 전이 표용 (판정 제외 포함)
    is_excl = scoped["verdict_before"].eq(V_EXCLUDED) | scoped["verdict_after"].eq(V_EXCLUDED)
    used = scoped[~is_excl].copy()  # σ 집계용: 기존 또는 개선이 판정 제외면 뺌
    verdict_excl = scoped[is_excl].groupby("group").size()
    n_verdict_excl = int(is_excl.sum())
    print(f"분석 ITEM: {len(used)}개 (정렬 의심 {'제외' if a.exclude_misaligned else '포함'})"
          + (f", {V_EXCLUDED} {n_verdict_excl}개 뺌" if n_verdict_excl else ""))

    # 그룹별 표
    rows = [{"그룹": "전체", **summarize(used)}]
    order = sorted(used["group"].unique(), key=lambda x: (x == UNGROUPED, x))
    for name in order:
        rows.append({"그룹": name, **summarize(used[used["group"] == name])})
    excluded = c[~keep].groupby("group").size()
    tab = pd.DataFrame(rows)
    tab["제외(짝 없음"+(", 정렬 의심" if a.exclude_misaligned else "")+")"] = tab["그룹"].map(lambda x: int(excluded.sum()) if x == "전체" else int(excluded.get(x, 0)))
    if n_verdict_excl:
        tab[V_EXCLUDED] = tab["그룹"].map(lambda x: n_verdict_excl if x == "전체" else int(verdict_excl.get(x, 0)))
    tab.to_csv(out / "group_summary.csv", index=False, encoding="utf-8-sig")

    vt = pd.crosstab(scoped["group"], scoped["verdict_before"] + "→" + scoped["verdict_after"])
    vt.loc["전체"] = vt.sum()
    vt.to_csv(out / "verdict_by_group.csv", encoding="utf-8-sig")

    # 안정성 비교: 기존끼리, 개선끼리 (중앙값 대비 σ %, 측정정밀도 %)
    used = compare_metrics.with_pct(used)
    stab = compare_metrics.stability_row
    srows = [{"그룹": "전체", **stab(used)}] + [{"그룹": n, **stab(used[used["group"] == n])} for n in order]
    st = pd.DataFrame(srows)
    for side in ("기존", "개선"):  # 같은 조건 안에서 순위 (1 = 가장 안정)
        st[f"{side} 안정 순위"] = st[f"{side} σ_die% 중앙값"].where(st["그룹"] != "전체").rank(method="min").astype("Int64")
    st.to_csv(out / "stability_by_group.csv", index=False, encoding="utf-8-sig")

    # 그림: 지표마다 그룹 비교 한 장 (기준선 = 전체 중앙값; plot_group_compare 가 used 전체로 계산)
    for m in compare_metrics.METRICS:
        compare_metrics.plot_group_compare(used, "group", m, out / f"{m}.png")

    # 그림: 그룹마다 폴더 하나, 지표별 그림 (worst 표에 ITEM 이름이 보이게 ID 로 넘김)
    dirs = group_dirs(order)
    pd.DataFrame({"그룹": list(dirs), "폴더": list(dirs.values())}).to_csv(
        out / "group_dirs.csv", index=False, encoding="utf-8-sig")
    for name, sub in dirs.items():
        d = used[used["group"] == name]
        compare_metrics.draw_all(d.assign(ID=d["ITEM"]), out / sub, top=10)

    print(f"전체 {total}행 중 사용 {len(used)}행, 그룹 {len(order)}개")
    print(f"그룹 파일에 없는 ITEM: {int((used['group'] == UNGROUPED).sum())}개 → '{UNGROUPED}'")
    print(tab.to_string(index=False))
    print("\n안정성 (σ / |중앙값| %)")
    print(st.to_string(index=False))
    print(f"\n출력: {out.resolve()}")


if __name__ == "__main__":
    main()
