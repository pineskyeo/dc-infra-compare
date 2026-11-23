#!/usr/bin/env python3
"""판정 불변 검사의 정답 파일(tests/data/golden/*.csv)을 지금 코드로 다시 쓴다. 바뀐 행을 출력한다.

판정을 일부러 바꿀 때만 쓴다. 판정을 바꾸지 않는 작업은 이 파일들을 건드리지 않고
tests/test_verdicts_golden.py 를 통과해야 한다.

usage: python tools/update_golden.py [묶음 이름 ...]   (기본: 전부)
"""
from __future__ import annotations

import difflib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from golden_cases import CASES, GOLDEN_DIR, build_data, golden_path, run_case  # noqa: E402


def main(argv: list[str]) -> int:
    names = set(argv)
    unknown = names - {c.name for c in CASES}
    if unknown:
        print(f"모르는 묶음: {', '.join(sorted(unknown))} (있는 묶음: {', '.join(c.name for c in CASES)})",
              file=sys.stderr)
        return 2
    cases = [c for c in CASES if not names or c.name in names]
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        data = build_data(Path(tmp) / "data", {c.data for c in cases})
        for case in cases:
            new = run_case(case, data[case.data], Path(tmp) / "out" / case.name)
            path = golden_path(case)
            old = path.read_text(encoding="utf-8") if path.is_file() else ""
            if old == new:
                print(f"{case.name}: 그대로")
                continue
            path.write_text(new, encoding="utf-8", newline="\n")
            diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "이전", "지금", lineterm="", n=0))
            print(f"{case.name}: 바뀜 ({path.relative_to(ROOT)})")
            print("\n".join(diff[2:]) if old else f"  새 파일, {new.count(chr(10)) - 1}행")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
