"""조합 하나의 결과 폴더를 웹브라우저로 여는 리포트로 만든다 (설계 1-9). 폴더에 이미 있는 결과 파일만 읽는다.
그림은 파일 안에 넣고(base64 PNG) 외부 주소·스크립트를 부르지 않아 인터넷 없이 열리고 메일로 보내도 깨지지 않는다.

  python report.py <out>/<이름> [--anon] [--groups ITEM,그룹 파일]

  <폴더>/report.html         판정: 한눈에 (LoQ 요약 포함), 판정 지도, 차이·미결, 판정 제외, LoQ·log 확인 필요, 측정 안정도,
                             log 허용폭 두 방식
  <폴더>/loq/report.html     loq/ 가 있으면 (dcc.py loq): LoQ 아래 ITEM 만. 한 줄 답, 동등이 된 이유, 만든 비교의 시험,
                             LoQ 규칙·판정 길로 동등이 된 ITEM, LoQ 확인 필요, 방법과 한계. 같은 표를 loq/LoQ.xlsx 로도 쓴다
  <폴더>/item/report.html    item/ 이 있으면: ITEM 별 변화량, ITEM 마다 카드 (판정, 이유, 한 장 그림, 근거 숫자)
  <폴더>/group/report.html   group/ 이 있으면: 그룹별 표, 그룹 × LEVEL 측정 정밀도, 그룹 그림
  <폴더>/compare/report.html compare/ 가 있으면: 기존·개선 비교 요약, 그룹별, 판정 변화, 나빠진 ITEM, 그림.
                             같은 표를 compare/비교.xlsx 로도 쓴다 (--anon 이면 비교_anon.xlsx)

주제마다 접는 칸(<details>)이고 첫 화면 칸만 펼쳐 둔다. 화면에는 짧은 이름과 숫자만 두고 설명(읽는 법, 열 뜻, 원래 값과
단위)은 마우스를 올리거나 키보드로 고르면 뜨는 풍선(ⓘ, 표 칸의 title)에 둔다.
--anon 이면 ITEM 이름 대신 익명 ID 만 쓰고 report_anon.html 로 따로 쓴다 (실명 report.html 은 그대로).
ITEM 이름이 그려진 그림은 넣지 않는다.
그룹 파일은 폴더 안에 없어서 그룹별 판정 개수 표는 --groups 를 줄 때만 만든다.
"""
from __future__ import annotations

import argparse
import base64
import html
import math
import os
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import columns_doc
import compare_book
import explain
import loq_check
import simple_xlsx
from explain import BASIS_NAMES, LOQ_ZONES, V_EXCLUDED, fmt, pct
from item_view import basis_numbers
from plot_verdicts import LOQ_HOW_TO_READ, MAP_HOW_TO_READ, map_points
from review import ITEM_HOW_TO_READ, LOG_MAP_HOW_TO_READ, LOQ_MAP_HOW_TO_READ
from stability import HOW_TO_READ as STABILITY_HOW_TO_READ
from stability import LEVEL_HOW_TO_READ

COLUMNS_PAGE = Path(__file__).resolve().parent / "docs" / "sop" / "columns.html"
VERDICT_ORDER = ("차이", "미결", "동등", V_EXCLUDED)
SEVERE = ("차이", "미결")
WORST_PER_GROUP = 3
ANON_FIGURE_NOTE = "익명 리포트라 ITEM 이름이 그려진 그림은 넣지 않았다"
FOREST_HOW_TO_READ = ("한 줄이 ITEM 하나다. 점은 변화량 중앙값, 막대는 90% 신뢰구간이고 ±1 이 허용폭이다. 막대 전체가 "
                      "초록 띠 안이면 동등, 전체가 밖이면 차이, 걸치면 미결이다.")
ITEM_VIEW_HOW_TO_READ = ("① 같은 die 의 POR1 대 DOE(빨강)·다른 POR 회차(회색), 점선은 대각선 ± 허용폭. ② die별 변화량을 "
                         "작은 순으로 세운 막대, 진한 막대가 중앙값, 파란 띠가 90% 신뢰구간을 정하는 die, 주황 점선이 "
                         "±허용폭. ③ 좌표가 있으면 같은 변화량을 웨이퍼 위치에. ④ 회차별 die 값 분포.")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""], dtype=str)


def num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def plain_num(x) -> str:
    v = num(x)
    if not math.isfinite(v):
        return "-" if not isinstance(x, str) or not x.strip() else x
    return f"{v:,.0f}" if v == int(v) and abs(v) < 1e15 else f"{v:.3g}"


def share(x) -> str:
    return explain.share_text(x)


def precision_pct(x) -> str:
    v = num(x)
    return (f"{v:,.0f}%" if v >= 100 else f"{v:.3g}%") if math.isfinite(v) else "-"


def yes(x) -> bool:
    return str(x).strip().lower() == "true"


def true_rows(t: pd.DataFrame, col: str) -> pd.DataFrame:
    """col 이 True 인 행 (열이 없거나 빈 표면 빈 표)."""
    return t.loc[t[col].map(yes).astype(bool)] if col in t else t.iloc[0:0]


class Namer:
    """ITEM 이름 ↔ 익명 ID. anon 이면 화면에 나가는 모든 글자에서 ITEM 이름을 ID 로 바꾼다."""

    def __init__(self, items: pd.DataFrame, anon: bool):
        self.anon = anon
        self.report_file = "report_anon.html" if anon else "report.html"   # 익명본이 실명본을 덮지 않게
        names = items["ITEM"].astype(str)
        ids = items["ID"].astype(str) if "ID" in items else pd.Series([f"ITEM{i + 1:04d}" for i in range(len(items))])
        self.id_of = dict(zip(names, ids))
        hidden = dict(self.id_of)
        for col in ("blank_item", "blank_LoQ_item"):
            for name in items.get(col, pd.Series(dtype=str)).dropna().astype(str):
                hidden.setdefault(name, "blank 항목")
        self._hidden = hidden
        words = sorted((n for n in hidden if n.strip()), key=len, reverse=True)
        self._pattern = (re.compile(r"(?<![0-9A-Za-z_])(?:" + "|".join(map(re.escape, words)) + r")(?![0-9A-Za-z_])")
                         if words else None)

    def label(self, item) -> str:
        item = str(item)
        return self.id_of.get(item, "ID 없음") if self.anon else item

    def text(self, s) -> str:
        s = "" if s is None or (isinstance(s, float) and math.isnan(s)) else str(s)
        if self.anon and self._pattern is not None:
            s = self._pattern.sub(lambda m: self._hidden[m[0]], s)
        return html.escape(s)


@dataclass(frozen=True)
class Col:
    """표 한 열. 머리글은 열 사전(kind 결과 파일의 column)의 쉬운이름과 뜻(풍선), kind 가 빈 칸이면 column 과 head_tip.
    get 은 행 → 칸 글자 (없으면 column 값을 숫자로), tip 은 행 → 칸 풍선 (원래 값과 단위, 설명)."""
    kind: str
    column: str
    get: Callable[[Mapping], str] | None = None
    item_name: bool = False      # 실제 ITEM 이름 열 (익명이면 뺀다)
    tip: Callable[[Mapping], str] | None = None
    head_tip: str = ""
    cls: Callable[[Mapping], str] | None = None      # 칸 class (색)

    def cell(self, row: Mapping) -> str:
        return self.get(row) if self.get else plain_num(row.get(self.column))


def csv_cols(kind: str, columns: Iterable[str], formats: Mapping[str, Callable] | None = None) -> list[Col]:
    formats = formats or {}
    return [Col(kind, c, (lambda r, c=c, f=formats[c]: f(r.get(c))) if c in formats else None) for c in columns]


@dataclass(frozen=True)
class Figure:
    path: Path
    title: str
    names: bool                  # ITEM 이름이 그려져 있음
    how: str = ""                # 읽는 법 (마우스오버)


@dataclass
class Section:
    badge: str = ""              # 접힌 제목 옆 숫자 (안을 그리고 나서 정해도 된다)


