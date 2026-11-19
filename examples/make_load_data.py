"""Deterministic synthetic DCNORMAL load data: three POR runs, one DOE, and blank.

Example:
    python examples/make_load_data.py OUT --items 6000 --dies 60 --seed 7
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np


HEADER = [
    "#FileFormatInformationStart",
    "FILEFORMAT=DCNORMAL",
    "#FileFormatInformationEnd",
    "#ProductInformationStart",
    "WAFERID=W01",
    "#ProductInformationEnd",
    "#MeasureDataStart",
    "COORD_X_Y,FLAT_X_Y,DIE_X_Y,POINT_NAME,MODULE_NO,BIN,DUT,ITEM,UNIT,MEASURE_PNT,DATA,SPECLOW,SPECHIGH,JUDGE_LIM,JUDGE_RST",
]
FOOTER = ["#MeasureDataEnd", "[EOF]"]


@dataclass(frozen=True)
class Template:
    """Parameters copied from make_por3_data.py, plus the FEW_DIE hard case."""

    unit: str
    center: float
    spread: float
    sigma_die: float
    sigma_run: float
    shift: float = 0.0
    spec: tuple[float, float] | None = None
    level: str = ""
    calcval: str = "1"
    derived: str = "N"
    blank: bool = False
    kind: str = "normal"


TEMPLATES = {
    "VT_SAME": Template("V", 0.45, 0.01, 1e-3, 0.3e-3, level="100mV"),
    "RON_CONTACT": Template("ohm", 100.0, 3.0, 2.0, 1.5, 2.0, level="", derived="Y"),
    "IDSAT_SPEC": Template(
        "A", 600e-6, 5e-6, 0.5e-6, 0.2e-6, 8e-6,
        spec=(500e-6, 510e-6), level="100uA",
    ),
    "IOFF_RUNWOBBLE": Template("A", 0.0, 0.0, 0.0, 0.0, level="1pA", kind="wobble"),
    "VT_SHIFT": Template("V", 0.45, 0.01, 1e-3, 0.3e-3, 0.03, level="100mV"),
    # A shift exactly at the 5% policy margin: the sign-test CI straddles it.
    "VT_BORDER": Template("V", 0.45, 0.01, 1e-3, 0.0, 0.05 * 0.45, level="100mV"),
    # A quantifiable 50 pA baseline keeps this out of the <LoQ branch. Only a
    # minority of DOE dies moves one 10 pA step, so the sign-test CI of the
    # median shift is [0, 0] and the verdict is 동등 (CI inside ±Δ).
    # DERIVED=Y prevents an instrument accuracy margin from masking the case.
    "IOFF_STEP": Template(
        "A", 50e-12, 0.0, 0.0, 0.0, level="", calcval="", derived="Y", kind="step",
    ),
    "IOFF_FLOOR": Template(
        "A", 0.0, 0.0, 1e-12, 0.1e-12, level="100fA", blank=True, kind="floor",
    ),
    # The 8 pA centre is normally between the blank LoD and LoQ. The minority
    # of leaky DOE dies exercises the <LoQ reporting rule without a median shift.
    "IOFF_LEAK": Template(
        "A", 8e-12, 0.0, 1e-12, 0.1e-12, level="10fA", blank=True, kind="leak",
    ),
    "ION_OUTLIER": Template(
        "A", 500e-6, 5e-6, 0.5e-6, 0.1e-6, level="100uA", kind="outlier",
    ),
    "FEW_DIE": Template("V", 10.0, 0.0, 0.05, 0.0, 0.48, level="100mV", kind="few"),
}

# A 100-slot shuffled rotation gives exact default proportions and deterministic
# assignment by ITEM number. FEW_DIE takes 1% from the roughly 70% same group.
WEIGHTS = {
    "VT_SAME": 45,
    "RON_CONTACT": 12,
    "IDSAT_SPEC": 8,
    "IOFF_RUNWOBBLE": 4,
    "VT_SHIFT": 10,
    "VT_BORDER": 8,
    "IOFF_STEP": 5,
    "IOFF_FLOOR": 3,
    "IOFF_LEAK": 2,
    "ION_OUTLIER": 2,
    "FEW_DIE": 1,
}
EXPECTED = {
    "VT_SAME": "동등",
    "RON_CONTACT": "동등 (run margin)",
    "IDSAT_SPEC": "동등 (spec ignored)",
    "IOFF_RUNWOBBLE": "동등 / <LoQ",
    "VT_SHIFT": "차이",
    "VT_BORDER": "미결 경계",
    "IOFF_STEP": "동등 (minority 10 pA step, median CI [0, 0])",
    "IOFF_FLOOR": "동등 / LoQ 미만",
    "IOFF_LEAK": "동등 / 검출~정량, <LoQ 보고 일치",
    "ION_OUTLIER": "동등 + outlier dies",
    "FEW_DIE": "미결 die 부족",
}


@dataclass(frozen=True)
class Item:
    number: int
    code: str
    template_name: str

    @property
    def template(self) -> Template:
        return TEMPLATES[self.template_name]


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def nonnegative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def stream_rng(seed: int, item_number: int, stream: int) -> np.random.Generator:
    """Independent streams make output independent of file/item write order."""
    return np.random.default_rng(np.random.SeedSequence([seed, item_number, stream]))


def selected_dies(seed: int, item: Item, dies: int, fraction: float) -> np.ndarray:
    count = min(dies, max(1, int(round(dies * fraction))))
    return stream_rng(seed, item.number, 2).choice(dies, size=count, replace=False)


def measure(seed: int, item: Item, run: int, dies: int) -> np.ndarray:
    """Return one run; run 0..2 are POR and run 3 is DOE."""
    t = item.template
    if t.kind == "step":
        values = np.full(dies, t.center)
        if run == 3:
            values[selected_dies(seed, item, dies, 5 / 61)] += 10e-12
        return values

    base = stream_rng(seed, item.number, 0).normal(t.center, t.spread, dies)
    offsets = stream_rng(seed, item.number, 1).normal(0.0, t.sigma_run, 4)
    if item.template_name == "RON_CONTACT":
        offsets = np.array([0.0, 1.8, -1.6, 0.5])
    elif t.kind == "wobble":
        offsets = np.array([0.0, 15e-12, -12e-12, 12e-12])

    noise = stream_rng(seed, item.number, 10 + run).normal(0.0, t.sigma_die, dies)
    values = base + noise + offsets[run]
    if run == 3:
        values += t.shift
        if t.kind == "leak":
            values[selected_dies(seed, item, dies, 20 / 61)] += 30e-12
        elif t.kind == "outlier":
            values[selected_dies(seed, item, dies, 4 / 61)] += 80e-6
    return values


def write_rows(path: Path, rows: list[str]) -> None:
    """Build all lines in memory and perform one write per output file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(HEADER + rows + FOOTER) + "\n", encoding="utf-8")


