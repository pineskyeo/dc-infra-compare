"""이름 붙인 POR/DOE 조합(combos.ini)으로 판정·ITEM 근거·그룹 요약을 한 명령으로 실행한다.

  python dcc.py list                              조합 이름, POR 회차 수, DOE, 출력 폴더
  python dcc.py judge A1                          판정(por_doe_compare) + 판정 요약 그림
  python dcc.py judge all                         파일 순서대로 모든 조합 (하나가 실패해도 계속)
  python dcc.py judge A1 --detail                 판정 뒤 차이·미결 ITEM 전부 item 분석까지
  python dcc.py item A1 VT_SAME,VT_SHIFT [--plots]  그 ITEM 만 Fail 근거 (+ 상세 그림)
  python dcc.py item A1 --items-file 볼항목.txt    ITEM 목록 파일 (한 줄에 하나, 또는 ITEM·ID 열 CSV)
  python dcc.py group A1 [--before 이전/items.csv]  그룹별 요약 그림 (+ 기존·개선 비교, 그룹 요약)

설정 파일은 기본으로 현재 폴더의 combos.ini (--config 로 바꿈). 형식은 combos.example.ini.
조합 하나의 산출물은 <out>/<이름>/ 에 둔다: items.csv, plots/, item/, group/.
item, group 은 <out>/<이름>/items.csv 를 다시 쓰고, 없을 때만 judge 단계를 먼저 실행한다.
"""
from __future__ import annotations

import argparse
import configparser
import csv
import io
import sys
from dataclasses import dataclass
from pathlib import Path

from step_runner import run_step

KEYS = {"por", "doe", "level", "blank", "blank_map", "key", "encoding", "r", "groups", "scales", "before", "out"}
DEFAULT_OUT = "dcc_out"
ALL = "all"
DETAIL_VERDICTS = ("차이", "미결")

Step = tuple[str, list[str]]


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Combo:
    """설정 파일의 조합 하나. 경로는 모두 절대 경로, out 은 <out>/<이름>."""
    name: str
    por: tuple[Path, ...]
    doe: Path
    out: Path
    level: Path | None = None
    blank: tuple[Path, ...] = ()
    blank_map: Path | None = None
    key: str | None = None
    encoding: str | None = None
    r: float | None = None
    groups: Path | None = None
    scales: Path | None = None
    before: Path | None = None

    @property
    def items_csv(self) -> Path:
        return self.out / "items.csv"

    def inputs(self) -> list[Path]:
        single = [self.doe, self.level, self.blank_map, self.groups, self.scales, self.before]
        return [*self.por, *self.blank, *(p for p in single if p is not None)]

    def raw_args(self) -> list[str]:
        """por_doe_compare.add_common_args 인자 (fail_evidence, plot_verdicts 도 같은 인자를 받는다)."""
        args: list[str] = []
        for run in self.por:
            args += ["--por", str(run)]
        args += ["--doe", str(self.doe)]
        if self.r is not None:
            args += ["--r", repr(self.r)]
        if self.level is not None:
            args += ["--level", str(self.level)]
        if self.blank:
            args += ["--blank", *map(str, self.blank)]
        if self.blank_map is not None:
            args += ["--blank-map", str(self.blank_map)]
        if self.key is not None:
            args += ["--key", self.key]
        if self.encoding is not None:
            args += ["--encoding", self.encoding]
        return args


def _lines(value: str) -> list[str]:
    return [s.strip() for s in value.splitlines() if s.strip()]


