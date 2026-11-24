#!/usr/bin/env python3
"""docs/slides/dc-equiv-criteria-v4.pptx 와 쪽별 jpg 를 합성 데이터로 다시 만든다 (실데이터 없음).

합성 데이터 = examples/make_load_data.py 600 ITEM (seed 7), 그룹 = ITEM 유형 앞부분 (VT, IOFF, RON, IDSAT, ION, FEW).
실데이터 장표는 판정한 PC 에서 python dcc.py slides <조합> 으로 만든다 (<out>/<조합>/slides.pptx).

    python docs/slides/v4-src/build.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

import make_load_data as load  # noqa: E402
import numpy as np  # noqa: E402
import slides  # noqa: E402

NAME, ITEMS, SEED = "dc-equiv-criteria-v4", 600, 7
OUT = ROOT / "docs" / "slides"


def groups_csv(path: Path) -> None:
    """make_load_data 와 같은 순서로 ITEM 유형을 배정해 ITEM,group 파일을 쓴다."""
    rotation = [name for name, weight in load.WEIGHTS.items() for _ in range(weight)]
    np.random.default_rng(SEED).shuffle(rotation)
    width = max(5, len(str(ITEMS)))
    rows = [f"IT{i + 1:0{width}d},{rotation[i % len(rotation)].split('_')[0]}" for i in range(ITEMS)]
    path.write_text("ITEM,group\n" + "\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    py = sys.executable
    with tempfile.TemporaryDirectory() as tmp:
        data, out = Path(tmp) / "data", Path(tmp) / "out"
        subprocess.run([py, str(ROOT / "examples" / "make_load_data.py"), str(data), "--items", str(ITEMS),
                        "--dies", "61", "--seed", str(SEED)], check=True, capture_output=True)
        groups_csv(data / "groups.csv")
        raw = [a for k in (1, 2, 3) for a in ("--por", str(data / f"por_run{k}"))]
        subprocess.run([py, str(ROOT / "por_doe_compare.py"), *raw, "--doe", str(data / "doe"),
                        "--level", str(data / "level.csv"), "--blank", str(data / "blank"),
                        "--blank-map", str(data / "blank_map.csv"), "--groups", str(data / "groups.csv"),
                        "--out", str(out)], check=True, capture_output=True, cwd=ROOT)
        deck = slides.build(out, label="합성 예시")
        pptx = slides.write_pptx(OUT / f"{NAME}.pptx", deck, title="DC Test 판정 기준 개선")
        print(pptx)
        for jpg in slides.render_previews(deck, OUT / NAME):
            print(jpg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
