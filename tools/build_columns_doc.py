#!/usr/bin/env python3
"""열 사전 쪽(docs/sop/columns.html)을 docs/columns/*.csv 에서 만든다.

머리글과 왼쪽 목차는 docs/sop/index.html 에서 가져온다. 그래서 목차를 바꾸면 이 쪽도 다시 만들어야 한다
(tests/test_columns_page.py 가 커밋된 쪽과 새로 만든 쪽이 같은지 본다).

usage: python tools/build_columns_doc.py          docs/sop/columns.html 을 다시 쓴다
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import columns_doc  # noqa: E402
from columns_doc import OUTPUTS, ColumnDoc, Output  # noqa: E402

SOP_DIR = ROOT / "docs" / "sop"
PAGE = SOP_DIR / "columns.html"
PAGE_NAME = PAGE.name
TITLE = "열 사전"
RAW_DOC = "item_raw"
# 수식에 나오는 원데이터 입력 파일의 열 (DCNORMAL 의 DATA, --level 파일, --blank-map 파일). raw.csv 열과 함께 '원데이터'
RAW_FILE_COLUMNS = ("DATA", "CALCVAL", "LEVEL", "BLANK_ITEM")

# 결과 파일 종류마다 한 줄 설명
PURPOSE = {
    "items.csv": "ITEM마다 판정, 판정 근거 숫자, 데이터 상태를 한 행에 적는다. 모든 결과의 출발점이다.",
    "outlier_dies.csv": "튀는 die(items.csv `n_outlier_die`에 센 die)마다 한 행. die 위치와 회차별 값을 적는다.",
    "scales_auto.csv": "척도가 auto인 그룹마다 log와 linear 중 무엇을 골랐는지 적는다. --scales를 줄 때만 생긴다.",
    "item_map.csv": "익명 번호와 실제 ITEM 이름의 대응표. 공유하지 않는다.",
    "fail_evidence.csv": "items.csv 모든 행을 옮기고, 기본 판정이 차이·미결인 ITEM은 근거 숫자를 Δ 단위와 % 단위로 "
                         "다시 적는다.",
    "items_index.csv": "ITEM별 근거 폴더 목록. 최종 판정 차이·미결 ITEM, 지정한 ITEM, log 진단 대상 ITEM마다 한 행이다 "
                       "(dcc item은 지정한 ITEM만).",
    "items/*/summary.csv": "ITEM 하나의 items.csv 행 전체. --compare를 주면 compare.csv의 같은 ITEM 열이 cmp_ 접두사로 "
                           "붙는다.",
    "items/*/raw.csv": "ITEM 하나의 die별 원데이터. 원데이터 인자(--por, --doe)를 줄 때만 생긴다. 다른 파일 수식의 "
                       "die별 열(`POR{k}`, `DOE`, `d`)은 이 파일의 열이다.",
    "compare.csv": "기존 결과(--before)와 이번 결과를 ITEM 이름으로 맞춰 흔들림과 판정을 견준다.",
    "stability_overall.csv": "compare.csv에서 짝이 있는 ITEM 전체의 흔들림 분포를 한 행으로 요약한다.",
    "worst_items.csv": "비율 지표(반복성, 회차 이동, 측정 정밀도)마다 가장 나빠진 ITEM을 적는다.",
    "group_summary.csv": "compare.csv를 ITEM 그룹별로 요약한다. 맨 위는 전체 행이다.",
    "verdict_by_group.csv": "그룹마다 판정 변화(기존→개선)별 ITEM 수를 센다.",
    "stability_by_group.csv": "그룹마다 기존·개선 흔들림 분포와 안정 순위를 적는다.",
    "group_dirs.csv": "그룹 이름과 그룹 그림 폴더 이름의 대응표.",
    "item_evidence": "ITEM 하나의 판정 근거를 원데이터에서 다시 적는다. 신뢰구간을 정한 die와 그 값, 허용폭의 구성, 올라간·내려간 die 수, 튀는 die. ITEM 폴더마다 한 행이다.",
    "stability/overall.csv": "측정 안정도 전체 요약 한 행. 판정력 구간별 ITEM 비율, 정밀도와 판정력의 중앙값·상위 10%, 상태별·잡음 모양별 ITEM 수.",
    "stability/groups.csv": "측정 안정도를 그룹마다 한 행으로 요약한다. --groups를 줄 때만 생긴다.",
    "stability/group_levels.csv": "그룹 × LEVEL(측정 자릿수)마다 판정력 비율과 측정 정밀도. 같은 그룹에서 낮은 LEVEL만 불안정한지 본다. --level을 줄 때만 생긴다.",
    "stability/dies.csv": "die 위치마다 POR 반복 흔들림 점수. 여러 ITEM에서 함께 크게 흔들리는 die를 찾는다.",
    "stability/runs.csv": "POR 회차마다 다른 회차 대비 밀린 정도. 회차 하나가 통째로 밀렸는지 본다.",
    "loq_review.csv": "LoQ 아래·LoQ 근처 ITEM을 LoQ 규칙과 무관한 근거(방향 일관성, 배수, 검출률, 꼬리)로 다시 보고 '확인 필요'를 표시한다. 판정은 바꾸지 않는다.",
    "log_review.csv": "log로 판정했거나 log 대상인 ITEM을 선형과 log로 나란히 보고, 선형 차이가 log로 동등이 된 ITEM과 꼬리가 바뀐 ITEM에 '확인 필요'를 표시한다. 판정은 바꾸지 않는다.",
}

# 열 설명 문서마다 수식이 읽는 다른 문서 (그 파일이 입력으로 읽는 결과 파일). 원데이터는 모든 문서가 읽는다.
INPUTS = {
    "items": (), "outlier_dies": (), "item_raw": (),
    "scales_auto": ("items",), "item_map": ("items",), "fail_evidence": ("items",), "items_index": ("items",),
    "compare": ("items",),
    "stability_overall": ("compare",), "worst_items": ("compare",), "group_summary": ("compare",),
    "verdict_by_group": ("compare",), "stability_by_group": ("compare",), "group_dirs": ("group_summary",),
    "loq_review": ("items",), "log_review": ("items",), "measure_stability_overall": ("items",), "measure_stability_groups": ("items",),
    "measure_stability_dies": ("items",), "measure_stability_runs": ("items",), "item_evidence": ("items",),
    "measure_stability_group_levels": ("items",),
}

HOW_TO_READ = (
    "`열 이름`처럼 표시한 글자는 결과 파일의 열이다. 같은 파일에 없으면 그 파일이 읽는 파일의 열이다 (파일마다 적음).",
    "`POR{k}`의 {k}는 회차 번호다 (POR1, POR2, …). `{verdict}→{verdict}`의 {verdict}는 판정 이름이다.",
    "die별은 die마다 따로 계산한다는 뜻이다. median은 중앙값, mean은 평균, |x|는 절댓값이다.",
    "r은 허용 비율(--r, 기본 0.05), J는 POR 회차 수, n은 die 수다.",
    "계산할 수 없으면 빈 칸이다 (0으로 나누기, 값 부족 등).",
)


def anchor(kind: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", kind.lower()).strip("-")


def inline(text: str) -> str:
    """HTML 로 옮기고 `이름` 은 <code> 로."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text, quote=False))


