"""결과 CSV 열 사전. 모든 결과 파일의 열 설명은 docs/columns/<문서>.csv 한곳에 있다.

문서 CSV 는 UTF-8 (BOM 포함, 엑셀에서 한글이 바로 열림), 열은 column,쉬운이름,뜻,수식,볼것. 엑셀에서 고쳐도 된다
(엑셀이 CP949 로 저장해도 읽는다). column 칸에는 패턴을 쓸 수 있다:
  {k}        숫자 하나 이상    POR{k}_mean → POR1_mean, POR12_mean
  {verdict}  판정 이름         {verdict}→{verdict} → 동등→미결

OUTPUTS 는 결과 파일 종류마다 출력 폴더 기준 glob 과 설명 문서를 적는다. 같은 파일이 dcc.py(item/, group/)와
run_all.py(fail_evidence/, compare/, groups/)에서 다른 폴더에 생기므로 glob 이 여러 개다.

  python columns_doc.py OUT_DIR ...          OUT_DIR 아래 결과 CSV 중 열 사전에 없는 열을 출력 (없으면 rc 0)
  python columns_doc.py --add OUT_DIR ...    없는 열을 설명 칸이 빈 행으로 문서 끝에 더함 (설명은 사람이 채움)
"""
from __future__ import annotations

import csv
import io
import re
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent / "docs" / "columns"
FIELDS = ("column", "쉬운이름", "뜻", "수식", "볼것")
VERDICTS = ("동등", "미결", "차이", "판정 제외")
PLACEHOLDERS = {"{k}": r"\d+", "{verdict}": "(?:" + "|".join(map(re.escape, VERDICTS)) + ")"}


@dataclass(frozen=True)
class ColumnDoc:
    column: str          # 열 이름이나 패턴
    easy_name: str = ""  # 쉬운이름
    meaning: str = ""    # 뜻
    formula: str = ""    # 수식
    look_for: str = ""   # 볼것

    @property
    def pattern(self) -> re.Pattern:
        parts = re.split("(" + "|".join(map(re.escape, PLACEHOLDERS)) + ")", self.column)
        return re.compile("".join(PLACEHOLDERS.get(p, re.escape(p)) for p in parts))

    def matches(self, column: str) -> bool:
        return self.pattern.fullmatch(column) is not None


@dataclass(frozen=True)
class Output:
    kind: str                # 결과 파일 종류 이름
    globs: tuple[str, ...]   # 출력 폴더 기준
    doc: str                 # docs/columns/<doc>.csv
    made_by: str


OUTPUTS: tuple[Output, ...] = (
    Output("items.csv", ("items.csv",), "items", "por_doe_compare.py (dcc judge, run_all)"),
    Output("outlier_dies.csv", ("outlier_dies.csv",), "outlier_dies", "por_doe_compare.py"),
    Output("scales_auto.csv", ("scales_auto.csv",), "scales_auto", "por_doe_compare.py --scales"),
    Output("item_map.csv", ("item_map.csv",), "item_map", "summarize.py (run_all)"),
    Output("fail_evidence.csv", ("item/fail_evidence.csv", "fail_evidence/fail_evidence.csv"), "fail_evidence",
           "fail_evidence.py (dcc item, run_all)"),
    Output("items_index.csv", ("item/items_index.csv", "fail_evidence/items_index.csv"), "items_index",
           "fail_evidence.py"),
    # ITEM 하나의 summary.csv 는 items.csv 한 행이라 설명도 items 를 같이 쓴다
    Output("items/*/summary.csv", ("item/items/*/summary.csv", "fail_evidence/items/*/summary.csv"), "items",
           "fail_evidence.py"),
    Output("items/*/raw.csv", ("item/items/*/raw.csv", "fail_evidence/items/*/raw.csv"), "item_raw",
           "fail_evidence.py (원데이터 인자를 줄 때)"),
    Output("compare.csv", ("group/compare/compare.csv", "compare/compare.csv"), "compare",
           "compare_before_after.py compare (dcc group --before, run_all --before)"),
    Output("stability_overall.csv", ("group/compare/stability_overall.csv", "compare/stability_overall.csv"),
           "stability_overall", "compare_before_after.py compare"),
    Output("worst_items.csv", ("group/compare/worst_items.csv", "compare/worst_items.csv"), "worst_items",
           "compare_before_after.py compare"),
    Output("group_summary.csv", ("group/summary/group_summary.csv", "groups/group_summary.csv"), "group_summary",
           "group_summary.py (dcc group --before, run_all --before --groups)"),
    Output("verdict_by_group.csv", ("group/summary/verdict_by_group.csv", "groups/verdict_by_group.csv"),
           "verdict_by_group", "group_summary.py"),
    Output("stability_by_group.csv", ("group/summary/stability_by_group.csv", "groups/stability_by_group.csv"),
           "stability_by_group", "group_summary.py"),
    Output("group_dirs.csv", ("group/summary/group_dirs.csv", "groups/group_dirs.csv"), "group_dirs",
           "group_summary.py"),
    Output("log_compare.csv", ("log_compare/log_compare.csv",), "log_compare", "log_compare.py (run_all)"),
)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949")


