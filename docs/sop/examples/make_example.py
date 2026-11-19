"""합성 예시 ITEM 1개 (EX_ITEM): 기준 조건 3회 + 비교 조건 1회, die 60개. seed 20263255 고정.
참값 = 100 + die 사이 퍼짐(SD 3), 회차 이동 -0.5 / 0 / +0.5, 반복 흔들림 SD 1.0, 비교 조건 이동 +0.8.
기준 조건 die별 3회 평균의 중앙값이 100이 되게 전체를 옮기고 소수 3자리로 반올림.
사용: python make_example.py OUTDIR  → OUTDIR/ref_run1..3/REF.dcn, OUTDIR/cand/CAND.dcn, OUTDIR/example_wide.csv"""
import sys
from pathlib import Path
import numpy as np
SEED, N = 20263255, 60
out = Path(sys.argv[1]); rng = np.random.default_rng(SEED)
true = 100 + rng.normal(0, 3.0, N)
Y = np.stack([true + o + rng.normal(0, 1.0, N) for o in (-0.5, 0.0, 0.5)], 1)
z = true + 0.8 + rng.normal(0, 1.0, N)
off = 100 - np.median(Y.mean(1)); Y = np.round(Y + off, 3); z = np.round(z + off, 3)
dies = [(i % 10, i // 10) for i in range(N)]
def write(path, v):
    L = ["#FileFormatInformationStart", "FILEFORMAT=DCNORMAL", "#FileFormatInformationEnd", "#ProductInformationStart",
         "WAFERID=W01", "#ProductInformationEnd", "#MeasureDataStart",
         "COORD_X_Y,FLAT_X_Y,DIE_X_Y,POINT_NAME,MODULE_NO,BIN,DUT,ITEM,UNIT,MEASURE_PNT,DATA,SPECLOW,SPECHIGH,JUDGE_LIM,JUDGE_RST"]
    for i, (x, y) in enumerate(dies):
        L.append(f"{x}_{y},{x}_{y},{x}_{y},P1,1,1,1,EX_ITEM,[ohm],1,{v[i]:.3f},,,,")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L + ["#MeasureDataEnd", "[EOF]"]) + "\n")
for r in range(3): write(out / f"ref_run{r + 1}" / "REF.dcn", Y[:, r])
write(out / "cand" / "CAND.dcn", z)
with open(out / "example_wide.csv", "w") as f:
    f.write("die,coord,ref1,ref2,ref3,cand\n")
    for i, (x, y) in enumerate(dies): f.write(f"{i + 1},{x}_{y},{Y[i,0]:.3f},{Y[i,1]:.3f},{Y[i,2]:.3f},{z[i]:.3f}\n")
