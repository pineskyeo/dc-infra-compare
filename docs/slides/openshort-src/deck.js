/*
 * Open/Short형 ITEM · log 설명 deck (4 slides, LAYOUT_WIDE 13.333 x 7.5 in)
 * v3-src/deck.js 방식: pptxgenjs, Pretendard, NAVY 3D4C61, TINT EEF1F5.
 * 입력: ./numbers.json, ./charts/*.png (charts.py 생성)  출력: ../dc-openshort-log.pptx
 */
'use strict';

const fs = require('fs');
const path = require('path');
const PptxGenJS = require('pptxgenjs');

const NAVY = '3D4C61';
const GRAY = '595959';
const GRAY_MID = '808080';
const GRAY_SOFT = 'A6A6A6';
const WHITE = 'FFFFFF';
const ACCENT = 'B5523B';
const F = 'Pretendard';
const TXT = '262626';
const TINT = 'EEF1F5';
const LINE = 'D0D4DA';
const W = __dirname;
const NUM = JSON.parse(fs.readFileSync(path.join(W, 'numbers.json'), 'utf8'));
const OUT = path.join(W, '..', 'dc-openshort-log.pptx');
const N_SLIDES = 4;
const DECK_LABEL = 'DC Test · Open/Short형 ITEM 과 log 축';

function pngAR(f) { const b = fs.readFileSync(f); return b.readUInt32BE(16) / b.readUInt32BE(20); }
const fmt = (x, d) => Number(x).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const sg = (x, d) => (x > 0 ? '+' : x < 0 ? '−' : '') + fmt(Math.abs(x), d);
const chart = (n) => path.join(W, 'charts', n);

function deckChrome(s, n) {
  s.addShape('line', { x: 0.5, y: 0.42, w: 12.333, h: 0, line: { color: NAVY, width: 0.5 } });
  s.addText(DECK_LABEL, { x: 0.5, y: 0.14, w: 6, h: 0.25, margin: 0, fontSize: 9, fontFace: F, color: GRAY_MID });
  s.addText(n + ' / ' + N_SLIDES, { x: 11.333, y: 0.14, w: 1.5, h: 0.25, margin: 0, align: 'right', fontSize: 9, fontFace: F, color: GRAY_MID });
  s.addShape('line', { x: 0.5, y: 7.08, w: 12.333, h: 0, line: { color: NAVY, width: 0.5 } });
  s.addText('Process / Test Engineering', { x: 0.5, y: 7.12, w: 4, h: 0.25, margin: 0, fontSize: 8, fontFace: F, color: GRAY_SOFT });
  s.addText('그림은 모두 합성 데이터 (seed ' + NUM.seed + ')', { x: 7.833, y: 7.12, w: 5, h: 0.25, margin: 0, align: 'right', fontSize: 8, fontFace: F, color: GRAY_SOFT });
}

function title(s, main, sub) {
  s.addText([
    { text: main, options: { bold: true, color: TXT } },
    { text: '  —  ' + sub, options: { color: NAVY } },
  ], { x: 0.5, y: 0.52, w: 12.333, h: 0.55, margin: 0, fontSize: 22, fontFace: F, valign: 'middle' });
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

function box(s, pptx, x, y, w, h, runs, fill, lineColor, lw) {
  s.addText(runs, { shape: pptx.shapes.ROUNDED_RECTANGLE, x, y, w, h, rectRadius: 0.06,
    fill: { color: fill }, line: { color: lineColor, width: lw || 0.75 },
    margin: 0.04, align: 'center', valign: 'middle', fontFace: F });
}
function ln(s, pptx, x, y, w, h, color, width, opts) {
  s.addShape(pptx.shapes.LINE, { x, y, w, h, line: Object.assign({ color, width }, opts || {}) });
}

function keyBar(s, pptx, label, text) {
  const ZY = 6.3, ZH = 0.66;
  s.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: ZY, w: 12.333, h: ZH, fill: { color: TINT }, line: { color: TINT, width: 0 } });
  s.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: ZY, w: 0.08, h: ZH, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
  s.addText(label, { x: 0.75, y: ZY, w: 1.2, h: ZH, margin: 0, fontSize: 12, bold: true, fontFace: F, color: NAVY, valign: 'middle' });
  s.addText(text, { x: 1.95, y: ZY, w: 10.8, h: ZH, margin: 0, fontSize: 12.5, bold: true, fontFace: F, color: TXT, valign: 'middle' });
}