@dataclass
class Page:
    title: str
    namer: Namer
    out: Path
    subtitle: str = ""
    parts: list[str] = field(default_factory=list)
    sections: list[tuple[str, str]] = field(default_factory=list)
    used: dict[tuple[str, str], columns_doc.ColumnDoc] = field(default_factory=dict)
    hidden_figures: int = 0

    def add(self, html_text: str) -> None:
        self.parts.append(html_text)

    def tip(self, text: str) -> str:
        """마우스를 올리거나 Tab 으로 고르면 뜨는 풍선 (스크립트 없이 CSS 만)."""
        if not text:
            return ""
        t = self.namer.text(text)
        return f'<span class="tip" tabindex="0" role="note" aria-label="{t}" data-tip="{t}">i</span>'

    @contextmanager
    def section(self, anchor: str, title: str, tip: str = "", open: bool = False) -> Iterator[Section]:
        """접는 주제 칸. anchor 는 내용 칸의 id (목차가 가리키면 브라우저가 칸을 펼친다)."""
        self.sections.append((anchor, title))
        sec, at = Section(), len(self.parts)
        self.add("")
        yield sec
        badge = f'<span class="badge">{self.namer.text(sec.badge)}</span>' if sec.badge else ""
        self.parts[at] = (f'<details class="sec"{" open" if open else ""}><summary><h2>{self.namer.text(title)}</h2>'
                          f'{badge}{self.tip(tip)}</summary><div class="body" id="{anchor}">')
        self.add("</div></details>")

    @contextmanager
    def fold(self, summary: str) -> Iterator[None]:
        """칸 안에서 한 번 더 접는 부분 (보조 그림·숫자 표). 처음에는 접혀 있다."""
        self.add(f'<details class="sub"><summary>{self.namer.text(summary)}</summary>')
        yield
        self.add("</details>")

    def h3(self, text: str, tip: str = "") -> None:
        self.add(f"<h3>{self.namer.text(text)}{self.tip(tip)}</h3>")

    def p(self, text: str, cls: str = "") -> None:
        self.add(f'<p{f" class={cls!r}" if cls else ""}>{self.namer.text(text)}</p>')

    def lede(self, text: str) -> None:
        self.p(text, "lede")

    def skipped(self, what: str) -> None:
        self.p(f"{what} 없음.", "note")

    def header(self, col: Col) -> tuple[str, str]:
        doc = columns_doc.doc_for(col.kind, col.column) if col.kind else None
        if doc is None:
            return col.column, col.head_tip
        self.used[(doc.easy_name or col.column, doc.meaning)] = doc
        name = doc.easy_name if doc.column == col.column and doc.easy_name else col.column
        return name, col.head_tip or doc.meaning

    def table(self, cols: list[Col], rows: Iterable[Mapping]) -> None:
        rows = list(rows)
        if not rows:
            self.p("해당 행 없음.", "note")
            return
        cols = [c for c in cols if not (self.namer.anon and c.item_name)]
        heads = "".join(f'<th title="{self.namer.text(m)}">{self.namer.text(n)}</th>' if m else
                        f"<th>{self.namer.text(n)}</th>" for n, m in map(self.header, cols))

        def td(c: Col, r: Mapping) -> str:
            tip = c.tip(r) if c.tip else ""
            cls = c.cls(r) if c.cls else ""
            attr = (f' title="{self.namer.text(tip)}"' if tip else "") + (f' class="{self.namer.text(cls)}"' if cls else "")
            return f"<td{attr}>{self.namer.text(c.cell(r))}</td>"
        body = "".join("<tr>" + "".join(td(c, r) for c in cols) + "</tr>" for r in rows)
        self.add(f'<div class="wrap"><table><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table></div>')

    def figure(self, fig: Figure) -> bool:
        """그림을 넣는다. 파일이 없으면 False. 익명이고 ITEM 이름이 그려진 그림이면 세기만 한다."""
        if not fig.path.is_file():
            return False
        if self.namer.anon and fig.names:
            self.hidden_figures += 1
            return True
        data = base64.b64encode(fig.path.read_bytes()).decode("ascii")
        title = self.namer.text(fig.title)
        hover = f' title="{self.namer.text(fig.how)}"' if fig.how else ""
        self.add(f'<figure><figcaption>{title}{self.tip(fig.how)}</figcaption>'
                 f'<img alt="{title}"{hover} src="data:image/png;base64,{data}"></figure>')
        return True

    def figures(self, figs: Iterable[Figure]) -> None:
        if not sum(self.figure(f) for f in figs):
            self.skipped("그림 파일")

    def html(self) -> str:
        notes = (f'<p class="note">{ANON_FIGURE_NOTE} ({self.hidden_figures}장).</p>'
                 if self.hidden_figures else "")
        nav = ("<nav>" + "".join(f'<a href="#{a}">{self.namer.text(t)}</a>' for a, t in self.sections) + "</nav>"
               if len(self.sections) > 1 else "")
        sub = f'<p class="sub">{self.namer.text(self.subtitle)}</p>' if self.subtitle else ""
        return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">'
                f"<title>{self.namer.text(self.title)}</title><style>{CSS}</style></head><body>"
                f"<header><h1>{self.namer.text(self.title)}</h1>{sub}</header>{nav}<main>{notes}"
                f"{''.join(self.parts)}</main></body></html>")

    def glossary(self) -> None:
        """이 쪽 표에 쓴 열의 뜻 (메일로 받아 열 사전 쪽이 없는 사람용)."""
        if not self.used:
            return
        rows = "".join(f"<tr><td>{self.namer.text(name)}</td><td>{self.namer.text(d.meaning)}</td>"
                       f"<td>{self.namer.text(d.look_for)}</td></tr>"
                       for (name, _), d in sorted(self.used.items()))
        self.add('<details class="sub"><summary>이 리포트의 표에 쓴 열</summary><div class="wrap"><table><thead><tr>'
                 f"<th>열</th><th>뜻</th><th>볼 것</th></tr></thead><tbody>{rows}</tbody></table></div></details>")

    def link(self, text: str, href: str) -> None:
        self.add(f'<p class="note"><a href="{html.escape(href)}">{self.namer.text(text)}</a></p>')

    def columns_link(self) -> None:
        try:
            href = Path(os.path.relpath(COLUMNS_PAGE, self.out.parent)).as_posix()
        except ValueError:
            href = COLUMNS_PAGE.as_uri()
        self.add(f'<p class="note">모든 열의 뜻·수식·볼 것: <a href="{html.escape(href)}">docs/sop/columns.html</a> '
                 "(dc-infra-compare 저장소 안).</p>")

    def write(self) -> Path:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(self.html(), encoding="utf-8")
        return self.out


