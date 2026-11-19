/*
 * DC Test 동일성 검증 판정 기준 개선 - family deck (minimal_general base, 13.333 x 7.5 in)
 * Recreated with pptxgenjs.  Every slide is built by a small builder
 * function; shared visual idioms (running chrome, kickers, headings,
 * body copy, oversized numerals, clip-art icons) live in the helpers below.
 */
'use strict';

const path = require('path');
const PptxGenJS = require('pptxgenjs');

// ---------------------------------------------------------------- palette
const NAVY       = '3D4C61';   // primary brand colour
const GRAY       = '595959';   // headings / labels
const GRAY_MID   = '808080';
const GRAY_SOFT  = 'A6A6A6';   // body copy
const GRAY_PALE  = 'BFBFBF';
const GRAY_BOX   = 'D9D9D9';   // large tint panels
const WHITE      = 'FFFFFF';
const TAUPE      = '666357';
const BROWN      = '594A42';
const SCREEN     = 'EFEFEF';   // device screens
const INK        = '181818';
const INK_DEEP   = '0C0D11';
const STEEL      = 'D2D3D5';
const STEEL_DARK = 'A8A9AA';
const CASE       = '333333';

// ------------------------------------------------------------------ fonts
const POPPINS  = 'Pretendard';
const SEMI     = 'Pretendard SemiBold';
const PLAYFAIR = 'Pretendard';
const LATO     = 'Pretendard';

// The template repeats one filler sentence; body() slices it by length.
const LOREM =
  'Lorem ipsum dolor sit amet  lacus nulla ac netus nibh aliquet, porttitor ligula justo ' +
  'libero vivamus porttitor dolor conubia mollit  Sapien nam suspendisse tincidunt eget ' +
  'ante tincidunt  eros in auctor fringilla praesent at diam';

// ---------------------------------------------------------------- helpers

/** Header rule, footer rule and the four running labels shared by slides 2-34. */
function chrome(s, pageLabel) {
  s.addShape('line', { x: 2.07, y: 0.623, w: 9.707, h: 0, line: { color: NAVY, width: 0.5 } });
  s.addShape('line', { x: 0.55, y: 6.83, w: 12.075, h: 0, line: { color: NAVY, width: 0.5 } });
  const label = (x, y, w, t, size) =>
    s.addText(t, { x, y, w, h: 0.252, valign: 'top', wrap: false, fontSize: size, fontFace: POPPINS, color: GRAY });
  label(0.55, 0.49, 1.319, 'Negai Template', 10);
  label(11.946, 0.49, 0.717, pageLabel, 9);
  label(0.46, 6.907, 0.465, '2021', 9);
  label(5.89, 6.907, 1.394, 'BringmeTheDesign', 9);
  label(11.578, 6.907, 1.021, 'Lorem Ipsum', 9);
}

/** 16 pt Poppins eyebrow line that sits above every section heading. */
function kicker(s, x, y, w, text) {
  s.addText(text, { x, y, w, h: 0.37, valign: 'top', wrap: false, fontSize: 16, fontFace: POPPINS, color: GRAY });
}

/** 40 pt Poppins SemiBold section heading. */
function heading(s, x, y, w, text, color) {
  s.addText(text, {
    x, y, w, h: 0.774, valign: 'top', wrap: false,
    fontSize: 40, fontFace: SEMI, bold: true, color: color || GRAY,
  });
}

/** Oversized Playfair numeral; the original pairs it with a smaller trailing space. */
function bigNumber(s, x, y, w, h, text, color, size, spacing) {
  const sz = size || 115;
  const runOpts = { fontFace: PLAYFAIR, color: color || GRAY_MID };
  if (spacing) runOpts.charSpacing = spacing;
  s.addText([
    { text, options: Object.assign({ fontSize: sz }, runOpts) },
    { text: ' ', options: Object.assign({ fontSize: Math.round(sz * 0.766) }, runOpts) },
  ], { x, y, w, h, align: 'center', valign: 'top', wrap: false });
}

/**
 * Body copy block.  `spec` lists the runs: a positive number takes that many
 * characters from the front of LOREM, 0 is a single space, a negative number
 * takes the tail from that offset, 999 is the long double-length variant.
 * Entries may be `[len, colour]` when a block mixes colours.
 */
function body(s, x, y, w, h, spec, color, align, size) {
  const piece = (n) => (n === 0 ? ' ' : n === 999 ? LOREM.slice(0, 140) + LOREM
    : n < 0 ? LOREM.slice(-n) : LOREM.slice(0, n));
  const runs = spec.map((item) => {
    const [len, tint] = Array.isArray(item) ? item : [item, color];
    return { text: piece(len), options: { fontSize: size || 9, fontFace: LATO, color: tint } };
  });
  s.addText(runs, {
    x, y, w, h, valign: 'top', lineSpacingMultiple: 1.5,
    align: align && align !== 'left' ? align : undefined,
  });
}

/**
 * The template ships its picture frames empty - it contains no raster media at
 * all - so an unfilled frame is drawn as nothing, exactly as the original does.
 * Set SHOW_IMAGE_FRAMES to true to outline where a photo would be dropped in.
 */
const SHOW_IMAGE_FRAMES = false;
function imagePlaceholder(s, x, y, w, h) {
  if (!SHOW_IMAGE_FRAMES) return;
  s.addShape('rect', { x, y, w, h, fill: { color: GRAY_BOX }, line: { color: GRAY_PALE, width: 0.75 } });
  s.addText('[image]', {
    x, y, w, h, align: 'center', valign: 'middle', fontSize: 11, fontFace: POPPINS, color: GRAY_MID,
  });
}

// -------------------------------------------------------- drawn-icon set
// The template's artwork is vector clip-art; it is rebuilt here from
// native shapes so nothing has to be embedded as an image.

