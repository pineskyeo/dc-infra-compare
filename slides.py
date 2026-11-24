#!/usr/bin/env python3
"""판정 기준 장표 2쪽 (pptx). 판정 결과 폴더를 읽어 만든다. ITEM 은 익명 ID 로만 쓴다.

  1쪽  01 기존 문제 · 02 새 판정 3단계 (전체 TOST → LoQ 판정 → ITEM 유형별 판정 길)
  2쪽  03 판정 결과 · 04 그룹 × 측정 LEVEL 측정 정밀도 · 05 미결 원인과 조치

    python slides.py <결과 폴더> [--before 이전/items.csv] [--out 장표.pptx] [--font 맑은 고딕]

결과 폴더 = dcc.py judge 의 <out>/<조합> (items.csv, 있으면 stability/group_levels.csv).
dcc.py slides <조합> 이 부른다. pptx 는 표준 라이브러리로 쓰고 틀(테마·마스터)은 assets/pptx 를 쓴다.
"""
from __future__ import annotations

import argparse
import io
import math
import re
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "assets" / "pptx"
FONT = "맑은 고딕"
SLIDE_W, SLIDE_H = 13.333, 7.5          # 인치 (16:9)
EMU = 914400

NAVY, TINT, TEXT, MUTED, RULE = "3D4C61", "EEF1F5", "1F2933", "6B7785", "D5DBE3"
OK, HOLD, BAD, EXCL = "1A8754", "C27C0E", "B5523B", "9AA3AE"
VERDICTS = ("동등", "미결", "차이", "판정 제외")
VERDICT_COLOR = dict(zip(VERDICTS, (OK, HOLD, BAD, EXCL)))
MAX_GROUPS, MAX_LEVELS, MAX_FOREST = 10, 10, 10
BOTTOM = 6.35                           # 2쪽 본문 아래 끝 (그 밑은 다음 조치 띠)


# ---------------------------------------------------------------- 도형 (단위: 인치)

@dataclass(frozen=True)
class Run:
    text: str
    size: float = 10.0
    color: str = TEXT
    bold: bool = False


@dataclass(frozen=True)
class Para:
    runs: tuple[Run, ...]
    align: str = "l"            # l, ctr, r
    after: float = 0.0          # 문단 뒤 간격 (pt)


def para(*runs: Run, align: str = "l", after: float = 0.0) -> Para:
    return Para(tuple(runs), align, after)


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float
    paras: tuple[Para, ...] = ()
    fill: str | None = None
    line: str | None = None
    line_w: float = 0.75
    geom: str = "rect"          # rect, roundRect, ellipse
    anchor: str = "t"           # t, ctr, b
    inset: float = 0.04


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    color: str = NAVY
    w: float = 0.75
    arrow: bool = False


@dataclass(frozen=True)
class Pic:
    x: float
    y: float
    w: float
    h: float
    png: bytes


Shape = Box | Line | Pic


@dataclass
class Slide:
    shapes: list[Shape] = field(default_factory=list)

    def add(self, *shapes: Shape) -> None:
        self.shapes.extend(shapes)


def text(x: float, y: float, w: float, h: float, *paras: Para, anchor: str = "t", **kw) -> Box:
    return Box(x, y, w, h, tuple(paras), anchor=anchor, **kw)


# ---------------------------------------------------------------- pptx 쓰기

def _e(v: float) -> int:
    return int(round(v * EMU))


def _fill(color: str | None) -> str:
    return f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>' if color else "<a:noFill/>"


def _ln(color: str | None, w: float, arrow: bool = False) -> str:
    if not color:
        return "<a:ln><a:noFill/></a:ln>"
    tail = '<a:tailEnd type="triangle" w="med" len="med"/>' if arrow else ""
    return f'<a:ln w="{_e(w / 72)}">{_fill(color)}{tail}</a:ln>'


def _run(r: Run, font: str) -> str:
    bold = ' b="1"' if r.bold else ""
    return (f'<a:r><a:rPr lang="ko-KR" sz="{int(round(r.size * 100))}"{bold} dirty="0">{_fill(r.color)}'
            f'<a:latin typeface="{font}"/><a:ea typeface="{font}"/><a:cs typeface="{font}"/></a:rPr>'
            f"<a:t>{escape(r.text)}</a:t></a:r>")


def _para(p: Para, font: str) -> str:
    size = p.runs[0].size if p.runs else 10
    after = f'<a:spcAft><a:spcPts val="{int(p.after * 100)}"/></a:spcAft>' if p.after else ""
    return (f'<a:p><a:pPr algn="{p.align}" marL="0" indent="0">{after}<a:buNone/></a:pPr>'
            + "".join(_run(r, font) for r in p.runs)
            + f'<a:endParaRPr lang="ko-KR" sz="{int(round(size * 100))}" dirty="0"/></a:p>')


def _xfrm(x: float, y: float, w: float, h: float, flip: str = "") -> str:
    return f'<a:xfrm{flip}><a:off x="{_e(x)}" y="{_e(y)}"/><a:ext cx="{_e(w)}" cy="{_e(h)}"/></a:xfrm>'


def _box(b: Box, sid: int, font: str) -> str:
    av = '<a:gd name="adj" fmla="val 6000"/>' if b.geom == "roundRect" else ""
    body = ""
    if b.paras:
        i = _e(b.inset)
        body = (f'<p:txBody><a:bodyPr wrap="square" lIns="{i}" tIns="{i}" rIns="{i}" bIns="{i}" anchor="{b.anchor}" '
                f'rtlCol="0"><a:noAutofit/></a:bodyPr><a:lstStyle/>'
                + "".join(_para(p, font) for p in b.paras) + "</p:txBody>")
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="Shape {sid}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f"<p:spPr>{_xfrm(b.x, b.y, b.w, b.h)}<a:prstGeom prst=\"{b.geom}\"><a:avLst>{av}</a:avLst></a:prstGeom>"
            f"{_fill(b.fill)}{_ln(b.line, b.line_w)}</p:spPr>{body}</p:sp>")