CSS = """
:root{--fg:#1f2328;--muted:#656d76;--faint:#8c959f;--line:#e4e7eb;--bg:#ffffff;--card:#f7f8fa;--accent:#256abf;
--차이:#c8463d;--미결:#d08a1e;--동등:#3d8b54;--제외:#8c959f}
*{box-sizing:border-box}
body{font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;color:var(--fg);
background:var(--bg);margin:0;line-height:1.55;font-size:14px;font-variant-numeric:tabular-nums}
header,nav,main{max-width:1240px;margin:0 auto;padding:0 24px}
header{padding-top:28px}h1{font-size:22px;font-weight:650;margin:0}.sub{color:var(--muted);margin:2px 0 0}
nav{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.94);backdrop-filter:blur(6px);
border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:2px 16px;padding-top:10px;padding-bottom:10px;
font-size:13px}
nav a{color:var(--muted);text-decoration:none}nav a:hover{color:var(--accent)}
main{padding-bottom:64px}
details.sec{border-bottom:1px solid var(--line)}
details.sec>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;padding:16px 0}
details.sec>summary::-webkit-details-marker{display:none}
details.sec>summary::before{content:"";width:7px;height:7px;border-right:2px solid var(--faint);
border-bottom:2px solid var(--faint);transform:rotate(-45deg);transition:transform .15s;margin:0 4px 0 2px}
details.sec[open]>summary::before{transform:rotate(45deg)}
summary h2{font-size:17px;font-weight:650;margin:0}
.body{padding:0 0 22px 21px;scroll-margin-top:96px}
.badge{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:0 9px;font-size:12px;
color:var(--muted)}
h3{font-size:14px;font-weight:650;margin:22px 0 8px;display:flex;align-items:center}
p{margin:6px 0}.lede{color:var(--muted);margin:0 0 12px}.note{color:var(--muted);font-size:12.5px}
.tip{position:relative;display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;
border-radius:50%;border:1px solid var(--faint);color:var(--muted);font:italic 600 11px/1 Georgia,serif;
cursor:help;margin-left:8px;flex:none}
.tip:hover,.tip:focus{border-color:var(--accent);color:var(--accent);outline:none}
.tip::after{content:attr(data-tip);position:absolute;left:-10px;top:calc(100% + 8px);width:max-content;
max-width:min(460px,80vw);padding:10px 12px;background:#24292f;color:#fff;border-radius:6px;font:400 12.5px/1.6
-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;white-space:pre-line;text-align:left;
box-shadow:0 6px 18px rgba(0,0,0,.18);opacity:0;visibility:hidden;transition:opacity .12s;z-index:30;
pointer-events:none}
.tip:hover::after,.tip:focus::after{opacity:1;visibility:visible}
.wrap{overflow-x:auto}
table{border-collapse:collapse;font-size:13px;margin:4px 0 8px}
th,td{padding:6px 14px 6px 0;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:12px;white-space:nowrap;border-bottom-color:#cfd5dc}
th[title],td[title]{cursor:help}td[title]{text-decoration:underline dotted var(--faint);text-underline-offset:3px}
tbody tr:hover{background:var(--card)}
figure{margin:14px 0 26px}figcaption{display:flex;align-items:center;font-size:14px;font-weight:600;
margin-bottom:8px}img{display:block;max-width:100%;height:auto;border:1px solid var(--line);border-radius:6px}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 16px;min-width:120px;
color:var(--muted);font-size:13px}.card b{display:block;font-size:24px;font-weight:650;color:var(--fg);margin:2px 0}
.card.차이{border-top:3px solid var(--차이)}.card.미결{border-top:3px solid var(--미결)}
.card.동등{border-top:3px solid var(--동등)}.card.판정.제외{border-top:3px solid var(--제외)}
.chips{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0 0 6px;color:var(--muted);font-size:13px}
.chip{border:1px solid var(--line);border-radius:999px;padding:1px 10px}.chip b{color:var(--fg);margin-left:4px}
details.item{border:1px solid var(--line);border-radius:8px;margin:10px 0;padding:0 14px}
details.item>summary{cursor:pointer;padding:10px 0;font-weight:600}
details.item[open]>summary{border-bottom:1px solid var(--line);margin-bottom:10px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;background:var(--제외)}
.dot.차이{background:var(--차이)}.dot.미결{background:var(--미결)}.dot.동등{background:var(--동등)}
details.sub{margin:10px 0}details.sub>summary{cursor:pointer;color:var(--muted);font-size:13px}
ul.lines{margin:6px 0;padding-left:18px;color:var(--muted)}
.headline{font-size:17px;font-weight:650;margin:2px 0 8px}
td.좋아짐{color:var(--동등);font-weight:650}td.나빠짐{color:var(--차이);font-weight:650}td.비슷{color:var(--faint)}
@media print{nav{display:none}.wrap{overflow:visible}figure{break-inside:avoid}}
"""


def cards(page: Page, entries: Iterable[tuple[str, str, str]]) -> None:
    """(이름, 큰 숫자, 아래 작은 글) 카드 한 줄."""
    page.add('<div class="cards">' + "".join(
        f'<div class="card {page.namer.text(name)}">{page.namer.text(name)}<b>{page.namer.text(big)}</b>'
        f'{page.namer.text(small)}</div>' for name, big, small in entries) + "</div>")


def chips(page: Page, label: str, entries: Iterable[tuple[str, str]], tip: str = "") -> None:
    page.add(f'<p class="chips">{page.namer.text(label)}{page.tip(tip)}' + "".join(
        f'<span class="chip">{page.namer.text(name)}<b>{page.namer.text(n)}</b></span>' for name, n in entries)
        + "</p>")


# ── 판정 리포트 ──────────────────────────────────────────────────────────────

def unit_of(row: Mapping) -> str:
    u = row.get("UNIT")
    return "" if u is None or (isinstance(u, float) and math.isnan(u)) else str(u)


def basis_of(row: Mapping) -> str:
    b = row.get("verdict_basis")
    return b if isinstance(b, str) and b else "linear"


def basis_name(row: Mapping) -> str:
    return BASIS_NAMES.get(basis_of(row), basis_of(row))


def with_map(items: pd.DataFrame) -> list[dict]:
    """items 행마다 판정 지도 좌표를 더한다: map_x = 정규화 변화량, map_y = 정규화 불확실성 (최종 판정을 정한 방법의
    허용폭으로 나눔, plot_verdicts.map_points 와 같은 값)."""
    pts = map_points(items)
    return [{**r, "map_x": x, "map_y": y} for r, x, y in zip(items.to_dict("records"), pts["x"], pts["y"])]


def severity(row: Mapping) -> float:
    """신뢰구간 끝이 허용폭의 몇 배까지 가나 (= |정규화 변화량| + 정규화 불확실성). 클수록 심하다."""
    v = abs(num(row.get("map_x"))) + num(row.get("map_y"))
    return v if math.isfinite(v) else -math.inf


def by_severity(items: pd.DataFrame) -> list[dict]:
    return sorted(with_map(items), key=lambda r: (VERDICT_ORDER.index(r["verdict_final"])
                                                 if r.get("verdict_final") in VERDICT_ORDER else len(VERDICT_ORDER),
                                                 -severity(r)))


def id_cols(kind: str, id_kind: str | None = None, namer: Namer | None = None) -> list[Col]:
    """익명 ID 와 ITEM 이름 두 열. id_kind 는 ID 열을 설명하는 결과 파일 (ID 열이 없는 파일이면 items.csv)."""
    get_id = (lambda r: namer.id_of.get(str(r.get("ITEM")), "-")) if namer else None
    return [Col(id_kind or kind, "ID", get_id), Col(kind, "ITEM", lambda r: str(r.get("ITEM")), item_name=True)]


def log_pct(v) -> str:
    """log 단위 허용폭·이동 → 배율 %. 0.0212 → +5.0%."""
    x = num(v)
    return f"{(10 ** x - 1) * 100:+.1f}%" if math.isfinite(x) else "-"


def _raw(row: Mapping) -> tuple[Callable[[float], str], object]:
    """(값 → 원래 단위 글자, 최종 판정을 정한 숫자). log 판정이면 배율 %."""
    b = basis_numbers(row)
    return (log_pct if b.log else (lambda v: fmt(v, unit_of(row), signed=True))), b


def shift_tip(row: Mapping) -> str:
    show, b = _raw(row)
    return (f"변화량 {show(b.center)}, 90% 신뢰구간 {show(b.ci_low)} ~ {show(b.ci_high)}, "
            f"허용폭 ±{show(b.margin).lstrip('+')}")


def spread_tip(row: Mapping) -> str:
    show, b = _raw(row)
    return f"신뢰구간 반폭 {show((b.ci_high - b.ci_low) / 2).lstrip('+')} ÷ 허용폭 {show(b.margin).lstrip('+')}"


def signed2(v) -> str:
    x = num(v)
    return f"{x:+.2f}" if math.isfinite(x) else "-"


NORM_SHIFT = Col("", "정규화 변화량", lambda r: signed2(r.get("map_x")), tip=shift_tip,
                 head_tip="신뢰구간 가운데 ÷ 허용폭. 0 = 그대로, ±1 = 허용폭만큼 변함 (판정 지도 가로축). "
                          "칸에 마우스를 올리면 원래 값과 단위.")
NORM_SPREAD = Col("", "정규화 불확실성", lambda r: signed2(r.get("map_y")).lstrip("+"), tip=spread_tip,
                  head_tip="90% 신뢰구간 반폭 ÷ 허용폭. 0 = 확실, 클수록 흔들림 (판정 지도 세로축).")


