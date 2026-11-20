#!/usr/bin/env python3
"""read_dcnormal 속도 비교: (a) 전체 읽기 후 ITEM 거르기 vs (b) items=집합 으로 읽을 때부터 거르기 (--only 경로).

합성 DCNORMAL 파일을 임시 폴더에 스스로 만든다(실제 데이터 불필요).
usage:
  python tools/bench_read_only.py [--items 6000] [--dies 60] [--files 3] [--pick 2] [--repeat 3] [--seed 0]
"""
from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra_compare import MEASURE_COLS, read_dcnormal  # noqa: E402


def write_synthetic(path: Path, items: list[str], dies: int, rng: random.Random) -> None:
    lines = ["#FileFormatInformationStart", "FILEFORMAT=DCNORMAL", "#FileFormatInformationEnd",
             "#HeaderStart", f"LOTID=LOT{rng.randrange(1000)}", f"WAFERID=W{rng.randrange(25)}", "EQPID=EQ0",
             "STARTDATETIME=2000/01/01 00:00:00", "#HeaderEnd", "#MeasureDataStart", ",".join(MEASURE_COLS)]
    for d in range(dies):
        xy = f"{d % 10}_{d // 10}"
        for it in items:
            lines.append(f"{xy},{xy},{xy},PT,1,1,1,{it},[V],1,{rng.gauss(1.0, 0.1):.6E},0,2,0,PASS")
    lines += ["#MeasureDataEnd", "[EOF]"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def full_then_filter(files: list[Path], keep: set[str]) -> pd.DataFrame:
    parts = [df[df["ITEM"].isin(keep)] for df in (read_dcnormal(f, "auto") for f in files)]
    return pd.concat(parts, ignore_index=True)


def read_only(files: list[Path], keep: set[str]) -> pd.DataFrame:
    return pd.concat([read_dcnormal(f, "auto", items=keep) for f in files], ignore_index=True)


def best_time(fn, repeat: int) -> tuple[float, pd.DataFrame]:
    best, out = float("inf"), None
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t0)
    return best, out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--items", type=int, default=6000, help="파일당 ITEM 수")
    p.add_argument("--dies", type=int, default=60, help="파일당 die 수")
    p.add_argument("--files", type=int, default=3, help="파일 수")
    p.add_argument("--pick", type=int, default=2, help="지정할 ITEM 수(--only)")
    p.add_argument("--repeat", type=int, default=3, help="반복 횟수(최소 시간 사용)")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)
    if min(a.items, a.dies, a.files, a.repeat) < 1 or not 0 <= a.pick <= a.items:
        p.error("--items/--dies/--files/--repeat 는 1 이상, --pick 은 0..--items")

    rng = random.Random(a.seed)
    items = [f"T{i:05d}" for i in range(a.items)]
    keep = set(rng.sample(items, a.pick))
    with tempfile.TemporaryDirectory() as tmp:
        files = [Path(tmp) / f"s{k}.result" for k in range(a.files)]
        for f in files:
            write_synthetic(f, items, a.dies, rng)
        size_mb = sum(f.stat().st_size for f in files) / 1e6
        t_full, df_full = best_time(lambda: full_then_filter(files, keep), a.repeat)
        t_only, df_only = best_time(lambda: read_only(files, keep), a.repeat)
    pd.testing.assert_frame_equal(df_only, df_full)

    print(f"합성 DCNORMAL {a.files}개 ({size_mb:.1f} MB, 파일당 {a.items:,} ITEM × {a.dies} die), "
          f"지정 ITEM {a.pick}개, 반복 {a.repeat}회 최소값")
    print(f"{'방식':<24}{'시간(s)':>10}{'행':>10}")
    print(f"{'(a) 전체 읽기 후 거르기':<24}{t_full:>10.3f}{len(df_full):>10,}")
    print(f"{'(b) items= 로 읽기':<24}{t_only:>10.3f}{len(df_only):>10,}")
    print(f"속도 배수 (a)/(b): {t_full / t_only:.1f}x, 결과 동일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