def write_measurement(
    path: Path,
    seed: int,
    items: list[Item],
    coordinates: list[tuple[int, int]],
    run: int,
    few_count: int,
) -> None:
    # Each tuple is (ITEM, UNIT, SPECLOW, SPECHIGH, values, first die to omit).
    data = []
    for item in items:
        t = item.template
        lo, hi = (f"{t.spec[0]:g}", f"{t.spec[1]:g}") if t.spec else ("", "")
        omit_from = few_count if t.kind == "few" else len(coordinates)
        data.append((item.code, t.unit, lo, hi, measure(seed, item, run, len(coordinates)), omit_from))

    lines = []
    for i, (x, y) in enumerate(coordinates):
        coord = f"{x}_{y}"
        for code, unit, lo, hi, values, omit_from in data:
            if i >= omit_from:
                continue
            lines.append(
                f"{coord},{coord},{coord},P1,1,1,1,{code},[{unit}],1,"
                f"{values[i]:.10g},{lo},{hi},,"
            )
    write_rows(path, lines)


def write_blank(path: Path, seed: int, coordinates: list[tuple[int, int]]) -> None:
    values = np.random.default_rng(np.random.SeedSequence([seed, 0, 100])).normal(
        0.0, 1.5e-12, len(coordinates)
    )
    lines = [
        f"{x}_{y},{x}_{y},{x}_{y},P1,1,1,1,OPEN_I,[A],1,{values[i]:.10g},,,,"
        for i, (x, y) in enumerate(coordinates)
    ]
    write_rows(path, lines)


def write_metadata(out: Path, items: list[Item]) -> None:
    level_lines = ["ITEM,LEVEL,CALCVAL,DERIVED"]
    blank_lines = ["ITEM,BLANK_ITEM"]
    for item in items:
        t = item.template
        level_lines.append(f"{item.code},{t.level},{t.calcval},{t.derived}")
        if t.blank:
            blank_lines.append(f"{item.code},OPEN_I")
    (out / "level.csv").write_text("\n".join(level_lines) + "\n", encoding="utf-8")
    (out / "blank_map.csv").write_text("\n".join(blank_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, metavar="OUT")
    parser.add_argument("--items", type=positive_int, default=6000)
    parser.add_argument("--dies", type=positive_int, default=60)
    parser.add_argument("--seed", type=nonnegative_int, default=7)
    args = parser.parse_args()

    rotation = [name for name, weight in WEIGHTS.items() for _ in range(weight)]
    np.random.default_rng(args.seed).shuffle(rotation)
    width = max(5, len(str(args.items)))
    items = [
        Item(i + 1, f"IT{i + 1:0{width}d}", rotation[i % len(rotation)])
        for i in range(args.items)
    ]
    coordinates = [(i % 9, i // 9) for i in range(args.dies)]
    few_count = min(6, args.dies)  # below por_doe_compare.MIN_DIE (= 10)

    for run in range(3):
        write_measurement(
            args.out / f"por_run{run + 1}" / "POR",
            args.seed, items, coordinates, run, few_count,
        )
    write_measurement(args.out / "doe" / "DOE", args.seed, items, coordinates, 3, few_count)
    write_blank(args.out / "blank" / "BLANK", args.seed, coordinates)
    write_metadata(args.out, items)

    counts = Counter(item.template_name for item in items)
    print(f"Wrote {len(items):,} synthetic ITEMs and {args.dies:,} dies to {args.out}")
    print("Counts per template:")
    for name in WEIGHTS:
        print(f"  {name:16s} {counts[name]:6d}  {EXPECTED[name]}")


if __name__ == "__main__":
    main()
