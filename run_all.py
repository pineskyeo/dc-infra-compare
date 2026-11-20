"""POR/DOE 판정부터 요약·근거·그림(선택: 기존·개선 비교, 그룹 요약)까지 한 번에 실행한다.

  python run_all.py --por POR1/ --por POR2/ --por POR3/ --doe DOE/ --level item_info.csv --out 결과
  python run_all.py ... --groups groups.csv        (그룹별 대시보드 그림)
  python run_all.py ... --before 이전결과/items.csv --groups groups.csv   (+ 그룹별 비교 요약)

각 단계는 repo 안 스크립트를 별도 프로세스로 실행하고, 실패하면 그 단계에서 멈춘다.
RUN_ALL_FAIL_STEP=<단계 이름> 환경변수는 테스트용이다(그 단계를 rc=3으로 강제 실패시킴).
"""
import argparse
import fnmatch
import os
import sys
import subprocess
from pathlib import Path

from por_doe_compare import add_common_args

ROOT = Path(__file__).resolve().parent

# 앞에서부터 처음 맞는 규칙의 설명을 쓴다 (경로는 --out 기준 상대경로, '/' 구분).
DESCRIPTIONS = [
    ("items.csv", "ITEM별 판정·상태"),
    ("outlier_dies.csv", "튀는 die"),
    ("summary_items.txt", "summarize 출력"),
    ("summary.txt", "공유용 판정 요약 (ITEM 이름 없음, summarize 출력)"),
    ("item_map.csv", "익명 번호 ↔ 실제 ITEM 대응표 (공유하지 말 것)"),
    ("fail_evidence/fail_evidence.csv", "Fail 근거"),
    ("fail_evidence/summary.txt", "Fail 근거 요약"),
    ("fail_evidence/forest.png", "Fail 근거 전체 그림"),
    ("fail_evidence/items/*.png", "ITEM별 근거 그림"),
    ("plots/*.png", "판정 요약 그림"),
    ("compare/*", "기존·개선 비교"),
    ("groups/*", "그룹별 요약"),
]


def describe(rel: str) -> str:
    for pattern, desc in DESCRIPTIONS:
        if fnmatch.fnmatchcase(rel, pattern):
            return desc
    return "산출물"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--out", default="run_all_out", help="모든 산출물을 둘 폴더 (기본 run_all_out)")
    ap.add_argument("--before", help="기존(이전) 결과 items.csv. 주면 기존·개선 비교 단계 추가")
    ap.add_argument("--groups", help="ITEM,그룹 파일. 주면 그룹별 대시보드(plots/summary_group_*.png)를 그리고, "
                                     "--before도 주면 그룹별 비교 요약 단계(groups/) 추가")
    ap.add_argument("--plot-top", type=int, default=None,
                    help="비교 단계 σ 짝 그림에 변화가 큰 ITEM N개만 그린다 (compare_before_after.py 기본 30)")
    return ap


def _abs(p: str) -> str:
    return str(Path(p).resolve())


def compare_forward_args(ap: argparse.ArgumentParser, a: argparse.Namespace) -> list[str]:
    """add_common_args 옵션 중 기본값과 다른 것(사용자가 준 것)만 por_doe_compare.py 인자로 만든다."""
    args: list[str] = []
    for run in a.por:
        args += ["--por", *map(_abs, run)]
    args += ["--doe", *map(_abs, a.doe)]
    if a.r != ap.get_default("r"):
        args += ["--r", repr(a.r)]
    if a.level is not None:
        args += ["--level", _abs(a.level)]
    if a.blank:
        args += ["--blank", *map(_abs, a.blank)]
    if a.blank_map is not None:
        args += ["--blank-map", _abs(a.blank_map)]
    if a.key != ap.get_default("key"):
        args += ["--key", a.key]
    if a.encoding != ap.get_default("encoding"):
        args += ["--encoding", a.encoding]
    return args


def plan_steps(ap: argparse.ArgumentParser, a: argparse.Namespace, out: Path) -> list[tuple[str, list[str], Path | None]]:
    """(이름, 스크립트 인자, stdout 저장 파일) 목록."""
    items = str(out / "items.csv")
    plot_args = ["plot_verdicts.py", "--items-csv", items, "--summary", "--out", str(out / "plots")]
    if a.groups:
        plot_args += ["--groups", _abs(a.groups)]
    steps = [
        ("por_doe_compare", ["por_doe_compare.py", *compare_forward_args(ap, a), "--out", str(out)], None),
        ("summarize", ["summarize.py", items], out / "summary_items.txt"),
        ("fail_evidence", ["fail_evidence.py", "--input", items, "--out", str(out / "fail_evidence")], None),
        # 요약 그림은 items.csv만 쓴다 (POR/DOE 원자료는 상세 그림에서만 필요).
        ("plot_verdicts", plot_args, None),
    ]
    if a.before:
        cmp_args = ["compare_before_after.py", "compare", _abs(a.before), items, "-o", str(out / "compare")]
        if a.plot_top is not None:
            cmp_args += ["--plot-top", str(a.plot_top)]
        steps.append(("compare_before_after", cmp_args, None))
    if a.before and a.groups:
        steps.append(("group_summary",
                      ["group_summary.py", "--compare", str(out / "compare" / "compare.csv"),
                       "--groups", _abs(a.groups), "--out", str(out / "groups")], None))
    return steps


def _env() -> dict:
    env = os.environ.copy()
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + old if old else "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    steps = plan_steps(ap, a, out)
    total = len(steps)
    fail_step = os.environ.get("RUN_ALL_FAIL_STEP")
    env = _env()
    for n, (name, script_args, stdout_file) in enumerate(steps, 1):
        print(f"[단계 {n}/{total}] {name}", flush=True)
        cmd = [sys.executable, str(ROOT / script_args[0]), *script_args[1:]]
        if name == fail_step:
            cmd = [sys.executable, "-c", "import sys; sys.exit(3)"]
        proc = subprocess.run(cmd, cwd=ROOT, env=env, check=False, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            print(f"[실패] 단계 {n}/{total} {name}: {subprocess.list2cmdline(cmd)}")
            print(f"rc={proc.returncode}")
            tail = (proc.stderr or "").splitlines()[-20:]
            for line in tail:
                print(line)
            sys.stdout.flush()
            return proc.returncode or 1
        if stdout_file is not None:
            stdout_file.write_text(proc.stdout, encoding="utf-8")
            print(f"  → {stdout_file.relative_to(out).as_posix()}")
        elif proc.stdout:
            print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)

    print()
    print("생성 파일")
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    for rel in files:
        print(f"{rel}  {describe(rel)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
