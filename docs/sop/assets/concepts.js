(() => {
  'use strict';

  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function tween(update, done) {
    if (motion.matches) {
      update(1);
      if (done) done();
      return () => {};
    }
    let frame = 0;
    let cancelled = false;
    const start = performance.now();
    function step(now) {
      if (cancelled) return;
      const p = Math.min(1, (now - start) / 400);
      update(p);
      if (p < 1) frame = requestAnimationFrame(step);
      else if (done) done();
    }
    frame = requestAnimationFrame(step);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }

  function controlsFor(root) {
    const controls = root.parentElement.querySelector('.ctl');
    if (controls) controls.hidden = false;
    return controls;
  }

  function setX(line, x0, x1) {
    line.setAttribute('x1', x0);
    line.setAttribute('x2', x1);
  }

  function initSplit(root) {
    const input = document.getElementById('split-ctl');
    const play = document.getElementById('split-play');
    const out = document.getElementById('split-out');
    const live = document.getElementById('split-live');
    const liveLine = document.getElementById('split-line');
    const liveDots = Array.from(live.querySelectorAll('circle'));
    const groups = [1, 2, 3].map(k => document.getElementById(`split-r${k}`));
    const runs = [
      { r: -0.5, e: [0.6, -1.3, 0.2, -0.4, 1.5, -0.7, 0.9, -0.1] },
      { r: 0, e: [-0.5, 1.1, -2.0, 0.3, -0.2, 0.7, -0.9, 1.3] },
      { r: 0.5, e: [0.4, -0.6, 2.0, -1.1, 0.1, -1.5, 0.5, -0.3] }
    ];
    const labels = [
      '세 회차 모두 · σ_die 1.0 · σ_run 0.5',
      '1회: 전체 이동 −0.5 · 점은 점선 둘레로 따로 흔들림',
      '2회: 전체 이동 0 · 점은 점선 둘레로 따로 흔들림',
      '3회: 전체 이동 +0.5 · 점은 점선 둘레로 따로 흔들림'
    ];
    let state = 0;
    let timer = 0;
    let cancel = () => {};
    controlsFor(root);

    function stop() {
      if (timer) window.clearInterval(timer);
      timer = 0;
      play.textContent = '재생';
      play.setAttribute('aria-pressed', 'false');
    }

    function render(next, move = true) {
      cancel();
      state = next;
      input.value = String(next);
      input.setAttribute('aria-valuetext', labels[next]);
      if (next === 0) out.innerHTML = '세 회차 모두 · σ<sub>die</sub> 1.0 · σ<sub>run</sub> 0.5';
      else out.textContent = labels[next];
      if (next === 0) {
        groups.forEach(group => group.setAttribute('opacity', '1'));
        live.style.display = 'none';
        return;
      }
      const k = next - 1;
      const run = runs[k];
      const ys = run.e.map(e => 130 - (run.r + e) * 35);
      const lineY = 130 - run.r * 35;
      groups.forEach(group => group.setAttribute('opacity', '.15'));
      live.style.display = '';
      live.setAttribute('class', `r${next}`);
      const fromY = liveDots.map((dot, i) => Number(dot.getAttribute('cy')) || ys[i]);
      const fromLine = Number(liveLine.getAttribute('y1')) || lineY;
      const update = p => {
        liveDots.forEach((dot, i) => dot.setAttribute('cy', fromY[i] + (ys[i] - fromY[i]) * p));
        const y = fromLine + (lineY - fromLine) * p;
        liveLine.setAttribute('y1', y);
        liveLine.setAttribute('y2', y);
      };
      if (move) cancel = tween(update);
      else update(1);
    }

    input.addEventListener('input', () => {
      stop();
      render(Number(input.value));
    });
    play.addEventListener('click', () => {
      if (timer) {
        stop();
        return;
      }
      play.textContent = '멈춤';
      play.setAttribute('aria-pressed', 'true');
      if (state === 0) render(1);
      timer = window.setInterval(() => render(state % 3 + 1), 1200);
    });
    function motionChanged() {
      play.hidden = motion.matches;
      if (motion.matches) stop();
    }
    motion.addEventListener('change', motionChanged);
    motionChanged();
    render(0, false);
  }

  function initTost(root) {
    const input = document.getElementById('tost-ctl');
    const out = document.getElementById('tost-out');
    const ci = document.getElementById('tost-ci');
    const c0 = document.getElementById('tost-c0');
    const c1 = document.getElementById('tost-c1');
    const label = document.getElementById('tost-lab');
    const states = [
      { lo: 0.610, hi: 1.10233, cls: 'ok', label: '90% CI [0.610, 1.102] · 예시 ITEM', out: '<span class="pill ok">동등</span> 예시 ITEM 구간 [0.610, 1.102] 전체가 ±Δ 6.699 안' },
      { lo: 5.5, hi: 8.0, cls: 'hold', label: '가상 구간: +Δ에 걸침', out: '<span class="pill hold">미결</span> 가상 구간이 +Δ 6.699 선에 걸침(경계)' },
      { lo: 7.5, hi: 9.5, cls: 'bad', label: '가상 구간: +Δ 밖', out: '<span class="pill bad">차이</span> 가상 구간 전체가 +Δ 6.699 밖' }
    ];
    let cancel = () => {};
    controlsFor(root);

    function render(index, move = true) {
      cancel();
      const state = states[index];
      const x0 = 320 + state.lo * 24;
      const x1 = 320 + state.hi * 24;
      input.value = String(index + 1);
      input.setAttribute('aria-valuetext', state.label);
      out.innerHTML = state.out;
      [ci, c0, c1, label].forEach(el => el.setAttribute('class', state.cls));
      label.textContent = state.label;
      const from0 = Number(ci.getAttribute('x1'));
      const from1 = Number(ci.getAttribute('x2'));
      const update = p => {
        const a = from0 + (x0 - from0) * p;
        const b = from1 + (x1 - from1) * p;
        setX(ci, a, b);
        setX(c0, a, a);
        setX(c1, b, b);
        label.setAttribute('x', (a + b) / 2);
      };
      if (move) cancel = tween(update);
      else update(1);
    }

    input.addEventListener('input', () => render(Number(input.value) - 1));
    render(0, false);
  }

  function phiInv(p) {
    const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.383577518672690e2, -3.066479806614716e1, 2.506628277459239e0];
    const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1];
    const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838e0, -2.549732539343734e0, 4.374664141464968e0, 2.938163982698783e0];
    const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996e0, 3.754408661907416e0];
    const plow = 0.02425;
    const phigh = 1 - plow;
    let q;
    let r;
    if (p < plow) {
      q = Math.sqrt(-2 * Math.log(p));
      return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
    }
    if (p > phigh) {
      q = Math.sqrt(-2 * Math.log(1 - p));
      return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
    }
    q = p - 0.5;
    r = q * q;
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
      (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }

  function initCi(root) {
    const input = document.getElementById('ci-ctl');
    const out = document.getElementById('ci-out');
    const dots = document.getElementById('ci-dots');
    const bar = document.getElementById('ci-bar');
    const loLabel = document.getElementById('ci-lo');
    const hiLabel = document.getElementById('ci-hi');
    // EDIT: 예시 ITEM d(examples/example_wide.csv)의 앞 n개 die, 순번·구간은 도구 ci_median과 같은 규칙
    const states = [{"n": 10, "rankLo": 2, "rankHi": 9, "lo": -0.58867, "hi": 1.63167, "med": 0.74917, "loText": "−0.589", "hiText": "1.632", "text": "예시 ITEM 앞 die 10개 · 크기순 2번째 ~ 9번째 · 구간 [−0.589, 1.632] · 폭 2.220 · 포함 확률 1 − 2 × P(B ≤ 1) = 97.85%", "vals": [-1.05, -0.5887, 0.507, 0.61, 0.7267, 0.7717, 1.416, 1.5337, 1.6317, 1.7667]}, {"n": 20, "rankLo": 6, "rankHi": 15, "lo": 0.51367, "hi": 1.53367, "med": 0.74917, "loText": "0.514", "hiText": "1.534", "text": "예시 ITEM 앞 die 20개 · 크기순 6번째 ~ 15번째 · 구간 [0.514, 1.534] · 폭 1.020 · 포함 확률 1 − 2 × P(B ≤ 5) = 95.86%", "vals": [-1.05, -0.7457, -0.5887, 0.2893, 0.507, 0.5137, 0.5447, 0.61, 0.663, 0.7267, 0.7717, 0.841, 1.1, 1.416, 1.5337, 1.5937, 1.6317, 1.7667, 1.777, 2.3587]}, {"n": 30, "rankLo": 11, "rankHi": 20, "lo": 0.663, "hi": 1.21433, "med": 0.80633, "loText": "0.663", "hiText": "1.214", "text": "예시 ITEM 앞 die 30개 · 크기순 11번째 ~ 20번째 · 구간 [0.663, 1.214] · 폭 0.551 · 포함 확률 1 − 2 × P(B ≤ 10) = 90.13%", "vals": [-1.502, -1.05, -0.7457, -0.5887, 0.2893, 0.32, 0.507, 0.5137, 0.5447, 0.61, 0.663, 0.7147, 0.7267, 0.735, 0.7717, 0.841, 1.0083, 1.1, 1.1023, 1.2143, 1.2993, 1.416, 1.5337, 1.5937, 1.6317, 1.7667, 1.776, 1.777, 2.3587, 2.9217]}, {"n": 45, "rankLo": 17, "rankHi": 29, "lo": 0.71467, "hi": 1.22867, "med": 0.97867, "loText": "0.715", "hiText": "1.229", "text": "예시 ITEM 앞 die 45개 · 크기순 17번째 ~ 29번째 · 구간 [0.715, 1.229] · 폭 0.514 · 포함 확률 1 − 2 × P(B ≤ 16) = 92.75%", "vals": [-1.502, -1.3443, -1.05, -0.7457, -0.5887, -0.19, 0.2303, 0.2893, 0.32, 0.4177, 0.494, 0.507, 0.5137, 0.5447, 0.61, 0.663, 0.7147, 0.7267, 0.735, 0.7717, 0.785, 0.841, 0.9787, 1.0083, 1.0977, 1.1, 1.1023, 1.2143, 1.2287, 1.2857, 1.2993, 1.416, 1.4667, 1.5337, 1.5937, 1.6317, 1.701, 1.7667, 1.776, 1.777, 2.3587, 2.598, 2.7073, 2.9217, 3.9643]}, {"n": 60, "rankLo": 24, "rankHi": 37, "lo": 0.61, "hi": 1.10233, "med": 0.78583, "loText": "0.610", "hiText": "1.102", "text": "예시 ITEM 앞 die 60개 · 크기순 24번째 ~ 37번째 · 구간 [0.610, 1.102] · 폭 0.492 · 포함 확률 1 − 2 × P(B ≤ 23) = 90.75%", "vals": [-3.0143, -1.502, -1.3443, -1.05, -0.9303, -0.7457, -0.5887, -0.352, -0.19, -0.0207, -0.0037, 0.0237, 0.2303, 0.2893, 0.32, 0.4177, 0.454, 0.494, 0.507, 0.5137, 0.5447, 0.5527, 0.5787, 0.61, 0.663, 0.7147, 0.7267, 0.735, 0.7717, 0.785, 0.7867, 0.841, 0.9787, 1.0083, 1.0977, 1.1, 1.1023, 1.2107, 1.2143, 1.2287, 1.2857, 1.2993, 1.416, 1.4667, 1.5337, 1.5937, 1.6317, 1.701, 1.7667, 1.776, 1.777, 2.3187, 2.3587, 2.3723, 2.4483, 2.598, 2.7073, 2.8533, 2.9217, 3.9643]}];
    let cancel = () => {};
    controlsFor(root);

    function drawDots(state) {
      dots.replaceChildren();
      for (let i = 1; i <= state.n; i += 1) {
        const value = state.vals[i - 1];
        const dot = document.createElementNS(dots.namespaceURI, 'circle');
        dot.setAttribute('cx', 300 + value * 70);
        dot.setAttribute('cy', 50 + (i % 3) * 10);
        dot.setAttribute('r', '3');
        dot.setAttribute('class', i >= state.rankLo && i <= state.rankHi ? 'hi' : 'dot');
        if (i < state.rankLo || i > state.rankHi) dot.setAttribute('opacity', '.5');
        dots.appendChild(dot);
      }
    }

    function render(index, move = true) {
      cancel();
      const state = states[index];
      const x0 = 300 + state.lo * 70;
      const x1 = 300 + state.hi * 70;
      input.value = String(index);
      input.setAttribute('aria-valuetext', state.text);
      out.textContent = state.text;
      drawDots(state);
      const med = document.getElementById('ci-med'), medt = document.getElementById('ci-medt');
      if (med) { const mx = 300 + state.med * 70; med.setAttribute('x1', mx); med.setAttribute('x2', mx); if (medt) medt.setAttribute('x', mx); }
      loLabel.textContent = state.loText;
      hiLabel.textContent = state.hiText;
      const from0 = Number(bar.getAttribute('x1'));
      const from1 = Number(bar.getAttribute('x2'));
      const update = p => {
        const a = from0 + (x0 - from0) * p;
        const b = from1 + (x1 - from1) * p;
        setX(bar, a, b);
        loLabel.setAttribute('x', a);
        hiLabel.setAttribute('x', b);
      };
      if (move) cancel = tween(update);
      else update(1);
    }

    input.addEventListener('input', () => render(Number(input.value)));
    render(4, false);
  }

  function initCoef(root) {
    const input = document.getElementById('coef-ctl');
    const out = document.getElementById('coef-out');
    const ring = document.getElementById('coef-hi');
    const values = {
      2: ['6.314', '7.73'], 3: ['2.920', '3.37'], 4: ['2.353', '2.63'],
      5: ['2.132', '2.34'], 6: ['2.015', '2.18'], 7: ['1.943', '2.08'],
      8: ['1.895', '2.01'], 9: ['1.860', '1.96'], 10: ['1.833', '1.92']
    };
    let cancel = () => {};
    controlsFor(root);

    function render(j, move = true) {
      cancel();
      const [t, c] = values[j];
      const text = `J = ${j} · t = ${t} · 계수 ${c}`;
      const x = 80 + (j - 2) * 60;
      const y = 200 - Number(c) * 22;
      input.value = String(j);
      input.setAttribute('aria-valuetext', text);
      out.textContent = text;
      const fromX = Number(ring.getAttribute('cx'));
      const fromY = Number(ring.getAttribute('cy'));
      const update = p => {
        ring.setAttribute('cx', fromX + (x - fromX) * p);
        ring.setAttribute('cy', fromY + (y - fromY) * p);
      };
      if (move) cancel = tween(update);
      else update(1);
    }

    input.addEventListener('input', () => render(Number(input.value)));
    render(3, false);
  }

  function initLoq(root) {
    const input = document.getElementById('loq-ctl');
    const play = document.getElementById('loq-play');
    const out = document.getElementById('loq-out');
    const band = document.getElementById('loq-band');
    const dot = document.getElementById('loq-dot');
    const a0 = document.getElementById('loq-a0');
    const a1 = document.getElementById('loq-a1');
    const a2 = document.getElementById('loq-a2');
    // EDIT: 예시 ITEM σ_die 0.98965(LoD 3.2559 = 3.29 × σ_die, LoQ 9.8965 = 10 × σ_die)
    const states = [
      { t: 2, rsd: '49.48%', text: '실제 값 2 · σ_die 0.98965 · 상대 흔들림 0.98965 ÷ 2 = 49.48%', pill: '<span class="pill hold">LoD 3.2559 미만</span>', aria: 'LoD 3.2559 미만' },
      { t: 5, rsd: '19.79%', text: '실제 값 5 · σ_die 0.98965 · 상대 흔들림 0.98965 ÷ 5 = 19.79%', pill: '<span class="pill hold">LoQ 9.8965 미만</span>', aria: 'LoQ 9.8965 미만' },
      { t: 9.8965, rsd: '10%', text: '실제 값 9.8965 · σ_die 0.98965 · 상대 흔들림 0.98965 ÷ 9.8965 = 10%', pill: '<span class="pill ok">LoQ, 정량 시작</span>', aria: 'LoQ, 정량 시작' },
      { t: 50, rsd: '1.98%', text: '실제 값 50 · σ_die 0.98965 · 상대 흔들림 0.98965 ÷ 50 = 1.98%', pill: '<span class="pill ok">정량</span>', aria: '정량' },
      { t: 100, rsd: '0.99%', text: '실제 값 100 · σ_die 0.98965 · 상대 흔들림 0.98965 ÷ 100 = 0.99%', pill: '<span class="pill ok">정량 · 예시 ITEM 중앙값</span>', aria: '정량 · 예시 ITEM 중앙값' }
    ];
    const noise = [0.8, -1.2, 0.3, -0.5, 1.6, -0.9, 0.1, -1.9, 1.1, -0.2];
    let state = states[2];
    let timer = 0;
    let noiseIndex = 0;
    let cancel = () => {};
    controlsFor(root);

    function moveDot(x, move = true) {
      cancel();
      const from = Number(dot.getAttribute('cx'));
      const update = p => dot.setAttribute('cx', from + (x - from) * p);
      if (move) cancel = tween(update);
      else update(1);
    }

    function stop(center = true) {
      if (timer) window.clearInterval(timer);
      timer = 0;
      play.textContent = '흔들어 보기';
      play.setAttribute('aria-pressed', 'false');
      if (center) moveDot(320);
    }

    function shake() {
      const z = noise[noiseIndex % noise.length];
      noiseIndex += 1;
      moveDot(320 + z * 0.98965 * 260 / state.t);
    }

    function render(index, move = true) {
      cancel();
      state = states[index];
      const x = 320 - 0.98965 * 260 / state.t;
      const width = 2 * 0.98965 * 260 / state.t;
      input.value = String(index);
      input.setAttribute('aria-valuetext', `${state.text} · ${state.aria}`);
      out.innerHTML = `${state.text} ${state.pill}`;
      band.setAttribute('class', state.t < 9.8965 ? 'bandhold' : 'band');
      a0.textContent = '0';
      a1.textContent = String(state.t);
      a2.textContent = String(Math.round(state.t * 2 * 10000) / 10000);
      const fromX = Number(band.getAttribute('x'));
      const fromWidth = Number(band.getAttribute('width'));
      const fromDot = Number(dot.getAttribute('cx'));
      const update = p => {
        band.setAttribute('x', fromX + (x - fromX) * p);
        band.setAttribute('width', fromWidth + (width - fromWidth) * p);
        dot.setAttribute('cx', fromDot + (320 - fromDot) * p);
      };
      if (move) cancel = tween(update);
      else update(1);
    }

    input.addEventListener('input', () => {
      stop(false);
      render(Number(input.value));
    });
    play.addEventListener('click', () => {
      if (timer) {
        stop();
        return;
      }
      play.textContent = '멈춤';
      play.setAttribute('aria-pressed', 'true');
      shake();
      timer = window.setInterval(shake, 500);
    });
    function motionChanged() {
      play.hidden = motion.matches;
      if (motion.matches) stop();
    }
    motion.addEventListener('change', motionChanged);
    motionChanged();
    render(2, false);
  }

  /* v4: 범용 단계 슬라이더. figure.cfig[data-anim="steps"] + script.states(JSON 상태 배열) */
  function initSteps(root) {
    const data = root.querySelector('script.states');
    const ctl = root.querySelector('.ctl');
    if (!data || !ctl) return;
    let states;
    try {
      states = JSON.parse(data.textContent);
    } catch (err) {
      return;
    }
    if (!Array.isArray(states) || states.length < 2) return;
    const input = ctl.querySelector('input[type=range]');
    if (!input) return;
    const play = ctl.querySelector('button.play');
    const out = ctl.querySelector('output');
    const rows = Array.from(root.querySelectorAll('table.states tbody tr'));
    const last = states.length - 1;
    const start = Math.min(last, Math.max(0, Math.round(Number(root.dataset.start)) || 0));
    let index = start;
    let timer = 0;
    let cancel = () => {};
    input.min = '0';
    input.max = String(last);
    input.step = '1';
    ctl.hidden = false;

    function apply(state, move) {
      const jobs = [];
      const set = state && state.set ? state.set : {};
      Object.keys(set).forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        Object.keys(set[id]).forEach(key => {
          const to = String(set[id][key]);
          if (key === 'text') {
            el.textContent = to;
            return;
          }
          const end = Number(to);
          const from = Number(el.getAttribute(key));
          if (move && to.trim() !== '' && el.hasAttribute(key) && Number.isFinite(end) && Number.isFinite(from)) {
            jobs.push({ el, key, from, end });
          } else {
            el.setAttribute(key, (key === 'width' || key === 'height') && Number(to) < 0 ? '0' : to);
          }
        });
      });
      if (!jobs.length) return () => {};
      // EDIT: width/height는 0 밑으로 내려가지 않게 막음(SVG 음수 폭 오류 방지)
      const nonNeg = key => key === 'width' || key === 'height';
      return tween(p => jobs.forEach(j => {
        const v = j.from + (j.end - j.from) * p;
        j.el.setAttribute(j.key, String(nonNeg(j.key) ? Math.max(0, v) : v));
      }));
    }

    function render(next, move) {
      cancel();
      index = next;
      const state = states[next] || {};
      const label = state.label ? String(state.label) : '';
      input.value = String(next);
      input.setAttribute('aria-valuetext', label);
      if (out) out.textContent = label;
      rows.forEach((row, i) => row.classList.toggle('now', i === next));
      cancel = apply(state, move);
    }

    function stop() {
      if (timer) window.clearInterval(timer);
      timer = 0;
      if (play) {
        play.textContent = '재생';
        play.setAttribute('aria-pressed', 'false');
      }
    }

    input.addEventListener('input', () => {
      stop();
      render(Number(input.value), true);
    });

    if (play) {
      play.addEventListener('click', () => {
        if (timer) {
          stop();
          return;
        }
        play.textContent = '멈춤';
        play.setAttribute('aria-pressed', 'true');
        render(index >= last ? 0 : index + 1, true);
        timer = window.setInterval(() => {
          if (index >= last) {
            stop();
            return;
          }
          render(index + 1, true);
        }, 1200);
      });
      const motionChanged = () => {
        play.hidden = motion.matches;
        if (motion.matches) stop();
      };
      motion.addEventListener('change', motionChanged);
      motionChanged();
    }

    render(start, false);
  }
  const initialisers = { split: initSplit, tost: initTost, ci: initCi, coef: initCoef, loq: initLoq, steps: initSteps };
  document.querySelectorAll('figure.cfig[data-anim]').forEach(root => {
    const init = initialisers[root.dataset.anim];
    if (init) init(root);
  });
})();