def _parse_combo(name: str, raw: dict[str, str], base: Path) -> Combo:
    def path(value: str) -> Path:
        return (base / Path(value.strip()).expanduser()).resolve()

    def opt_path(k: str) -> Path | None:
        return path(raw[k]) if raw.get(k, "").strip() else None

    def opt_str(k: str) -> str | None:
        return raw[k].strip() or None if k in raw else None

    por = _lines(raw.get("por", ""))
    if len(por) < 2:
        raise ConfigError(f"[{name}] POR 은 2회 이상 필요합니다 (por 에 한 줄에 하나씩, 지금 {len(por)}개)")
    if not raw.get("doe", "").strip():
        raise ConfigError(f"[{name}] doe 가 없습니다")
    r = None
    if opt_str("r") is not None:
        try:
            r = float(raw["r"])
        except ValueError:
            raise ConfigError(f"[{name}] r 은 숫자여야 합니다: {raw['r'].strip()!r}") from None
    return Combo(
        name=name,
        por=tuple(map(path, por)),
        doe=path(raw["doe"]),
        out=path(raw.get("out") or DEFAULT_OUT) / name,
        level=opt_path("level"),
        blank=tuple(map(path, _lines(raw.get("blank", "")))),
        blank_map=opt_path("blank_map"),
        key=opt_str("key"),
        encoding=opt_str("encoding"),
        r=r,
        groups=opt_path("groups"),
        scales=opt_path("scales"),
        before=opt_path("before"),
    )


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949")


def load_config(path: Path) -> dict[str, Combo]:
    """설정 파일을 조합 이름 → Combo 로 읽는다 (파일 순서). 상대 경로는 설정 파일 폴더 기준."""
    if not path.is_file():
        raise ConfigError(f"설정 파일이 없습니다: {path} (combos.example.ini 를 복사해 만드세요)")
    cp = configparser.ConfigParser(interpolation=None, default_section="\0")
    try:
        cp.read_string(_read_text(path), source=str(path))
    except (configparser.Error, UnicodeDecodeError) as e:
        raise ConfigError(f"설정 파일 형식 오류 ({path}): {e}") from None
    sections = {name: dict(cp[name]) for name in cp.sections()}
    defaults = sections.pop("defaults", {})
    for name, raw in [("defaults", defaults), *sections.items()]:
        unknown = sorted(set(raw) - KEYS)
        if unknown:
            raise ConfigError(f"[{name}] 모르는 키: {', '.join(unknown)} (쓸 수 있는 키: {', '.join(sorted(KEYS))})")
    if ALL in sections:
        raise ConfigError(f"조합 이름 '{ALL}' 은 쓸 수 없습니다 (judge all 과 겹침)")
    base = path.resolve().parent
    return {name: _parse_combo(name, {**defaults, **raw}, base) for name, raw in sections.items()}


def _unique(names) -> list[str]:
    return list(dict.fromkeys(n for n in (s.strip() for s in names) if n))


def _split_commas(values: list[str]) -> list[str]:
    return [s for v in values for s in v.split(",")]


def _table_column(header: list[str]) -> int | None:
    """ITEM 목록 표의 ITEM 열, 없으면 ID 열 위치."""
    names = [h.strip().strip('"').upper() for h in header]
    return next((names.index(want) for want in ("ITEM", "ID") if want in names), None)


def read_items_file(path: Path) -> list[str]:
    """ITEM 목록 파일: ITEM·ID 열이 있는 CSV/TSV, 아니면 한 줄에 하나(쉼표도 구분, # 뒤는 주석)."""
    if not path.is_file():
        raise ConfigError(f"ITEM 목록 파일이 없습니다: {path}")
    try:
        text = _read_text(path)
    except UnicodeDecodeError:
        raise ConfigError(f"ITEM 목록 파일을 읽을 수 없습니다 (UTF-8, CP949 아님): {path}") from None
    first = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = "\t" if "\t" in first else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    col = _table_column(rows[0]) if rows else None
    if col is not None:
        return _unique(r[col] for r in rows[1:] if col < len(r))
    return _unique(_split_commas([line.split("#", 1)[0] for line in text.splitlines()]))


def wanted_items(positional: list[str], items_file: str | None) -> list[str]:
    """명령행 ITEM 과 목록 파일을 합친다 (중복 제거, 처음 순서)."""
    from_file = read_items_file(Path(items_file)) if items_file else []
    items = _unique([*_split_commas(positional), *from_file])
    if not items:
        raise ConfigError("ITEM 을 주세요 (명령행 ITEM_A,ITEM_B 나 --items-file 목록 파일)")
    return items


