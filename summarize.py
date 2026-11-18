"""por_doe_compare.py 결과(items.csv)를 공유용 요약으로 만든다. ITEM 이름은 익명 번호로 바꾼다.

  python summarize.py 결과/items.csv
  → 결과/summary.txt   : 붙여 넣어 공유할 요약 (ITEM 이름 없음)
  → 결과/item_map.csv  : 익명 번호 ↔ 실제 ITEM 대응표 (공유하지 말 것)
"""
from __future__ import annotations

import argparse
import io
import math
from pathlib import Path

import numpy as np
import pandas as pd


def decade(v: float) -> str:
    if not np.isfinite(v) or v == 0:
        return "0"
    return f"1e{math.floor(math.log10(abs(v))):+d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("items", help="por_doe_compare.py 가 만든 items.csv")
    ap.add_argument("--family-regex", default=r"^([A-Za-z]+)", help="항목군을 뽑는 정규식 (기본: 앞쪽 영문자)")
    ap.add_argument("--keep-family", action="store_true", help="항목군 이름(VT, ION 등)은 그대로 둠")
    ap.add_argument("--list", type=int, default=60, help="차이·미결 목록 최대 행 수 (기본 60)")
    a = ap.parse_args()

    path = Path(a.items)
    d = pd.read_csv(path)
    d["FAMILY"] = d["ITEM"].astype(str).str.extract(a.family_regex, expand=False).fillna("?")
    fam_ids = {f: f"F{i + 1:02d}" for i, f in enumerate(pd.unique(d["FAMILY"]))}
    d["ID"] = [f"I{i + 1:04d}" for i in range(len(d))]
    if not a.keep_family:
        d["FAMILY"] = d["FAMILY"].map(fam_ids)
    d["ID"] = d["FAMILY"] + "_" + d["ID"]
    d[["ID", "ITEM"]].to_csv(path.parent / "item_map.csv", index=False, encoding="utf-8-sig")
    if "UNIT" not in d:
        d["UNIT"] = "?"
    d["LEVEL"] = d["UNIT"].fillna("?").astype(str) + " " + d["por_median"].map(decade)
    q = d[d["zone"] == "정량"]
    bad = d[d["verdict"] != "동등"]

    buf = io.StringIO()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.max_rows", 500)

    def sec(title: str, body) -> None:
        buf.write(f"\n== {title}\n{body if isinstance(body, str) else body.to_string()}\n")

    def ct(rows, cols) -> pd.DataFrame:
        return pd.crosstab(rows, cols, margins=True, margins_name="합계")

    n_die = d["n_die"].median()
    buf.write(f"ITEM {len(d):,}개, die 중앙값 {n_die:.0f}개, POR 회차 {int(d['n_por_runs'].max())}회\n")
    sec("구간 x 판정", ct(d["zone"], d["verdict"]))
    sec("구간 x 방법 x 판정", pd.crosstab([d["zone"], d["method"]], d["verdict"]))
    if len(q):
        sec("정량: t-test x TOST", ct(q["ttest"], q["verdict"]))
        sec("정량: POR끼리 t-test 유의차 쌍 수", q["por_ttest_sig"].value_counts().sort_index())
        ratio = (q["sigma_run"] / q["sigma_die"]).replace([np.inf, -np.inf], np.nan)
        sec("정량: sigma_run / sigma_die", ratio.describe(percentiles=[.1, .25, .5, .75, .9]))
    for zname, zz in (("정량", q), ("LoQ 미만", d[d["zone"].isin(["검출한계 이하", "검출~정량"])])):
        if len(zz):
            run_dom = zz[zz["run_margin"] > zz["policy_margin"]]
            sec(f"{zname}: 허용폭 구성", pd.Series({
                "정책 몫 / Δ (중앙값)": round((zz["policy_margin"] / zz["delta"]).median(), 3),
                "회차 흔들림 몫 / Δ (중앙값)": round((zz["run_margin"] / zz["delta"]).median(), 3),
                "신뢰구간 반폭 / Δ (중앙값)": round((zz["h"] / zz["delta"]).median(), 3),
                "회차 흔들림 몫 > 정책 몫인 ITEM": len(run_dom),
                "  그중 동등": int((run_dom["verdict"] == "동등").sum()),
            }, dtype=object).to_string())
    if "verdict_no_blank" in d:
        hb = d[d["verdict_no_blank"].notna()]
        sec(f"blank: 연결 {len(hb)}개, blank가 한계를 정한 ITEM {int((hb['limit_source'] == 'blank').sum())}개",
            pd.crosstab(hb["verdict_no_blank"].rename("blank 없이"), hb["verdict"].rename("blank 적용"),
                        margins=True, margins_name="합계"))
        changed = hb[hb["verdict_no_blank"] != hb["verdict"]]
        if len(changed):
            sec("blank로 판정이 바뀐 ITEM", changed[["ID", "UNIT", "zone_no_blank", "zone", "verdict_no_blank", "verdict",
                                              "sigma_die", "LoQ", "blank_LoQ"]].to_string(
                index=False, float_format=lambda v: f"{v:.4g}"))
    if "verdict_tost_low" in d:
        lr = d[d["reason"].astype(str).str.startswith("<LoQ 보고 일치")]
        if len(lr):
            sec(f"<LoQ 보고 일치로 동등이 된 ITEM {len(lr)}개 중 DOE 비율이 POR 회차 범위 밖인 ITEM "
                f"{int(lr['doe_det_outside_por'].sum())}개", pd.crosstab(lr["FAMILY"], lr["doe_det_outside_por"].map(
                    {True: "DOE가 POR 범위 밖", False: "POR 범위 안"})))
    if "verdict_no_accuracy" in d and (d.get("delta_source") == "장비 정확도").any():
        qa = d[d["zone"] == "정량"]
        sec(f"장비 정확도 하한: 허용폭을 정한 ITEM {int((qa['delta_source'] == '장비 정확도').sum())}개",
            pd.crosstab(qa["verdict_no_accuracy"].rename("정확도 없이"), qa["verdict"].rename("정확도 적용"),
                        margins=True, margins_name="합계"))
    if "range_changed" in d:
        sec("POR과 DOE의 auto range가 다른 ITEM (판정별)", pd.crosstab(d["range_changed"], d["verdict"]))
        if "limit_source" in d:
            sec("LoQ를 정한 쪽", d["limit_source"].value_counts())
    sec("이상 신호", pd.Series({
        "sigma_die = 0 (계단값 의심)": int((d["sigma_die"] == 0).sum()),
        "sigma_run = 0": int((d["sigma_run"] == 0).sum()),
        "sigma_run > 2 x sigma_die": int((d["sigma_run"] > 2 * d["sigma_die"]).sum()),
        "튀는 die가 있는 ITEM (|d − 중앙값| > 5 robust σ)": int((d["n_outlier_die"] > 0).sum()),
    }))
    fam = pd.crosstab(d["FAMILY"], d["verdict"])
    fam["동등 아님 비율"] = (1 - fam.get("동등", 0) / fam.sum(axis=1)).round(3)
    sec("항목군별 판정 (동등 아님이 있는 항목군)", fam[fam["동등 아님 비율"] > 0].sort_values("동등 아님 비율", ascending=False))
    lv = pd.crosstab(d["LEVEL"], d["verdict"])
    lv["동등 아님 비율"] = (1 - lv.get("동등", 0) / lv.sum(axis=1)).round(3)
    sec("단위 x 값 자릿수별 판정 (동등 아님이 있는 구간)", lv[lv["동등 아님 비율"] > 0])
    sec("동등 아닌 사유", bad["reason"].str.replace(r"shift .*가", "shift가", regex=True).value_counts())

    runs = sorted(c for c in d.columns if c.startswith("POR") and c.endswith("_mean"))
    qb = bad[bad["zone"] == "정량"]
    if len(qb):
        rel = pd.DataFrame({"ID": qb["ID"], "UNIT": qb["UNIT"], "verdict": qb["verdict"],
                            "POR 값": qb["por_median"].map(lambda v: f"{v:.3g}")})
        base = qb[runs].mean(axis=1).abs().replace(0, np.nan)
        for c in runs + ["DOE_mean"]:
            rel[c.replace("_mean", "")] = ((qb[c] - qb[runs].mean(axis=1)) / base * 100).map(lambda v: f"{v:+.2f}%")
        rel["shift %"] = (qb["rel_shift"] * 100).map(lambda v: f"{v:+.2f}")
        rel["Δ %"] = (qb["delta"] / qb["por_median"].abs() * 100).map(lambda v: f"{v:.2f}")
        rel["CI %"] = [f"[{lo / abs(m) * 100:+.2f}, {hi / abs(m) * 100:+.2f}]"
                       for lo, hi, m in zip(qb["ci_low"], qb["ci_high"], qb["por_median"])]
        rel["튀는 die"] = qb["n_outlier_die"]
        if "range_por" in qb:
            rel["range POR→DOE"] = qb["range_por"].fillna("").astype(str) + "→" + qb["range_doe"].fillna("").astype(str)
        if "delta_source" in qb:
            rel["Δ 출처"] = qb["delta_source"]
        sec("정량 차이·미결: 회차별 평균 (POR 평균 대비 %). DOE가 POR 회차들의 퍼짐 밖에 있나", rel.head(a.list).to_string(index=False))
    dets = sorted(c for c in d.columns if c.startswith("POR") and c.endswith("_det"))
    lb = bad[bad["zone"].isin(["검출한계 이하", "검출~정량"])]
    if len(lb) and dets:
        t = lb[["ID", "UNIT", "verdict", "por_median"] + dets + ["DOE_det", "center", "delta", "ci_low", "ci_high"]].copy()
        t.columns = ["ID", "UNIT", "verdict", "POR 값"] + [c.replace("_det", "") for c in dets] + \
                    ["DOE", "비율 차이", "Δ", "CI low", "CI high"]
        sec("LoQ 미만 차이·미결: 회차별 LoQ 넘는 die 비율", t.head(a.list).to_string(
            index=False, float_format=lambda v: f"{v:.3g}"))
    od_path = path.parent / "outlier_dies.csv"
    if od_path.exists():
        od = pd.read_csv(od_path)
        if len(od):
            die_cols = [c for c in od.columns if c not in ("ITEM", "DOE") and not c.startswith("POR")]
            top = od.groupby(die_cols).size().sort_values(ascending=False)
            sec(f"튀는 die: 여러 ITEM에서 반복되는 die (상위 15, ITEM {len(d):,}개 중 몇 개에서 튀었나)",
                top.head(15).rename("ITEM 수"))
    cols = ["ID", "UNIT", "zone", "verdict", "reason", "ttest", "por_ttest_sig", "por_median",
            "center", "delta", "ci_low", "ci_high", "sigma_die", "sigma_run", "n_outlier_die"]
    cols = [c for c in cols if c in d]
    sec(f"차이·미결 ITEM (최대 {a.list}개)",
        bad[cols].head(a.list).to_string(index=False, float_format=lambda v: f"{v:.4g}") if len(bad) else "없음")

    text = buf.getvalue()
    (path.parent / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"공유용 요약: {path.parent / 'summary.txt'}")
    print(f"익명 번호 대응표 (공유하지 마세요): {path.parent / 'item_map.csv'}")


if __name__ == "__main__":
    main()
