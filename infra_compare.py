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

blank가 있는 ITEM은 먼저 구간을 나눈다 (CLSI EP17 / IUPAC, μ·SD = blank 평균·표준편차):
  LoB = |μ| + 1.645·SD,  LoD = |μ| + 3.29·SD,  LoQ = |μ| + 10·SD
  구간은 median(|Ref|)로 정한다.
  < LoD       : 검출한계 이하  → 숫자 비교 안 함. die별 검출 일치로 판정
  LoD ~ LoQ   : 검출~정량      → 숫자 비교 안 함. die별 검출 일치로 판정
  ≥ LoQ       : 정량           → 위 TOST
  검출 여부(|값| ≥ LoD)가 한쪽만 나온 die가 한 방향으로 치우치면(McNemar p < 0.05) 그리고 순차이가 5%를 넘으면 차이.
측정값 자체의 1회 흔들림 robustσ(New − Ref)/√2 가 blank보다 크거나 blank가 없으면 그 값으로 같은 구간을 나눈다 (μ = 0).

usage:
  python infra_compare.py --ref REF_DIR --new NEW_DIR [--blank BLANK ...] [--blank-map map.csv]
                          [--r 0.01] [--key WAFERID,COORD_X_Y,ITEM] [--out result_dir]
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
K_LOB, K_LOD, K_LOQ = 1.645, 3.29, 10.0
MISMATCH_MAX = 0.05
VERBOSE = False


def info(msg: str) -> None:
    if VERBOSE:
        print(msg)