def _line(ln: Line, sid: int) -> str:
    flip = (' flipH="1"' if ln.x2 < ln.x1 else "") + (' flipV="1"' if ln.y2 < ln.y1 else "")
    x, y = min(ln.x1, ln.x2), min(ln.y1, ln.y2)
    return (f'<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="{sid}" name="Line {sid}"/><p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>'
            f"<p:spPr>{_xfrm(x, y, abs(ln.x2 - ln.x1), abs(ln.y2 - ln.y1), flip)}"
            f'<a:prstGeom prst="line"><a:avLst/></a:prstGeom>{_ln(ln.color, ln.w, ln.arrow)}</p:spPr></p:cxnSp>')


def _pic(p: Pic, sid: int, rid: str) -> str:
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{sid}" name="Picture {sid}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/>'
            f'</p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch>'
            f'</p:blipFill><p:spPr>{_xfrm(p.x, p.y, p.w, p.h)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            "</p:pic>")


NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _slide_xml(slide: Slide, number: int, font: str) -> tuple[str, str, list[tuple[str, bytes]]]:
    """(slide xml, rels xml, [(미디어 이름, png)])."""
    parts, media, rels = [], [], [f'<Relationship Id="rId1" Type="{REL}/slideLayout" '
                                  'Target="../slideLayouts/slideLayout1.xml"/>']
    for sid, shape in enumerate(slide.shapes, start=2):
        if isinstance(shape, Pic):
            name, rid = f"slide{number}-image{len(media) + 1}.png", f"rId{len(media) + 2}"
            media.append((name, shape.png))
            rels.append(f'<Relationship Id="{rid}" Type="{REL}/image" Target="../media/{name}"/>')
            parts.append(_pic(shape, sid, rid))
        elif isinstance(shape, Line):
            parts.append(_line(shape, sid))
        else:
            parts.append(_box(shape, sid, font))
    xml = (f'{XML_HEAD}<p:sld {NS}><p:cSld name="Slide {number}"><p:bg><p:bgPr>{_fill("FFFFFF")}<a:effectLst/>'
           '</p:bgPr></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
           '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/>'
           f'</a:xfrm></p:grpSpPr>{"".join(parts)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
           "</p:sld>")
    return xml, f'{XML_HEAD}<Relationships xmlns="{PKG_REL}">{"".join(rels)}</Relationships>', media