def shell(index_html: str) -> str:
    """index.html 의 머리글·목차를 이 쪽 것으로 (제목, 지금 쪽 표시)."""
    head = index_html[:index_html.index('<main><div class="wrap">') + len('<main><div class="wrap">')]
    head = re.sub(r"<title>[^<]*</title>", f"<title>{TITLE} · DC Test 동일성 검증</title>", head, count=1)
    head = head.replace(' aria-current="page"', "")
    link = f'<a href="{PAGE_NAME}">'
    if link not in head:
        raise SystemExit(f"index.html 왼쪽 목차에 {link} 가 없습니다")
    return head.replace(link, f'<a href="{PAGE_NAME}" aria-current="page">', 1)


def where(o: Output) -> str:
    """두 명령이 쓰는 폴더 (dcc 는 <조합>/, run_all 은 --out/)."""
    return " · ".join(f"<code>{html.escape(g)}</code>" for g in o.globs)


def column_table(docs: tuple[ColumnDoc, ...]) -> str:
    rows = "\n".join(
        f"<tr><td><code>{html.escape(d.column)}</code></td><td>{inline(d.easy_name)}</td><td>{inline(d.meaning)}</td>"
        f"<td>{inline(d.formula)}</td><td>{inline(d.look_for)}</td></tr>" for d in docs)
    return ('<div class="tw"><table><thead><tr><th>열</th><th>쉬운 이름</th><th>뜻</th><th>수식</th><th>볼 것</th>'
            f"</tr></thead><tbody>\n{rows}\n</tbody></table></div>")