def problem_cols(namer: Namer) -> list[Col]:
    return [
        *id_cols("items.csv", namer=namer),
        Col("items.csv", "verdict_final", lambda r: r["verdict_final"], tip=explain.reason_plain),
        Col("", "판정 방법", basis_name, head_tip="최종 판정을 정한 방법 (verdict_basis)"),
        NORM_SHIFT, NORM_SPREAD,
        Col("", "변화 %", lambda r: "-" if r.get("zone") in LOQ_ZONES else pct(r.get("center"), r.get("por_median")),
            tip=lambda r: f"POR 중앙값 {fmt(r.get('por_median'), unit_of(r))} 대비",
            head_tip="변화량 ÷ |POR 중앙값|. LoQ 아래 ITEM 은 값이 작아 % 가 커 보여 비운다."),
    ]


HOW_TO_READ = (
    "판정은 DOE와 POR의 die별 차이(변화량)의 90% 신뢰구간을 허용폭과 견주어 정한다. 전체가 허용폭 안이면 동등, "
    "전체가 밖이면 차이, 걸치면 미결이다. 판정 제외는 계산할 수 없는 ITEM 이다.",
    "최종 판정은 ITEM 유형에 맞는 방법(판정 방법 열)으로 정한다. 정규화 변화량·불확실성은 그 방법의 허용폭으로 나눈 값이다.",
    "판정력은 신뢰구간 반폭 ÷ 허용폭이다. 0.5 이하면 안정, 0.8 이하면 주의, 그 위는 불안정이다. 불안정 ITEM 의 미결은 측정 탓일 수 있다.",
    "LoQ·log 확인 필요는 참고 표시다. 판정은 바꾸지 않는다. 확인 필요 ITEM 은 상세 그림을 보고 원데이터를 다시 확인한다.",
    "LoQ 요약은 LoQ 아래 ITEM 만 따로 센 것이다. 시험은 POR 회차 하나를 DOE 자리에 둔, 답을 아는 비교다 (loq/report.html).",
    "제목 옆 i, 표 머리글, 밑줄 친 칸에 마우스를 올리면 설명과 원래 값이 나온다.",
)


def kpi(page: Page, items: pd.DataFrame) -> None:
    n = len(items)
    counts = items["verdict_final"].value_counts()
    cards(page, [(v, f"{int(counts.get(v, 0)):,}", f"{100 * counts.get(v, 0) / n:.0f}%" if n else "")
                 for v in ("동등", "미결", "차이", V_EXCLUDED)])
    basis = items["verdict_basis"].fillna("linear").value_counts() if "verdict_basis" in items else pd.Series(dtype=int)
    chips(page, "판정 방법", [(BASIS_NAMES.get(b, b), f"{int(c):,}") for b, c in basis.items()],
          "최종 판정을 정한 방법별 ITEM 수")


LOQ_BLOCK_TIP = ("LoQ 아래 ITEM (zone 검출한계 이하·검출~정량) 만 따로 센 것. 동등이 된 이유와, POR 회차 하나를 DOE "
                 "자리에 두고 알려진 변화를 넣어 판정 코드를 그대로 돌린 시험의 잡힌 비율이다. 판정은 그대로다.")
PASS_TIP = ("이동이 허용폭 안 = LoQ 규칙 없이도 동등. DOE 구간도 LoQ 아래·DOE 구간이 LoQ에 걸침 = LoQ 규칙으로 동등. "
            "판정 길 = 2단계는 차이·미결인데 3단계 판정 길 (괄호 안) 이 동등.")


def loq_block(page: Page, book: loq_check.LoqBook) -> None:
    """한눈에 칸의 LoQ 요약: ITEM 수, 동등이 된 이유, LoQ 규칙 효과, 시험 한 줄, LoQ 리포트 링크."""
    page.h3("LoQ 요약", LOQ_BLOCK_TIP)
    if not book.summary.ledger.n_zone:
        page.p("LoQ 아래 ITEM 이 없다.", "note")
        return
    first, *rest = book.headline_lines()
    page.p(first)
    chips(page, "동등이 된 이유", [(k, f"{n:,}") for k, n in book.summary.ledger.passes.items()], PASS_TIP)
    for line in rest:
        page.p(line)
    if book.check is not None:
        page.link("LoQ만 본 리포트 → loq/report.html", f"{loq_check.LOQ_DIR}/{page.namer.report_file}")


def problems(page: Page, items: pd.DataFrame, sec: Section) -> None:
    rows = [r for r in by_severity(items) if r.get("verdict_final") in SEVERE]
    sec.badge = f"{len(rows):,}"
    if not rows:
        page.p("차이·미결 ITEM 이 없다.", "note")
        return
    page.table(problem_cols(page.namer), rows)


def excluded(page: Page, items: pd.DataFrame, sec: Section) -> None:
    rows = items[items["verdict_final"] == V_EXCLUDED].to_dict("records")
    sec.badge = f"{len(rows):,}"
    if not rows:
        page.p("판정 제외 ITEM 이 없다.", "note")
        return
    size = pd.Series([explain.reason_plain(r) for r in rows]).value_counts()
    rows.sort(key=lambda r: (-size[explain.reason_plain(r)], explain.reason_plain(r)))
    page.table([*id_cols("items.csv", namer=page.namer), Col("item_evidence", "reason_plain", explain.reason_plain),
                Col("items.csv", "n_die")], rows)


def log_run_compare(page: Page, items: pd.DataFrame) -> None:
    """verdict_final 과 verdict_final_log_run (log 허용폭만 선형 꼴로 고친 최종 판정) 이 다른 ITEM."""
    if "verdict_final_log_run" not in items:
        page.p("이 items.csv 에는 고친 log 허용폭 결과(verdict_final_log_run)가 없다.", "note")
        return
    changed = items[items["verdict_final"].astype(str) != items["verdict_final_log_run"].astype(str)]
    if changed.empty:
        page.lede("두 방식의 최종 판정이 같다. 바뀌는 ITEM 이 없다.")
        return
    pairs = changed.groupby(["verdict_final", "verdict_final_log_run"]).size()
    page.lede(f"최종 판정이 바뀌는 ITEM {len(changed):,}개: "
              + ", ".join(f"{a} → {b} {n:,}개" for (a, b), n in pairs.items()) + ".")
    cols = [*id_cols("items.csv", namer=page.namer), Col("items.csv", "verdict_final", lambda r: r.get("verdict_final")),
            Col("items.csv", "verdict_final_log_run", lambda r: r.get("verdict_final_log_run")),
            Col("items.csv", "center_log", lambda r: log_pct(r.get("center_log")),
                tip=lambda r: f"90% 신뢰구간 {log_pct(r.get('ci_low_log'))} ~ {log_pct(r.get('ci_high_log'))}"),
            Col("items.csv", "delta_log", lambda r: log_pct(r.get("delta_log"))),
            Col("items.csv", "delta_log_run", lambda r: log_pct(r.get("delta_log_run")))]
    page.table(cols, changed.to_dict("records"))


LOG_RUN_TIP = ("log 판정의 허용폭을 두 가지로 계산해 최종 판정을 나란히 놓았다 (결정 대기). 지금 방식(delta_log)은 die를 "
               "다시 잴 때의 흔들림을 허용폭에 더하는데, 그 흔들림은 신뢰구간 폭에도 이미 들어 있어 두 번 세는 셈이다. 고친 "
               "방식(delta_log_run)은 선형 허용폭과 같은 꼴로 웨이퍼 공통 회차 흔들림만 더한다. 집계와 다른 표는 지금 "
               "방식(verdict_final)을 쓴다. 숫자는 log 값을 배율로 바꾼 %다 (+5.0% = POR의 1.05배).")

REVIEW_ITEM_DIR = "items"
REVIEW_FIGURES = 20      # 재확인 칸마다 싣는 확인 필요 ITEM 상세 그림 수 (review CSV 순서 = 근거가 센 순서)


def review_figure(folder: Path, item: str) -> Path:
    from compare_metrics import safe_group_name
    return folder / "review" / REVIEW_ITEM_DIR / f"{safe_group_name(item)}.png"


