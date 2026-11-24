// 장면: steps-b 담당 (④ 변화 구간 · ⑤ 허용폭 Δ · ⑥ 판정 3단계 · ⑦ 다음 행동). 도우미는 assets/sop.js 의 window.SOP.
(() => {
  'use strict';
  const { defineScene, h, s, fmt, pill, scale, domain, VCLASS, TRACK } = window.SOP;
  const W = 720;
  const BASIS = {
    linear: '1단계 TOST', loq: '2단계 LoQ 판정', log: '3단계 · log TOST', abs: '3단계 · 절대 허용폭',
    accuracy: '3단계 · 장비 정확도 폭', limit: '3단계 · 한계 비교'
  };

  // ---------- 글자 자리 ----------
  // 그림을 그리기 전이라 글자 폭을 잴 수 없어 어림한다 (한글 1em, 그 밖 0.62em)
  function textWidth(str, size) {
    let w = 0;
    for (const ch of String(str)) w += /[ᄀ-ᇿ㄰-㆏가-힣]/.test(ch) ? size : size * 0.62;
    return w;
  }
  // 글자를 후보 자리({x, y, a: start|middle|end})에 차례로 대 보고, 이미 놓인 글자·선·막대와 겹치지 않는 첫 자리에 둔다.
  // 다 겹치면 optional 은 버리고, 아니면 첫 자리에 둔다 (흰 테두리가 밑의 선을 가린다)
  function labeler(xmin, xmax) {
    const boxes = [];
    const hit = b => boxes.some(o => b.x0 < o.x1 && o.x0 < b.x1 && b.y0 < o.y1 && o.y0 < b.y1);
    function block(x0, x1, y0, y1) { boxes.push({ x0: Math.min(x0, x1), x1: Math.max(x0, x1), y0, y1 }); }
    function text(str, spots, cls, opt) {
      const size = (opt && opt.size) || 13;
      const w = textWidth(str, size) + 4;
      const boxOf = sp => {
        const x0 = sp.a === 'start' ? sp.x : sp.a === 'end' ? sp.x - w : sp.x - w / 2;
        return { x0, x1: x0 + w, y0: sp.y - size * 0.85, y1: sp.y + size * 0.25 };
      };
      const clamp = sp => {
        const b = boxOf(sp);
        return { ...sp, x: sp.x + Math.max(0, xmin - b.x0) - Math.max(0, b.x1 - xmax) };
      };
      let pick = spots.map(clamp).find(sp => !hit(boxOf(sp)));
      if (!pick) {
        if (opt && opt.optional) return null;
        pick = clamp(spots[0]);
      }
      boxes.push(boxOf(pick));
      return s('text', { x: pick.x, y: pick.y, 'text-anchor': pick.a, class: `${cls} halo` }, str);
    }
    return { block, text };
  }
  const around = (x, y) => [{ x, y, a: 'middle' }, { x, y, a: 'end' }, { x, y, a: 'start' }];

  function pct(r, signed) {
    const v = Number((r * 100).toPrecision(2));
    return `${signed && v > 0 ? '+' : ''}${v}%`.replace('-', '−');
  }
  const ratio = L => 10 ** L - 1;

  // 판정을 정한 숫자 (plot_verdicts.map_points 와 같은 고름): log 판정이면 log 구간과 Δ_log, 아니면 구간과 판정에 쓴 폭
  function basisNumbers(t) {
    if (t.final.basis === 'log' && t.step4.log) {
      const g = t.step4.log;
      return { lo: g.ci_low, hi: g.ci_high, tol: t.step5.delta_log, log: true };
    }
    return { lo: t.step4.ci_low, hi: t.step4.ci_high, tol: t.step5.used.value, log: false };
  }

  // ---------- 가운데 0, ±폭 띠, 그 위의 구간 막대 (⑤ · ⑥) ----------
  // r: lo, hi, c (구간과 가운데), tol (띠 반폭), name (띠 이름), ciName, show (값 → 글자), ghost (점선으로 겹쳐 보일 다른 폭)
  function bandRow(y, r, b, x0 = 176, x1 = 700) {
    const vals = [-r.tol, r.tol, 0];
    if (r.lo !== undefined) vals.push(r.lo, r.hi);
    if (r.ghost) vals.push(-r.ghost, r.ghost);
    let [d0, d1] = domain(vals, 0.12);
    const hasCi = r.lo !== undefined;
    const ciText = hasCi ? `${r.ciName} ${r.show(r.lo, true)} ~ ${r.show(r.hi, true)}` : '';
    // 구간이 띠 밖에 통째로 있으면 그 바깥쪽에 구간 이름이 들어갈 만큼 축을 늘린다
    const room = (x1 - x0) / (x1 - x0 - textWidth(ciText, 13) - 10);
    if (hasCi && r.lo > r.tol) d1 = Math.max(d1, d0 + (r.lo - d0) * room);
    if (hasCi && r.hi < -r.tol) d0 = Math.min(d0, d1 - (d1 - r.hi) * room);
    const x = scale(d0, d1, x0, x1);
    const L = labeler(x0 - 8, x1 + 16);
    const edges = [-r.tol, r.tol].map(v => x(v));
    edges.forEach(e => L.block(e - 1, e + 1, y + 24, y + 88));
    if (hasCi) L.block(Math.min(x(r.lo), x(r.hi) - 4), Math.max(x(r.hi), x(r.lo) + 4), y + 55, y + 67);

    const nameW = textWidth(`+${r.name}`, 13);
    const names = edges[1] - edges[0] > nameW + 10
      ? [L.text(`−${r.name}`, around(edges[0], y + 18), 'sc-t eq'), L.text(`+${r.name}`, around(edges[1], y + 18), 'sc-t eq')]
      : [L.text(`±${r.name}`, around(x(0), y + 18), 'sc-t eq')];
    const lowT = r.show(-r.tol, false), highT = r.show(r.tol, true);
    const valW = Math.max(textWidth(lowT, 13), textWidth(highT, 13));
    const values = edges[1] - edges[0] > valW + 10
      ? [L.text(lowT, around(edges[0], y + 102), 'sc-t'), L.text(highT, around(edges[1], y + 102), 'sc-t')]
      : [L.text(lowT === `−${highT.slice(1)}` ? `±${highT.slice(1)}` : `${lowT} ~ ${highT}`, around(x(0), y + 102), 'sc-t')];
    let ci = null;
    if (hasCi) {
      const mid = (x(r.lo) + x(r.hi)) / 2;
      ci = L.text(ciText, [
        ...(r.lo > r.tol ? [{ x: x(r.lo), y: y + 46, a: 'start' }] : r.hi < -r.tol ? [{ x: x(r.hi), y: y + 46, a: 'end' }] : []),
        ...around(mid, y + 46), { x: x(r.hi), y: y + 46, a: 'start' }, { x: x(r.lo), y: y + 46, a: 'end' },
        ...around(mid, y + 18), ...around(mid, y + 102)], 'sc-t doe');
    }
    const zero = L.text('0', [{ x: x(0), y: y + 102, a: 'middle' }], 'sc-t', { optional: true });
    const ghost = r.ghost ? s('rect', {
      x: x(-r.ghost), y: y + 34, width: Math.max(2, x(r.ghost) - x(-r.ghost)), height: 44, rx: 4, class: 'b-ghost'
    }) : null;
    return s('g', { 'data-b': b }, [
      s('line', { x1: x0, x2: x1, y1: y + 61, y2: y + 61, class: 'sc-axis' }),
      s('rect', { x: edges[0], y: y + 28, width: Math.max(2, edges[1] - edges[0]), height: 56, rx: 8, class: 'sc-band grow' }),
      ghost,
      ...edges.map(e => s('line', { x1: e, x2: e, y1: y + 24, y2: y + 88, class: 'sc-edge' })),
      s('line', { x1: x(0), x2: x(0), y1: y + 52, y2: y + 70, class: 'sc-zero' }),
      ...names, ...values, zero,
      hasCi ? s('g', { class: 'late' }, [
        s('rect', { x: Math.min(x(r.lo), x(r.hi) - 4), y: y + 56, width: Math.max(4, x(r.hi) - x(r.lo)), height: 10, rx: 5, class: 'sc-ci' }),
        s('circle', { cx: x(r.c), cy: y + 61, r: 4.5, class: 'sc-c' }),
        ci]) : null
    ]);
  }
  const linearShow = unit => (v, signed) => fmt(v, signed, unit);
  const ratioShow = (v, signed) => pct(ratio(v), signed);

  // ---------- ④ 변화 구간: d 를 줄 세우고 양끝에서 k번째 두 값이 90% 구간 ----------
  function binomCdf(n, k) {           // P(B ≤ k), B ~ 이항(n, ½)
    let term = 0.5 ** n, sum = 0;
    for (let i = 0; i <= k; i++) { sum += term; term = term * (n - i) / (i + 1); }
    return sum;
  }
  function coverage(n, k) { return 1 - 2 * binomCdf(n, k - 1); }

  defineScene('interval', t => {
    const d = t.raw.d.filter(v => v !== null && isFinite(v));
    const n = d.length, k = t.step4.ci_rank_k, iv = t.step4;
    const byRank = d.map((v, i) => i).sort((a, b) => d[a] - d[b]);
    const rank = new Array(n);
    byRank.forEach((i, r) => { rank[i] = r; });
    const PX0 = 70, PX1 = 520, GX = 548, AX = 286, TOP = 44, BOT = 250;
    const x = scale(...domain(d, 0.04), PX0, PX1);
    const ry = r => BOT - r * (BOT - TOP) / Math.max(1, n - 1);
    const lo = k - 1, hi = n - k, mid = (n - 1) / 2;
    const cov = coverage(n, k);

    const dots = d.map((v, i) => {
      const jy = AX - 10 + ((i * 37) % 11) * 2;
      const r = rank[i];
      const cls = `b4-dot${r < lo || r > hi ? ' out' : ''}${r === lo || r === hi ? ' end' : ''}`;
      return s('circle', { cx: x(v), cy: jy, r: 2.7, class: cls, style: `--dy:${ry(r) - jy}px;--r:${r}` });
    });
    const yEnd = [ry(lo), ry(hi)], xEnd = [x(d[byRank[lo]]), x(d[byRank[hi]])];
    const leader = (x1, y1) => s('line', { x1: x1 + 6, x2: GX - 6, y1, y2: y1, class: 'b4-leader' });
    const gut = (y1, name, value, cls) => s('text', { x: GX, y: y1 + 4, class: `sc-t ${cls}` },
      [s('tspan', {}, `${name} `), s('tspan', { class: 'b4-val' }, value)]);
    const L = labeler(PX0, PX1 + 40);
    L.block(x(iv.ci_low) - 2, x(iv.ci_high) + 2, AX - 6, AX + 6);
    const ciLabel = L.text(`90% 구간 ${fmt(iv.ci_low, true)} ~ ${fmt(iv.ci_high, true)}`,
      around((x(iv.ci_low) + x(iv.ci_high)) / 2, AX + 26), 'sc-t doe');
    const zeroIn = x(0) > PX0 && x(0) < PX1;

    const svg = s('svg', { viewBox: `0 0 ${W} ${AX + 36}`, class: 'scene-svg', role: 'img', 'aria-label': `${t.name} 예제의 die별 차이와 90% 구간` }, [
      s('g', { 'data-b': 0 }, [
        s('line', { x1: PX0, x2: PX1, y1: AX, y2: AX, class: 'sc-axis' }),
        zeroIn ? s('line', { x1: x(0), x2: x(0), y1: AX - 8, y2: AX + 8, class: 'sc-zero' }) : null,
        zeroIn ? s('text', { x: x(0), y: AX - 13, 'text-anchor': 'middle', class: 'sc-t halo' }, '0') : null,
        s('text', { x: PX0 - 10, y: AX + 4, 'text-anchor': 'end', class: 'sc-t' }, 'd')]),
      s('g', { 'data-b': 1, class: 'b4-lift' }),
      s('g', { 'data-b': 3, class: 'b4-pick' }),
      s('g', { 'data-b': 0, class: 'b4-dots' }, dots),
      s('g', { 'data-b': 1 }, [
        s('text', { x: PX0 - 10, y: TOP + 4, 'text-anchor': 'end', class: 'sc-t' }, `${n}번째`),
        s('text', { x: PX0 - 10, y: BOT + 4, 'text-anchor': 'end', class: 'sc-t' }, '1번째'),
        s('text', { x: PX0 - 10, y: (TOP + BOT) / 2 + 4, 'text-anchor': 'end', class: 'sc-t muted' }, '크기 순')]),
      s('g', { 'data-b': 2 }, [
        leader(x(iv.center), ry(mid)),
        s('circle', { cx: x(iv.center), cy: ry(mid), r: 5, class: 'sc-c' }),
        gut(ry(mid), '가운데 = 중앙값', fmt(iv.center, true), 'b4-mid')]),
      s('g', { 'data-b': 3 }, [
        leader(xEnd[1], yEnd[1]), leader(xEnd[0], yEnd[0]),
        gut(yEnd[1], `위에서 ${k}번째`, fmt(iv.ci_high, true), 'doe'),
        gut(yEnd[0], `아래에서 ${k}번째`, fmt(iv.ci_low, true), 'doe')]),
      s('g', { 'data-b': 4 }, [
        ...xEnd.map((xe, j) => s('line', { x1: xe, x2: xe, y1: yEnd[j] + 4, y2: AX - 6, class: 'b4-drop' })),
        s('rect', { x: Math.min(x(iv.ci_low), x(iv.ci_high) - 4), y: AX - 5, width: Math.max(4, x(iv.ci_high) - x(iv.ci_low)), height: 10, rx: 5, class: 'sc-ci' }),
        s('circle', { cx: x(iv.center), cy: AX, r: 4.5, class: 'sc-c' }),
        ciLabel])
    ]);
    return {
      nodes: [svg],
      beats: [`die ${n}개의 차이 d를 값 축에 찍는다`, '작은 값부터 크기 순으로 세운다',
        `가운데 값이 중앙값 ${fmt(iv.center, true)}`, `양끝에서 ${k}번째 두 값을 고른다`,
        `그 사이가 90% 구간 (포함 확률 ${(cov * 100).toFixed(1)}%)`]
    };
  });

  // ---------- ⑤ 허용폭 Δ: 두 몫을 쌓아 Δ, 그리고 이 예제가 실제로 쓴 폭 ----------
  function usedWhy(t) {
    const p = t.step5, st = t.step3;
    if (t.final.basis === 'log') return '잡음이 값에 비례해 배율(log)로 본다.';
    if (t.final.basis === 'abs') {
      if (st.cls.level === '0 중심') return '값이 0 근처라 Δ 대신 LoQ를 절대 허용폭으로 쓴다.';
      const parts = [['Δ', p.delta], ['값 간격 한 칸', p.resolution_step], ['장비 정확도 폭', p.accuracy_margin]]
        .filter(([, v]) => v !== null && isFinite(v));
      const top = parts.reduce((a, b) => (b[1] > a[1] ? b : a));
      return `계단 값이라 ${parts.map(([n]) => n).join(', ')} 중 큰 쪽(${top[0]})을 쓴다.`;
    }
    if (t.final.basis === 'accuracy') return '바닥 근처라 Δ와 장비 정확도 폭 중 큰 쪽을 쓴다.';
    if (t.final.basis === 'loq') return 'Δ로 이동을 보고, ⑥ 2단계에서 LoQ와 함께 본다.';
    return 'Δ를 그대로 판정에 쓴다.';
  }
  defineScene('delta', t => {
    const p = t.step5, X0 = 176, X1 = 700;
    const x = scale(0, p.delta || 1, X0, X1);
    const xm = x(p.policy_margin);
    const L = labeler(X0 - 8, X1 + 16);
    L.block(X0, X1, 40, 66);
    const seg1 = L.text(`5% × |POR 중앙값 ${fmt(t.step3.por_median)}| = ${fmt(p.policy_margin)}`, around((X0 + xm) / 2, 88), 'sc-t eq');
    const seg2 = L.text(p.run_margin > 0
      ? `회차 몫 ${fmt(p.t_factor, false, '')} × σ_run ${fmt(t.step2.sigma_run)} = ${fmt(p.run_margin)}`
      : '회차 몫 0 (σ_run = 0)', [{ x: X1, y: 110, a: 'end' }, { x: xm, y: 110, a: 'start' }], 'sc-t');
    const head = (y, title, sub, b) => s('g', { 'data-b': b }, [
      s('text', { x: 0, y: y + 28, class: 'sc-h' }, title), s('text', { x: 0, y: y + 47, class: 'sc-sub' }, sub)]);

    const u = p.used, Y2 = 140;
    const isLog = t.final.basis === 'log';
    const row2 = isLog
      ? bandRow(Y2, { tol: p.delta_log, name: '허용', show: ratioShow }, 3)
      : bandRow(Y2, { tol: u.value, name: { abs: '절대폭', accuracy: "Δ'" }[t.final.basis] || 'Δ', show: linearShow(),
        ghost: u.value !== p.delta ? p.delta : null }, 3);
    const svg = s('svg', { viewBox: `0 0 ${W} ${Y2 + 112}`, class: 'scene-svg', role: 'img', 'aria-label': `${t.name} 예제의 허용폭` }, [
      head(0, '허용폭 Δ', '두 몫을 더한다', 0),
      s('line', { x1: X0, x2: X1, y1: 53, y2: 53, class: 'sc-axis' }),
      s('g', { 'data-b': 0 }, [s('rect', { x: X0, y: 40, width: Math.max(2, xm - X0), height: 26, rx: 4, class: 'b5-seg1 b5-grow' }), seg1]),
      s('g', { 'data-b': 1 }, [s('rect', { x: xm, y: 40, width: Math.max(0, X1 - xm), height: 26, rx: 4, class: 'b5-seg2 b5-grow' }), seg2]),
      s('g', { 'data-b': 2 }, [
        s('path', { d: `M${X0} 34V28H${X1}V34`, class: 'b5-brace' }),
        s('text', { x: (X0 + X1) / 2, y: 20, 'text-anchor': 'middle', class: 'sc-t b5-sum halo' }, `Δ = ${fmt(p.delta)}`)]),
      head(Y2, '판정에 쓴 폭', isLog ? '배율 변화' : u.name, 3),
      row2
    ]);
    const big = isLog ? `${pct(ratio(-p.delta_log))} ~ ${pct(ratio(p.delta_log), true)}` : `±${fmt(u.value)}`;
    const ghostNote = !isLog && u.value !== p.delta ? ` 점선 = 1단계에서 쓴 ±Δ (${fmt(p.delta)}).` : '';
    const result = h('div', { class: 'scene-result', 'data-b': 3 }, [
      h('span', { class: 'b5-big' }, big),
      h('div', {}, [h('p', { class: 'res-basis' }, `판정에 쓴 폭 · ${isLog ? '배율 변화 (log 허용폭)' : u.name}`),
        h('p', { class: 'res-why' }, usedWhy(t) + ghostNote)])]);
    return {
      nodes: [svg, result],
      beats: ['첫째 몫: POR 중앙값의 5%', p.run_margin > 0 ? '둘째 몫: 회차가 밀리는 만큼' : '둘째 몫: 회차 흔들림 0이라 0',
        `두 몫을 더하면 허용폭 Δ = ${fmt(p.delta)}`, `이 예제가 판정에 쓴 폭: ${isLog ? '배율' : u.name}`]
    };
  });
  const base5 = TRACK[5];
  TRACK[5] = t => {
    const c = base5(t), u = t.step5.used;
    const shown = t.final.basis === 'log'
      ? `배율 ${pct(ratio(-t.step5.delta_log))} ~ ${pct(ratio(t.step5.delta_log), true)}` : `${u.name} ±${fmt(u.value)}`;
    return { ...c, output: [c.output[0], ['판정에 쓴 폭', shown]] };
  };

  // ---------- ⑥ 판정 3단계: 행마다 한 단계 ----------
  const X0 = 176, X1 = 700, RH = 112;
  function loqRow(y, r, b) {
    const a = r.m + r.lo, z = r.m + r.hi;
    const vals = [r.m, a, z, r.loq, 0];
    if (Math.min(r.m, a) < 0) vals.push(-r.loq);
    const x = scale(...domain(vals, 0.12), X0, X1);
    const left = Math.max(x(-r.loq), X0), right = Math.min(x(r.loq), X1);
    const lines = [r.loq, -r.loq].filter(v => x(v) >= X0 && x(v) <= X1);
    const L = labeler(X0 - 8, X1 + 16);
    lines.forEach(v => L.block(x(v) - 1, x(v) + 1, y + 22, y + 90));
    L.block(Math.min(x(a), x(z) - 4) - 8, Math.max(x(z), x(a) + 4) + 8, y + 36, y + 54);
    L.block(x(r.m) - 6, x(r.m) + 6, y + 55, y + 67);
    const loqLabels = lines.map(v => L.text(`${v < 0 ? '−' : ''}LoQ ${fmt(r.loq)}`,
      [{ x: x(v) + 5, y: y + 16, a: 'start' }, { x: x(v) - 5, y: y + 16, a: 'end' }], 'sc-t por'));
    const midDoe = (x(a) + x(z)) / 2;
    const doeLabel = L.text(`DOE 구간 ${fmt(a)} ~ ${fmt(z)}`, [
      ...around(midDoe, y + 31), { x: x(z), y: y + 31, a: 'end' }, { x: x(a), y: y + 31, a: 'start' },
      ...around(midDoe, y + 16), ...around(midDoe, y + 102)], 'sc-t doe');
    const porLabel = L.text(`POR 중앙값 ${fmt(r.m)}`, [...around(x(r.m), y + 102), ...around(x(r.m), y + 80)], 'sc-t por');
    const note = right - left > 40 ? L.text("'<LoQ' 로 보고하는 곳", [{ x: left + 8, y: y + 80, a: 'start' }, { x: right - 8, y: y + 80, a: 'end' }],
      'sc-t muted', { optional: true, size: 12 }) : null;
    return s('g', { 'data-b': b }, [
      s('line', { x1: X0, x2: X1, y1: y + 61, y2: y + 61, class: 'sc-axis' }),
      s('rect', { x: left, y: y + 28, width: Math.max(0, right - left), height: 56, rx: 6, class: 'sc-below' }),
      note,
      ...lines.map(v => s('line', { x1: x(v), x2: x(v), y1: y + 22, y2: y + 90, class: 'sc-loq' })),
      ...loqLabels,
      s('circle', { cx: x(r.m), cy: y + 61, r: 5, class: 'sc-por' }),
      porLabel,
      s('g', { class: 'late' }, [
        s('rect', { x: Math.min(x(a), x(z) - 4), y: y + 40, width: Math.max(4, x(z) - x(a)), height: 10, rx: 5, class: 'sc-ci' }),
        s('path', { d: `M${x(r.m + r.c)} ${y + 36}l8 9l-8 9l-8 -9z`, class: 'sc-doe' }),
        doeLabel])
    ]);
  }
  function noteRow(y, text, b) {
    return s('g', { 'data-b': b }, [s('text', { x: X0, y: y + 60, class: 'sc-t note' }, text)]);
  }
  function rowHead(y, title, sub, verdict, b, bv) {
    return s('g', {}, [
      s('g', { 'data-b': b }, [s('text', { x: 0, y: y + 28, class: 'sc-h' }, title), s('text', { x: 0, y: y + 47, class: 'sc-sub' }, sub)]),
      s('g', { 'data-b': bv, class: 'pop' }, [
        s('rect', { x: 0, y: y + 60, width: 76, height: 28, rx: 14, class: `sc-pill ${VCLASS[verdict] || 'skip'}` }),
        s('text', { x: 38, y: y + 79, 'text-anchor': 'middle', class: 'sc-pill-t' }, verdict || '없음')])
    ]);
  }
  const S1_CAP = {
    '동등': '구간이 ±Δ 띠 안에 통째로 → 1단계 동등',
    '차이': '구간이 ±Δ 띠 밖에 통째로 → 1단계 차이',
    '미결': '구간이 ±Δ 띠 경계에 걸침 → 1단계 미결'
  };
  function s2Cap(st) {
    const why = st.reason || '';
    if (why.includes('LoQ 미만')) return "DOE 구간도 LoQ 아래 → 둘 다 '<LoQ' 보고 → 동등";
    if (why.includes('LoQ에 걸침')) return "DOE 구간이 LoQ 선에 걸침 → '<LoQ'와 같다고 봄";
    if (why.includes('±Δ 안')) return '이동이 ±Δ 안 → 2단계 동등';
    if (st.verdict === '차이') return 'DOE 구간이 통째로 LoQ 위, 이동은 띠 밖 → 차이';
    return 'DOE 구간은 LoQ 위, 이동이 띠에 걸침 → 미결';
  }
  function stage3Row(t) {
    const basis = t.step6.stage3.basis, iv = t.step4, p = t.step5;
    if (basis === 'log' && iv.log) {
      return { lo: iv.log.ci_low, hi: iv.log.ci_high, c: iv.log.center, tol: p.delta_log, name: '허용', ciName: '배율 변화', show: ratioShow };
    }
    const tol = { abs: p.abs_delta, accuracy: p.used && p.used.value }[basis];
    const name = { abs: '절대폭', accuracy: "Δ'" }[basis];
    return tol ? { lo: iv.ci_low, hi: iv.ci_high, c: iv.center, tol, name, ciName: '90% 구간', show: linearShow() } : null;
  }

  defineScene('stages', t => {
    const st = t.step6, iv = t.step4;
    const rows = [];
    const beats = ['die별 차이 d의 90% 구간(파란 막대)과 ±Δ 띠(초록)', S1_CAP[st.stage1.verdict] || st.stage1.reason];
    rows.push(rowHead(0, '1단계 · TOST', '모든 ITEM', st.stage1.verdict, 0, 1));
    rows.push(bandRow(0, { lo: iv.ci_low, hi: iv.ci_high, c: iv.center, tol: t.step5.delta, name: 'Δ', ciName: '90% 구간', show: linearShow() }, 0));
    let y = RH;
    if (st.stage2) {
      const b = beats.length;
      beats.push(s2Cap(st.stage2));
      rows.push(rowHead(y, '2단계 · LoQ 판정', 'POR 값이 LoQ 아래', st.stage2.verdict, b, b));
      rows.push(loqRow(y, { m: t.step3.por_median, lo: iv.ci_low, hi: iv.ci_high, c: iv.center, loq: t.step3.LoQ }, b));
      y += RH;
    }
    if (st.stage3) {
      const b = beats.length;
      const r = stage3Row(t);
      const v = st.stage3.verdict;
      const log = st.stage3.basis === 'log';
      beats.push(v ? `동등이 아님 → '${st.stage3.route}'${log ? ' (배율로 봄)' : ''}에서 다시 봄 → ${v}`
        : `판정 길 '${st.stage3.route}'는 따로 판정하지 않음 → 앞 판정 유지`);
      rows.push(rowHead(y, '3단계 · 판정 길', st.stage3.route, v, b, b));
      rows.push(r ? bandRow(y, r, b) : noteRow(y, '이 길은 따로 판정하지 않아 1·2단계 판정을 그대로 둔다', b));
      y += RH;
    }
    const last = beats.length;
    beats.push(`최종 판정 ${st.final.verdict} · ${BASIS[st.final.basis] || st.final.basis}`);
    const svg = s('svg', { viewBox: `0 0 ${W} ${y}`, class: 'scene-svg', role: 'img', 'aria-label': `${t.name} 예제의 판정 3단계` }, rows);
    const g = iv.log;
    const raw = st.stage3 && st.stage3.basis === 'log' && g ? h('p', { class: 'b-raw' },
      `log 값 · 구간 ${fmt(g.ci_low, true, '')} ~ ${fmt(g.ci_high, true, '')} (가운데 ${fmt(g.center, true, '')}) · ±Δ_log ${fmt(t.step5.delta_log, false, '')}`) : null;
    const result = h('div', { class: 'scene-result', 'data-b': last }, [
      pill(st.final.verdict, 'big'),
      h('div', {}, [h('p', { class: 'res-basis' }, `최종 판정 · ${BASIS[st.final.basis] || st.final.basis}`),
        h('p', { class: 'res-why' }, t.final.why), raw])
    ]);
    return { nodes: [svg, result], beats };
  });
  const base6 = TRACK[6];
  TRACK[6] = t => {
    const c = base6(t);
    if (t.final.basis !== 'log' || !t.step4.log) return c;
    const g = t.step4.log;
    return { ...c, inputs: [...c.inputs,
      ['배율 변화', `${pct(ratio(g.ci_low), true)} ~ ${pct(ratio(g.ci_high), true)}`],
      ['허용 배율', `${pct(ratio(-t.step5.delta_log))} ~ ${pct(ratio(t.step5.delta_log), true)}`]] };
  };

  // ---------- ⑦ 판정 → 원인 → 할 일 ----------
  // 원인 이름과 순서는 slides.py CAUSES (미결) 와 docs/sop/examples/journeys.py DIFF_CAUSE (차이) 를 따른다
  const HOLD_CAUSES = ['die 부족', '측정 흔들림', '기준 조건 흔들림', '허용폭 경계'];
  const DIFF_CAUSE = '이동이 허용폭 밖';
  function causeFacts(t) {
    const b = basisNumbers(t);
    const half = (b.hi - b.lo) / 2;
    const show = b.log ? (v => fmt(v, false, '')) : (v => fmt(v));
    return {
      'die 부족': `die ${t.n_die}개 (10개 이상이면 아님)`,
      '측정 흔들림': `구간 반폭 ÷ 허용폭 = ${(half / b.tol).toFixed(2)} (1 이상이면 맞음)`,
      '기준 조건 흔들림': `POR 회차 상태: ${t.step3.cls.run}`,
      '허용폭 경계': '구간이 허용폭 경계에 걸침',
      [DIFF_CAUSE]: `구간 ${show(b.lo)} ~ ${show(b.hi)}가 ±${show(b.tol)} 밖`
    };
  }
  defineScene('next', t => {
    const v = t.final.verdict, cause = t.step7.cause;
    if (v === '미결' && !HOLD_CAUSES.includes(cause)) throw new Error(`⑦ 장면이 모르는 미결 원인: ${cause}`);
    if (v === '차이' && cause !== DIFF_CAUSE) throw new Error(`⑦ 장면이 모르는 차이 원인: ${cause}`);
    const facts = causeFacts(t);
    const groups = [['동등', ['원인 찾지 않음']], ['미결', HOLD_CAUSES], ['차이', [DIFF_CAUSE]], ['판정 제외', ['사유 열(reason)을 본다']]];
    const RY = 30, PX = 140, CW = 236, FX = PX + CW + 22;
    let row = 0;
    const kids = [
      s('text', { x: 0, y: 14, class: 'sc-sub' }, '⑥ 최종 판정'),
      s('text', { x: PX, y: 14, class: 'sc-sub' }, v === '미결' ? '원인 (위에서부터 처음 맞는 것)' : '원인'),
      s('text', { x: FX, y: 14, class: 'sc-sub' }, '이 예제에서 본 것')];
    const hitIndex = HOLD_CAUSES.indexOf(cause);
    groups.forEach(([gv, causes]) => {
      const top = 28 + row * RY, mine = gv === v;
      const cy = top + (causes.length * RY) / 2 - RY / 2 + 13;
      kids.push(s('g', { class: `b7-verdict${mine ? ' mine' : ''}`, 'data-b': 0 }, [
        s('rect', { x: 0, y: cy - 14, width: 84, height: 28, rx: 14, class: `sc-pill ${VCLASS[gv]}` }),
        s('text', { x: 42, y: cy + 5, 'text-anchor': 'middle', class: 'sc-pill-t' }, gv)]));
      causes.forEach((c, i) => {
        const yy = top + i * RY + 13;
        const hit = mine && (gv !== '미결' || i === hitIndex);
        const passed = mine && gv === '미결' && i < hitIndex;
        const wire = cls => s('path', { d: `M84 ${cy}C${PX - 30} ${cy} ${PX - 30} ${yy} ${PX} ${yy}`, class: `b7-wire${cls}`, 'data-b': cls ? 1 : 0 });
        kids.push(wire(''));
        if (hit) kids.push(wire(' hit'));
        const box = cls => s('g', { class: `b7-cause${cls}`, 'data-b': cls ? 1 : 0 }, [
          s('rect', { x: PX, y: yy - 12, width: CW, height: 24, rx: 6 }),
          s('text', { x: PX + 12, y: yy + 5, class: 'sc-t' }, gv === '미결' ? `${i + 1}. ${c}` : c)]);
        kids.push(box(''));
        if (hit || passed) kids.push(box(hit ? ' hit' : ' passed'));
        const fact = facts[c];
        if ((hit || passed) && fact) {
          kids.push(s('text', { x: FX, y: yy + 5, class: `sc-t ${hit ? 'b7-fact' : 'muted'}`, 'data-b': 1 },
            `${hit ? '✓' : '✕'} ${fact}`));
        }
      });
      row += causes.length;
    });
    const svg = s('svg', { viewBox: `0 0 ${W} ${28 + row * RY}`, class: 'scene-svg', role: 'img', 'aria-label': `${t.name} 예제의 다음 행동` }, kids);
    const result = h('div', { class: 'scene-result', 'data-b': 2 }, [
      pill(v, 'big'),
      h('div', {}, [h('p', { class: 'res-basis' }, cause ? `원인 · ${cause}` : '원인 없음'), h('p', { class: 'res-why b7-action' }, t.step7.action)])]);
    const b1 = v === '동등' ? '동등이면 원인을 찾지 않는다'
      : v === '미결' ? `원인을 위에서부터 → ${hitIndex + 1}번 ${cause}` : `원인: ${cause}`;
    return { nodes: [svg, result], beats: [`⑥ 최종 판정은 ${v}`, b1, v === '동등' ? '할 일 없음, 결과만 기록' : '원인에 맞는 할 일을 한다'] };
  });
})();
