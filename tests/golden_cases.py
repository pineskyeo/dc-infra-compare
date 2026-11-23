"""판정 불변 검사의 데이터 묶음과 실행. tests/test_verdicts_golden.py 와 tools/update_golden.py 가 같이 쓴다.

묶음마다 합성 데이터(seed 고정)를 만들고 por_doe_compare.py 를 돌려 items.csv 의 판정 열(VERDICT_COLS)만 글자 그대로
남긴다. 정답 파일은 tests/data/golden/<묶음>.csv.
"""
from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "data" / "golden"
VERDICT_COLS = ("ITEM", "verdict", "verdict_final", "verdict_basis", "zone", "reason", "verdict_log", "log_reason",
                "verdict_with_accuracy", "scale", "status")
DCNORMAL_HEAD = [
    "#FileFormatInformationStart", "FILEFORMAT=DCNORMAL", "#FileFormatInformationEnd", "#ProductInformationStart",
    "WAFERID=W01", "#ProductInformationEnd", "#MeasureDataStart",
    "COORD_X_Y,FLAT_X_Y,DIE_X_Y,POINT_NAME,MODULE_NO,BIN,DUT,ITEM,UNIT,MEASURE_PNT,DATA,SPECLOW,SPECHIGH,JUDGE_LIM,JUDGE_RST",
]


def _run(argv: list, cwd: Path = ROOT) -> None:
    env = {**os.environ, "OMP_NUM_THREADS": "1"}
    done = subprocess.run([sys.executable, "-B", *map(str, argv)], cwd=cwd, env=env, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"{argv[0]} rc={done.returncode}\n{done.stderr[-3000:]}")


def make_por3(data: Path) -> None:
    _run([ROOT / "examples" / "make_por3_data.py", data])
    (data / "groups.csv").write_text("ITEM,group\nVT_SAME,VT\nVT_SHIFT,VT\nVT_NOISY_DOE,VT\nRON_CONTACT,RON\n"
                                     "IOFF_FLOOR,IOFF\nIOFF_LEAK,IOFF\nIOFF_STEP,IOFF\n", encoding="utf-8")
    (data / "scales.csv").write_text("group,scale\nVT,log\nRON,linear\n", encoding="utf-8")


def make_ref_new(data: Path) -> None:
    """make_test_data.py + add_hard_cases.py. ref 는 die를 나눠 담은 한 회분이라 POR 1회 = ref 의 재측정 없는 파일,
    POR 2회 = ref 전부(REF_zz_repeat 가 RON_A~C 를 한 번 더 잰 값이 중앙값에 들어감)로 POR 2회를 만든다."""
    _run([ROOT / "examples" / "make_test_data.py", data])
    _run([ROOT / "examples" / "add_hard_cases.py", data])
    (data / "level.csv").write_text("ITEM,LEVEL,CALCVAL,DERIVED\nVT_N,100mV,1,N\nVT_SHIFT,100mV,1,N\n"
                                    "IOFF_FLOOR,1pA,1,N\nIOFF_MAP,1pA,1,N\nILEAK_DETECT,1pA,1,N\nIOFF_OFFSET,1pA,1,N\n"
                                    "IOFF_LEAKY,1pA,1,N\nILEAK_WOBBLE,10pA,1,N\nION_BIMODAL,100uA,1,N\n"
                                    "RON_A,,,Y\n", encoding="utf-8")


# 정답을 아는 묶음 (scratchpad loq-check/compare_branch.py 가 쓰는 measure_rule_options.write_data 를 줄인 것)
TRUTH_DIES, TRUTH_SEEDS = 61, 2
TRUTH_SCALES = (0.001, 1.0, 1000.0)
TRUTH_RATIOS = {"wide": (1.0, 1.03, 1.1, 1.15, 1.3, 1.5), "noise floor": (1.0, 1.15), "excluded": (1.3,)}


def _truth_sample(kind: str, ratio: float, seed: int):
    rng = np.random.default_rng([seed, list(TRUTH_RATIOS).index(kind), round(ratio * 100)])
    log_die = rng.normal(0.0, 0.45, TRUTH_DIES)
    die = 10 ** (log_die - np.median(log_die))
    if kind == "excluded":
        die = np.round(die * 10, 6)
        return [die + offset for offset in (0.0, 0.25, 0.5)], die * ratio
    if kind == "noise floor":
        noisy = lambda value: value + rng.normal(0, 0.03, TRUTH_DIES)  # noqa: E731
    else:
        noisy = lambda value: value * 10 ** rng.normal(0, 0.008, TRUTH_DIES)  # noqa: E731
    return [noisy(die) for _ in range(3)], noisy(die * ratio)