def ratio_tip(r: Mapping) -> str:
    lo, hi = num(r.get("ratio_lo")), num(r.get("ratio_hi"))
    return f"90% 범위 {lo:.3g} ~ {hi:.3g}배" if math.isfinite(lo) and math.isfinite(hi) else ""


def ratio_text(r: Mapping) -> str:
    v = num(r.get("ratio"))
    return f"{v:.3g}배" if math.isfinite(v) else "-"


def flag_kinds(kinds: Mapping[str, str]) -> Callable[[Mapping], str]:
    """확인 근거 칸: kinds (flag 열 → 짧은 이름) 중 True 인 것."""
    return lambda r: " · ".join(name for col, name in kinds.items() if yes(r.get(col))) or "-"


def flag_col(kinds: Mapping[str, str]) -> Col:
    return Col("", "확인 근거", flag_kinds(kinds), tip=lambda r: str(r.get("why") or ""),
               head_tip="왜 확인 필요인지. 칸에 마우스를 올리면 쉬운 설명.")


@dataclass(frozen=True)
class Review:
    file: str
    tip: str
    figure_title: str
    figure_how: str
    cols: Callable[[Namer], list[Col]]


REVIEWS = {
    "loq": Review("loq_review.csv", "LoQ 아래·근처 ITEM 을 원데이터로 다시 본 결과. 확인 필요는 die 대부분이 한 방향으로 "
                  "움직였거나(방향) 일부 die만 크게 벗어난(꼬리) ITEM 이다. 참고 표시이고 판정은 그대로다.",
                  "LoQ 재확인 지도", LOQ_MAP_HOW_TO_READ, lambda namer: [
        *id_cols("loq_review.csv", "items.csv", namer),
        Col("loq_review.csv", "verdict_final", lambda r: r.get("verdict_final") or "-",
            tip=lambda r: f"구간 {r.get('zone') or '-'}"),
        flag_col({"flag_direction": "방향", "flag_tail": "꼬리"}),
        Col("", "방향", lambda r: f"↑{plain_num(r.get('n_up'))} ↓{plain_num(r.get('n_down'))}",
            head_tip="DOE 가 높아진 die 수 ↑, 낮아진 die 수 ↓"),
        Col("loq_review.csv", "ratio", ratio_text, tip=ratio_tip),
        Col("loq_review.csv", "tail_frac", lambda r: share(r.get("tail_frac")))]),
    "log": Review("log_review.csv", "log 로 판정한 ITEM 과 log 대상 ITEM 을 선형과 나란히 본 결과. 확인 필요는 선형으로 "
                  "차이인데 log 로 동등이 됐거나 log 값에서 일부 die만 크게 벗어난 ITEM 이다. 참고 표시이고 판정은 그대로다.",
                  "log 재확인: 선형과 log 나란히", LOG_MAP_HOW_TO_READ, lambda namer: [
        *id_cols("log_review.csv", "items.csv", namer),
        Col("", "선형 → log 판정", lambda r: f"{r.get('verdict') or '-'} → {r.get('verdict_log') or '-'}",
            tip=lambda r: f"최종 판정 {r.get('verdict_final') or '-'}",
            head_tip="같은 ITEM 을 선형 값과 log 값으로 판정한 결과"),
        flag_col({"log_overrode_diff": "log 가 차이를 동등으로", "flag_tail": "꼬리"}),
        Col("log_review.csv", "shift_pct", lambda r: pct(r.get("shift_pct"), 100),
            tip=lambda r: f"허용폭 ±{pct(r.get('delta_pct'), 100).lstrip('+')}"),
        Col("log_review.csv", "shift_log_pct", lambda r: pct(r.get("shift_log_pct"), 100),
            tip=lambda r: f"허용폭 ±{pct(r.get('delta_log_pct'), 100).lstrip('+')}"),
        Col("log_review.csv", "tail_frac", lambda r: share(r.get("tail_frac")))]),
}


def review_section(page: Page, folder: Path, which: str, sec: Section) -> None:
    r = REVIEWS[which]
    path = folder / "review" / r.file
    if not path.is_file():
        page.skipped(f"review/{r.file}")
        return
    table = read_csv(path)
    flagged = true_rows(table, "flag")
    sec.badge = f"{len(flagged):,}"
    page.lede(f"대상 {len(table):,}개 중 확인 필요 {len(flagged):,}개 · 판정은 그대로")
    if not flagged.empty:
        page.table(r.cols(page.namer), flagged.to_dict("records"))
    if len(table):
        page.figure(Figure(folder / "review" / f"{which}_review.png", r.figure_title, names=True, how=r.figure_how))
    drawn = [i for i in flagged["ITEM"].astype(str) if review_figure(folder, i).is_file()]
    shown = min(len(drawn), REVIEW_FIGURES)
    for item in drawn[:shown]:
        page.figure(Figure(review_figure(folder, item), f"{page.namer.label(item)} · 확인 필요 상세", names=True,
                           how=ITEM_HOW_TO_READ))
    if len(flagged) > shown:
        page.p(f"상세 그림은 근거가 센 {shown:,}개만 싣는다 (확인 필요 {len(flagged):,}개, 그린 그림 {len(drawn):,}장은 "
               "review/items/, 그릴 수는 review.py --max-figures).", "note")


STABILITY_FORMATS = {**{c: share for c in ("share_stable", "share_caution", "share_unstable", "share_no_band",
                                           "share_over_3x")}, "flagged": lambda v: "예" if yes(v) else "아니오",
                     **{c: precision_pct for c in ("meas_precision_pct_median", "meas_precision_pct_p90",
                                                   "rsd_pct_median", "rsd_pct_p90")}}
KV_COLS = [Col("", "항목", lambda r: r["name"], tip=lambda r: r["meaning"]), Col("", "값", lambda r: r["value"])]


def kv_rows(kind: str, row: Mapping, render: Callable[[str, object], str]) -> list[dict]:
    """한 행짜리 결과를 (쉬운이름, 값, 뜻) 세로 표로. 뜻은 이름 칸 풍선."""
    out = []
    for col, v in row.items():
        doc = columns_doc.doc_for(kind, col)
        out.append({"name": doc.easy_name if doc and doc.easy_name else col, "value": render(col, v),
                    "meaning": doc.meaning if doc else ""})
    return out


def level_section(page: Page, folder: Path) -> None:
    """그룹 × LEVEL 측정 정밀도 열지도 (stability/group_levels.png)."""
    if not page.figure(Figure(folder / "stability" / "group_levels.png", "그룹 × LEVEL 측정 정밀도 (중앙값)",
                              names=False, how=LEVEL_HOW_TO_READ)):
        page.p("그룹 × LEVEL 측정 정밀도는 판정할 때 level 파일(--level, 조합의 level 키)을 주면 그린다.", "note")


def stability_section(page: Page, folder: Path) -> None:
    d = folder / "stability"
    if not d.is_dir():
        page.skipped("stability/ 폴더")
        return
    overall = d / "overall.csv"
    if overall.is_file():
        o = read_csv(overall).iloc[0]
        cards(page, [("안정", share(o.get("share_stable")), "판정력 0.5 이하"),
                     ("주의", share(o.get("share_caution")), "0.5~0.8"),
                     ("불안정", share(o.get("share_unstable")), "0.8 초과"),
                     ("측정 정밀도 중앙값", precision_pct(o.get("meas_precision_pct_median")), "값 대비 측정 흔들림 %")])
    level_section(page, folder)
    page.figure(Figure(d / "stability.png", "die·회차 안정도", names=False, how=STABILITY_HOW_TO_READ))
    dies = d / "dies.csv"
    if dies.is_file():
        t = read_csv(dies)
        hit = true_rows(t, "flagged")
        page.lede(f"흔들리는 die {len(hit):,}개 / {len(t):,}개 (die 흔들림 배수 1.5 이상이거나 튀는 ITEM 비율 20% 이상)")
        if not hit.empty:
            page.table(csv_cols("stability/dies.csv", [c for c in t.columns if c != "flagged"], STABILITY_FORMATS),
                       hit.to_dict("records"))
    tables = [(name, d / f"{name}.csv") for name in ("overall", "groups", "runs")]
    if any(path.is_file() for _, path in tables):
        with page.fold("숫자 표 (전체 · 그룹별 · POR 회차)"):
            number_tables(page, tables)