function fullImage(s, name, y, maxH) {
  const ar = pngAR(chart(name));
  let w = 12.333, h = w / ar;
  if (h > maxH) { h = maxH; w = h * ar; }
  s.addImage({ path: chart(name), x: 0.5 + (12.333 - w) / 2, y, w, h });
  return y + h;
}

// ------------------------------------------------------------ 1. 분포 모양 5가지
function shapesSlide(pptx) {
  const s = pptx.addSlide();
  s.background = { color: WHITE };
  deckChrome(s, 1);
  title(s, 'Open/Short형 ITEM 분포 모양 5가지', '같은 ITEM 형태라도 die 값 범위가 몇 자리씩 다름');
  const bot = fullImage(s, 's1_shapes.png', 1.15, 4.3);
  const sh = Object.fromEntries(NUM.shapes.map((r) => [r.name, r]));
  const notes = [
    ['전부 Open', ['모든 die 가 높은 값에 몰림', '폭 좁음 → 선형·log 모양 비슷']],
    ['전부 Short', ['모든 die 가 낮은 값에 몰림', '폭 좁음 → 선형·log 모양 비슷']],
    ['Open 정도 차이', ['값이 ' + fmt(sh['Open 정도 차이'].decades, 1) + '자리에 걸침', '선형: 왼쪽 뭉침 + 긴 꼬리', 'log: 대칭에 가까움']],
    ['Short 정도 차이', ['값이 ' + fmt(sh['Short 정도 차이'].decades, 1) + '자리에 걸침', '작은 쪽에서 같은 현상', 'log: 대칭에 가까움']],
    ['Open·Short 혼재', ['log 에서 두 덩어리 (BC ' + fmt(sh['Open·Short 혼재'].bimodality_log, 2) + ')', '선형: 0 근처 막대 + 먼 점들', '중앙값 하나로 요약 곤란']],
  ];
  const cw = 12.333 / 5, ty = bot + 0.08;
  notes.forEach(([name, items], i) => {
    const x = 0.5 + i * cw + 0.08;
    s.addText(name, { x, y: ty, w: cw - 0.2, h: 0.24, margin: 0, fontSize: 10, bold: true, fontFace: F, color: NAVY });
    bullets(s, x, ty + 0.27, cw - 0.2, 6.2 - ty - 0.3, items, 9.5);
  });
  keyBar(s, pptx, '핵심', '폭이 좁으면 선형·log 차이 작음  ·  여러 자리에 걸치거나 두 덩어리면 log 축이어야 모양이 보임');
}

// ------------------------------------------------------------ 2. 동등이 어려운 이유
function runsSlide(pptx) {
  const s = pptx.addSlide();
  s.background = { color: WHITE };
  deckChrome(s, 2);
  const R = NUM.runs;
  title(s, '동등이 나오기 어려운 이유', '같은 die 도 회차마다 값이 배수로 바뀜');
  const bot = fullImage(s, 's2_runs.png', 1.15, 3.85);
  const ty = bot + 0.12, cw = (12.333 - 0.4) / 3, bh = 6.2 - ty - 0.4;
  const cols = [
    ['01', '회차 흔들림', [
      '반복 측정마다 마진이 변함',
      '회차 전체 값이 함께 배수로 이동',
      ['합성 설정: 회차 배수 ln σ ' + fmt(R.run_sd_ln, 2)],
    ]],
    ['02', '컨택 마진', [
      '접촉 저항이 매번 달라짐 (추정)',
      'die 마다 따로 배수로 이동',
      ['합성: 같은 die 최대/최소 중앙 ×' + fmt(R.same_die_fold_median, 1) + ', 최대 ×' + fmt(R.same_die_fold_max, 1)],
    ]],
    ['03', '선형 Δ 와 맞지 않음', [
      'Δ = r·|중앙값| (r = ' + fmt(R.r * 100, 0) + '%) → 중앙값 몇 % 이동만 허용',
      '배수 변화 앞에서는 같은 조건끼리도 Δ 밖',
      ['합성 ITEM ' + R.n_item + '개 중 ±Δ 안 ' + fmt(R.inside_delta_frac * 100, 0) + '% · 이동 중앙 ' + fmt(R.median_abs_shift_pct, 0) + '%'],
    ]],
  ];
  cols.forEach(([n, head, items], i) => {
    const x = 0.5 + i * (cw + 0.2);
    zoneHead(s, x, ty, cw, n, head);
    bullets(s, x, ty + 0.42, cw, bh, items, 10.5);
  });
  keyBar(s, pptx, '핵심', '회차·접촉 흔들림이 배수로 들어옴 → 같은 조건 반복도 선형 Δ = r·|중앙값| 안에 들기 어려움');
}