def write_pptx(path: Path, slides: Sequence[Slide], font: str = FONT, title: str = "") -> Path:
    """slides 를 16:9 pptx 하나로 쓴다. 틀(테마·마스터·레이아웃)은 assets/pptx."""
    ct = "application/vnd.openxmlformats-officedocument"
    overrides = {"/ppt/presentation.xml": f"{ct}.presentationml.presentation.main+xml",
                 "/ppt/slideMasters/slideMaster1.xml": f"{ct}.presentationml.slideMaster+xml",
                 "/ppt/slideLayouts/slideLayout1.xml": f"{ct}.presentationml.slideLayout+xml",
                 "/ppt/theme/theme1.xml": f"{ct}.theme+xml",
                 "/ppt/presProps.xml": f"{ct}.presentationml.presProps+xml",
                 "/ppt/viewProps.xml": f"{ct}.presentationml.viewProps+xml",
                 "/ppt/tableStyles.xml": f"{ct}.presentationml.tableStyles+xml",
                 "/docProps/core.xml": "application/vnd.openxmlformats-package.core-properties+xml",
                 "/docProps/app.xml": f"{ct}.extended-properties+xml",
                 **{f"/ppt/slides/slide{i}.xml": f"{ct}.presentationml.slide+xml" for i in range(1, len(slides) + 1)}}
    types = (f'{XML_HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="png" ContentType="image/png"/>'
             + "".join(f'<Override PartName="{k}" ContentType="{v}"/>' for k, v in overrides.items()) + "</Types>")
    root_rels = (f'{XML_HEAD}<Relationships xmlns="{PKG_REL}">'
                 f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="ppt/presentation.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/'
                 'metadata/core-properties" Target="docProps/core.xml"/>'
                 f'<Relationship Id="rId3" Type="{REL}/extended-properties" Target="docProps/app.xml"/></Relationships>')
    n = len(slides)
    pres_rels = ([f'<Relationship Id="rId1" Type="{REL}/slideMaster" Target="slideMasters/slideMaster1.xml"/>']
                 + [f'<Relationship Id="rId{i + 1}" Type="{REL}/slide" Target="slides/slide{i}.xml"/>'
                    for i in range(1, n + 1)]
                 + [f'<Relationship Id="rId{n + 2 + k}" Type="{REL}/{t}" Target="{f}"/>' for k, (t, f) in enumerate(
                     (("presProps", "presProps.xml"), ("viewProps", "viewProps.xml"), ("theme", "theme/theme1.xml"),
                      ("tableStyles", "tableStyles.xml")))])
    presentation = (f'{XML_HEAD}<p:presentation {NS} saveSubsetFonts="1"><p:sldMasterIdLst>'
                    '<p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>'
                    + "".join(f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>' for i in range(1, n + 1))
                    + f'</p:sldIdLst><p:sldSz cx="{_e(SLIDE_W)}" cy="{_e(SLIDE_H)}"/><p:notesSz cx="6858000" '
                    'cy="9144000"/></p:presentation>')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = (f'{XML_HEAD}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
            'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(title)}</dc:title>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>')
    app = (f'{XML_HEAD}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           f"<Slides>{n}</Slides><Application>dc-infra-compare slides.py</Application></Properties>")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels",
                   f'{XML_HEAD}<Relationships xmlns="{PKG_REL}">{"".join(pres_rels)}</Relationships>')
        for name, target in (("theme1.xml", "ppt/theme/theme1.xml"),
                             ("slideMaster1.xml", "ppt/slideMasters/slideMaster1.xml"),
                             ("slideMaster1.xml.rels", "ppt/slideMasters/_rels/slideMaster1.xml.rels"),
                             ("slideLayout1.xml", "ppt/slideLayouts/slideLayout1.xml"),
                             ("slideLayout1.xml.rels", "ppt/slideLayouts/_rels/slideLayout1.xml.rels"),
                             ("presProps.xml", "ppt/presProps.xml"), ("viewProps.xml", "ppt/viewProps.xml"),
                             ("tableStyles.xml", "ppt/tableStyles.xml")):
            z.writestr(target, (TEMPLATE / name).read_bytes())
        for i, slide in enumerate(slides, start=1):
            xml, rels, media = _slide_xml(slide, i, font)
            z.writestr(f"ppt/slides/slide{i}.xml", xml)
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", rels)
            for name, png in media:
                z.writestr(f"ppt/media/{name}", png)
    return path


# ---------------------------------------------------------------- 그림 (matplotlib → png)

def _hex(c: str) -> str:
    return f"#{c}"


def _png(fig) -> bytes:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _axes(w: float, h: float):
    from compare_metrics import set_font
    import matplotlib.pyplot as plt
    set_font()
    fig, ax = plt.subplots(figsize=(w, h), layout="constrained")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#9AA3AE")
    ax.tick_params(colors="#6B7785", labelsize=7, length=2)
    return fig, ax


def _bars(ax, bars, label_x: float) -> None:
    for y, (lo, hi, verdict) in enumerate(reversed(bars)):
        color = _hex(VERDICT_COLOR[verdict])
        ax.plot([lo, hi], [y, y], color=color, lw=3.2, solid_capstyle="round")
        ax.plot([(lo + hi) / 2], [y], "o", color="white", mec=color, mew=1.4, ms=4.5)
        ax.text(label_x, y, verdict, color=color, fontsize=8, fontweight="bold", va="center")
    ax.set_yticks([])
    ax.set_ylim(-0.7, len(bars) - 0.3)


def stage1_png() -> bytes:
    """1단계: 90% 신뢰구간 대 ±Δ."""
    fig, ax = _axes(2.3, 1.3)
    ax.axvspan(-1, 1, color="#E3F1EA", zorder=0)
    for v in (-1, 1):
        ax.axvline(v, color=_hex(OK), lw=0.8, ls="--")
    _bars(ax, ((-0.55, 0.35, "동등"), (0.45, 1.55, "미결"), (1.3, 2.0, "차이")), 2.25)
    ax.set_xlim(-1.8, 2.9)
    ax.set_xticks([-1, 0, 1], ["-Δ", "0", "+Δ"])
    return _png(fig)


def stage2_png() -> bytes:
    """2단계: DOE 수준 구간 대 LoQ."""
    fig, ax = _axes(2.3, 1.3)
    ax.axvspan(0, 1, color="#ECEFF3", zorder=0)
    ax.axvline(1, color=_hex(NAVY), lw=1.1)
    ax.text(0.5, 2.55, "'<LoQ' 보고", ha="center", fontsize=7, color=_hex(MUTED))
    _bars(ax, ((0.15, 0.7, "동등"), (0.72, 1.35, "미결"), (1.2, 1.8, "차이")), 1.95)
    ax.set_ylim(-0.7, 2.9)
    ax.set_xlim(0, 2.45)
    ax.set_xticks([0, 1], ["0", "LoQ"])
    return _png(fig)


def heatmap_png(table: pd.DataFrame, w: float, h: float) -> bytes:
    """그룹(줄) × 측정 LEVEL(칸) 의 측정 정밀도 중앙값. 진할수록 흔들림이 크다."""
    from matplotlib.colors import LogNorm
    import matplotlib.pyplot as plt
    from compare_metrics import set_font
    set_font()
    groups, levels = list(table.index), list(table.columns)
    values = table.to_numpy(float)
    fig, ax = plt.subplots(figsize=(w, h), layout="constrained")
    finite = values[np.isfinite(values) & (values > 0)]
    norm = LogNorm(finite.min(), max(finite.max(), finite.min() * 1.01)) if finite.size else None
    masked = np.ma.masked_invalid(np.where(values > 0, values, np.nan))
    cmap = plt.get_cmap("Blues").copy()
    cmap.set_bad("#F1F3F6")
    ax.pcolormesh(masked, cmap=cmap, norm=norm, edgecolors="white", linewidth=2)
    size = 8 if len(groups) * len(levels) <= 40 else 6.5
    for i in range(len(groups)):
        for j in range(len(levels)):
            v = values[i, j]
            if np.isfinite(v):
                dark = norm is not None and v > 0 and norm(v) > 0.55
                label = f"{v:,.0f}%" if v >= 100 else f"{v:.2g}%" if v >= 1 else f"{v:.2f}%"
                ax.text(j + 0.5, i + 0.5, label, ha="center", va="center", fontsize=size,
                        color="white" if dark else _hex(TEXT), fontweight="bold")
    ax.set_xticks(np.arange(len(levels)) + 0.5, levels, fontsize=7)
    ax.set_yticks(np.arange(len(groups)) + 0.5, groups, fontsize=7)
    ax.xaxis.tick_top()
    ax.invert_yaxis()
    ax.tick_params(length=0, colors=_hex(TEXT))
    for side in ax.spines.values():
        side.set_visible(False)
    return _png(fig)


def forest_png(rows: pd.DataFrame, w: float, h: float) -> bytes:
    """미결 ITEM 의 정규화 변화량 구간 (가운데 점, ±1 = 허용폭). 색 = 원인."""
    fig, ax = _axes(w, h)
    lim = 3.5
    ax.axvspan(-1, 1, color="#E3F1EA", zorder=0)
    for v in (-1, 1):
        ax.axvline(v, color=_hex(OK), lw=0.8, ls="--")
    ax.axvline(0, color="#C9CFD7", lw=0.6)
    for y, r in enumerate(rows.itertuples()):
        lo, hi, x = (float(np.clip(v, -lim, lim)) for v in (r.lo, r.hi, r.x))
        color = _hex(r.color)
        ax.plot([lo, hi], [y, y], color=color, lw=2.6, solid_capstyle="round")
        ax.plot([x], [y], "o", color="white", mec=color, mew=1.3, ms=3.8)
        for edge, raw in ((lo, r.lo), (hi, r.hi)):
            if abs(raw) > lim:
                ax.text(edge, y, "▶" if raw > 0 else "◀", color=color, fontsize=6, ha="center", va="center")
    ax.set_yticks(range(len(rows)), rows["ID"], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(-lim - 0.2, lim + 0.2)
    ax.set_xticks([-3, -2, -1, 0, 1, 2, 3], ["-3", "-2", "-Δ", "0", "+Δ", "2", "3"])
    ax.set_xlabel("정규화 변화량 (90% 구간 ÷ 허용폭)", fontsize=7, color=_hex(MUTED))
    return _png(fig)


# ---------------------------------------------------------------- 결과에서 숫자 읽기

@dataclass(frozen=True)
class Cause:
    """미결 원인. 위에서부터 처음 맞는 것."""
    name: str
    action: str
    color: str
    hit: Callable[[Mapping], bool]


LOQ_CROSS = re.compile(r"LoQ\([^)]*\)에 걸침")
CAUSES = (
    Cause("die 부족", "die 10개 미만 · die를 늘려 다시 판정", "6B7785", lambda r: r["zone"] == "die 부족"),
    Cause("LoQ 선에 걸침", "DOE가 LoQ 근처 · 재측정으로 위·아래 확정", "8E6CB0",
          lambda r: r["basis"] == "loq" and bool(LOQ_CROSS.search(r["reason"]))),
    Cause("측정 흔들림", "구간이 허용폭보다 넓음 · die 추가·재측정", "C27C0E", lambda r: r["y"] >= 1),
    Cause("기준 조건 흔들림", "POR 회차끼리 어긋남 · POR 재측정, 프로빙·온도 확인", "3F7CAC",
          lambda r: any(s in r["status"] for s in ("회차 흔들림", "조건 불안정"))),
    Cause("허용폭 경계", "변화가 허용폭 근처 · 재측정으로 확정, 필요하면 허용폭 검토", "B5523B", lambda r: True),
)


def read_items(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""], low_memory=False)


def final_col(items: pd.DataFrame) -> pd.Series:
    return (items["verdict_final"] if "verdict_final" in items else items["verdict"]).astype(str)


def undecided(items: pd.DataFrame) -> pd.DataFrame:
    """미결 ITEM 한 행씩: ID, cause (CAUSES 이름), color, x (정규화 변화량 가운데), y (정규화 불확실성), lo, hi.
    원인 순서 (CAUSES), 그 안은 |x| 큰 순."""
    from plot_verdicts import map_points
    pts = map_points(items)
    mine = items.assign(_x=pts["x"].to_numpy(), _y=pts["y"].to_numpy())[final_col(items) == "미결"]
    rows = []
    for r in mine.to_dict("records"):
        facts = {"zone": str(r.get("zone", "")), "basis": str(r.get("verdict_basis", "") or ""),
                 "reason": str(r.get("reason", "") or ""), "status": str(r.get("status", "") or ""),
                 "y": float(r["_y"]) if pd.notna(r["_y"]) else -math.inf}
        cause = next(c for c in CAUSES if c.hit(facts))
        x, y = float(r["_x"]), float(r["_y"])
        rows.append({"ID": str(r.get("ID") or r["ITEM"]), "cause": cause.name, "color": cause.color,
                     "x": x, "y": y, "lo": x - y, "hi": x + y})
    t = pd.DataFrame(rows, columns=["ID", "cause", "color", "x", "y", "lo", "hi"])
    rank = {c.name: i for i, c in enumerate(CAUSES)}
    return t.assign(_r=t["cause"].map(rank), _a=-t["x"].abs()).sort_values(["_r", "_a"], kind="stable").drop(
        columns=["_r", "_a"]).reset_index(drop=True)


def precision_table(folder: Path) -> tuple[pd.DataFrame | None, str]:
    """(그룹 × LEVEL 측정 정밀도 중앙값 표, 줄인 내용). group_levels.csv 가 없으면 (None, 이유)."""
    path = folder / "stability" / "group_levels.csv"
    if not path.is_file():
        return None, "판정할 때 level 파일(--level)을 주면 그룹 × 측정 LEVEL 측정 정밀도가 생긴다."
    from stability import UNGROUPED, level_order
    t = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    t["meas_precision_pct_median"] = pd.to_numeric(t["meas_precision_pct_median"], errors="coerce")
    groups = t.groupby("group")["n_items"].sum().sort_values(ascending=False)
    keep_g = sorted(groups.index[:MAX_GROUPS], key=lambda g: (g == UNGROUPED, g))
    levels = t[t["group"].isin(keep_g)].groupby("level")["n_items"].sum().sort_values(ascending=False)
    keep_l = sorted(levels.index[:MAX_LEVELS], key=level_order)
    pivot = t.pivot_table(index="group", columns="level", values="meas_precision_pct_median", aggfunc="first")
    cut = []
    if len(groups) > len(keep_g):
        cut.append(f"그룹 {len(groups):,}개 중 ITEM이 많은 {len(keep_g)}개")
    if len(levels) > len(keep_l):
        cut.append(f"LEVEL {len(levels):,}개 중 많은 {len(keep_l)}개")
    return pivot.reindex(index=keep_g, columns=keep_l), (" · ".join(cut) + "만 보임. 전체는 리포트") if cut else ""


def verdict_counts(items: pd.DataFrame) -> dict[str, int]:
    v = final_col(items).value_counts()
    return {k: int(v.get(k, 0)) for k in VERDICTS}


def basis_counts(items: pd.DataFrame) -> list[tuple[str, int]]:
    from explain import BASIS_NAMES
    if "verdict_basis" not in items:
        return []
    v = items["verdict_basis"].astype(str).value_counts()
    order = list(BASIS_NAMES)
    return [(BASIS_NAMES.get(b, b), int(v[b])) for b in sorted(v.index, key=lambda b: order.index(b)
                                                                if b in order else len(order))]


# ---------------------------------------------------------------- 쪽 구성

def chrome(s: Slide, page: int, pages: int, title: str, subtitle: str, note: str) -> None:
    s.add(text(0.5, 0.12, 8, 0.26, para(Run("DC Test 판정 기준 개선 · 내부 리뷰", 9, MUTED))),
          text(11.33, 0.12, 1.5, 0.26, para(Run(f"{page} / {pages}", 9, MUTED), align="r")),
          Line(0.5, 0.42, 12.83, 0.42, NAVY, 0.5),
          text(0.5, 0.55, 12.33, 0.62, para(Run(title, 24, NAVY, True), Run(f"   {subtitle}", 17, "5B6B80")),
               anchor="ctr"),
          Line(0.5, 7.05, 12.83, 7.05, RULE, 0.5),
          text(0.5, 7.1, 6.5, 0.25, para(Run("Process / Test Engineering", 8, MUTED))),
          text(6.0, 7.1, 6.83, 0.25, para(Run(note, 8, MUTED), align="r")))


def heading(s: Slide, x: float, y: float, w: float, number: str, title: str, aside: str = "") -> None:
    runs = [Run(f"{number}  ", 13, NAVY, True), Run(title, 13, NAVY, True)]
    if aside:
        runs.append(Run(f"   {aside}", 9.5, MUTED))
    s.add(text(x, y, w, 0.34, para(*runs), anchor="b"), Line(x, y + 0.38, x + w, y + 0.38, NAVY, 0.75))


PROBLEMS = (
    ("같은 조건을 다시 재도 Fail", "회차 흔들림·잡음과 실제 변화를 가르지 못함"),
    ("LoQ·0 근처 값에서 판정이 흔들림", "DOE 중심 한 점으로 LoQ와 비교 · 값이 0에 가까우면 % 허용폭도 0"),
    ("모든 ITEM을 같은 % 허용폭으로", "값에 비례해 흔들리는 ITEM(누설 전류 등)도 선형으로 봄"),
)
STAGES = (
    ("1", "전체 TOST", "모든 ITEM", ("90% 신뢰구간이 ±Δ 안 → 동등", "통째로 밖 → 차이 · 걸침 → 미결",
                                    "Δ = 5% × |POR 중앙값| + 회차 흔들림 몫")),
    ("2", "LoQ 판정", "POR 중앙값이 LoQ 아래인 ITEM", ("DOE 구간이 통째로 LoQ 아래 → 동등",
                                                     "통째로 위 → 차이 · LoQ 선에 걸침 → 미결",
                                                     "LoQ = 10σ (반복 흔들림·분해능·blank 중 큰 값)")),
)
CHANGES = (("변화 판단", "한 점", "90% 구간"), ("LoQ 아래", "DOE 중심 한 점", "DOE 구간"),
           ("허용폭", "모두 같은 %", "ITEM 유형별"))
ROUTES = (
    ("한계 비교", "측정 한계에 걸린 die가 많음 → 한계 밖 die만으로 TOST"),
    ("절대 허용폭", "값이 0 근처 · 계단처럼 찍힘 → ±고정 허용폭 (기본 LoQ)"),
    ("LoQ 판정", "POR이 LoQ 아래 → 2단계 판정 그대로"),
    ("log TOST", "잡음이 값에 비례 → 배율(log)로 TOST"),
    ("선형 TOST", "나머지 → 1단계 그대로 · 바닥 근처는 장비 정확도까지"),
    ("제외", "판정할 수 없는 데이터 → 1·2단계 그대로"),
)
AXES = (("부호", "섞임·양수·음수"), ("수준", "0 중심·바닥·정량"), ("분해능", "연속·계단"), ("모양", "한계에 걸림 등"),
        ("척도", "잡음 ∝ 값 → log"))


def page_method(before: tuple[int, int] | None, note: str) -> Slide:
    s = Slide()
    chrome(s, 1, 2, "DC Test 판정 기준 개선", "3단계 판정 · TOST → LoQ → ITEM 유형", note)
    heading(s, 0.5, 1.3, 3.75, "01", "기존 문제")
    for i, (head, sub) in enumerate(PROBLEMS):
        y = 1.88 + i * 1.12
        s.add(Box(0.5, y, 3.75, 0.98, fill=TINT, geom="roundRect"),
              Box(0.5, y, 0.06, 0.98, fill=BAD),
              text(0.7, y + 0.1, 3.45, 0.8, para(Run(f"{'①②③'[i]}  {head}", 11.5, TEXT, True), after=4),
                   para(Run(sub, 9.5, MUTED))))
    if before:
        old, new = before
        s.add(text(0.5, 5.32, 3.75, 0.95,
                   para(Run("같은 데이터, 미결·차이 ITEM", 9.5, MUTED), after=2),
                   para(Run(f"{old:,}", 22, BAD, True), Run("  →  ", 14, MUTED), Run(f"{new:,}", 22, NAVY, True),
                        Run("   기존 → 새 판정", 9.5, MUTED))))
    else:
        s.add(text(0.5, 5.3, 3.75, 0.28, para(Run("무엇이 바뀌나", 9.5, NAVY, True))))
        for j, (what, old, new) in enumerate(CHANGES):
            y = 5.6 + j * 0.27
            s.add(text(0.5, y, 1.0, 0.26, para(Run(what, 8.5, MUTED))),
                  text(1.45, y, 2.8, 0.26, para(Run(old, 8.5, MUTED), Run("  →  ", 8.5, MUTED),
                                                Run(new, 8.5, NAVY, True))))

    heading(s, 4.55, 1.3, 8.28, "02", "새 판정 · 3단계", "앞 단계에서 동등이면 확정, 뒤 단계는 동등이 아닌 ITEM만")
    figures = (stage1_png(), stage2_png())
    x = 4.55
    for k, (num, name, who, rules) in enumerate(STAGES):
        w = 2.55
        s.add(Box(x, 1.88, w, 3.72, fill=TINT, geom="roundRect"),
              text(x + 0.14, 1.96, w - 0.28, 0.55, para(Run(f"{num}  ", 13, NAVY, True), Run(name, 13, NAVY, True)),
                   para(Run(who, 8.5, MUTED))),
              Pic(x + 0.12, 2.62, w - 0.24, (w - 0.24) * 1.3 / 2.3, figures[k]),
              text(x + 0.14, 4.08, w - 0.28, 1.45, *(para(Run(r, 9.2, TEXT if j < 2 else MUTED), after=3)
                                                    for j, r in enumerate(rules))),
              Line(x + w + 0.01, 3.74, x + w + 0.1, 3.74, MUTED, 1.0, arrow=True))
        x += w + 0.11
    w = 12.83 - x
    s.add(Box(x, 1.88, w, 3.72, fill=NAVY, geom="roundRect"),
          text(x + 0.14, 1.96, w - 0.28, 0.55, para(Run("3  ", 13, "FFFFFF", True), Run("ITEM 유형별 판정", 13, "FFFFFF", True)),
               para(Run("1·2단계에서 동등이 아닌 ITEM만, 유형에 맞는 판정 길로", 8.5, "C9D2DE"))))
    for j, (route, how) in enumerate(ROUTES):
        y = 2.6 + j * 0.49
        s.add(text(x + 0.14, y, w - 0.28, 0.46, para(Run(route, 10, "FFFFFF", True)), para(Run(how, 8.3, "C9D2DE"))))
        if j:
            s.add(Line(x + 0.14, y - 0.02, x + w - 0.14, y - 0.02, "56657B", 0.5))
    s.add(Box(4.55, 5.75, 8.28, 0.62, fill="FFFFFF", line=RULE, geom="roundRect"),
          text(4.7, 5.75, 2.1, 0.62, para(Run("ITEM 유형 자동 분류", 10.5, NAVY, True)),
               para(Run("POR 값만 보고 · 처음 맞는 판정 길로", 8, MUTED)), anchor="ctr"))
    for k, (name, sub) in enumerate(AXES):
        s.add(Box(6.85 + k * 1.18, 5.83, 1.1, 0.46, (para(Run(name, 9, NAVY, True), align="ctr"),
                                                     para(Run(sub, 7.5, MUTED), align="ctr")),
                  fill=TINT, geom="roundRect", anchor="ctr", inset=0.02))
    s.add(Box(0.5, 6.48, 12.33, 0.45, fill=TINT, geom="roundRect"),
          text(0.68, 6.48, 12.0, 0.45, para(Run("핵심  ", 10, NAVY, True),
                                            Run("측정 흔들림과 진짜 변화를 구간으로 가르고, 애매하면 미결로 보류, "
                                                "ITEM 성격에 맞는 허용폭으로 판정", 10, TEXT)), anchor="ctr"))
    return s


def page_results(label: str, items: pd.DataFrame, folder: Path, before_counts: dict[str, int] | None,
                 note: str) -> Slide:
    s = Slide()
    counts, n = verdict_counts(items), len(items)
    chrome(s, 2, 2, "동일 조건 반복 검증 결과", f"· 미결 분석   ({label}, ITEM {n:,}개)", note)
    heading(s, 0.5, 1.3, 6.15, "03", "판정 결과")
    for i, v in enumerate(VERDICTS):
        x = 0.5 + i * 1.56
        lines = [para(Run(v, 10, MUTED)), para(Run(f"{counts[v]:,}", 26, VERDICT_COLOR[v], True)),
                 para(Run(f"{100 * counts[v] / n:.0f}%" if n else "-", 9, MUTED))]
        if before_counts is not None:
            lines[-1] = para(Run(f"{100 * counts[v] / n:.0f}%" if n else "-", 9, MUTED),
                             Run(f"   기존 {before_counts.get(v, 0):,}", 8.5, MUTED))
        s.add(Box(x, 1.85, 1.46, 1.12, fill=TINT, geom="roundRect"), Box(x, 1.85, 1.46, 0.05, fill=VERDICT_COLOR[v]),
              text(x + 0.12, 1.92, 1.3, 1.02, *lines))
    bases = basis_counts(items)
    if bases:
        s.add(text(0.5, 3.03, 6.15, 0.3, para(Run("판정 방법   ", 9, MUTED, True),
                                               Run(" · ".join(f"{name} {k:,}" for name, k in bases), 9, TEXT))))
    heading(s, 0.5, 3.35, 6.15, "04", "그룹별 측정 정밀도", "흔들림 σ ÷ |POR| · 그룹 × 측정 LEVEL")
    table, cut = precision_table(folder)
    if table is None or table.empty:
        s.add(text(0.5, 3.9, 6.15, 0.6, para(Run(cut or "측정 정밀도 표가 없다.", 9.5, MUTED))))
    else:
        rows, cols = table.shape
        h = min(BOTTOM - 3.88 - 0.3, 0.42 + 0.27 * rows)
        w = min(6.15, 1.1 + 0.62 * cols)
        s.add(Pic(0.5, 3.88, w, h, heatmap_png(table, w, h)),
              text(0.5, 3.9 + h, 6.15, 0.3, para(Run("칸 = 그룹·LEVEL의 측정 정밀도 중앙값 · 진할수록 흔들림이 큼 · "
                                                    "허용폭 5%와 견줌" + (f" · {cut}" if cut else ""), 8, MUTED))))

    rows = undecided(items)
    heading(s, 6.95, 1.3, 5.88, "05", "미결 분석", f"미결 {len(rows):,}개 · 원인과 다음 조치")
    s.add(Box(0.5, 6.45, 12.33, 0.48, fill=TINT, geom="roundRect"),
          text(0.68, 6.45, 12.0, 0.48, para(Run("다음 조치  ", 10, NAVY, True), *next_steps(rows, counts)),
               anchor="ctr"))
    if rows.empty:
        s.add(text(6.95, 1.9, 5.88, 0.5, para(Run("미결 없음", 12, OK, True))))
        return s
    by = rows["cause"].value_counts()
    shown = [c for c in CAUSES if by.get(c.name, 0)]
    top = max(by.values)
    for j, c in enumerate(shown):
        y = 1.88 + j * 0.47
        k = int(by[c.name])
        s.add(Box(6.95, y + 0.08, 0.09, 0.3, fill=c.color),
              text(7.1, y, 1.65, 0.46, para(Run(c.name, 10, TEXT, True)), anchor="ctr"),
              text(8.75, y, 0.5, 0.46, para(Run(f"{k:,}", 13, c.color, True), align="r"), anchor="ctr"),
              Box(9.35, y + 0.15, 1.1 * k / top, 0.16, fill=c.color),
              text(10.55, y, 2.28, 0.46, para(Run(c.action, 8, MUTED)), anchor="ctr"))
    y0 = 1.95 + len(shown) * 0.47
    room = BOTTOM - y0 - 0.3
    fit = max(0, min(MAX_FOREST, int((room - 0.45) / 0.2)))
    forest = forest_rows(rows, fit)
    if not forest.empty:
        h = min(room, 0.45 + 0.2 * len(forest))
        s.add(text(6.95, y0, 5.88, 0.25, para(Run("미결 ITEM 구간 (익명 번호, 같은 구간은 한 줄)", 9, MUTED, True))),
              Pic(6.95, y0 + 0.27, 5.88, h, forest_png(forest, 5.88, h)))
    return s


def forest_rows(rows: pd.DataFrame, limit: int) -> pd.DataFrame:
    """그림에 넣을 미결 줄: 구간이 같은 ITEM 은 한 줄로 묶어 이름에 '외 n개'를 붙이고, 원인마다 돌아가며 limit 줄까지."""
    ok = rows[np.isfinite(rows["x"]) & np.isfinite(rows["y"])]
    if ok.empty or limit <= 0:
        return ok.head(0)
    key = ok["lo"].round(2).astype(str) + "|" + ok["hi"].round(2).astype(str)
    grouped = ok.assign(_k=key).groupby(["cause", "_k"], sort=False)
    merged = grouped.head(1).assign(_n=grouped["ID"].transform("size").loc[grouped.head(1).index])
    merged["ID"] = [i if n == 1 else f"{i} 외 {n - 1}개" for i, n in zip(merged["ID"], merged["_n"])]
    queues = [g for _, g in merged.groupby("cause", sort=False)]
    picked = []
    while len(picked) < limit and any(len(q) for q in queues):
        for k, q in enumerate(queues):
            if len(q) and len(picked) < limit:
                picked.append(q.iloc[0])
                queues[k] = q.iloc[1:]
    rank = {c.name: i for i, c in enumerate(CAUSES)}
    out = pd.DataFrame(picked).drop(columns=["_k", "_n"])
    return out.assign(_r=out["cause"].map(rank)).sort_values("_r", kind="stable").drop(columns="_r")


def next_steps(rows: pd.DataFrame, counts: dict[str, int]) -> list[Run]:
    """다음 조치 띠: 미결이 많은 원인 셋의 조치, 차이가 있으면 원데이터 확인."""
    runs = []
    by = rows["cause"].value_counts() if not rows.empty else pd.Series(dtype=int)
    action = {c.name: c.action.split(" · ")[-1] for c in CAUSES}
    for k, (cause, n) in enumerate(by.head(3).items(), start=1):
        runs += [Run(f"{k}  ", 10, NAVY, True), Run(f"{cause} {n:,}개", 10, TEXT, True),
                 Run(f" → {action[cause]}     ", 10, TEXT)]
    if counts.get("차이"):
        runs += [Run(f"{len(by.head(3)) + 1}  ", 10, NAVY, True), Run(f"차이 {counts['차이']:,}개", 10, TEXT, True),
                 Run(" → ITEM 그림으로 진짜 이동인지 확인", 10, TEXT)]
    return runs or [Run("미결·차이 없음", 10, TEXT)]


def build(folder: Path, before: Path | None = None, label: str | None = None) -> list[Slide]:
    items = read_items(folder / "items.csv")
    old = read_items(before) if before else None
    before_counts = verdict_counts(old) if old is not None else None
    pair = None
    if before_counts is not None:
        bad = ("미결", "차이")
        pair = (sum(before_counts[v] for v in bad), sum(verdict_counts(items)[v] for v in bad))
    note = f"숫자: {label or folder.name} · {datetime.now():%Y-%m-%d} · ITEM은 익명 번호"
    return [page_method(pair, note), page_results(label or folder.name, items, folder, before_counts, note)]


# ---------------------------------------------------------------- 미리보기 그림 (Chrome)

PX = 96                       # 인치당 px (CSS)
CHROME_PATHS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "google-chrome", "chromium")