// Outline of the angular "N" monogram, as fractions of its own bounding box.
const MONOGRAM = [
  [1, 0],      [0.2745, 0.272],  [0, 0.1967], [0, 0.529],
  [0.2135, 0.5876], [0, 0.6676], [0, 1],      [0.7255, 0.728],
  [1, 0.8033], [1, 0.471],       [0.7865, 0.4124], [1, 0.3324],
];

/** The monogram, sized and centred against the brand disc that encloses it. */
function monogram(s, x, y, d, markColor) {
  const w = d * 0.411, h = d * 0.839;
  s.addShape('custGeom', {
    x: x + d * 0.294, y: y + (d - h) / 2, w, h, fill: { color: markColor }, flipH: true,
    points: MONOGRAM.map(([px, py], i) => ({ x: px * w, y: py * h, moveTo: i === 0 })).concat([{ close: true }]),
  });
}

/** Globe on a stand: sphere, meridian ring, tilt handle, post and base (slide 27). */
function globeIcon(s, x, y, w, h) {
  const ring = { fill: { type: 'none' }, line: { color: NAVY, width: 9 } };
  const d = w * 0.9;
  s.addShape('ellipse', Object.assign({ x: x + w * 0.1, y, w: d, h: d }, ring));           // meridian
  s.addShape('ellipse', Object.assign({ x, y: y + h * 0.04, w: d * 0.93, h: d * 0.93 }, ring)); // sphere
  s.addShape('line', { x, y: y + h * 0.6, w: w * 0.17, h: w * 0.17, line: { color: NAVY, width: 9 }, flipV: true });
  s.addShape('rect', { x: x + w * 0.44, y: y + h * 0.71, w: w * 0.07, h: h * 0.14, fill: { color: NAVY } });
  s.addShape('roundRect', { x: x + w * 0.2, y: y + h * 0.83, w: w * 0.62, h: h * 0.07, fill: { color: NAVY }, rectRadius: 0.5 });
}

/** Desktop monitor outline that frames the 24h badge (slide 28). */
function monitorIcon(s, x, y, w, h) {
  s.addShape('roundRect', { x, y, w, h: h * 0.78, fill: { type: 'none' }, line: { color: NAVY, width: 12 }, rectRadius: 0.07 });
  s.addShape('rect', { x: x + w * 0.44, y: y + h * 0.76, w: w * 0.12, h: h * 0.13, fill: { color: NAVY } });
  s.addShape('roundRect', { x: x + w * 0.24, y: y + h * 0.87, w: w * 0.52, h: h * 0.11, fill: { color: NAVY }, rectRadius: 0.5 });
  s.addShape('ellipse', { x: x + w * 0.79, y: y + h * 0.53, w: w * 0.09, h: w * 0.09, fill: { color: NAVY } });
}

/** "24" inside a ring whose top-right is broken by a reload arrow (slide 28). */
function clockIcon(s, x, y, w, h) {
  const d = Math.min(w, h) * 0.92;
  const cx = x + w / 2, cy = y + h * 0.56;
  s.addShape('blockArc', {
    x: cx - d / 2, y: cy - d / 2, w: d, h: d,
    fill: { color: NAVY }, angleRange: [310, 250], arcThicknessRatio: 0.13,
  });
  s.addText('24', {
    x: cx - d / 2, y: cy - d / 2, w: d, h: d, align: 'center', valign: 'middle',
    fontSize: Math.round(d * 30), fontFace: POPPINS, color: NAVY,
  });
  s.addShape('triangle', {
    x: cx + d * 0.22, y: cy - d * 0.66, w: d * 0.3, h: d * 0.26, fill: { color: NAVY }, rotate: 90,
  });
}

/** Three stacked books; the middle volume is shelved the other way round (slide 29). */
function booksIcon(s, x, y, w, h) {
  const bar = h * 0.3, gap = h * 0.35;
  for (let i = 0; i < 3; i++) {
    s.addShape('roundRect', {
      x: x + (i === 1 ? 0 : w * 0.13), y: y + i * gap, w: w * 0.87, h: bar,
      fill: { type: 'none' }, line: { color: NAVY, width: 7 }, rectRadius: 0.5,
    });
  }
}

/** Head-and-shoulders pictogram. */
function personIcon(s, x, y, w, h, color) {
  const head = w * 0.52;
  s.addShape('ellipse', {
    x: x + (w - head) / 2, y, w: head, h: head,
    fill: { type: 'none' }, line: { color, width: 4.5 },
  });
  s.addShape('round2SameRect', {
    x, y: y + h * 0.6, w, h: h * 0.4,
    fill: { type: 'none' }, line: { color, width: 4.5 }, rectRadius: 0.3,
  });
}

/** Card with a person on it (slide 32 bullet). */
function listIcon(s, x, y, w, h) {
  s.addShape('rect', { x, y, w: w * 0.82, h, fill: { type: 'none' }, line: { color: NAVY, width: 4.5 } });
  personIcon(s, x + w * 0.2, y + h * 0.22, w * 0.42, h * 0.5, NAVY);
  for (let i = 0; i < 3; i++) {
    s.addShape('rect', { x: x + w * 0.82, y: y + h * (0.15 + i * 0.28), w: w * 0.18, h: h * 0.16, fill: { color: NAVY } });
  }
}

/** Two opposed outline arrows meaning "exchange" (slide 33). */
function exchangeIcon(s, x, y, w, h) {
  const arrow = { fill: { type: 'none' }, line: { color: NAVY, width: 6 } };
  s.addShape('leftArrow', Object.assign({ x, y, w: w * 0.78, h: h * 0.42 }, arrow));
  s.addShape('rightArrow', Object.assign({ x: x + w * 0.22, y: y + h * 0.5, w: w * 0.78, h: h * 0.42 }, arrow));
}