// ------------------------------------------------------------ 3. log 가 맞는 이유
function logSlide(pptx) {
  const s = pptx.addSlide();
  s.background = { color: WHITE };
  deckChrome(s, 3);
  const L = NUM.linlog;
  title(s, 'log 가 맞는 이유', '곱 구조라 log 에서 흔들림이 고르게 됨');
  const LX = 0.5, LW = 3.85, top = 1.2;
  const blocks = [
    ['01', '곱 구조', [
      '값 = die 고유값 × 회차 배수 × 접촉 배수',
      '저항·누설이 배수로 변함 (추정)',
    ]],
    ['02', '오차가 값에 비례', [
      '큰 die 는 크게, 작은 die 는 작게 흔들림',
      '선형: spearman_size_jitter ρ = ' + sg(L.spearman_size_jitter_lin, 2) + ' (클수록 흔들림)',
    ]],
    ['03', 'log 에서 곱 → 합', [
      'log(값) = log(고유값) + log(배수)',
      '흔들림 폭이 크기와 무관 → ρ = ' + sg(L.spearman_size_jitter_log, 2),
    ]],
    ['04', '분포도 대칭으로', [
      'skew_lin ' + sg(L.skew_lin, 1) + ' → skew_log ' + sg(L.skew_log, 1),
      'log_fit = ' + sg(L.log_fit, 2) + ' > 0, decades ' + fmt(L.decades, 1) + ' → log 후보',
    ]],
  ];
  const bh = (6.15 - top) / blocks.length;
  blocks.forEach(([n, head, items], i) => {
    const y = top + i * bh;
    zoneHead(s, LX, y, LW, n, head);
    bullets(s, LX, y + 0.42, LW, bh - 0.45, items, 10);
  });
  const ar = pngAR(chart('s3_linlog.png'));
  const IX = 4.6, IW = 12.833 - IX, IH = Math.min(IW / ar, 4.75);
  const iw = IH * ar;
  s.addImage({ path: chart('s3_linlog.png'), x: IX + (IW - iw) / 2, y: top, w: iw, h: IH });
  s.addText('같은 합성 데이터: die ' + NUM.n_die + ' × ' + L.n_run + '회, 접촉 배수 ln σ ' + fmt(NUM.runs.contact_sd_ln, 2) +
    '  ·  위: 크기-흔들림 산점도, 아래: die 값 분포', {
    x: IX, y: top + IH + 0.03, w: IW, h: 0.24, margin: 0, fontSize: 8.5, fontFace: F, color: GRAY, align: 'center' });
  keyBar(s, pptx, '핵심', '흔들림이 값에 비례하면 log 에서 고르게 됨 → 같은 기준(배수 Δ)을 크기와 무관하게 적용 가능 (추정)');
}

