"""SOP 쪽 만들기(tools/build_sop.py): 커밋된 쪽이 새로 만든 것과 같고, 링크가 모두 이어지고, 표시를 바르게 바꾼다."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_sop  # noqa: E402
from build_sop import SITE, BuildError, link_problems, render  # noqa: E402

PAGE = next(p for p in SITE if p.slug == "step-6")


@pytest.fixture(scope="module")
def refs():
    return build_sop.load_refs(build_sop.REFERENCES.read_text(encoding="utf-8"))


def test_check_passes_on_committed_pages():
    assert build_sop.main(["--check"]) == 0, "python tools/build_sop.py 로 다시 만드세요"


def test_every_site_page_has_fragment_and_page_and_nav_link():
    index = (build_sop.SOP / "index.html").read_text(encoding="utf-8")
    for p in SITE:
        assert (build_sop.SRC / p.file).is_file(), p.slug
        assert (build_sop.SOP / p.file).is_file(), p.slug
        assert f'href="{p.file}"' in index, p.slug


def test_unknown_ref_fails_the_build(refs):
    with pytest.raises(BuildError, match="999"):
        render(PAGE, '<section class="easy"><p>x<sup data-ref="999"></sup></p></section>', refs)


def test_known_ref_becomes_numbered_footnote_with_status(refs):
    out = render(PAGE, '<p>a<sup data-ref="13"></sup> b<sup data-ref="12"></sup> c<sup data-ref="13"></sup></p>', refs)
    assert out.count('href="#ref-13"') == 2 and '>1</a></sup>' in out and '>2</a></sup>' in out
    assert 'id="ref-13"><span class="st st-int">내부 기준</span>' in out
    assert 'id="ref-12"><span class="st st-ok">확인</span>' in out


def test_expert_section_is_collapsed_and_labelled(refs):
    out = render(PAGE, '<section class="expert" data-title="수식"><h2>a</h2><section><p>b</p></section></section>', refs)
    assert '<details class="layer expert"><summary><span class="layer-tag">전문</span>' in out
    assert '<section class="expert"' not in out and "<p>b</p></section></div></details>" in out


def test_unknown_scene_and_code_pointer_fail(refs):
    with pytest.raises(BuildError, match="장면"):
        render(PAGE, '<div data-scene="no-such-scene"></div>', refs)
    with pytest.raises(BuildError, match="코드 위치"):
        render(PAGE, '<code data-code="por_doe_compare.py:no_such_function"></code>', refs)


def test_link_check_finds_missing_file_and_anchor():
    pages = {"a.html": '<a href="b.html#x">1</a><a href="b.html?type=log#y">2</a><a href="zz.html">3</a>'
                       '<a href="#self">4</a><a href="https://example.com/q">5</a>',
             "b.html": '<p id="y">b</p>'}
    assert link_problems(pages) == ["a.html: 없는 이름표 b.html#x", "a.html: 없는 파일 zz.html",
                                    "a.html: 없는 이름표 #self"]
