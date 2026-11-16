#!/usr/bin/env python3
"""두 테스트 인프라(Ref / New)의 같은 die, 같은 ITEM 측정값이 같은지 항목별로 판정한다.

판정 (TOST 방식, 항목마다):
  d      = New - Ref                      (die별 차이)
  m      = median(d)                      (공통 shift)
  h      = 1.645 * 1.2533 * robustσ(d) / √n   (m의 90% 신뢰구간 반폭)
  Δ      = r * |median(Ref)| + 1.645 * σ₀     (허용폭. σ₀ = blank 노이즈, 없으면 0)
  동등   : [m-h, m+h] 가 (-Δ, +Δ) 안
  차이   : [m-h, m+h] 가 통째로 ±Δ 밖
  미결   : 걸침. 사유 = 해상도 부족(h ≥ Δ) / 경계 shift / die 부족

blank σ₀ = MR̄ / 1.128 (이웃 측정 차이로 구한 단기 노이즈, 측정 순서 기준).

usage:
  python infra_compare.py --ref REF_DIR --new NEW_DIR [--blank BLANK ...] [--blank-map map.csv]
                          [--r 0.01] [--key WAFERID,DIE_X_Y,ITEM] [--out result_dir]
  --ref/--new/--blank 에는 폴더(하위의 DCNORMAL 결과를 모두 읽음)나 파일을 여러 개 줄 수 있다.
  --blank 형식: DCNORMAL 파일·폴더 / CSV(ITEM,SIGMA0 요약) / CSV(ITEM,VALUE 원측정값, 측정 순서대로)
  --blank-map : CSV(ITEM,BLANK_ITEM). 제품 ITEM 이름과 blank ITEM 이름이 다를 때 연결. 없으면 같은 이름끼리.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MEASURE_COLS = ["COORD_X_Y", "FLAT_X_Y", "DIE_X_Y", "POINT_NAME", "MODULE_NO", "BIN", "DUT", "ITEM", "UNIT",
                "MEASURE_PNT", "DATA", "SPECLOW", "SPECHIGH", "JUDGE_LIM", "JUDGE_RST"]
SKIP_SUFFIXES = {".csv", ".tsv", ".parquet", ".xlsx", ".xls", ".json", ".txt", ".md", ".py", ".log"}
Z90 = 1.645            # 단측 5% (TOST 90% 신뢰구간)
MEDIAN_SE = 1.2533     # 정규분포에서 중앙값 표준오차 / 평균 표준오차
D2 = 1.128             # 관리도 상수 d2 (n=2)
MIN_PAIRS = 10
OUTLIER_K = 5.0


# ------------------------------------------------------------------ DCNORMAL 읽기
def is_dcnormal(path: Path) -> bool:
    try:
        head = path.open("rb").read(256).lstrip(b"\xef\xbb\xbf").replace(b"\r", b"")
    except OSError:
        return False
    return head.startswith(b"#FileFormatInformationStart") and b"\nFILEFORMAT=DCNORMAL" in head


def find_files(inputs: list[str]) -> list[Path]:
    out: list[Path] = []
    for s in inputs:
        p = Path(s)
        if p.is_dir():
            out += sorted(q for q in p.rglob("*") if q.is_file() and q.suffix.lower() not in SKIP_SUFFIXES
                          and (q.suffix.lower() == ".result" or is_dcnormal(q)))
        elif p.is_file():
            out.append(p)
        else:
            sys.exit(f"없는 경로: {s}")
    return list(dict.fromkeys(out))


def decode(raw: bytes, path: Path, encoding: str) -> tuple[str, str]:
    """auto: UTF-8 먼저, 안 되면 CP949(한글 윈도우·엑셀 기본)."""
    for enc in (["utf-8-sig", "cp949"] if encoding == "auto" else [encoding]):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    sys.exit(f"{path}: 인코딩 {encoding} 으로 읽을 수 없습니다. --encoding 으로 지정하세요 (예: cp949, euc-kr, latin-1)")


def read_csv_auto(path: Path, encoding: str) -> pd.DataFrame:
    text, _ = decode(path.read_bytes(), path, encoding)
    return pd.read_csv(io.StringIO(text))


def read_dcnormal(path: Path, encoding: str) -> pd.DataFrame:
    header: dict[str, str] = {}
    rows: list[list] = []
    block, header_ok, bad = None, None, 0
    text, enc = decode(path.read_bytes(), path, encoding)
    for no, line in enumerate(text.splitlines(), start=1):
        if line == "[EOF]":
            break
        if line.startswith("#") and (line.endswith("Start") or line.endswith("End")):
            block = line[1:-5] if line.endswith("Start") else None
            header_ok = None
            continue
        if block == "MeasureData":
            f = next(csv.reader([line]))
            if header_ok is None:
                header_ok = f == MEASURE_COLS
                if not header_ok:
                    raise ValueError(f"{path}: MeasureData 헤더가 DCNORMAL 15열 규격과 다릅니다")
                continue
            if len(f) != len(MEASURE_COLS):
                bad += 1
                continue
            rows.append(f + [no])
        elif block and "=" in line:
            k, v = line.split("=", 1)
            header.setdefault(k, v.strip('"'))
    if bad:
        print(f"  경고: {path.name} 열 개수가 맞지 않는 행 {bad}개 제외", file=sys.stderr)
    df = pd.DataFrame(rows, columns=MEASURE_COLS + ["LINE"])
    df["DATA"] = pd.to_numeric(df["DATA"], errors="coerce")
    df["UNIT"] = df["UNIT"].str.strip("[]")
    for k in ("LOTID", "WAFERID", "EQPID", "STARTDATETIME"):
        df[k] = header.get(k)
    df["FILE"] = str(path)
    df["ENC"] = enc
    return df


def load_side(inputs: list[str], label: str, encoding: str) -> pd.DataFrame:
    files = find_files(inputs)
    if not files:
        sys.exit(f"{label}: DCNORMAL 파일이 없습니다 ({inputs})")
    df = pd.concat([read_dcnormal(f, encoding) for f in files], ignore_index=True)
    n_nan = int(df["DATA"].isna().sum())
    df = df.dropna(subset=["DATA"])
    encs = df.drop_duplicates("FILE")["ENC"].value_counts().to_dict()
    print(f"[{label}] 파일 {len(files)}개 (인코딩 {encs}), 측정 {len(df):,}행 (숫자 아닌 DATA {n_nan}행 제외), "
          f"ITEM {df['ITEM'].nunique():,}개")
    return df


# ------------------------------------------------------------------ blank
def blank_sigma(values: pd.Series) -> dict:
    v = values.to_numpy(dtype=float)
    v = v[~np.isnan(v)]
    if len(v) < 2:
        return {}
    sigma_mr = float(np.mean(np.abs(np.diff(v))) / D2)
    sd = float(np.std(v, ddof=1))
    return {"blank_n": len(v), "blank_offset": float(np.mean(v)), "blank_sd": sd, "sigma0": sigma_mr,
            "blank_drift_ratio": sd / sigma_mr if sigma_mr > 0 else np.nan}


def load_blank(inputs: list[str], encoding: str) -> pd.DataFrame:
    raw: list[pd.DataFrame] = []
    summary: list[pd.DataFrame] = []
    dc_inputs: list[str] = []
    for s in inputs:
        p = Path(s)
        if p.is_file() and p.suffix.lower() == ".csv":
            t = read_csv_auto(p, encoding)
            t.columns = [c.strip().upper() for c in t.columns]
            if {"ITEM", "SIGMA0"} <= set(t.columns):
                summary.append(t[["ITEM", "SIGMA0"]].rename(columns={"SIGMA0": "sigma0"}).assign(blank_source=p.name))
            elif {"ITEM", "VALUE"} <= set(t.columns):
                raw.append(t[["ITEM", "VALUE"]].rename(columns={"VALUE": "DATA"}).assign(blank_source=p.name))
            elif "ITEM" not in t.columns:
                t = read_csv_auto(p, encoding)   # 가로형: 열 이름 = blank ITEM, 위에서 아래로 측정 순서
                long = t.melt(var_name="ITEM", value_name="DATA").dropna(subset=["DATA"])
                raw.append(long.assign(DATA=pd.to_numeric(long["DATA"], errors="coerce"), blank_source=p.name))
            else:
                sys.exit(f"{p}: blank CSV 형식을 알 수 없습니다 (가로형, ITEM,VALUE, ITEM,SIGMA0 중 하나)")
        else:
            dc_inputs.append(s)
    if dc_inputs:
        d = load_side(dc_inputs, "Blank", encoding)
        raw.append(d[["ITEM", "DATA", "UNIT"]].assign(blank_source="DCNORMAL"))
    rows = []
    for t in raw:
        for (item, src), g in t.groupby(["ITEM", "blank_source"], sort=False):
            st = blank_sigma(g["DATA"])
            if st:
                unit = g["UNIT"].iloc[0] if "UNIT" in g else None
                rows.append({"BLANK_ITEM": item, "blank_source": src, "blank_unit": unit, **st})
    out = pd.DataFrame(rows)
    if summary:
        s = pd.concat(summary).rename(columns={"ITEM": "BLANK_ITEM"})
        out = pd.concat([out, s], ignore_index=True)
    if out.empty:
        return pd.DataFrame(columns=["BLANK_ITEM", "sigma0", "blank_source"])
    dup = out["BLANK_ITEM"].duplicated(keep="last")
    if dup.any():
        print(f"  경고: blank ITEM {dup.sum()}개가 여러 입력에 중복. 마지막 입력 값을 사용", file=sys.stderr)
    out = out[~dup]
    print(f"[Blank] σ₀ 확보 ITEM {len(out)}개")
    return out


# ------------------------------------------------------------------ 짝짓기와 판정
def pair_up(ref: pd.DataFrame, new: pd.DataFrame, key: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    def agg(df: pd.DataFrame, side: str) -> pd.DataFrame:
        g = df.groupby(key, dropna=False).agg(**{side: ("DATA", "median"), f"n_{side}": ("DATA", "size"),
                                                 "UNIT": ("UNIT", "first")})
        return g
    a, b = agg(ref, "ref"), agg(new, "new")
    paired = a.join(b.drop(columns="UNIT"), how="inner").reset_index()
    cnt = pd.DataFrame({
        "n_ref_only": a.index.difference(b.index).to_frame(index=False).groupby("ITEM").size(),
        "n_new_only": b.index.difference(a.index).to_frame(index=False).groupby("ITEM").size(),
        "n_dup_ref": a[a["n_ref"] > 1].reset_index().groupby("ITEM").size(),
        "n_dup_new": b[b["n_new"] > 1].reset_index().groupby("ITEM").size(),
    }).fillna(0).astype(int)
    print(f"[짝짓기] 키 {key}: 짝 {len(paired):,}개, Ref만 {int(cnt['n_ref_only'].sum()):,}, "
          f"New만 {int(cnt['n_new_only'].sum()):,}, 중복 키(중앙값 사용) Ref {int(cnt['n_dup_ref'].sum()):,} / "
          f"New {int(cnt['n_dup_new'].sum()):,}")
    return paired, cnt


def judge_item(g: pd.DataFrame, r: float, sigma0: float) -> tuple[dict, np.ndarray]:
    d = (g["new"] - g["ref"]).to_numpy(dtype=float)
    n = len(d)
    m = float(np.median(d))
    s = 1.4826 * float(np.median(np.abs(d - m)))
    if s == 0 and n > 1:
        s = float(np.std(d, ddof=1))       # 값이 계단식(양자화)이라 MAD가 0인 경우
    h = Z90 * MEDIAN_SE * s / math.sqrt(n) if n else np.nan
    ref_med = float(np.median(g["ref"]))
    has_blank = not math.isnan(sigma0)
    d_rel = r * abs(ref_med)
    d_blank = Z90 * sigma0 if has_blank else 0.0
    delta = d_rel + d_blank
    lo, hi = m - h, m + h
    out_mask = np.abs(d - m) > OUTLIER_K * s if s > 0 else np.zeros(n, bool)

    if n < MIN_PAIRS:
        verdict, reason = "미결", f"die 부족(n<{MIN_PAIRS})"
    elif delta == 0:
        verdict, reason = "미결", "허용폭 0(기준값 0, blank 없음)"
    elif -delta < lo and hi < delta:
        verdict, reason = "동등", ""
    elif hi <= -delta or lo >= delta:
        verdict, reason = "차이", "New가 큼" if m > 0 else "New가 작음"
    elif h >= delta:
        verdict, reason = "미결", "해상도 부족" + ("" if has_blank else " / blank 없음")
    else:
        verdict, reason = "미결", "경계 shift"

    return {"n_pair": n, "ref_median": ref_med, "new_median": float(np.median(g["new"])),
            "shift_m": m, "ci_lo": lo, "ci_hi": hi, "h": h, "robust_sd_d": s,
            "delta": delta, "delta_rel": d_rel, "delta_blank": d_blank,
            "h_over_delta": h / delta if delta else np.nan, "m_over_delta": abs(m) / delta if delta else np.nan,
            "D95_abs_d": float(np.percentile(np.abs(d), 95)), "n_outlier_die": int(out_mask.sum()),
            "verdict": verdict, "reason": reason}, out_mask


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", nargs="+", required=True)
    ap.add_argument("--new", nargs="+", required=True)
    ap.add_argument("--blank", nargs="*", default=[])
    ap.add_argument("--blank-map")
    ap.add_argument("--r", type=float, default=0.01, help="상대 허용폭 (기본 0.01 = 1%%)")
    ap.add_argument("--key", default="WAFERID,DIE_X_Y,ITEM", help="die·item 짝짓기 키 (ITEM 포함 필수)")
    ap.add_argument("--out", default="infra_compare_out")
    ap.add_argument("--encoding", default="auto", help="auto(기본: UTF-8, 안 되면 CP949) 또는 cp949, euc-kr 등")
    a = ap.parse_args()

    key = [k.strip() for k in a.key.split(",")]
    if "ITEM" not in key:
        sys.exit("--key 에 ITEM 이 있어야 합니다")
    ref = load_side(a.ref, "Ref", a.encoding)
    new = load_side(a.new, "New", a.encoding)
    paired, counts = pair_up(ref, new, key)
    if paired.empty:
        sys.exit("짝지어진 die가 없습니다. --key (WAFERID, DIE_X_Y 등)가 두 데이터에서 같은지 확인하세요")

    blank = load_blank(a.blank, a.encoding) if a.blank else pd.DataFrame(columns=["BLANK_ITEM", "sigma0"])
    items = pd.DataFrame({"ITEM": paired["ITEM"].unique()})
    if a.blank_map:
        mp = read_csv_auto(Path(a.blank_map), a.encoding)
        mp.columns = [c.strip().upper() for c in mp.columns]
        items = items.merge(mp[["ITEM", "BLANK_ITEM"]], on="ITEM", how="left")
        items["BLANK_ITEM"] = items["BLANK_ITEM"].fillna(items["ITEM"])
    else:
        items["BLANK_ITEM"] = items["ITEM"]
    items = items.merge(blank, on="BLANK_ITEM", how="left").set_index("ITEM")

    results, outliers = [], []
    for item, g in paired.groupby("ITEM", sort=True):
        sigma0 = float(items.at[item, "sigma0"]) if pd.notna(items.at[item, "sigma0"]) else math.nan
        res, mask = judge_item(g, a.r, sigma0)
        unit = g["UNIT"].iloc[0]
        bu = items.at[item, "blank_unit"] if "blank_unit" in items.columns else None
        if pd.notna(bu) and unit and bu != unit:
            res["reason"] = (res["reason"] + " / " if res["reason"] else "") + f"blank 단위 다름({bu})"
        results.append({"ITEM": item, "UNIT": unit, **res, "sigma0": sigma0,
                        "blank_item": items.at[item, "BLANK_ITEM"] if pd.notna(sigma0) else "",
                        "blank_drift_ratio": items.at[item, "blank_drift_ratio"]
                        if "blank_drift_ratio" in items.columns else np.nan})
        if mask.any():
            o = g.loc[mask, key + ["ref", "new"]].assign(d=lambda x: x["new"] - x["ref"], shift_m=res["shift_m"])
            outliers.append(o)

    res = pd.DataFrame(results).set_index("ITEM").join(counts, how="left").fillna(
        {c: 0 for c in counts.columns}).reset_index()
    order = {"차이": 0, "미결": 1, "동등": 2}
    res = res.sort_values(by=["verdict", "m_over_delta"], key=lambda c: c.map(order) if c.name == "verdict" else -c)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "items.csv", index=False, encoding="utf-8-sig")
    if outliers:
        pd.concat(outliers).to_csv(out / "outlier_dies.csv", index=False, encoding="utf-8-sig")
    if not blank.empty:
        blank.to_csv(out / "blank_sigma.csv", index=False, encoding="utf-8-sig")

    print(f"\n판정 (r = {a.r:.2%}, ITEM {len(res):,}개)")
    print(res["verdict"].value_counts().reindex(["동등", "차이", "미결"], fill_value=0).to_string())
    und = res[res["verdict"] == "미결"]
    if len(und):
        print("\n미결 사유")
        print(und["reason"].value_counts().to_string())
    print(f"\n출력: {out / 'items.csv'}" + (f", {out / 'outlier_dies.csv'}" if outliers else "")
          + (f", {out / 'blank_sigma.csv'}" if not blank.empty else ""))


if __name__ == "__main__":
    main()
