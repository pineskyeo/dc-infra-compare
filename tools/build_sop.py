#!/usr/bin/env python3
"""SOP 쪽(docs/sop/*.html)을 본문 조각 docs/sop/src/<slug>.html 과 SITE 표에서 만든다.

쪽 목록·제목·순서는 SITE 표가 유일한 원본이다. 조각은 본문만 담고, 이 도구가 한 가지 틀(왼쪽 목차, 위쪽 막대와
'쉽게 | 전문까지' 토글, 단계 띠, 앞뒤 쪽, 스크립트)로 감싼다. 조각에서 쓰는 표시:

  <section class="easy">…</section>          쉽게 영역 (펼침)
  <section class="expert" data-title="…">    전문 영역 (접힘, 다른 색·모양, 머리표 '전문')
  <div data-scene="이름"></div>               애니메이션 자리 (assets/sop.js 의 defineScene 이름만)
  <div data-tracker="단계"></div>             예제 따라가기 카드 자리 (0~7)
  <div data-journeys="cards|list"></div>      예제 유형 카드·목록 자리
  <div data-flowchart></div>                  개요의 전체 흐름도 (SITE 제목으로 그림)
  <sup data-ref="12"></sup>                   references.md 대조표의 행 번호. 모르는 번호면 실패
  <div data-refs></div>                       각주 목록 자리 (없으면 쪽 끝에 접힌 전문 영역으로 붙임)
  <code data-code="파일.py:이름"></code>      코드 위치. 파일에 그 이름의 def·대입이 없으면 실패

쪽을 새로 쓰거나 더할 때: SITE 에 행을 두고, docs/sop/src/<slug>.html 에 본문만 쓰고,
이 도구를 돌린다. 쉽게 영역의 숫자는 assets/journeys.js 에서만 온다 (data-scene, data-tracker 로 그린다).
assets/journeys.js 가 생기면 stub 대신 그것을 싣도록 쪽이 바뀌므로 다시 돌려야 --check 가 통과한다.

usage: python tools/build_sop.py            쪽을 다시 쓰고 링크를 검사한다
       python tools/build_sop.py --check    커밋된 쪽이 새로 만든 것과 다르거나 링크가 깨졌으면 실패
"""
from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOP = ROOT / "docs" / "sop"
SRC = SOP / "src"
REFERENCES = SOP / "references.md"
SITE_NAME = "DC Test 동일성 검증"
SECTIONS = ("개요", "따라하기", "결과 읽기", "공부하기", "참고")
STEP_MARKS = "⓪①②③④⑤⑥⑦"


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    section: str
    purpose: str
    step: int | None = None

    @property
    def file(self) -> str:
        return f"{self.slug}.html"


