#!/usr/bin/env python3
"""판정 기준 장표 2쪽 (pptx). 판정 결과 폴더를 읽어 만든다. ITEM 은 익명 ID 로만 쓴다.

  1쪽  01 기존 문제와 해결 · 02 새 판정 흐름 6단계 · 03 판정 3단계 (전체 TOST → LoQ 판정 → ITEM 유형별)
  2쪽  03 판정 길별 결과 · 04 믿을 근거 (같은 조건 t-test, 차이 확인, 허용폭 ±20%)
       05 그룹 × 측정 LEVEL 측정 정밀도 · 06 미결 원인과 조치

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

from por_doe_compare import (JUDGED, R_ABS, R_EXCLUDED, R_LIMIT, R_LINEAR, R_LOG, R_LOQ, rescaled_verdicts)

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "assets" / "pptx"
FONT = "맑은 고딕"
SLIDE_W, SLIDE_H = 13.333, 7.5          # 인치 (16:9)
EMU = 914400

NAVY, TINT, TEXT, MUTED, RULE = "3D4C61", "EEF1F5", "1F2933", "6B7785", "D5DBE3"
OK, HOLD, BAD, EXCL = "1A8754", "C27C0E", "B5523B", "9AA3AE"
VERDICTS = ("동등", "미결", "차이", "판정 제외")
VERDICT_COLOR = dict(zip(VERDICTS, (OK, HOLD, BAD, EXCL)))
JUDGED_ORDER = VERDICTS[:3]
FIRM = ("동등", "차이")
SCALES = (0.8, 1.2)                     # 허용폭 ±20%
MAX_GROUPS, MAX_LEVELS = 6, 10
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
    fig.savefig(buf, format="png", dpi=300, facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def _axes(w: float, h: float, bg: str = "FFFFFF"):
    from compare_metrics import set_font
    import matplotlib.pyplot as plt
    set_font()
    fig, ax = plt.subplots(figsize=(w, h), layout="constrained", facecolor=_hex(bg))
    ax.set_facecolor(_hex(bg))
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


def stage1_png(bg: str = "FFFFFF") -> bytes:
    """1단계: 90% 신뢰구간 대 ±Δ. bg = 그림이 놓일 상자 색."""
    fig, ax = _axes(2.3, 1.3, bg)
    ax.axvspan(-1, 1, color="#E3F1EA", zorder=0)
    for v in (-1, 1):
        ax.axvline(v, color=_hex(OK), lw=0.8, ls="--")
    _bars(ax, ((-0.55, 0.35, "동등"), (0.45, 1.55, "미결"), (1.3, 2.0, "차이")), 2.25)
    ax.set_xlim(-1.8, 2.9)
    ax.set_xticks([-1, 0, 1], ["-Δ", "0", "+Δ"])
    return _png(fig)


def stage2_png(bg: str = "FFFFFF") -> bytes:
    """2단계: DOE 수준 구간 대 LoQ. bg = 그림이 놓일 상자 색."""
    fig, ax = _axes(2.3, 1.3, bg)
    ax.axvspan(0, 1, color="#ECEFF3", zorder=0)
    ax.axvline(1, color=_hex(NAVY), lw=1.1)
    ax.text(0.5, 2.55, "'<LoQ' 보고", ha="center", fontsize=7, color=_hex(MUTED))
    _bars(ax, ((0.15, 0.7, "동등"), (0.72, 1.35, "동등"), (1.2, 1.8, "차이")), 1.95)
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


def tolerance_png(bars: Sequence[tuple[str, pd.Series]], w: float, h: float) -> bytes:
    """허용폭 배율마다 판정 비율의 100% 가로 막대 (판정 색). 칸이 넓으면 개수를 쓴다."""
    import matplotlib.pyplot as plt
    from compare_metrics import set_font
    set_font()
    fig, ax = plt.subplots(figsize=(w, h), layout="constrained")
    for y, (_, v) in enumerate(bars):
        counts, left = v.value_counts(), 0
        for name in JUDGED_ORDER:
            k = int(counts.get(name, 0))
            share = k / len(v)
            ax.barh(y, share, left=left, height=0.74, color=_hex(VERDICT_COLOR[name]), edgecolor="white", linewidth=0.8)
            if share >= 0.1:
                ax.text(left + share / 2, y, f"{k:,}", ha="center", va="center", fontsize=6.5, color="white",
                        fontweight="bold")
            left += share
    ax.set_yticks(range(len(bars)), [label for label, _ in bars], fontsize=7, color=_hex(TEXT))
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.tick_params(length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    return _png(fig)


# ---------------------------------------------------------------- 결과에서 숫자 읽기

@dataclass(frozen=True)
class Cause:
    """미결 원인. 위에서부터 처음 맞는 것."""
    name: str
    action: str
    color: str
    hit: Callable[[Mapping], bool]


CAUSES = (
    Cause("die 부족", "die 10개 미만 · die를 늘려 다시 판정", "6B7785", lambda r: r["zone"] == "die 부족"),
    Cause("측정 흔들림", "구간이 허용폭보다 넓음 · die 추가·재측정", "C27C0E", lambda r: r["y"] >= 1),
    Cause("기준 조건 흔들림", "POR 회차끼리 어긋남 · POR 재측정, 프로빙·온도 확인", "3F7CAC",
          lambda r: any(s in r["status"] for s in ("회차 흔들림", "조건 불안정"))),
    Cause("허용폭 경계", "변화가 허용폭 근처 · 재측정으로 확정, 필요하면 허용폭 검토", "B5523B", lambda r: True),
)


def read_items(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""], low_memory=False)


def final_col(items: pd.DataFrame) -> pd.Series:
    return (items["verdict_final"] if "verdict_final" in items else items["verdict"]).astype(str)


def undecided_causes(items: pd.DataFrame) -> pd.Series:
    """미결 ITEM 마다 원인 이름 (CAUSES 에서 처음 맞는 것)."""
    from plot_verdicts import map_points
    mine = final_col(items) == "미결"
    y = map_points(items)["y"][mine]
    def cause(r: Mapping, v: float) -> str:
        facts = {"zone": str(r.get("zone", "")), "basis": str(r.get("verdict_basis", "") or ""),
                 "reason": str(r.get("reason", "") or ""), "status": str(r.get("status", "") or ""),
                 "y": float(v) if pd.notna(v) else -math.inf}
        return next(c.name for c in CAUSES if c.hit(facts))
    return pd.Series([cause(r, v) for r, v in zip(items[mine].to_dict("records"), y)], dtype=object)


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


def route_table(items: pd.DataFrame) -> pd.DataFrame | None:
    """판정 길(줄, ROUTE_ORDER 순서) × 최종 판정(VERDICTS) ITEM 수. route 열이 없는 옛 결과면 None."""
    if "route" not in items:
        return None
    t = pd.crosstab(items["route"].astype(str), final_col(items)).reindex(columns=VERDICTS, fill_value=0)
    return t.loc[sorted(t.index, key=lambda r: ROUTE_ORDER.index(r) if r in ROUTE_ORDER else len(ROUTE_ORDER))]


def stage3_line(items: pd.DataFrame) -> str:
    """3단계(판정 길)가 정한 ITEM 수와 1·2단계 판정에서 바뀐 판정."""
    if not {"verdict", "verdict_basis"} <= set(items):
        return ""
    n3 = int((~items["verdict_basis"].astype(str).isin(("linear", "loq"))).sum())
    before, after = items["verdict"].astype(str), final_col(items)
    moved = pd.DataFrame({"before": before, "after": after})[before != after].value_counts()
    if moved.empty:
        return "3단계에서 바뀐 판정 없음 (모두 1·2단계 판정)"
    return f"3단계 판정 길이 정한 ITEM {n3:,} · 바뀐 판정 " + " · ".join(
        f"{a}→{b} {k:,}" for (a, b), k in moved.head(3).items())


@dataclass(frozen=True)
class Proof:
    """믿을 근거 한 줄: 큰 숫자, 주장, 풀이 한 줄, 있으면 작은 그림."""
    big: str
    claim: str
    detail: str
    chart: bytes | None = None


def judged_items(items: pd.DataFrame) -> pd.DataFrame:
    return items[final_col(items).isin(JUDGED)]


def ttest_proof(items: pd.DataFrame) -> Proof | None:
    """같은 조건(POR 회차끼리)에서도 t-test 가 유의차를 내는 비율 (회차 짝 기준)."""
    judged = judged_items(items)
    if "por_ttest_sig" not in judged:
        return None
    pairs = judged["por_ttest_sig"].astype(str).str.extract(r"^(\d+)/(\d+)$").astype(float).dropna()
    pairs = pairs[pairs[1] >= 1]
    if pairs.empty:
        return None
    k, n = int(pairs[0].sum()), int(pairs[1].sum())
    detail = f"POR 회차 짝 {k:,} / {n:,} 유의차 (우연이면 약 5%)"
    if "ttest" in judged:
        sig = judged["ttest"].astype(str) == "유의차"
        eq = int((sig & (final_col(judged) == "동등")).sum())
        detail += f" · DOE t-test 유의차 {int(sig.sum()):,}개 중 {eq:,}개는 변화가 허용폭 안 → 동등"
    return Proof(f"{100 * k / n:.0f}%", "같은 조건끼리도 t-test는 '다름'", detail)


def difference_proof(items: pd.DataFrame) -> Proof | None:
    """차이 ITEM 중 t-test 도 유의차인 수, DOE 이동이 POR 회차끼리 차의 몇 배인지 (중앙값)."""
    diff = items[final_col(items) == "차이"]
    if diff.empty or "ttest" not in diff:
        return None
    agree = int((diff["ttest"].astype(str) == "유의차").sum())
    detail, cols = "", ("center", "por_gap_over_delta", "delta")
    if set(cols) <= set(diff):
        center, gap_over_delta, delta = (pd.to_numeric(diff[k], errors="coerce") for k in cols)
        gap = gap_over_delta * delta
        ratio = (center.abs() / gap)[np.isfinite(gap) & (gap > 0)].dropna()
        if not ratio.empty:
            r = float(ratio.median())
            detail = f"DOE 이동 = POR 회차끼리 차의 {f'{r:.0f}' if r >= 10 else f'{r:.1f}'}배 (중앙값)"
    return Proof(f"{agree:,}/{len(diff):,}", "차이는 t-test로도 확인", detail)


PROOF_CHART = (2.1, 0.66)               # 허용폭 막대 그림 (인치)


def tolerance_proof(items: pd.DataFrame) -> Proof | None:
    """허용폭을 ×0.8, ×1.2 로 바꿔도 최종 판정이 그대로인 ITEM 비율. 바뀐 ITEM 은 동등↔차이와 미결 경계로 나눈다."""
    judged = judged_items(items)
    if judged.empty:
        return None
    now = final_col(judged)
    lo, hi = (rescaled_verdicts(judged, s) for s in SCALES)
    flip = pd.Series(False, index=judged.index)
    for v in (lo, hi):
        flip |= now.isin(FIRM) & v.isin(FIRM) & (v != now)
    changed = (lo != now) | (hi != now)
    n_changed, n_flip = int(changed.sum()), int(flip.sum())
    if not n_changed:
        detail = "±20%에서 바뀌는 ITEM 없음"
    else:
        detail = f"바뀌는 {n_changed:,}개 · 미결 경계 {n_changed - n_flip:,}" + (
            f" · 동등↔차이 {n_flip:,}" if n_flip else " · 동등↔차이로 뒤집히는 ITEM 없음")
    chart = tolerance_png((("×0.8", lo), ("×1", now), ("×1.2", hi)), *PROOF_CHART)
    return Proof(f"{100 * (1 - n_changed / len(judged)):.0f}%", "허용폭을 ±20% 바꿔도 같은 판정", detail, chart)


PROOFS: tuple[Callable[[pd.DataFrame], Proof | None], ...] = (ttest_proof, difference_proof, tolerance_proof)


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


ROUTE_ORDER = (R_LIMIT, R_ABS, R_LOQ, R_LOG, R_LINEAR, R_EXCLUDED)     # 2쪽 판정 길 줄 순서

PROBLEMS = (    # (기존 문제, 원인, 해결)
    ("같은 조건을 다시 재도 Fail", "회차 흔들림·잡음을 변화로 봄", "회차 흔들림 몫을 허용폭에 넣고 90% 구간으로 판정"),
    ("LoQ·0 근처에서 판정이 흔들림", "DOE 중심 한 점을 LoQ와 비교 · 0 근처는 % 허용폭이 0",
     "DOE 구간 전체를 LoQ와 비교 · 0 근처는 절대 허용폭"),
    ("모든 ITEM에 같은 % 허용폭", "값에 비례해 흔들리는 ITEM(누설 전류 등)도 선형으로 봄",
     "ITEM 유형을 자동으로 나눠 맞는 허용폭으로"),
)
FLOW = (        # (단계, 한 줄, 풀이)
    ("반복 측정", "POR J회 · DOE 1회", "같은 die 약 60개"),
    ("흔들림 분리", "σ_die  같은 die 반복", "σ_run  회차 전체 이동"),
    ("ITEM 유형 분류", "POR 값만 보고", "부호·수준·분해능·모양·척도"),
    ("변화 구간", "die별 DOE − POR", "중앙값 · 90% 신뢰구간"),
    ("허용폭 Δ · LoQ", "Δ = 5%×|POR| + 회차 몫", "LoQ = 10σ"),
    ("판정 3단계", "동등 · 미결 · 차이", "TOST → LoQ → 유형별"),
)
STAGES = (      # (이름, 대상, 그림, 규칙)
    ("전체 TOST", "모든 ITEM", stage1_png, ("90% 구간이 ±Δ 안 → 동등", "통째로 밖 → 차이", "걸침 → 미결")),
    ("LoQ 판정", "POR이 LoQ 아래인 ITEM", stage2_png,
     ("DOE 구간이 LoQ 아래·걸침 → 동등", "통째로 위 + 이동 밖 → 차이", "그 밖 → 미결")),
)
STAGE3_ROUTES = ((R_LOG, "잡음 ∝ 값 → 배율로 비교"), (R_ABS, "0 근처·계단 → ±고정값"),
                 (R_LIMIT, "측정 한계에 걸림 → 한계 밖 die만"), ("그 밖", "1·2단계 판정 그대로"))


def page_method(before: tuple[int, int] | None, note: str) -> Slide:
    s = Slide()
    chrome(s, 1, 2, "DC Test 판정 기준 개선", "Median shift·Sigma ratio → 90% 구간·허용폭 판정", note)

    heading(s, 0.5, 1.26, 12.33, "01", "기존 문제와 해결")
    w = (12.33 - 2 * 0.18) / 3
    for i, (head, why, fix) in enumerate(PROBLEMS):
        x = 0.5 + i * (w + 0.18)
        s.add(Box(x, 1.78, w, 0.9, fill=TINT, geom="roundRect"), Box(x, 1.78, 0.06, 0.9, fill=BAD),
              text(x + 0.2, 1.85, w - 0.3, 0.8, para(Run(f"{'①②③'[i]}  {head}", 11, TEXT, True), after=3),
                   para(Run(why, 8.8, MUTED), after=3), para(Run(f"→ {fix}", 9, NAVY, True))))

    heading(s, 0.5, 2.82, 12.33, "02", "새 판정 흐름", "반복 측정에서 판정까지")
    gap = 0.22
    w = (12.33 - (len(FLOW) - 1) * gap) / len(FLOW)
    for k, (name, a, b) in enumerate(FLOW):
        x = 0.5 + k * (w + gap)
        last = k == len(FLOW) - 1
        head, body, sub = ("FFFFFF", "FFFFFF", "C9D2DE") if last else (NAVY, TEXT, MUTED)
        s.add(Box(x, 3.34, w, 0.98, fill=NAVY if last else TINT, geom="roundRect"),
              text(x + 0.12, 3.41, w - 0.2, 0.9, para(Run(f"{k + 1}  {name}", 11, head, True), after=4),
                   para(Run(a, 8.6, body)), para(Run(b, 8.6, sub))))
        if not last:
            s.add(Line(x + w + 0.03, 3.83, x + w + gap - 0.03, 3.83, MUTED, 1.0, arrow=True))

    heading(s, 0.5, 4.44, 12.33, "03", "판정 3단계", "앞 단계에서 동등이면 확정 · 뒤 단계는 동등이 아닌 ITEM만")
    gap = 0.25
    w = (12.33 - 2 * gap) / 3
    for k in range(3):
        x = 0.5 + k * (w + gap)
        s.add(Box(x, 4.94, w, 1.41, fill=TINT, geom="roundRect"))
        if k < len(STAGES):
            name, who, chart, rules = STAGES[k]
            s.add(text(x + 0.14, 5.0, w - 0.28, 0.3, para(Run(f"{k + 1}  {name}", 11, NAVY, True),
                                                           Run(f"   {who}", 8.5, MUTED))),
                  Pic(x + 0.1, 5.3, 1.85, 1.85 * 1.3 / 2.3, chart(TINT)),
                  text(x + 2.05, 5.4, w - 2.15, 0.9, *(para(Run(r, 8.8, TEXT), after=2) for r in rules)),
                  Line(x + w + 0.03, 5.65, x + w + gap - 0.03, 5.65, MUTED, 1.0, arrow=True))
        else:
            s.add(text(x + 0.14, 5.0, w - 0.28, 0.3, para(Run("3  ITEM 유형별 판정", 11, NAVY, True),
                                                           Run("   1·2단계에서 동등이 아닌 ITEM", 8.5, MUTED))))
            for j, (route, how) in enumerate(STAGE3_ROUTES):
                s.add(text(x + 0.14, 5.4 + j * 0.23, w - 0.28, 0.23,
                           para(Run(route, 8.8, NAVY, True), Run(f"   {how}", 8.6, TEXT))))

    s.add(Box(0.5, 6.48, 12.33, 0.45, fill=TINT, geom="roundRect"),
          text(0.68, 6.48, 12.0, 0.45, para(Run("핵심  ", 10, NAVY, True),
                                            Run("측정 흔들림과 진짜 변화를 구간으로 가르고, 애매하면 미결로 보류, "
                                                "ITEM 성격에 맞는 허용폭으로 판정", 10, TEXT)), anchor="ctr"))
    if before:
        old, new = before
        s.add(text(8.6, 6.48, 4.1, 0.45, para(Run("같은 데이터 미결·차이  ", 9, MUTED),
                                              Run(f"기존 {old:,} → 새 {new:,}", 10, NAVY, True), align="r"),
                   anchor="ctr"))
    return s


TOP, MID = 1.25, 4.1                   # 2쪽 위·아래 칸의 제목 높이
LEFT, LEFT_W, RIGHT, RIGHT_W = 0.5, 6.15, 6.95, 5.88


def verdict_table(s: Slide, items: pd.DataFrame, before_counts: dict[str, int] | None) -> None:
    """03: 머리 줄 = 판정별 전체 개수, 그 아래 판정 길마다 판정별 개수, 맨 아래 3단계 한 줄."""
    counts, n = verdict_counts(items), len(items)
    y, cols_x = TOP + 0.47, LEFT + 1.8
    cw = (LEFT + LEFT_W - cols_x) / len(VERDICTS)
    head_h = 0.8
    s.add(Box(LEFT, y, LEFT_W, head_h, fill=TINT, geom="roundRect"),
          text(LEFT + 0.14, y, 1.6, head_h, para(Run("전체", 9, MUTED)), para(Run(f"ITEM {n:,}", 14, TEXT, True)),
               anchor="ctr"))
    for i, v in enumerate(VERDICTS):
        x = cols_x + i * cw
        share = [Run(f"{100 * counts[v] / n:.0f}%" if n else "-", 8, MUTED)]
        if before_counts is not None:
            share.append(Run(f"  기존 {before_counts.get(v, 0):,}", 7.5, MUTED))
        s.add(Box(x + 0.1, y, cw - 0.2, 0.04, fill=VERDICT_COLOR[v]),
              text(x, y + 0.06, cw, head_h - 0.08, para(Run(v, 8.5, MUTED), align="ctr"),
                   para(Run(f"{counts[v]:,}", 17, VERDICT_COLOR[v], True), align="ctr"), para(*share, align="ctr"),
                   anchor="ctr", inset=0.01))
    table = route_table(items)
    y += head_h + 0.04
    if table is None:
        s.add(text(LEFT, y, LEFT_W, 0.3, para(Run("옛 결과라 판정 길(route) 열이 없어 판정 길별 개수는 생략", 8.5, MUTED))))
        return
    row_h = 0.2
    for j, (route, row) in enumerate(table.iterrows()):
        ry = y + j * row_h
        s.add(text(LEFT + 0.14, ry, 1.15, row_h, para(Run(route, 9, TEXT, True)), anchor="ctr", inset=0.01),
              text(LEFT + 1.2, ry, 0.5, row_h, para(Run(f"{int(row.sum()):,}", 9, MUTED), align="r"), anchor="ctr",
                   inset=0.01))
        for i, v in enumerate(VERDICTS):
            k = int(row[v])
            cell = Run(f"{k:,}", 9.5, VERDICT_COLOR[v], True) if k else Run("·", 9.5, RULE, True)
            s.add(text(cols_x + i * cw, ry, cw, row_h, para(cell, align="ctr"), anchor="ctr", inset=0.01))
        s.add(Line(LEFT, ry + row_h, LEFT + LEFT_W, ry + row_h, RULE, 0.5))
    line = stage3_line(items)
    if line:
        s.add(text(LEFT, y + len(table) * row_h + 0.03, LEFT_W, 0.24, para(Run(line, 8.5, NAVY)), anchor="ctr"))


def proof_rows(s: Slide, items: pd.DataFrame) -> None:
    """04: PROOFS 중 숫자를 낼 수 있는 것만 한 줄씩 (큰 숫자 · 주장 · 풀이 · 그림)."""
    proofs = [p for p in (f(items) for f in PROOFS) if p is not None]
    if not proofs:
        s.add(text(RIGHT, TOP + 0.5, RIGHT_W, 0.4, para(Run("근거를 낼 판정 ITEM이 없다.", 9.5, MUTED))))
        return
    row_h = (MID - TOP - 0.55) / len(PROOFS)
    for j, p in enumerate(proofs):
        y = TOP + 0.5 + j * row_h
        text_w = RIGHT_W - 1.35 - (PROOF_CHART[0] + 0.1 if p.chart else 0)
        s.add(text(RIGHT, y, 1.3, row_h, para(Run(p.big, 21, NAVY, True), align="ctr"), anchor="ctr", inset=0.01),
              text(RIGHT + 1.35, y, text_w, row_h, para(Run(p.claim, 10.5, TEXT, True), after=2),
                   para(Run(p.detail, 8.3, MUTED)), anchor="ctr"))
        if p.chart:
            cw, ch = PROOF_CHART
            s.add(Pic(RIGHT + RIGHT_W - cw, y + (row_h - ch) / 2, cw, ch, p.chart))
        if j:
            s.add(Line(RIGHT, y, RIGHT + RIGHT_W, y, RULE, 0.5))


def precision_block(s: Slide, folder: Path) -> None:
    """05: 그룹 × LEVEL 측정 정밀도 열지도와 풀이 한 줄."""
    table, cut = precision_table(folder)
    y = MID + 0.48
    if table is None or table.empty:
        s.add(text(LEFT, y, LEFT_W, 0.6, para(Run(cut or "측정 정밀도 표가 없다.", 9.5, MUTED))))
        return
    rows, cols = table.shape
    h = min(BOTTOM - y - 0.38, 0.32 + 0.2 * rows)
    w = min(LEFT_W, 1.1 + 0.62 * cols)
    s.add(Pic(LEFT, y, w, h, heatmap_png(table, w, h)),
          text(LEFT, y + h + 0.02, LEFT_W, 0.36, para(Run("칸 = 그룹·LEVEL의 측정 정밀도 중앙값 · 진할수록 흔들림이 큼 · "
                                                        "허용폭 5%와 견줌" + (f" · {cut}" if cut else ""), 8, MUTED))))


def cause_rows(s: Slide, causes: pd.Series) -> None:
    """06: 미결 원인마다 이름 · 개수 · 막대 · 다음 조치."""
    y0 = MID + 0.48
    if causes.empty:
        s.add(text(RIGHT, y0, RIGHT_W, 0.5, para(Run("미결 없음", 12, OK, True))))
        return
    by = causes.value_counts()
    top = int(by.max())
    for j, c in enumerate(c for c in CAUSES if by.get(c.name, 0)):
        y, k = y0 + j * 0.42, int(by[c.name])
        s.add(Box(RIGHT, y + 0.07, 0.09, 0.28, fill=c.color),
              text(RIGHT + 0.15, y, 1.65, 0.42, para(Run(c.name, 10, TEXT, True)), anchor="ctr"),
              text(RIGHT + 1.8, y, 0.5, 0.42, para(Run(f"{k:,}", 13, c.color, True), align="r"), anchor="ctr"),
              Box(RIGHT + 2.4, y + 0.13, 1.1 * k / top, 0.16, fill=c.color),
              text(RIGHT + 3.6, y, RIGHT_W - 3.6, 0.42, para(Run(c.action, 8, MUTED)), anchor="ctr"))


def page_results(label: str, items: pd.DataFrame, folder: Path, before_counts: dict[str, int] | None,
                 note: str) -> Slide:
    s = Slide()
    chrome(s, 2, 2, "동일 조건 반복 검증 결과", f"· 결과와 근거   ({label}, ITEM {len(items):,}개)", note)
    causes = undecided_causes(items)
    heading(s, LEFT, TOP, LEFT_W, "03", "판정 결과", "ITEM 유형(판정 길)별")
    verdict_table(s, items, before_counts)
    heading(s, RIGHT, TOP, RIGHT_W, "04", "믿을 근거", "판정을 믿어도 되는 이유")
    proof_rows(s, items)
    heading(s, LEFT, MID, LEFT_W, "05", "그룹별 측정 정밀도", "흔들림 σ ÷ |POR| · 그룹 × 측정 LEVEL")
    precision_block(s, folder)
    heading(s, RIGHT, MID, RIGHT_W, "06", "미결 분석", f"미결 {len(causes):,}개 · 원인과 다음 조치")
    cause_rows(s, causes)
    s.add(Box(0.5, 6.45, 12.33, 0.48, fill=TINT, geom="roundRect"),
          text(0.68, 6.45, 12.0, 0.48, para(Run("다음 조치  ", 10, NAVY, True),
                                            *next_steps(causes, verdict_counts(items))), anchor="ctr"))
    return s


def next_steps(causes: pd.Series, counts: dict[str, int]) -> list[Run]:
    """다음 조치 띠: 미결이 많은 원인 셋의 조치, 차이가 있으면 원데이터 확인."""
    runs = []
    by = causes.value_counts()
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
