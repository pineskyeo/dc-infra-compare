// 장면: guide 담당 (예제 따라가기 journey, 결과 읽기 reading-row · reading-map).
(() => {
  'use strict';
  const { defineScene, h, s, fmt, pill, scale, domain, VCLASS, MARKS } = window.SOP;

  const BASIS_NAME = {
    linear: '1단계 TOST', loq: '2단계 LoQ 판정', log: '3단계 · log TOST', abs: '3단계 · 절대 허용폭',
    accuracy: '3단계 · 장비 정확도 폭', limit: '3단계 · 한계 비교'
  };
  const basisName = b => BASIS_NAME[b] || b;
  const kv = rows => h('dl', { class: 'gj-kv' }, rows.map(([k, v, cls]) => h('div', { class: cls }, [h('dt', {}, k), h('dd', {}, v)])));
  const svg = (w, ht, label, kids) => s('svg', { viewBox: `0 0 ${w} ${ht}`, class: 'gj-svg', role: 'img', 'aria-label': label }, kids);
  const txt = (x, y, cls, str, b) => s('text', { x, y, class: `gt ${cls || ''}`, 'data-b': typeof b === 'number' ? b : null, style: typeof b === 'string' ? b : null }, str);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  // 1·2단계 판정 (items.csv verdict, reason): LoQ 아래 ITEM 은 2단계가 곧 1·2단계 결과
  const stage12 = t => t.step6.stage2 || t.step6.stage1;

  // 최종 판정을 정한 방법의 구간과 허용폭. LoQ 판정·한계 비교는 구간 대 허용폭 그림이 아니라 null
  function judgedBy(t) {
    const b = t.final.basis, iv = t.step4, p = t.step5;
    if (b === 'log' && iv.log) {
      return { lo: iv.log.ci_low, hi: iv.log.ci_high, c: iv.log.center, tol: p.delta_log, name: 'Δlog', unit: '', ci: 'log 구간' };
    }
    const tol = { linear: p.delta, abs: p.abs_delta, accuracy: p.used && p.used.value }[b];
    if (!tol) return null;
    return { lo: iv.ci_low, hi: iv.ci_high, c: iv.center, tol, name: { linear: 'Δ', abs: '절대 허용폭', accuracy: "Δ'" }[b], ci: '90% 구간' };
  }

  // ---------- 예제 따라가기: ITEM 하나를 ⓪ → ⑦ ----------
  const W = 640;

  function drawDies(t) {
    const cx = 96, cy = 78, R = 72, g = 14;
    const cells = [];
    for (let gy = -5; gy <= 5; gy++) for (let gx = -5; gx <= 5; gx++) {
      const x = gx * g + (gy % 2 ? g / 2 : 0), y = gy * g;
      if (Math.hypot(x, y) < R - 8) cells.push([x, y]);
    }
    cells.sort((a, b) => Math.hypot(...a) - Math.hypot(...b));
    const pick = cells.slice(0, t.n_die);
    const ox = pick.reduce((p, c) => p + c[0], 0) / pick.length, oy = pick.reduce((p, c) => p + c[1], 0) / pick.length;
    const dies = pick.map(([x, y]) => [x - ox, y - oy]).map(([x, y], i) =>
      s('circle', { cx: cx + x, cy: cy + y, r: 4.6, class: 'gj-die gj-a', style: `--i:${Math.floor(i / 6)}` }));
    const runs = [];
    for (let j = 0; j < t.J; j++) {
      const y = 40 + j * 28;
      runs.push(txt(250, y + 5, 'gj-a', `POR ${j + 1}회`), ...Array.from({ length: 10 }, (_, i) =>
        s('circle', { cx: 330 + i * 18, cy: y, r: 4, class: 'gj-por gj-a', style: `--i:${j + 1}` })));
    }
    const yd = 40 + t.J * 28;
    runs.push(txt(250, yd + 5, 'gj-a doe', 'DOE 1회'), ...Array.from({ length: 10 }, (_, i) =>
      s('path', { d: `M${330 + i * 18} ${yd - 6}l6 6l-6 6l-6 -6z`, class: 'gj-doe gj-a', style: `--i:${t.J + 1}` })));
    return svg(W, 170, `die ${t.n_die}개, POR ${t.J}회와 DOE 1회`, [
      s('circle', { cx, cy, r: R, class: 'gj-wafer' }), ...dies,
      txt(cx, 166, 'mid', `die ${t.n_die}개`), ...runs, txt(510, yd + 30, 'mid muted', '같은 die를 매번 다시 잰다')]);
  }

  // 왼쪽: die 하나를 크게 (POR J번, 평균, DOE, 차이 d). 오른쪽: 앞 die 몇 개도 같은 방식이라는 작은 그림
  function drawRaw(t) {
    const por = t.raw.por[0], doe = t.raw.doe[0], d = t.raw.d[0];
    const m0 = por.reduce((p, v) => p + v, 0) / t.J;
    const [a, b] = domain([...por, doe], 0.35);
    const y = scale(a, b, 146, 30), px = j => 118 + j * 40, xd = px(t.J) + 20;
    const kids = [
      s('rect', { x: 20, y: 8, width: xd + 92, height: 158, rx: 10, class: 'gj-focus' }),
      txt(30, 26, 'por', `die ${t.raw.die[0]}`),
      s('line', { x1: px(0) - 16, x2: xd + 14, y1: y(m0), y2: y(m0), class: 'gj-mean gj-a', style: `--i:${t.J}` }),
      txt(px(0) - 24, y(m0) + 4, 'end por gj-a', 'POR 평균', `--i:${t.J}`)];
    por.forEach((v, j) => kids.push(
      s('circle', { cx: px(j), cy: y(v), r: 6, class: 'gj-por gj-a', style: `--i:${j}` }),
      txt(px(j), 162, 'mid muted', `POR ${j + 1}`)));
    kids.push(s('path', { d: `M${xd} ${y(doe) - 9}l9 9l-9 9l-9 -9z`, class: 'gj-doe gj-a', style: `--i:${t.J + 1}` }),
      txt(xd, 162, 'mid doe', 'DOE'),
      s('line', { x1: xd + 22, x2: xd + 22, y1: y(m0), y2: y(doe), class: 'gj-d gj-a', style: `--i:${t.J + 2}` }),
      txt(xd + 30, (y(m0) + y(doe)) / 2 + 4, 'strong gj-a', `d ${fmt(d, true)}`, null));
    const k = Math.min(12, t.n_die), vals = [];
    for (let i = 0; i < k; i++) vals.push(...t.raw.por[i], t.raw.doe[i]);
    const [c0, c1] = domain(vals, 0.1);
    const yy = scale(c0, c1, 140, 40), xx = i => 400 + i * 19;
    for (let i = 0; i < k; i++) {
      t.raw.por[i].forEach(v => kids.push(s('circle', { cx: xx(i) - 3, cy: yy(v), r: 2.8, class: 'gj-por', opacity: i ? 0.55 : 1 })));
      kids.push(s('path', { d: `M${xx(i) + 5} ${yy(t.raw.doe[i]) - 4}l4 4l-4 4l-4 -4z`, class: 'gj-doe', opacity: i ? 0.55 : 1 }));
    }
    kids.push(txt(392, 26, 'muted', `앞 die ${k}개도 die마다 d`), txt(392, 162, 'muted', 'die 사이 차이는 d에 안 들어감'));
    return svg(W, 170, `die ${t.raw.die[0]}의 POR ${t.J}회, DOE, 차이 d`, kids);
  }

  function drawBars(rows, label) {
    const max = Math.max(...rows.map(r => r[1] || 0)) || 1;
    const x = scale(0, max, 0, 380);
    return svg(W, 30 + rows.length * 44, label, rows.flatMap(([name, v, cls], i) => {
      const y = 18 + i * 44;
      return [txt(110, y + 17, 'end', name),
        s('rect', { x: 122, y, width: Math.max(2, x(v || 0)), height: 24, rx: 6, class: `gj-bar ${cls} gj-a`, style: `--i:${i}` }),
        txt(132 + Math.max(2, x(v || 0)), y + 17, 'strong gj-a', fmt(v || 0))];
    }));
  }

  function drawLoq(t) {
    const m = Math.abs(t.step3.por_median), q = t.step3.LoQ;
    const x = scale(0, Math.max(m, q) * 1.3, 40, W - 40);
    const below = m < q;
    return svg(W, 150, `POR 중앙값 ${fmt(m)}, LoQ ${fmt(q)}`, [
      s('line', { x1: 40, x2: W - 40, y1: 90, y2: 90, class: 'gj-axis' }),
      s('rect', { x: 40, y: 52, width: x(q) - 40, height: 76, rx: 6, class: 'gj-below gj-a' }),
      x(q) - 40 > 120 ? txt(50, 122, 'muted gj-a', "'<LoQ' 로 보고") : txt(x(q) + 8, 122, 'muted gj-a', "← '<LoQ' 로 보고"),
      s('line', { x1: x(q), x2: x(q), y1: 40, y2: 136, class: 'gj-loq gj-a', style: '--i:1' }),
      txt(x(q), 32, 'mid por gj-a', `LoQ = 10σ · ${fmt(q)}`),
      s('circle', { cx: x(m), cy: 90, r: 7, class: 'gj-pordot gj-a', style: '--i:2' }),
      txt(clamp(x(m), 90, W - 90), below ? 74 : 112, 'mid strong gj-a', `|POR 중앙값| ${fmt(m)}`),
      txt(40, 148, 'muted', '0')]);
  }

  function drawSorted(t) {
    const d = t.raw.d.filter(v => v !== null && isFinite(v)).sort((p, q) => p - q);
    const n = d.length, k = t.step4.ci_rank_k;
    const [a, b] = domain([...d, 0], 0.08);
    const y = scale(a, b, 142, 18), step = (W - 140) / n, x = i => 70 + i * step + step / 2;
    const iv = t.step4;
    const kids = [
      s('rect', { x: 70, y: y(iv.ci_high) - 2, width: W - 140, height: Math.max(4, y(iv.ci_low) - y(iv.ci_high) + 4), rx: 4, class: 'gj-ciband gj-a', style: '--i:3' }),
      s('line', { x1: 70, x2: W - 70, y1: y(0), y2: y(0), class: 'gj-zero' }), txt(62, y(0) + 4, 'end muted', '0')];
    d.forEach((v, i) => kids.push(s('circle', {
      cx: x(i), cy: y(v), r: 3, class: `${i >= k - 1 && i <= n - k ? 'gj-in' : 'gj-off'} gj-a`, style: `--i:${i < n / 3 ? 0 : i < 2 * n / 3 ? 1 : 2}`
    })));
    kids.push(s('line', { x1: x((n - 1) / 2), x2: x((n - 1) / 2), y1: 12, y2: 150, class: 'gj-med gj-a', style: '--i:4' }),
      txt(74, 24, 'doe gj-a', `90% 구간 ${fmt(iv.ci_low, true)} ~ ${fmt(iv.ci_high, true)}`),
      txt(x((n - 1) / 2) + 6, 168, 'strong gj-a', `가운데 값 ${fmt(iv.center, true)}`),
      txt(70, 168, 'muted', `작은 d`), txt(W - 70, 168, 'end muted', `큰 d`));
    return svg(W, 174, `die별 차이 d ${n}개를 크기 순으로`, kids);
  }

  function drawDelta(t) {
    const p = t.step5, sameUnit = p.used.name === '절대 허용폭';
    const max = Math.max(p.delta, sameUnit ? p.used.value : 0) * 1.08;
    const x = scale(0, max || 1, 0, W - 220);
    const x0 = 150, kids = [];
    kids.push(txt(x0 - 12, 42, 'end', 'Δ'),
      s('rect', { x: x0, y: 26, width: Math.max(2, x(p.policy_margin)), height: 26, rx: 5, class: 'gj-bar eq gj-a' }),
      s('rect', { x: x0 + x(p.policy_margin), y: 26, width: Math.max(p.run_margin ? 2 : 0, x(p.run_margin)), height: 26, rx: 5, class: 'gj-bar aux gj-a', style: '--i:1' }),
      txt(x0 + Math.max(2, x(p.delta)) + 10, 44, 'strong gj-a', `±${fmt(p.delta)}`),
      txt(x0, 72, 'eq gj-a', `5% 몫 ${fmt(p.policy_margin)}`),
      txt(x0 + 170, 72, 'muted gj-a', `+ 회차 몫 ${fmt(p.run_margin)}`));
    if (sameUnit) {
      kids.push(txt(x0 - 12, 116, 'end', '절대 허용폭'),
        s('rect', { x: x0, y: 100, width: Math.max(2, x(p.used.value)), height: 26, rx: 5, class: 'gj-bar abs gj-a', style: '--i:2' }),
        txt(x0 + x(p.used.value) + 10, 118, 'strong gj-a', `±${fmt(p.used.value)}`),
        txt(x0, 146, 'muted gj-a', '이 ITEM은 판정 길에서 이 폭으로 본다'));
    } else if (p.used.name !== '허용폭 Δ') {
      kids.push(txt(x0, 116, 'strong gj-a', `${p.used.name} ±${fmt(p.used.value, false, '')}`),
        txt(x0, 140, 'muted gj-a', 'log 값(배율)으로 판정할 때 쓰는 폭'));
    }
    return svg(W, sameUnit || p.used.name !== '허용폭 Δ' ? 156 : 84, `허용폭 Δ ${fmt(p.delta)}`, kids);
  }

  function shiftFigure(r, label) {
    const [d0, d1] = domain([-r.tol, r.tol, r.lo, r.hi, 0], 0.14);
    const x = scale(d0, d1, 30, W - 30), y = 78;
    const mid = clamp((x(r.lo) + x(r.hi)) / 2, 130, W - 130);
    return svg(W, 140, label, [
      s('line', { x1: 30, x2: W - 30, y1: y, y2: y, class: 'gj-axis' }),
      s('rect', { x: x(-r.tol), y: y - 30, width: x(r.tol) - x(-r.tol), height: 60, rx: 8, class: 'gj-band gj-a' }),
      txt(x(-r.tol), y - 38, 'mid eq gj-a', `−${r.name}`), txt(x(r.tol), y - 38, 'mid eq gj-a', `+${r.name} ${fmt(r.tol, false, r.unit)}`),
      s('line', { x1: x(0), x2: x(0), y1: y - 10, y2: y + 10, class: 'gj-zero' }),
      s('rect', { x: Math.min(x(r.lo), x(r.hi) - 4), y: y - 6, width: Math.max(4, x(r.hi) - x(r.lo)), height: 12, rx: 6, class: 'gj-ci gj-a', style: '--i:2' }),
      s('circle', { cx: x(r.c), cy: y, r: 5, class: 'gj-c gj-a', style: '--i:2' }),
      txt(mid, y + 52, 'mid doe gj-a', `${r.ci} ${fmt(r.lo, true, r.unit)} ~ ${fmt(r.hi, true, r.unit)}`)]);
  }

  function loqFigure(t) {
    const m = t.step3.por_median, q = t.step3.LoQ, iv = t.step4;
    const a = m + iv.ci_low, z = m + iv.ci_high;
    const vals = [m, a, z, q, 0];
    if (Math.min(m, a) < 0) vals.push(-q);
    const [d0, d1] = domain(vals, 0.12);
    const x = scale(d0, d1, 30, W - 30), y = 82;
    const left = Math.max(x(-q), 30), right = Math.min(x(q), W - 30);
    return svg(W, 140, `DOE 구간 ${fmt(a)} ~ ${fmt(z)}, LoQ ${fmt(q)}`, [
      s('line', { x1: 30, x2: W - 30, y1: y, y2: y, class: 'gj-axis' }),
      s('rect', { x: left, y: y - 36, width: Math.max(0, right - left), height: 72, rx: 6, class: 'gj-below gj-a' }),
      txt(left + 8, y + 30, 'muted gj-a', "'<LoQ' 로 보고하는 곳"),
      s('line', { x1: x(q), x2: x(q), y1: y - 44, y2: y + 44, class: 'gj-loq gj-a' }),
      txt(x(q), y - 50, 'mid por gj-a', `LoQ ${fmt(q)}`),
      s('rect', { x: x(a), y: y - 18, width: Math.max(4, x(z) - x(a)), height: 12, rx: 6, class: 'gj-ci gj-a', style: '--i:2' }),
      txt(clamp((x(a) + x(z)) / 2, 120, W - 120), y + 56, 'mid doe gj-a', `DOE 구간 ${fmt(a)} ~ ${fmt(z)}`),
      s('circle', { cx: x(m), cy: y, r: 6, class: 'gj-pordot gj-a', style: '--i:1' })]);
  }

  function drawVerdict(t) {
    const r = judgedBy(t);
    return r ? shiftFigure(r, `${r.ci}과 ±${r.name}`) : loqFigure(t);
  }

  function stageChips(st) {
    const cells = [['1단계', st.stage1], ['2단계', st.stage2], ['3단계', st.stage3]].filter(([, g]) => g);
    return h('span', { class: 'gj-chips' }, cells.flatMap(([n, g], i) => [
      i ? h('span', { class: 'gj-arrow' }, '→') : null,
      h('span', { class: `gj-chip c-${VCLASS[g.verdict] || 'skip'}` }, `${n} ${g.verdict || '판정 안 함'}`)]));
  }

  // 단계마다: 한 줄 이야기, 핵심 숫자, 작은 그림. 숫자는 모두 예제 자료(SOP_JOURNEYS)에서
  const JOURNEY = [
    t => ({
      say: `die ${t.n_die}개를 POR ${t.J}회, DOE 1회 잰다. die가 10개 이상이어야 판정한다.`,
      rows: [['die 수', `${t.n_die}개`], ['POR 회차 J', `${t.J}회`], ['DOE', '1회']],
      vis: drawDies(t)
    }),
    t => {
      const m0 = t.raw.por[0].reduce((p, v) => p + v, 0) / t.J;
      return {
        say: `die ${t.raw.die[0]} 하나를 보면, DOE에서 POR ${t.J}회 평균을 뺀 값이 이 die의 차이 d.`,
        rows: [['POR 값', t.raw.por[0].map(v => fmt(v)).join(' · ')], ['POR 평균', fmt(m0)], ['DOE 값', fmt(t.raw.doe[0])],
          ['d', fmt(t.raw.d[0], true)]],
        vis: drawRaw(t)
      };
    },
    t => ({
      say: '측정 흔들림을 둘로 나눈다. 같은 die를 다시 잰 흔들림(σ_die)과 회차마다 다 같이 밀린 크기(σ_run).',
      rows: [['σ_die', fmt(t.step2.sigma_die)], ['σ_run', fmt(t.step2.sigma_run)],
        ['측정 정밀도', `${fmt(t.step2.meas_precision_pct, false, '')}%`]],
      vis: drawBars([['σ_die', t.step2.sigma_die, 'por'], ['σ_run', t.step2.sigma_run, 'aux']], 'σ_die와 σ_run')
    }),
    t => {
      const c = t.step3.cls;
      return {
        say: `POR 값만 보고 ITEM 유형을 정한다. 이 ITEM의 판정 길은 '${t.step3.route}'.`,
        rows: [['|POR 중앙값|', fmt(Math.abs(t.step3.por_median))], ['LoQ', fmt(t.step3.LoQ)], ['구간', t.step3.zone],
          ['유형', `${c.level} · ${c.resolution} · ${c.sign}`], ['판정 길', t.step3.route]],
        vis: drawLoq(t)
      };
    },
    t => ({
      say: `d ${t.n_die}개를 줄 세워 가운데 값과 90% 구간을 잡는다. 구간이 이 ITEM이 바뀐 정도.`,
      rows: [['가운데 값', fmt(t.step4.center, true)], ['90% 구간', `${fmt(t.step4.ci_low, true)} ~ ${fmt(t.step4.ci_high, true)}`],
        ['구간 끝', `${t.step4.ci_rank_k}번째 · ${t.n_die - t.step4.ci_rank_k + 1}번째`]],
      vis: drawSorted(t)
    }),
    t => {
      const p = t.step5;
      const used = p.used.name === '허용폭 Δ' ? null : [p.used.name, `±${fmt(p.used.value, false, p.used.name.startsWith('log') ? '' : undefined)}`];
      return {
        say: used ? `허용폭 Δ를 만들지만, 이 ITEM의 판정 길은 '${p.used.name}'을 쓴다.` : '5% 몫과 회차 몫을 더해 허용폭 Δ를 만든다. 이 안이면 같다고 본다.',
        rows: [['5% 몫', fmt(p.policy_margin)], ['회차 몫', fmt(p.run_margin)], ['Δ', `±${fmt(p.delta)}`], used].filter(Boolean),
        vis: drawDelta(t)
      };
    },
    t => {
      const st = t.step6;
      return {
        say: `구간을 허용폭과 견준다. 최종 판정은 ${st.final.verdict} (${basisName(st.final.basis)}).`,
        rows: [['단계', stageChips(st), 'wide'], ['최종 판정', pill(st.final.verdict)], ['정한 곳', basisName(st.final.basis)]],
        vis: drawVerdict(t)
      };
    },
    t => ({
      say: t.step7.cause ? `${t.final.verdict}이라 원인을 찾고 다음에 할 일을 정한다.` : '동등이라 더 할 일이 없다. 결과만 기록한다.',
      rows: [t.step7.cause ? ['원인', t.step7.cause] : null, ['할 일', t.step7.action]].filter(Boolean),
      vis: h('div', { class: 'gj-end' }, [pill(t.final.verdict, 'big'), h('p', { class: 'gj-why' }, t.final.why)])
    })
  ];

  // 단계 이름은 쪽 위 단계 띠(SITE 표에서 만든 것)에서 읽는다
  function stepTitles() {
    const chips = [...document.querySelectorAll('.strip a.chip')];
    return JOURNEY.map((_, k) => {
      const a = chips[k];
      return { title: a ? a.getAttribute('title') : MARKS[k], href: a ? a.getAttribute('href') : `step-${k}.html` };
    });
  }

  let at = (() => {
    const k = Number(new URLSearchParams(location.search).get('step'));
    return Number.isInteger(k) && k >= 0 && k < JOURNEY.length ? k : 0;
  })();

  defineScene('journey', t => {
    const steps = stepTitles();
    const rail = h('ol', { class: 'gj-rail', 'aria-label': '단계' });
    const panel = h('div', { class: 'gj-panel', 'aria-live': 'polite' });
    const prev = h('button', { type: 'button', class: 'gj-btn' }, '◀ 앞 단계');
    const next = h('button', { type: 'button', class: 'gj-btn gj-next' }, '다음 단계 ▶');
    const more = h('a', { class: 'gj-more' });
    const root = h('div', { class: 'gj', tabindex: '-1' }, [rail, panel, h('div', { class: 'gj-nav' }, [prev, more, next])]);

    const dots = steps.map((st, k) => {
      const b = h('button', { type: 'button', class: 'gj-dot', title: st.title, 'aria-label': st.title }, MARKS[k]);
      b.addEventListener('click', () => show(k));
      return h('li', {}, b);
    });
    rail.replaceChildren(...dots);

    function show(k) {
      at = clamp(k, 0, JOURNEY.length - 1);
      const c = JOURNEY[at](t);
      dots.forEach((li, i) => {
        const b = li.firstChild;
        b.classList.toggle('done', i < at);
        b.classList.toggle('now', i === at);
        b.setAttribute('aria-current', i === at ? 'step' : 'false');
      });
      rail.style.setProperty('--fill', `${(100 * at) / (JOURNEY.length - 1)}%`);
      panel.replaceChildren(h('div', { class: 'gj-card' }, [
        h('p', { class: 'gj-head' }, [h('span', { class: 'gj-n' }, `${at + 1} / ${JOURNEY.length}`), steps[at].title]),
        h('p', { class: 'gj-say' }, c.say),
        h('div', { class: 'gj-vis' }, c.vis),
        kv(c.rows)]));
      more.setAttribute('href', steps[at].href);
      more.textContent = `${steps[at].title} 쪽에서 자세히 →`;
      prev.disabled = at === 0;
      next.disabled = at === JOURNEY.length - 1;
      try {
        const u = new URL(location.href);
        u.searchParams.set('step', String(at));
        history.replaceState(null, '', u.href);
      } catch (e) { /* file:// 에서 막히면 주소만 그대로 */ }
    }
    prev.addEventListener('click', () => show(at - 1));
    next.addEventListener('click', () => show(at + 1));
    root.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft') show(at - 1);
      if (e.key === 'ArrowRight') show(at + 1);
    });
    show(at);
    return { nodes: [root], beats: ['◀ ▶ 로 단계를 넘긴다'] };
  });

  // ---------- 결과 읽기: items.csv 한 줄 ----------
  defineScene('reading-row', t => {
    const v12 = stage12(t).verdict, fin = t.final;
    const cell = (col, val, b) => h('div', { class: 'gr-cell' }, [
      h('span', { class: 'gr-col' }, col), h('span', { class: 'gr-val' }, val),
      ...[].concat(b).map(k => h('span', { class: 'gr-hl', 'data-b': k, 'data-u': k }))]);
    const row = h('div', { class: 'gr-row' }, [
      cell('ITEM', t.item, 0), cell('verdict', pill(v12), 3), cell('route', t.step3.route, 2),
      cell('verdict_final', pill(fin.verdict), 1), cell('verdict_basis', fin.basis, 2)]);
    const changed = v12 !== fin.verdict;
    const notes = h('ol', { class: 'gr-notes' }, [
      h('li', { 'data-b': 1 }, [h('code', {}, 'verdict_final'), ' 이 최종 판정. 집계와 차이·미결 목록은 이 열로 센다.']),
      h('li', { 'data-b': 2 }, [h('code', {}, 'verdict_basis'), ` '${fin.basis}' = ${basisName(fin.basis)}에서 정했다.`]),
      h('li', { 'data-b': 3 }, [h('code', {}, 'verdict'), changed
        ? ` 는 1·2단계 판정(${v12}). 판정 길 '${t.step3.route}'이 ${fin.verdict}로 바꿨다.`
        : ' 는 1·2단계 판정. 최종 판정과 같다.']),
      h('li', { 'data-b': 4, class: 'gr-why' }, [h('b', {}, '쉬운 말 사유 '), fin.why])]);
    return {
      nodes: [h('div', { class: 'gr' }, [h('p', { class: 'gr-file' }, 'items.csv · 한 줄 = ITEM 하나'), row, notes])],
      beats: [
        `한 줄이 ITEM 하나 (${t.item})`,
        `verdict_final = ${fin.verdict} → 이것이 판정`,
        `verdict_basis = ${fin.basis} → 판정을 정한 곳`,
        changed ? `1·2단계 ${v12} → 3단계가 ${fin.verdict}로 바꿈` : '1·2단계 판정이 그대로 최종',
        '리포트는 판정 칸에 쉬운 말 사유를 띄운다']
    };
  });

  // ---------- 결과 읽기: 판정 지도 (plots/summary.png) ----------
  // 점 = ITEM. 가로 = 구간 가운데 ÷ 허용폭, 세로 = 구간 반폭 ÷ 허용폭 (최종 판정을 정한 방법의 것)
  function mapPoint(t) {
    const r = judgedBy(t);
    if (!r || !(r.tol > 0)) return null;
    return { x: (r.lo + r.hi) / 2 / r.tol, y: (r.hi - r.lo) / 2 / r.tol };
  }

  defineScene('reading-map', t => {
    const MW = 640, MH = 330, XM = 2.6, YM = 1.4;
    const X = scale(-XM, XM, 50, MW - 20), Y = scale(0, YM, MH - 40, 30);
    const pts = (...p) => p.map(([a, b]) => `${X(a)},${Y(b)}`).join(' ');
    const side = sg => pts([sg, 0], [sg * XM, 0], [sg * XM, YM], [sg * (YM + 1), YM]);
    const all = window.SOP_JOURNEYS;
    const others = all.order.filter(k => all.types[k] !== t).map(k => mapPoint(all.types[k])).filter(Boolean);
    const p = mapPoint(t);
    const v = t.final.verdict;
    const inMap = p && Math.abs(p.x) <= XM && p.y <= YM;
    const kids = [
      s('rect', { x: X(-XM), y: Y(YM), width: X(XM) - X(-XM), height: Y(0) - Y(YM), class: 'gm-hold', 'data-b': 3 }),
      s('polygon', { points: pts([-1, 0], [1, 0], [0, 1]), class: 'gm-eq', 'data-b': 1 }),
      s('polygon', { points: side(1), class: 'gm-diff', 'data-b': 2 }),
      s('polygon', { points: side(-1), class: 'gm-diff', 'data-b': 2 }),
      s('g', { 'data-b': 0 }, [
        s('line', { x1: X(-XM), x2: X(XM), y1: Y(0), y2: Y(0), class: 'gm-axis' }),
        s('line', { x1: X(0), x2: X(0), y1: Y(0), y2: Y(YM), class: 'gm-axis' }),
        ...[-2, -1, 0, 1, 2].map(k => txt(X(k), Y(0) + 18, 'mid muted', String(k).replace('-', '−'))),
        txt(X(0) - 8, Y(1) + 4, 'end muted', '1'),
        txt(X(XM), Y(0) + 34, 'end', '이동 ÷ 허용폭 →'),
        txt(X(-XM), Y(YM) - 8, '', '↑ 흔들림(구간 반폭) ÷ 허용폭')]),
      txt(X(0), Y(0.3), 'mid gm-l eq', '동등', 1),
      txt(X(1.95), Y(0.28), 'mid gm-l diff', '차이', 2), txt(X(-1.95), Y(0.28), 'mid gm-l diff', '차이', 2),
      txt(X(0), Y(1.2), 'mid gm-l hold', '미결 (흔들려서 판단 불가)', 3), txt(X(-1.25), Y(0.95), 'mid gm-l hold', '미결', 3)
    ];
    kids.push(s('g', { 'data-b': 4 }, [
      ...others.filter(o => Math.abs(o.x) <= XM && o.y <= YM).map(o => s('circle', { cx: X(o.x), cy: Y(o.y), r: 4, class: 'gm-other' })),
      inMap ? s('circle', { cx: X(p.x), cy: Y(p.y), r: 8, class: `gm-pt ${VCLASS[v]}` }) : null,
      inMap ? txt(clamp(X(p.x), 110, MW - 110), Y(p.y) - 16, 'mid strong gm-lab', `${t.item} · ${v}`) : null]));
    const last = inMap ? `${t.item}는 ${v} 칸에 놓인다 (최종 판정 색과 같다)`
      : p ? `${t.item}는 지도 범위 밖 (${v})` : `LoQ 아래 ITEM은 이 지도 대신 summary_loq.png 에`;
    return {
      nodes: [s('svg', { viewBox: `0 0 ${MW} ${MH}`, class: 'scene-svg', role: 'img', 'aria-label': '판정 지도' }, kids)],
      beats: ['점 하나 = ITEM 하나. 가로는 이동, 세로는 흔들림', '|가로| + 세로 ≤ 1 이면 동등 (초록 삼각형)',
        '|가로| − 세로 > 1 이면 차이 (양옆)', '그 사이는 모두 미결', last]
    };
  });
})();