SITE: tuple[Page, ...] = (
    Page("index", "개요", "개요", "DC Test 측정 항목(ITEM)마다 바꾼 조건(DOE)이 지금 조건(POR)과 같다고 볼 수 있는지 판정하는 절차."),
    Page("run", "실행 방법", "따라하기", "측정 파일을 모으고 도구를 돌리는 방법."),
    Page("step-0", "⓪ 표본 크기 정하기", "따라하기", "die 몇 개, POR 몇 회를 잴지 정한다.", 0),
    Page("step-1", "① 반복 측정", "따라하기", "같은 die를 POR J회, DOE 1회 잰다.", 1),
    Page("step-2", "② 흔들림 나누기", "따라하기", "측정 흔들림을 die 반복(σ_die)과 회차 이동(σ_run)으로 나눈다.", 2),
    Page("step-3", "③ LoQ와 ITEM 유형", "따라하기", "LoQ = 10σ를 구하고, POR 값만 보고 ITEM 유형과 판정 길을 정한다.", 3),
    Page("step-4", "④ 변화 구간", "따라하기", "die별 차이 d의 중앙값과 부호검정 90% 구간을 구한다.", 4),
    Page("step-5", "⑤ 허용폭 Δ", "따라하기", "이만큼 안이면 같다고 보는 폭 Δ를 정한다.", 5),
    Page("step-6", "⑥ 판정 3단계", "따라하기", "90% 구간을 허용폭과 견줘 동등 · 미결 · 차이를 정한다.", 6),
    Page("step-7", "⑦ 미결·차이일 때 다음 행동", "따라하기", "동등이 아닐 때 원인을 찾고 다음에 할 일을 정한다.", 7),
    Page("journey", "예제 따라가기", "따라하기", "ITEM 유형마다 예제 하나를 골라 ⓪부터 ⑦까지 따라간다."),
    Page("reading", "결과 읽는 법", "결과 읽기", "결과 파일에서 판정과 그 이유를 읽는다."),
    Page("columns", "열 사전", "결과 읽기", "결과 CSV의 열마다 뜻, 계산, 볼 것."),
    Page("concepts", "개념 익히기", "공부하기", "판정에 쓰는 통계 개념을 하나씩 익힌다."),
    Page("c-sigma-split", "σ_die와 σ_run", "공부하기", "흔들림을 die 반복과 회차 이동으로 나누는 이유."),
    Page("c-loq", "LoQ와 10배", "공부하기", "숫자로 믿고 비교할 수 있는 가장 작은 크기."),
    Page("c-median-ci", "중앙값 90% 구간 구하기", "공부하기", "구간 끝 순위를 정하는 계산."),
    Page("c-delta", "허용폭 Δ", "공부하기", "Δ = 5%·|POR 중앙값| + 회차 몫."),
    Page("c-tost", "TOST와 동등 · 차이 · 미결", "공부하기", "같음을 직접 보이는 검정."),
    Page("c-routes", "ITEM 유형과 판정 길", "공부하기", "POR 값만 보고 유형과 판정 길을 정하는 표."),
    Page("c-abs-tol", "0 근처와 절대 허용폭", "공부하기", "값이 0 근처일 때 고정 허용폭을 쓰는 이유."),
    Page("c-log-scale", "잡음이 값에 비례하면 log", "공부하기", "배율로 보는 판정."),
    Page("c-power", "검정력과 표본 크기", "공부하기", "die 수를 정하는 계산."),
    Page("glossary", "용어집", "참고", "약어와 기호 풀이."),
    Page("appendix", "부록", "참고", "근거 대조표와 미해결 항목."),
)
STEPS = {p.step: p for p in SITE if p.step is not None}
JS = SOP / "assets" / "sop.js"
DATA_FILE = "assets/journeys.js"
SCENE_FILES = ('assets/scenes/steps-a', 'assets/scenes/steps-b', 'assets/scenes/guide', 'assets/scenes/concepts')   # 맡은 사람마다 .js·.css 하나 (쪽마다 같은 목록)


class BuildError(Exception):
    pass


# ---------- references.md 대조표 ----------

@dataclass(frozen=True)
class Ref:
    key: str
    item: str
    sources: tuple[str, ...]
    locations: tuple[str, ...]
    urls: tuple[str, ...]
    status: str                 # 확인 / 부분 / 내부 기준
    note: str                   # 상태 칸의 나머지 말


STATUS_PREFIX = (("확인", "확인"), ("부분", "부분"), ("근거 없음", "내부 기준"))


def _cells(line: str) -> list[str]:
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _lines(cell: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in cell.split("<br>") if x.strip() and x.strip() != "—")


def load_refs(text: str) -> dict[str, Ref]:
    table = text[text.index("## 1."):text.index("## 2.")]
    refs = {}
    for line in table.splitlines():
        cells = _cells(line) if line.startswith("|") else []
        if len(cells) != 8 or not re.fullmatch(r"\d+[a-z]?", cells[0]):
            continue
        key, item, _, source, where, url, _, status = cells
        label = next((lab for pre, lab in STATUS_PREFIX if status.startswith(pre)), None)
        if label is None:
            raise BuildError(f"references.md #{key}: 상태를 모름 ({status[:20]})")
        note = re.sub(r"^(확인|부분|근거 없음-내부 기준)[.\s]*", "", status)
        note = re.sub(r"^\(([^)]*)\)\.?\s*", r"\1. ", note).strip()
        refs[key] = Ref(key, item, _lines(source), _lines(where), _lines(url), label, note)
    return refs


STATUS_CLASS = {"확인": "st-ok", "부분": "st-part", "내부 기준": "st-int"}