def slide_html(slide: Slide, font: str = FONT) -> str:
    """한 쪽을 같은 좌표의 HTML 로 (미리보기 그림용). 글자 줄바꿈은 브라우저가 한다."""
    import base64
    family = f"'{font}', 'Apple SD Gothic Neo', 'Malgun Gothic', 'NanumGothic', sans-serif"
    parts, lines = [], []
    for sh in slide.shapes:
        if isinstance(sh, Line):
            head = ' marker-end="url(#arrow)"' if sh.arrow else ""
            lines.append(f'<line x1="{sh.x1 * PX}" y1="{sh.y1 * PX}" x2="{sh.x2 * PX}" y2="{sh.y2 * PX}" '
                         f'stroke="#{sh.color}" stroke-width="{sh.w * PX / 72}"{head}/>')
            continue
        pos = f"left:{sh.x * PX}px;top:{sh.y * PX}px;width:{sh.w * PX}px;height:{sh.h * PX}px"
        if isinstance(sh, Pic):
            src = base64.b64encode(sh.png).decode()
            parts.append(f'<img style="position:absolute;{pos}" src="data:image/png;base64,{src}">')
            continue
        radius = 0.06 * min(sh.w, sh.h) * PX if sh.geom == "roundRect" else (999 if sh.geom == "ellipse" else 0)
        style = (f"position:absolute;{pos};box-sizing:border-box;padding:{sh.inset * PX}px;border-radius:{radius}px;"
                 f"display:flex;flex-direction:column;justify-content:"
                 f"{dict(t='flex-start', ctr='center', b='flex-end')[sh.anchor]};"
                 + (f"background:#{sh.fill};" if sh.fill else "")
                 + (f"border:{sh.line_w * PX / 72}px solid #{sh.line};" if sh.line else ""))
        body = "".join(
            f'<p style="margin:0 0 {p.after}pt 0;text-align:{dict(l="left", ctr="center", r="right")[p.align]}">'
            + "".join(f'<span style="font-size:{r.size}pt;color:#{r.color};font-weight:{700 if r.bold else 400}">'
                      f"{escape(r.text)}</span>" for r in p.runs) + "</p>" for p in sh.paras)
        parts.append(f'<div style="{style}">{body}</div>')
    w, h = SLIDE_W * PX, SLIDE_H * PX
    svg = (f'<svg width="{w}" height="{h}" style="position:absolute;left:0;top:0">'
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" '
           'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#6B7785"/></marker></defs>' + "".join(lines) + "</svg>")
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;background:#fff}}'
            f"body{{font-family:{family};line-height:1.2;word-break:keep-all}}</style></head><body>"
            f'<div style="position:relative;width:{w}px;height:{h}px;overflow:hidden">{svg}{"".join(parts)}'
            "</div></body></html>")


