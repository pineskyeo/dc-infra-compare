"""판정 불변 검사: 합성 데이터 여러 벌의 판정 열이 tests/data/golden 과 글자 하나까지 같다.

판정을 바꾸지 않는 작업은 정답 파일을 건드리지 않고 이 테스트를 통과해야 한다.
판정을 일부러 바꿀 때만 python tools/update_golden.py 로 정답을 다시 쓴다.
"""
import difflib
from pathlib import Path

import pytest

from golden_cases import CASES, build_data, golden_path, run_case


@pytest.fixture(scope="module")
def datasets(tmp_path_factory) -> dict[str, Path]:
    return build_data(tmp_path_factory.mktemp("golden"))


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_verdict_columns_match_golden(case, datasets, tmp_path: Path):
    expected = golden_path(case).read_text(encoding="utf-8")
    actual = run_case(case, datasets[case.data], tmp_path / "out")
    diff = "\n".join(difflib.unified_diff(expected.splitlines(), actual.splitlines(), "golden", "now",
                                          lineterm="", n=0))
    assert actual == expected, f"{case.name}: 판정 열이 바뀜\n{diff}"


def test_cases_cover_every_verdict_and_basis():
    text = "".join(golden_path(c).read_text(encoding="utf-8") for c in CASES)
    for value in ("동등", "차이", "미결", "판정 제외", "검출한계 이하", "검출~정량", "die 부족",
                  "log", "accuracy", "log_physics", "auto→log", "auto→linear"):
        assert f",{value}," in text, value