def ref_item(ref: Ref) -> str:
    if len(ref.sources) == len(ref.locations):
        pairs = [f"{s} · {w}" for s, w in zip(ref.sources, ref.locations)]
    else:
        pairs = list(ref.sources) or ["출처 없음 (내부 기준)"]
    if len(ref.urls) == len(pairs):
        pairs = [f'{html.escape(p)} <a href="{html.escape(u)}" rel="noopener">원문</a>' for p, u in zip(pairs, ref.urls)]
    else:
        pairs = [html.escape(p) for p in pairs]
    note = f'<span class="ref-note">{html.escape(ref.note)}</span>' if ref.note else ""
    return (f'<li id="ref-{ref.key}"><span class="st {STATUS_CLASS[ref.status]}">{ref.status}</span> '
            f'<b>{html.escape(ref.item)}</b><span class="ref-src">{"<br>".join(pairs)}</span>{note}'
            f'<span class="ref-no">대조표 #{ref.key}</span></li>')


# ---------- 조각 표시 바꾸기 ----------

SECTION_TAG = re.compile(r"<section\b[^>]*>|</section>")
EXPERT_OPEN = re.compile(r'<section class="expert"(?: data-title="([^"]*)")?(?: id="([^"]*)")?>')
DEFAULT_EXPERT_TITLE = "수식 · 기준표 · 근거 · 코드"


def _closing(text: str, start: int) -> int:
    """text[start] 의 <section 에 짝이 되는 </section> 의 위치."""
    depth = 0
    for m in SECTION_TAG.finditer(text, start):
        depth += -1 if m.group().startswith("</") else 1
        if depth == 0:
            return m.start()
    raise BuildError("짝이 없는 <section>")


def expand_layers(text: str) -> str:
    text = text.replace('<section class="easy">', '<section class="layer easy" aria-label="쉽게">')
    while m := EXPERT_OPEN.search(text):
        end = _closing(text, m.start())
        title = html.escape(m.group(1) or DEFAULT_EXPERT_TITLE)
        ident = f' id="{m.group(2)}"' if m.group(2) else ""
        head = (f'<details class="layer expert"{ident}><summary><span class="layer-tag">전문</span>'
                f'<span class="layer-title">{title}</span></summary><div class="layer-body">')
        text = text[:m.start()] + head + text[m.end():end] + "</div></details>" + text[end + len("</section>"):]
    if '<section class="expert"' in text:
        raise BuildError('<section class="expert"> 의 속성은 data-title, id 순서만 됩니다')
    return text


def scene_names() -> set[str]:
    files = [JS, *(SOP / f"{f}.js" for f in SCENE_FILES)]
    return {n for f in files if f.is_file() for n in re.findall(r"defineScene\('([\w-]+)'", f.read_text(encoding="utf-8"))}


def expand_mounts(text: str, page: Page) -> str:
    known = scene_names()
    for name in re.findall(r'data-scene="([^"]*)"', text):
        if name not in known:
            raise BuildError(f"{page.file}: 모르는 장면 data-scene=\"{name}\" (sop.js defineScene 에 없음)")

    def tracker(m: re.Match) -> str:
        step = int(m[1]) if m[1].isdigit() else -1
        if step not in STEPS:
            raise BuildError(f"{page.file}: data-tracker=\"{m[1]}\" 는 0~7 이어야 합니다")
        # 단계 쪽은 다음 단계로, 개념·안내 쪽은 그 단계 쪽으로 잇는다
        nxt, label = (STEPS.get(step + 1), "다음 단계") if page.step is not None else (STEPS[step], "이 단계 쪽")
        attrs = (f' data-next-href="{nxt.file}" data-next-title="{html.escape(nxt.title)}"'
                 f' data-next-label="{label}"') if nxt else ""
        return f'<div class="tracker" data-tracker="{step}"{attrs}></div>'
    text = re.sub(r'<div data-tracker="([^"]*)"></div>', tracker, text)
    steps = html.escape(json.dumps([[p.file, p.title] for p in STEPS.values()], ensure_ascii=False))
    text = text.replace('<div data-journeys="list"></div>', f'<div data-journeys="list" data-steps="{steps}"></div>')
    if "<div data-flowchart></div>" in text:
        text = text.replace("<div data-flowchart></div>", flowchart())
    return text


