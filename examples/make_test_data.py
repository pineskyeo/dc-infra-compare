"""합성 DCNORMAL: Ref 10파일, New 2파일, blank(DCNORMAL + CSV). 항목별 기대 판정은 EXPECT."""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(7)
dies = [(x, y) for x in range(10) for y in range(10)]
N = len(dies)

def vt():   return rng.normal(0.45, 0.01, N)
true = {
    "VT_N": ("V", vt(), 0.5e-3, 0.0),
    "VT_SHIFT": ("V", vt(), 0.5e-3, 10e-3),
    "VT_BORDER": ("V", np.full(N, 0.45) + rng.normal(0, 0.01, N), 0.5e-3, 4.5e-3),
    "IOFF_FLOOR": ("A", np.zeros(N), 0.7e-12, 0.0),
    "IOFF_NOBLANK": ("A", np.zeros(N), 0.7e-12, 0.0),
    "IOFF_OFFSET": ("A", np.zeros(N), 0.7e-12, 3e-12),
    "IOFF_MAP": ("A", np.zeros(N), 0.7e-12, 0.0),
    "ION_BIMODAL": ("A", np.where(np.arange(N) % 2, 500e-6, 300e-6), 0.5e-6, 0.0),
    "CAP_OUT": ("F", rng.normal(1e-12, 2e-14, N), 1e-15, 0.0),
}
EXPECT = {"VT_N": "동등", "VT_SHIFT": "차이", "VT_BORDER": "미결(경계 shift)", "IOFF_FLOOR": "동등",
          "IOFF_NOBLANK": "미결(해상도 부족 / blank 없음)", "IOFF_OFFSET": "차이", "IOFF_MAP": "동등",
          "ION_BIMODAL": "동등", "CAP_OUT": "동등 + 이상 die 3개"}

def measure(side):
    vals = {}
    for item, (unit, t, noise, shift) in true.items():
        v = t + rng.normal(0, noise, N) + (shift if side == "new" else 0.0)
        if item == "CAP_OUT" and side == "new":
            v[[5, 40, 77]] = 0.0
        vals[item] = (unit, v)
    return vals

def write(path, die_idx, vals, items=None, wafer="W01"):
    lines = ["#FileFormatInformationStart", "FILEFORMAT=DCNORMAL", "VERSION=1", "#FileFormatInformationEnd",
             "#ProductInformationStart", "LOTID=TLOT01", f"WAFERID={wafer}", "#ProductInformationEnd",
             "#MeasureDataStart",
             "COORD_X_Y,FLAT_X_Y,DIE_X_Y,POINT_NAME,MODULE_NO,BIN,DUT,ITEM,UNIT,MEASURE_PNT,DATA,SPECLOW,SPECHIGH,JUDGE_LIM,JUDGE_RST"]
    for i in die_idx:
        x, y = dies[i]
        for item in (items or vals):
            unit, v = vals[item]
            val = v[i] if np.ndim(v) else v
            lines.append(f"{x}_{y},{x}_{y},{x}_{y},P1,1,1,1,{item},[{unit}],1,{val:.10g},,,,")
    lines += ["#MeasureDataEnd", "[EOF]"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")

ref, new = measure("ref"), measure("new")
for k in range(10):
    write(out / "ref" / f"REF_part{k:02d}", range(k * 10, k * 10 + 10), ref)
for k in range(2):
    write(out / "new" / f"NEW_part{k}", range(k * 50, k * 50 + 50), new)

blank_vals = {"IOFF_FLOOR": ("A", rng.normal(0, 0.7e-12, 61)), "OPEN_I_1PA": ("A", rng.normal(0, 0.7e-12, 61))}
write(out / "blank" / "BLANK_open", range(61), {k: (u, v) for k, (u, v) in blank_vals.items()})
(out / "blank_summary.csv").write_text("ITEM,SIGMA0\nIOFF_OFFSET,7e-13\n")
(out / "blank_map.csv").write_text("ITEM,BLANK_ITEM\nIOFF_MAP,OPEN_I_1PA\n")
print("기대 판정:")
for k, v in EXPECT.items():
    print(f"  {k:14s} {v}")
