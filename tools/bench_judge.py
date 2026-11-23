#!/usr/bin/env python3
"""판정 속도 기준: make_load_data.py 부하 데이터(N ITEM, die 61, POR 3회 + DOE + blank)로 por_doe_compare.py 를
처음부터 끝까지 여러 번 돌려 시간 중앙값과 최대 메모리를 출력한다.

최대 메모리는 가장 큰 단일 프로세스 값(ru_maxrss, 병렬 작업자 포함)이고 작업자 합이 아니다. 병렬 작업 수는 DC_JOBS
(없으면 CPU 수)를 그대로 따른다.

usage: python tools/bench_judge.py N [--runs 3] [--seed 7]
"""
from __future__ import annotations

import argparse
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIES = 61


def maxrss_mb(ru_maxrss: int) -> float:
    return ru_maxrss / 2**20 if sys.platform == "darwin" else ru_maxrss / 2**10


def timed(argv: list[str]) -> tuple[float, float]:
    """(초, 최대 RSS MB). wait4 로 이 자식과 그 자식들의 rusage 만 본다."""
    t0 = time.perf_counter()
    proc = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    _, status, usage = os.wait4(proc.pid, 0)
    seconds = time.perf_counter() - t0
    proc.returncode = os.waitstatus_to_exitcode(status)
    if proc.returncode:
        sys.exit(f"rc={proc.returncode}: {' '.join(argv)}\n{proc.stderr.read().decode(errors='replace')[-2000:]}")
    proc.stderr.close()
    return seconds, maxrss_mb(usage.ru_maxrss)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("n", type=int, help="ITEM 수")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    py = [sys.executable, "-B"]
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "load"
        gen_s, _ = timed([*py, str(ROOT / "examples" / "make_load_data.py"), str(data), "--items", str(a.n),
                          "--dies", str(DIES), "--seed", str(a.seed)])
        judge = [*py, str(ROOT / "por_doe_compare.py"),
                 "--por", str(data / "por_run1"), "--por", str(data / "por_run2"), "--por", str(data / "por_run3"),
                 "--doe", str(data / "doe"), "--level", str(data / "level.csv"), "--blank", str(data / "blank"),
                 "--blank-map", str(data / "blank_map.csv")]
        runs = [timed([*judge, "--out", str(Path(tmp) / f"out{i}")]) for i in range(a.runs)]
        judged = {(Path(tmp) / f"out{i}" / "items.csv").read_text(encoding="utf-8-sig").count("\n") - 1
                  for i in range(a.runs)}
    if judged != {a.n}:
        sys.exit(f"items.csv 행 수가 ITEM 수와 다름: {sorted(judged)} != {a.n}")
    secs = [s for s, _ in runs]
    print(f"ITEM {a.n}, die {DIES}, POR 3회 + DOE, --level --blank, seed {a.seed}, "
          f"DC_JOBS={os.environ.get('DC_JOBS', '') or f'(CPU {os.cpu_count()})'}")
    print(f"machine: {platform.platform()}, {platform.machine()}, Python {platform.python_version()}")
    print(f"data generation: {gen_s:.2f} s, items.csv rows per run: {a.n}")
    print("por_doe_compare runs (s): " + ", ".join(f"{s:.2f}" for s in secs))
    print(f"median: {statistics.median(secs):.2f} s")
    print(f"peak RSS: {max(m for _, m in runs):.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
