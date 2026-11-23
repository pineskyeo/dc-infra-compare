"""조합 하나의 결과 폴더를 웹브라우저로 여는 리포트로 만든다 (설계 1-9). 폴더에 이미 있는 결과 파일만 읽는다.
그림은 파일 안에 넣고(base64 PNG) 외부 주소를 부르지 않아 인터넷 없이 열리고 메일로 보내도 깨지지 않는다.

  python report.py <out>/<이름> [--anon] [--groups ITEM,그룹 파일]

  <폴더>/report.html         판정: 판정별 개수, 판정 지도, 차이·미결 표, 판정 제외, LoQ·log 확인 필요, 측정 안정도
  <폴더>/item/report.html    item/ 이 있으면: ITEM 마다 판정 카드, ITEM 한 장 그림, 근거 숫자
  <폴더>/group/report.html   group/ 이 있으면: 그룹별 표, 그룹 그림, 기존·개선 비교 표

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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import columns_doc
import explain
from explain import BASIS_NAMES, LOQ_ZONES, V_EXCLUDED, fmt, pct

COLUMNS_PAGE = Path(__file__).resolve().parent / "docs" / "sop" / "columns.html"
VERDICT_ORDER = ("차이", "미결", "동등", V_EXCLUDED)
SEVERE = ("차이", "미결")
WORST_PER_GROUP = 3
ANON_FIGURE_NOTE = "익명 리포트라 ITEM 이름이 그려진 그림은 넣지 않았다"


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
    v = num(x)
    return f"{100 * v:.0f}%" if math.isfinite(v) else "-"


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
    """표 한 열. 머리글은 열 사전(kind 결과 파일의 column)의 쉬운이름, kind 가 빈 칸이면 column 그대로.
    get 은 행 → 칸 글자 (없으면 column 값을 숫자로)."""
    kind: str
    column: str
    get: Callable[[Mapping], str] | None = None
    item_name: bool = False      # 실제 ITEM 이름 열 (익명이면 뺀다)

    def cell(self, row: Mapping) -> str:
        return self.get(row) if self.get else plain_num(row.get(self.column))


def csv_cols(kind: str, columns: Iterable[str], formats: Mapping[str, Callable] | None = None) -> list[Col]:
    formats = formats or {}
    return [Col(kind, c, (lambda r, c=c, f=formats[c]: f(r.get(c))) if c in formats else None) for c in columns]


@dataclass(frozen=True)
class Figure:
    path: Path
    title: str
    names: bool                  # ITEM 이름이 그림 안에 그려져 있음


@dataclass
class Page:
    title: str
    namer: Namer
    out: Path
    parts: list[str] = field(default_factory=list)
    used: dict[tuple[str, str], columns_doc.ColumnDoc] = field(default_factory=dict)
    hidden_figures: int = 0

    def add(self, html_text: str) -> None:
        self.parts.append(html_text)

    def h2(self, text: str, anchor: str) -> None:
        self.add(f'<h2 id="{anchor}">{self.namer.text(text)}</h2>')

    def p(self, text: str, cls: str = "") -> None:
        self.add(f'<p{f" class={cls!r}" if cls else ""}>{self.namer.text(text)}</p>')

    def skipped(self, what: str) -> None:
        self.p(f"{what} 없음. 이 칸은 건너뛴다.", "note")

    def header(self, col: Col) -> tuple[str, str]:
        doc = columns_doc.doc_for(col.kind, col.column) if col.kind else None
        if doc is None:
            return col.column, ""
        self.used[(doc.easy_name or col.column, doc.meaning)] = doc
        name = doc.easy_name if doc.column == col.column and doc.easy_name else col.column
        return name, doc.meaning

    def table(self, cols: list[Col], rows: Iterable[Mapping]) -> None:
        rows = list(rows)
        if not rows:
            self.p("해당 행 없음.")
            return
        cols = [c for c in cols if not (self.namer.anon and c.item_name)]
        heads = "".join(f'<th title="{self.namer.text(m)}">{self.namer.text(n)}</th>'
                        for n, m in map(self.header, cols))
        body = "".join("<tr>" + "".join(f"<td>{self.namer.text(c.cell(r))}</td>" for c in cols) + "</tr>"
                       for r in rows)
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
        self.add(f'<figure><img alt="{title}" src="data:image/png;base64,{data}"><figcaption>{title}</figcaption>'
                 "</figure>")
        return True

    def figures(self, figs: Iterable[Figure]) -> None:
        if not sum(self.figure(f) for f in figs):
            self.skipped("그림 파일")

    def html(self) -> str:
        notes = (f'<p class="note">{ANON_FIGURE_NOTE} ({self.hidden_figures}장).</p>'
                 if self.hidden_figures else "")
        return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">'
                f"<title>{self.namer.text(self.title)}</title><style>{CSS}</style></head><body>"
                f"<h1>{self.namer.text(self.title)}</h1>{notes}{''.join(self.parts)}</body></html>")

    def glossary(self) -> None:
        """이 쪽 표에 쓴 열의 뜻 (메일로 받아 열 사전 쪽이 없는 사람용)."""
        if not self.used:
            return
        rows = "".join(f"<tr><td>{self.namer.text(name)}</td><td>{self.namer.text(d.meaning)}</td>"
                       f"<td>{self.namer.text(d.look_for)}</td></tr>"
                       for (name, _), d in sorted(self.used.items()))
        self.add('<details><summary>이 리포트의 표에 쓴 열</summary><div class="wrap"><table><thead><tr><th>열</th>'
                 f"<th>뜻</th><th>볼 것</th></tr></thead><tbody>{rows}</tbody></table></div></details>")

    def columns_link(self) -> None:
        try:
            href = Path(os.path.relpath(COLUMNS_PAGE, self.out.parent)).as_posix()
        except ValueError:
            href = COLUMNS_PAGE.as_uri()
        self.add(f'<p>모든 열의 뜻·수식·볼 것은 열 사전 쪽에 있다: <a href="{html.escape(href)}">docs/sop/columns.html</a> '
                 "(dc-infra-compare 저장소 안).</p>")

    def write(self) -> Path:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(self.html(), encoding="utf-8")
        return self.out


CSS = """
:root{--fg:#1f2328;--muted:#59636e;--line:#d0d7de;--bg:#ffffff;--card:#f6f8fa;
--차이:#c8463d;--미결:#d08a1e;--동등:#3d8b54;--제외:#8c959f}
body{font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;color:var(--fg);
background:var(--bg);margin:0 auto;max-width:1200px;padding:16px;line-height:1.5;font-size:14px}
h1{font-size:22px;margin:8px 0 4px}h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid var(--line);
padding-bottom:4px}h3{font-size:15px;margin:18px 0 6px}
.note{color:var(--muted);font-size:13px}.wrap{overflow-x:auto}
table{border-collapse:collapse;font-size:13px;margin:6px 0}th,td{border:1px solid var(--line);padding:4px 6px;
text-align:left;vertical-align:top}th{background:var(--card);white-space:nowrap}
figure{margin:12px 0}img{max-width:100%;height:auto;border:1px solid var(--line)}figcaption{color:var(--muted);
font-size:13px}.cards{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}.card{background:var(--card);
border:1px solid var(--line);border-radius:6px;padding:8px 12px;min-width:110px}.card b{display:block;font-size:20px}
.card.차이{border-left:5px solid var(--차이)}.card.미결{border-left:5px solid var(--미결)}
.card.동등{border-left:5px solid var(--동등)}.card.판정.제외{border-left:5px solid var(--제외)}
.item{border:1px solid var(--line);border-radius:6px;padding:8px 12px;margin:14px 0}
.item p{margin:2px 0}nav a{margin-right:12px}
@media print{.wrap{overflow:visible}figure{break-inside:avoid}}
"""


def cards(page: Page, entries: Iterable[tuple[str, str, str]]) -> None:
    """(이름, 큰 숫자, 아래 작은 글) 카드 한 줄."""
    page.add('<div class="cards">' + "".join(
        f'<div class="card {page.namer.text(name)}">{page.namer.text(name)}<b>{page.namer.text(big)}</b>'
        f'<span class="note">{page.namer.text(small)}</span></div>' for name, big, small in entries) + "</div>")


def nav(page: Page, links: Iterable[tuple[str, str]]) -> None:
    page.add("<nav>" + "".join(f'<a href="#{a}">{page.namer.text(t)}</a>' for a, t in links) + "</nav>")


# ── 판정 리포트 ──────────────────────────────────────────────────────────────

def unit_of(row: Mapping) -> str:
    u = row.get("UNIT")
    return "" if u is None or (isinstance(u, float) and math.isnan(u)) else str(u)


def basis_of(row: Mapping) -> str:
    b = row.get("verdict_basis")
    return b if isinstance(b, str) and b else "linear"


def severity(row: Mapping) -> float:
    """신뢰구간 끝이 허용폭의 몇 배까지 가나 (최종 판정을 정한 척도로). 클수록 심하다."""
    suffix = "_log" if basis_of(row) in ("log", "log_physics") else ""
    lo, hi, d = (num(row.get(f"{k}{suffix}")) for k in ("ci_low", "ci_high", "delta"))
    if not (math.isfinite(lo) and math.isfinite(hi) and math.isfinite(d)) or d <= 0:
        return -math.inf
    return max(abs(lo), abs(hi)) / d


def by_severity(items: pd.DataFrame) -> list[dict]:
    rows = items.to_dict("records")
    return sorted(rows, key=lambda r: (VERDICT_ORDER.index(r["verdict_final"])
                                       if r.get("verdict_final") in VERDICT_ORDER else len(VERDICT_ORDER),
                                       -severity(r)))


def id_cols(kind: str, id_kind: str | None = None, namer: Namer | None = None) -> list[Col]:
    """익명 ID 와 ITEM 이름 두 열. id_kind 는 ID 열을 설명하는 결과 파일 (ID 열이 없는 파일이면 items.csv)."""
    get_id = (lambda r: namer.id_of.get(str(r.get("ITEM")), "-")) if namer else None
    return [Col(id_kind or kind, "ID", get_id), Col(kind, "ITEM", lambda r: str(r.get("ITEM")), item_name=True)]


def problem_cols(namer: Namer) -> list[Col]:
    return [
        *id_cols("items.csv", namer=namer),
        Col("items.csv", "verdict_final", lambda r: r["verdict_final"]),
        Col("items.csv", "verdict_basis", lambda r: BASIS_NAMES.get(basis_of(r), basis_of(r))),
        Col("item_evidence", "reason_plain", explain.reason_plain),
        Col("log_review.csv", "shift_pct",
            lambda r: "-" if r.get("zone") in LOQ_ZONES else pct(r.get("center"), r.get("por_median"))),
        Col("log_review.csv", "delta_pct", lambda r: pct(r.get("delta"), r.get("por_median")).lstrip("+")),
        *(Col("items.csv", c, lambda r, c=c: fmt(r.get(c), unit_of(r), signed=True)) for c in ("ci_low", "ci_high")),
        Col("items.csv", "status", lambda r: r.get("status") or "-"),
        Col("items.csv", "judgeability", lambda r: r.get("judgeability") or "-"),
    ]


def kpi(page: Page, items: pd.DataFrame, folder: Path) -> None:
    n = len(items)
    counts = items["verdict_final"].value_counts()
    page.p(f"ITEM {n:,}개")
    cards(page, [(v, f"{int(counts.get(v, 0)):,}", f"{100 * counts.get(v, 0) / n:.0f}%" if n else "")
                 for v in ("동등", "미결", "차이", V_EXCLUDED)])
    basis = items["verdict_basis"].fillna("linear").value_counts() if "verdict_basis" in items else pd.Series(dtype=int)
    page.p("최종 판정을 정한 방법별 ITEM 수:")
    cards(page, [(BASIS_NAMES.get(b, b), f"{int(c):,}", "") for b, c in basis.items()])
    overall = folder / "stability" / "overall.csv"
    if overall.is_file():
        o = read_csv(overall).iloc[0]
        page.p("측정 안정도 (판정력 = 신뢰구간 반폭 ÷ 허용폭):")
        cards(page, [("안정", share(o.get("share_stable")), "0.5 이하"),
                     ("주의", share(o.get("share_caution")), "0.5~0.8"),
                     ("불안정", share(o.get("share_unstable")), "0.8 초과"),
                     ("정밀도 중앙값", f"{plain_num(o.get('rsd_pct_median'))}%", "같은 die 다시 재면 흔들리는 %")])


def problems(page: Page, items: pd.DataFrame) -> None:
    rows = [r for r in by_severity(items) if r.get("verdict_final") in SEVERE]
    if not rows:
        page.p("차이·미결 ITEM 이 없다.")
        return
    page.p(f"{len(rows):,}개. 차이 먼저, 그 안에서는 이동량 범위 끝이 허용폭을 많이 넘는 순. "
           "%는 POR 중앙값 대비다.")
    page.table(problem_cols(page.namer), rows)


def excluded(page: Page, items: pd.DataFrame) -> None:
    rows = items[items["verdict_final"] == V_EXCLUDED].to_dict("records")
    if not rows:
        page.p("판정 제외 ITEM 이 없다.")
        return
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(explain.reason_plain(r), []).append(r)
    cols = [*id_cols("items.csv", namer=page.namer), Col("items.csv", "status", lambda r: r.get("status") or "-"),
            Col("items.csv", "n_die")]
    for reason, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        page.add(f"<h3>{page.namer.text(reason)} ({len(rs):,}개)</h3>")
        page.table(cols, rs)



def log_pct(v) -> str:
    """log 단위 허용폭·이동 → 배율 %. 0.0212 → +5.0%."""
    x = num(v)
    return f"{(10 ** x - 1) * 100:+.1f}%" if math.isfinite(x) else "-"


def log_run_compare(page: Page, items: pd.DataFrame) -> None:
    """verdict_final 과 verdict_final_log_run (log 허용폭만 선형 꼴로 고친 최종 판정) 이 다른 ITEM."""
    if "verdict_final_log_run" not in items:
        page.p("이 items.csv 에는 고친 log 허용폭 결과(verdict_final_log_run)가 없다. 지금 코드로 다시 판정하면 생긴다.",
               "note")
        return
    page.p("log 판정의 허용폭을 두 가지로 계산해 최종 판정을 나란히 놓았다. 지금 방식(delta_log)은 die를 다시 잴 때의 "
           "흔들림을 허용폭에 더하는데, 그 흔들림은 신뢰구간 폭에도 이미 들어 있어 두 번 세는 셈이다. 고친 방식"
           "(delta_log_run)은 선형 허용폭과 같은 꼴로 웨이퍼 공통 회차 흔들림만 더한다. 집계와 다른 표는 지금 방식"
           "(verdict_final)을 쓴다.")
    changed = items[items["verdict_final"].astype(str) != items["verdict_final_log_run"].astype(str)]
    if changed.empty:
        page.p("두 방식의 최종 판정이 같다. 바뀌는 ITEM 이 없다.")
        return
    pairs = changed.groupby(["verdict_final", "verdict_final_log_run"]).size()
    page.p(f"최종 판정이 바뀌는 ITEM {len(changed):,}개: "
           + ", ".join(f"{a} → {b} {n:,}개" for (a, b), n in pairs.items()) + ".")
    cols = [*id_cols("items.csv", namer=page.namer), Col("items.csv", "verdict_final", lambda r: r.get("verdict_final")),
            Col("items.csv", "verdict_final_log_run", lambda r: r.get("verdict_final_log_run")),
            Col("items.csv", "center_log", lambda r: log_pct(r.get("center_log"))),
            Col("items.csv", "ci_low_log", lambda r: log_pct(r.get("ci_low_log"))),
            Col("items.csv", "ci_high_log", lambda r: log_pct(r.get("ci_high_log"))),
            Col("items.csv", "delta_log", lambda r: log_pct(r.get("delta_log"))),
            Col("items.csv", "delta_log_run", lambda r: log_pct(r.get("delta_log_run")))]
    page.table(cols, changed.to_dict("records"))
    page.p("숫자는 log 값을 배율로 바꾼 %다 (+5.0% = POR의 1.05배).", "note")


REVIEW_ITEM_DIR = "items"


def review_figure(folder: Path, item: str) -> Path:
    from compare_metrics import safe_group_name
    return folder / "review" / REVIEW_ITEM_DIR / f"{safe_group_name(item)}.png"


def ratio_text(r: Mapping) -> str:
    v, lo, hi = (num(r.get(k)) for k in ("ratio", "ratio_lo", "ratio_hi"))
    if not math.isfinite(v):
        return "-"
    rng = f" ({lo:.3g}~{hi:.3g})" if math.isfinite(lo) and math.isfinite(hi) else ""
    return f"{v:.3g}배{rng}"


@dataclass(frozen=True)
class Review:
    file: str
    what: str
    figure_title: str
    cols: Callable[[Namer], list[Col]]


REVIEWS = {
    "loq": Review("loq_review.csv", "LoQ 아래·근처 ITEM 을 원데이터로 다시 본 결과 (판정은 그대로)",
                  "LoQ 재확인: 네 칸 그림에 확인 필요 표시", lambda namer: [
        *id_cols("loq_review.csv", "items.csv", namer),
        Col("loq_review.csv", "zone", lambda r: r.get("zone") or "-"),
        Col("loq_review.csv", "verdict_final", lambda r: r.get("verdict_final") or "-"),
        Col("loq_review.csv", "n_up"), Col("loq_review.csv", "n_down"),
        Col("loq_review.csv", "ratio", ratio_text),
        Col("loq_review.csv", "det_change", lambda r: pct(r.get("det_change"), 1)),
        Col("loq_review.csv", "tail_frac", lambda r: share(r.get("tail_frac"))),
        Col("loq_review.csv", "why", lambda r: r.get("why") or "")]),
    "log": Review("log_review.csv", "log 로 판정한 ITEM 과 log 대상 ITEM 을 선형과 나란히 본 결과 (판정은 그대로)",
                  "log 재확인: 선형과 log 나란히", lambda namer: [
        *id_cols("log_review.csv", "items.csv", namer),
        Col("log_review.csv", "verdict", lambda r: r.get("verdict") or "-"),
        Col("log_review.csv", "verdict_log", lambda r: r.get("verdict_log") or "-"),
        Col("log_review.csv", "verdict_final", lambda r: r.get("verdict_final") or "-"),
        Col("log_review.csv", "shift_pct", lambda r: pct(r.get("shift_pct"), 100)),
        Col("log_review.csv", "shift_log_pct", lambda r: pct(r.get("shift_log_pct"), 100)),
        Col("log_review.csv", "delta_pct", lambda r: pct(r.get("delta_pct"), 100).lstrip("+")),
        Col("log_review.csv", "delta_log_pct", lambda r: pct(r.get("delta_log_pct"), 100).lstrip("+")),
        Col("log_review.csv", "tail_frac", lambda r: share(r.get("tail_frac"))),
        Col("log_review.csv", "why", lambda r: r.get("why") or "")]),
}


def review(page: Page, folder: Path, which: str) -> None:
    r = REVIEWS[which]
    path = folder / "review" / r.file
    if not path.is_file():
        page.skipped(f"review/{r.file}")
        return
    table = read_csv(path)
    flagged = true_rows(table, "flag")
    page.p(f"{r.what}. 대상 {len(table):,}개 중 확인 필요 {len(flagged):,}개.")
    if not flagged.empty:
        page.table(r.cols(page.namer), flagged.to_dict("records"))
    if len(table):
        page.figure(Figure(folder / "review" / f"{which}_review.png", r.figure_title, names=True))
    for item in flagged["ITEM"].astype(str):
        page.figure(Figure(review_figure(folder, item), f"{page.namer.label(item)} 확인 필요 상세", names=True))


STABILITY_FORMATS = {**{c: share for c in ("share_stable", "share_caution", "share_unstable", "share_no_band",
                                           "share_over_3x")}, "flagged": lambda v: "예" if yes(v) else "아니오"}
KV_COLS = [Col("", "항목", lambda r: r["name"]), Col("", "값", lambda r: r["value"]), Col("", "뜻", lambda r: r["meaning"])]


def kv_rows(kind: str, row: Mapping, render: Callable[[str, object], str]) -> list[dict]:
    """한 행짜리 결과를 (쉬운이름, 값, 뜻) 세로 표로."""
    out = []
    for col, v in row.items():
        doc = columns_doc.doc_for(kind, col)
        out.append({"name": doc.easy_name if doc and doc.easy_name else col, "value": render(col, v),
                    "meaning": doc.meaning if doc else ""})
    return out


def stability(page: Page, folder: Path) -> None:
    d = folder / "stability"
    if not d.is_dir():
        page.skipped("stability/ 폴더")
        return
    overall = d / "overall.csv"
    if overall.is_file():
        row = read_csv(overall).iloc[0].to_dict()
        page.add("<h3>전체</h3>")
        page.table(KV_COLS, kv_rows("stability/overall.csv", row, lambda c, v: STABILITY_FORMATS.get(c, plain_num)(v)))
    groups = d / "groups.csv"
    if groups.is_file():
        page.add("<h3>그룹별</h3>")
        t = read_csv(groups)
        page.table(csv_cols("stability/groups.csv", t.columns, STABILITY_FORMATS), t.to_dict("records"))
    dies = d / "dies.csv"
    if dies.is_file():
        t = read_csv(dies)
        hit = true_rows(t, "flagged")
        page.add("<h3>die 위치</h3>")
        page.p(f"die {len(t):,}개 중 흔들리는 die {len(hit):,}개 (die 점수 1.5 이상이거나 튀는 ITEM 비율 20% 이상).")
        if not hit.empty:
            page.table(csv_cols("stability/dies.csv", t.columns, STABILITY_FORMATS), hit.to_dict("records"))
    runs = d / "runs.csv"
    if runs.is_file():
        t = read_csv(runs)
        page.add("<h3>POR 회차</h3>")
        page.table(csv_cols("stability/runs.csv", t.columns, STABILITY_FORMATS), t.to_dict("records"))
    page.figure(Figure(d / "stability.png", "측정 안정도 그림", names=False))


HOW_TO_READ = (
    "판정은 DOE와 POR의 die별 차이(이동량)와 그 90% 신뢰구간(이동량 범위)을 허용폭과 견주어 정한다.",
    "이동량 범위 전체가 허용폭 안이면 동등, 전체가 밖이면 차이, 걸치면 미결이다. 판정 제외는 계산할 수 없는 ITEM 이다.",
    "최종 판정은 기본 판정이 차이·미결일 때만 옵션(log, 장비 정확도)으로 다시 본 결과다. 판정 근거가 기본 판정이 아니면 옵션이 바꾼 ITEM 이다.",
    "판정력은 신뢰구간 반폭 ÷ 허용폭이다. 0.5 이하면 안정, 0.8 이하면 주의, 그 위는 불안정이다. 불안정 ITEM 의 미결은 측정 탓일 수 있다.",
    "LoQ·log 확인 필요는 참고 표시다. 판정은 바꾸지 않는다. 확인 필요 ITEM 은 상세 그림을 보고 원데이터를 다시 확인한다.",
    "표 머리글에 마우스를 올리면 열 뜻이 나온다.",
)


def how_to_read(page: Page) -> None:
    page.h2("읽는 법", "how")
    page.add("<ul>" + "".join(f"<li>{page.namer.text(s)}</li>" for s in HOW_TO_READ) + "</ul>")
    page.columns_link()
    page.glossary()


def judge_report(folder: Path, items: pd.DataFrame, namer: Namer) -> Path:
    page = Page(f"판정 리포트 · {folder.name}", namer, folder / namer.report_file)
    nav(page, [("kpi", "한눈에"), ("map", "판정 지도"), ("problems", "차이·미결"), ("excluded", "판정 제외"),
               ("loq", "LoQ 확인 필요"), ("log", "log 확인 필요"), ("logrun", "log 허용폭 두 방식"),
               ("stability", "측정 안정도"), ("how", "읽는 법")])
    page.h2("한눈에", "kpi")
    kpi(page, items, folder)
    page.h2("판정 지도", "map")
    page.figures([Figure(folder / "plots" / "summary.png", "판정 지도", names=True),
                  Figure(folder / "plots" / "summary_loq.png", "LoQ 아래 ITEM", names=True)])
    page.h2("차이·미결", "problems")
    problems(page, items)
    page.h2("판정 제외", "excluded")
    excluded(page, items)
    page.h2("LoQ 확인 필요", "loq")
    review(page, folder, "loq")
    page.h2("log 확인 필요", "log")
    review(page, folder, "log")
    page.h2("log 허용폭 두 방식", "logrun")
    log_run_compare(page, items)
    page.h2("측정 안정도", "stability")
    stability(page, folder)
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


def item_report(folder: Path, namer: Namer) -> Path | None:
    item_dir = folder / "item"
    if not item_dir.is_dir():
        return None
    page = Page(f"ITEM 리포트 · {folder.name}", namer, item_dir / namer.report_file)
    page.p("ITEM 마다 판정 카드(쉬운 말), ITEM 한 장 그림, 판정 근거 숫자(evidence.csv)를 싣는다.")
    page.figure(Figure(item_dir / "forest.png", "ITEM 별 이동량과 허용폭 (forest)", names=True))
    cards_shown = 0
    for d in item_folders(item_dir):
        summary = d / "summary.csv"
        if not summary.is_file():
            continue
        row = read_csv(summary).iloc[0].to_dict()
        ev_path = d / "evidence.csv"
        ev = read_csv(ev_path).iloc[0].to_dict() if ev_path.is_file() else {}
        up, down = (int(num(ev[k])) if math.isfinite(num(ev.get(k))) else None for k in ("n_d_pos", "n_d_neg"))
        item = str(row.get("ITEM"))
        lines = explain.verdict_card(row, up, down)
        head = lines[0] + ("" if namer.anon else f" · 익명 ID {namer.id_of.get(item, '-')}")
        page.add(f'<section class="item" id="item-{cards_shown + 1}"><h3>{namer.text(head)}</h3>'
                 + "".join(f"<p>{namer.text(line)}</p>" for line in lines[1:]))
        page.figure(Figure(d / "item_view.png", f"{namer.label(item)} 한 장 보기", names=True))
        if ev:
            page.add("<details><summary>근거 숫자 (evidence.csv)</summary>")
            page.table(KV_COLS, evidence_rows(ev, unit_of(row)))
            page.add("</details>")
        else:
            page.skipped("evidence.csv (원데이터 없이 만든 ITEM 폴더)")
        page.add("</section>")
        cards_shown += 1
    if not cards_shown:
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
            Col(kind, "rsd_pct_median", lambda r: f"{plain_num(r['rsd_pct_median'])}%"),
            *csv_cols(kind, ("share_stable", "share_caution", "share_unstable"), STABILITY_FORMATS),
            Col("", "가장 나쁜 ITEM", lambda r: r["worst"])]


GROUP_SUMMARY_FIGURES = {          # compare_metrics 그림: 파일 → (제목, ITEM 이름이 그려짐)
    "verdict_center_delta.png": ("이동량 ÷ 허용폭 분포: 기존 대 개선", False),
    "stability_meas_precision_pct.png": ("측정 정밀도 % 분포: 기존 대 개선", False),
    "stability_sigma_die_pct.png": ("die 산포 % 분포: 기존 대 개선", False),
    "sigma_die_ratio.png": ("die 산포 비 (개선/기존)", True),
    "sigma_run_ratio.png": ("회차 흔들림 비 (개선/기존)", True),
    "meas_precision_ratio.png": ("측정 정밀도 비 (개선/기존)", True),
}

COMPARE_TABLES = (    # (폴더 안 경로, 열 사전 종류, 제목, 실제 ITEM 이름이 든 열)
    ("summary/group_summary.csv", "group_summary.csv", "그룹 요약 (기존 대 개선)", ()),
    ("summary/verdict_by_group.csv", "verdict_by_group.csv", "그룹별 판정 변화", ()),
    ("summary/stability_by_group.csv", "stability_by_group.csv", "그룹별 측정 안정도 (기존 대 개선)", ()),
    ("compare/stability_overall.csv", "stability_overall.csv", "전체 측정 안정도 (기존 대 개선)", ()),
    ("compare/worst_items.csv", "worst_items.csv", "가장 나빠진 ITEM", ("ID", "ITEM")),
)


def compare_tables(page: Page, group_dir: Path) -> None:
    shown = 0
    for rel, kind, title, name_cols in COMPARE_TABLES:
        path = group_dir / rel
        if not path.is_file():
            continue
        t = read_csv(path)
        page.add(f"<h3>{page.namer.text(title)}</h3>")
        cols = [Col(kind, c, (lambda r, c=c: page.namer.label(r[c])) if c in name_cols else None) for c in t.columns]
        page.table(cols, t.to_dict("records"))
        shown += 1
    changed = group_dir / "compare" / "compare.csv"
    if changed.is_file():
        t = read_csv(changed)
        moved = t[t["verdict_before"] != t["verdict_after"]] if {"verdict_before", "verdict_after"} <= set(t) else t[:0]
        page.add("<h3>판정이 바뀐 ITEM</h3>")
        page.p(f"짝이 있는 ITEM {len(t):,}개 중 {len(moved):,}개.")
        if not moved.empty:
            kind = "compare.csv"
            page.table([*id_cols(kind), *csv_cols(kind, ("verdict_before", "verdict_after", "center_delta_before",
                                         "center_delta_after"))], moved.to_dict("records"))
        shown += 1
    if not shown:
        page.skipped("기존·개선 비교 결과 (dcc group --before 로 만든다)")


def group_report(folder: Path, items: pd.DataFrame, namer: Namer, groups: Path | None) -> Path | None:
    group_dir = folder / "group"
    if not group_dir.is_dir():
        return None
    page = Page(f"그룹 리포트 · {folder.name}", namer, group_dir / namer.report_file)
    nav(page, [("groups", "그룹별 표"), ("figures", "그룹 그림"), ("compare", "기존·개선 비교")])
    page.h2("그룹별 표", "groups")
    if groups is not None and groups.is_file():
        from infra_compare import read_groups
        g = read_groups(groups)
        page.p("판정력 비율은 신뢰구간 반폭 ÷ 허용폭이 0.5 이하(안정), 0.8 이하(주의), 그 위(불안정)인 ITEM 비율이다. "
               "가장 나쁜 ITEM 은 차이·미결 중 이동량 범위 끝이 허용폭을 많이 넘는 순으로 셋.")
        page.table(group_table_cols(), group_rows(items, dict(zip(g["ITEM"], g["group"])), namer))
    elif (folder / "stability" / "groups.csv").is_file():
        t = read_csv(folder / "stability" / "groups.csv")
        page.p("그룹 파일(--groups)을 주지 않아 그룹별 판정 개수는 없다. 판정할 때 만든 그룹별 측정 안정도만 싣는다.")
        page.table(csv_cols("stability/groups.csv", t.columns, STABILITY_FORMATS), t.to_dict("records"))
    else:
        page.p("그룹별 표는 그룹 파일이 있어야 만든다: python report.py <폴더> --groups ITEM,그룹 파일.", "note")
    page.h2("그룹 그림", "figures")
    plots = group_dir / "plots"
    page.figures([*(Figure(p, f"그룹 {p.stem.removeprefix('summary_group_')}", names=True)
                    for p in sorted(plots.glob("summary_group_*.png"))),
                  *(Figure(group_dir / "summary" / f, t, n) for f, (t, n) in GROUP_SUMMARY_FIGURES.items())])
    page.h2("기존·개선 비교", "compare")
    compare_tables(page, group_dir)
    page.glossary()
    page.columns_link()
    return page.write()


# ── 진입점 ─────────────────────────────────────────────────────────────────

def write_reports(folder, anon: bool = False, groups=None) -> list[Path]:
    """folder (<out>/<이름>) 의 결과 파일로 report.html, item/report.html, group/report.html 을 쓴다.
    item/·group/ 이 없으면 그 리포트는 건너뛴다. 쓴 파일 목록을 돌려준다."""
    folder = Path(folder)
    items_csv = folder / "items.csv"
    if not items_csv.is_file():
        raise FileNotFoundError(f"{items_csv} 가 없습니다 (먼저 dcc.py judge 로 판정하세요)")
    items = read_csv(items_csv)
    namer = Namer(items, anon)
    written = [judge_report(folder, items, namer), item_report(folder, namer),
               group_report(folder, items, namer, Path(groups) if groups else None)]
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