def find_chrome() -> str | None:
    import shutil
    for c in CHROME_PATHS:
        if Path(c).is_file() or shutil.which(c):
            return c
    return None


def render_previews(slides: Sequence[Slide], out_prefix: Path, font: str = FONT) -> list[Path]:
    """쪽마다 <out_prefix>-slide-NN.jpg (Chrome 으로 HTML 미리보기를 찍는다). Chrome 이 없으면 빈 목록."""
    from PIL import Image
    chrome = find_chrome()
    if chrome is None:
        print("미리보기: Chrome 을 찾지 못해 건너뜀", file=sys.stderr)
        return []
    paths = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, slide in enumerate(slides, start=1):
            page = Path(tmp) / f"page{i}.html"
            page.write_text(slide_html(slide, font), encoding="utf-8")
            png = Path(tmp) / f"page{i}.png"
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--force-device-scale-factor=1.5",
                            f"--window-size={int(SLIDE_W * PX)},{int(SLIDE_H * PX)}", f"--screenshot={png}",
                            page.as_uri()], check=True, capture_output=True)
            jpg = out_prefix.parent / f"{out_prefix.name}-slide-{i:02d}.jpg"
            Image.open(png).convert("RGB").save(jpg, quality=90)
            paths.append(jpg)
    return paths


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="판정 기준 장표 2쪽 (pptx)을 판정 결과 폴더로 만든다.")
    p.add_argument("folder", help="dcc.py judge 결과 폴더 (<out>/<조합>, items.csv 가 있는 곳)")
    p.add_argument("--before", help="기존 판정 items.csv (주면 기존 → 새 판정 개수를 함께 보임)")
    p.add_argument("--out", help="pptx 경로 (기본 <폴더>/slides.pptx)")
    p.add_argument("--label", help="장표에 쓰는 데이터 이름 (기본 폴더 이름)")
    p.add_argument("--font", default=FONT, help=f"글꼴 (기본 {FONT})")
    p.add_argument("--preview", action="store_true", help="Chrome 으로 쪽마다 jpg 미리보기도 만든다")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    folder = Path(a.folder)
    if not (folder / "items.csv").is_file():
        print(f"오류: {folder / 'items.csv'} 가 없습니다. 먼저 판정하세요 (dcc.py judge).", file=sys.stderr)
        return 2
    slides = build(folder, Path(a.before) if a.before else None, a.label)
    out = write_pptx(Path(a.out) if a.out else folder / "slides.pptx", slides, a.font, "DC Test 판정 기준 개선")
    print(out)
    if a.preview:
        for p in render_previews(slides, out.with_suffix(""), a.font):
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