def number_tables(page: Page, tables: list[tuple[str, Path]]) -> None:
    for name, path in tables:
        if not path.is_file():
            continue
        t = read_csv(path)
        page.h3({"overall": "전체", "groups": "그룹별", "runs": "POR 회차"}[name])
        kind = f"stability/{name}.csv"
        if name == "overall":
            page.table(KV_COLS, kv_rows(kind, t.iloc[0].to_dict(), lambda c, v: STABILITY_FORMATS.get(c, plain_num)(v)))
        else:
            page.table(csv_cols(kind, t.columns, STABILITY_FORMATS), t.to_dict("records"))


def how_to_read(page: Page) -> None:
    page.add('<ul class="lines">' + "".join(f"<li>{page.namer.text(s)}</li>" for s in HOW_TO_READ) + "</ul>")
    page.columns_link()
    page.glossary()


def judge_report(folder: Path, items: pd.DataFrame, namer: Namer, book: loq_check.LoqBook) -> Path:
    page = Page(f"판정 리포트 · {folder.name}", namer, folder / namer.report_file,
                subtitle=f"ITEM {len(items):,}개 · POR 대 DOE")
    with page.section("kpi", "한눈에", HOW_TO_READ[0], open=True):
        kpi(page, items)
        loq_block(page, book)
    with page.section("map", "판정 지도", open=True):
        hidden = page.hidden_figures
        if not page.figure(Figure(folder / "plots" / "summary.png", "정규화 변화량 × 정규화 불확실성", names=True,
                                  how=MAP_HOW_TO_READ)):
            page.skipped("그림 파일")
        loq = Figure(folder / "plots" / "summary_loq.png", "DOE 수준 × 정규화 변화량", names=True, how=LOQ_HOW_TO_READ)
        if page.namer.anon:
            page.figure(loq)
        elif loq.path.is_file():
            with page.fold("LoQ 아래 ITEM 지도"):
                page.figure(loq)
        if page.hidden_figures > hidden:
            page.p(f"{ANON_FIGURE_NOTE}.", "note")
    with page.section("problems", "차이·미결", "차이 먼저, 그 안에서는 신뢰구간 끝이 허용폭을 많이 넘는 순 "
                      "(|정규화 변화량| + 정규화 불확실성). 판정 칸에 마우스를 올리면 판정 이유.", open=True) as sec:
        problems(page, items, sec)
    with page.section("excluded", "판정 제외", "계산할 수 없어 판정에서 뺀 ITEM. 같은 사유끼리 모았다.") as sec:
        excluded(page, items, sec)
    with page.section("loq", "LoQ 확인 필요", REVIEWS["loq"].tip) as sec:
        review_section(page, folder, "loq", sec)
    with page.section("log", "log 확인 필요", REVIEWS["log"].tip) as sec:
        review_section(page, folder, "log", sec)
    with page.section("stability", "측정 안정도", "같은 die 를 POR 로 다시 쟀을 때 얼마나 같게 나오나 (참고, 판정에 안 씀)."):
        stability_section(page, folder)
    with page.section("logrun", "log 허용폭 두 방식", LOG_RUN_TIP):
        log_run_compare(page, items)
    with page.section("how", "읽는 법"):
        how_to_read(page)
    return page.write()


# ── ITEM 리포트 ─────────────────────────────────────────────────────────────

EVIDENCE_VALUE_COLS = ("center", "ci_low", "ci_high", "ci_low_d", "ci_high_d", "delta", "policy_margin",
                       "run_margin", "accuracy_margin")
EVIDENCE_SIGNED = ("center", "ci_low", "ci_high", "ci_low_d", "ci_high_d")
EVIDENCE_SKIP = ("ITEM", "ID", "verdict_final", "verdict_basis", "reason_plain")


def evidence_rows(ev: Mapping, unit: str) -> list[dict]:
    linear = ev.get("d_scale") != "log"

    def render(col: str, v) -> str:
        if col == "LoQ" or (linear and col in EVIDENCE_VALUE_COLS):
            return fmt(v, unit, signed=col in EVIDENCE_SIGNED)
        return plain_num(v)
    return kv_rows("item_evidence", {k: v for k, v in ev.items() if k not in EVIDENCE_SKIP}, render)


def item_folders(item_dir: Path) -> list[Path]:
    index = item_dir / "items_index.csv"
    if index.is_file():
        t = read_csv(index)
        if "폴더" in t:
            return [item_dir / f for f in t["폴더"].dropna()]
    return sorted(p.parent for p in item_dir.glob("items/*/summary.csv"))


def item_card(page: Page, d: Path, n: int) -> bool:
    """ITEM 하나: 접는 카드 (제목 = 판정, 첫 줄 = 이유, 한 장 그림, 근거 숫자는 한 번 더 접음). 첫 카드만 펼친다."""
    summary = d / "summary.csv"
    if not summary.is_file():
        return False
    namer = page.namer
    row = read_csv(summary).iloc[0].to_dict()
    ev_path = d / "evidence.csv"
    ev = read_csv(ev_path).iloc[0].to_dict() if ev_path.is_file() else {}
    up, down = (int(num(ev[k])) if math.isfinite(num(ev.get(k))) else None for k in ("n_d_pos", "n_d_neg"))
    item = str(row.get("ITEM"))
    lines = explain.verdict_card(row, up, down)
    head = lines[0] + ("" if namer.anon else f" · {namer.id_of.get(item, '-')}")
    reason = [line for line in lines[1:] if line.startswith("→ ")]
    detail = [line for line in lines[1:] if not line.startswith("→ ")]
    final = str(row.get("verdict_final") or row.get("verdict") or "")
    page.add(f'<details class="item" id="item-{n}"{" open" if n == 1 else ""}><summary>'
             f'<span class="dot {namer.text(final)}"></span>{namer.text(head)}</summary>')
    for line in reason:
        page.lede(line.removeprefix("→ "))
    page.figure(Figure(d / "item_view.png", f"{namer.label(item)} 한 장 보기", names=True, how=ITEM_VIEW_HOW_TO_READ))
    with page.fold("근거 숫자"):
        page.add('<ul class="lines">' + "".join(f"<li>{namer.text(line)}</li>" for line in detail) + "</ul>")
        if ev:
            page.table(KV_COLS, evidence_rows(ev, unit_of(row)))
        else:
            page.skipped("evidence.csv (원데이터 없이 만든 ITEM 폴더)")
    page.add("</details>")
    return True


def item_report(folder: Path, namer: Namer) -> Path | None:
    item_dir = folder / "item"
    if not item_dir.is_dir():
        return None
    folders = item_folders(item_dir)
    page = Page(f"ITEM 리포트 · {folder.name}", namer, item_dir / namer.report_file,
                subtitle="ITEM 마다 판정, 이유, 한 장 그림, 근거 숫자")
    with page.section("forest", "ITEM 별 변화량", open=True):
        if not page.figure(Figure(item_dir / "forest.png", "ITEM 별 변화량과 허용폭", names=True,
                                  how=FOREST_HOW_TO_READ)):
            page.skipped("forest.png")
    with page.section("items", "ITEM 카드", "카드를 펼치면 판정 이유, ITEM 한 장 그림, 근거 숫자가 나온다.",
                      open=True) as sec:
        shown = sum(item_card(page, d, n) for n, d in enumerate(folders, 1))
        sec.badge = f"{shown:,}"
        if not shown:
            page.skipped("ITEM 폴더")
    page.columns_link()
    return page.write()


# ── 그룹 리포트 ─────────────────────────────────────────────────────────────

def group_rows(items: pd.DataFrame, group_of: Mapping[str, str], namer: Namer) -> list[dict]:
    from stability import UNGROUPED, by_group
    base = by_group(items, dict(group_of))
    group = items["ITEM"].astype(str).str.strip().map(group_of).fillna(UNGROUPED)
    rows = []
    for rec in base.to_dict("records"):
        mine = items[group == rec["group"]]
        counts = mine["verdict_final"].value_counts()
        worst = [r for r in by_severity(mine) if r.get("verdict_final") in SEVERE][:WORST_PER_GROUP]
        rows.append({**rec, **{f"n_{v}": int(counts.get(v, 0)) for v in VERDICT_ORDER},
                     "worst": ", ".join(f"{namer.label(r['ITEM'])} ({r['verdict_final']})" for r in worst) or "-"})
    return rows