ZONE_FLOOR, ZONE_DETECT, ZONE_QUANT, ZONE_NOBLANK = "검출한계 이하", "검출~정량", "정량", "blank 없음"


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
    info(f"[{label}] 파일 {len(files)}개 (인코딩 {encs}), 측정 {len(df):,}행 (숫자 아닌 DATA {n_nan}행 제외), "
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
    info(f"[Blank] σ₀ 확보 ITEM {len(out)}개")
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
    info(f"[짝짓기] 키 {key}: 짝 {len(paired):,}개, Ref만 {int(cnt['n_ref_only'].sum()):,}, "
          f"New만 {int(cnt['n_new_only'].sum()):,}, 중복 키(중앙값 사용) Ref {int(cnt['n_dup_ref'].sum()):,} / "
          f"New {int(cnt['n_dup_new'].sum()):,}")
    return paired, cnt


def ref_repeat(ref: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """Ref에서 같은 키를 두 번 이상 잰 die로 ITEM별 재측정 흔들림을 구한다.
    rep_sigma = 1회 측정의 흔들림 = robustσ(2회차 − 1회차) / √2,  rep_shift = median(2회차 − 1회차)."""
    r = ref.sort_values(["FILE", "LINE"]).assign(_rep=lambda x: x.groupby(key).cumcount())
    r = r[r["_rep"] < 2]
    two = r.pivot_table(index=key, columns="_rep", values="DATA", aggfunc="first")
    if 1 not in two.columns:
        return pd.DataFrame(columns=["n_rep", "rep_shift", "rep_sigma"])
    d = (two[1] - two[0]).dropna().rename("d").reset_index()

    def robust(x: pd.Series) -> float:
        return 1.4826 * float(np.median(np.abs(x - np.median(x)))) / math.sqrt(2)
    st = d.groupby("ITEM")["d"].agg(n_rep="size", rep_shift="median", rep_sigma=robust)
    st = st[st["n_rep"] >= MIN_PAIRS]
    info(f"[Ref 재측정] 같은 die를 두 번 잰 ITEM {len(st)}개 (die {MIN_PAIRS}개 이상)")
    return st


def judge_item(g: pd.DataFrame, r: float, sigma0: float) -> tuple[dict, np.ndarray]:
    d = (g["new"] - g["ref"]).to_numpy(dtype=float)
    n = len(d)
    m = float(np.median(d))
    s = 1.4826 * float(np.median(np.abs(d - m)))
    stepped = s == 0 and n > 1
    if stepped:
        s = float(np.std(d, ddof=1))       # 값이 계단식(양자화)이라 MAD가 0인 경우
    h = Z90 * MEDIAN_SE * s / math.sqrt(n) if n else np.nan
    ref_med = float(np.median(g["ref"]))
    has_noise = not math.isnan(sigma0)
    d_rel = r * abs(ref_med)
    d_noise = Z90 * sigma0 if has_noise else 0.0
    delta = d_rel + d_noise
    lo, hi = m - h, m + h
    out_mask = np.abs(d - m) > OUTLIER_K * s if s > 0 else np.zeros(n, bool)

    if n < MIN_PAIRS:
        verdict, reason = "미결", f"die 부족(n<{MIN_PAIRS})"
    elif delta == 0:
        verdict, reason = "미결", "허용폭 0(기준값 0, 흔들림 정보 없음)"
    elif -delta < lo and hi < delta:
        verdict, reason = "동등", ""
    elif h >= delta:
        # 허용폭이 해상도보다 작으면 노이즈 수준의 shift도 '차이'로 잡히므로 판정하지 않는다
        pos = float((g["ref"] > 0).mean())
        why = [w for w, hit in (("die 적음", n < 40), ("부호 섞임", 0.1 < pos < 0.9),
                                ("계단값", stepped), ("흔들림 정보 없음", not has_noise)) if hit]
        verdict, reason = "미결", "해상도 부족" + (f" ({', '.join(why)})" if why else "")
    elif hi <= -delta or lo >= delta:
        verdict, reason = "차이", "New가 큼" if m > 0 else "New가 작음"
    else:
        verdict, reason = "미결", "경계 shift"

    return {"n_pair": n, "ref_median": ref_med, "new_median": float(np.median(g["new"])),
            "shift_m": m, "ci_lo": lo, "ci_hi": hi, "h": h, "robust_sd_d": s,
            "delta": delta, "delta_rel": d_rel, "delta_noise": d_noise,
            "h_over_delta": h / delta if delta else np.nan, "m_over_delta": abs(m) / delta if delta else np.nan,
            "D95_abs_d": float(np.percentile(np.abs(d), 95)), "n_outlier_die": int(out_mask.sum()),
            "verdict": verdict, "reason": reason}, out_mask


def blank_limits(row: pd.Series) -> tuple[float, float, float] | None:
    sd = row.get("blank_sd")
    sd = float(sd) if pd.notna(sd) else float(row.get("sigma0", np.nan))
    if math.isnan(sd):
        return None
    mu = row.get("blank_offset")
    mu = abs(float(mu)) if pd.notna(mu) else 0.0
    return mu + K_LOB * sd, mu + K_LOD * sd, mu + K_LOQ * sd


def mcnemar_p(b: int, c: int) -> float:
    """짝지은 검출 여부의 McNemar 정확 검정 (양측). b, c = 한쪽만 검출된 die 수."""
    k, m = min(b, c), b + c
    if m == 0:
        return 1.0
    tail = sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m
    return min(1.0, 2 * tail)


def judge_detection(g: pd.DataFrame, lob: float, lod: float, zone: str) -> tuple[dict, np.ndarray]:
    """die별 검출 여부(|값| ≥ LoD)를 두 인프라가 같은 비율로 내는지 본다.
    차이 = 한쪽만 검출된 die가 한 방향으로 치우치고(McNemar p < 0.05) 그 순차이가 die의 5%를 넘을 때."""
    rd, nd = g["ref"].abs().to_numpy() >= lod, g["new"].abs().to_numpy() >= lod
    b, c = int((rd & ~nd).sum()), int((~rd & nd).sum())
    n = len(rd)
    p = mcnemar_p(b, c)
    net = (c - b) / n if n else 0.0
    if n < MIN_PAIRS:
        verdict, reason = "미결", f"die 부족(n<{MIN_PAIRS})"
    elif p < 0.05 and abs(net) > MISMATCH_MAX:
        verdict, reason = "차이", f"{zone}: {'New' if net > 0 else 'Ref'}만 검출 die가 {abs(net):.0%} 더 많음"
    else:
        verdict, reason = "동등", f"{zone}: 검출 일치"
    return {"verdict": verdict, "reason": reason, "n_mismatch_die": b + c, "only_ref_detect": b, "only_new_detect": c,
            "mcnemar_p": p, "ref_detect_frac": float(rd.mean()), "new_detect_frac": float(nd.mean())}, rd != nd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", nargs="+", required=True)
    ap.add_argument("--new", nargs="+", required=True)
    ap.add_argument("--blank", nargs="*", default=[])
    ap.add_argument("--blank-map")
    ap.add_argument("--r", type=float, default=0.01, help="상대 허용폭 (기본 0.01 = 1%%)")
    ap.add_argument("--key", default="WAFERID,COORD_X_Y,ITEM", help="die·item 짝짓기 키 (ITEM 포함 필수)")
    ap.add_argument("--out", default="infra_compare_out")
    ap.add_argument("--encoding", default="auto", help="auto(기본: UTF-8, 안 되면 CP949) 또는 cp949, euc-kr 등")
    ap.add_argument("--no-repeat", action="store_true", help="Ref 재측정 흔들림을 허용폭에 넣지 않음")
    ap.add_argument("--verbose", action="store_true", help="입력 요약, 재측정 반영 전후, 항목군·값 구간 표까지 출력")
    ap.add_argument("--family-regex", default=r"^[A-Za-z]+",
                    help="ITEM 이름에서 항목군을 뽑는 정규식 (기본: 앞쪽 영문자. 예: VTN_LIN_1 → VTN)")
    a = ap.parse_args()
    global VERBOSE
    VERBOSE = a.verbose

    key = [k.strip() for k in a.key.split(",")]
    if "ITEM" not in key:
        sys.exit("--key 에 ITEM 이 있어야 합니다")
    ref = load_side(a.ref, "Ref", a.encoding)
    new = load_side(a.new, "New", a.encoding)
    paired, counts = pair_up(ref, new, key)
    if paired.empty:
        sys.exit("짝지어진 die가 없습니다. --key (WAFERID, COORD_X_Y 등)가 두 데이터에서 같은지 확인하세요")
    per_item = paired.groupby("ITEM").size()
    if per_item.median() < MIN_PAIRS:
        filled = {c: int(ref[c].nunique()) for c in ("COORD_X_Y", "FLAT_X_Y", "DIE_X_Y")}
        print(f"\n  경고: ITEM당 짝 die 수 중앙값이 {per_item.median():.0f}개뿐입니다. 키 {key}가 die를 구별하지 못하는 것 같습니다.\n"
              f"  Ref의 좌표 열별 서로 다른 값 개수: {filled}. 값이 많은 열을 --key 에 쓰세요.\n", file=sys.stderr)

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
    items["FAMILY"] = items.index.to_series().str.extract(f"({a.family_regex})", expand=False).fillna("(기타)")
    items["ref_abs"] = paired.groupby("ITEM")["ref"].median().abs()
    rep = pd.DataFrame(columns=["n_rep", "rep_shift", "rep_sigma"]) if a.no_repeat else ref_repeat(ref, key)
    items = items.join(rep, how="left")
    rel = (items["rep_sigma"] / items["ref_abs"]).where(items["ref_abs"] > 0)
    fam_rel = rel.groupby(items["FAMILY"]).agg(["median", "count"])
    fam_rel = fam_rel.loc[fam_rel["count"] >= 3, "median"]

    results, outliers, mismatches = [], [], []
    for item, g in paired.groupby("ITEM", sort=True):
        sigma0 = float(items.at[item, "sigma0"]) if pd.notna(items.at[item, "sigma0"]) else math.nan
        sigma_rep, source = math.nan, ""
        if pd.notna(items.at[item, "rep_sigma"]):
            sigma_rep, source = float(items.at[item, "rep_sigma"]), "재측정"
        elif items.at[item, "FAMILY"] in fam_rel.index:
            sigma_rep, source = float(fam_rel[items.at[item, "FAMILY"]]) * float(items.at[item, "ref_abs"]), "항목군 추정"
        sigma_noise = float(np.nanmax([sigma0, sigma_rep])) if not (math.isnan(sigma0) and math.isnan(sigma_rep)) else math.nan
        noise_source = ("blank" if sigma_noise == sigma0 else source) if not math.isnan(sigma_noise) else ""
        base, _ = judge_item(g, a.r, sigma0)
        res, mask = judge_item(g, a.r, sigma_noise)
        res.update(verdict_blank_only=base["verdict"], sigma_rep=sigma_rep, noise_source=noise_source,
                   rep_shift=items.at[item, "rep_shift"], FAMILY=items.at[item, "FAMILY"],
                   rel_noise_d=res["robust_sd_d"] / abs(res["ref_median"]) if res["ref_median"] else np.nan)
        # 실제 측정 흔들림이 blank보다 크면 그쪽으로 한계를 정한다. 1회 측정 흔들림 = robustσ(New − Ref) / √2
        s_meas = res["robust_sd_d"] / math.sqrt(2)
        lim, limit_source = blank_limits(items.loc[item]), "blank"
        if s_meas > 0 and (lim is None or K_LOD * s_meas > lim[1]):
            lim, limit_source = (K_LOB * s_meas, K_LOD * s_meas, K_LOQ * s_meas), "자체 흔들림"
        if lim is None:
            res["zone"] = ZONE_NOBLANK
        else:
            lob, lod, loq = lim
            ref_abs = float(g["ref"].abs().median())
            res.update(LoB=lob, LoD=lod, LoQ=loq, limit_source=limit_source)
            res["zone"] = ZONE_FLOOR if ref_abs < lod else ZONE_DETECT if ref_abs < loq else ZONE_QUANT
            if res["zone"] != ZONE_QUANT:
                det, mis = judge_detection(g, lob, lod, res["zone"])
                res.update(det, verdict_blank_only=det["verdict"])
                if mis.any():
                    mismatches.append(g.loc[mis, key + ["ref", "new"]].assign(LoB=lob, LoD=lod))
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
    files = [out / "items.csv"]
    for name, frames in (("outlier_dies.csv", outliers), ("mismatch_dies.csv", mismatches)):
        if frames:
            pd.concat(frames).to_csv(out / name, index=False, encoding="utf-8-sig")
            files.append(out / name)
    if not blank.empty:
        blank.to_csv(out / "blank_sigma.csv", index=False, encoding="utf-8-sig")
        files.append(out / "blank_sigma.csv")

    fam, lvl = pattern_tables(res)
    fam.to_csv(out / "patterns_family.csv", encoding="utf-8-sig")
    lvl.to_csv(out / "patterns_level.csv", encoding="utf-8-sig")
    files += [out / "patterns_family.csv", out / "patterns_level.csv"]

    verdicts = ["동등", "차이", "미결"]
    if VERBOSE:
        src = res["limit_source"].fillna("") if "limit_source" in res else pd.Series("", index=res.index)
        view = res["zone"] + np.where(src == "", "", " (" + src + ")")
        zones = [f"{z} ({s})" for z in (ZONE_FLOOR, ZONE_DETECT, ZONE_QUANT) for s in ("blank", "자체 흔들림")] + [ZONE_NOBLANK]
    else:
        view, zones = res["zone"], [ZONE_FLOOR, ZONE_DETECT, ZONE_QUANT, ZONE_NOBLANK]
    tab = pd.crosstab(view, res["verdict"]).reindex(index=zones, columns=verdicts, fill_value=0)
    tab = tab[tab.sum(axis=1) > 0]
    tab.loc["합계"] = tab.sum()
    print(f"\n판정 (ITEM {len(res):,}개, 짝 die 중앙값 {int(per_item.median())}개, r = {a.r:.0%})")
    print(tab.rename_axis(index=None, columns=None).to_string())
    for label, v in (("차이", "차이"), ("미결", "미결")):
        sub = res.loc[res["verdict"] == v, "reason"].fillna("")
        if len(sub):
            kind = (sub.str.replace(r"^[^:]*: ", "", regex=True)
                       .str.replace(r"die가 \d+% 더 많음", "die가 더 많음", regex=True))
            print(f"\n{label} 사유")
            print(kind.value_counts().rename_axis(None).to_string())
    if VERBOSE:
        if not a.no_repeat:
            print("\n재측정 흔들림 반영 전(blank만) → 후")
            print(pd.crosstab(res["verdict_blank_only"], res["verdict"]).reindex(
                index=verdicts, columns=verdicts, fill_value=0).rename_axis(index="전", columns="후").to_string())
            print("흔들림 출처: " + str(res["noise_source"].replace("", "없음").value_counts().to_dict()))
        print("\n동등이 아닌 ITEM이 많은 항목군 (상위 10)")
        print(fam.head(10).to_string())
        print("\n값 구간별 (단위, 10의 거듭제곱)")
        print(lvl.to_string())
        print("\n출력: " + ", ".join(str(f) for f in files))
    else:
        print(f"\n결과: {out}/items.csv (verdict, reason 열). 자세한 화면은 --verbose")


def pattern_tables(res: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """동등이 아닌 ITEM이 어느 항목군·값 구간에 몰리는지. rel_noise_d = die별 차이의 흔들림 / |Ref 값|."""
    r = res.assign(not_eq=res["verdict"] != "동등", unresolved=res["reason"].fillna("").str.startswith("해상도"),
                   decade=np.floor(np.log10(res["ref_median"].abs().where(res["ref_median"] != 0))))

    def summarize(g: pd.core.groupby.DataFrameGroupBy) -> pd.DataFrame:
        t = g.agg(ITEM수=("ITEM", "size"), 동등아님=("not_eq", "sum"), 해상도부족=("unresolved", "sum"),
                  차이=("verdict", lambda v: int((v == "차이").sum())), 흔들림_중앙값=("rel_noise_d", "median"))
        t["동등아님_비율"] = (t["동등아님"] / t["ITEM수"]).round(3)
        t["흔들림_중앙값"] = t["흔들림_중앙값"].round(3)
        return t
    fam = summarize(r.groupby("FAMILY")).sort_values(["동등아님", "동등아님_비율"], ascending=False)
    r["level"] = r["UNIT"].fillna("") + " 1e" + r["decade"].astype("Int64").astype(str)
    lvl = summarize(r.groupby("level")).sort_index()
    return fam, lvl


if __name__ == "__main__":
    main()