def doc_kind(doc: str) -> str:
    """문서 이름 → 그 문서를 처음 쓰는 결과 파일 종류."""
    return next(o.kind for o in OUTPUTS if o.doc == doc)


def section(o: Output, docs: dict[str, tuple[ColumnDoc, ...]]) -> str:
    first = doc_kind(o.doc)
    meta = [f"만드는 명령 {html.escape(o.made_by)}", f"위치 {where(o)}"]
    inputs = INPUTS[o.doc]
    if inputs:
        meta.append("수식의 다른 열 " + ", ".join(
            f'<a href="#{anchor(doc_kind(d))}">{html.escape(doc_kind(d))}</a>' for d in inputs) + " 열")
    if first != o.kind:
        body = f'<p>열 설명은 <a href="#{anchor(first)}">{html.escape(first)}</a>와 같다.</p>'
    else:
        body = f"<p class=\"s\">열 {len(docs[o.doc])}개</p>\n{column_table(docs[o.doc])}"
    return (f'<section id="{anchor(o.kind)}"><h2>{html.escape(o.kind)}</h2>\n<p>{inline(PURPOSE[o.kind])}</p>\n'
            f'<p class="s">{" · ".join(meta)}</p>\n{body}\n</section>')


def render() -> str:
    docs = columns_doc.load()
    files = "\n".join(
        f'<tr><td><a href="#{anchor(o.kind)}"><code>{html.escape(o.kind)}</code></a></td>'
        f"<td>{html.escape(o.made_by)}</td><td>{inline(PURPOSE[o.kind])}</td></tr>" for o in OUTPUTS)
    how = "\n".join(f"<li>{inline(t)}</li>" for t in HOW_TO_READ)
    main = f"""
<p class="loc"><a href="index.html">개요</a> › {TITLE} · 관련 <a href="reading.html">결과 읽는 법</a></p>
<h1>결과 파일 {TITLE}</h1>

<section id="q"><h2>이 쪽이 답하는 질문</h2>
<p class="q">결과 CSV의 열마다 무슨 뜻이고, 어떻게 계산하고, 무엇을 보면 되나</p>
<p class="s">이 쪽은 docs/columns/*.csv에서 tools/build_columns_doc.py로 만든다. 고칠 때는 CSV를 고치고 다시 만든다.</p>
</section>

<section id="how"><h2>수식 읽는 법</h2>
<ul>
{how}
</ul>
</section>

<section id="files"><h2>결과 파일</h2>
<div class="tw"><table><thead><tr><th>파일</th><th>만드는 명령</th><th>무엇</th></tr></thead><tbody>
{files}
</tbody></table></div>
</section>

{chr(10).join(section(o, docs) for o in OUTPUTS)}

<footer class="pager"><a href="reading.html">← 이전 · 결과 읽는 법</a><a href="concepts.html">다음 · 개념 익히기 →</a></footer>
</div></main></body></html>
"""
    return shell((SOP_DIR / "index.html").read_text(encoding="utf-8")) + main


def main() -> int:
    PAGE.write_text(render(), encoding="utf-8")
    print(f"{PAGE.relative_to(ROOT)}: 결과 파일 {len(OUTPUTS)}종, 열 {sum(len(v) for v in columns_doc.load().values())}행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
