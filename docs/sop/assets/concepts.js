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
      { lo: -1.0, hi: 2.0, cls: 'ok', label: '90% CI [−1.0, 2.0]', out: '<span class="pill ok">동등</span> 구간 전체가 ±Δ 안' },
      { lo: 5.5, hi: 8.0, cls: 'hold', label: '90% CI [5.5, 8.0]', out: '<span class="pill hold">미결</span> 구간이 +Δ 6.686에 걸침' },
      { lo: 7.5, hi: 9.5, cls: 'bad', label: '90% CI [7.5, 9.5]', out: '<span class="pill bad">차이</span> 구간 전체가 +Δ 6.686 밖' }
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
    const states = [
      { n: 10, rankLo: 2, rankHi: 9, lo: -0.736, hi: 1.336, loText: '−0.736', hiText: '1.336', text: 'die 10개 · 크기순 2번째 ~ 9번째 · 구간 [−0.736, 1.336] · 폭 2.072 · 포함 확률 97.85% · 0을 포함' },
      { n: 20, rankLo: 6, rankHi: 15, lo: -0.298, hi: 0.898, loText: '−0.298', hiText: '0.898', text: 'die 20개 · 크기순 6번째 ~ 15번째 · 구간 [−0.298, 0.898] · 폭 1.196 · 포함 확률 95.86% · 0을 포함' },
      { n: 30, rankLo: 11, rankHi: 20, lo: -0.085, hi: 0.685, loText: '−0.085', hiText: '0.685', text: 'die 30개 · 크기순 11번째 ~ 20번째 · 구간 [−0.085, 0.685] · 폭 0.770 · 포함 확률 90.13% · 0을 포함' },
      { n: 60, rankLo: 24, rankHi: 37, lo: 0.025, hi: 0.575, loText: '0.025', hiText: '0.575', text: 'die 60개 · 크기순 24번째 ~ 37번째 · 구간 [0.025, 0.575] · 폭 0.550 · 포함 확률 90.75% · 0을 포함하지 않음' }
    ];
    let cancel = () => {};
    controlsFor(root);

    function drawDots(state) {
      dots.replaceChildren();
      for (let i = 1; i <= state.n; i += 1) {
        const value = Math.round((0.3 + phiInv((i - 0.5) / state.n)) * 1000) / 1000;
        const dot = document.createElementNS(dots.namespaceURI, 'circle');
        dot.setAttribute('cx', 300 + value * 100);
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
      const x0 = 300 + state.lo * 100;
      const x1 = 300 + state.hi * 100;
      input.value = String(index);
      input.setAttribute('aria-valuetext', state.text);
      out.textContent = state.text;
      drawDots(state);
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
    render(3, false);
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
    const states = [
      { t: 5, rsd: '40%', text: '실제 값 5 · σ 2.0 · 상대 흔들림 40%', pill: '<span class="pill hold">LoD 6.58 미만</span>', aria: 'LoD 6.58 미만' },
      { t: 10, rsd: '20%', text: '실제 값 10 · σ 2.0 · 상대 흔들림 20%', pill: '<span class="pill hold">LoQ 20.0 미만</span>', aria: 'LoQ 20.0 미만' },
      { t: 20, rsd: '10%', text: '실제 값 20 · σ 2.0 · 상대 흔들림 10%', pill: '<span class="pill ok">LoQ, 정량 시작</span>', aria: 'LoQ, 정량 시작' },
      { t: 50, rsd: '4%', text: '실제 값 50 · σ 2.0 · 상대 흔들림 4%', pill: '<span class="pill ok">정량</span>', aria: '정량' },
      { t: 100, rsd: '2%', text: '실제 값 100 · σ 2.0 · 상대 흔들림 2%', pill: '<span class="pill ok">정량</span>', aria: '정량' }
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
      moveDot(320 + z * 520 / state.t);
    }

    function render(index, move = true) {
      cancel();
      state = states[index];
      const x = 320 - 520 / state.t;
      const width = 1040 / state.t;
      input.value = String(index);
      input.setAttribute('aria-valuetext', `${state.text} · ${state.aria}`);
      out.innerHTML = `${state.text} ${state.pill}`;
      band.setAttribute('class', state.t < 20 ? 'bandhold' : 'band');
      a0.textContent = '0';
      a1.textContent = String(state.t);
      a2.textContent = String(state.t * 2);
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

  const initialisers = { split: initSplit, tost: initTost, ci: initCi, coef: initCoef, loq: initLoq };
  document.querySelectorAll('figure.cfig[data-anim]').forEach(root => {
    const init = initialisers[root.dataset.anim];
    if (init) init(root);
  });
})();