def expand_code(text: str, page: Page) -> str:
    def code(m: re.Match) -> str:
        path, name = m[1], m[2]
        src = ROOT / path
        if not src.is_file() or not re.search(rf"^(def {re.escape(name)}\(|{re.escape(name)}\b[^=\n]*=)",
                                              src.read_text(encoding="utf-8"), re.M):
            raise BuildError(f"{page.file}: 코드 위치 {path}:{name} 를 찾지 못함")
        call = "()" if name[0].islower() else ""
        return f'<code class="codeptr">{html.escape(path)} · {html.escape(name)}{call}</code>'
    return re.sub(r'<code data-code="([^":]+):([\w]+)"></code>', code, text)


def expand_refs(text: str, page: Page, refs: dict[str, Ref]) -> str:
    order: list[str] = []

    def sup(m: re.Match) -> str:
        key = m[1]
        if key not in refs:
            raise BuildError(f"{page.file}: references.md 에 없는 근거 data-ref=\"{key}\"")
        if key not in order:
            order.append(key)
        n = order.index(key) + 1
        return f'<sup class="ref"><a href="#ref-{key}" aria-label="근거 {n}">{n}</a></sup>'
    text = re.sub(r'<sup data-ref="([^"]*)"></sup>', sup, text)
    if not order:
        if "<div data-refs></div>" in text:
            raise BuildError(f"{page.file}: data-refs 자리가 있는데 data-ref 가 없음")
        return text
    items = "\n".join(ref_item(refs[k]) for k in order)
    listing = f'<ol class="refs" id="sources">\n{items}\n</ol>'
    if "<div data-refs></div>" in text:
        return text.replace("<div data-refs></div>", listing)
    return (text + '\n<details class="layer expert"><summary><span class="layer-tag">전문</span>'
            f'<span class="layer-title">근거와 문헌</span></summary><div class="layer-body">{listing}</div></details>\n')


# ---------- 개요 흐름도 ----------

def _box(x: float, y: float, w: float, h: float, href: str, lines: tuple[str, str], cls: str = "") -> str:
    a, b = (html.escape(s) for s in lines)
    return (f'<a href="{href}" class="fc-link"><g class="fc-box {cls}">'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/>'
            f'<text x="{x + w / 2}" y="{y + h / 2 - 5}" class="fc-a">{a}</text>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + 15}" class="fc-b">{b}</text></g></a>')


def _arrow(x1: float, y1: float, x2: float, y2: float, cls: str = "") -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="fc-ar {cls}" marker-end="url(#fc-head)"/>'


def flowchart() -> str:
    """⓪~⑤ 한 줄 → ⑥ 판정 3단계 판 → 판 전체에서 최종 판정 하나 → 동등·기록, 미결·차이 → ⑦, 판정 제외 → 사유 확인."""
    w, gap, h = 116, 12.8, 64
    parts = []
    for k in range(6):
        p = STEPS[k]
        x = k * (w + gap)
        parts.append(_box(x, 0, w, h, p.file, (STEP_MARKS[k], p.title[2:]), "fc-step"))
        if k < 5:
            parts.append(_arrow(x + w + 2, h / 2, x + w + gap - 2, h / 2))
    parts.append('<path d="M58 74 V84 H702 V74" class="fc-brace"/>')
    parts.append(_arrow(380, 84, 380, 108))
    parts.append('<rect x="0" y="112" width="760" height="150" rx="14" class="fc-panel"/>')
    parts.append(f'<a href="{STEPS[6].file}" class="fc-link"><text x="20" y="140" class="fc-title">'
                 f'{html.escape(STEPS[6].title)}</text></a>')
    parts.append('<text x="740" y="140" class="fc-note">die 10개 미만은 판정 없이 미결</text>')
    stages = (("1 TOST", "모든 ITEM"), ("2 LoQ 판정", "POR 값이 LoQ 아래일 때"), ("3 판정 길", "1·2단계가 동등이 아닐 때"))
    sw, sg = 210, 45
    for k, (a, b) in enumerate(stages):
        x = 20 + k * (sw + sg)
        parts.append(_box(x, 160, sw, 80, STEPS[6].file, (a, b), f"fc-stage s{k + 1}"))
        if k < 2:
            parts.append(_arrow(x + sw + 4, 200, x + sw + sg - 4, 200))
    parts.append('<path d="M20 268 V278 H740 V268" class="fc-brace"/>')
    parts.append(_arrow(380, 278, 380, 292))
    parts.append('<g class="fc-out fc-final"><rect x="320" y="294" width="120" height="34" rx="8"/>'
                 '<text x="380" y="316">최종 판정</text></g>')
    parts.append(_arrow(318, 311, 268, 311))
    parts.append('<g class="fc-out"><rect x="124" y="294" width="140" height="34" rx="17" class="v-eq"/>'
                 '<text x="194" y="316">동등 · 기록</text></g>')
    parts.append(_arrow(442, 311, 474, 311))
    parts.append('<g class="fc-out"><rect x="478" y="294" width="134" height="34" rx="17" class="v-hold"/>'
                 '<text x="545" y="316">미결 · 차이</text></g>')
    parts.append(_arrow(614, 311, 636, 311, "dash"))
    p7 = STEPS[7]
    parts.append(_box(640, 283, 120, 56, p7.file, (STEP_MARKS[7] + " 다음 행동", "미결·차이일 때만"), "fc-opt"))
    parts.append(_arrow(380, 330, 380, 350))
    parts.append('<g class="fc-out fc-excl"><rect x="300" y="354" width="160" height="30" rx="15" class="v-excl"/>'
                 '<text x="380" y="374">판정 제외 · 사유 확인</text></g>')
    return ('<figure class="flowchart" id="flow"><svg viewBox="-2 -2 764 390" role="img" '
            'aria-label="판정 흐름도: ⓪~⑤ 준비, ⑥ 판정 3단계에서 최종 판정 하나, 동등이면 기록, 미결·차이면 ⑦ 다음 행동, '
            '판정 제외면 사유 확인">'
            '<defs><marker id="fc-head" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" '
            'orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z"/></marker></defs>'
            + "".join(parts) + "</svg><figcaption>상자를 누르면 그 단계 쪽으로 갑니다. 판정 3단계를 다 거친 뒤 최종 판정 하나가 나옵니다.</figcaption></figure>")