// ------------------------------------------------------------ 4. 지표로 판단하는 법
function indexSlide(pptx) {
  const s = pptx.addSlide();
  s.background = { color: WHITE };
  deckChrome(s, 4);
  title(s, '지표로 판단하는 법', 'log 후보는 표시만, 판정은 그대로');
  const TX = 0.5, TW = 7.25, top = 1.2;
  zoneHead(s, TX, top, TW, '01', '지표 표  (기준값은 모두 추천(검토 필요))');
  const H = (t) => ({ text: t, options: { bold: true, color: WHITE, fill: { color: NAVY }, align: 'center', valign: 'middle', fontSize: 9 } });
  const C = (t, o) => ({ text: t, options: Object.assign({ valign: 'middle', color: TXT, fontSize: 8.5 }, o || {}) });
  const K = (t) => C(t, { bold: true, color: NAVY, fontFace: 'Consolas' });
  const rows = [
    ['열 이름', '정의', '기준값', '뜻'].map(H),
    [K('spearman_size_jitter'), C('die 크기 vs 회차 흔들림 순위 상관 ρ'), C('ρ ≤ −0.5 / ρ ≥ +0.5\ndie ≥10'), C("'작을수록 흔들림' / '클수록 흔들림'")],
    [K('decades'), C('log10(max|x| / min|x|)'), C('≥ 2'), C('값이 두 자리 이상에 걸침')],
    [K('skew_lin · skew_log'), C('선형 값 · log 값의 왜도'), C('—'), C('0 에 가까울수록 대칭')],
    [K('log_fit'), C('|skew_lin| − |skew_log|'), C('> 0'), C('log 쪽이 대칭')],
    [K('bimodality_log'), C('log 값의 BC'), C('> 0.555\ndie ≥10'), C("'두 덩어리'")],
    [C("'log 후보'", { bold: true, color: NAVY }), C('decades 와 log_fit 조합'), C('decades ≥2\n그리고 log_fit > 0'), C('log 축으로 보기 권장')],
    [C('판정 제외', { bold: true, color: ACCENT }), C('σ_die = 0 또는 고정값 비율 > 50%'), C('해당 시'), C('verdict 만 판정 제외, status 는 계산됨')],
    [K('verdict_log'), C('log 축으로 낸 판정'), C('참고'), C('verdict(판정)는 불변')],
  ];
  s.addTable(rows, { x: TX, y: top + 0.45, w: TW, colW: [1.85, 2.2, 1.45, 1.75],
    rowH: [0.3, 0.52, 0.42, 0.42, 0.42, 0.52, 0.52, 0.52, 0.42], fontFace: F, margin: 0.05,
    border: { type: 'solid', pt: 0.5, color: LINE } });

  // ---- 흐름도
  const FX = 8.15, FW = 4.683, MW = 2.75, SX = FX + MW + 0.38, SW = FX + FW - SX;
  zoneHead(s, FX, top, FW, '02', '흐름도');
  const steps = [
    ['ITEM die 값 (die ≥10 권장)', null, 'start'],
    ['σ_die = 0 또는\n고정값 비율 > 50%?', '판정 제외\n(산포 0)', 'exit'],
    ['decades ≥ 2 그리고\nlog_fit > 0?', "'log 후보' 표시", 'flag'],
    ['bimodality_log > 0.555\n(die ≥10)?', "'두 덩어리' 표시", 'flag'],
    ['spearman_size_jitter\nρ ≤ −0.5 또는 ≥ +0.5 (die ≥10)?', "'작을수록 / 클수록\n흔들림' 표시", 'flag'],
    ['verdict_log 는 참고로 같이 봄\n판정(verdict) 불변', null, 'end'],
  ];
  const y0 = top + 0.5, bh = 0.6, gap = (6.15 - y0 - steps.length * bh) / (steps.length - 1);
  steps.forEach(([q, side, kind], i) => {
    const y = y0 + i * (bh + gap);
    const end = kind === 'end';
    box(s, pptx, FX, y, MW, bh, [{ text: q, options: { fontSize: 8.5, bold: kind !== 'flag' && kind !== 'exit' ? true : false, color: end ? WHITE : TXT } }],
      end ? NAVY : kind === 'start' ? WHITE : TINT, NAVY, kind === 'start' ? 1.5 : 0.75);
    if (i < steps.length - 1) {
      ln(s, pptx, FX + MW / 2, y + bh, 0, gap, NAVY, 1, { endArrowType: 'triangle' });
      const lbl = kind === 'exit' ? '아니오' : kind === 'flag' ? '계속' : '';
      if (lbl) s.addText(lbl, { x: FX + MW / 2 + 0.06, y: y + bh, w: 0.8, h: gap, margin: 0, fontSize: 7.5, fontFace: F, color: GRAY, valign: 'middle' });
    }
    if (side) {
      ln(s, pptx, FX + MW, y + bh / 2, SX - FX - MW, 0, kind === 'exit' ? ACCENT : NAVY, 1, { endArrowType: 'triangle' });
      s.addText('예', { x: FX + MW + 0.02, y: y + bh / 2 - 0.2, w: 0.34, h: 0.18, margin: 0, fontSize: 7.5, fontFace: F, color: GRAY, align: 'center' });
      box(s, pptx, SX, y + 0.04, SW, bh - 0.08, [{ text: side, options: { fontSize: 8.5, bold: true, color: kind === 'exit' ? ACCENT : NAVY } }],
        WHITE, kind === 'exit' ? ACCENT : NAVY, 1);
    }
  });
  keyBar(s, pptx, '핵심', "산포 0 은 판정 제외  ·  'log 후보' 는 decades ≥2 그리고 log_fit > 0  ·  verdict_log 는 참고, 판정 불변");
}

function build() {
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'Process / Test Engineering';
  pptx.title = 'Open/Short형 ITEM 과 log 축';
  shapesSlide(pptx);
  runsSlide(pptx);
  logSlide(pptx);
  indexSlide(pptx);
  return pptx.writeFile({ fileName: OUT });
}
build().then((f) => console.log('wrote', f)).catch((e) => { console.error(e); process.exit(1); });