/** Telephone handset: an open arc with a rounded pad at each end. */
function phoneIcon(s, x, y, w, h) {
  const OPEN = 225;                       // the gap in the arc faces up and right
  s.addShape('blockArc', {
    x, y, w, h, fill: { color: NAVY }, angleRange: [125, 55], arcThicknessRatio: 0.3, rotate: OPEN,
  });
  const cx = x + w / 2, cy = y + h / 2, r = w * 0.42, cw = w * 0.34, ch = h * 0.3;
  [125 + OPEN, 55 + OPEN].forEach((deg) => {
    const rad = (deg * Math.PI) / 180;
    s.addShape('roundRect', {
      x: cx + r * Math.cos(rad) - cw / 2, y: cy + r * Math.sin(rad) - ch / 2,
      w: cw, h: ch, fill: { color: NAVY }, rectRadius: 0.45, rotate: (deg + 90) % 360,
    });
  });
}

/** All-in-one desktop computer (slide 30). */
function imacDevice(s, x, y, w, h) {
  s.addShape('roundRect', { x, y, w, h: h * 0.75, fill: { color: INK }, rectRadius: 0.03 });
  s.addShape('rect', { x: x + w * 0.039, y: y + h * 0.051, w: w * 0.922, h: h * 0.648, fill: { color: INK_DEEP } });
  s.addShape('rect', { x: x + w * 0.043, y: y + h * 0.057, w: w * 0.913, h: h * 0.637, fill: { color: SCREEN } });
  s.addShape('ellipse', { x: x + w * 0.494, y: y + h * 0.021, w: 0.05, h: 0.05, fill: { color: '2C2C2C' } });
  s.addShape('rect', { x, y: y + h * 0.751, w, h: h * 0.118, fill: { color: STEEL } });
  s.addShape('rect', { x: x + w * 0.328, y: y + h * 0.851, w: w * 0.34, h: h * 0.145, fill: { color: STEEL } });
  s.addShape('rect', { x: x + w * 0.328, y: y + h * 0.851, w: w * 0.275, h: h * 0.145, fill: { color: STEEL_DARK } });
  s.addShape('roundRect', { x: x + w * 0.33, y: y + h * 0.983, w: w * 0.337, h: h * 0.017, fill: { color: INK }, rectRadius: 0.5 });
}

/** Tablet in a black case (slide 31). */
function ipadDevice(s, x, y, w, h) {
  s.addShape('roundRect', { x, y, w, h, fill: { color: CASE }, rectRadius: 0.07 });
  s.addShape('roundRect', { x: x + w * 0.006, y: y + h * 0.003, w: w * 0.989, h: h * 0.992, fill: { color: INK }, rectRadius: 0.07 });
  s.addShape('rect', { x: x + w * 0.06, y: y + h * 0.084, w: w * 0.881, h: h * 0.828, fill: { color: INK_DEEP } });
  s.addShape('rect', { x: x + w * 0.065, y: y + h * 0.087, w: w * 0.871, h: h * 0.821, fill: { color: SCREEN } });
  s.addShape('ellipse', { x: x + w * 0.49, y: y + h * 0.041, w: 0.058, h: 0.058, fill: { color: '2C2C2C' } });
  s.addShape('ellipse', { x: x + w * 0.463, y: y + h * 0.93, w: 0.24, h: 0.244, fill: { color: CASE } });
  s.addShape('ellipse', { x: x + w * 0.481, y: y + h * 0.943, w: 0.124, h: 0.124, fill: { color: INK } });
}


// ------------------------------------------------------------ slides


// ============================================================ deck content
const F = 'Pretendard';
const TXT = '262626';
const TINT = 'EEF1F5';
const LINE = 'D0D4DA';
const W = path.join(__dirname, '..');
const NUM = JSON.parse(require('fs').readFileSync(path.join(W, 'numbers.json'), 'utf8'));
function pngAR(f) { const b = require('fs').readFileSync(f); return b.readUInt32BE(16) / b.readUInt32BE(20); }
const fmt = (x, d) => x.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const DECK_LABEL = 'DC Test 판정 기준 개선 · 내부 리뷰';

function deckChrome(s, page) {
  s.addShape('line', { x: 0.5, y: 0.42, w: 12.333, h: 0, line: { color: NAVY, width: 0.5 } });
  s.addText(DECK_LABEL, { x: 0.5, y: 0.14, w: 5, h: 0.25, margin: 0, fontSize: 9, fontFace: F, color: GRAY_MID });
  s.addText(page, { x: 11.333, y: 0.14, w: 1.5, h: 0.25, margin: 0, align: 'right', fontSize: 9, fontFace: F, color: GRAY_MID });
  s.addShape('line', { x: 0.5, y: 7.08, w: 12.333, h: 0, line: { color: NAVY, width: 0.5 } });
  s.addText('Process / Test Engineering', { x: 0.5, y: 7.12, w: 4, h: 0.25, margin: 0, fontSize: 8, fontFace: F, color: GRAY_SOFT });
  s.addText('Internal', { x: 10.833, y: 7.12, w: 2, h: 0.25, margin: 0, align: 'right', fontSize: 8, fontFace: F, color: GRAY_SOFT });
}

function zoneHead(s, x, y, w, num, text) {
  s.addText([
    { text: num + '  ', options: { color: NAVY, bold: true } },
    { text, options: { color: TXT, bold: true } },
  ], { x, y, w, h: 0.28, margin: 0, fontSize: 12, fontFace: F, valign: 'bottom' });
  s.addShape('line', { x, y: y + 0.32, w, h: 0, line: { color: NAVY, width: 1 } });
}