# ---------- 틀 ----------

def nav(page: Page) -> str:
    cur = ' aria-current="page"'

    def links(rows) -> str:
        return "".join(f'<a href="{p.file}"{cur if p is page else ""}>{html.escape(p.title)}</a>' for p in rows)
    out = []
    for section in SECTIONS:
        rows = [p for p in SITE if p.section == section]
        if section == "개요":
            out.append(links(rows))
            continue
        body = links(rows)
        if section == "공부하기":
            opened = " open" if page.section == section else ""
            body = (f'{links(rows[:1])}<details class="nav-more"{opened}><summary>개념 {len(rows) - 1}쪽</summary>'
                    f"{links(rows[1:])}</details>")
        out.append(f'<div class="nav-group"><p class="nav-h">{section}</p>{body}</div>')
    return f'<nav class="side" aria-label="문서">{"".join(out)}</nav>'


def strip(page: Page) -> str:
    chips = []
    for k, p in STEPS.items():
        now = p is page
        label = html.escape(p.title) if now else STEP_MARKS[k]
        cur = ' aria-current="step"' if now else ""
        chips.append(f'<a href="{p.file}" class="chip{" now" if now else ""}" title="{html.escape(p.title)}"{cur}>'
                     f"{label}</a>")
    return f'<nav class="strip" aria-label="단계">{"".join(chips)}</nav>'


def pager(page: Page) -> str:
    i = SITE.index(page)
    prev = SITE[i - 1] if i > 0 else None
    nxt = SITE[i + 1] if i + 1 < len(SITE) else None
    left = f'<a href="{prev.file}" class="prev">← {html.escape(prev.title)}</a>' if prev else "<span></span>"
    right = f'<a href="{nxt.file}" class="next">{html.escape(nxt.title)} →</a>' if nxt else "<span></span>"
    return f'<footer class="pager">{left}{right}</footer>'


ERROR_GUARD = ("<script>(function(){function f(m){var b=document.body;if(!b)return;b.setAttribute('data-sop-error','');"
               "var n=document.getElementById('sop-error');if(n){n.hidden=false;n.textContent='쪽 스크립트 오류: '+m;}}"
               "window.SOP_FAIL=f;window.addEventListener('error',function(e){var t=e.target;"
               "f(e.message||('불러오지 못함 '+((t&&(t.src||t.href))||'')));},true);"
               "window.addEventListener('unhandledrejection',function(e){f(String(e.reason));});})();</script>")
