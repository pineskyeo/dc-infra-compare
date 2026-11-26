"""합성 데이터로 report_v2 브라우저 리포트를 처음부터 끝까지 만든다.

  python examples/demo_report_v2.py OUT [--items N] [--dies D] [--seed S] [--images MODE]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(label: str, argv: list[object]) -> float:
    started = time.perf_counter()
    print(f"\n[{label}] 시작", flush=True)
    subprocess.run([sys.executable, *map(str, argv)], cwd=ROOT, check=True)
    seconds = time.perf_counter() - started
    print(f"[{label}] {seconds:.2f}초", flush=True)
    return seconds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, metavar="OUT")
    parser.add_argument("--items", type=int, default=6000)
    parser.add_argument("--dies", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--images", choices=("fail", "fail+pending", "all", "none"), default="fail")
    args = parser.parse_args()
    out = args.out.resolve()
    common = [
        *(arg for run in (1, 2, 3) for arg in ("--por", out / f"por_run{run}")),
        "--doe", out / "doe",
        "--level", out / "level.csv",
        "--blank", out / "blank",
        "--blank-map", out / "blank_map.csv",
    ]
    started = time.perf_counter()
    run_step("합성 데이터", [ROOT / "examples" / "make_load_data.py", out,
                             "--items", args.items, "--dies", args.dies, "--seed", args.seed])
    run_step("POR/DOE 판정", [ROOT / "por_doe_compare.py", *common, "--out", out])
    run_step("원데이터 통계", [ROOT / "raw_stats.py", *common, "--out", out])
    run_step("LoQ 점검", [ROOT / "loq_check.py", "--input", out / "items.csv", "--out", out, *common])
    run_step("브라우저 리포트", [ROOT / "report_v2.py", out, *common, "--images", args.images])
    print(f"\n전체 {time.perf_counter() - started:.2f}초")
    print(f"리포트: {out / 'report' / 'index.html'}")


if __name__ == "__main__":
    main()