def read_doc(path: Path) -> list[ColumnDoc]:
    rows = list(csv.reader(io.StringIO(read_text(path), newline="")))
    if not rows or tuple(rows[0][:len(FIELDS)]) != FIELDS:
        raise ValueError(f"{path}: 첫 줄은 {','.join(FIELDS)} 여야 합니다 (지금 {rows[0] if rows else '빈 파일'})")
    return [ColumnDoc(*(row + [""] * len(FIELDS))[:len(FIELDS)]) for row in rows[1:] if row and row[0].strip()]


def write_doc(path: Path, docs: list[ColumnDoc]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(FIELDS)
        w.writerows((d.column, d.easy_name, d.meaning, d.formula, d.look_for) for d in docs)


@cache
def load(docs_dir: Path = DOCS_DIR) -> dict[str, tuple[ColumnDoc, ...]]:
    """문서 이름 → 열 설명. OUTPUTS 가 가리키는 문서가 없으면 빈 것으로 본다."""
    return {o.doc: tuple(read_doc(docs_dir / f"{o.doc}.csv")) if (docs_dir / f"{o.doc}.csv").is_file() else ()
            for o in OUTPUTS}


def output(kind: str) -> Output:
    for o in OUTPUTS:
        if o.kind == kind:
            return o
    raise KeyError(f"모르는 결과 파일 종류: {kind} (있는 것: {', '.join(o.kind for o in OUTPUTS)})")


def doc_for(kind: str, column: str) -> ColumnDoc | None:
    """kind 결과 파일의 column 설명. 이름이 같은 행이 패턴 행보다 먼저."""
    docs = load()[output(kind).doc]
    return next((d for d in docs if d.column == column), None) or next((d for d in docs if d.matches(column)), None)


def produced(out_dir: Path) -> dict[str, list[Path]]:
    """out_dir 아래에서 찾은 결과 파일 (종류 → 파일 목록). 하나도 없는 종류는 빠진다."""
    found = {o.kind: sorted({p for g in o.globs for p in Path(out_dir).glob(g) if p.is_file()}) for o in OUTPUTS}
    return {k: v for k, v in found.items() if v}


def header(path: Path) -> list[str]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f), [])


def undocumented(out_dir: Path) -> dict[str, list[str]]:
    """out_dir 아래 결과 CSV 열 중 열 사전에 없는 것 (종류 → 열, 처음 나온 순서). 다 있으면 {}."""
    missing: dict[str, list[str]] = {}
    for kind, paths in produced(out_dir).items():
        for path in paths:
            for col in header(path):
                if doc_for(kind, col) is None and col not in missing.get(kind, []):
                    missing.setdefault(kind, []).append(col)
    return missing


def add_missing(out_dir: Path) -> dict[str, list[str]]:
    """undocumented(out_dir) 열을 설명 칸이 빈 행으로 문서 끝에 더한다. 더한 것을 돌려준다."""
    missing = undocumented(out_dir)
    for kind, cols in missing.items():
        path = DOCS_DIR / f"{output(kind).doc}.csv"
        old = read_doc(path) if path.is_file() else []
        write_doc(path, old + [ColumnDoc(c) for c in cols if all(d.column != c for d in old)])
        load.cache_clear()
    return missing


def main(argv: list[str]) -> int:
    add = "--add" in argv
    dirs = [a for a in argv if a != "--add"]
    if not dirs:
        print(__doc__)
        return 2
    missing: dict[str, list[str]] = {}
    for out_dir in dirs:
        for kind, cols in (add_missing if add else undocumented)(Path(out_dir)).items():
            missing.setdefault(kind, []).extend(c for c in cols if c not in missing.get(kind, []))
    for kind, cols in missing.items():
        print(f"{kind} ({output(kind).doc}.csv){' 더함' if add else ''}: {', '.join(cols)}")
    return 1 if missing and not add else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