LAYER_BOOT = ("<script>try{if(localStorage.getItem('sop-layer')==='expert')"
              "document.documentElement.setAttribute('data-layer','expert');}catch(e){}</script>")


def render(page: Page, fragment: str, refs: dict[str, Ref]) -> str:
    body = expand_refs(expand_code(expand_mounts(expand_layers(fragment), page), page), page, refs)
    needs_data = any(f"data-{k}" in body for k in ("scene", "tracker", "journeys"))
    css = '<link rel="stylesheet" href="assets/sop.css">' + "".join(
        f'<link rel="stylesheet" href="{f}.css">' for f in SCENE_FILES)
    scripts = []
    if needs_data:
        scripts.append(f'<script src="{DATA_FILE}"></script>')
    scripts.append('<script src="assets/sop.js"></script>')
    scripts += [f'<script src="{f}.js"></script>' for f in SCENE_FILES]
    head = (
        f'<header class="page-head"><p class="kicker">{html.escape(page.section)}</p>'
        f'<h1>{html.escape(SITE_NAME if page.slug == "index" else page.title)}</h1><p class="purpose">{html.escape(page.purpose)}</p></header>\n')
    step = f' data-step="{page.step}"' if page.step is not None else ""
    return f"""<!doctype html>
<html lang="ko" data-layer="easy">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(page.title)} · {SITE_NAME}</title>
{css}
{LAYER_BOOT}
</head>
<body data-page="{page.slug}"{step}>
{ERROR_GUARD}
<header class="top"><a class="brand" href="index.html">{SITE_NAME}</a>
<div class="layer-toggle" role="group" aria-label="보기"><button type="button" data-set-layer="easy">쉽게</button><button type="button" data-set-layer="expert">전문까지</button></div></header>
<div id="sop-error" class="sop-error" role="alert" hidden></div>
{nav(page)}
<main id="main">{"" if page.slug == "index" else strip(page)}
<article class="page">
{head}{body.strip()}
{pager(page)}
</article></main>
{chr(10).join(scripts)}
</body></html>
"""


def build() -> dict[str, str]:
    refs = load_refs(REFERENCES.read_text(encoding="utf-8"))
    pages = {}
    for page in SITE:
        src = SRC / page.file
        if not src.is_file():
            raise BuildError(f"조각이 없음: {src.relative_to(ROOT)}")
        pages[page.file] = render(page, src.read_text(encoding="utf-8"), refs)
    return pages


# ---------- 링크 검사 ----------

LINK_RE = re.compile(r'\b(?:href|src)="([^"]*)"')
ID_RE = re.compile(r'\b(?:id|name)="([^"]*)"')


def link_problems(pages: dict[str, str], root: Path = SOP) -> list[str]:
    """상대 링크가 가리키는 파일과 #이름표가 있는지. pages 는 {파일 이름: HTML}."""
    ids = {name: set(ID_RE.findall(text)) for name, text in pages.items()}
    problems = []
    for name, text in pages.items():
        for link in LINK_RE.findall(text):
            if re.match(r"^[a-z]+:", link) or not link:
                continue
            path, _, anchor = link.partition("#")
            path = path.split("?")[0]
            target = path or name
            if path and target not in pages and not (root / path).is_file():
                problems.append(f"{name}: 없는 파일 {link}")
                continue
            if anchor and target.endswith(".html"):
                have = ids.get(target)
                if have is None:
                    have = set(ID_RE.findall((root / target).read_text(encoding="utf-8")))
                if anchor not in have:
                    problems.append(f"{name}: 없는 이름표 {link}")
    return problems


def main(argv: list[str]) -> int:
    check = "--check" in argv
    try:
        pages = build()
    except BuildError as e:
        print(f"실패: {e}")
        return 1
    problems = link_problems(pages)
    extra = sorted({p.name for p in SOP.glob("*.html")} - set(pages))
    problems += [f"SITE 에 없는 쪽: {name}" for name in extra]
    if check:
        stale = [name for name, text in pages.items()
                 if not (SOP / name).is_file() or (SOP / name).read_text(encoding="utf-8") != text]
        problems += [f"다시 만들어야 함: {name} (python tools/build_sop.py)" for name in stale]
    else:
        for name, text in pages.items():
            (SOP / name).write_text(text, encoding="utf-8")
    for p in problems:
        print(p)
    print(f"{len(pages)}쪽, 문제 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