def group_table_cols() -> list[Col]:
    kind = "stability/groups.csv"
    return [Col(kind, "group", lambda r: r["group"]), Col(kind, "n_items"),
            *(Col("", v, lambda r, v=v: f"{r[f'n_{v}']:,}") for v in VERDICT_ORDER),
            Col(kind, "meas_precision_pct_median", lambda r: precision_pct(r["meas_precision_pct_median"])),
            Col("", "가장 나쁜 ITEM", lambda r: r["worst"],
                head_tip="차이·미결 중 신뢰구간 끝이 허용폭을 많이 넘는 순으로 셋")]


def group_report(folder: Path, items: pd.DataFrame, namer: Namer, groups: Path | None) -> Path | None:
    group_dir = folder / "group"
    if not group_dir.is_dir():
        return None
    page = Page(f"그룹 리포트 · {folder.name}", namer, group_dir / namer.report_file,
                subtitle=f"ITEM {len(items):,}개")
    if (folder / "compare" / namer.report_file).is_file():
        page.link("기존·개선 비교는 compare 리포트에 있다", f"../compare/{namer.report_file}")
    with page.section("groups", "그룹별 표", "그룹마다 판정 개수, 측정 정밀도 중앙값, 가장 나쁜 ITEM.", open=True):
        if groups is not None and groups.is_file():
            from infra_compare import read_groups
            g = read_groups(groups)
            page.table(group_table_cols(), group_rows(items, dict(zip(g["ITEM"], g["group"])), namer))
        elif (folder / "stability" / "groups.csv").is_file():
            t = read_csv(folder / "stability" / "groups.csv")
            page.p("그룹 파일(--groups)을 주지 않아 그룹별 판정 개수는 없다. 판정할 때 만든 그룹별 정밀도만 싣는다.", "note")
            page.table(csv_cols("stability/groups.csv", ("group", "n_items", "meas_precision_pct_median"), STABILITY_FORMATS),
                       t.to_dict("records"))
        else:
            page.p("그룹별 표는 그룹 파일이 있어야 만든다: python report.py <폴더> --groups ITEM,그룹 파일.", "note")
    with page.section("levels", "그룹 × LEVEL 측정 정밀도", open=True):
        level_section(page, folder)
    with page.section("figures", "그룹 그림"):
        page.figures([Figure(p, f"그룹 {p.stem.removeprefix('summary_group_')}", names=True, how=MAP_HOW_TO_READ)
                      for p in sorted((group_dir / "plots").glob("summary_group_*.png"))])
    with page.section("how", "열 뜻"):
        page.columns_link()
        page.glossary()
    return page.write()


# ── 기존·개선 비교 리포트 ─────────────────────────────────────────────────────

COMPARE_FIGURES = {          # compare_metrics 그림: 파일 → (제목, ITEM 이름이 그려짐)
    "meas_precision_ratio.png": ("측정 정밀도 비 (개선/기존)", True),
    "sigma_die_ratio.png": ("반복성 σ_die 비 (개선/기존)", True),
    "sigma_run_ratio.png": ("회차 이동 σ_run 비 (개선/기존)", True),
    "stability_meas_precision_pct.png": ("측정 정밀도 % 분포: 기존 대 개선", False),
    "stability_sigma_die_pct.png": ("반복성 % 분포: 기존 대 개선", False),
    "verdict_center_delta.png": ("이동량 ÷ 허용폭 분포: 기존 대 개선", False),
}
WORSENED_SHOWN = 30


def frame_cols(table: pd.DataFrame, tips: Mapping[str, str] = compare_book.TIPS) -> list[Col]:
    """시트 표 (compare_book, loq_check) 의 열. 머리글 풍선은 tips, 판단 칸은 색."""
    def col(c: str) -> Col:
        tip = tips.get(c) or next((t for k, t in tips.items() if c.endswith(" " + k)), "")
        trend = c == "판단"
        return Col("", c, lambda r, c=c: plain_num(r.get(c)) if not isinstance(r.get(c), str) else r.get(c),
                   item_name=c == "ITEM", head_tip=tip, cls=(lambda r: str(r.get("판단") or "")) if trend else None)
    return [col(c) for c in table.columns]


def frame(page: Page, table: pd.DataFrame, limit: int | None = None,
          tips: Mapping[str, str] = compare_book.TIPS) -> None:
    rows = table.to_dict("records")
    page.table(frame_cols(table, tips), rows[:limit] if limit else rows)


def compare_report(folder: Path, namer: Namer) -> Path | None:
    """compare/report.html 과 compare/비교.xlsx (익명이면 report_anon.html, 비교_anon.xlsx)."""
    cdir = folder / "compare"
    if not (cdir / "scope.csv").is_file():
        return None
    c = compare_book.load(cdir)
    sheets = compare_book.sheets(c, lambda item: namer.id_of.get(str(item), "ID 없음"), names=not namer.anon)
    book = simple_xlsx.write(cdir / (compare_book.WORKBOOK_ANON if namer.anon else compare_book.WORKBOOK), sheets)
    tables = {name: table for name, table, _ in sheets}
    page = Page(f"기존·개선 비교 · {folder.name}", namer, cdir / namer.report_file,
                subtitle=f"ITEM {int(c.scope['n_compared']):,}개 비교 · 같은 표는 {book.name}")
    with page.section("summary", "요약", compare_book.RULE, open=True):
        page.add(f'<p class="headline">{namer.text(compare_book.conclusion(c))}</p>')
        page.lede(compare_book.scope_line(c.scope))
        frame(page, tables[compare_book.SUMMARY])
        page.p(compare_book.RULE, "note")
    if compare_book.GROUPS in tables:
        with page.section("groups", "그룹별", "측정 정밀도 비가 작은(많이 좋아진) 그룹부터. 맨 위는 전체.", open=True):
            frame(page, tables[compare_book.GROUPS])
    with page.section("verdicts", "판정 변화", "기존 판정 → 개선 판정 ITEM 수. 판정 제외도 센다.") as sec:
        verdicts = tables[compare_book.VERDICTS]
        moved = verdicts[verdicts["변화 종류"] != compare_book.SHIFTS[-1]]
        sec.badge = f"바뀜 {int(moved[compare_book.TOTAL].sum()):,}"
        frame(page, verdicts)
        items = tables[compare_book.ITEMS]
        changed = items[items["기존 판정"] != items["개선 판정"]]
        if len(changed):
            with page.fold(f"판정이 바뀐 ITEM {len(changed):,}개"):
                frame(page, changed[[k for k in changed.columns if k in ("ID", "ITEM", "그룹", "기존 판정", "개선 판정")
                                     or k.startswith("측정 정밀도")]])
    if c.grouped:
        with page.section("levels", "그룹 × LEVEL", compare_book.LEVELS_SOURCE):
            if compare_book.LEVELS in tables:
                frame(page, tables[compare_book.LEVELS])
            else:
                page.p(compare_book.LEVELS_NOTE, "note")
    with page.section("worse", "나빠진 ITEM", f"측정 정밀도 비가 {1 + compare_book.TREND_BAND:.1f} 넘는 ITEM, "
                      "비 큰 순.") as sec:
        worse = tables[compare_book.WORSENED]
        sec.badge = f"{len(worse):,}"
        if worse.empty:
            page.p("측정 정밀도가 나빠진 ITEM 이 없다.", "note")
        else:
            frame(page, worse, WORSENED_SHOWN)
            if len(worse) > WORSENED_SHOWN:
                page.p(f"비 큰 {WORSENED_SHOWN}개만 싣는다. 전부는 {book.name} 의 {compare_book.WORSENED} 시트.", "note")
    with page.section("figures", "그림"):
        groups_dir = cdir / "groups"
        page.figures([*(Figure(cdir / f, t, n) for f, (t, n) in COMPARE_FIGURES.items()),
                      *(Figure(groups_dir / f, f"그룹별 {t}", False) for f, (t, _) in COMPARE_FIGURES.items()
                        if c.grouped)])
    with page.section("how", "열 뜻"):
        page.link(f"같은 표 엑셀: {book.name}", book.name)
        used = sorted({k for t in tables.values() for k in t.columns if k in compare_book.TIPS})
        page.table([Col("", "열", lambda r: r["k"]), Col("", "뜻", lambda r: r["v"])],
                   [{"k": k, "v": compare_book.TIPS[k]} for k in used])
        page.columns_link()
    return page.write()


