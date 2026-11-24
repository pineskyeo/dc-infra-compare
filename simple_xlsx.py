"""표 몇 개를 엑셀 파일(.xlsx) 하나로 쓴다. 표준 라이브러리만 쓴다 (openpyxl·xlsxwriter 없이도 된다).

    write(path, [(시트 이름, DataFrame, 아래 메모 줄), ...])

시트마다 첫 줄은 굵은 머리글이고 고정(틀 고정)이다. 숫자는 숫자 칸, 글자는 그대로 (인라인 문자열), 빈 값은 빈 칸이다.
메모 줄은 표 아래 한 줄 띄고 A 열에 적는다. 열 너비는 머리글·값 길이로 정한다 (한글은 두 칸).
시트 이름은 엑셀 규칙대로 31자 이하, []:*?/\\ 는 _ 로 바꾸고 겹치면 뒤에 번호를 붙인다.
"""
from __future__ import annotations

import math
import re
import unicodedata
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

MAX_NAME = 31
MAX_WIDTH = 60
_BAD_NAME = re.compile(r"[\[\]:*?/\\]")
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006"
_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
BOLD = 1          # styles.xml cellXfs 순서: 0 보통, 1 굵게

Sheet = tuple[str, pd.DataFrame, Sequence[str]]


def sheet_names(names: Iterable[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        base = _BAD_NAME.sub("_", str(name)).strip("'") or "Sheet"
        cand, k = base[:MAX_NAME], 1
        while cand.lower() in (o.lower() for o in out):
            k += 1
            cand = f"{base[:MAX_NAME - len(str(k)) - 1]}_{k}"
        out.append(cand)
    return out


def col_letter(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _text_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA or v is pd.NaT


def _cell(ref: str, v, style: int = 0) -> str:
    s = f' s="{style}"' if style else ""
    if _is_number(v):
        return f'<c r="{ref}"{s}><v>{repr(float(v)) if isinstance(v, float) else int(v)}</v></c>'
    text = _BAD_XML.sub("", str(v))
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _plain(v):
    """numpy 수·bool 을 파이썬 값으로."""
    if hasattr(v, "item") and not isinstance(v, str):
        try:
            return v.item()
        except (ValueError, AttributeError):
            return v
    return v


def sheet_xml(table: pd.DataFrame, notes: Sequence[str] = ()) -> str:
    header = [str(c) for c in table.columns]
    rows = [[_plain(v) for v in row] for row in table.itertuples(index=False, name=None)]
    widths = [_text_width(h) for h in header]
    lines = [f'<row r="1">' + "".join(_cell(f"{col_letter(j)}1", h, BOLD) for j, h in enumerate(header)) + "</row>"]
    for i, row in enumerate(rows, 2):
        cells = []
        for j, v in enumerate(row):
            if _blank(v):
                continue
            cells.append(_cell(f"{col_letter(j)}{i}", v))
            widths[j] = max(widths[j], _text_width(f"{v:.6g}" if _is_number(v) and isinstance(v, float) else str(v)))
        lines.append(f'<row r="{i}">' + "".join(cells) + "</row>")
    for k, note in enumerate(notes, len(rows) + 3):
        lines.append(f'<row r="{k}">{_cell(f"A{k}", note)}</row>')
    cols = "".join(f'<col min="{j + 1}" max="{j + 1}" width="{min(MAX_WIDTH, w + 2)}" customWidth="1"/>'
                   for j, w in enumerate(widths))
    return (f'{_HEAD}<worksheet xmlns="{_NS}" xmlns:r="{_REL_NS}">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
            'state="frozen"/></sheetView></sheetViews>'
            f'{f"<cols>{cols}</cols>" if cols else ""}<sheetData>{"".join(lines)}</sheetData></worksheet>')


STYLES = (f'{_HEAD}<styleSheet xmlns="{_NS}">'
          '<fonts count="2"><font><sz val="11"/><name val="Malgun Gothic"/></font>'
          '<font><b/><sz val="11"/><name val="Malgun Gothic"/></font></fonts>'
          '<fills count="2"><fill><patternFill patternType="none"/></fill>'
          '<fill><patternFill patternType="gray125"/></fill></fills>'
          '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
          '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
          '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
          '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
          '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
          '</styleSheet>')


def write(path: Path, sheets: Sequence[Sheet]) -> Path:
    """sheets 를 path 에 쓴다 (시트가 없으면 ValueError). 쓴 경로를 돌려준다."""
    if not sheets:
        raise ValueError("시트가 하나도 없습니다")
    names = sheet_names(name for name, _, _ in sheets)
    n = len(sheets)
    content_types = (
        f'{_HEAD}<Types xmlns="{_PKG}/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                  for i in range(1, n + 1))
        + "</Types>")
    root_rels = (f'{_HEAD}<Relationships xmlns="{_PKG}/relationships">'
                 f'<Relationship Id="rId1" Type="{_REL_NS}/officeDocument" Target="xl/workbook.xml"/>'
                 "</Relationships>")
    workbook = (f'{_HEAD}<workbook xmlns="{_NS}" xmlns:r="{_REL_NS}"><bookViews><workbookView/></bookViews><sheets>'
                + "".join(f'<sheet name="{escape(name, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                          for i, name in enumerate(names, 1))
                + "</sheets></workbook>")
    wb_rels = (f'{_HEAD}<Relationships xmlns="{_PKG}/relationships">'
               + "".join(f'<Relationship Id="rId{i}" Type="{_REL_NS}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                         for i in range(1, n + 1))
               + f'<Relationship Id="rId{n + 1}" Type="{_REL_NS}/styles" Target="styles.xml"/></Relationships>')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", STYLES)
        for i, (_, table, notes) in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(table, notes))
    return path