def make_truth(data: Path) -> None:
    """ITEM 마다 DOE = POR × ratio (참 배율). scale 번호별 그룹 S0·S1·S2: S0 log, S1 auto, S2 는 표에 없음(auto).
    die 6개뿐인 FEW_DIE 하나를 더한다 (die 부족)."""
    lines = {name: [] for name in ("por1", "por2", "por3", "doe")}
    groups = ["ITEM,group"]
    n = 0
    for kind, ratios in TRUTH_RATIOS.items():
        for ratio in ratios:
            for seed in range(TRUTH_SEEDS):
                runs, doe = _truth_sample(kind, ratio, seed)
                for number, scale in enumerate(TRUTH_SCALES):
                    item = f"I{n:05d}"
                    n += 1
                    groups.append(f"{item},S{number}")
                    for name, values in zip(lines, (*runs, doe)):
                        for die, value in enumerate(values * scale):
                            xy = f"{die % 9}_{die // 9}"
                            lines[name].append(f"{xy},{xy},{xy},P1,1,1,1,{item},[u],1,{value:.15g},,,,")
    for name, values in zip(lines, ([1.0, 1.1, 0.9, 1.05, 0.95, 1.0], [1.01, 1.1, 0.92, 1.04, 0.95, 1.0],
                                    [0.99, 1.12, 0.9, 1.05, 0.96, 1.01], [1.2, 1.3, 1.1, 1.25, 1.15, 1.2])):
        lines[name] += [f"{die}_9,{die}_9,{die}_9,P1,1,1,1,FEW_DIE,[u],1,{value:.15g},,,," for die, value in enumerate(values)]
    for name, rows in lines.items():
        (data / name).mkdir(parents=True)
        (data / name / "DCNORMAL").write_text("\n".join(DCNORMAL_HEAD + rows + ["#MeasureDataEnd", "[EOF]"]) + "\n")
    (data / "groups.csv").write_text("\n".join(groups) + "\n", encoding="utf-8")
    (data / "scales.csv").write_text("group,scale\nS0,log\nS1,auto\n", encoding="utf-8")


@dataclass(frozen=True)
class Case:
    name: str
    data: str                       # DATASETS 키
    args: Callable[[Path], list]    # 데이터 폴더 → por_doe_compare.py 인자 (--out 빼고)


DATASETS: dict[str, Callable[[Path], None]] = {"por3": make_por3, "ref_new": make_ref_new, "truth": make_truth}


def _por3(d: Path) -> list:
    return ["--por", d / "por_run1", "--por", d / "por_run2", "--por", d / "por_run3", "--doe", d / "doe"]


def _por3_lb(d: Path) -> list:
    return [*_por3(d), "--level", d / "level.csv", "--blank", d / "blank", "--blank-map", d / "blank_map.csv"]


def _ref_new(d: Path) -> list:
    once = sorted(p for p in (d / "ref").iterdir() if p.name != "REF_zz_repeat")
    return ["--por", *once, "--por", d / "ref", "--doe", d / "new"]


def _truth(d: Path) -> list:
    return ["--por", d / "por1", "--por", d / "por2", "--por", d / "por3", "--doe", d / "doe"]


def _scales(d: Path) -> list:
    return ["--groups", d / "groups.csv", "--scales", d / "scales.csv"]


CASES = (
    Case("por3", "por3", _por3),
    Case("por3_level_blank", "por3", _por3_lb),
    Case("por3_level_blank_scales", "por3", lambda d: [*_por3_lb(d), *_scales(d)]),
    Case("ref_new", "ref_new", _ref_new),
    Case("ref_new_level_blank", "ref_new",
         lambda d: [*_ref_new(d), "--level", d / "level.csv", "--blank", d / "blank",
                    "--blank-map", d / "blank_map.csv"]),
    Case("truth", "truth", _truth),
    Case("truth_scales", "truth", lambda d: [*_truth(d), *_scales(d)]),
)


def verdict_table(items_csv: Path) -> str:
    """items.csv 의 VERDICT_COLS 를 글자 그대로 (숫자로 읽지 않음) CSV 문자열로. 행 순서는 items.csv 그대로."""
    with open(items_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(VERDICT_COLS)
    w.writerows([row.get(c, "") for c in VERDICT_COLS] for row in rows)
    return buf.getvalue()


def build_data(root: Path, names=None) -> dict[str, Path]:
    """root 아래에 DATASETS 를 만든다 (names 만, 기본 전부). 이름 → 데이터 폴더."""
    out = {}
    for name in names or DATASETS:
        DATASETS[name](root / name)
        out[name] = root / name
    return out


def run_case(case: Case, data: Path, out: Path) -> str:
    _run([ROOT / "por_doe_compare.py", *case.args(data), "--out", out])
    return verdict_table(out / "items.csv")


def golden_path(case: Case) -> Path:
    return GOLDEN_DIR / f"{case.name}.csv"
