"""열 사전 쪽(docs/sop/columns.html): 커밋된 쪽이 CSV 에서 새로 만든 것과 같고, 설명 칸이 비지 않고,
수식에 나오는 열 이름이 실제 열이다."""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_columns_doc  # noqa: E402
import columns_doc  # noqa: E402
from columns_doc import ColumnDoc  # noqa: E402

SOP = ROOT / "docs" / "sop"
NAME_RE = re.compile(r"`([^`]+)`")


def unknown_names(doc: str, docs: dict[str, tuple[ColumnDoc, ...]]) -> list[tuple[str, str]]:
    """doc 의 수식 칸에서 `이름` 중 같은 문서·입력 문서·원데이터 어느 열도 아닌 것 (열, 이름)."""
    pool = [d for name in {doc, build_columns_doc.RAW_DOC, *build_columns_doc.INPUTS[doc]} for d in docs[name]]
    pool += [ColumnDoc(c) for c in build_columns_doc.RAW_FILE_COLUMNS]
    return [(row.column, name) for row in docs[doc] for name in NAME_RE.findall(row.formula)
            if not any(d.column == name or d.matches(name) for d in pool)]


def test_committed_page_is_fresh():
    assert (SOP / "columns.html").read_text(encoding="utf-8") == build_columns_doc.render(), \
        "python tools/build_columns_doc.py 로 다시 만드세요"


def test_page_lists_every_column_of_every_output():
    page = build_columns_doc.render()
    for o in columns_doc.OUTPUTS:
        assert f'<h2>{html.escape(o.kind)}</h2>' in page, o.kind
    for doc, rows in columns_doc.load().items():
        for row in rows:
            assert f"<td><code>{html.escape(row.column)}</code></td><td>{html.escape(row.easy_name)}</td>" in page, \
                (doc, row.column)


def test_no_row_has_empty_easy_name_or_meaning():
    empty = [(doc, d.column) for doc, rows in columns_doc.load().items() for d in rows
             if not d.easy_name.strip() or not d.meaning.strip()]
    assert empty == []


def test_no_long_dash_in_descriptions():
    bad = [(doc, d.column) for doc, rows in columns_doc.load().items() for d in rows
           if any(ch in f"{d.easy_name}{d.meaning}{d.formula}{d.look_for}" for ch in "—–")]
    assert bad == []


def test_formula_names_are_real_columns():
    docs = columns_doc.load()
    assert {doc: unknown_names(doc, docs) for doc in docs if unknown_names(doc, docs)} == {}


def test_formula_name_check_catches_unknown_and_input_scope():
    docs = dict(columns_doc.load())
    docs["compare"] = docs["compare"] + (ColumnDoc("x", formula="`no_such_col` + `sigma_die` + `DATA`"),)
    docs["group_dirs"] = (ColumnDoc("y", formula="`center`"),)
    assert unknown_names("compare", docs) == [("x", "no_such_col")]
    assert unknown_names("group_dirs", docs) == [("y", "center")]


def test_index_links_page_and_reading_points_to_it():
    index = (SOP / "index.html").read_text(encoding="utf-8")
    reading = (SOP / "reading.html").read_text(encoding="utf-8")
    assert 'href="columns.html"' in index
    columns = reading[reading.index('<section id="columns">'):]
    columns = columns[:columns.index("</section>")]
    assert 'href="columns.html#items-csv"' in columns
    assert "<table" not in columns
