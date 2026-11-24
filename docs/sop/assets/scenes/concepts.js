// 장면: concepts 담당 (공부하기 쪽). SOP.defineScene('이름', t => ...) 로 등록한다 (assets/sop.js 의 window.SOP).
(() => {
  'use strict';
  const { defineScene, h, s, fmt, pill, scale, domain, VCLASS } = window.SOP;
  const W = 720;

  // ---------- 작은 도구 ----------
  const T = (x, y, str, cls, attrs) => s('text', Object.assign({ x, y, class: `sc-t${cls ? ' ' + cls : ''}` }, attrs || {}), str);
  const B = (b, kids, u, cls) => s('g', { 'data-b': b, 'data-u': u, class: cls }, kids);
  // 박자 b 에 (dx, dy) 만큼 옮긴다. 보이고 숨는 것은 바깥 묶음이 정한다
  const MOVE = (b, dx, dy, kids) => s('g', { 'data-b': b, class: 'cx-mv', style: `--dx:${dx}px;--dy:${dy}px` }, kids);
  const svg = (H, label, kids) => s('svg', { viewBox: `0 0 ${W} ${H}`, class: 'scene-svg', role: 'img', 'aria-label': label }, kids);
  const line = (x1, y1, x2, y2, cls) => s('line', { x1, y1, x2, y2, class: cls });
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const mean = a => a.reduce((p, q) => p + q, 0) / a.length;
  const sorted = a => a.slice().sort((p, q) => p - q);
  function median(a) {
    const x = sorted(a), n = x.length;
    return n % 2 ? x[(n - 1) / 2] : (x[n / 2 - 1] + x[n / 2]) / 2;
  }
  const close = (a, b) => Math.abs(a - b) <= 1e-3 * Math.max(Math.abs(a), Math.abs(b), 1e-300);
  function check(ok, what) { if (!ok) throw new Error(`concepts 장면: ${what}`); }

  function svgPill(x, y, v, w) {
    const ww = w || 76;
    return s('g', {}, [
      s('rect', { x, y, width: ww, height: 26, rx: 13, class: `sc-pill ${VCLASS[v] || 'skip'}` }),
      s('text', { x: x + ww / 2, y: y + 18, class: 'sc-pill-t mid' }, v || '없음')]);
  }

  // por_doe_compare.tost 와 같은 규칙 (계단 값의 부동소수 오차는 상대 1e-9 안이면 같은 값)
  function tost(lo, hi, D) {
    const tol = 1e-9 * Math.max(Math.abs(D), Math.abs(lo), Math.abs(hi));
    if (-D - tol <= lo && hi <= D + tol) return '동등';
    if (lo > D + tol || hi < -D - tol) return '차이';
    return '미결';
  }

  // 부호검정 90% 구간: B ~ 이항(n, ½), P(B ≤ k−1) ≤ 0.05 인 가장 큰 k (1-based 아래 끝 순번)
  function binomCdf(k, n) {
    let sum = 0, lc = 0;
    for (let i = 0; i <= k; i++) {
      if (i > 0) lc += Math.log((n - i + 1) / i);
      sum += Math.exp(lc - n * Math.LN2);
    }
    return sum;
  }
  function signRank(n) {
    let k = 0;
    while (binomCdf(k, n) <= 0.05) k++;
    return Math.max(k, 1);
  }
  function signCi(d) {
    const x = sorted(d), n = x.length, k = signRank(n);
    return { lo: x[k - 1], hi: x[n - k], c: median(x), k };
  }

  // t 분포 한쪽 95% 값 (Simpson 적분 + 이분법)
  function lnGamma(z) {
    const g = [676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61503916999185,
      12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
    if (z < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - lnGamma(1 - z);
    z -= 1;
    let a = 0.99999999999980993;
    const t = z + 7.5;
    g.forEach((c, i) => { a += c / (z + i + 1); });
    return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(a);
  }
  function tCdf(x, df) {
    const c = Math.exp(lnGamma((df + 1) / 2) - lnGamma(df / 2)) / Math.sqrt(df * Math.PI);
    const f = u => c * Math.pow(1 + u * u / df, -(df + 1) / 2);
    const m = 400, hh = x / m;
    let sum = f(0) + f(x);
    for (let i = 1; i < m; i++) sum += (i % 2 ? 4 : 2) * f(i * hh);
    return 0.5 + sum * hh / 3;
  }
  function t95(df) {
    let a = 0, b = 20;
    for (let i = 0; i < 60; i++) { const m = (a + b) / 2; if (tCdf(m, df) < 0.95) a = m; else b = m; }
    return (a + b) / 2;
  }
  const runFactor = J => t95(J - 1) * Math.sqrt(1 + 1 / J);

  // 오른쪽 끝 글자들이 겹치지 않게 y 를 벌린다
  function spreadY(items, gap, lo, hi) {
    const xs = items.slice().sort((a, b) => a.y - b.y);
    for (let i = 1; i < xs.length; i++) if (xs[i].y - xs[i - 1].y < gap) xs[i].y = xs[i - 1].y + gap;
    const over = xs.length ? xs[xs.length - 1].y - hi : 0;
    if (over > 0) xs.forEach(it => { it.y -= over; });
    xs.forEach(it => { it.y = Math.max(lo, it.y); });
    return items;
  }

  // ---------- σ_die 와 σ_run ----------
  defineScene('c-sigma-split', t => {
    const Y = t.raw.por, n = Y.length, J = t.J, st = t.step2;
    const sd = st.sigma_die, sr = st.sigma_run;
    const e = Y.map(row => { const m = mean(row); return row.map(v => v - m); });
    const r = Array.from({ length: J }, (_, j) => median(e.map(row => row[j])));
    const all = e.flat().map(Math.abs);
    let lim = Math.max(3.2 * sd, Math.max(...r.map(Math.abs)) + 2.2 * sd);
    if (!(lim > 0)) lim = Math.max(...all) * 1.1 || 1;
    const X0 = 96, X1 = 480, colW = (X1 - X0) / J;
    const y = scale(-lim, lim, 248, 36);
    const cx = j => X0 + colW * (j + 0.5);
    const jit = i => ((i * 0.6180339887) % 1) - 0.5;
    const kids = [];
    kids.push(B(0, [
      T(X0 - 6, 20, 'die 평균에서 떨어진 값', 'muted', { 'text-anchor': 'start' }),
      line(X0, y(0), X1, y(0), 'sc-axis'),
      T(X0 - 8, y(0) + 4, 'die 평균', 'muted cx-end'),
      ...Array.from({ length: J }, (_, j) => T(cx(j), 274, `POR ${j + 1}회`, 'por mid'))]));
    kids.push(B(2, [
      s('rect', { x: X0, y: y(sd), width: X1 - X0, height: y(-sd) - y(sd), rx: 6, class: 'cx-band-die' }),
      T(X1 + 6, y(sd) + 4, `+σ_die`, 'por'), T(X1 + 6, y(-sd) + 4, `−σ_die`, 'por')]));
    const cols = [];
    for (let j = 0; j < J; j++) {
      const dots = e.map((row, i) => {
        const v = row[j], out = Math.abs(v) > lim;
        return s('circle', { cx: cx(j) + jit(i) * colW * 0.62, cy: y(clamp(v, -lim, lim)), r: 3.1, class: `cx-dot${out ? ' cx-clip' : ''}` });
      });
      const bar = B(1, [s('rect', { x: cx(j) - colW * 0.38, y: y(r[j]) - 2.5, width: colW * 0.76, height: 5, rx: 2.5, class: 'cx-runbar' })]);
      cols.push(B(0, [MOVE(2, 0, y(0) - y(r[j]), [...dots, bar])]));
    }
    kids.push(...cols);
    const path = r.map((v, j) => `${j ? 'L' : 'M'}${cx(j)} ${y(v)}`).join(' ');
    kids.push(B(1, [s('path', { d: path, class: 'cx-runline' }),
      T(X1 + 6, y(r[J - 1]) + 4, '회차 중앙값', 'cx-run')], 1));
    // 오른쪽: die 를 모으면 줄어드는 몫과 남는 몫
    const pooled = sd * Math.sqrt(Math.PI / 2) / Math.sqrt(n);
    const rows = [['σ_die · 한 번 잴 때 흔들림', sd, 'cx-fill-die'],
      [`die ${n}개 중앙값에 남는 몫`, pooled, 'cx-fill-pool'],
      ['σ_run · 회차 이동', sr, 'cx-fill-run']];
    const vmax = Math.max(...rows.map(q => q[1])) || 1;
    const RX = 540;
    kids.push(B(3, [T(RX, 44, 'die를 모으면', 'cx-h'),
      ...rows.flatMap(([lab, v, c], i) => {
        const yy = 76 + i * 60, w = Math.max(v > 0 ? 2 : 0, 108 * v / vmax);
        return [T(RX, yy, lab, 'cx-small'),
          s('rect', { x: RX, y: yy + 8, width: w, height: 16, rx: 4, class: c }),
          T(RX + w + 8, yy + 21, v > 0 ? fmt(v) : '0', 'cx-val')];
      })]));
    const beats = [
      `die ${n}개 × POR ${J}회, die마다 자기 평균을 0에 맞춤`,
      sr > 0 ? `회차마다 구름이 통째로 밀린다 → σ_run ${fmt(sr)}` : '회차 밀림이 die 잡음보다 작다 → σ_run 0',
      `밀린 몫을 빼고 남은 흔들림 → σ_die ${fmt(sd)}`,
      'die를 모으면 σ_die 몫은 줄고 σ_run은 남는다'];
    return { nodes: [svg(290, `${t.name} 예제의 POR 반복 값으로 본 두 가지 흔들림`, kids)], beats };
  });

  // ---------- 중앙값과 부호검정 90% 구간 ----------
  defineScene('c-median-ci', t => {
    const d = sorted(t.raw.d.filter(v => v !== null && isFinite(v)));
    const n = d.length, k = t.step4.ci_rank_k;
    const lo = d[k - 1], hi = d[n - k], med = median(d);
    check(close(lo, t.step4.ci_low) && close(hi, t.step4.ci_high), `${t.key}: 구간 끝이 step4 와 다름`);
    check(signRank(n) === k, `${t.key}: 순번 k 가 부호검정 규칙과 다름`);
    const a = d[Math.min(2, n - 1)], b = d[Math.max(n - 3, 0)];
    const [d0, d1] = domain([a, b, lo, hi, med], 0.22);
    const X0 = 130, X1 = 660;
    const x = scale(d0, d1, X0, X1);
    const xc = v => clamp(x(v), X0 - 8, X1 + 8);
    const yr = i => 248 - i * (210 / Math.max(1, n - 1));
    const m0 = mean(d);
    const far = d[n - 1] + 12 * (d1 - d0);
    const m1 = m0 + (far - d[n - 1]) / n;
    const AY = 270;
    const kids = [];
    kids.push(B(0, [line(X0 - 10, AY, X1 + 10, AY, 'sc-axis'),
      T(X1 + 10, AY - 8, 'd →', 'muted cx-end'),
      d0 < 0 && d1 > 0 ? s('g', {}, [line(x(0), 30, x(0), AY, 'cx-zline'), T(x(0), 22, '0', 'mid muted')]) : null]));
    const dots = d.map((v, i) => {
      const cut = i < k - 1 || i > n - k;
      const dot = s('circle', { cx: xc(v), cy: yr(i), r: 3.3, class: `cx-d${x(v) < X0 - 8 || x(v) > X1 + 8 ? ' cx-clip' : ''}` });
      const grey = cut ? B(3, [s('circle', { cx: xc(v), cy: yr(i), r: 3.6, class: 'cx-cut' })]) : null;
      if (i === n - 1) {
        const big = s('circle', { cx: xc(v), cy: yr(i), r: 3.6, class: 'cx-d' });
        return B(0, [MOVE(2, X1 + 40 - xc(v), 0, [big, grey, B(2, [T(xc(v) + 4, yr(i) - 12, '크게 튄 die (그림용)', 'cx-small cx-end')])])]);
      }
      return B(0, [dot, grey]);
    });
    kids.push(...dots);
    kids.push(B(2, [s('path', { d: `M${X1 + 14} ${yr(n - 1)}h16m-5 -5l5 5l-5 5`, class: 'cx-arrow' })]));
    // 중앙값, 평균
    const xm0 = xc(m0), xm1 = xc(m1);
    const medRow = (n - 1) / 2;
    kids.push(B(1, [line(x(med), yr(medRow), x(med), AY, 'cx-guide'),
      s('circle', { cx: x(med), cy: AY, r: 5.5, class: 'sc-c' })]));
    kids.push(B(1, [MOVE(2, xm1 - xm0, 0, [s('path', { d: `M${xm0 - 6} ${AY - 16}h12l-6 9z`, class: 'cx-mean' })])]));
    const near = Math.abs(x(med) - xm0) < 120, near1 = Math.abs(x(med) - xm1) < 120;
    const labX = v => clamp(v, X0 + 30, X1 - 30);
    kids.push(B(1, [T(labX(x(med)), AY + 24, `중앙값 ${fmt(med, true)}`, 'doe mid')], 2));
    kids.push(B(1, [T(labX(xm0), near ? AY + 42 : AY + 24, `평균 ${fmt(m0, true)}`, 'cx-meant mid')], 1));
    kids.push(B(2, [T(labX(xm1), near1 ? AY + 42 : AY + 24, `평균 ${fmt(m1, true)}`, 'cx-meant mid')], 2));
    // 90% 구간
    kids.push(B(3, [
      line(x(lo), yr(k - 1), x(lo), AY, 'cx-guide'), line(x(hi), yr(n - k), x(hi), AY, 'cx-guide'),
      s('rect', { x: x(lo), y: AY - 5, width: Math.max(4, x(hi) - x(lo)), height: 10, rx: 5, class: 'sc-ci' }),
      s('circle', { cx: x(med), cy: AY, r: 4.5, class: 'sc-c' }),
      T(labX((x(lo) + x(hi)) / 2), AY + 24, `90% 구간 ${fmt(lo, true)} ~ ${fmt(hi, true)}`, 'doe mid'),
      s('path', { d: `M${X0 - 40} ${yr(0)}V${yr(k - 2)}`, class: 'cx-brace' }),
      s('path', { d: `M${X0 - 40} ${yr(n - 1)}V${yr(n - k + 1)}`, class: 'cx-brace' }),
      T(X0 - 48, (yr(0) + yr(k - 2)) / 2 + 4, `${k - 1}개 뗌`, 'cx-small cx-end'),
      T(X0 - 48, (yr(n - 1) + yr(n - k + 1)) / 2 + 4, `${k - 1}개 뗌`, 'cx-small cx-end')]));
    const beats = [
      `die별 차이 d ${n}개를 작은 것부터 쌓는다`,
      '가운데 값 = 중앙값(○), 다 더해 나눈 값 = 평균(▼)',
      '큰 d 하나가 튀면 평균만 끌려간다 (그림용)',
      `양 끝 ${k - 1}개씩 떼고 남은 범위 = 90% 구간`];
    return { nodes: [svg(326, `${t.name} 예제의 die별 차이로 본 중앙값과 90% 구간`, kids)], beats };
  });

  // ---------- TOST ----------
  function iconRow(y, which) {
    const cells = [['동등', 0.15, 0.55], ['미결', 0.6, 1.25], ['차이', 1.25, 1.75]];
    return cells.map(([v, a, b], i) => {
      const x0 = 160 + i * 190, w = 150;
      const xs = scale(-2, 2, x0, x0 + w);
      return s('g', { class: v === which ? 'cx-pick' : 'cx-dim' }, [
        s('rect', { x: xs(-1), y, width: xs(1) - xs(-1), height: 30, rx: 6, class: 'sc-band' }),
        line(xs(-1), y - 3, xs(-1), y + 33, 'sc-edge'), line(xs(1), y - 3, xs(1), y + 33, 'sc-edge'),
        line(x0, y + 15, x0 + w, y + 15, 'sc-axis'),
        s('rect', { x: xs(a), y: y + 10, width: xs(b) - xs(a), height: 10, rx: 5, class: 'sc-ci' }),
        svgPill(x0 + w / 2 - 34, y + 40, v, 68)]);
    });
  }
  defineScene('c-tost', t => {
    const iv = t.step4, D = t.step5.delta, v = t.step6.stage1.verdict;
    const [d0, d1] = domain([-D, D, iv.ci_low, iv.ci_high, 0], 0.14);
    const x = scale(d0, d1, 170, 700);
    const zeroIn = iv.ci_low <= 0 && 0 <= iv.ci_high;
    const bar = yy => [s('rect', { x: Math.min(x(iv.ci_low), x(iv.ci_high) - 4), y: yy - 5, width: Math.max(4, x(iv.ci_high) - x(iv.ci_low)), height: 10, rx: 5, class: 'sc-ci' }),
      s('circle', { cx: x(iv.center), cy: yy, r: 4.5, class: 'sc-c' })];
    const labX = clamp((x(iv.ci_low) + x(iv.ci_high)) / 2, 290, 600);
    const kids = [];
    kids.push(B(0, [s('text', { x: 0, y: 34, class: 'sc-h' }, '① 차이가 0인가?'),
      s('text', { x: 0, y: 53, class: 'sc-sub' }, '보통 검정(t-test)의 질문'),
      line(170, 60, 700, 60, 'sc-axis'), ...bar(60),
      T(labX, 40, `90% 구간 ${fmt(iv.ci_low, true)} ~ ${fmt(iv.ci_high, true)}`, 'doe mid')]));
    kids.push(B(1, [line(x(0), 50, x(0), 84, 'cx-zero'), T(x(0), 100, '0', 'mid cx-zerot'),
      s('text', { x: 0, y: 80, class: 'sc-sub cx-ans' }, zeroIn ? '0이 구간 안 → 0이 아니라고 못 함' : '0이 구간 밖 → "0은 아니다"')]));
    const y2 = 170;
    kids.push(B(2, [s('text', { x: 0, y: y2 - 26, class: 'sc-h' }, '② ±Δ 안인가?'),
      s('text', { x: 0, y: y2 - 7, class: 'sc-sub' }, 'TOST의 질문'),
      line(170, y2, 700, y2, 'sc-axis'),
      s('rect', { x: x(-D), y: y2 - 26, width: x(D) - x(-D), height: 52, rx: 8, class: 'sc-band grow' }),
      line(x(-D), y2 - 30, x(-D), y2 + 30, 'sc-edge'), line(x(D), y2 - 30, x(D), y2 + 30, 'sc-edge'),
      T(x(-D), y2 + 46, `−Δ ${fmt(-D)}`, 'eq mid'), T(x(D), y2 + 46, `+Δ ${fmt(D)}`, 'eq mid'),
      s('g', { class: 'late' }, bar(y2))]));
    kids.push(B(3, [svgPill(0, y2 + 4, v)]));
    kids.push(B(3, [T(160, 262, '판정 규칙', 'cx-small cx-end'), ...iconRow(250, v)]));
    const cap = { '동등': '구간이 통째로 띠 안 → 동등', '미결': '구간이 띠 경계에 걸침 → 미결', '차이': '구간이 통째로 띠 밖 → 차이' };
    const beats = [
      'die별 차이 d의 90% 구간 (파란 막대)',
      zeroIn ? '① 0과 견주면: 0이 구간 안 → 차이를 못 찾음' : '① 0과 견주면: 0이 밖 → "차이가 있다"',
      '② "같다"는 구간 전체가 ±Δ 띠 안이어야 한다',
      cap[v] || t.step6.stage1.reason];
    return { nodes: [svg(326, `${t.name} 예제의 90% 구간을 0 과 ±Δ 에 견준 그림`, kids)], beats };
  });

  // ---------- 허용폭 Δ ----------
  defineScene('c-delta', t => {
    const p = t.step5.policy_margin, q = t.step5.run_margin, D = t.step5.delta, J = t.J;
    const f = runFactor(J);
    check(Math.abs(f - t.step5.t_factor) < 2e-3, `t·√(1+1/J) 계산 ${f} 가 ${t.step5.t_factor} 와 다름`);
    const x = scale(-1.3 * D, 1.3 * D, 40, 680);
    const by = 46, bh = 40;
    const kids = [];
    kids.push(B(0, [line(40, by + bh / 2, 680, by + bh / 2, 'sc-axis'),
      line(x(0), by - 4, x(0), by + bh + 4, 'sc-zero'),
      s('rect', { x: x(-p), y: by, width: x(p) - x(-p), height: bh, rx: 6, class: 'cx-pol grow' }),
      T(clamp(x(-p / 2), 110, 300), by - 10, `5% × |POR 중앙값| = ${fmt(p)}`, 'eq mid')]));
    kids.push(B(1, [
      s('rect', { x: x(p), y: by, width: Math.max(0, x(D) - x(p)), height: bh, rx: 4, class: 'cx-runseg' }),
      s('rect', { x: x(-D), y: by, width: Math.max(0, x(-p) - x(-D)), height: bh, rx: 4, class: 'cx-runseg' }),
      T(clamp(x((p + D) / 2), 440, 640), by - 10, q > 0 ? `회차 몫 = ${fmt(q)}` : '회차 몫 0 (σ_run = 0)', 'cx-run mid')]));
    kids.push(B(2, [line(x(-D), by - 4, x(-D), by + bh + 4, 'sc-edge'), line(x(D), by - 4, x(D), by + bh + 4, 'sc-edge'),
      T(x(-D), by + bh + 20, `−Δ`, 'eq mid'), T(x(D), by + bh + 20, `+Δ`, 'eq mid'),
      T(360, by + bh + 44, `Δ = ${fmt(p)} + ${fmt(q)} = ${fmt(D)}`, 'cx-formula mid')]));
    // J 에 따른 배수
    const Js = [2, 3, 4, 5, 6, 7, 8, 9, 10];
    const fs = Js.map(runFactor);
    const jx = scale(2, 10, 170, 660), jy = scale(0, Math.ceil(fs[0]), 318, 178);
    const pts = Js.map((j, i) => `${i ? 'L' : 'M'}${jx(j)} ${jy(fs[i])}`).join(' ');
    const sel = Js.indexOf(J);
    kids.push(B(3, [
      s('text', { x: 0, y: 196, class: 'sc-h' }, '회차 몫의 배수'),
      s('text', { x: 0, y: 216, class: 'sc-sub' }, 't(0.95, J−1)·√(1+1/J)'),
      s('text', { x: 0, y: 236, class: 'sc-sub' }, 'POR를 J회 잴 때'),
      line(170, 318, 660, 318, 'sc-axis'),
      line(170, jy(1.645), 660, jy(1.645), 'cx-asym'),
      T(660, jy(1.645) + 15, 'J가 아주 크면 1.645', 'muted cx-end'),
      s('path', { d: pts, class: 'cx-fline' }),
      ...Js.map((j, i) => s('circle', { cx: jx(j), cy: jy(fs[i]), r: j === J ? 6.5 : 3.5, class: j === J ? 'cx-fsel' : 'cx-fpt' })),
      ...Js.map(j => T(jx(j), 336, `${j}`, 'mid muted')),
      T(150, 336, 'J', 'cx-end muted'),
      T(jx(2) + 10, jy(fs[0]) + 4, fmt(fs[0], false, ''), 'cx-small'),
      sel >= 0 ? T(jx(J) + 12, jy(fs[sel]) - 8, `J=${J}: ${fmt(fs[sel], false, '')}`, 'cx-fsel-t') : null,
      T(jx(10), jy(fs[8]) - 10, fmt(fs[8], false, ''), 'cx-small mid')]));
    const beats = [
      `정책 몫: POR 중앙값의 5% = ${fmt(p)}`,
      q > 0 ? `회차 몫: ${fmt(f, false, '')} × σ_run = ${fmt(q)}` : '회차 몫: σ_run이 0이라 0',
      `두 몫을 더한 ±Δ ${fmt(D)} 안이면 같다고 본다`,
      `J가 늘면 배수가 준다 (J=${J}: ${fmt(f, false, '')})`];
    return { nodes: [svg(344, `${t.name} 예제의 허용폭 Δ 구성`, kids)], beats };
  });

  // ---------- LoQ ----------
  function loqCap(st2) {
    if (!st2) return null;
    const why = st2.reason || '';
    if (why.includes('LoQ 미만')) return "DOE 구간도 LoQ 아래 → 둘 다 '<LoQ' → 동등";
    if (why.includes('LoQ에 걸침')) return "DOE 구간이 LoQ 선에 걸침 → '<LoQ'와 같다고 봄";
    if (why.includes('±Δ 안')) return '이동이 ±Δ 안 → 동등';
    if (st2.verdict === '차이') return 'DOE 구간이 통째로 LoQ 위 → 차이';
    return 'DOE 구간은 LoQ 위, 이동이 ±Δ에 걸침 → 미결';
  }
  defineScene('c-loq', t => {
    const Q = t.step3.LoQ, sg = Q / 10, m = t.step3.por_median, iv = t.step4, st2 = t.step6.stage2;
    const a = m + iv.ci_low, b = m + iv.ci_high;
    const far = Math.abs(m) > 4 * Q;
    const lo0 = far ? 0 : Math.min(0, a, m);
    const hi0 = far ? 2.4 * Q : Math.max(2.4 * Q, b, m) ;
    const x = scale(lo0 - (hi0 - lo0) * 0.04, hi0 + (hi0 - lo0) * 0.04, 70, 640);
    const lanes = [0.25, 0.5, 1, 2];
    const kids = [];
    kids.push(B(0, [T(70, 16, '같은 흔들림 ±σ 를 여러 크기의 값에 붙이면', 'muted', { 'text-anchor': 'start' }),
      ...lanes.map((f, i) => {
        const v = f * Q, yy = 34 + i * 22;
        return s('g', { class: f === 1 ? 'cx-lane cx-lane-q' : 'cx-lane' }, [
          line(x(v - sg), yy, x(v + sg), yy, 'cx-whisk'),
          line(x(v - sg), yy - 5, x(v - sg), yy + 5, 'cx-whisk'), line(x(v + sg), yy - 5, x(v + sg), yy + 5, 'cx-whisk'),
          s('circle', { cx: x(v), cy: yy, r: 4, class: 'sc-por' }),
          T(x(v + sg) + 8, yy + 4, `σ ÷ 값 = ${fmt(100 * sg / v, false, '')}%`, 'cx-small')]);
      })]));
    const AY = 196;
    const x0 = x(Math.max(lo0, 0));
    kids.push(B(1, [
      s('rect', { x: x0, y: 122, width: x(Q) - x0, height: 108, rx: 6, class: 'sc-below' }),
      T(x0 + 8, 138, "'<LoQ' 로 보고하는 곳", 'muted'),
      line(x(Q), 22, x(Q), 236, 'sc-loq'),
      T(x(Q) + 6, 138, `LoQ = 10σ = ${fmt(Q)}`, 'por')]));
    kids.push(B(0, [line(70, AY, 640, AY, 'sc-axis')]));
    if (x(0) > 70) kids.push(B(0, [line(x(0), AY - 5, x(0), AY + 5, 'sc-zero'), T(x(0), AY + 18, '0', 'muted mid')]));
    if (far) {
      kids.push(B(2, [s('circle', { cx: 650, cy: AY, r: 6, class: 'sc-por' }), s('path', { d: `M660 ${AY}h14m-5 -5l5 5l-5 5`, class: 'cx-arrow' }),
        T(700, AY + 30, `POR 중앙값 ${fmt(m)} (LoQ의 ${fmt(Math.abs(m) / Q, false, '')}배)`, 'por cx-end')]));
    } else {
      kids.push(B(2, [s('circle', { cx: x(m), cy: AY, r: 6, class: 'sc-por' }),
        Math.abs(m) < Q ? T(Math.max(x(m) + 10, 190), AY + 30, `POR 중앙값 ${fmt(m)}`, 'por cx-end')
          : T(Math.min(x(m) - 10, 520), AY + 30, `POR 중앙값 ${fmt(m)}`, 'por')]));
      kids.push(B(3, [
        s('rect', { x: Math.min(x(a), x(b) - 4), y: 160, width: Math.max(4, x(b) - x(a)), height: 10, rx: 5, class: 'sc-ci' }),
        s('path', { d: `M${x(m + iv.center)} ${156}l8 9l-8 9l-8 -9z`, class: 'sc-doe' }),
        T(clamp((x(a) + x(b)) / 2, 170, 540), 258, `DOE 구간 ${fmt(a)} ~ ${fmt(b)}`, 'doe mid'),
        line(x(a), 172, x(a), 244, 'cx-guide'), line(x(b), 172, x(b), 244, 'cx-guide')]));
    }
    kids.push(B(3, [st2 ? svgPill(640, 244, st2.verdict) : T(710, 262, '2단계 없음 (1단계 TOST만)', 'muted cx-end')]));
    const below = Math.abs(m) < Q;
    const beats = [
      '값이 작을수록 같은 ±σ가 값에 비해 커진다',
      `σ가 값의 10%인 곳 = LoQ = 10σ = ${fmt(Q)}`,
      below ? "POR 중앙값이 LoQ 아래 → 숫자 대신 '<LoQ'" : 'POR 중앙값이 LoQ 위 → 숫자로 비교 (정량)',
      st2 ? loqCap(st2) : 'LoQ 위 ITEM은 2단계 없이 1단계 TOST로 판정'];
    return { nodes: [svg(276, `${t.name} 예제의 LoQ 와 POR 중앙값`, kids)], beats };
  });

  // ---------- ITEM 유형과 판정 길 ----------
  const AXES = [['cls_valid', '판정할 수 있나'], ['cls_sign', '부호'], ['cls_level', '높이 (LoQ 대비)'], ['cls_resolution', '값이 계단인가'],
    ['cls_shape', '분포 모양'], ['cls_noise', '잡음 모양'], ['cls_scale', '척도'], ['cls_run', 'POR 회차']];
  // classify.py ROUTES 와 같은 순서와 조건
  const ROUTES = [
    ['제외', '판정할 수 없는 ITEM인가?', ['cls_valid'], c => c.cls_valid !== '정상'],
    ['한계 비교', '한계(Open·최댓값)에 걸린 값이 있나?', ['cls_shape'], c => c.cls_shape.split(';').includes('한계에 걸림')],
    ['절대 허용폭', '0 중심이거나, 계단이고 정량·바닥 근처인가?', ['cls_level', 'cls_resolution'],
      c => c.cls_level === '0 중심' || (c.cls_resolution === '계단' && ['정량', '바닥 근처'].includes(c.cls_level))],
    ['LoQ 판정', 'LoQ 아래(바닥 아래)인가?', ['cls_level'], c => c.cls_level === '바닥 아래'],
    ['log TOST', 'log 척도이고 부호가 하나인가?', ['cls_scale', 'cls_sign'], c => c.cls_scale === 'log' && ['양수만', '음수만'].includes(c.cls_sign)],
    ['선형 TOST', '나머지 모두', [], () => true]];
  // journeys 의 step3.cls 는 열 이름에서 'cls_' 를 뗀 키
  const clsOf = t => Object.fromEntries(Object.entries(t.step3.cls).map(([k, v]) => [`cls_${k}`, v]));
  defineScene('c-routes', t => {
    const c = clsOf(t), st = t.step6;
    const hit = ROUTES.findIndex(r => r[3](c));
    check(ROUTES[hit][0] === t.step3.route, `${t.key}: 판정 길 ${ROUTES[hit][0]} ≠ ${t.step3.route}`);
    const used = new Set(ROUTES[hit][2]);
    const kids = [];
    const cardY = 20, rh = 31;
    kids.push(B(0, [s('rect', { x: 0, y: cardY - 6, width: 248, height: AXES.length * rh + 34, rx: 12, class: 'cx-card' }),
      T(14, cardY + 14, 'POR 값만 본 ITEM 유형', 'cx-h', { 'text-anchor': 'start' }),
      ...AXES.map(([col, name], i) => {
        const yy = cardY + 44 + i * rh;
        return s('g', {}, [T(14, yy, name, 'cx-small'), T(234, yy, c[col] || '–', 'cx-axv cx-end'),
          used.has(col) ? B(2, [s('rect', { x: 6, y: yy - 17, width: 236, height: 25, rx: 6, class: 'cx-axhit' })]) : null]);
      })]));
    const RX = 300, RW = 420, gy = 14, rg = 44;
    ROUTES.forEach(([name, q], i) => {
      const yy = gy + i * rg;
      const state = i < hit ? 'no' : i === hit ? 'yes' : 'rest';
      kids.push(B(1, [s('rect', { x: RX, y: yy, width: RW, height: 36, rx: 9, class: `cx-rung cx-rung-${state}` }),
        T(RX + 14, yy + 23, q, state === 'rest' ? 'cx-small muted' : 'cx-small'),
        T(RX + RW - 12, yy + 23, name, `cx-route cx-end${state === 'rest' ? ' muted' : ''}`),
        state === 'no' ? T(RX - 8, yy + 23, '아니오', 'cx-no cx-end') : null]));
      if (state === 'yes') {
        kids.push(B(2, [s('rect', { x: RX - 3, y: yy - 3, width: RW + 6, height: 42, rx: 11, class: 'cx-rung-ring' }),
          T(RX - 8, yy + 23, '예', 'cx-yes cx-end')]));
      }
    });
    const s1 = st.stage1.verdict, s2 = st.stage2 ? st.stage2.verdict : null;
    const settled = s1 === '동등' || s2 === '동등';
    const s3 = st.stage3 ? (st.stage3.verdict || '앞 판정 유지') : '가지 않음';
    const chips = [['1단계', s1], ['2단계', st.stage2 ? s2 : '건너뜀'], ['3단계 · ' + t.step3.route, s3], ['최종', st.final.verdict]];
    const cy = 314;
    kids.push(B(3, chips.flatMap(([lab, v], i) => {
      const xx = 8 + i * 178;
      const w = 160;
      return [s('rect', { x: xx, y: cy, width: w, height: 40, rx: 10, class: `cx-chip cx-chip-${VCLASS[v] || 'skip'}` }),
        T(xx + w / 2, cy + 16, lab, 'cx-small mid'), T(xx + w / 2, cy + 33, v, `cx-chipv mid cx-v-${VCLASS[v] || 'skip'}`),
        i < 3 ? T(xx + w + 9, cy + 25, '→', 'muted mid') : null];
    })));
    const beats = [
      'POR 값만 보고 ITEM 유형 8칸을 적는다',
      '판정 길 질문 여섯 개를 위에서부터 묻는다',
      `처음 '예'인 곳이 판정 길: ${t.step3.route}`,
      settled ? '1·2단계가 동등이라 이 길로 다시 보지 않는다' : `동등이 아니라 '${t.step3.route}'로 다시 봄 → ${st.final.verdict}`];
    return { nodes: [svg(360, `${t.name} 예제의 ITEM 유형과 판정 길`, kids)], beats };
  });

  // ---------- log 척도 (그림용 예) ----------
  defineScene('c-log-scale', t => {
    const N = 8, k = 1.35, up = 1.05;
    const v = Array.from({ length: N }, (_, i) => Math.pow(10, i * 0.3));
    const X0 = 70, step = 40;
    const xi = i => X0 + 24 + i * step;
    const ylin = scale(0, 180, 262, 34);
    const ylog = scale(-0.15, 2.35, 262, 34);
    const lg = Math.log10;
    function panel(yf, ticks, title) {
      return [T(X0, 22, title, 'cx-h', { 'text-anchor': 'start' }),
        line(X0, 262, X0 + 24 + (N - 1) * step + 24, 262, 'sc-axis'),
        ...ticks.map(([val, lab]) => s('g', {}, [line(X0 - 4, yf(val), X0, yf(val), 'sc-axis'), T(X0 - 8, yf(val) + 4, lab, 'muted cx-end')])),
        ...v.map((val, i) => {
          const [a, b] = [val / k, val * k].map(z => yf === ylog ? ylog(lg(z)) : ylin(z));
          const c = yf === ylog ? ylog(lg(val)) : ylin(val);
          return s('g', {}, [line(xi(i), a, xi(i), b, 'cx-wob'), line(xi(i) - 5, a, xi(i) + 5, a, 'cx-wob'), line(xi(i) - 5, b, xi(i) + 5, b, 'cx-wob'),
            s('circle', { cx: xi(i), cy: c, r: 4, class: 'sc-por' })]);
        })];
    }
    const kids = [];
    kids.push(B(0, panel(ylin, [[0, '0'], [50, '50'], [100, '100'], [150, '150']], '선형 눈금'), 0));
    kids.push(B(1, panel(ylog, [[0, '1'], [1, '10'], [2, '100']], 'log 눈금')));
    kids.push(B(2, v.map((val, i) => s('path', { d: `M${xi(i) + 14} ${ylog(lg(val * up)) - 6}l6 6l-6 6l-6 -6z`, class: 'sc-doe' }))));
    kids.push(B(0, [T(X0 + 24 + (N - 1) * step + 24, 282, '그림용 예 · die 8개, 흔들림 ∝ 값', 'muted cx-end')]));
    const RX = 450, bw = 22, bx = i => RX + 8 + i * 30;
    const dmax = (up - 1) * v[N - 1];
    kids.push(B(2, [
      T(RX, 44, '차이 DOE − POR', 'cx-h', { 'text-anchor': 'start' }),
      line(RX, 130, RX + 250, 130, 'sc-axis'),
      ...v.map((val, i) => s('rect', { x: bx(i), y: 130 - 74 * (up - 1) * val / dmax, width: bw, height: 74 * (up - 1) * val / dmax, rx: 3, class: 'cx-fill-diff' })),
      T(RX + 250, 150, 'die마다 다르다', 'cx-small cx-end'),
      T(RX, 186, '배율 log(DOE ÷ POR)', 'cx-h', { 'text-anchor': 'start' }),
      line(RX, 262, RX + 250, 262, 'sc-axis'),
      ...v.map((_, i) => s('rect', { x: bx(i), y: 262 - 30, width: bw, height: 30, rx: 3, class: 'cx-fill-ratio' })),
      T(RX + 250, 282, '모든 die에서 같다', 'cx-small cx-end')]));
    const c = clsOf(t);
    kids.push(B(3, [s('rect', { x: 0, y: 298, width: W, height: 34, rx: 10, class: 'cx-card' }),
      T(14, 320, `이 예제 (${t.name}): 잡음 모양 '${c.cls_noise}' · 척도 '${c.cls_scale}' → 판정 길 '${t.step3.route}'`, 'cx-small', { 'text-anchor': 'start' })]));
    const beats = [
      '선형 눈금: 큰 die일수록 흔들림 막대가 길다',
      'log 눈금: 모든 die의 막대 길이가 같다',
      '그래서 차이 대신 배율(DOE ÷ POR)로 본다',
      c.cls_scale === 'log' ? '이 예제는 척도 log → log TOST로 판정' : `이 예제는 척도 '${c.cls_scale}' → log 길이 아니다`];
    return { nodes: [svg(336, '잡음이 값에 비례할 때 선형 눈금과 log 눈금 비교 (그림용 예)', kids)], beats };
  });

  // ---------- 0 근처와 절대 허용폭 ----------
  defineScene('c-abs-tol', t => {
    const iv = t.step4, p5 = t.step5, m = Math.abs(t.step3.por_median);
    const r = m > 0 ? p5.policy_margin / m : 0.05, q = p5.run_margin;
    const lo = iv.ci_low, hi = iv.ci_high;
    const farEnd = Math.max(Math.abs(lo), Math.abs(hi));
    const nearEnd = lo > 0 || hi < 0 ? Math.min(Math.abs(lo), Math.abs(hi)) : 0;
    const hasAbs = p5.abs_delta !== null && p5.abs_delta !== undefined;
    const fixed = hasAbs ? p5.abs_delta : t.step3.LoQ;
    const cross = r > 0 ? (farEnd - q) / r : 0;
    const xmax = Math.max(m * 1.3, cross * 1.4, m > 0 ? 0 : 1);
    const Dm = mm => r * mm + q;
    const ymax = Math.max(farEnd, fixed, Dm(xmax)) * 1.12;
    const X0 = 90, X1 = 600, Y0 = 250, Y1 = 34;
    const x = scale(0, xmax, X0, X1), y = scale(0, ymax, Y0, Y1);
    const kids = [];
    kids.push(B(0, [line(X0, Y0, X1, Y0, 'sc-axis'), line(X0, Y0, X0, Y1 - 6, 'sc-axis'),
      T(X0 - 8, Y0 + 4, '0', 'muted cx-end'), T(X0, Y0 + 20, '0', 'muted mid'),
      T(X1, Y0 + 20, 'POR 중앙값 →', 'muted cx-end'), T(X0 - 8, Y1 - 4, '폭', 'muted cx-end'),
      s('rect', { x: X0, y: y(farEnd), width: X1 - X0, height: Math.max(3, y(nearEnd) - y(farEnd)), class: 'cx-ivband' })]));
    const vcol = mm => { const d = Dm(mm); return d >= farEnd ? 'eq' : d < nearEnd ? 'diff' : 'hold'; };
    const segs = [];
    const NS = 160;
    for (let i = 0; i < NS; i++) {
      const a = xmax * i / NS, b = xmax * (i + 1) / NS;
      segs.push(line(x(a), y(Dm(a)), x(b), y(Dm(b)), `cx-dline cx-${vcol((a + b) / 2)}`));
    }
    const labels = spreadY([
      { key: 'band', y: (y(farEnd) + y(Math.max(nearEnd, 0))) / 2 + 4 },
      { key: 'delta', y: y(Dm(xmax)) + 4 },
      { key: 'fixed', y: y(fixed) + 4 }], 18, Y1, Y0 - 4);
    const ly = k => labels.find(l => l.key === k).y;
    kids.push(B(0, [T(X1 + 8, ly('band'), '이동 90% 구간', 'doe')]));
    kids.push(B(1, [...segs, T(X1 + 8, ly('delta'), 'Δ (비례 폭)', 'cx-dlab')]));
    const v1 = tost(lo, hi, Dm(m));
    const mx = x(m);
    kids.push(B(2, [line(mx, Y0, mx, Y1, 'cx-guide'), s('circle', { cx: mx, cy: y(Dm(m)), r: 5.5, class: `cx-dot-${VCLASS[v1]}` }),
      T(clamp(mx, X0 + 70, X1 - 70), Y0 + 38, `이 예제 POR 중앙값 ${fmt(t.step3.por_median)}`, 'por mid'),
      svgPill(clamp(mx - 84, X0 + 4, X1 - 160), clamp(Math.min(y(Dm(m)), y(farEnd)) - 36, Y1, Y0 - 30), v1)]));
    const v2 = tost(lo, hi, fixed);
    kids.push(B(3, [line(X0, y(fixed), X1, y(fixed), 'cx-fixed'),
      T(X1 + 8, ly('fixed'), hasAbs ? '절대 허용폭' : '고정 폭 (LoQ)', 'cx-fixedt'),
      s('circle', { cx: mx, cy: y(fixed), r: 5.5, class: `cx-dot-${VCLASS[v2]}` }),
      svgPill(clamp(mx + 10, X0 + 4, X1 - 80), clamp(y(fixed) - 36, Y1, Y0 - 30), v2)]));
    const route = t.step3.route;
    const beats = [
      '이동 구간(파란 띠)은 그대로 두고',
      'Δ는 중앙값이 0으로 가면 좁아진다 (색 = 판정)',
      `이 예제 중앙값에서 Δ로 보면 ${v1}`,
      route === '절대 허용폭' ? `고정 폭 ${fmt(fixed)}로 보면 ${v2} (판정 길 ${route})`
        : `고정 폭으로 보면 ${v2} · 이 예제 길은 '${route}'`];
    return { nodes: [svg(300, `${t.name} 예제로 본 비례 허용폭과 고정 허용폭`, kids)], beats };
  });

  // ---------- 검정력과 표본 크기 ----------
  function mulberry32(a) {
    return () => {
      a = (a + 0x6D2B79F5) | 0;
      let z = Math.imul(a ^ (a >>> 15), 1 | a);
      z = (z + Math.imul(z ^ (z >>> 7), 61 | z)) ^ z;
      return ((z ^ (z >>> 14)) >>> 0) / 4294967296;
    };
  }
  function normals(seed, N) {
    const rnd = mulberry32(seed), out = [];
    while (out.length < N) out.push(Math.sqrt(-2 * Math.log(rnd() || 1e-12)) * Math.cos(2 * Math.PI * rnd()));
    return out;
  }
  // 그림용 모형: 참 이동 0.35, die별 흔들림 1, Δ 1 (die 10 → 미결, 80 → 동등 이 되게 고른 값)
  const POWER = (() => {
    const z = normals(1, 80).map(u => 0.35 + u);
    return [10, 20, 40, 80].map(n => Object.assign({ n }, signCi(z.slice(0, n))));
  })();
  defineScene('c-power', t => {
    const D = 1;
    const [d0, d1] = domain([-D, D, ...POWER.flatMap(r => [r.lo, r.hi])], 0.08);
    const x = scale(d0, d1, 170, 700);
    const kids = [];
    kids.push(B(0, [s('rect', { x: x(-D), y: 8, width: x(D) - x(-D), height: 4 * 52 + 4, rx: 8, class: 'sc-band' }),
      line(x(-D), 4, x(-D), 4 * 52 + 16, 'sc-edge'), line(x(D), 4, x(D), 4 * 52 + 16, 'sc-edge'),
      T(x(-D), 4 * 52 + 32, '−Δ', 'eq mid'), T(x(D), 4 * 52 + 32, '+Δ', 'eq mid'),
      T(x(0), 4 * 52 + 32, '0', 'muted mid'), T(700, 4 * 52 + 32, '그림용 예', 'muted cx-end')]));
    POWER.forEach((r, i) => {
      const yy = 34 + i * 52, b = i === 0 ? 0 : i < 3 ? 1 : 2;
      const v = tost(r.lo, r.hi, D);
      kids.push(B(b, [T(0, yy + 5, `die ${r.n}개`, 'cx-rowh'),
        line(170, yy, 700, yy, 'sc-axis'),
        s('rect', { x: x(r.lo), y: yy - 6, width: x(r.hi) - x(r.lo), height: 12, rx: 6, class: 'sc-ci' }),
        s('circle', { cx: x(r.c), cy: yy, r: 4.5, class: 'sc-c' }),
        B(2, [svgPill(78, yy - 13, v, 68)])]));
    });
    const iv = t.step4, Dx = t.step5.delta;
    const ratio = (iv.ci_high - iv.ci_low) / 2 / Dx;
    const gmax = Math.max(1.2, Math.min(ratio * 1.1, 3));
    const g = scale(0, gmax, 170, 700);
    const gy = 290;
    const zone = (a, b, cls, lab) => {
      const xa = g(Math.min(a, gmax)), xb = g(Math.min(b, gmax));
      return xb > xa ? s('g', {}, [s('rect', { x: xa, y: gy - 12, width: xb - xa, height: 24, class: cls }),
        T((xa + xb) / 2, gy + 30, lab, 'cx-small mid')]) : null;
    };
    const name = ratio <= 0.5 ? '안정' : ratio <= 0.8 ? '주의' : '불안정';
    kids.push(B(3, [s('text', { x: 0, y: gy - 2, class: 'sc-h' }, '이 예제'),
      s('text', { x: 0, y: gy + 17, class: 'sc-sub' }, `die ${t.n_die}개 · 반폭 ÷ Δ`),
      zone(0, 0.5, 'cx-z-eq', '안정'), zone(0.5, 0.8, 'cx-z-hold', '주의'), zone(0.8, gmax, 'cx-z-diff', '불안정'),
      line(g(1), gy - 18, g(1), gy + 16, 'cx-guide'), T(g(1), gy - 22, '1', 'muted mid'),
      s('rect', { x: g(0), y: gy - 5, width: Math.max(3, g(Math.min(ratio, gmax)) - g(0)), height: 10, rx: 5, class: 'sc-ci' }),
      T(clamp(g(Math.min(ratio, gmax)) + 8, 180, 650), gy - 16, `${ratio.toFixed(2)}${ratio > gmax ? ' →' : ''}`, 'doe')]));
    const beats = [
      'die 10개: 구간이 넓어 ±Δ 띠를 넘는다 (그림용 예)',
      'die를 늘리면 구간이 좁아진다',
      '충분히 좁아지면 띠 안에 들어와 동등',
      `이 예제: 구간 반폭이 Δ의 ${ratio.toFixed(2)}배 → ${name}`];
    return { nodes: [svg(330, 'die 수에 따라 좁아지는 90% 구간 (그림용 예)과 이 예제의 반폭 ÷ Δ', kids)], beats };
  });
})();
