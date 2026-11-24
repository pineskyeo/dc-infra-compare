"""SOP 쪽에 옮겨 적은 표가 코드와 같은지: ⑤ 회차 계수 표, ④ 구간 순번 표, ⑦ 원인·조치 표."""
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "docs" / "sop" / "examples")]

import journeys  # noqa: E402
import por_doe_compare as pdc  # noqa: E402
import slides  # noqa: E402

SRC = ROOT / "docs" / "sop" / "src"


def table_rows(page: str, cls: str) -> list[list[str]]:
    html = (SRC / page).read_text(encoding="utf-8")
    body = re.search(rf'<table class="{cls}">(.*?)</table>', html, re.S)[1]
    rows = [[re.sub("<[^>]+>", "", c) for c in re.findall(r"<td>(.*?)</td>", r)] for r in re.findall(r"<tr>(.*?)</tr>", body)]
    return [r for r in rows if r]


def test_run_factor_table_on_step5_matches_code():
    rows = table_rows("step-5.html", "b-num")
    assert rows
    for r in rows:
        J = int(r[0])
        want = [f"{stats.t.ppf(.95, J - 1):.4f}", f"{np.sqrt(1 + 1 / J):.4f}", f"{pdc.run_factor(J):.4f}",
                f"{5 / pdc.run_factor(J):.3f}%"]
        assert r[1:] == want, (J, r, want)


def test_interval_rank_table_on_step4_matches_code():
    rows = table_rows("step-4.html", "b-num")
    assert rows
    for r in rows:
        n = int(r[0])
        k = pdc.ci_rank(n)
        want = [f"{k + 1}번째", f"{n - k}번째", f"{(1 - 2 * stats.binom.cdf(k, n, .5)) * 100:.2f}%"]
        assert r[1:] == want, (n, r, want)


@pytest.mark.parametrize("cause", slides.CAUSES, ids=lambda c: c.name)
def test_step7_lists_every_cause_and_action_from_slides(cause):
    page = (SRC / "step-7.html").read_text(encoding="utf-8")
    assert cause.name in page and cause.action in page


def test_step7_and_its_scene_follow_the_cause_order():
    page = (SRC / "step-7.html").read_text(encoding="utf-8")
    assert journeys.DIFF_CAUSE[1] in page and journeys.NO_ACTION in page
    js = (ROOT / "docs" / "sop" / "assets" / "scenes" / "steps-b.js").read_text(encoding="utf-8").replace('"', "'")
    assert f"HOLD_CAUSES = {[c.name for c in slides.CAUSES]!r}".replace('"', "'") in js


def test_pages_copying_journey_numbers_are_rechecked_when_journeys_change():
    import hashlib
    guard = ROOT / "docs" / "sop" / "examples" / "journeys.sha256"
    lines = [ln.strip() for ln in guard.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    recorded = lines[0].split()[0]
    pages = lines[1:]
    missing = [p for p in pages if not (SRC / f"{p}.html").is_file()]
    assert not missing, f"journeys.sha256 의 쪽이 없음: {missing}"
    actual = hashlib.sha256((ROOT / "docs" / "sop" / "examples" / "journeys.json").read_bytes()).hexdigest()
    assert actual == recorded, (
        "journeys.json 이 바뀌었다. 다음 쪽 전문 영역에 옮겨 적은 예제 숫자를 새 값과 맞춘 뒤 "
        f"docs/sop/examples/journeys.sha256 의 sha256 을 {actual} 로 바꾼다: "
        + ", ".join(f"docs/sop/src/{p}.html" for p in pages))


def test_step3_gloss_explains_every_class_value():
    import classify
    js = (ROOT / "docs" / "sop" / "assets" / "scenes" / "steps-a.js").read_text(encoding="utf-8")
    block = re.search(r"const GLOSS = \{(.*?)\n  \};", js, re.S)[1]
    gloss = {k: set(re.findall(r"'([^']+)':", body)) for k, body in re.findall(r"(\w+): \{(.*?)\}", block, re.S)}
    values = {a.column.removeprefix("cls_"): set(a.known) for a in classify.AXES}
    values["noise"] |= set(pdc.NOISE_PATTERNS)
    values["scale"] |= {pdc.SCALE_LOG, pdc.SCALE_LINEAR}
    for axis, want in values.items():
        assert want <= gloss.get(axis, set()), (axis, sorted(want - gloss.get(axis, set())))
