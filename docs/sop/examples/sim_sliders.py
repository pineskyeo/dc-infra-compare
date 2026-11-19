"""슬라이더용 확률 표. 예시 ITEM과 같은 모형(참값 100, die 퍼짐 SD 3, 반복 σ_die 0.98965 · 회차 이동 σ_run 0.50389 (예시 ITEM의 도구 추정값), 회차 이동 σ_run, 비교 조건 이동 b)으로
데이터를 만들어 por_doe_compare.judge()를 그대로 돌림. 각 칸 2000회, seed 고정. → sliders.json"""
import sys, json; sys.path.insert(0, '/workspace/dc-infra-compare-review')
import numpy as np
from por_doe_compare import judge
REP = 2000
SD, SR = 0.98965, 0.50389   # 예시 ITEM의 도구 추정값 (items.csv sigma_die, sigma_run)
def run(b=0.8, s_run=SR, J=3, n=60, s_die=SD, seed=1):
    rng = np.random.default_rng(seed); c = {'동등': 0, '미결': 0, '차이': 0}; D = []; W = []
    for _ in range(REP):
        true = 100 + rng.normal(0, 3, n); off = rng.normal(0, s_run, J + 1)
        Y = np.stack([true + off[j] + rng.normal(0, s_die, n) for j in range(J)], 1); z = true + off[J] + b + rng.normal(0, s_die, n)
        r, _ = judge(Y, z, 0.05); c[r['verdict']] += 1; D.append(r['delta']); W.append(r['ci_high'] - r['ci_low'])
    return dict(p_eq=round(c['동등']/REP*100, 1), p_hold=round(c['미결']/REP*100, 1), p_diff=round(c['차이']/REP*100, 1), delta_med=round(float(np.median(D)), 3), ci_width_med=round(float(np.median(W)), 3))
o = {'model': '참값 100, die 퍼짐 SD 3, σ_die 0.98965, 각 회차 이동 N(0, σ_run 0.50389), 비교 조건 이동 b, judge() 2000회씩', 'base': dict(b=0.8, s_run=SR, s_die=SD, J=3, n=60)}
o['b'] = {str(b): run(b=b) for b in (0, 2, 4, 5, 6, 7, 8, 10)}
o['s_run'] = {str(s): run(s_run=s) for s in (0.25, SR, 1.0, 1.5, 2.0, 3.0)}
o['J'] = {str(j): run(J=j) for j in (2, 3, 4, 5, 6, 8, 10)}
o['n'] = {str(m): run(n=m, b=5.5) for m in (10, 20, 30, 45, 60, 90, 120)}
o['s_run_b55'] = {str(x): run(s_run=x, b=5.5) for x in (0.25, SR, 1.0, 1.5, 2.0, 3.0)}
o['J_b55'] = {str(j): run(J=j, b=5.5) for j in (2, 3, 4, 5, 6, 8, 10)}
o['s_die_b0'] = {str(x): run(s_die=x, b=0.0) for x in (SD, 2.0, 4.0, 6.0, 8.0)}
o['s_die_b0_n'] = {str(m): run(s_die=6.0, b=0.0, n=m) for m in (30, 60, 90, 120)}
o['n_note'] = 'n, s_run_b55, J_b55 표는 b = 5.5 (Δ 가까이). s_die_b0 = 실제로 같을 때(b 0) σ_die를 키움. s_die_b0_n = σ_die 6, b 0에서 die 수'
json.dump(o, open('sliders.json', 'w'), ensure_ascii=False, indent=1); print(json.dumps(o, ensure_ascii=False))