def detail_items(items_csv: Path) -> list[str]:
    """items.csv 에서 verdict_final 이 차이·미결인 ITEM (판정 제외·동등은 빼고, 파일 순서)."""
    with open(items_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    key = "ITEM" if rows and "ITEM" in rows[0] else "ID"
    return _unique(r[key] for r in rows if (r.get("verdict_final") or "").strip() in DETAIL_VERDICTS)


def check_inputs(combo: Combo) -> None:
    missing = [p for p in combo.inputs() if not p.exists()]
    if missing:
        raise ConfigError(f"[{combo.name}] 없는 경로:\n" + "\n".join(f"  {p}" for p in missing))


def judge_steps(c: Combo, a: argparse.Namespace) -> list[Step]:
    scales: list[str] = []
    if c.scales is not None:
        if c.groups is None:
            raise ConfigError(f"[{c.name}] scales 에는 groups 가 필요합니다 (조합이나 [defaults] 에 groups = ITEM,그룹 파일)")
        scales = ["--groups", str(c.groups), "--scales", str(c.scales)]
    return [
        ("por_doe_compare", ["por_doe_compare.py", *c.raw_args(), *scales, "--out", str(c.out)]),
        ("plot_verdicts", ["plot_verdicts.py", "--items-csv", str(c.items_csv), "--summary",
                           "--out", str(c.out / "plots")]),
    ]


def item_steps(c: Combo, a: argparse.Namespace) -> list[Step]:
    return evidence_steps(c, wanted_items(a.items, a.items_file), a.plots)


def evidence_steps(c: Combo, names: list[str], plots: bool) -> list[Step]:
    out = c.out / "item"
    items = ",".join(names)
    steps = [("fail_evidence", ["fail_evidence.py", "--input", str(c.items_csv), "--out", str(out),
                                "--only", items, *c.raw_args()])]
    if plots:
        steps.append(("plot_verdicts", ["plot_verdicts.py", "--items-csv", str(c.items_csv), "--no-summary",
                                        "--detail", "--items", items, "--out", str(out / "plots"), *c.raw_args()]))
    return steps


def group_steps(c: Combo, a: argparse.Namespace) -> list[Step]:
    if c.groups is None:
        raise ConfigError(f"[{c.name}] groups 파일이 없습니다 (조합이나 [defaults] 에 groups = ITEM,그룹 파일)")
    out = c.out / "group"
    before = Path(a.before).resolve() if a.before else c.before
    steps = [("plot_verdicts", ["plot_verdicts.py", "--items-csv", str(c.items_csv), "--summary",
                                "--groups", str(c.groups), "--out", str(out / "plots")])]
    if before is not None:
        if not before.is_file():
            raise ConfigError(f"[{c.name}] --before 파일이 없습니다: {before}")
        steps += [
            ("compare_before_after", ["compare_before_after.py", "compare", str(before), str(c.items_csv),
                                      "-o", str(out / "compare")]),
            ("group_summary", ["group_summary.py", "--compare", str(out / "compare" / "compare.csv"),
                               "--groups", str(c.groups), "--out", str(out / "summary")]),
        ]
    return steps


MODES = {"judge": judge_steps, "item": item_steps, "group": group_steps}


def plan(mode: str, c: Combo, a: argparse.Namespace) -> list[Step]:
    """모드의 단계 목록. item·group 은 items.csv 가 없으면 judge 단계를 앞에 붙인다."""
    steps = MODES[mode](c, a)
    if mode != "judge" and not c.items_csv.is_file():
        steps = judge_steps(c, a) + steps
    return steps


def run_combo(c: Combo, mode: str, steps: list[Step]) -> tuple[str, int] | None:
    """단계를 차례로 실행한다. 실패하면 (단계 이름, rc), 다 성공하면 None."""
    print(f"== {c.name} {mode} → {c.out}", flush=True)
    for n, (name, script_args) in enumerate(steps, 1):
        proc = run_step(n, len(steps), name, script_args, show_cmd=True)
        if proc.returncode != 0:
            return name, proc.returncode
        if proc.stdout:
            print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
    return None


def run_target(c: Combo, a: argparse.Namespace, steps: list[Step]) -> tuple[str, int] | None:
    """조합 하나 실행. judge --detail 이면 판정이 성공한 뒤 차이·미결 ITEM 을 item 분석한다."""
    failed = run_combo(c, a.cmd, steps)
    if failed is not None or not getattr(a, "detail", False):
        return failed
    names = detail_items(c.items_csv)
    if not names:
        print(f"[{c.name}] 차이·미결 ITEM 이 없어 item 분석을 건너뜁니다", flush=True)
        return None
    print(f"[{c.name}] 차이·미결 ITEM {len(names)}개 item 분석", flush=True)
    return run_combo(c, "item", evidence_steps(c, names, plots=False))


def print_list(combos: dict[str, Combo]) -> None:
    if not combos:
        print("조합이 없습니다")
        return
    width = max(len("이름"), *(len(n) for n in combos))
    print(f"{'이름'.ljust(width)}  POR  DOE  →  출력")
    for c in combos.values():
        print(f"{c.name.ljust(width)}  {len(c.por):>3}  {c.doe}  →  {c.out}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="combos.ini", help="조합 설정 파일 (기본: 현재 폴더의 combos.ini)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", parents=[common], help="조합 목록")
    p = sub.add_parser("judge", parents=[common], help="판정 + 판정 요약 그림")
    p.add_argument("name", help=f"조합 이름, 또는 {ALL} (모든 조합)")
    p.add_argument("--detail", action="store_true",
                   help="판정 뒤 verdict_final 이 차이·미결인 ITEM 을 모두 item 분석 (<out>/<이름>/item/)")
    p = sub.add_parser("item", parents=[common], help="고른 ITEM 만 Fail 근거 (<out>/<이름>/item/)")
    p.add_argument("name", help="조합 이름")
    p.add_argument("items", nargs="*", metavar="ITEM_A,ITEM_B", help="ITEM 이름이나 익명 ID (쉼표나 공백 구분)")
    p.add_argument("--items-file", metavar="FILE",
                   help="ITEM 목록 파일. 한 줄에 하나(# 뒤는 주석), 또는 ITEM·ID 열이 있는 CSV/TSV. 명령행 ITEM 과 합침")
    p.add_argument("--plots", action="store_true",
                   help="ITEM 상세 그림도 그림 (item/plots/). 원데이터 전체를 읽으므로 느림")
    p = sub.add_parser("group", parents=[common], help="그룹별 요약 (<out>/<이름>/group/)")
    p.add_argument("name", help="조합 이름")
    p.add_argument("--before", help="기존(이전) 결과 items.csv. 주면 기존·개선 비교와 그룹 요약 추가 "
                                    "(조합의 before 키보다 우선)")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    run_all_combos = a.cmd == "judge" and a.name == ALL
    try:
        combos = load_config(Path(a.config))
        if a.cmd == "list":
            print_list(combos)
            return 0
        if run_all_combos:
            targets = list(combos.values())
            if not targets:
                raise ConfigError(f"{a.config} 에 조합이 없습니다")
        elif a.name in combos:
            targets = [combos[a.name]]
        else:
            raise ConfigError(f"모르는 조합 이름: {a.name} (있는 이름: {', '.join(combos) or '없음'})")
        plans = []
        for c in targets:
            check_inputs(c)
            plans.append((c, plan(a.cmd, c, a)))
    except ConfigError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    results = [(c.name, run_target(c, a, steps)) for c, steps in plans]
    if run_all_combos:
        print("\n결과")
        for name, failed in results:
            print(f"{name}  " + ("성공" if failed is None else f"실패 (단계 {failed[0]}, rc={failed[1]})"))
    failures = [f for _, f in results if f is not None]
    if not failures:
        return 0
    return 1 if run_all_combos else failures[0][1]


if __name__ == "__main__":
    sys.exit(main())