# ── LoQ 리포트 ──────────────────────────────────────────────────────────────

LOQ_ITEMS_SHOWN = 100


def loq_report(folder: Path, namer: Namer, book: loq_check.LoqBook) -> Path | None:
    """loq/report.html 과 loq/LoQ.xlsx (익명이면 report_anon.html, LoQ_anon.xlsx). loq/ 가 없으면 None."""
    if book.check is None:
        return None
    ldir = folder / loq_check.LOQ_DIR
    sheets = book.sheets(lambda item: namer.id_of.get(str(item), "ID 없음"), names=not namer.anon)
    xlsx = simple_xlsx.write(ldir / (loq_check.WORKBOOK_ANON if namer.anon else loq_check.WORKBOOK), sheets)
    tables = {name: table for name, table, _ in sheets}
    g, c = book.summary.ledger, book.check
    page = Page(f"LoQ 리포트 · {folder.name}", namer, ldir / namer.report_file,
                subtitle=f"LoQ 아래 ITEM {g.n_zone:,}개 · 판정은 그대로 · 같은 표는 {xlsx.name}")
    lines = book.headline_lines()
    items = tables[loq_check.ITEMS_SHEET]
    with page.section("answer", "한 줄 답", LOQ_BLOCK_TIP, open=True):
        null, high = c.at("final", loq_check.NO_CHANGE), c.at("final", 1.5)
        cards(page, [("LoQ 아래 ITEM", f"{g.n_zone:,}", f"전체 {g.n_total:,}개 중"),
                     ("LoQ 규칙으로 동등", f"{g.rule_pass:,}",
                      f"보통 TOST 였다면 차이 {g.rule_tost['차이']:,}·미결 {g.rule_tost['미결']:,}"
                      + ("" if g.rule_flagged is None else f" · 재확인 확인 필요 {g.rule_flagged:,}")),
                     ("변화 없음에서 잡힘", share(null.rate), f"시험한 ITEM {c.n_items:,}개 · 비교 {null.n:,}번"),
                     ("DOE 1.5×LoQ 에서 잡힘", share(high.rate), f"비교 {high.n:,}번")])
        page.add('<ul class="lines">' + "".join(f"<li>{namer.text(s)}</li>" for s in lines) + "</ul>")
        for question, answer in book.answers():
            page.h3(question)
            page.p(answer)
    with page.section("reasons", "동등이 된 이유", "한계 영역을 전부 통과시켰나? LoQ 아래 ITEM 이 어떻게 동등이 됐나.",
                      open=True):
        page.lede(lines[1])
        if page.figure(Figure(book.reasons, "동등이 된 이유 (구간별)", names=False, how=loq_check.REASONS_HOW_TO_READ)):
            page.p(loq_check.REASONS_HOW_TO_READ, "note")
        frame(page, tables[loq_check.REASONS], tips=loq_check.TIPS)
    with page.section("trials", "시험 결과 (POR 회차로 만든 비교)",
                      "진짜 변한 것을 놓치나? 안 변한 것을 걸리게 하나? 답을 아는 비교로 본다.", open=True):
        if c.n_items:
            page.lede(loq_check.curve_note(c))
        if page.figure(Figure(book.curve, "DOE 수준별 잡힌 비율", names=False, how=loq_check.CURVE_HOW_TO_READ)):
            page.p(loq_check.CURVE_HOW_TO_READ, "note")
        levels = tables[loq_check.LEVELS_SHEET]
        shown = book.levels["level"].isin(loq_check.REVIEW_LEVELS).to_numpy()
        frame(page, levels[shown], tips=loq_check.TIPS)
        page.p(f"0.1~3배 모든 수준은 {xlsx.name} 의 {loq_check.LEVELS_SHEET} 시트, 비교 하나하나는 "
               f"loq/{loq_check.TRIALS_CSV} (변화 없음과 위 수준).", "note")
        never = items[items["잡히는 수준 ×LoQ"] == "inf"]
        if len(never):
            with page.fold(f"DOE 를 LoQ 의 3배까지 올려도 회차 비교가 다 잡히지는 않는 ITEM {len(never):,}개"):
                frame(page, never, LOQ_ITEMS_SHOWN, tips=loq_check.TIPS)
    with page.section("items", "LoQ 규칙·판정 길로 동등이 된 ITEM",
                      "LoQ 규칙이나 판정 길로 동등이 된 ITEM. 재확인 확인 필요 먼저, 그다음 잡히는 수준이 POR 의 몇 배인지 "
                      "큰 순.") as sec:
        rule = items[items["동등 이유"].isin(loq_check.LISTED)]
        sec.badge = f"{len(rule):,}"
        if rule.empty:
            page.p("LoQ 규칙이나 판정 길로 동등이 된 ITEM 이 없다.", "note")
        else:
            frame(page, rule, LOQ_ITEMS_SHOWN, tips=loq_check.TIPS)
            if len(rule) > LOQ_ITEMS_SHOWN:
                page.p(f"앞의 {LOQ_ITEMS_SHOWN}개만 싣는다. 전부는 {xlsx.name} 의 {loq_check.ITEMS_SHEET} 시트.", "note")
    with page.section("loq", "LoQ 확인 필요", REVIEWS["loq"].tip) as sec:
        review_section(page, folder, "loq", sec)
    with page.section("method", "방법과 한계"):
        page.h3("만든 비교")
        page.add('<ul class="lines">' + "".join(f"<li>{namer.text(s)}</li>" for s in loq_check.METHOD_LINES) + "</ul>")
        page.h3("치우침과 그 방향")
        page.add('<ul class="lines">' + "".join(f"<li>{namer.text(s)}</li>" for s in book.bias_lines()) + "</ul>")
        if c.untested:
            page.p("시험 못 한 ITEM: " + ", ".join(f"{k} {n:,}개" for k, n in c.untested.items()) + ".", "note")
        page.link(f"같은 표 엑셀: {xlsx.name}", xlsx.name)
        page.columns_link()
        page.glossary()
    return page.write()


# ── 진입점 ─────────────────────────────────────────────────────────────────

def write_reports(folder, anon: bool = False, groups=None) -> list[Path]:
    """folder (<out>/<이름>) 의 결과 파일로 report.html, item/report.html, compare/report.html(+ 비교.xlsx),
    group/report.html, loq/report.html(+ LoQ.xlsx) 을 쓴다. item/·compare/·group/·loq/ 이 없으면 그 리포트는 건너뛴다.
    쓴 리포트 목록을 돌려준다."""
    folder = Path(folder)
    items_csv = folder / "items.csv"
    if not items_csv.is_file():
        raise FileNotFoundError(f"{items_csv} 가 없습니다 (먼저 dcc.py judge 로 판정하세요)")
    items = read_csv(items_csv)
    namer = Namer(items, anon)
    book = loq_check.load(folder)
    written = [judge_report(folder, items, namer, book), item_report(folder, namer), compare_report(folder, namer),
               group_report(folder, items, namer, Path(groups) if groups else None), loq_report(folder, namer, book)]
    return [p for p in written if p is not None]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="조합 결과 폴더 (<out>/<이름>, items.csv 가 있는 곳)")
    ap.add_argument("--anon", action="store_true", help="ITEM 이름 대신 익명 ID 만 (밖으로 공유할 때)")
    ap.add_argument("--groups", help="ITEM,그룹 파일. 주면 group/report.html 에 그룹별 판정 개수 표")
    a = ap.parse_args(argv)
    try:
        paths = write_reports(a.folder, anon=a.anon, groups=a.groups)
    except FileNotFoundError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    for p in paths:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
