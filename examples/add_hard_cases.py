"""해상도 부족 원인별 항목(die 적음, 부호 섞임, 계단값, blank보다 큰 흔들림)과 일부 die만 누설이 큰 바닥 항목."""
import sys
from pathlib import Path

import numpy as np

td = Path(sys.argv[1])
rng = np.random.default_rng(1)


def write(path, rows):
    lines = ["#FileFormatInformationStart", "FILEFORMAT=DCNORMAL", "#FileFormatInformationEnd",
             "#ProductInformationStart", "WAFERID=W01", "#ProductInformationEnd", "#MeasureDataStart",
             "COORD_X_Y,FLAT_X_Y,DIE_X_Y,POINT_NAME,MODULE_NO,BIN,DUT,ITEM,UNIT,MEASURE_PNT,DATA,SPECLOW,SPECHIGH,JUDGE_LIM,JUDGE_RST"]
    lines += [f"{x}_{y},{x}_{y},{x}_{y},P1,1,1,1,{it},[{u}],1,{v:.10g},,,," for (x, y, it, u, v) in rows]
    path.write_text("\n".join(lines + ["#MeasureDataEnd", "[EOF]"]) + "\n")


dies = [(x, y) for x in range(10) for y in range(10)]
R, N = [], []
for i, (x, y) in enumerate(dies):
    if i < 15:
        R.append((x, y, "FEW_DIE", "V", 10 + rng.normal(0, 0.05)))
        N.append((x, y, "FEW_DIE", "V", 10 + rng.normal(0, 0.05) + 0.48))
    t = 5e-5 if i % 2 else -5e-5
    R.append((x, y, "SIGNMIX", "V", t + rng.normal(0, 5e-6)))
    N.append((x, y, "SIGNMIX", "V", t + rng.normal(0, 5e-6)))
    R.append((x, y, "STEP", "V", 1.0))
    N.append((x, y, "STEP", "V", 1.0 + (0.3 if i % 9 == 0 else 0)))
    R.append((x, y, "ILEAK_WOBBLE", "A", 20e-12 + rng.normal(0, 15e-12)))
    N.append((x, y, "ILEAK_WOBBLE", "A", 20e-12 + rng.normal(0, 15e-12)))
    # 바닥 항목인데 New에서 die 30%에 20 pA 누설: LoQ 기준으로도 잡혀야 함
    R.append((x, y, "IOFF_LEAKY", "A", rng.normal(0, 0.7e-12)))
    N.append((x, y, "IOFF_LEAKY", "A", rng.normal(0, 0.7e-12) + (20e-12 if i % 10 < 3 else 0)))
write(td / "ref" / "REF_extra", R)
write(td / "new" / "NEW_extra", N)
with open(td / "blank_map.csv", "a") as f:
    f.write("ILEAK_WOBBLE,OPEN_I_1PA\n")
