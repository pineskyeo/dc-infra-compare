"""POR 회차와 DOE의 ITEM별 원데이터 통계를 낸다. 판정에는 쓰지 않는 참고 표다.

  python raw_stats.py --por POR1/ --por POR2/ --doe DOE/ --out 결과

모든 숫자 행을 그대로 쓴다. die 맞추기, 중복 제거, 이상치 제거, 절삭을 하지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from infra_compare import find_files, read_dcnormal
from por_doe_compare import add_common_args


DOE_COLUMNS = ("n_raw_DOE", "n_nonnum_DOE", "median_raw_DOE", "sd_raw_DOE")
RUN_COLUMNS = ("n_raw", "n_nonnum", "median_raw", "sd_raw", "med_shift", "sigma_ratio", "raw_note")


def column_names(n_runs: int) -> list[str]:
    """raw_stats.csv 열 순서. report_v2 가 파일이 없을 때 빈 열을 만드는 데도 쓴다."""
    return ["ITEM", *DOE_COLUMNS, *(f"{name}_POR{k}" for k in range(1, n_runs + 1) for name in RUN_COLUMNS)]


def _values(frame: pd.DataFrame, item: str) -> tuple[np.ndarray, int]:
    if frame is None or frame.empty:
        return np.array([], dtype=float), 0
    data = pd.to_numeric(frame.loc[frame["ITEM"].astype(str) == item, "DATA"], errors="coerce")
    return data.dropna().to_numpy(dtype=float), int(data.isna().sum())


def _median_sd(values: np.ndarray) -> tuple[float, float]:
    if not len(values):
        return np.nan, np.nan
    return float(np.median(values)), float(np.std(values, ddof=1)) if len(values) > 1 else np.nan


def _shift_ratio(ref: np.ndarray, doe: np.ndarray, sd_ref: float, sd_doe: float) -> tuple[float, float, str]:
    if len(ref) < 2 or len(doe) < 2:
        return np.nan, np.nan, "n<2"
    if not np.isfinite(ref).all() or not np.isfinite(doe).all():
        return np.nan, np.nan, "비유한 값"
    if sd_ref == 0:
        return np.nan, np.nan, "σ_ref=0"
    shift = abs(float(np.median(ref)) - float(np.median(doe))) / sd_ref
    return shift, (0.0 if sd_doe == 0 else sd_doe / sd_ref), ""


def raw_stats(por_frames: list[pd.DataFrame], doe_frame: pd.DataFrame) -> pd.DataFrame:
    """긴 형식 POR 회차들과 DOE 에서 ITEM 별 원데이터 통계를 계산한다."""
    frames = [*por_frames, doe_frame]
    items = sorted({str(item) for frame in frames if frame is not None and not frame.empty
                    for item in frame["ITEM"].dropna().unique()})
    rows = []
    for item in items:
        doe, doe_nonnum = _values(doe_frame, item)
        doe_median, doe_sd = _median_sd(doe)
        row = {"ITEM": item, "n_raw_DOE": len(doe), "n_nonnum_DOE": doe_nonnum,
               "median_raw_DOE": doe_median, "sd_raw_DOE": doe_sd}
        for k, frame in enumerate(por_frames, 1):
            ref, ref_nonnum = _values(frame, item)
            ref_median, ref_sd = _median_sd(ref)
            shift, ratio, note = _shift_ratio(ref, doe, ref_sd, doe_sd)
            row.update({f"n_raw_POR{k}": len(ref), f"n_nonnum_POR{k}": ref_nonnum,
                        f"median_raw_POR{k}": ref_median, f"sd_raw_POR{k}": ref_sd,
                        f"med_shift_POR{k}": shift, f"sigma_ratio_POR{k}": ratio, f"raw_note_POR{k}": note})
        rows.append(row)
    return pd.DataFrame(rows, columns=column_names(len(por_frames)))


def read_side(inputs: list[str], encoding: str = "auto") -> pd.DataFrame:
    """load_side 와 같은 파일 찾기·파싱을 쓰되 숫자 아닌 DATA 행도 남긴다."""
    files = find_files(inputs)
    if not files:
        raise ValueError(f"DCNORMAL 파일이 없습니다 ({inputs})")
    return pd.concat([read_dcnormal(path, encoding) for path in files], ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--out", default="por_doe_out")
    a = ap.parse_args(argv)
    por_frames = [read_side(run, a.encoding) for run in a.por]
    result = raw_stats(por_frames, read_side(a.doe, a.encoding))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "raw_stats.csv"
    result.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"원데이터 통계: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
