"""POR/DOE 판정부터 요약·LoQ·log 재확인·근거·그림(선택: 기존·개선 비교, 그룹 요약)까지 한 번에 실행한다.

  python run_all.py --por POR1/ --por POR2/ --por POR3/ --doe DOE/ --level item_info.csv --out 결과
  python run_all.py ... --groups groups.csv        (그룹별 판정 지도)
  python run_all.py ... --before 이전결과/items.csv --groups groups.csv   (+ 그룹별 비교 요약)

각 단계는 repo 안 스크립트를 별도 프로세스로 실행하고, 실패하면 그 단계에서 멈춘다.
RUN_ALL_FAIL_STEP=<단계 이름> 환경변수는 테스트용이다(그 단계를 rc=3으로 강제 실패시킴).
"""
import argparse
import fnmatch
import os
import sys
from pathlib import Path

from fail_evidence import add_raw_args
from por_doe_compare import add_common_args
from step_runner import run_step

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
    ("fail_evidence/items_index.csv", "ITEM별 근거 폴더 목록"),
    ("fail_evidence/items/.fail_evidence_items", "fail_evidence 가 만든 items/ 라는 표식 (다시 실행할 때 지울 폴더)"),
    ("fail_evidence/items/*/summary.csv", "ITEM 하나의 판정 열 전체"),
    ("fail_evidence/items/*/raw.csv", "ITEM 하나의 die별 원데이터"),
    ("fail_evidence/items/*/evidence.csv", "ITEM 하나의 판정 근거 (신뢰구간을 정한 die, 허용폭 구성)"),
    ("fail_evidence/items/*/item_view.png", "ITEM 한 장 보기 (판정 카드, 짝 그림, 차이 막대, 맵)"),
    ("fail_evidence/items/*/*.png", "ITEM 하나의 근거 그림"),
    ("plots/summary.png", "판정 지도"),
    ("plots/summary_loq.png", "LoQ 아래 ITEM 그림 (LoQ 재확인 표시)"),
    ("plots/summary_group_*.png", "그룹 하나의 판정 지도"),
    ("plots/*.png", "판정 요약 그림"),
    ("stability/overall.csv", "측정 안정도 전체 요약"),
    ("stability/groups.csv", "측정 안정도 그룹별 요약"),
    ("stability/group_levels.csv", "측정 안정도 그룹 × LEVEL 요약"),
    ("stability/dies.csv", "die 위치별 흔들림 점수"),
    ("stability/runs.csv", "POR 회차별 밀림 점수"),
    ("stability/stability.png", "측정 안정도 그림"),
    ("stability/group_levels.png", "그룹 × LEVEL 판정력과 측정 정밀도 그림"),
    ("review/loq_review.csv", "LoQ 재확인 (참고용, 판정은 그대로)"),
    ("review/log_review.csv", "log 재확인 (참고용, 판정은 그대로)"),
    ("review/loq_review.png", "LoQ 재확인 그림"),
    ("review/log_review.png", "log 재확인 그림 (선형과 log 나란히)"),
    ("review/items/*.png", "재확인 '확인 필요' ITEM 그림"),
    # compare/ (--before): compare_before_after.py compare
    ("compare/compare.csv", "ITEM별 기존·개선 비교"),
    ("compare/summary.txt", "기존·개선 비교 요약"),
    ("compare/stability_overall.csv", "전체 안정성 (group_summary '전체' 행과 같은 값)"),
    ("compare/worst_items.csv", "비율 지표별 악화 상위 ITEM"),
    ("compare/*.png", "기존·개선 지표 그림"),
    ("compare/*", "기존·개선 비교"),
    # groups/ (--before + --groups): group_summary.py
    ("groups/group_summary.csv", "그룹별 요약 (맨 위 '전체' 행)"),
    ("groups/verdict_by_group.csv", "그룹별 판정 변화"),
    ("groups/stability_by_group.csv", "그룹별 안정성"),
    ("groups/group_dirs.csv", "그룹 이름 → 폴더 이름"),
    ("groups/*/*.png", "그룹 하나의 지표 그림"),
    ("groups/*.png", "그룹 비교 지표 그림"),
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
    ap.add_argument("--groups", help="ITEM,그룹 파일. 주면 그룹별 판정 지도(plots/summary_group_*.png)를 그리고, "
                                     "--before도 주면 그룹별 비교 요약 단계(groups/) 추가")
    ap.add_argument("--plot-top", type=int, default=None,
                    help="비율 지표 그림의 악화 상위 표 ITEM 수 (compare 기본 10)")
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


def raw_forward_args(args: list[str]) -> list[str]:
    """compare_forward_args 결과에서 fail_evidence 의 add_raw_args 가 받는 옵션(과 그 값)만 남긴다."""
    probe = argparse.ArgumentParser(add_help=False)
    add_raw_args(probe)
    accepted = {s for act in probe._actions for s in act.option_strings}
    kept: list[str] = []
    keep = False
    for tok in args:
        if tok.startswith("--"):
            keep = tok in accepted
        if keep:
            kept.append(tok)
    return kept


def plan_steps(ap: argparse.ArgumentParser, a: argparse.Namespace, out: Path) -> list[tuple[str, list[str], Path | None]]:
    """(이름, 스크립트 인자, stdout 저장 파일) 목록."""
    items = str(out / "items.csv")
    plot_args = ["plot_verdicts.py", "--items-csv", items, "--summary", "--out", str(out / "plots")]
    if a.groups:
        plot_args += ["--groups", _abs(a.groups)]
    raw_args = compare_forward_args(ap, a)
    steps = [
        ("por_doe_compare", ["por_doe_compare.py", *raw_args, "--out", str(out)], None),
        ("summarize", ["summarize.py", items], out / "summary_items.txt"),
        ("review", ["review.py", "--input", items, "--out", str(out), *raw_forward_args(raw_args)], None),
        # --compare 는 안 넘긴다 (compare 단계가 이 단계보다 뒤).
        ("fail_evidence", ["fail_evidence.py", "--input", items, "--out", str(out / "fail_evidence"),
                           *raw_forward_args(raw_args)], None),
        # summary_loq.png 가 review/loq_review.csv 의 '확인 필요' 를 표시하므로 review 뒤.
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


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    steps = plan_steps(ap, a, out)
    total = len(steps)
    fail_step = os.environ.get("RUN_ALL_FAIL_STEP")
    for n, (name, script_args, stdout_file) in enumerate(steps, 1):
        proc = run_step(n, total, name, script_args, fail=name == fail_step)
        if proc.returncode != 0:
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
