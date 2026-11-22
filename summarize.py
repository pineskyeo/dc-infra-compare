"""por_doe_compare.py 결과(items.csv)를 공유용 요약으로 만든다. ITEM 이름은 익명 번호로 바꾼다.

  python summarize.py 결과/items.csv
  → 결과/summary.txt   : 붙여 넣어 공유할 요약 (ITEM 이름 없음)
  → 결과/item_map.csv  : 익명 번호 ↔ 실제 ITEM (공유하지 말 것)
  → 결과/items.csv     : ITEM 옆에 같은 익명 번호(ID 열)를 넣어 다시 저장

익명 번호는 ITEM 이름 순서로 매기므로 같은 ITEM 목록이면 실행마다 같은 번호가 나온다.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import numpy as np
import pandas as pd

from por_doe_compare import V_EXCLUDED, reason_group, verdict_col


def not_equivalent(d: pd.DataFrame) -> pd.DataFrame:
    """차이·미결 표 대상: 최종 판정(verdict_final, 옛 CSV 면 verdict)이 동등도 판정 제외도 아닌 행."""
    return d[~verdict_col(d).isin(["동등", V_EXCLUDED])]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("items", help="por_doe_compare.py 가 만든 items.csv")
    ap.add_argument("--family-regex", default=r"^([A-Za-z]+)", help="항목군을 뽑는 정규식 (기본: 앞쪽 영문자)")
    ap.add_argument("--keep-family", action="store_true", help="항목군 이름(VT, ION 등)은 그대로 둠")
    ap.add_argument("--list", type=int, default=60, help="표 최대 행 수 (기본 60)")
    a = ap.parse_args()

    path = Path(a.items)
    raw = pd.read_csv(path).drop(columns=["ID"], errors="ignore")
    d = raw.copy()
    fam = d["ITEM"].astype(str).str.extract(a.family_regex, expand=False).fillna("?")
    fam_ids = {f: f"F{i + 1:02d}" for i, f in enumerate(sorted(fam.unique()))}
    item_no = {it: i + 1 for i, it in enumerate(sorted(d["ITEM"].astype(str)))}
    d["FAMILY"] = fam if a.keep_family else fam.map(fam_ids)
    d["ID"] = d["FAMILY"] + "_" + d["ITEM"].astype(str).map(lambda it: f"I{item_no[it]:04d}")
    d[["ID", "ITEM"]].to_csv(path.parent / "item_map.csv", index=False, encoding="utf-8-sig")
    raw.insert(raw.columns.get_loc("ITEM") + 1, "ID", d["ID"])
    raw.to_csv(path, index=False, encoding="utf-8-sig")

    q = d[d["zone"] == "정량"]
    low = d[d["zone"].isin(["검출한계 이하", "검출~정량"])]
    vf = verdict_col(d).rename("verdict")
    ex = d[vf == V_EXCLUDED]
    bad = not_equivalent(d)
    runs = sorted(c for c in d.columns if c.startswith("POR") and c.endswith("_mean"))
    f4 = lambda v: f"{v:.4g}"
    buf = io.StringIO()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.max_rows", 500)

    def sec(title: str, body) -> None:
        buf.write(f"\n== {title}\n{body if isinstance(body, str) else body.to_string()}\n")

    buf.write(f"ITEM {len(d):,}개, die 중앙값 {d['n_die'].median():.0f}개, POR 회차 {len(runs)}회\n"
              f"판정: 중앙값 TOST, 허용폭 = r × |POR| + POR 회차 흔들림, LoQ 미만은 '<LoQ 보고 일치'\n")
    if len(ex):
        causes = reason_group(ex["reason"]).str.split("; ").explode().str.replace(f"^{V_EXCLUDED}: ", "", regex=True)
        buf.write(f"{V_EXCLUDED} ITEM: {len(ex):,} ("
                  + ", ".join(f"{k} {v:,}" for k, v in causes.value_counts().items()) + ")\n")

    # 1. 결과
    sec("구간 x 판정", pd.crosstab(d["zone"], vf, margins=True, margins_name="합계"))
    if len(bad):
        sec("동등 아닌 사유", reason_group(bad["reason"]).value_counts())
    qb = bad[bad["zone"] == "정량"]
    if len(qb):
        base = qb[runs].mean(axis=1).abs().replace(0, np.nan)
        lv = qb["por_median"].abs().replace(0, np.nan)
        t = pd.DataFrame({"ID": qb["ID"], "UNIT": qb["UNIT"], "verdict": vf[qb.index], "POR 값": qb["por_median"].map(f4)})
        for c in runs + ["DOE_mean"]:
            t[c.replace("_mean", "")] = ((qb[c] - qb[runs].mean(axis=1)) / base * 100).map(lambda v: f"{v:+.2f}%")
        t["shift %"] = (qb["center"] / lv * 100).map(lambda v: f"{v:+.2f}")
        t["CI %"] = [f"[{lo / m * 100:+.2f}, {hi / m * 100:+.2f}]" for lo, hi, m in zip(qb["ci_low"], qb["ci_high"], lv)]
        t["Δ %"] = (qb["delta"] / lv * 100).map(lambda v: f"{v:.2f}")
        t["튀는 die"] = qb["n_outlier_die"]
        if "range_por" in qb:
            t["range"] = qb["range_por"].fillna("").astype(str)
        sec("정량 차이·미결: 회차별 평균 (POR 평균 대비 %). DOE만 POR 회차들 밖인가", t.head(a.list).to_string(index=False))
    lb = bad[bad["zone"].isin(["검출한계 이하", "검출~정량"])]
    if len(lb):
        t = lb[["ID", "UNIT", "verdict", "por_median", "LoQ"] + runs + ["DOE_mean", "center", "ci_low", "ci_high", "delta",
                                                                         "doe_center"]].copy()
        t["verdict"] = vf[lb.index]
        t.columns = ["ID", "UNIT", "verdict", "POR 값", "LoQ"] + [c.replace("_mean", "") for c in runs] + \
                    ["DOE", "shift", "CI low", "CI high", "Δ", "DOE 중심"]
        sec("LoQ 미만 차이·미결: 회차별 평균과 중심 이동", t.head(a.list).to_string(index=False, float_format=f4))
    fm = pd.crosstab(d["FAMILY"], vf)
    fm = fm[fm.drop(columns="동등", errors="ignore").sum(axis=1) > 0]
    if len(fm):
        sec("항목군별 판정 (동등 아님이 있는 항목군)", fm)

    # 2. 설득용
    if len(q):
        n_por = int((q["por_ttest_sig"].astype(str).str.split("/").str[0].astype(int) > 0).sum())
        sec("t-test로 판정했다면 (정량 구간)", pd.Series({
            "DOE vs POR t-test 유의차": f"{int((q['ttest'] == '유의차').sum()):,} / {len(q):,}",
            "  그중 TOST 동등": f"{int(((q['ttest'] == '유의차') & (q['verdict'] == '동등')).sum()):,}",
            "POR끼리 t-test 유의차 (1쌍 이상)": f"{n_por:,} / {len(q):,}",
        }).to_string())

    # 3. 판정 근거 점검
    rows = {}
    for name, z in (("정량", q), ("LoQ 미만", low)):
        if len(z):
            wide = z["run_margin"] > z["policy_margin"]
            rows[f"{name}: POR 회차 흔들림 몫이 정책 몫보다 큰 ITEM"] = \
                f"{int(wide.sum()):,} (그중 동등 {int((wide & (z['verdict'] == '동등')).sum()):,})"
    for k, v in d["limit_source"].value_counts().items():
        rows[f"LoQ를 정한 쪽 · {k}"] = int(v)
    if "verdict_no_blank" in d:
        hb = d[d["verdict_no_blank"].notna()]
        rows["blank 때문에 판정이 바뀐 ITEM"] = f"{int((hb['verdict_no_blank'] != hb['verdict']).sum())} / 연결 {len(hb):,}"
    if "verdict_with_accuracy" in d:
        da = d[d["verdict_with_accuracy"].notna()]
        rows["장비 정확도 폭을 쓰면 판정이 바뀔 ITEM (판정에는 안 씀)"] = \
            f"{int((da['verdict_with_accuracy'] != da['verdict']).sum())} / 정확도 폭 있음 {len(da):,}"
    sec("판정 근거 점검", pd.Series(rows).to_string())

    # 4. 입력 점검
    rows = {}
    if "spec_status" in d:
        for k, v in d["spec_status"].fillna("item_info 없음").value_counts().items():
            rows[f"장비 사양 · {k}"] = int(v)
    if "blank_status" in d:
        for k, v in d["blank_status"].dropna().value_counts().items():
            rows[f"blank · {k}"] = int(v)
    rows["sigma_die = 0 (계단값 의심)"] = int((d["sigma_die"] == 0).sum())
    rows["튀는 die가 있는 ITEM"] = int((d["n_outlier_die"] > 0).sum())
    sec("입력 점검", pd.Series(rows).to_string())
    if "level_check" in d:
        lvbad = d[d["level_check"].astype(str).str.startswith("불일치")]
        if len(lvbad):
            sec(f"CALCVAL로 환산한 실제 값이 LEVEL 자릿수와 다른 ITEM {len(lvbad)}개 (앞 10개)",
                lvbad[["ID", "level_check"]].head(10).to_string(index=False))
    od_path = path.parent / "outlier_dies.csv"
    if od_path.exists():
        od = pd.read_csv(od_path)
        if len(od):
            die_cols = [c for c in od.columns if c not in ("ITEM", "DOE") and not c.startswith("POR")]
            sec(f"여러 ITEM에서 반복해서 튀는 die (상위 10, ITEM {len(d):,}개 중)",
                od.groupby(die_cols).size().sort_values(ascending=False).head(10).rename("ITEM 수"))

    text = buf.getvalue()
    (path.parent / "summary.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"공유용 요약: {path.parent / 'summary.txt'}")
    print(f"익명 번호 대응표 (공유하지 마세요): {path.parent / 'item_map.csv'}  (items.csv 에도 ID 열 추가)")


if __name__ == "__main__":
    main()
