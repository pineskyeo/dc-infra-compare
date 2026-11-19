"""예시 ITEM 숫자를 단계별로 직접 계산하고 por_doe_compare.py 출력(tool_out/items.csv)과 맞춰 본다. → example.json"""
import json, math, csv
import numpy as np, pandas as pd
from scipy import stats
W = pd.read_csv('data/example_wide.csv'); Y = W[['ref1','ref2','ref3']].to_numpy(); z = W['cand'].to_numpy()
n, J = Y.shape; T = pd.read_csv('tool_out/items.csv').iloc[0]
o = {'source': 'data/example_wide.csv (make_example.py seed 20263255), tool: por_doe_compare.py @5e6ddae', 'n': n, 'J': J}
R = Y.mean(1); d = z - R
o['dies_head'] = [dict(die=int(W.die[i]), ref1=float(Y[i,0]), ref2=float(Y[i,1]), ref3=float(Y[i,2]), ref_mean=round(float(R[i]),4), cand=float(z[i]), d=round(float(d[i]),4)) for i in range(6)]
# sigma_die
dd = [Y[:,k+1]-Y[:,k] for k in range(J-1)]; meds = [float(np.median(x)) for x in dd]
pool = np.concatenate([x-np.median(x) for x in dd]); mad = float(np.median(np.abs(pool-np.median(pool))))
s_die = 1.4826*mad/math.sqrt(2)
o['sigma_die'] = dict(diff_head=[[round(float(dd[0][i]),3), round(float(dd[1][i]),3)] for i in range(6)], pair_medians=[round(m,4) for m in meds],
  pooled_n=len(pool), pooled_median=round(float(np.median(pool)),4), MAD=round(mad,5), robust_sigma=round(1.4826*mad,5), value=round(s_die,5))
# sigma_run
e = Y - R[:,None]; r = np.median(e, 0); var_r = float(r.var(ddof=1)); share = math.pi/2*s_die**2/n
s_run = math.sqrt(max(0, var_r-share))
o['sigma_run'] = dict(run_medians=[round(float(x),5) for x in r], var_r=round(var_r,6), die_share_var=round(share,6), die_share_sd=round(math.sqrt(share),5), value=round(s_run,5),
  run_means=[round(float(x),4) for x in Y.mean(0)])
# LoQ
o['loq'] = dict(sigma=round(s_die,5), LoQ=round(10*s_die,4), LoD=round(3.29*s_die,4), data_resolution=0.001, res_term=round(0.001/math.sqrt(12),6), ref_median=round(float(np.median(R)),4), zone='정량' if abs(np.median(R))>=10*s_die else '<LoQ')
# Delta
t = float(stats.t.ppf(0.95, J-1)); f = math.sqrt(1+1/J); coef = t*f
o['delta'] = dict(r=0.05, policy=round(0.05*abs(float(np.median(R))),4), t=round(t,6), sqrt_term=round(f,6), coef=round(coef,4), run_margin=round(coef*s_run,5), value=round(0.05*abs(float(np.median(R)))+coef*s_run,5))
o['coef_table'] = {str(j): dict(t=round(float(stats.t.ppf(.95,j-1)),4), sqrt=round(math.sqrt(1+1/j),4), coef=round(float(stats.t.ppf(.95,j-1))*math.sqrt(1+1/j),4)) for j in range(2,11)}
# CI
x = np.sort(d); k = int(stats.binom.ppf(0.05, n, .5))
if stats.binom.cdf(k, n, .5) > 0.05: k -= 1
cov = float(1-2*stats.binom.cdf(k, n, .5))
o['ci'] = dict(median=round(float(np.median(d)),5), lo_rank=k+1, hi_rank=n-k, lo=round(float(x[k]),5), hi=round(float(x[n-1-k]),5), coverage=round(cov*100,2), sorted_around=[round(float(v),4) for v in x[k-2:k+3]], sorted_around_hi=[round(float(v),4) for v in x[n-1-k-2:n-1-k+3]])
o['rank_table'] = {}
for m in (30,45,60,90):
    kk = int(stats.binom.ppf(0.05, m, .5))
    if stats.binom.cdf(kk, m, .5) > 0.05: kk -= 1
    o['rank_table'][str(m)] = dict(lo_rank=kk+1, hi_rank=m-kk, coverage=round((1-2*stats.binom.cdf(kk,m,.5))*100,2))
D = o['delta']['value']
o['tost'] = dict(delta=round(D,5), inside=bool(-D < x[k] and x[n-1-k] < D), verdict='동등' if (-D < x[k] and x[n-1-k] < D) else ('차이' if (x[k]>D or x[n-1-k]<-D) else '미결'))
o['ttest'] = dict(t=round(float(d.mean()/(d.std(ddof=1)/math.sqrt(n))),3), p=float(T.ttest_p), verdict=T.ttest, ref_pairs=T.por_ttest_sig)
z95 = float(stats.norm.ppf(.95))
mm = 1.25*(z95+z95)*s_die*math.sqrt(1+1/J)/math.sqrt(n)
o['min_margin'] = dict(z95=round(z95,4), value=round(mm,4), value_sigma1=round(1.25*2*z95*1*math.sqrt(1+1/J)/math.sqrt(n),4), formula='1.25·(z0.95+z0.95)·σ_die·√(1+1/J)/√n')
o['jbins'] = dict(run_ratio_pct=round(s_run/abs(float(np.median(R)))*100,4), J3=round(5/o['coef_table']['3']['coef'],3), J4=round(5/o['coef_table']['4']['coef'],3), J5=round(5/o['coef_table']['5']['coef'],3), J5_shown='2.13 (2.13×2.34 = 4.984 < 5)')
# match with tool
chk = {'sigma_die': (s_die, T.sigma_die), 'sigma_run': (s_run, T.sigma_run), 'LoQ': (10*s_die, T.LoQ), 'LoD': (3.29*s_die, T.LoD), 'delta': (0.05*abs(float(np.median(R)))+coef*s_run, T.delta), 'run_margin': (coef*s_run, T.run_margin),
       'center': (float(np.median(d)), T.center), 'ci_low': (float(x[k]), T.ci_low), 'ci_high': (float(x[n-1-k]), T.ci_high), 'por_median': (float(np.median(R)), T.por_median)}
o['tool_match'] = {k: dict(mine=round(a,6), tool=round(float(b),6), same=bool(abs(a-b) < 1e-9)) for k,(a,b) in chk.items()}
o['tool_match']['verdict'] = dict(mine=o['tost']['verdict'], tool=T.verdict, same=o['tost']['verdict']==T.verdict)
json.dump(o, open('example.json','w'), ensure_ascii=False, indent=1)
print(json.dumps({k: o[k] for k in ('sigma_die','sigma_run','loq','delta','ci','tost','min_margin','jbins','rank_table')}, ensure_ascii=False))
print({k: v['same'] for k,v in o['tool_match'].items()})