function bullets(s, x, y, w, h, items, size) {
  const runs = items.map((t, i) => {
    const sub = Array.isArray(t);
    const text = sub ? t[0] : t;
    return { text, options: { bullet: { indent: 10 }, indentLevel: sub ? 1 : 0,
      color: sub ? GRAY : TXT, fontSize: sub ? (size || 10.5) - 1 : (size || 10.5),
      breakLine: i < items.length - 1, paraSpaceAfter: 3 } };
  });
  s.addText(runs, { x, y, w, h, margin: 0, fontFace: F, valign: 'top' });
}


function box(s, pptx, x, y, w, h, runs, fill, lineColor, dash, lw) {
  s.addText(runs, { shape: pptx.shapes.ROUNDED_RECTANGLE, x, y, w, h, rectRadius: 0.06,
    fill: { color: fill }, line: { color: lineColor, width: lw || 0.75, dashType: dash || 'solid' },
    margin: 0.03, align: 'center', valign: 'middle', fontFace: F });
}
function ln(s, pptx, x, y, w, h, color, width, opts) {
  s.addShape(pptx.shapes.LINE, Object.assign({ x, y, w, h, line: Object.assign({ color, width }, opts || {}) }));
}

function summarySlide(pptx) {
  const s = pptx.addSlide();
  s.background = { color: WHITE };
  deckChrome(s, '1 / 2');
  s.addText([
    { text: 'DC Test 동일성 검증 판정 기준 개선', options: { bold: true, color: TXT } },
    { text: '  —  Median shift·Sigma ratio → Δ·CI 판정', options: { color: NAVY } },
  ], { x: 0.5, y: 0.52, w: 12.333, h: 0.55, margin: 0, fontSize: 22, fontFace: F, valign: 'middle' });

  const TOP = 1.2;
  const LX = 0.5, LW = 5.0;
  const CX = 5.75, CW = 4.85;
  const RX = 10.85, RW = 1.983;
  const BOT = 6.1;

  // ---------- Zone 1
  zoneHead(s, LX, TOP, LW, '01', '기존 기준의 한계');
  bullets(s, LX, TOP + 0.4, LW, 0.36, [
    '기존 판정: Median shift · Sigma ratio 기준',
    '회차 간 흔들림과 LoQ 근처 노이즈 구분 불가 → 동일 조건 반복에서도 Fail 다수',
  ], 10);

  // ---------- Zone 2: flow
  const Z2 = 1.98;
  zoneHead(s, LX, Z2, LW, '02', '새 판정 흐름');
  const steps = [
    ['1', '기준 J회·비교 1회', 'die 60'],
    ['2', '흔들림 분리', 'σ_die · σ_run'],
    ['3', 'LoQ = 10σ', '구간 나누기'],
    ['4', '차이 중앙값', '90% 신뢰구간(CI)'],
    ['5', '허용 범위 Δ', '5%×기준 중앙값 + 회차 예측 한계'],
    ['6', '판정', '동등 · 차이 · 미결'],
  ];
  const gap = 0.16, bw = (LW - 2 * gap) / 3, bh = 0.46, rgap = 0.2;
  const fy = Z2 + 0.42;
  steps.forEach((st, i) => {
    const row = Math.floor(i / 3), col = i % 3;
    const bx = LX + col * (bw + gap), by = fy + row * (bh + rgap);
    const last = i === 5, key = i === 2;
    box(s, pptx, bx, by, bw, bh, [
      { text: st[0] + '  ', options: { bold: true, fontSize: 9, color: last ? WHITE : NAVY } },
      { text: st[1], options: { bold: true, fontSize: 8.5, color: last ? WHITE : TXT, breakLine: true } },
      { text: st[2], options: { fontSize: 7.5, color: last ? WHITE : GRAY } },
    ], last ? NAVY : (key ? WHITE : TINT), NAVY, 'solid', key ? 2 : 0.75);
    if (col < 2) ln(s, pptx, bx + bw + 0.02, by + bh / 2, gap - 0.04, 0, NAVY, 1, { endArrowType: 'triangle' });
  });
  const r1b = fy + bh, r2t = fy + bh + rgap, midY = r1b + rgap / 2;
  const x3 = LX + 2 * (bw + gap) + bw / 2, x4 = LX + bw / 2;
  ln(s, pptx, x3, r1b, 0, midY - r1b, NAVY, 1);
  ln(s, pptx, x4, midY, x3 - x4, 0, NAVY, 1);
  ln(s, pptx, x4, midY, 0, r2t - midY, NAVY, 1, { endArrowType: 'triangle' });

  // ---------- LoQ panel (key point)
  const PY0 = fy + 2 * bh + rgap + 0.12;   // ~3.81
  const PH = BOT - PY0;
  s.addShape(pptx.shapes.RECTANGLE, { x: LX, y: PY0, w: LW, h: PH, fill: { color: 'F4F6F9' }, line: { color: NAVY, width: 1 } });
  s.addShape(pptx.shapes.RECTANGLE, { x: LX, y: PY0, w: LW, h: 0.3, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
  s.addText([
    { text: 'KEY  ', options: { bold: true, color: 'C9D1DC', fontSize: 8.5 } },
    { text: '정량한계(LoQ, Limit of Quantitation) 판정', options: { bold: true, color: WHITE, fontSize: 10.5 } },
  ], { x: LX + 0.12, y: PY0, w: LW - 0.24, h: 0.3, margin: 0, fontFace: F, valign: 'middle' });
  const T = (t, o) => ({ text: t, options: Object.assign({ color: TXT }, o || {}) });
  const B = (t) => ({ text: t, options: { bold: true, color: NAVY } });
  s.addText([
    T('LoQ = 10σ ', { bold: true, bullet: { indent: 9 } }), T('(σ = 측정 흔들림 중 최대값) → 이 아래는 노이즈 수준, 수치 변화 신뢰 어려움', { breakLine: true }),
    T('정량 구간(≥LoQ): ', { bold: true, bullet: { indent: 9 } }), T('양측 단측검정(TOST, Two One-Sided Tests) · 90% CI가 ±Δ 안 = '), B('동등'), T(' · 밖 = '), B('차이'), T(' · 경계 걸침 = '), B('미결'), T('', { breakLine: true }),
    T('LoQ 미만 구간: ', { bold: true, bullet: { indent: 9 } }), T('CI가 ±Δ 밖이어도 비교 조건 중심(기준 중앙값 + 차이 중앙값) ≥ LoQ일 때만 '), B('차이'), T('', { breakLine: true }),
    T('중심 < LoQ → ', { bullet: { indent: 9 }, indentLevel: 1, color: GRAY }), B('동등'), T(' (사유: <LoQ 보고 일치) · 미결 없음', { color: GRAY }),
  ], { x: LX + 0.12, y: PY0 + 0.38, w: 2.8, h: PH - 0.72, margin: 0, fontSize: 9, fontFace: F, valign: 'top', paraSpaceAfter: 5 });

  // mini figures
  const FW = LW - 3.2, AX = LX + 3.08, BX = AX;
  const FH = (PH - 0.38 - 0.32 - 0.1) / 2;           // each figure incl. caption
  const FYA = PY0 + 0.38, FYB = FYA + FH + 0.1;
  const cap = (y, t) => s.addText(t, { x: AX, y, w: FW, h: 0.16, margin: 0, fontSize: 7.5, bold: true, fontFace: F, color: GRAY });
  cap(FYA, '정량 구간 TOST: 90% CI vs ±Δ');
  cap(FYB, 'LoQ 미만: ○기준 → ●비교 조건 중심');
  const FY = FYA;
  // vertical divider between text and figures
  ln(s, pptx, AX - 0.1, PY0 + 0.4, 0, PH - 0.75, LINE, 0.5);
  // (a) ±Δ band + 3 CI bars
  let gy = FYA + 0.2, gh = FH - 0.2;
  const bandX = AX + 0.3, bandW = 0.75, mid = bandX + bandW / 2;
  s.addShape(pptx.shapes.RECTANGLE, { x: bandX, y: gy, w: bandW, h: gh, fill: { color: 'E1E6ED' }, line: { color: 'E1E6ED', width: 0 } });
  ln(s, pptx, bandX, gy, 0, gh, NAVY, 0.75, { dashType: 'dash' });
  ln(s, pptx, bandX + bandW, gy, 0, gh, NAVY, 0.75, { dashType: 'dash' });
  s.addText('−Δ', { x: bandX - 0.32, y: gy, w: 0.3, h: 0.16, margin: 0, fontSize: 7, fontFace: F, color: NAVY, align: 'right' });
  s.addText('+Δ', { x: bandX + bandW + 0.02, y: gy, w: 0.3, h: 0.16, margin: 0, fontSize: 7, fontFace: F, color: NAVY });
  [[mid - 0.22, 0.44, '동등'], [bandX + bandW + 0.08, 0.36, '차이'], [bandX + bandW - 0.25, 0.5, '미결']].forEach((c, i) => {
    const yy = gy + 0.12 + i * ((gh - 0.22) / 2);
    ln(s, pptx, c[0], yy, c[1], 0, NAVY, 1.5);
    ln(s, pptx, c[0], yy - 0.045, 0, 0.09, NAVY, 1);
    ln(s, pptx, c[0] + c[1], yy - 0.045, 0, 0.09, NAVY, 1);
    s.addShape(pptx.shapes.OVAL, { x: c[0] + c[1] / 2 - 0.03, y: yy - 0.03, w: 0.06, h: 0.06, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
    s.addText(c[2], { x: AX + FW - 0.38, y: yy - 0.09, w: 0.38, h: 0.18, margin: 0, fontSize: 7.5, bold: true, fontFace: F, color: TXT, align: 'right' });
  });
  // (b) value axis + LoQ line, two cases
  gy = FYB + 0.2; gh = FH - 0.22;
  const axX = BX + 0.12, axTop = gy, axBot = gy + gh;
  ln(s, pptx, axX, axTop, 0, axBot - axTop, GRAY_MID, 0.75, { beginArrowType: 'triangle' });
  s.addText('값', { x: BX - 0.08, y: axTop - 0.02, w: 0.18, h: 0.16, margin: 0, fontSize: 7, fontFace: F, color: GRAY });
  const loqY = axTop + gh * 0.4;
  s.addShape(pptx.shapes.RECTANGLE, { x: axX, y: loqY, w: FW - 0.12, h: axBot - loqY, fill: { color: 'E1E6ED' }, line: { color: 'E1E6ED', width: 0 } });
  ln(s, pptx, axX, loqY, FW - 0.12, 0, NAVY, 1.25, { dashType: 'dash' });
  s.addText('LoQ', { x: BX + FW - 0.35, y: loqY + 0.02, w: 0.35, h: 0.15, margin: 0, fontSize: 7, bold: true, fontFace: F, color: NAVY, align: 'right' });
  const caseDraw = (cx, endY, label) => {
    const baseY = axBot - 0.05;
    ln(s, pptx, cx, endY + 0.04, 0, baseY - endY - 0.04, NAVY, 1, { beginArrowType: 'triangle' });
    s.addShape(pptx.shapes.OVAL, { x: cx - 0.04, y: baseY - 0.04, w: 0.08, h: 0.08, fill: { color: WHITE }, line: { color: GRAY_MID, width: 1 } });
    s.addShape(pptx.shapes.OVAL, { x: cx - 0.045, y: endY - 0.045, w: 0.09, h: 0.09, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
    s.addText(label, { x: cx + 0.07, y: endY - 0.09, w: 0.4, h: 0.18, margin: 0, fontSize: 7.5, bold: true, fontFace: F, color: TXT });
  };
  caseDraw(axX + 0.35, loqY + 0.12, '동등');
  caseDraw(axX + 0.9, axTop + 0.08, '차이');
  // 출처 (SOP v4.1 citations only)
  s.addText([
    { text: '출처  ', options: { bold: true, color: NAVY } },
    { text: 'LoQ = 10σ: Eurachem Guide (2014) §6.2.4 · ICH Q2(R2) §3.2.3.3  |  TOST: Schuirmann (1987)  |  σ 최대값 규칙 · LoQ 미만 판정: ', options: { color: GRAY } },
    { text: '내부 기준', options: { bold: true, color: TXT } },
  ], { x: LX + 0.12, y: BOT - 0.33, w: LW - 0.24, h: 0.3, margin: 0, fontSize: 7, fontFace: F, valign: 'middle' });

  // ---------- Zone 3: table
  zoneHead(s, CX, TOP, CW, '03', '동일 조건 반복 검증 결과');
  s.addText('같은 조건 반복을 새 기준으로 판정  ·  이상적 결과는 전부 동등', {
    x: CX, y: TOP + 0.42, w: CW, h: 0.26, margin: 0, fontSize: 10, fontFace: F, color: GRAY });
  const H = (t, o) => ({ text: t, options: Object.assign({ bold: true, color: WHITE, fill: { color: NAVY }, align: 'center', valign: 'middle', fontSize: 8 }, o || {}) });
  const H2 = (t) => H(t, { fill: { color: '5A6A80' } });
  const C = (t, o) => ({ text: t, options: Object.assign({ align: 'center', valign: 'middle', color: TXT, fontSize: 8.5 }, o || {}) });
  const TT = (t) => C(t, { bold: true, fill: { color: TINT }, color: NAVY, fontSize: 11 });
  const rows = [
    ['구분', 'ITEM 수', '동등', '차이', '미결'].map((t) => H(t, { fontSize: 8.5 })),
    [C('신규 기준 판정', { bold: true, align: 'left' }), C('정훈님 데이터 확인 후 입력', { colspan: 2, color: GRAY_MID, fontSize: 8 }),
      TT(String(NUM.verdict['차이'])), TT(String(NUM.verdict['미결']))],
  ];
  const tY = TOP + 0.78;
  s.addTable(rows, { x: CX, y: tY, w: CW, colW: [1.45, 0.95, 0.95, 0.75, 0.75], rowH: [0.32, 0.44], fontFace: F, margin: 0.04,
    border: { type: 'solid', pt: 0.5, color: LINE } });
  // forest chart of the 11 real Fails (charts.py)
  const IY = tY + 0.9, IW = CW, IH = IW / pngAR(path.join(W, 'charts/s1_forest.png'));
  s.addText('Fail ' + NUM.n + '건: 차이 중앙값 · 90% 신뢰구간(CI) vs 허용 범위 ±Δ', { x: CX, y: IY, w: CW, h: 0.24, margin: 0, fontSize: 9.5, bold: true, fontFace: F, color: GRAY });
  s.addImage({ path: path.join(W, 'charts/s1_forest.png'), x: CX, y: IY + 0.28, w: IW, h: IH });

  // ---------- Zone 4: Fail 분석
  zoneHead(s, RX, TOP, RW, '04', 'Fail 분석');
  s.addText('진짜 Fail인지 보는 논리', { x: RX, y: TOP + 0.42, w: RW, h: 0.25, margin: 0, fontSize: 9.5, bold: true, fontFace: F, color: GRAY });
  const diffs = NUM.items.filter((r) => r.group === '차이');
  const maxGap = Math.max(...diffs.map((r) => r.por_gap_pct));
  const reasons = [
    ['차이 = 비교 회차 단독 이동', NUM.verdict['차이'] + ' / ' + NUM.n, '기준 조건 2회 차 ' + Math.ceil(maxGap) + '% 미만 · 비교 조건만 이동 · CI 전체가 Δ 밖', 17],
    ['애매한 것은 미결로 보류', NUM.verdict['미결'] + '건', 'CI가 Δ 경계에 걸침 → 차이로 세지 않음 (과잉 Fail 없음)', 17],
    ['미결 중 기준 조건 흔들림', NUM.group['미결-기준'] + ' / ' + NUM.verdict['미결'], '기준 회차 간 차이 · 중앙값 불일치 → 재측정 대상', 17],
    ['계산 확인 필요', 'sigma_run = 0', '회차 간 표준편차 0 → Δ = 중앙값 5%뿐 (추정: 회차 흔들림 미반영)', 14],
  ];
  const RY0 = TOP + 0.75, RH = (BOT - RY0) / 4;
  reasons.forEach((r, i) => {
    const yy = RY0 + i * RH;
    s.addText([
      { text: (i + 1) + '  ', options: { color: NAVY, bold: true } },
      { text: r[0], options: { color: TXT, bold: true } },
    ], { x: RX, y: yy, w: RW, h: 0.3, margin: 0, fontSize: 9.5, fontFace: F, valign: 'top' });
    s.addText(r[1], { x: RX, y: yy + 0.3, w: RW, h: 0.36, margin: 0, fontSize: r[3], bold: true, fontFace: F, color: NAVY, valign: 'middle' });
    s.addText(r[2], { x: RX, y: yy + 0.66, w: RW, h: 0.34, margin: 0, fontSize: 8.5, fontFace: F, color: GRAY, valign: 'top' });
    if (i < 3) ln(s, pptx, RX, yy + RH - 0.04, RW, 0, 'E6E8EC', 0.75);
  });

  // ---------- Zone 5: 결론
  const ZY = 6.25, ZH = 0.66;
  s.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: ZY, w: 12.333, h: ZH, fill: { color: TINT }, line: { color: TINT, width: 0 } });
  s.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: ZY, w: 0.08, h: ZH, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
  s.addText('05  결론', { x: 0.75, y: ZY, w: 1.0, h: ZH, margin: 0, fontSize: 12, bold: true, fontFace: F, color: NAVY, valign: 'middle' });
  s.addText('신규 기준의 차이 = 비교 회차 단독 이동(진짜 Fail) · 애매한 것은 미결로 보류', {
    x: 1.75, y: ZY, w: 7.8, h: ZH, margin: 0, fontSize: 13, bold: true, fontFace: F, color: TXT, valign: 'middle' });
  s.addText([
    { text: '동등률  ', options: { color: GRAY } }, { text: '확인 필요', options: { bold: true, color: GRAY_MID, breakLine: true } },
    { text: '주원인  ', options: { color: GRAY } }, { text: '비교 회차 단독 이동', options: { bold: true, color: NAVY } },
  ], { x: 9.6, y: ZY, w: 3.1, h: ZH, margin: 0, fontSize: 10.5, fontFace: F, valign: 'middle', align: 'right' });
}

function reviewSlide(pptx) {
  const s = pptx.addSlide();
  s.background = { color: WHITE };
  deckChrome(s, '2 / 2');
  s.addText([
    { text: '실제 Fail ' + NUM.n + '건 검토', options: { bold: true, color: TXT } },
    { text: '  —  차이 ' + NUM.verdict['차이'] + '건은 진짜 이동, 미결 ' + NUM.verdict['미결'] + '건은 보류', options: { color: NAVY } },
  ], { x: 0.5, y: 0.52, w: 12.333, h: 0.5, margin: 0, fontSize: 22, fontFace: F, valign: 'middle' });
  s.addText([
    { text: '●', options: { color: '7F8C9F' } }, { text: ' 기준 조건 1회(POR1)    ', options: { color: GRAY } },
    { text: '■', options: { color: '7F8C9F' } }, { text: ' 기준 조건 2회(POR2)    ', options: { color: GRAY } },
    { text: '◆', options: { color: 'B5523B' } }, { text: ' 비교 조건(DOE)    ', options: { color: GRAY } },
    { text: '▇', options: { color: 'E1E6ED' } }, { text: ' 허용 범위 ±Δ  ·  값 = 기준 중앙값 대비 %  ·  CI = 90% 신뢰구간', options: { color: GRAY } },
  ], { x: 0.5, y: 1.06, w: 12.333, h: 0.24, margin: 0, fontSize: 9, fontFace: F, valign: 'middle' });

  const it = Object.fromEntries(NUM.items.map((r) => [r.ID, r]));
  const sg = (v, d) => (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), d === undefined ? 1 : d);
  const shift = (id) => '비교 ' + sg(it[id].center_pct) + '%';
  const groups = [
    ['차이 ' + NUM.group['차이'] + '  —  기준 조건 일치, 비교 회차만 이동 (진짜 Fail)', '차이', [
      ['F31_I3475', '기준 2회 일치 · ' + shift('F31_I3475') + ' (Δ 5%) · CI 전체가 −Δ 밖 · 값이 LoQ의 ' + fmt(it.F31_I3475.median_over_loq, 1) + '배', '진짜 이동'],
      ['F65_I6106', '기준 2회 일치 · ' + shift('F65_I6106') + ' (Δ 5%) · CI 전체가 −Δ 밖 · 값이 LoQ의 ' + fmt(it.F65_I6106.median_over_loq, 1) + '배', '진짜 이동'],
    ]],
    ['미결 ' + NUM.group['미결-정상'] + '  —  기준 조건 일치, 비교 회차가 Δ 경계 (정상 보류)', '미결-정상', [
      ['F54_I5492', '기준 2회 일치 · ' + shift('F54_I5492') + ' · CI가 +Δ에 걸침', '경계 미결'],
      ['F54_I5493', '기준 2회 일치 · ' + shift('F54_I5493') + ' · CI가 −Δ에 걸침', '경계 미결'],
      ['F61_I6003', '기준 2회 일치 · ' + shift('F61_I6003') + ' · CI가 +Δ에 걸침', '경계 미결'],
      ['F59_I5574', '기준 2회 같은 값 · CI 반폭이 Δ의 ' + fmt(it.F59_I5574.half_over_d, 1) + '배 → 해상도 부족', '해상도 미결'],
    ]],
    ['미결 ' + NUM.group['미결-기준'] + '  —  기준 조건 흔들림 · 데이터 불일치 (재측정 대상)', '미결-기준', [
      ['F15_I1403', 'POR1이 POR2의 ' + fmt(it.F15_I1403.por1_over_por2, 1) + '배인데 sigma_run = 0', '기준 흔들림 · 재측정'],
      ['F23_I2064', 'POR1 · POR2 ' + fmt(it.F23_I2064.por_gap_pct, 0) + '% 차이 · 중앙값이 세 회차 평균보다 큼', '기준 흔들림 · 재측정'],
      ['F14_I1231', 'POR1 · POR2 ' + fmt(it.F14_I1231.por_gap_pct, 1) + '% 차이 · 중앙값이 세 회차 평균보다 작음', '기준 흔들림 · 재측정'],
      ['F31_I3583', '중앙값이 세 회차 평균보다 ' + fmt(it.F31_I3583.median_gap_min_pct, 0) + '~' + fmt(it.F31_I3583.median_gap_max_pct, 0) + '% 작음 (분포 튐 추정)', '데이터 확인 · 재측정'],
      ['F31_I3870', '중앙값이 세 회차 평균보다 ' + fmt(it.F31_I3870.median_gap_min_pct, 0) + '~' + fmt(it.F31_I3870.median_gap_max_pct, 0) + '% 작음 (분포 튐 추정)', '데이터 확인 · 재측정'],
    ]],
  ];
  const X = 0.5, cw = [1.2, 0.55, 3.75, 5.0, 1.833];
  const cx = cw.reduce((a, w, i) => (a.push(i ? a[i - 1] + cw[i - 1] : X), a), []);
  let y = 1.38;
  const HH = 0.5, GH = 0.28, RHH = 0.325;
  s.addShape(pptx.shapes.RECTANGLE, { x: X, y, w: 12.333, h: HH, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
  ['ITEM', '판정', '', '근거', '판단'].forEach((t, i) => t && s.addText(t, { x: cx[i] + 0.06, y, w: cw[i] - 0.12, h: HH, margin: 0, fontSize: 9.5, bold: true, color: WHITE, fontFace: F, valign: 'middle', align: i === 1 ? 'center' : 'left' }));
  s.addText('회차별 값 (기준 중앙값 대비 %)', { x: cx[2], y: y + 0.02, w: cw[2], h: 0.2, margin: 0, fontSize: 9, bold: true, color: WHITE, fontFace: F, align: 'center' });
  const axAR = pngAR(path.join(W, 'charts/s2_axis.png'));
  s.addShape(pptx.shapes.RECTANGLE, { x: cx[2] + 0.025, y: y + 0.24, w: 3.7, h: 0.24, fill: { color: WHITE }, line: { color: WHITE, width: 0 } });
  s.addImage({ path: path.join(W, 'charts/s2_axis.png'), x: cx[2] + 0.025, y: y + 0.245, w: 3.7, h: 3.7 / axAR });
  y += HH;
  const GC = { '차이': NAVY, '미결-정상': '9AA8BC', '미결-기준': 'C9A27A' };
  groups.forEach(([title, key, items]) => {
    s.addShape(pptx.shapes.RECTANGLE, { x: X, y, w: 12.333, h: GH, fill: { color: TINT }, line: { color: TINT, width: 0 } });
    s.addShape(pptx.shapes.RECTANGLE, { x: X, y, w: 0.06, h: GH, fill: { color: GC[key] }, line: { color: GC[key], width: 0 } });
    s.addText(title, { x: X + 0.15, y, w: 11, h: GH, margin: 0, fontSize: 9.5, bold: true, color: key === '차이' ? NAVY : TXT, fontFace: F, valign: 'middle' });
    y += GH;
    items.forEach(([id, why, judge]) => {
      const r = it[id];
      s.addText(id, { x: cx[0] + 0.06, y, w: cw[0] - 0.08, h: RHH, margin: 0, fontSize: 9.5, bold: key === '차이', color: TXT, fontFace: F, valign: 'middle' });
      s.addText(r.verdict, { x: cx[1], y, w: cw[1], h: RHH, margin: 0, fontSize: 9.5, bold: true, color: key === '차이' ? NAVY : GRAY, fontFace: F, valign: 'middle', align: 'center' });
      s.addImage({ path: path.join(W, 'charts/s2_row_' + id + '.png'), x: cx[2] + 0.025, y: y + (RHH - 0.3) / 2, w: 3.7, h: 0.3 });
      s.addText(why, { x: cx[3] + 0.08, y, w: cw[3] - 0.1, h: RHH, margin: 0, fontSize: 9, color: TXT, fontFace: F, valign: 'middle' });
      s.addText(judge, { x: cx[4] + 0.06, y, w: cw[4] - 0.06, h: RHH, margin: 0, fontSize: 9.5, bold: true, color: key === '차이' ? NAVY : key === '미결-정상' ? GRAY : 'A0703F', fontFace: F, valign: 'middle' });
      y += RHH;
      ln(s, pptx, X, y, 12.333, 0, 'E6E8EC', 0.5);
    });
  });

  const ZY = 6.3, ZH = 0.66;
  s.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: ZY, w: 12.333, h: ZH, fill: { color: TINT }, line: { color: TINT, width: 0 } });
  s.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: ZY, w: 0.08, h: ZH, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
  s.addText('다음 조치', { x: 0.75, y: ZY, w: 1.1, h: ZH, margin: 0, fontSize: 12, bold: true, fontFace: F, color: NAVY, valign: 'middle' });
  s.addText([
    { text: '1  ', options: { bold: true, color: NAVY } }, { text: '기준 흔들림 ' + NUM.group['미결-기준'] + '건: die 원본 분포 확인 · 재측정     ', options: { color: TXT } },
    { text: '2  ', options: { bold: true, color: NAVY } }, { text: 'sigma_run = 0 계산 확인 (추정: 회차 마진 미반영)     ', options: { color: TXT } },
    { text: '3  ', options: { bold: true, color: NAVY } }, { text: '차이 ' + NUM.verdict['차이'] + '건: LoQ 근처 값 → 재측정으로 재현 확인', options: { color: TXT } },
  ], { x: 1.85, y: ZY, w: 10.9, h: ZH, margin: 0, fontSize: 11, bold: false, fontFace: F, valign: 'middle' });
}

function build() {
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'Process / Test Engineering';
  pptx.title = 'DC Test 동일성 검증 판정 기준 개선';
  summarySlide(pptx);
  reviewSlide(pptx);
  return pptx.writeFile({ fileName: path.join(__dirname, 'build.pptx') });
}
build().then((f) => console.log('wrote', f)).catch((e) => { console.error(e); process.exit(1); });
