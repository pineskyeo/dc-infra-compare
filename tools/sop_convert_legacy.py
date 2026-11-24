#!/usr/bin/env python3
"""옛 SOP 쪽(손으로 쓴 HTML)을 build_sop.py 가 감싸는 본문 조각 docs/sop/src/<slug>.html 로 옮긴다.

옛 쪽은 git 기록(REV)에서 읽는다. 본문(<main><div class="wrap"> 안)만 남기고, 머리글·목차·흐름도 패널·쪽 넘김은
버린다 (새 틀이 만든다). 새로 쓴 쪽(SITE 의 legacy=False)과 다른 도구가 만드는 쪽(columns)은 건드리지 않는다.
옛 sop.css 에서 본문 모양 규칙만 골라 .legacy 아래로 묶어 assets/legacy.css 로 쓴다 (틀 규칙은 버림).
옛 쪽이 새로 쓴 쪽의 없어진 이름표(#C6-3 등)를 가리키면 LINK_MAP 으로 새 이름표로 바꾼다.

usage: python tools/sop_convert_legacy.py [REV]     기본 REV 는 옛 쪽이 마지막으로 있던 커밋
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_sop import SITE  # noqa: E402

SRC = ROOT / "docs" / "sop" / "src"
REV = "9062aaa"
NEW = {p.slug for p in SITE if not p.legacy}
GENERATED = {"columns"}
OPEN, CLOSE = '<main><div class="wrap">', "</div></main>"
PAGER_RE = re.compile(r'\n?<footer class="pager">.*?</footer>\n?', re.S)

LINK_MAP = {
    **{f"step-6.html#C6-{k}": "step-6.html#stage1" for k in range(1, 7)},
    **{f"step-6.html#C6-{k}": "step-6.html#loq" for k in range(7, 12)},
    "step-6.html#C6-12": "step-6.html#final",
    "step-6.html#C6-13": "step-6.html#typed",
    "step-6.html#ex-data": "step-6.html",
    "index.html#procedure": "index.html#flow",
}


def git_show(rev: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def fragment(page: str) -> str:
    body = page[page.index(OPEN) + len(OPEN):page.rindex(CLOSE)]
    body = PAGER_RE.sub("\n", body)
    for old, new in LINK_MAP.items():
        body = body.replace(f'href="{old}"', f'href="{new}"')
    return body.strip() + "\n"


# 옛 틀(목차, 흐름도 패널, 개요 흐름도, 쪽 넘김)과 문서 전체 규칙. legacy.css 로 옮기지 않는다
LAYOUT_RE = re.compile(r"\.(side|fp|fp-[\w-]+|fb|fb-[\w-]+|pager|flow|box|fork|ar|hero|flowbig|lab)\b"
                       r"|(^|[\s,>+~])(main|html|body|\*|:focus-visible)")


def css_rules(text: str):
    """(선택자, 본문, @묶음인가) 를 차례로."""
    i = 0
    while (j := text.find("{", i)) >= 0:
        sel = text[i:j].strip()
        if sel.startswith("@"):
            depth, k = 1, j + 1
            while depth:
                depth += {"{": 1, "}": -1}.get(text[k], 0)
                k += 1
            yield sel, text[j + 1:k - 1], True
        else:
            k = text.index("}", j) + 1
            yield sel, text[j + 1:k - 1], False
        i = k


def scoped(sel: str) -> str:
    parts = []
    for one in (x.strip() for x in sel.split(",")):
        if one == ":root":
            parts.append(".legacy")
        elif not LAYOUT_RE.search(" " + one):
            one = one.replace(".wrap ", "").replace(".wrap", "")
            parts.append(f".legacy {one}".strip())
    return ",".join(parts)


def legacy_css(text: str) -> str:
    out = []
    for sel, body, group in css_rules(text):
        if group:
            inner = legacy_css(body) if sel.startswith("@media") else ""
            if inner:
                out.append(f"{sel}{{\n{inner}}}")
        elif (s := scoped(sel)) and "--fp-w" not in body:
            out.append(f"{s}{{{body.strip()}}}")
    return "\n".join(out) + ("\n" if out else "")


def main(rev: str) -> int:
    names = subprocess.run(["git", "ls-tree", "--name-only", rev, "docs/sop/"], cwd=ROOT, check=True,
                           capture_output=True, text=True).stdout.split()
    SRC.mkdir(parents=True, exist_ok=True)
    done = []
    for path in names:
        slug = Path(path).stem
        if not path.endswith(".html") or slug in NEW | GENERATED:
            continue
        (SRC / f"{slug}.html").write_text(fragment(git_show(rev, path)), encoding="utf-8")
        done.append(slug)
    css = re.sub(r"/\*.*?\*/", "", git_show(rev, "docs/sop/assets/sop.css"), flags=re.S)
    css = re.sub(r"@import url\([^)]*\);", "", css)
    (ROOT / "docs" / "sop" / "assets" / "legacy.css").write_text(
        "/* 옛 쪽(SITE legacy=True) 본문 모양. tools/sop_convert_legacy.py 가 만든다. 모든 쪽을 새로 쓰면 지운다. */\n"
        + legacy_css(css), encoding="utf-8")
    print(f"{len(done)}쪽 옮김: {' '.join(done)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else REV))
