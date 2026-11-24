(() => {
  'use strict';

  const D = window.SOP_JOURNEYS;
  const SVGNS = 'http://www.w3.org/2000/svg';
  const params = new URLSearchParams(location.search);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const still = reduced || params.has('still');
  const BEAT_MS = 1900;

  const store = {
    get(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* 저장 못 하면 이 쪽에서만 유지 */ } }
  };

  function h(tag, attrs, kids) {
    const el = document.createElement(tag);
    return fill(el, attrs, kids);
  }
  function s(tag, attrs, kids) {
    const el = document.createElementNS(SVGNS, tag);
    return fill(el, attrs, kids);
  }
  function fill(el, attrs, kids) {
    Object.entries(attrs || {}).forEach(([k, v]) => { if (v !== null && v !== undefined) el.setAttribute(k, v); });
    [].concat(kids === undefined ? [] : kids).forEach(k => {
      if (k !== null && k !== undefined && k !== false) el.append(k instanceof Node ? k : String(k));
    });
    return el;
  }

  // ---------- 숫자와 판정 말 ----------
  const SI = [[1e6, 'M'], [1e3, 'k'], [1, ''], [1e-3, 'm'], [1e-6, 'µ'], [1e-9, 'n'], [1e-12, 'p'], [1e-15, 'f']];
  const UNIT_NAME = { ohm: 'Ω' };
  // unit 을 안 주면 지금 고른 예제의 단위. 단위가 있으면 1e-12 → 1 pA 처럼 SI 접두어로, '' 이면 단위 없는 수
  function fmt(x, signed, unit) {
    if (x === null || x === undefined || !isFinite(x)) return '–';
    const u = unit === undefined ? (D && D.types[typeKey] ? D.types[typeKey].unit : '') : unit;
    const a = Math.abs(x);
    let t;
    if (u) {
      const [f, pre] = a === 0 ? [1, ''] : (SI.find(([f]) => a >= f * 0.9995) || SI[SI.length - 1]);
      t = `${Number((x / f).toPrecision(3))} ${pre}${UNIT_NAME[u] || u}`;
    } else {
      t = a !== 0 && (a >= 1e5 || a < 1e-3) ? x.toExponential(2) : String(Number(x.toPrecision(4)));
    }
    if (signed && x > 0) t = '+' + t;
    return t.replace('-', '−');
  }
  const VCLASS = { '동등': 'eq', '미결': 'hold', '차이': 'diff', '판정 제외': 'excl' };
  const BASIS = {
    linear: '1단계 TOST', loq: '2단계 LoQ 판정', log: '3단계 · log TOST', abs: '3단계 · 절대 허용폭',
    accuracy: '3단계 · 장비 정확도 폭', limit: '3단계 · 한계 비교'
  };
  function pill(v, extra) {
    return h('span', { class: `v v-${VCLASS[v] || 'none'}${extra ? ' ' + extra : ''}` }, v || '없음');
  }
  const MARKS = '⓪①②③④⑤⑥⑦';

  // ---------- 쉽게 | 전문까지 ----------
  function setLayer(layer, save) {
    document.documentElement.setAttribute('data-layer', layer);
    document.querySelectorAll('details.expert').forEach(d => { d.open = layer === 'expert'; });
    document.querySelectorAll('[data-set-layer]').forEach(b =>
      b.setAttribute('aria-pressed', String(b.dataset.setLayer === layer)));
    if (save) store.set('sop-layer', layer);
  }
  function initLayer() {
    const want = params.get('layer') || document.documentElement.getAttribute('data-layer');
    setLayer(want === 'expert' ? 'expert' : 'easy', false);
    document.querySelectorAll('[data-set-layer]').forEach(b =>
      b.addEventListener('click', () => setLayer(b.dataset.setLayer, true)));
    const reveal = () => {
      const id = decodeURIComponent(location.hash.slice(1));
      const target = id && document.getElementById(id);
      for (let p = target; p; p = p.parentElement) if (p.tagName === 'DETAILS') p.open = true;
      if (target) target.scrollIntoView();
    };
    window.addEventListener('hashchange', reveal);
    if (location.hash) reveal();
  }

  // ---------- 예제 유형 (쪽 사이에 이어짐) ----------
  const types = D ? D.order.filter(k => D.types[k]) : [];
  const pick = k => (types.includes(k) ? k : null);
  let typeKey = pick(params.get('type')) || pick(store.get('sop-type')) || types[0];
  const onType = [];
  function setType(k) {
    typeKey = k;
    store.set('sop-type', k);
    try {
      const u = new URL(location.href);
      u.searchParams.set('type', k);
      history.replaceState(null, '', u.href);
    } catch (e) { /* file:// 에서 막히면 주소만 그대로 */ }
    onType.forEach(f => f());
  }
  const current = () => D.types[typeKey];
  function withType(href) {
    const m = /^([\w-]+\.html)(\?[^#]*)?(#.*)?$/.exec(href);
    if (!m || !typeKey) return href;
    return `${m[1]}?type=${encodeURIComponent(typeKey)}${m[3] || ''}`;
  }
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[href]');
    if (a && typeKey) a.setAttribute('href', withType(a.getAttribute('href')));
  });

  function initTypebar() {
    const first = document.querySelector('[data-scene],[data-tracker]');
    if (!first) return;
    if (!types.length) throw new Error('예제 자료(SOP_JOURNEYS)가 없습니다');
    const tabs = types.map(k => {
      const b = h('button', { type: 'button', role: 'tab', class: 'tab', 'data-type': k }, D.types[k].name);
      b.addEventListener('click', () => setType(k));
      return b;
    });
    const story = h('p', { class: 'typebar-story' });
    const bar = h('div', { class: 'typebar' }, [
      h('div', { class: 'typebar-row', role: 'tablist', 'aria-label': '예제 ITEM 유형' },
        [h('span', { class: 'typebar-label' }, '예제 ITEM'), ...tabs]),
      story
    ]);
    first.before(bar);
    const sync = () => {
      tabs.forEach(b => b.setAttribute('aria-selected', String(b.dataset.type === typeKey)));
      const t = current();
      story.replaceChildren(h('b', {}, t.item), ` · ${t.unit} · ${t.story}`);
    };
    onType.push(sync);
    sync();
  }

  // ---------- 작은 그림 도구 ----------
  function scale(d0, d1, x0, x1) {
    const k = (x1 - x0) / ((d1 - d0) || 1);
    return v => x0 + (v - d0) * k;
  }
  function domain(values, pad) {
    const v = values.filter(x => x !== null && isFinite(x));
    let lo = Math.min(...v), hi = Math.max(...v);
    const span = (hi - lo) || Math.abs(hi) || 1;
    return [lo - span * pad, hi + span * pad];
  }
  function miniSvg(w, hgt, kids) {
    return s('svg', { viewBox: `0 0 ${w} ${hgt}`, class: 'mini-svg', role: 'img' }, kids);
  }

  // ---------- 예제 카드 (단계마다) ----------
  const TRACK = {
    0: t => ({
      inputs: [['die 수', `${t.n_die}개`], ['POR 회차 J', `${t.J}회`]],
      does: 'die가 10개 이상이어야 판정한다. 모자라면 미결.',
      output: [['준비', `die ${t.n_die}개 · POR ${t.J}회 + DOE 1회`]],
      mini: miniDies(t)
    }),
    1: t => ({
      inputs: [[`${t.raw.die[0]} POR`, t.raw.por[0].map(v => fmt(v)).join(' · ')], [`${t.raw.die[0]} DOE`, fmt(t.raw.doe[0])]],
      does: 'die마다 POR를 J번, DOE를 1번 잰다. 차이 d = DOE − POR 평균.',
      output: [[`${t.raw.die[0]}의 d`, fmt(t.raw.d[0], true)]],
      mini: miniRaw(t)
    }),
    2: t => ({
      inputs: [['POR 값', `die ${t.n_die}개 × ${t.J}회`]],
      does: '같은 die를 다시 잰 흔들림(σ_die)과 회차마다 다 같이 밀리는 크기(σ_run)로 나눈다.',
      output: [['σ_die', fmt(t.step2.sigma_die)], ['σ_run', fmt(t.step2.sigma_run)],
        ['측정 정밀도', `${fmt(t.step2.meas_precision_pct, false, '')}%`]],
      mini: miniBars([['σ_die', t.step2.sigma_die, 'por'], ['σ_run', t.step2.sigma_run, 'aux']])
    }),
    3: t => ({
      inputs: [['POR 중앙값', fmt(t.step3.por_median)], ['σ 출처', t.step3.limit_source]],
      does: 'LoQ = 10σ. POR 중앙값이 LoQ보다 작으면 LoQ 아래 ITEM. POR 값만 보고 판정 길을 고른다.',
      output: [['LoQ', fmt(t.step3.LoQ)], ['구간', t.step3.zone], ['판정 길', t.step3.route]],
      mini: miniLoq(t)
    }),
    4: t => ({
      inputs: [['die별 차이 d', `${t.n_die}개`]],
      does: `d를 크기 순으로 세워 가운데 값과 ${t.step4.ci_rank_k}번째 · ${t.n_die - t.step4.ci_rank_k + 1}번째 값을 90% 구간으로 삼는다.`,
      output: [['중앙값', fmt(t.step4.center, true)], ['90% 구간', `${fmt(t.step4.ci_low, true)} ~ ${fmt(t.step4.ci_high, true)}`]],
      mini: miniSorted(t)
    }),
    5: t => ({
      inputs: [['5% × |POR 중앙값|', fmt(t.step5.policy_margin)], ['회차 몫 t·√(1+1/J)·σ_run', fmt(t.step5.run_margin)]],
      does: '두 몫을 더해 허용폭 Δ를 만든다. 유형에 따라 판정 길이 다른 허용폭을 쓴다.',
      output: [['Δ', `±${fmt(t.step5.delta)}`], ['판정에 쓴 폭', `${t.step5.used.name} ${fmt(t.step5.used.value)}`]],
      mini: miniBars([['5% 몫', t.step5.policy_margin, 'eq'], ['회차 몫', t.step5.run_margin, 'aux']], true)
    }),
    6: t => {
      const st = t.step6;
      const inputs = [['90% 구간', `${fmt(t.step4.ci_low, true)} ~ ${fmt(t.step4.ci_high, true)}`], ['허용폭 Δ', `±${fmt(t.step5.delta)}`]];
      if (st.stage2) inputs.push(['LoQ', fmt(t.step3.LoQ)]);
      if (st.stage3) inputs.push(['판정 길', st.stage3.route]);
      let does = '1단계 TOST로 구간을 ±Δ와 견준다.';
      if (st.stage2) does += ' POR 값이 LoQ 아래라 2단계 LoQ 판정도 한다.';
      if (st.stage3) does += ` 동등이 아니라 판정 길 '${st.stage3.route}'에서 다시 본다.`;
      return {
        inputs, does,
        output: [['최종 판정', pill(st.final.verdict)], ['정한 곳', BASIS[st.final.basis] || st.final.basis]],
        mini: miniStages(st)
      };
    },
    7: t => ({
      inputs: [['최종 판정', pill(t.final.verdict)]],
      does: t.step7.cause ? `원인: ${t.step7.cause}` : '동등이면 더 할 일이 없다.',
      output: [['할 일', t.step7.action]],
      mini: null
    })
  };

  function miniDies(t) {
    const n = t.n_die, per = 15, r = 4;
    const rows = Math.ceil(n / per);
    return miniSvg(per * 12, rows * 12, Array.from({ length: n }, (_, i) =>
      s('circle', { cx: 6 + (i % per) * 12, cy: 6 + Math.floor(i / per) * 12, r, class: 'm-die' })));
  }
  function miniRaw(t) {
    const k = Math.min(10, t.n_die);
    const vals = [];
    for (let i = 0; i < k; i++) vals.push(...t.raw.por[i], t.raw.doe[i]);
    const [a, b] = domain(vals, 0.1);
    const y = scale(a, b, 70, 6);
    const kids = [];
    for (let i = 0; i < k; i++) {
      const x = 12 + i * 20;
      t.raw.por[i].forEach(v => kids.push(s('circle', { cx: x - 3, cy: y(v), r: 2.6, class: 'm-por' })));
      const d = y(t.raw.doe[i]);
      kids.push(s('path', { d: `M${x + 5} ${d - 4}l4 4l-4 4l-4 -4z`, class: 'm-doe' }));
    }
    return miniSvg(k * 20 + 8, 76, kids);
  }
  function miniBars(rows, stacked) {
    const max = stacked ? rows.reduce((a, r) => a + (r[1] || 0), 0) : Math.max(...rows.map(r => r[1] || 0));
    const x = scale(0, max || 1, 0, 200);
    if (stacked) {
      let at = 0;
      const kids = rows.map(([lab, v, c]) => {
        const g = s('g', {}, [s('rect', { x: x(at), y: 4, width: Math.max(1, x(v || 0)), height: 16, rx: 3, class: `m-${c}` }),
          s('text', { x: x(at) + 4, y: 36, class: 'm-t' }, lab)]);
        at += v || 0;
        return g;
      });
      return miniSvg(220, 42, kids);
    }
    return miniSvg(260, rows.length * 24, rows.map(([lab, v, c], i) => s('g', {}, [
      s('text', { x: 0, y: i * 24 + 15, class: 'm-t' }, lab),
      s('rect', { x: 52, y: i * 24 + 4, width: Math.max(1, x(v || 0)), height: 14, rx: 3, class: `m-${c}` })])));
  }
  function miniLoq(t) {
    const m = Math.abs(t.step3.por_median), q = t.step3.LoQ;
    const x = scale(0, Math.max(m, q) * 1.15, 4, 250);
    return miniSvg(260, 44, [
      s('rect', { x: 4, y: 8, width: x(q) - 4, height: 22, class: 'm-below' }),
      s('line', { x1: x(q), x2: x(q), y1: 2, y2: 36, class: 'm-loq' }),
      s('text', { x: x(q) + 4, y: 42, class: 'm-t' }, 'LoQ'),
      s('circle', { cx: x(m), cy: 19, r: 5, class: 'm-por' }),
      s('text', { x: 8, y: 42, class: 'm-t' }, '|POR 중앙값|')]);
  }
  function miniSorted(t) {
    const d = t.raw.d.filter(v => v !== null).slice().sort((a, b) => a - b);
    const k = t.step4.ci_rank_k;
    const y = scale(...domain(d, 0.05), 62, 6);
    const w = 260 / d.length;
    return miniSvg(264, 68, d.map((v, i) => s('circle', {
      cx: 2 + i * w + w / 2, cy: y(v), r: 2.4, class: i >= k - 1 && i <= d.length - k ? 'm-doe' : 'm-off'
    })));
  }
  function miniStages(st) {
    const cells = [['1', st.stage1], ['2', st.stage2], ['3', st.stage3]];
    return miniSvg(270, 34, cells.flatMap(([n, stg], i) => {
      const v = stg && stg.verdict;
      const x = i * 92;
      return [s('rect', { x, y: 4, width: 78, height: 26, rx: 13, class: `m-st m-${VCLASS[v] || 'skip'}` }),
        s('text', { x: x + 39, y: 21, class: 'm-st-t' }, `${n} ${v || '건너뜀'}`)];
    }));
  }

  function initTrackers() {
    document.querySelectorAll('[data-tracker]').forEach(host => {
      const step = Number(host.dataset.tracker);
      const render = () => {
        const t = current();
        const c = TRACK[step](t);
        const list = rows => h('dl', { class: 'kv' }, rows.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)]));
        const next = host.dataset.nextHref ? h('a', { class: 'tracker-next', href: host.dataset.nextHref },
          `${host.dataset.nextLabel || '다음 단계'} → ${host.dataset.nextTitle}`) : null;
        host.replaceChildren(h('div', { class: 'card' }, [
          h('p', { class: 'card-h' }, [`${MARKS[step]} 이 예제에서는 · `, h('b', {}, t.name)]),
          h('div', { class: 'flow3' }, [
            h('div', { class: 'f-in' }, [h('p', { class: 'f-h' }, '들어가는 값'), list(c.inputs)]),
            h('div', { class: 'f-do' }, [h('p', { class: 'f-h' }, '하는 일'), h('p', {}, c.does)]),
            h('div', { class: 'f-out' }, [h('p', { class: 'f-h' }, '나오는 값'), list(c.output)])
          ]),
          c.mini ? h('div', { class: 'mini' }, c.mini) : null,
          next
        ]));
      };
      onType.push(render);
      render();
    });
  }

  // ---------- 장면 (애니메이션) ----------
  const SCENES = {};
  function defineScene(name, build) { SCENES[name] = build; }
  // 장면 파일은 SOP.TRACK[단계] = t => ({inputs, does, output, mini}) 로 예제 카드를 바꿀 수 있다
  window.SOP = { defineScene, h, s, fill, fmt, pill, scale, domain, VCLASS, MARKS, BEAT_MS, TRACK, miniSvg };

  function initScenes() {
    document.querySelectorAll('[data-scene]').forEach(host => {
      const build = SCENES[host.dataset.scene];
      if (!build) throw new Error(`모르는 장면 ${host.dataset.scene}`);
      const stage = h('div', { class: 'scene-stage' });
      const cap = h('p', { class: 'scene-cap', 'aria-live': 'polite' });
      const dots = h('span', { class: 'scene-dots' });
      const btn = (label, title) => h('button', { type: 'button', class: 'scene-btn', 'aria-label': title, title }, label);
      const again = btn('⟲', '처음부터 다시'), prev = btn('◀', '앞 박자'), next = btn('▶', '다음 박자');
      host.replaceChildren(h('figure', { class: 'scene' }, [stage, h('div', { class: 'scene-foot' }, [cap,
        h('div', { class: 'scene-ctl' }, [again, prev, dots, next])])]));
      let beats = [], beat = 0, timer = 0, played = false;

      function go(k) {
        beat = Math.max(0, Math.min(beats.length - 1, k));
        stage.querySelectorAll('[data-b]').forEach(n => {
          const on = beat >= Number(n.dataset.b) && !(n.dataset.u && beat > Number(n.dataset.u));
          n.classList.toggle('on', on);
        });
        cap.replaceChildren(h('span', { class: 'scene-n' }, `${beat + 1}/${beats.length}`), beats[beat]);
        dots.replaceChildren(...beats.map((_, i) => {
          const d = h('button', { type: 'button', class: `dot${i === beat ? ' now' : ''}`, 'aria-label': `${i + 1}번째 박자` });
          d.addEventListener('click', () => { stop(); go(i); });
          return d;
        }));
        prev.disabled = beat === 0;
        next.disabled = beat === beats.length - 1;
      }
      function stop() { if (timer) window.clearInterval(timer); timer = 0; }
      function play() {
        stop();
        go(0);
        timer = window.setInterval(() => { if (beat >= beats.length - 1) stop(); else go(beat + 1); }, BEAT_MS);
      }
      function render() {
        stop();
        const out = build(current());
        beats = out.beats;
        stage.replaceChildren(...out.nodes);
        if (still || !('IntersectionObserver' in window)) go(beats.length - 1);
        else if (played) play();
        else go(0);
      }
      again.addEventListener('click', () => { played = true; play(); });
      prev.addEventListener('click', () => { stop(); go(beat - 1); });
      next.addEventListener('click', () => { stop(); go(beat + 1); });
      onType.push(render);
      render();
      if (!still && 'IntersectionObserver' in window) {
        const io = new IntersectionObserver(es => {
          if (es.some(e => e.isIntersecting) && !played) { played = true; play(); io.disconnect(); }
        }, { threshold: 0.35 });
        io.observe(host);
      }
    });
  }

  // 판정 3단계: 행마다 한 단계. 1단계 TOST → (LoQ 아래면) 2단계 → (1·2단계가 동등이 아니면) 3단계 → 최종.

  // ---------- 예제 유형 카드·목록 ----------
  function initJourneys() {
    document.querySelectorAll('[data-journeys]').forEach(host => {
      if (!types.length) throw new Error('예제 자료(SOP_JOURNEYS)가 없습니다');
      if (host.dataset.journeys === 'cards') {
        host.replaceChildren(h('div', { class: 'type-cards' }, types.map(k => {
          const t = D.types[k];
          return h('a', { class: 'type-card', href: `journey.html?type=${k}` }, [
            h('p', { class: 'tc-name' }, t.name), h('p', { class: 'tc-story' }, t.story),
            h('p', { class: 'tc-foot' }, [pill(t.final.verdict), h('span', {}, BASIS[t.final.basis] || t.final.basis)])]);
        })));
        return;
      }
      const steps = JSON.parse(host.dataset.steps);
      host.replaceChildren(...types.map(k => {
        const t = D.types[k];
        return h('section', { class: 'jr', id: `type-${k}` }, [
          h('h2', {}, [t.name, ' ', pill(t.final.verdict)]),
          h('p', { class: 'jr-story' }, [h('b', {}, t.item), ` · ${t.unit} · ${t.story}`]),
          h('ol', { class: 'jr-steps' }, steps.map(([href, title]) =>
            h('li', {}, h('a', { href: `${href}?type=${k}` }, title))))]);
      }));
    });
  }

  function run(step) {
    try { step(); } catch (e) {
      if (window.SOP_FAIL) window.SOP_FAIL(e.message);
      console.error(e);
    }
  }
  function boot() {
  run(initLayer);
  if (document.querySelector('[data-scene],[data-tracker],[data-journeys]')) {
    if (!D) run(() => { throw new Error('예제 자료(SOP_JOURNEYS)가 없습니다'); });
    else {
      run(initTypebar);
      run(initScenes);
      run(initTrackers);
      run(initJourneys);
    }
  }
  }
  // assets/scenes/*.js 가 defineScene 을 마친 뒤에 그린다 (스크립트는 body 끝에서 차례로 실행)
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
