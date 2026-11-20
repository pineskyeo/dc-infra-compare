/*
 * Open/Short형 ITEM · log 설명 deck (5 slides, LAYOUT_WIDE 13.333 x 7.5 in)
 * 흐름: 결론(판정 막대) → 물리 커브 → 두 축 → 판정 변화 → 언제 log
 * 입력: ./numbers.json, ./charts/*.png (charts.py 생성, 숫자는 모두 numbers.json 에서만)  출력: ../dc-openshort-log.pptx
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
const N_SLIDES = 5;
const DECK_LABEL = 'DC Test · Open/Short형 ITEM 과 log 축';
const C = Object.fromEntries(NUM.cases.map((c) => [c.key, c]));
const S1 = C[NUM.s1_case];
const T = NUM.thresholds;

function pngAR(f) { const b = fs.readFileSync(f); return b.readUInt32BE(16) / b.readUInt32BE(20); }
const NA = '—';
const fmt = (x, d) => (x == null ? NA : Number(x).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
const sg = (x, d) => (x == null ? NA : (x > 0 ? '+' : x < 0 ? '−' : '') + fmt(Math.abs(x), d));
// 유효숫자 3자리, 크거나 작으면 지수형 (1.23e5)
function g(x) {
  if (x == null) return NA;
  const a = Math.abs(x);
  if (a !== 0 && (a >= 1e4 || a < 1e-2)) {
    const [m, e] = Number(x).toExponential(2).split('e');
    return (x < 0 ? '−' : '') + m.replace('-', '') + 'e' + Number(e);
  }
  return (x < 0 ? '−' : '') + String(Number(a.toPrecision(3)));
}
// CI 반폭/Δ 표기: 0.001 미만은 4장 그림과 같이 '≈0'
const ratio = (x) => (x == null ? NA : x < 0.001 ? '≈0' : x < 0.01 ? '< 0.01' : fmt(x, 2));
const pct = (x) => fmt(x * 100, 0) + '%';
const chart = (n) => path.join(W, 'charts', n);

function deckChrome(s, n) {
  s.background = { color: WHITE };
  s.addShape('line', { x: 0.5, y: 0.42, w: 12.333, h: 0, line: { color: NAVY, width: 0.5 } });
  s.addText(DECK_LABEL, { x: 0.5, y: 0.14, w: 6, h: 0.25, margin: 0, fontSize: 9, fontFace: F, color: GRAY_MID });
  s.addText(n + ' / ' + N_SLIDES, { x: 11.333, y: 0.14, w: 1.5, h: 0.25, margin: 0, align: 'right', fontSize: 9, fontFace: F, color: GRAY_MID });
  s.addShape('line', { x: 0.5, y: 7.08, w: 12.333, h: 0, line: { color: NAVY, width: 0.5 } });
  s.addText('Process / Test Engineering', { x: 0.5, y: 7.12, w: 4, h: 0.25, margin: 0, fontSize: 8, fontFace: F, color: GRAY_SOFT });
  s.addText('그림·수치는 모두 합성 데이터 (seed ' + NUM.seed + ', die ' + NUM.n_die + ' × POR ' + NUM.n_run + '회 + DOE 1회)',
    { x: 6.333, y: 7.12, w: 6.5, h: 0.25, margin: 0, align: 'right', fontSize: 8, fontFace: F, color: GRAY_SOFT });
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
  const sz = size || 10.5;
  const runs = items.map((t, i) => {
    const sub = Array.isArray(t);
    return { text: sub ? t[0] : t, options: { bullet: { indent: 10 }, indentLevel: sub ? 1 : 0,
      color: sub ? GRAY : TXT, fontSize: sub ? sz - 1 : sz, breakLine: i < items.length - 1, paraSpaceAfter: 3 } };
  });
  s.addText(runs, { x, y, w, h, margin: 0, fontFace: F, valign: 'top' });
}

function keyBar(s, pptx, label, text) {
  const ZY = 6.3, ZH = 0.66;
  s.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: ZY, w: 12.333, h: ZH, fill: { color: TINT }, line: { color: TINT, width: 0 } });
  s.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: ZY, w: 0.08, h: ZH, fill: { color: NAVY }, line: { color: NAVY, width: 0 } });
  s.addText(label, { x: 0.75, y: ZY, w: 1.2, h: ZH, margin: 0, fontSize: 12, bold: true, fontFace: F, color: NAVY, valign: 'middle' });
  s.addText(text, { x: 1.95, y: ZY, w: 10.8, h: ZH, margin: 0, fontSize: 12, bold: true, fontFace: F, color: TXT, valign: 'middle' });
}

// 그림을 (x, y, w, h) 상자 안에 비율 유지로 넣고 실제 차지한 영역을 돌려줌
function fitImage(s, name, x, y, w, h) {
  const ar = pngAR(chart(name));
  let iw = w, ih = w / ar;
  if (ih > h) { ih = h; iw = h * ar; }
  const ix = x + (w - iw) / 2;
  s.addImage({ path: chart(name), x: ix, y, w: iw, h: ih });
  return { x: ix, y, w: iw, h: ih, bottom: y + ih };
}

const HC = (t) => ({ text: t, options: { bold: true, color: WHITE, fill: { color: NAVY }, align: 'center', valign: 'middle' } });
const TC = (t, o) => ({ text: String(t), options: Object.assign({ valign: 'middle', color: TXT, align: 'center' }, o || {}) });
const vColor = (v) => (v === '동등' ? NAVY : ACCENT);
const VC = (v) => TC(v, { bold: true, color: vColor(v) });

function table(s, rows, x, y, w, colW, rowH, size) {
  s.addTable(rows, { x, y, w, colW, rowH, fontFace: F, fontSize: size, margin: 0.03,
    border: { type: 'solid', pt: 0.5, color: LINE } });
}

// ------------------------------------------------------------ 1. 결론 먼저
function verdictSlide(pptx) {
  const s = pptx.addSlide();
  deckChrome(s, 1);
  title(s, '같은 ITEM, 축만 바꾸면 판정이 바뀜', '선형 ' + S1.verdict + ' → log ' + S1.verdict_log);
  fitImage(s, 's1_verdict.png', 0.5, 1.2, 5.9, 4.95);
  const X = 6.75, CW = 6.08;
  const blocks = [
    ['01', '합성 Open/Short ITEM 1개', [
      S1.name + ': die 마진이 커브 기울기부에 퍼짐',
      'DOE 가 모든 die 마진을 같은 양만큼 이동',
      ['커브 위에서 같은 비율 이동 → 참 이동 ' + sg(NUM.s1_true_shift_pct, 1) + '% (r = ' + pct(NUM.r) + ' 안)'],
    ]],
    ['02', '선형 축', [
      'center ' + g(S1.center) + ', 90% CI [' + g(S1.ci_low) + ', ' + g(S1.ci_high) + '], Δ ' + g(S1.delta),
      'CI 반폭/Δ = ' + fmt(S1.ci_half_over_delta, 2) + ' → ' + S1.verdict,
      ['큰 die 의 절대 이동이 커서 CI 가 넓어짐'],
    ]],
    ['03', 'log 축 (judge_log, 같은 judge)', [
      'center ' + g(S1.center_log) + ', 90% CI [' + g(S1.ci_low_log) + ', ' + g(S1.ci_high_log) + '], Δ ' + g(S1.delta_log),
      'CI 반폭/Δ = ' + ratio(S1.ci_half_over_delta_log) + ' → ' + S1.verdict_log,
      ['같은 비율 이동이 die 마다 같은 폭으로 보임'],
    ]],
  ];
  const top = 1.25, bh = (6.15 - top) / blocks.length;
  blocks.forEach(([n, head, items], i) => {
    const y = top + i * bh;
    zoneHead(s, X, y, CW, n, head);
    bullets(s, X, y + 0.42, CW, bh - 0.45, items, 11);
  });
  keyBar(s, pptx, '결론', '같은 데이터·같은 판정 코드, 축만 다름 → 선형 ' + S1.verdict + ', log ' + S1.verdict_log +
    '  ·  이유는 측정 커브에서 출발 (다음 장)');
}

// ------------------------------------------------------------ 2. 왜 곡선인가 (추정)
function curveSlide(pptx) {
  const s = pptx.addSlide();
  deckChrome(s, 2);
  const P = NUM.s2;
  title(s, '왜 곡선인가 (추정)', '마진이 지수 커브를 지나면 흔들림이 값에 비례');
  const im = fitImage(s, 's2_curve.png', 0.5, 1.15, 12.333, 3.85);
  const ty = im.bottom + 0.12, cw = (12.333 - 0.4) / 3, bh = 6.2 - ty - 0.42;
  const cols = [
    ['01', '지수 커브 (추정)', [
      '컨택 저항 R = R0·exp(−k·m): 마진 줄면 급증',
      '누설 I = I0·exp(k·m): 마진 늘면 급증',
      ['완전 Open·완전 Short 에서는 값이 포화 (평탄부)'],
    ]],
    ['02', '곱셈형 산포', [
      '같은 ±σ 마진 (σ = ' + fmt(P.sigma_m, 2) + ') 이 커브를 지남',
      'm = ' + fmt(P.m_lo, 0) + ' 의 y 폭 = m = ' + fmt(P.m_hi, 0) + ' 의 ×' + fmt(P.width_ratio, 1) + ' (값 비도 ×' + fmt(P.value_ratio, 1) + ')',
      ['폭/값 = ' + fmt(P.relwidth_lo, 2) + ' 로 일정 → log 폭 ' + fmt(P.log_width_dex, 2) + ' dex 로 같음'],
    ]],
    ['03', '5 케이스 = 커브 위 위치', [
      '평탄부 양끝: 전부 Open · 전부 Short',
      '기울기부: Open 정도 차이 · Short 정도 차이',
      '두 평탄부 걸침: Open·Short 혼재',
    ]],
  ];
  cols.forEach(([n, head, items], i) => {
    const x = 0.5 + i * (cw + 0.2);
    zoneHead(s, x, ty, cw, n, head);
    bullets(s, x, ty + 0.42, cw, bh, items, 10.5);
  });
  keyBar(s, pptx, '핵심', '같은 폭의 마진 흔들림 → 값에 비례하는 흔들림 (곱셈형)  ·  기울기부 ITEM 은 log 에서 폭이 고름 (추정)');
}

// ------------------------------------------------------------ 3. 같은 데이터, 두 축
function axesSlide(pptx) {
  const s = pptx.addSlide();
  deckChrome(s, 3);
  title(s, '같은 데이터, 두 축', '선형은 꼬리·오르는 흔들림, log 는 대칭·평평');
  const im = fitImage(s, 's3_hist.png', 0.5, 1.15, 8.45, 3.55);
  const keys = NUM.cases.map((c) => c.key);
  const K = (t) => TC(t, { bold: true, color: NAVY, align: 'left' });
  const rows = [
    [HC('지표 (코드 열)'), ...keys.map((k) => HC(C[k].name))],
    [K('decades'), ...keys.map((k) => TC(fmt(C[k].decades, 1)))],
    [K('skew_lin → skew_log'), ...keys.map((k) => TC(sg(C[k].skew_lin, 1) + ' → ' + sg(C[k].skew_log, 1)))],
    [K('log_fit'), ...keys.map((k) => TC(sg(C[k].log_fit, 2)))],
    [K('bimodality_log'), ...keys.map((k) => TC(fmt(C[k].bimodality_log, 2)))],
    [K('spearman_size_jitter'), ...keys.map((k) => TC(sg(C[k].spearman_size_jitter, 2)))],
  ];
  const ty = im.bottom + 0.08;
  table(s, rows, 0.5, ty, 8.45, [1.95, 1.3, 1.3, 1.3, 1.3, 1.3], Array(rows.length).fill((6.18 - ty) / rows.length), 8);
  const RX = 9.15, RW = 12.833 - RX;
  const jm = fitImage(s, 's3_jitter.png', RX, 1.15, RW, 4.6);
  s.addText(S1.name + ' ITEM · 위 ρ 는 참고 계산 (선형 범위), 아래 ρ 는 spearman_size_jitter (코드 열)', {
    x: RX, y: jm.bottom + 0.05, w: RW, h: 0.38, margin: 0, fontSize: 8.5, fontFace: F, color: GRAY, align: 'center', valign: 'top' });
  keyBar(s, pptx, '핵심', '기울기부: 선형은 한쪽 꼬리 + 클수록 흔들림, log 는 대칭 + 흔들림 평평 (spearman_size_jitter ' +
    sg(S1.spearman_size_jitter, 2) + ')  ·  혼재는 log 에서도 두 덩어리');
}

// ------------------------------------------------------------ 4. 판정이 어떻게 바뀌나
function judgeSlide(pptx) {
  const s = pptx.addSlide();
  deckChrome(s, 4);
  const M = C.mixed;
  title(s, '판정이 어떻게 바뀌나', '케이스별 judge() · log 열 (log_columns) 그대로');
  const im = fitImage(s, 's4_ratio.png', 0.5, 1.2, 6.7, 4.95);
  const X = Math.max(im.x + im.w + 0.3, 7.4), TW = 12.833 - X;
  zoneHead(s, X, 1.2, TW, '01', '케이스별 판정');
  const rows = [
    [HC('케이스'), HC('선형 판정'), HC('log 판정'), HC('CI 반폭/Δ 선형 → log')],
    ...NUM.cases.map((c) => [TC(c.name, { align: 'left' }), VC(c.verdict), VC(c.verdict_log),
      TC(ratio(c.ci_half_over_delta) + ' → ' + ratio(c.ci_half_over_delta_log))]),
  ];
  table(s, rows, X, 1.65, TW, [TW * 0.32, TW * 0.19, TW * 0.19, TW * 0.30], Array(rows.length).fill(0.3), 9);
  const by = 1.65 + 0.3 * rows.length + 0.25;
  zoneHead(s, X, by, TW, '02', '혼재는 log 로도 안 풀림');
  const mixedNote = M.verdict_log === '동등'
    ? 'log 판정 동등이어도 Open 비율 변화는 못 잡음'
    : 'log 판정도 ' + M.verdict_log;
  bullets(s, X, by + 0.42, TW, 6.15 - by - 0.42, [
    'Open die 비율: POR ' + pct(M.open_share_por) + ' → DOE ' + pct(M.open_share_doe) + ' (die ' + M.n_flip + '개 Open → Short)',
    '판정: 선형 ' + M.verdict + ', log ' + M.verdict_log + ' → ' + mixedNote,
    ["status '" + M.status + "' (bimodality_log " + fmt(M.bimodality_log, 2) + ')'],
    'Open·Short 를 나눠 비율부터 따로 봐야 함',
  ], 10);
  keyBar(s, pptx, '핵심', '기울기부 (정도 차이): log 에서 CI 가 좁아져 판정이 바뀜  ·  평탄부: 두 축 같음  ·  혼재: 두 덩어리 → 따로');
}

// ------------------------------------------------------------ 5. 언제 log
function whenSlide(pptx) {
  const s = pptx.addSlide();
  deckChrome(s, 5);
  title(s, '언제 log 로 보나', '지표로 고르고, 판정(verdict)은 그대로');
  const LX = 0.5, LW = 6.4;
  zoneHead(s, LX, 1.2, LW, '01', '기준 (코드 상수, 기준값은 추천(검토 대상))');
  const K = (t) => TC(t, { bold: true, color: NAVY, align: 'left' });
  const L = (t) => TC(t, { align: 'left' });
  const rule = [
    [HC('지표'), HC('기준'), HC('status'), HC('할 일')],
    [K('decades · log_fit'), L('decades ≥ ' + fmt(T.log_decades_min, 0) + ' 그리고 log_fit > 0'), L("'log 후보'"), L('verdict_log 참고')],
    [K('bimodality_log'), L('> ' + fmt(T.bimodal_bc_min, 3) + ' (die ≥ ' + T.bimodal_min_die + ')'), L("'두 덩어리'"), L('log 도 안 됨, 나눠서 봄')],
    [K('spearman_size_jitter'), L('≈ 0: 상대 흔들림 일정'), L('—'), L('곱셈형 → log 가 맞음 (추정)')],
    [K('spearman_size_jitter'), L('≤ ' + sg(T.size_jitter_rho, 1) + ' / ≥ ' + sg(T.size_jitter_rho_pos, 1) + ' (die ≥ ' + T.size_jitter_min_die + ')'),
      L("'작을수록 / 클수록 흔들림'"), L('log 로도 크기 의존 남음')],
    [K('decades 작음'), L('평탄부 (전부 Open / Short)'), L('—'), L('선형 그대로')],
  ];
  table(s, rule, LX, 1.65, LW, [1.6, 1.9, 1.4, 1.5], Array(rule.length).fill(0.5), 8.5);
  const RX = 7.2, RW = 12.833 - RX;
  zoneHead(s, RX, 1.2, RW, '02', '이 데이터에 적용 (item_status 결과)');
  const rows = [
    [HC('케이스'), HC('decades'), HC('log_fit'), HC('status'), HC('권장')],
    ...NUM.cases.map((c) => [L(c.name), TC(fmt(c.decades, 1)), TC(sg(c.log_fit, 2)), L(c.status), TC(c.reco, { bold: true, color: NAVY })]),
  ];
  table(s, rows, RX, 1.65, RW, [RW * 0.24, RW * 0.13, RW * 0.13, RW * 0.24, RW * 0.26], Array(rows.length).fill(0.5), 8.5);
  const oy = 1.65 + 0.5 * Math.max(rule.length, rows.length) + 0.25;
  zoneHead(s, LX, oy, 12.333, '03', '도구 출력 위치 (run_all.py --out 아래)');
  bullets(s, LX, oy + 0.42, 12.333, 6.2 - oy - 0.42, [
    '선형·log 판정 비교: log_compare/log_compare.png (log_compare.py)',
    'ITEM 별 선형 vs log 진단: fail_evidence/items/<유형>_<ID>/log_diag.png (log 대상 ITEM 만, fail_evidence.py)',
    ['verdict 는 바뀌지 않음, log 그림은 참고'],
  ], 10);
  keyBar(s, pptx, '정리', "기울기부 'log 후보' → verdict_log 참고  ·  평탄부 → 선형 그대로  ·  '두 덩어리' → 나눠서  ·  verdict 는 바뀌지 않음");
}

function build() {
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'Process / Test Engineering';
  pptx.title = 'Open/Short형 ITEM 과 log 축';
  verdictSlide(pptx);
  curveSlide(pptx);
  axesSlide(pptx);
  judgeSlide(pptx);
  whenSlide(pptx);
  return pptx.writeFile({ fileName: OUT });
}
build().then((f) => console.log('wrote', f)).catch((e) => { console.error(e); process.exit(1); });
