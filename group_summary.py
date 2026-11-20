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
  stability_panel.png 그룹별 안정성 그림
  ratio_hist.png      σ_die 비(개선/기존) 히스토그램, 로그 축
  density_die.png     σ_die 기존 vs 개선 밀도 산점도, 로그 축
  group_panel.png     그룹별 비교 (σ_die 비 중앙값·사분위, 감소 %), 그룹 10~20개용
사용하는 행: presence=matched 인 행 전부 (정렬 의심 포함). --exclude-misaligned 를 주면 정렬 의심은 뺀다.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

UNGROUPED = "미지정"


def set_font():
    names = {f.name for f in fm.fontManager.ttflist}
    for n in ("Apple SD Gothic Neo", "AppleGothic", "Malgun Gothic", "Pretendard",
              "Noto Sans CJK KR", "NanumGothic"):
        if n in names:
            plt.rcParams["font.family"] = n
            break
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 10


def read_table(path):
    p = Path(path)
    sep = "\t" if p.suffix.lower() in (".tsv", ".txt") else ","
    return pd.read_csv(p, sep=sep, encoding="utf-8-sig")


def read_groups(path):
    p = Path(path)
    raw = p.read_text(encoding="utf-8-sig")
    sep = "\t" if "\t" in raw.splitlines()[0] else ","
    g = pd.read_csv(p, sep=sep, header=None, dtype=str, encoding="utf-8-sig").iloc[:, :2]
    g.columns = ["ITEM", "group"]
    g = g.apply(lambda s: s.str.strip())
    if g.iloc[0, 0].upper() in ("ITEM", "ID"):  # 헤더 줄
        g = g.iloc[1:]
    g = g.dropna(subset=["ITEM"]).drop_duplicates("ITEM", keep="first")
    return g


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

    set_font()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

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
    for k in ("verdict_before", "verdict_after"):
        c[k] = c[k].fillna("").astype(str).str.strip()

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
    used = c[keep].copy()
    print(f"분석 ITEM: {len(used)}개 (정렬 의심 {'제외' if a.exclude_misaligned else '포함'})")

    # 그룹별 표
    rows = [{"그룹": "전체", **summarize(used)}]
    order = sorted(used["group"].unique(), key=lambda x: (x == UNGROUPED, x))
    for name in order:
        rows.append({"그룹": name, **summarize(used[used["group"] == name])})
    excluded = c[~c.index.isin(used.index)].groupby("group").size()
    tab = pd.DataFrame(rows)
    tab["제외(짝 없음"+(", 정렬 의심" if a.exclude_misaligned else "")+")"] = tab["그룹"].map(lambda x: int(excluded.sum()) if x == "전체" else int(excluded.get(x, 0)))
    tab.to_csv(out / "group_summary.csv", index=False, encoding="utf-8-sig")

    vt = pd.crosstab(used["group"], used["verdict_before"] + "→" + used["verdict_after"])
    vt.loc["전체"] = vt.sum()
    vt.to_csv(out / "verdict_by_group.csv", encoding="utf-8-sig")

    # 그림 1: σ_die 비 히스토그램
    ok = used["sigma_die_before"].gt(0) & used["sigma_die_after"].gt(0)
    r = (used.loc[ok, "sigma_die_after"] / used.loc[ok, "sigma_die_before"])
    lr = np.log10(r)
    fig, ax = plt.subplots(figsize=(7, 4))
    lo, hi = np.percentile(lr, [0.5, 99.5]) if len(lr) else (-1, 1)
    lim = max(abs(lo), abs(hi), 0.3)
    bins = np.linspace(-lim, lim, 41)
    clipped = lr.clip(-lim, lim)
    ax.hist(clipped[clipped < 0], bins=bins, color="#2f6db5", label="개선 (비 < 1)")
    ax.hist(clipped[clipped >= 0], bins=bins, color="#b0b0b0", label="악화·같음 (비 ≥ 1)")
    ax.axvline(0, color="black", lw=1)
    ticks = [t for t in (0.1, 0.2, 0.5, 1, 2, 5, 10) if abs(np.log10(t)) <= lim]
    ax.set_xticks(np.log10(ticks))
    ax.set_xticklabels([f"{t:g}" for t in ticks])
    ax.set_xlabel("σ_die 비 (개선 / 기존), 로그 축")
    ax.set_ylabel("ITEM 수")
    pct = 100 * (r < 1).mean() if len(r) else np.nan
    ax.set_title(f"{pct:.0f}%가 1 왼쪽 · 중앙값 {r.median():.2f} · n={len(r)}")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "ratio_hist.png", dpi=160)
    plt.close(fig)

    # 그림 2: 밀도 산점도
    x = np.log10(used.loc[ok, "sigma_die_before"])
    y = np.log10(used.loc[ok, "sigma_die_after"])
    fig, ax = plt.subplots(figsize=(5.5, 5))
    hb = ax.hexbin(x, y, gridsize=45, bins="log", cmap="Blues", mincnt=1)
    m0, m1 = min(x.min(), y.min()), max(x.max(), y.max())
    ax.plot([m0, m1], [m0, m1], color="black", lw=1)
    ax.set_xlabel("기존 σ_die (log10)")
    ax.set_ylabel("개선 σ_die (log10)")
    ax.set_title("대각선 아래 = 개선")
    fig.colorbar(hb, ax=ax, label="ITEM 수 (log)")
    fig.tight_layout()
    fig.savefig(out / "density_die.png", dpi=160)
    plt.close(fig)

    # 그림 3: 그룹 비교 패널 (그룹 10~20개 기준, σ_die 비 중앙값 순 정렬)
    gt = tab[tab["그룹"] != "전체"].dropna(subset=["σ_die 비 중앙값(개선/기존)"])
    gt = gt.sort_values("σ_die 비 중앙값(개선/기존)").reset_index(drop=True)
    ov = tab.iloc[0]
    q = {}
    for name in gt["그룹"]:
        sub = used[(used["group"] == name) & ok]
        rr = sub["sigma_die_after"] / sub["sigma_die_before"]
        q[name] = (rr.quantile(0.25), rr.quantile(0.75))
    G = len(gt)
    fig, axs = plt.subplots(1, 3, figsize=(11, 0.38 * G + 1.8), sharey=True,
                            gridspec_kw={"width_ratios": [1.6, 1, 1]})
    yy = np.arange(G)
    labels = [f"{g} (n={n})" for g, n in zip(gt["그룹"], gt["ITEM 수"])]
    med = gt["σ_die 비 중앙값(개선/기존)"].values
    lo_q = np.array([q[g][0] for g in gt["그룹"]]); hi_q = np.array([q[g][1] for g in gt["그룹"]])
    col = ["#2f6db5" if v < 1 else "#c0392b" for v in med]
    ax = axs[0]
    ax.hlines(yy, lo_q, hi_q, color="#9db8dc", lw=4)
    ax.scatter(med, yy, color=col, zorder=3, s=28)
    ax.axvline(1, color="black", lw=1)
    ax.axvline(ov["σ_die 비 중앙값(개선/기존)"], color="#2f6db5", lw=1, ls="--")
    ax.set_xscale("log")
    xt = [t for t in (0.2, 0.3, 0.5, 0.7, 1, 1.5, 2) if np.nanmin(lo_q) * 0.8 <= t <= max(np.nanmax(hi_q) * 1.2, 1.1)]
    ax.set_xticks(xt); ax.set_xticklabels([f"{t:g}" for t in xt]); ax.minorticks_off()
    ax.set_title("σ_die 비 (개선/기존)\n점=중앙값, 막대=가운데 50%")
    ax.set_yticks(yy); ax.set_yticklabels(labels); ax.invert_yaxis()
    for ax, colname, title in ((axs[1], "σ_die 감소 %", "σ_die 줄어든 ITEM %"),
                               (axs[2], "σ_run 감소 %(비교 가능 중)", "σ_run 줄어든 ITEM %\n(둘 다 0 제외)")):
        v = gt[colname].values
        ax.barh(yy, v, color="#2f6db5", height=0.6)
        ax.axvline(ov[colname], color="black", lw=1, ls="--")
        ax.axvline(50, color="#999999", lw=0.8)
        for i, x in enumerate(v):
            if np.isfinite(x):
                ax.text(x + 1, i, f"{x:.0f}", va="center", fontsize=8)
        ax.set_xlim(0, 105); ax.set_title(title)
    fig.suptitle(f"그룹별 산포 변화 · 점선=전체 (σ_die 비 {ov['σ_die 비 중앙값(개선/기존)']:.2f})", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "group_panel.png", dpi=160)
    plt.close(fig)

    # 안정성 비교: 기존끼리, 개선끼리 (중앙값 대비 σ %)
    for side in ("before", "after"):
        for k in ("die", "run"):
            col = f"sigma_{k}_pct_{side}"
            if col in used.columns:
                used[col] = pd.to_numeric(used[col], errors="coerce")
            else:
                mc = f"por_median_{side}"
                med_ = pd.to_numeric(used[mc], errors="coerce") if mc in used.columns else pd.Series(np.nan, index=used.index)
                used[col] = 100 * used[f"sigma_{k}_{side}"] / med_.abs().replace(0, np.nan)
        # 측정 정밀도 % (낮을수록 좋음): 열이 있으면 쓰고, 없으면 100 × sqrt(σ_die² + σ_run²) / |por_median|
        col = f"meas_precision_pct_{side}"
        if col in used.columns:
            used[col] = pd.to_numeric(used[col], errors="coerce")
        else:
            mc = f"por_median_{side}"
            med_ = pd.to_numeric(used[mc], errors="coerce") if mc in used.columns else pd.Series(np.nan, index=used.index)
            s_meas = np.hypot(used[f"sigma_die_{side}"], used[f"sigma_run_{side}"])
            used[col] = 100 * s_meas / med_.abs().replace(0, np.nan)
    SIDE = {"before": "기존", "after": "개선"}

    def stab(d):
        r = {"ITEM 수": len(d)}
        for side in ("before", "after"):
            dd = d[f"sigma_die_pct_{side}"].dropna()
            rr = d[f"sigma_run_pct_{side}"].dropna()
            r[f"{SIDE[side]} σ_die% 중앙값"] = round(float(dd.median()), 3) if len(dd) else np.nan
            r[f"{SIDE[side]} σ_die% 25%"] = round(float(dd.quantile(0.25)), 3) if len(dd) else np.nan
            r[f"{SIDE[side]} σ_die% 75%"] = round(float(dd.quantile(0.75)), 3) if len(dd) else np.nan
            r[f"{SIDE[side]} σ_run% 중앙값"] = round(float(rr.median()), 3) if len(rr) else np.nan
            r[f"{SIDE[side]} σ_run=0 %"] = round(100 * float((d[f"sigma_run_{side}"] == 0).mean()), 1) if len(d) else np.nan
        for side in ("before", "after"):
            mp = d[f"meas_precision_pct_{side}"].dropna()
            r[f"{SIDE[side]} 측정정밀도% 중앙값"] = round(float(mp.median()), 3) if len(mp) else np.nan
            r[f"{SIDE[side]} 측정정밀도% 25%"] = round(float(mp.quantile(0.25)), 3) if len(mp) else np.nan
            r[f"{SIDE[side]} 측정정밀도% 75%"] = round(float(mp.quantile(0.75)), 3) if len(mp) else np.nan
        return r

    srows = [{"그룹": "전체", **stab(used)}] + [{"그룹": n, **stab(used[used["group"] == n])} for n in order]
    st = pd.DataFrame(srows)
    for side in ("기존", "개선"):  # 같은 조건 안에서 순위 (1 = 가장 안정)
        st[f"{side} 안정 순위"] = st[f"{side} σ_die% 중앙값"].where(st["그룹"] != "전체").rank(method="min").astype("Int64")
    st.to_csv(out / "stability_by_group.csv", index=False, encoding="utf-8-sig")

    # 그림 4: 그룹별 안정성 (기존끼리 / 개선끼리)
    has_pct = st[["기존 σ_die% 중앙값", "개선 σ_die% 중앙값"]].gt(0).any().all()
    if not has_pct:
        print("compare.csv에 por_median/σ% 열이 없어 stability_panel.png는 건너뜁니다.")
    else:
        sg = st[st["그룹"] != "전체"].sort_values("기존 σ_die% 중앙값").reset_index(drop=True)
        tot = st.iloc[0]
        G = len(sg)
        yy = np.arange(G)
        fig, axs = plt.subplots(1, 2, figsize=(11, 0.38 * G + 1.9), sharey=True)
        colors = {"기존": "#8a8a8a", "개선": "#2f6db5"}
        off = {"기존": -0.15, "개선": 0.15}
        ax = axs[0]
        for side in ("기존", "개선"):
            m = sg[f"{side} σ_die% 중앙값"].values
            ax.hlines(yy + off[side], sg[f"{side} σ_die% 25%"], sg[f"{side} σ_die% 75%"], color=colors[side], lw=3, alpha=0.45)
            ax.scatter(m, yy + off[side], color=colors[side], s=26, zorder=3, label=side)
            ax.axvline(tot[f"{side} σ_die% 중앙값"], color=colors[side], lw=1, ls="--")
        ax.set_xscale("log")
        from matplotlib.ticker import FuncFormatter, LogLocator
        ax.xaxis.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
        ax.set_title("σ_die / |중앙값| (%), 왼쪽일수록 안정\n점=그룹 중앙값, 막대=가운데 50%, 점선=전체")
        ax.legend(frameon=False, loc="lower right")
        ax.set_yticks(yy); ax.set_yticklabels([f"{g} (n={n})" for g, n in zip(sg["그룹"], sg["ITEM 수"])]); ax.invert_yaxis()
        ax = axs[1]
        for side in ("기존", "개선"):
            vals = sg[f"{side} σ_run% 중앙값"]
            ax.barh(yy + off[side], vals, height=0.3, color=colors[side], label=side)
            for y_, v_, z_ in zip(yy + off[side], vals, sg[f"{side} σ_run=0 %"]):
                # 중앙값 0이면 막대가 안 보이므로 숫자로 표시 (σ_run=0 ITEM이 절반 이상)
                txt = f"0 (σ_run=0 {z_:g}%)" if v_ == 0 else (f"{v_:g}" if pd.notna(v_) else "값 없음")
                ax.text(v_ if pd.notna(v_) else 0, y_, " " + txt, va="center", fontsize=7, color=colors[side])
            ax.axvline(tot[f"{side} σ_run% 중앙값"], color=colors[side], lw=1, ls="--")
        ax.set_title("σ_run / |중앙값| (%) 그룹 중앙값\n짧을수록 안정, 점선=전체, 0은 σ_run=0 ITEM이 절반 이상")
        ax.legend(frameon=False, loc="lower right")
        fig.suptitle("그룹별 안정성: 기존끼리(회색), 개선끼리(파랑) 비교", fontsize=11)
        fig.tight_layout()
        fig.savefig(out / "stability_panel.png", dpi=160)
        plt.close(fig)

    print(f"전체 {total}행 중 사용 {len(used)}행, 그룹 {len(order)}개")
    print(f"그룹 파일에 없는 ITEM: {int((used['group'] == UNGROUPED).sum())}개 → '{UNGROUPED}'")
    print(tab.to_string(index=False))
    print("\n안정성 (σ / |중앙값| %)")
    print(st.to_string(index=False))
    print(f"\n출력: {out.resolve()}")


if __name__ == "__main__":
    main()
