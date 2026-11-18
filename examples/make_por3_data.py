"""합성 DCNORMAL: POR 3회(run1~3) + DOE 1회, die 61개. 항목별 기대 판정은 EXPECT."""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(11)
N = 61
dies = [(i % 9, i // 9) for i in range(N)]

# 항목: (단위, 참값, die 흔들림, 회차 평균 흔들림, DOE shift, 스펙)
ITEMS = {
    "VT_SAME": ("V", rng.normal(0.45, 0.01, N), 1e-3, 0.3e-3, 0.0, None),
    "VT_SHIFT": ("V", rng.normal(0.45, 0.01, N), 1e-3, 0.3e-3, 0.03, None),
    "RON_CONTACT": ("ohm", rng.normal(100, 3, N), 2.0, 1.5, 2.0, None),
    "IOFF_FLOOR": ("A", np.zeros(N), 1e-12, 0.1e-12, 0.0, None),
    "IOFF_LEAK": ("A", np.zeros(N), 1e-12, 0.1e-12, 0.0, None),
    "ION_OUTLIER": ("A", rng.normal(500e-6, 5e-6, N), 0.5e-6, 0.1e-6, 0.0, None),
    "IDSAT_SPEC": ("A", rng.normal(600e-6, 5e-6, N), 0.5e-6, 0.2e-6, 8e-6, (500e-6, 510e-6)),
    "IOFF_RUNWOBBLE": ("A", np.zeros(N), 1e-12, 0.0, 0.0, None),
    "VOS_OFFSET": ("V", rng.normal(30e-6, 3e-6, N), 2.4e-6, 0.5e-6, 3.7e-6, None),
}
EXPECT = {
    "VT_SAME": "동등",
    "VT_SHIFT": "차이",
    "RON_CONTACT": "t-test 유의차, TOST 동등 (회차 평균 흔들림 안)",
    "IOFF_FLOOR": "동등 (LoQ 미만)",
    "IOFF_LEAK": "차이 (LoQ 미만, DOE만 누설 die)",
    "ION_OUTLIER": "동등 (튀는 die 4개. Hodges–Lehmann이라 끌려가지 않음)",
    "IDSAT_SPEC": "동등 (가짜 스펙 10 µA는 무시. shift 8 µA < |POR| 5% = 30 µA)",
    "VOS_OFFSET": "차이 (+3.7 µV > |POR| 5% = 1.5 µV). --level level.csv --accuracy: 동등 (2 V range 정확도 안)",
    "IOFF_RUNWOBBLE": "동등 또는 미결, 차이 아님 (POR 회차마다 바닥 offset이 크게 다름. DOE offset은 그 범위 안)",
}
run_offset = {k: rng.normal(0, v[3], 4) for k, v in ITEMS.items()}
run_offset["RON_CONTACT"] = np.array([0.0, 1.8, -1.6, 0.5])
run_offset["IOFF_RUNWOBBLE"] = np.array([0.0, 15e-12, -12e-12, 12e-12])


def measure(run: int) -> dict:
    vals = {}
    for k, (u, t, s_die, _, shift, spec) in ITEMS.items():
        v = t + rng.normal(0, s_die, N) + run_offset[k][run]
        if run == 3:
            v = v + shift
            if k == "IOFF_LEAK":
                v[rng.permutation(N)[:20]] += 30e-12
            if k == "ION_OUTLIER":
                v[[3, 17, 40, 52]] += 80e-6
        if k == "VOS_OFFSET":
            v = np.round(v / 2e-6) * 2e-6      # 2 V range 분해능 2 µV
        vals[k] = (u, v, spec)
    return vals


def write(path: Path, vals: dict) -> None:
    lines = ["#FileFormatInformationStart", "FILEFORMAT=DCNORMAL", "#FileFormatInformationEnd",
             "#ProductInformationStart", "WAFERID=W01", "#ProductInformationEnd", "#MeasureDataStart",
             "COORD_X_Y,FLAT_X_Y,DIE_X_Y,POINT_NAME,MODULE_NO,BIN,DUT,ITEM,UNIT,MEASURE_PNT,DATA,SPECLOW,SPECHIGH,JUDGE_LIM,JUDGE_RST"]
    for i, (x, y) in enumerate(dies):
        for k, (u, v, spec) in vals.items():
            lo, hi = (f"{spec[0]:g}", f"{spec[1]:g}") if spec else ("", "")
            lines.append(f"{x}_{y},{x}_{y},{x}_{y},P1,1,1,1,{k},[{u}],1,{v[i]:.10g},{lo},{hi},,")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines + ["#MeasureDataEnd", "[EOF]"]) + "\n")


def step_item(run: int) -> tuple:
    """분해능 10 pA 계단값 바닥 항목. POR은 전부 0으로 읽히고 DOE만 die 5개가 한 계단 위."""
    v = np.zeros(N)
    if run == 3:
        v[rng.permutation(N)[:5]] = 10e-12
    return ("A", v, None)


for r in range(3):
    write(out / f"por_run{r + 1}" / "POR", {**measure(r), "IOFF_STEP": step_item(r)})
write(out / "doe" / "DOE", {**measure(3), "IOFF_STEP": step_item(3)})
write(out / "blank" / "BLANK", {"OPEN_I": ("A", rng.normal(0, 1.5e-12, N), None)})
(out / "blank_map.csv").write_text("ITEM,BLANK_ITEM\nIOFF_STEP,OPEN_I\nIOFF_FLOOR,OPEN_I\nIOFF_LEAK,OPEN_I\n")
(out / "level.csv").write_text("ITEM,LEVEL,SCALE\nVT_SAME,100mV,1\nVT_SHIFT,100mV,1\nVOS_OFFSET,10uV,1\nION_OUTLIER,100uA,1\n"
                               "IDSAT_SPEC,100uA,1\nIOFF_FLOOR,100fA,1\nIOFF_LEAK,10fA,1\nIOFF_STEP,1pA,\nIOFF_RUNWOBBLE,1pA,1\n")
EXPECT["IOFF_STEP"] = "blank 없이: 미결(해상도 부족, sigma_die = 0). blank 하한 적용: 동등 (LoQ 미만)"
print("기대 판정:")
for k, v in EXPECT.items():
    print(f"  {k:12s} {v}")
