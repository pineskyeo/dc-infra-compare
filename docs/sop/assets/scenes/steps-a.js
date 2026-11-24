// 장면: steps-a 담당 (⓪ 표본 크기 · ① 반복 측정 · ② 흔들림 나누기 · ③ LoQ와 ITEM 유형)
(() => {
  'use strict';
  const { defineScene, h, s, fmt, scale, domain, TRACK, miniSvg } = window.SOP;
  const W = 720, X0 = 176, X1 = 700;

  // ---------- 판정 코드와 같은 계산 (그림이 코드 결과와 같은지 아래에서 맞춰 본다) ----------
  const median = v => {
    const x = v.slice().sort((a, b) => a - b), n = x.length;
    return n % 2 ? x[(n - 1) / 2] : (x[n / 2 - 1] + x[n / 2]) / 2;
  };
  const mean = v => v.reduce((a, b) => a + b, 0) / v.length;
  // por_doe_compare.ci_rank: P(W ≤ k) ≤ 0.05 인 가장 큰 k (0부터 셈), W ~ 이항(n, ½)
  function ciRank(n) {
    let term = Math.pow(0.5, n), cdf = 0, k = -1;
    for (let i = 0; i <= n; i++) {
      cdf += term;
      if (cdf > 0.05 * (1 + 1e-12)) break;
      k = i;
      term = term * (n - i) / (i + 1);
    }
    return Math.max(k, 0);
  }
  function ciMedian(d) {
    const m = mean(d);
    if (d.every(v => v === d[0])) return [m, m, m];
    const x = d.slice().sort((a, b) => a - b), k = ciRank(d.length);
    return [median(d), x[k], x[d.length - 1 - k]];
  }
  const robustSigma = v => { const m = median(v); return 1.4826 * median(v.map(x => Math.abs(x - m))); };
  // por_doe_compare._noise_parts: σ_die 는 이웃 회차 차이, σ_run 은 회차별 중앙값의 분산에서 die 잡음 몫을 뺀 것
  function noiseSplit(Y) {
    const n = Y.length, J = Y[0].length;
    const e = [];
    for (let k = 0; k < J - 1; k++) {
      const dd = Y.map(r => r[k + 1] - r[k]);
      const m = median(dd);
      dd.forEach(x => e.push(x - m));
    }
    const sDie = robustSigma(e) / Math.SQRT2;
    const res = Y.map(r => { const m = mean(r); return r.map(v => v - m); });
    const runs = Array.from({ length: J }, (_, j) => median(res.map(r => r[j])));
    const rm = mean(runs);
    const varR = runs.reduce((a, x) => a + (x - rm) ** 2, 0) / (J - 1);
    return { sDie, sRun: Math.sqrt(Math.max(0, varR - (Math.PI / 2) * sDie * sDie / n)), runs, res };
  }
  // 예제 자료의 raw 값은 6자리로 반올림되어 있어 σ_run 처럼 빼기가 있는 값은 조금 더 벌어진다
  function same(a, b, what, rel = 2e-4) {
    if (Math.abs(a - b) > rel * Math.max(Math.abs(a), Math.abs(b)) + 1e-30) {
      throw new Error(`그림 계산이 예제 자료와 다름: ${what} ${a} ≠ ${b}`);
    }
  }
  const dValues = t => t.raw.d.filter(v => v !== null && isFinite(v));

  // 값 축: 양수만이고 범위가 넓으면 log 눈금
  function valueAxis(vals, y0, y1) {
    const pos = vals.every(v => v > 0);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    if (pos && hi / lo > 20) {
      const [a, b] = domain(vals.map(Math.log10), 0.08);
      const f = scale(a, b, y0, y1);
      return { y: v => f(Math.log10(v)), log: true, lo: Math.pow(10, a), hi: Math.pow(10, b) };
    }
    const [a, b] = domain(vals, 0.08);
    return { y: scale(a, b, y0, y1), log: false, lo: a, hi: b };
  }
  const RUN_CLASS = j => `sa-run${Math.min(j, 3)}`;
  const diamond = (x, y, r, cls) => s('path', { d: `M${x} ${y - r}l${r} ${r}l${-r} ${r}l${-r} ${-r}z`, class: cls });

  // ---------- ⓪ 표본 크기: die 수를 바꾸면 90% 구간이 어떻게 되나 ----------
  function tolerance(t) {
    const u = t.step5.used;
    if (u && u.name === '절대 허용폭') return { v: u.value, name: '절대폭' };
    return { v: t.step5.delta, name: 'Δ' };
  }
  defineScene('sample-size', t => {
    const d = dValues(t), N = d.length, MIN = 10;
    const full = ciMedian(d);
    same(full[1], t.step4.ci_low, 'ci_low');
    same(full[2], t.step4.ci_high, 'ci_high');
    const ns = [6, 10, 20, 40].filter(n => n < N).concat(N);
    const rows = ns.map(n => { const [c, lo, hi] = ciMedian(d.slice(0, n)); return { n, c, lo, hi }; });
    const tol = tolerance(t);
    const [d0, d1] = domain([-tol.v, tol.v, 0, ...rows.flatMap(r => [r.lo, r.hi])], 0.08);
    const x = scale(d0, d1, X0, X1);
    const RH = 46, top = 40, bottom = top + rows.length * RH;
    const beatOf = n => (n < MIN ? 0 : n === N ? 2 : 1);
    const nodes = [
      s('g', { 'data-b': 0 }, [
        s('rect', { x: x(-tol.v), y: top - 8, width: Math.max(2, x(tol.v) - x(-tol.v)), height: bottom - top + 8, rx: 6, class: 'sc-band' }),
        s('line', { x1: x(-tol.v), x2: x(-tol.v), y1: top - 12, y2: bottom, class: 'sc-edge' }),
        s('line', { x1: x(tol.v), x2: x(tol.v), y1: top - 12, y2: bottom, class: 'sc-edge' }),
        s('text', { x: x(-tol.v) - 4, y: top - 18, class: 'sc-t eq end' }, `−${tol.name}`),
        s('text', { x: x(tol.v) + (x(tol.v) > W - 130 ? -4 : 4), y: top - 18, class: `sc-t eq${x(tol.v) > W - 130 ? ' end' : ''}` },
          `+${tol.name} ${fmt(tol.v)}`),
        s('line', { x1: x(0), x2: x(0), y1: top - 4, y2: bottom, class: 'sa-zero' }),
        s('text', { x: x(0), y: bottom + 18, class: 'sc-t mid' }, '0'),
        s('text', { x: 0, y: top - 18, class: 'sc-sub' }, 'die별 차이 d의 90% 구간')
      ])
    ];
    rows.forEach((r, i) => {
      const y = top + i * RH + RH / 2, off = r.n < MIN, mine = r.n === N;
      nodes.push(s('g', { 'data-b': beatOf(r.n) }, [
        s('text', { x: 0, y: y - 2, class: `sc-h${off ? ' sa-off' : ''}` }, mine ? `die ${r.n}개 · 이 예제` : `die ${r.n}개`),
        s('text', { x: 0, y: y + 15, class: 'sc-sub' }, `반폭 ±${fmt((r.hi - r.lo) / 2)}`),
        off ? s('g', {}, [s('rect', { x: 112, y: y - 17, width: 50, height: 22, rx: 11, class: 'sc-pill hold' }),
          s('text', { x: 137, y: y - 1, class: 'sa-pill-t mid' }, '미결')]) : null,
        s('line', { x1: X0, x2: X1, y1: y, y2: y, class: 'sc-axis' }),
        s('rect', { x: Math.min(x(r.lo), x(r.hi) - 4), y: y - 5, width: Math.max(4, x(r.hi) - x(r.lo)), height: 10, rx: 5,
          class: off ? 'sa-ci-off' : mine ? 'sc-ci' : 'sa-ci-mid' }),
        s('circle', { cx: x(r.c), cy: y, r: 4, class: off ? 'sa-c-off' : 'sc-c' })
      ]));
    });
    const first = rows[0];
    const beats = [
      first.n < MIN ? `die ${first.n}개: 구간이 넓고, 10개 미만이라 미결` : `die ${first.n}개의 90% 구간`,
      'die 10개부터 판정. die가 늘면 구간이 좁아진다',
      `이 예제 die ${N}개: 구간 반폭 ±${fmt((full[2] - full[1]) / 2)}`
    ];
    return { nodes: [s('svg', { viewBox: `0 0 ${W} ${bottom + 26}`, class: 'scene-svg', role: 'img',
      'aria-label': `${t.name} 예제: die 수에 따라 바뀌는 90% 구간` }, nodes)], beats };
  });

  // ---------- ① 반복 측정: POR J회 + DOE 1회, die 하나의 d ----------
  function pickDie(t, k) {
    const c = t.step4.center;
    let best = 0;
    for (let i = 0; i < k; i++) if (t.raw.d[i] !== null && Math.abs(t.raw.d[i] - c) < Math.abs(t.raw.d[best] - c)) best = i;
    return best;
  }
  defineScene('repeat', t => {
    const k = Math.min(12, t.n_die), J = t.J;
    const por = t.raw.por.slice(0, k), doe = t.raw.doe.slice(0, k);
    const pick = pickDie(t, k);
    const PX0 = 64, PX1 = 486, Y0 = 34, Y1 = 236;
    const ax = valueAxis([...por.flat(), ...doe], Y1, Y0);
    const step = (PX1 - PX0) / k;
    const xd = i => PX0 + (i + 0.5) * step;
    const runOff = j => (j - (J - 1) / 2) * Math.min(6, step / (J + 3)) - 5;
    const nodes = [
      s('line', { x1: PX0, x2: PX0, y1: Y0 - 6, y2: Y1 + 6, class: 'sc-axis' }),
      s('text', { x: PX0 - 6, y: Y0 + 4, class: 'sc-t end' }, fmt(ax.hi)),
      s('text', { x: PX0 - 6, y: Y1 + 4, class: 'sc-t end' }, fmt(ax.lo)),
      ax.log ? s('text', { x: PX0 - 6, y: (Y0 + Y1) / 2, class: 'sc-t muted end' }, 'log 눈금') : null,
      s('text', { x: PX0, y: Y1 + 40, class: 'sc-t muted' }, `앞 die ${k}개 (전체 ${t.n_die}개)`),
      s('rect', { x: xd(pick) - step / 2 + 2, y: Y0 - 10, width: step - 4, height: Y1 - Y0 + 20, rx: 8, class: 'sa-hl', 'data-b': 3 })
    ];
    por.forEach((runs, i) => {
      nodes.push(s('text', { x: xd(i), y: Y1 + 20, class: 'sa-die mid' }, t.raw.die[i]));
      runs.forEach((v, j) => nodes.push(s('circle', { cx: xd(i) + runOff(j), cy: ax.y(v), r: 3.2, class: RUN_CLASS(j + 1), 'data-b': j === 0 ? 0 : 1 })));
      nodes.push(s('g', { 'data-b': 2 }, diamond(xd(i) + runOff(J - 1) + 10, ax.y(doe[i]), 5, 'sc-doe')));
    });
    // 오른쪽: 고른 die 크게 보기
    const r = por[pick], m = mean(r), dv = doe[pick] - m;
    same(dv, t.raw.d[pick], 'd');
    const zy = scale(...domain([...r, doe[pick], m], 0.25), Y1, Y0 + 26);
    const ZX = 520;
    nodes.push(s('g', { 'data-b': 3 }, [
      s('rect', { x: ZX, y: Y0 - 10, width: W - ZX, height: Y1 - Y0 + 20, rx: 12, class: 'sa-panel' }),
      s('text', { x: ZX + 14, y: Y0 + 10, class: 'sc-t por' }, `${t.raw.die[pick]} 크게 보기`),
      s('line', { x1: ZX + 14, x2: W - 14, y1: zy(m), y2: zy(m), class: 'sa-mean' }),
      s('text', { x: W - 14, y: zy(m) + (doe[pick] >= m ? 17 : -8), class: 'sc-t end' }, `POR 평균 ${fmt(m)}`),
      ...r.map((v, j) => s('circle', { cx: ZX + 26 + j * 14, cy: zy(v), r: 4.5, class: RUN_CLASS(j + 1) })),
      diamond(ZX + 100, zy(doe[pick]), 7, 'sc-doe'),
      s('text', { x: ZX + 100, y: zy(doe[pick]) + (doe[pick] >= m ? -12 : 22), class: 'sc-t doe mid' }, `DOE ${fmt(doe[pick])}`),
      s('line', { x1: ZX + 150, x2: ZX + 150, y1: zy(m), y2: zy(doe[pick]), class: 'sa-d' }),
      s('text', { x: ZX + 158, y: (zy(m) + zy(doe[pick])) / 2 + 5, class: 'sc-t doe' }, 'd'),
      s('text', { x: ZX + 14, y: Y1 + 2, class: 'sc-t doe' }, `d = ${fmt(dv, true)}`)
    ]));
    const legend = s('g', {}, [
      s('circle', { cx: PX0 + 6, cy: 10, r: 4, class: RUN_CLASS(1) }),
      s('text', { x: PX0 + 16, y: 14, class: 'sc-t' }, `POR 회차 (${J}회)`),
      diamond(PX0 + 140, 10, 5, 'sc-doe'),
      s('text', { x: PX0 + 152, y: 14, class: 'sc-t' }, 'DOE (1회)')
    ]);
    const beats = [
      'POR 1회차: die마다 한 번씩 잰다',
      `POR ${J}회까지: 같은 die를 다시 잰다`,
      'DOE 1회: 같은 die를 바꾼 조건으로 잰다',
      `die 하나의 d = DOE − POR 평균 = ${fmt(dv, true)}`
    ];
    return { nodes: [s('svg', { viewBox: `0 0 ${W} ${Y1 + 48}`, class: 'scene-svg', role: 'img',
      'aria-label': `${t.name} 예제: POR ${J}회와 DOE 1회, die 하나의 차이 d` }, [legend, ...nodes])], beats };
  });

  // ---------- ② 흔들림 나누기: die 수준을 빼고, 회차 이동과 반복 흔들림으로 ----------
  defineScene('noise-split', t => {
    const Y = t.raw.por, n = Y.length, J = Y[0].length;
    const ns = noiseSplit(Y);
    same(ns.sDie, t.step2.sigma_die, 'sigma_die');
    same(ns.sRun, t.step2.sigma_run, 'sigma_run', 3e-3);
    const PX0 = 64, PX1 = 700, Y0 = 30, Y1 = 230;
    const raw = valueAxis(Y.flat(), Y1, Y0);
    const lim = Math.max(...ns.res.flat().map(Math.abs), ns.sDie, ...ns.runs.map(Math.abs)) * 1.1 || 1;
    const yr = scale(-lim, lim, Y1, Y0);
    const xr = i => PX0 + (i + 0.5) * (PX1 - PX0) / n;
    const colW = (PX1 - PX0) / J;
    const cx = j => PX0 + (j + 0.5) * colW;
    const jit = i => (((i * 0.6180339887) % 1) - 0.5) * colW * 0.55;
    const dots = [];
    Y.forEach((row, i) => row.forEach((v, j) => {
      const x0 = xr(i), y0 = raw.y(v), x1 = cx(j) + jit(i), y1 = yr(ns.res[i][j]);
      dots.push(s('circle', { cx: x0, cy: y0, r: 2.6, class: `${RUN_CLASS(j + 1)} sa-mv`,
        style: `--dx:${(x1 - x0).toFixed(1)}px;--dy:${(y1 - y0).toFixed(1)}px;--i:${(i % 20) * 12}ms` }));
    }));
    const nodes = [
      // 박자 1: die 수준 그대로
      s('g', { 'data-b': 0, 'data-u': 0 }, [
        s('line', { x1: PX0, x2: PX0, y1: Y0 - 6, y2: Y1 + 6, class: 'sc-axis' }),
        s('text', { x: PX0 - 6, y: Y0 + 4, class: 'sc-t end' }, fmt(raw.hi)),
        s('text', { x: PX0 - 6, y: Y1 + 4, class: 'sc-t end' }, fmt(raw.lo)),
        raw.log ? s('text', { x: PX0 - 6, y: (Y0 + Y1) / 2, class: 'sc-t muted end' }, 'log 눈금') : null,
        s('text', { x: PX0, y: Y1 + 22, class: 'sc-t muted' }, `die 1 … ${n} (가로) · 색 = POR 회차`)
      ]),
      // 박자 2~: die 평균을 뺀 값, 회차별 칸
      s('g', { 'data-b': 1 }, [
        s('line', { x1: PX0, x2: PX1, y1: yr(0), y2: yr(0), class: 'sa-zero' }),
        s('text', { x: PX0 - 6, y: yr(0) + 4, class: 'sc-t end' }, '0'),
        s('text', { x: PX0 - 6, y: Y0 + 4, class: 'sc-t end' }, fmt(lim, true)),
        s('text', { x: PX0 - 6, y: Y1 + 4, class: 'sc-t end' }, fmt(-lim)),
        ...Array.from({ length: J }, (_, j) => s('text', { x: cx(j), y: Y1 + 22, class: 'sc-t por mid' }, `POR ${j + 1}회`)),
        ...Array.from({ length: J - 1 }, (_, j) => s('line', { x1: PX0 + (j + 1) * colW, x2: PX0 + (j + 1) * colW, y1: Y0, y2: Y1, class: 'sa-sep' }))
      ]),
      s('g', { 'data-b': 1, class: 'sa-stay' }, dots),
      // 박자 4: 반복 흔들림 띠
      s('g', { 'data-b': 3 }, ns.runs.map((r, j) => s('rect', { x: cx(j) - colW * 0.36, y: yr(r + ns.sDie),
        width: colW * 0.72, height: Math.max(2, yr(r - ns.sDie) - yr(r + ns.sDie)), rx: 6, class: 'sa-sdie' }))),
      // 박자 3: 회차 이동 선
      s('g', { 'data-b': 2 }, ns.runs.flatMap((r, j) => [
        s('line', { x1: cx(j) - colW * 0.4, x2: cx(j) + colW * 0.4, y1: yr(r), y2: yr(r), class: 'sa-runline' }),
        s('text', { x: cx(j), y: Math.max(Y0 - 4, yr(r + ns.sDie) - 7), class: 'sc-t por mid sa-halo' }, `이동 ${fmt(r, true)}`)])),
      s('g', { 'data-b': 3 }, [
        s('text', { x: PX0, y: Y1 + 44, class: 'sc-t sa-sdie-t' }, `띠 = 회차 이동 선 ± σ_die`)])
    ];
    const runZero = t.step2.sigma_run === 0;
    const beats = [
      'POR 값: die마다 수준이 다르다',
      'die마다 자기 평균을 빼면 흔들림만 남는다',
      '회차마다 다 같이 밀린 만큼 = 회차 이동',
      '밀린 선 둘레로 die마다 흔들림 = 반복 흔들림',
      `σ_die ${fmt(t.step2.sigma_die)} · σ_run ${fmt(t.step2.sigma_run)}`
    ];
    const result = h('div', { class: 'scene-result sa-result', 'data-b': 4 }, [
      h('div', { class: 'sa-num' }, [h('span', {}, 'σ_die · 반복 흔들림'), h('b', {}, fmt(t.step2.sigma_die))]),
      h('div', { class: 'sa-num' }, [h('span', {}, 'σ_run · 회차 이동'), h('b', {}, fmt(t.step2.sigma_run))]),
      h('p', { class: 'res-why' }, runZero
        ? '회차 이동이 반복 흔들림으로 설명되는 만큼뿐이라 σ_run = 0. σ_die는 ③ LoQ에 쓴다.'
        : 'σ_die는 ③ LoQ에, σ_run은 ⑤ 허용폭 Δ의 회차 몫에 쓴다.')
    ]);
    return { nodes: [s('svg', { viewBox: `0 0 ${W} ${Y1 + 50}`, class: 'scene-svg', role: 'img',
      'aria-label': `${t.name} 예제: POR 흔들림을 회차 이동과 반복 흔들림으로 나누기` }, nodes), result], beats };
  });

  // ---------- ③ LoQ와 ITEM 유형: LoQ 선, POR 값만 보고 분류 → 판정 길 ----------
  const AXES = [['valid', '판정 가능'], ['sign', '부호'], ['level', '수준'], ['resolution', '분해능'],
    ['shape', '모양'], ['noise', '잡음'], ['scale', '척도'], ['run', '회차']];
  // 분류 값마다 쉬운 풀이 한 줄. classify.py AXES 가 낼 수 있는 값 전부 (tests/test_sop_tables.py 가 맞춰 본다)
  const GLOSS = {
    valid: { '정상': '판정할 수 있다', 'die 부족': 'die가 10개보다 적어 판정하지 않는다' },
    sign: { '부호 섞임': '+ 값과 − 값이 함께 있다', '0 포함': '0인 값이 있다', '양수만': '모든 값이 0보다 크다',
      '음수만': '모든 값이 0보다 작다', '값 없음': 'Open 코드를 빼면 남는 값이 없다' },
    level: { '0 중심': '+와 −가 섞여 0 둘레에 있다 (크기가 LoQ보다 작다)', '바닥 아래': 'POR 중앙값이 LoQ보다 작다',
      '바닥 근처': 'LoQ의 1~2배. 숫자로 읽지만 바닥에 가깝다', '정량': 'LoQ의 2배 이상. 숫자로 믿고 견준다' },
    resolution: { '계단': '값이 띄엄띄엄 찍히고, 한 칸이 Δ의 10% 이상이다', '연속': '값 간격이 Δ에 비해 아주 작다' },
    shape: { '두 덩어리': 'die 값이 두 무리로 갈린다', '튀는 die': '몸통에서 멀리 떨어진 die가 있다',
      '한계에 걸림': 'Open 코드가 있거나, 최댓값·최솟값에 붙은 값이 5% 이상이다', '한 덩어리': '특별한 모양 없이 한 무리다' },
    noise: { '일정': '잡음 크기가 값과 상관없다', '비례': '값이 크면 잡음도 그만큼 크다',
      '위로 갈수록 벌어짐': '값이 클수록 잡음이 비례보다 더 커진다', '아래로 갈수록 벌어짐': '값이 작을수록 잡음이 커진다',
      '사이': '값이 크면 잡음이 조금 커진다 (일정과 비례 사이)',
      '판별 불가': '값 폭이 좁거나 die가 적거나, 일정·비례 둘 다 맞아 못 정한다' },
    scale: { 'log': '배율(몇 %)로 견주는 것이 맞다', 'linear': '차이(빼기)로 견주는 것이 맞다',
      '판별 불가': '값 폭이 좁아 척도를 정하지 않는다' },
    run: { '회차 밀림': '밀린 POR 회차를 따라 이 ITEM도 움직였다', '조건 불안정': 'POR 회차끼리 값이 옮겨 갔다',
      '회차 흔들림': '같은 die를 다시 잰 값 차이가 보통 Δ 이상이다', '안정': 'POR 회차에 문제가 없다' }
  };
  const BEND = ' (꺾임)';
  function glossOf(k, v) {
    if (k === 'valid' && !GLOSS.valid[v]) return `POR 값만 봐도 판정 제외 원인이 있다 (${v})`;
    const base = String(v).endsWith(BEND) ? String(v).slice(0, -BEND.length) : String(v);
    const line = base.split(';').map(x => GLOSS[k][x]).filter(Boolean).join(' · ');
    if (!line) throw new Error(`분류 값 풀이 없음: ${k} = ${v}`);
    return base === v ? line : `${line}. 아래·위 절반의 모양이 다르다 (꺾임)`;
  }
  // classify.ROUTES 순서. keys = 그 길을 고르게 한 분류 축
  const ROUTES = [
    ['제외', '판정 가능이 정상이 아님', () => ['valid']],
    ['한계 비교', '모양에 한계에 걸림', () => ['shape']],
    ['절대 허용폭', '수준 0 중심, 또는 계단 + 정량·바닥 근처', c => (c.level === '0 중심' ? ['level'] : ['level', 'resolution'])],
    ['LoQ 판정', '수준 바닥 아래', () => ['level']],
    ['log TOST', '척도 log, 부호가 하나', () => ['scale', 'sign']],
    ['선형 TOST', '위 어느 것도 아님', () => []]
  ];
  defineScene('loq-route', t => {
    const st = t.step3, cls = st.cls;
    const ri = ROUTES.findIndex(r => r[0] === st.route);
    if (ri < 0) throw new Error(`모르는 판정 길 ${st.route}`);
    const keys = ROUTES[ri][2](cls);
    const sigma = st.LoQ / 10;
    const cands = [['POR 반복', 'σ_die (②)', t.step2.sigma_die], ['데이터 분해능', '값 간격 ÷ √12', (t.step5.resolution_step || 0) / Math.sqrt(12)]];
    if (!cands.some(c => c[0] === st.limit_source)) cands.push([st.limit_source, st.limit_source, sigma]);
    same(Math.max(...cands.map(c => c[2])), sigma, 'LoQ / 10');
    const xs = scale(0, sigma * 1.05, X0, 470);
    const nodes = [];
    // 박자 1: σ 후보 → LoQ
    nodes.push(s('g', { 'data-b': 0 }, [
      s('text', { x: 0, y: 18, class: 'sc-h' }, 'σ 고르기'),
      s('text', { x: 0, y: 36, class: 'sc-sub' }, '후보 중 가장 큰 것'),
      ...cands.flatMap(([src, lab, v], i) => {
        const y = 8 + i * 26, on = src === st.limit_source;
        return [s('text', { x: X0 - 8, y: y + 13, class: `sc-t end${on ? ' por' : ''}` }, lab),
          s('rect', { x: X0, y, width: Math.max(2, xs(v) - X0), height: 16, rx: 4, class: on ? 'sa-bar-on' : 'sa-bar' }),
          s('text', { x: Math.max(X0, xs(v)) + 6, y: y + 13, class: `sc-t${on ? ' por' : ''}` }, fmt(v))];
      }),
      s('text', { x: X1, y: 22, class: 'sc-t por end' }, '× 10 →'),
      s('text', { x: X1, y: 44, class: 'sa-big end' }, `LoQ ${fmt(st.LoQ)}`)
    ]));
    // 박자 2: 값 축 위의 POR 중앙값과 LoQ
    const m = Math.abs(st.por_median), ay = 128;
    const xa = scale(0, Math.max(m, st.LoQ) * 1.22, X0, X1);
    const above = m >= st.LoQ;
    nodes.push(s('g', { 'data-b': 1 }, [
      s('text', { x: 0, y: ay - 14, class: 'sc-h' }, 'POR 값의 크기'),
      s('text', { x: 0, y: ay + 4, class: 'sc-sub' }, `값 위치: ${st.zone}`),
      s('rect', { x: X0, y: ay - 22, width: xa(st.LoQ) - X0, height: 44, rx: 6, class: 'sc-below' }),
      xa(st.LoQ) - X0 > 46 ? s('text', { x: X0 + 6, y: ay + 16, class: 'sc-t muted' }, xa(st.LoQ) - X0 > 120 ? "'<LoQ'로 보고" : '<LoQ') : null,
      s('line', { x1: X0, x2: X1, y1: ay, y2: ay, class: 'sc-axis' }),
      s('line', { x1: xa(st.LoD), x2: xa(st.LoD), y1: ay - 10, y2: ay + 22, class: 'sa-lod' }),
      xa(st.LoD) - X0 > 28 ? s('text', { x: xa(st.LoD), y: ay + 36, class: 'sc-t muted mid' }, 'LoD') : null,
      s('line', { x1: xa(st.LoQ), x2: xa(st.LoQ), y1: ay - 30, y2: ay + 24, class: 'sc-loq' }),
      s('text', { x: xa(st.LoQ), y: ay - 36, class: 'sc-t por mid' }, `LoQ ${fmt(st.LoQ)}`),
      s('text', { x: X0, y: ay + 36, class: 'sc-t muted mid' }, '0'),
      s('circle', { cx: xa(m), cy: ay, r: 6, class: 'sc-por' }),
      s('text', { x: Math.min(X1 - 70, Math.max(X0 + 70, xa(m))), y: ay - 12, class: 'sc-t por mid sa-halo' }, `|POR 중앙값| ${fmt(m)}`)
    ]));
    // 박자 3: 분류 칩, 박자 4: 판정 길
    const by = 196, CW = 166, CH = 44;
    const chipAt = i => [(i % 2) * (CW + 8), by + 30 + Math.floor(i / 2) * (CH + 8)];
    nodes.push(s('g', { 'data-b': 2 }, [
      s('text', { x: 0, y: by + 14, class: 'sc-h' }, 'POR 값만 보고 분류'),
      ...AXES.flatMap(([k, lab], i) => {
        const [cx0, cy0] = chipAt(i);
        return [s('rect', { x: cx0, y: cy0, width: CW, height: CH, rx: 10, class: 'sa-chip' }),
          s('text', { x: cx0 + 12, y: cy0 + 17, class: 'sa-chip-k' }, lab),
          s('text', { x: cx0 + 12, y: cy0 + 36, class: 'sa-chip-v' }, cls[k] || '–')];
      })
    ]));
    nodes.push(s('g', { 'data-b': 3 }, keys.map(k => {
      const [cx0, cy0] = chipAt(AXES.findIndex(a => a[0] === k));
      return s('rect', { x: cx0, y: cy0, width: CW, height: CH, rx: 10, class: 'sa-chip-key' });
    })));
    const LX = 372, LW = W - LX, RH = 40;
    nodes.push(s('g', { 'data-b': 2 }, [
      s('text', { x: LX, y: by + 14, class: 'sc-h' }, '판정 길 (위에서부터)'),
      ...ROUTES.flatMap(([name, cond], i) => {
        const y = by + 30 + i * RH;
        return [s('rect', { x: LX, y, width: LW, height: RH - 6, rx: 8, class: 'sa-route' }),
          s('text', { x: LX + 12, y: y + 15, class: 'sa-route-n' }, name),
          s('text', { x: LX + 12, y: y + 29, class: 'sa-route-c' }, cond)];
      })
    ]));
    nodes.push(s('g', { 'data-b': 3 }, ROUTES.flatMap((_, i) => {
      const y = by + 30 + i * RH;
      if (i < ri) return [s('rect', { x: LX, y, width: LW, height: RH - 6, rx: 8, class: 'sa-route-no' }),
        s('text', { x: X1 - 6, y: y + 22, class: 'sa-mark-no end' }, '아님')];
      if (i === ri) return [s('rect', { x: LX, y, width: LW, height: RH - 6, rx: 8, class: 'sa-route-yes' }),
        s('text', { x: X1 - 6, y: y + 22, class: 'sa-mark-yes end' }, '✓ 이 예제')];
      return [s('rect', { x: LX, y, width: LW, height: RH - 6, rx: 8, class: 'sa-route-skip' })];
    })));
    const beats = [
      `σ 후보 중 큰 것 × 10 = LoQ ${fmt(st.LoQ)}`,
      above ? 'POR 중앙값이 LoQ 위 → 숫자로 비교한다' : "POR 중앙값이 LoQ 아래 → '<LoQ'로 보고",
      'POR 값만 보고 여덟 가지로 나눈다',
      `위에서부터 처음 맞는 길 → ${st.route}`
    ];
    const gloss = h('div', { class: 'sa-gloss', 'data-b': 2 }, [
      h('p', { class: 'sa-gloss-h' }, '이 예제의 분류 값 풀이'),
      h('dl', {}, AXES.flatMap(([k, lab]) => [h('dt', {}, [`${lab} `, h('b', {}, cls[k] || '–')]),
        h('dd', {}, cls[k] ? glossOf(k, cls[k]) : '–')]))]);
    return { nodes: [s('svg', { viewBox: `0 0 ${W} ${by + 30 + ROUTES.length * RH}`, class: 'scene-svg', role: 'img',
      'aria-label': `${t.name} 예제: LoQ와 ITEM 유형, 판정 길` }, nodes), gloss], beats };
  });

  // ---------- 예제 카드 ----------
  const base0 = TRACK[0];
  TRACK[0] = t => {
    const c = base0(t);
    const ratio = t.step3.por_median ? 100 * t.step2.sigma_run / Math.abs(t.step3.por_median) : null;
    return {
      ...c,
      does: 'die가 10개 이상인지, 회차 이동(σ_run)에 J가 충분한지 본다.',
      output: [['판정', t.n_die >= 10 ? 'die 수 충분' : 'die 부족 → 미결'],
        ['σ_run ÷ |POR 중앙값|', ratio === null ? '–' : `${fmt(ratio, false, '')}%`],
        [`J ${t.J} 기준`, `${fmt(5 / t.step5.t_factor, false, '')}% 이하`]]
    };
  };
  const base1 = TRACK[1];
  TRACK[1] = t => {
    const i = pickDie(t, Math.min(12, t.n_die)), id = t.raw.die[i];
    return {
      ...base1(t),
      inputs: [[`${id} POR`, t.raw.por[i].map(v => fmt(v)).join(' · ')], [`${id} DOE`, fmt(t.raw.doe[i])]],
      output: [[`${id}의 d`, fmt(t.raw.d[i], true)], ['die 수', `${t.n_die}개`]]
    };
  };
  // 카드 그림: LoQ 이름표는 선 위, POR 중앙값 이름표는 점 아래 (두 이름표가 겹치지 않게)
  const base3 = TRACK[3];
  TRACK[3] = t => {
    const m = Math.abs(t.step3.por_median), q = t.step3.LoQ;
    const x = scale(0, Math.max(m, q) * 1.2, 4, 256);
    const clamp = v => Math.min(214, Math.max(46, v));
    return {
      ...base3(t),
      mini: miniSvg(260, 62, [
        s('rect', { x: 4, y: 18, width: x(q) - 4, height: 22, class: 'm-below' }),
        s('line', { x1: 4, x2: 256, y1: 29, y2: 29, class: 'sc-axis' }),
        s('line', { x1: x(q), x2: x(q), y1: 14, y2: 44, class: 'm-loq' }),
        s('text', { x: clamp(x(q)), y: 10, 'text-anchor': 'middle' }, `LoQ ${fmt(q)}`),
        s('circle', { cx: x(m), cy: 29, r: 5, class: 'm-por' }),
        s('text', { x: clamp(x(m)), y: 58, 'text-anchor': 'middle' }, `|POR 중앙값| ${fmt(m)}`)])
    };
  };
})();
