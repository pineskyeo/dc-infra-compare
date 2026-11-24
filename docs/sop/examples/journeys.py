"""SOP 예제 따라가기 데이터 (합성). ITEM 유형마다 예제 ITEM 하나를 ⓪~⑦ 단계 숫자로 남긴다.

유형마다 합성 데이터(seed 고정)를 만들어 POR 3회 + DOE 1회 DCNORMAL 한 벌로 합치고, 실제 판정 도구
(por_doe_compare.py, 분류와 최종 판정 포함)를 한 번 돌려 items.csv 의 그 ITEM 행에서 숫자를 옮긴다. 손으로 친 숫자는 없다.

  python docs/sop/examples/journeys.py           → journeys.json, ../assets/journeys.js 를 쓴다
  python docs/sop/examples/journeys.py --check   → 임시 폴더에 다시 만들어 두 파일과 다르면 실패 (exit 1)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (ROOT, ROOT / "examples", ROOT / "tests"):
    sys.path.insert(0, str(p))

import pandas as pd  # noqa: E402

import golden_cases  # noqa: E402
import make_load_data  # noqa: E402
import por_doe_compare as pdc  # noqa: E402
from classify import CLS_COLS  # noqa: E402
from explain import reason_plain  # noqa: E402
from item_view import basis_numbers  # noqa: E402

JSON_PATH = HERE / "journeys.json"
JS_PATH = HERE.parent / "assets" / "journeys.js"
JS_HEAD, JS_TAIL = "window.SOP_JOURNEYS = ", ";\n"
RUNS = ("por_run1", "por_run2", "por_run3", "doe")
Rows = list[list[str]]      # RUNS 순서로 DCNORMAL 측정 줄
LOAD_SEED, LOAD_DIES = 7, 60
LOG_RATIO, LOG_SEED, LOG_SCALE = 1.04, 0, 1e-6
ZERO_SEED, ZERO_DIES = 20261124, 60


def _line(coord: str, item: str, unit: str, value: str) -> str:
    return f"{coord},{coord},{coord},P1,1,1,1,{item},[{unit}],1,{value},,,,"


def _rows(item: str, unit: str, runs: list[np.ndarray], coords: list[str], fmt: str) -> Rows:
    return [[_line(c, item, unit, format(v, fmt)) for c, v in zip(coords, values)] for values in runs]


def _grid(n: int, width: int = 9) -> list[str]:
    return [f"{i % width}_{i // width}" for i in range(n)]


def _run_script(script: Path, out: Path) -> None:
    done = subprocess.run([sys.executable, "-B", str(script), str(out)], cwd=out.parent, capture_output=True,
                          text=True, env={**os.environ, "OMP_NUM_THREADS": "1"})
    if done.returncode:
        raise RuntimeError(f"{script.name} rc={done.returncode}\n{done.stderr[-2000:]}")


def _pick(folder: Path, item: str) -> Rows:
    """builder 가 쓴 DCNORMAL 에서 item 줄만 (값 글자 그대로)."""
    out = []
    for run in RUNS:
        files = sorted(p for p in (folder / run).rglob("*") if p.is_file())
        out.append([ln for f in files for ln in f.read_text().splitlines()
                    if ln.count(",") == 14 and ln.split(",")[7] == item])
    return out


def linear_rows(tmp: Path) -> Rows:
    _run_script(HERE / "make_example.py", tmp / "ex")
    w = pd.read_csv(tmp / "ex" / "example_wide.csv", dtype=str)
    return [[_line(c, "EX_ITEM", "ohm", v) for c, v in zip(w["coord"], w[col])]
            for col in ("ref1", "ref2", "ref3", "cand")]


def load_template_rows(name: str, number: int) -> Callable[[Path], Rows]:
    def make(tmp: Path) -> Rows:
        item = make_load_data.Item(number, name, name)
        runs = [make_load_data.measure(LOAD_SEED, item, run, LOAD_DIES) for run in range(4)]
        return _rows(name, item.template.unit, runs, _grid(LOAD_DIES), ".10g")
    return make


def log_rows(tmp: Path) -> Rows:
    runs, doe = golden_cases._truth_sample("wide", LOG_RATIO, LOG_SEED)
    values = [v * LOG_SCALE for v in (*runs, doe)]
    return _rows("ION_RATIO", "A", values, _grid(golden_cases.TRUTH_DIES), ".15g")


def zero_rows(tmp: Path) -> Rows:
    """0 근처 누설: die 참값 중앙 5 pA·퍼짐 4 pA (부호 섞임), 반복 흔들림 1 pA, 회차 이동 작음, DOE 만 +7 pA."""
    rng = np.random.default_rng(ZERO_SEED)
    true = rng.normal(5e-12, 4e-12, ZERO_DIES)
    offsets = (0.0, 0.2e-12, -0.15e-12, 0.0)
    runs = [true + off + rng.normal(0, 1e-12, ZERO_DIES) for off in offsets]
    runs[3] = runs[3] + 7e-12
    return _rows("IOFF_ZERO", "A", runs, _grid(ZERO_DIES), ".10g")


def step_rows(tmp: Path) -> Rows:
    _run_script(ROOT / "examples" / "make_por3_data.py", tmp / "por3")
    return _pick(tmp / "por3", "VOS_OFFSET")


@dataclass(frozen=True)
class Journey:
    key: str
    name: str
    item: str
    story: str
    source: str
    make: Callable[[Path], Rows]


JOURNEYS: tuple[Journey, ...] = (
    Journey("linear", "정량 · 선형", "EX_ITEM", "흔한 저항 값. DOE 가 POR 과 거의 같다.",
            "docs/sop/examples/make_example.py (seed 20263255, EX_ITEM)", linear_rows),
    Journey("shift", "정량 · 선형 · 이동", "VT_SHIFT", "문턱 전압. DOE 에서 30 mV 올라갔다.",
            f"examples/make_load_data.py measure (seed {LOAD_SEED}, 템플릿 VT_SHIFT, ITEM 번호 1, die {LOAD_DIES})",
            load_template_rows("VT_SHIFT", 1)),
    Journey("log", "정량 · 배율(log)", "ION_RATIO", "die 마다 값이 몇 배씩 다르고, 흔들림도 값에 비례한다.",
            f"tests/golden_cases.py _truth_sample (kind wide, 참 배율 {LOG_RATIO}, seed {LOG_SEED}) × {LOG_SCALE:g} A",
            log_rows),
    Journey("loq", "LoQ 아래", "IOFF_LEAK", "정량 한계 아래의 작은 전류. DOE 에서 일부 die 만 샌다.",
            f"examples/make_load_data.py measure (seed {LOAD_SEED}, 템플릿 IOFF_LEAK, ITEM 번호 2, die {LOAD_DIES}, blank 없음)",
            load_template_rows("IOFF_LEAK", 2)),
    Journey("zero", "0 근처", "IOFF_ZERO", "0 을 사이에 두고 +·− 로 찍히는 작은 전류.",
            f"docs/sop/examples/journeys.py zero_rows (seed {ZERO_SEED}, die {ZERO_DIES})", zero_rows),
    Journey("step", "계단 값", "VOS_OFFSET", "2 µV 간격으로만 찍히는 오프셋 전압.",
            "examples/make_por3_data.py (seed 11, VOS_OFFSET)", step_rows),
)
ORDER = [j.key for j in JOURNEYS]

USED_NAMES = {"linear": "허용폭 Δ", "loq": "허용폭 Δ", "log": "log 허용폭 Δ_log", "abs": "절대 허용폭",
              "accuracy": "Δ' = max(Δ, 장비 정확도)", "limit": "허용폭 Δ (한계 밖 die)"}
ROUTE_COLUMN = {pdc.R_LIMIT: "verdict_limit", pdc.R_ABS: "verdict_abs", pdc.R_LOG: "verdict_log",
                pdc.R_LINEAR: "verdict_with_accuracy"}
NO_ACTION = "할 일 없음 · 결과만 기록"
DIFF_CAUSE = ("이동이 허용폭 밖",
              "측정 쪽 원인부터 점검 (프로브카드 접촉 · 장비 · 측정 조건) · 다시 잼 · 그래도 차이면 차이로 두고 사람 판정 기록")


def write_dataset(folder: Path, parts: list[Rows]) -> None:
    for i, run in enumerate(RUNS):
        rows = [ln for part in parts for ln in part[i]]
        path = folder / run / "DCNORMAL"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(golden_cases.DCNORMAL_HEAD + rows + ["#MeasureDataEnd", "[EOF]"]) + "\n")


def judge(data: Path, out: Path) -> pd.DataFrame:
    args = [a for run in RUNS[:3] for a in ("--por", data / run)] + ["--doe", data / "doe", "--out", out]
    done = subprocess.run([sys.executable, "-B", str(ROOT / "por_doe_compare.py"), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True, env={**os.environ, "OMP_NUM_THREADS": "1"})
    if done.returncode:
        raise RuntimeError(f"por_doe_compare.py rc={done.returncode}\n{done.stderr[-3000:]}")
    return pd.read_csv(out / "items.csv", encoding="utf-8-sig").set_index("ITEM", drop=False)


def judge_input(data: Path) -> dict[str, pd.DataFrame]:
    """판정이 쓴 die 표 (por_doe_compare.load_wide, main 과 같은 ITEM 묶음과 순서)."""
    a = argparse.Namespace(por=[[str(data / run)] for run in RUNS[:3]], doe=[str(data / "doe")],
                           key="WAFERID,COORD_X_Y,ITEM", encoding="auto")
    wide, por_cols, _ = pdc.load_wide(a)
    return {item: g[["COORD_X_Y", *por_cols, "DOE"]] for item, g in wide.groupby("ITEM", sort=False)}


def num(x) -> float | None:
    """유효숫자 6자리. NaN·빈 값은 None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return float(f"{v:.6g}") if math.isfinite(v) else None


def text(x) -> str | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) or str(x).strip() == "" else str(x).strip()


def stage1(row: Mapping) -> dict:
    """1단계 전체 TOST. 정량 zone 은 items.csv 의 verdict·reason, LoQ zone 은 같은 구간·Δ 로 pdc.tost."""
    if row["zone"] not in pdc.LOQ_ZONE_NAMES:
        return {"verdict": row["verdict"], "reason": row["reason"]}
    v, why = pdc.tost(row["center"], row["ci_low"], row["ci_high"], row["delta"])
    return {"verdict": v, "reason": why}


def step6(row: Mapping) -> dict:
    s1 = stage1(row)
    s2 = ({"verdict": row["verdict"], "reason": row["reason"]} if row["zone"] in pdc.LOQ_ZONE_NAMES else None)
    s3 = None
    if row["verdict"] != "동등":
        col = pdc.route_method(row)
        s3 = {"route": row["route"], "verdict": text(row.get(col[0])) if col else None,
              "basis": row["verdict_basis"]}
    return {"stage1": s1, "stage2": s2, "stage3": s3,
            "final": {"verdict": row["verdict_final"], "basis": row["verdict_basis"]}}


def step7(row: Mapping, items: pd.DataFrame) -> dict:
    final = row["verdict_final"]
    if final == "동등":
        return {"cause": None, "action": NO_ACTION}
    if final == "미결":
        import slides
        name = slides.undecided_causes(items.loc[[row["ITEM"]]].reset_index(drop=True)).iloc[0]
        return {"cause": name, "action": next(c.action for c in slides.CAUSES if c.name == name)}
    if final == "차이":
        return {"cause": DIFF_CAUSE[0], "action": DIFF_CAUSE[1]}
    return {"cause": final, "action": text(row["reason"])}


def journey_record(j: Journey, row: Mapping, g: pd.DataFrame, items: pd.DataFrame) -> dict:
    por = g[[c for c in g.columns if c.startswith("POR")]].to_numpy(float)
    doe = g["DOE"].to_numpy(float)
    n, J = por.shape
    b = basis_numbers(row)
    log = {k: num(row[f"{k}_log"]) for k in ("center", "ci_low", "ci_high")}
    return {
        "key": j.key, "name": j.name, "item": j.item, "unit": text(row["UNIT"]), "story": j.story,
        "final": {"verdict": row["verdict_final"], "basis": row["verdict_basis"], "route": row["route"],
                  "why": reason_plain(row)},
        "n_die": int(row["n_die"]), "J": J,
        "raw": {"die": g["COORD_X_Y"].tolist(), "por": [[num(v) for v in r] for r in por],
                "doe": [num(v) for v in doe], "d": [num(v) for v in doe - por.mean(axis=1)]},
        "step2": {k: num(row[k]) for k in ("sigma_die", "sigma_run", "sigma_meas", "meas_precision_pct")},
        "step3": {"por_median": num(row["por_median"]), "LoD": num(row["LoD"]), "LoQ": num(row["LoQ"]),
                  "limit_source": row["limit_source"], "zone": row["zone"], "loq_ratio": num(row["loq_ratio"]),
                  "cls": {c.removeprefix("cls_"): text(row[c]) for c in CLS_COLS}, "route": row["route"]},
        "step4": {"center": num(row["center"]), "ci_low": num(row["ci_low"]), "ci_high": num(row["ci_high"]),
                  "ci_rank_k": pdc.ci_rank(n) + 1, "log": log if log["center"] is not None else None},
        "step5": {**{k: num(row.get(k)) for k in ("policy_margin", "run_margin", "delta", "delta_log", "abs_delta",
                                                   "accuracy_margin", "resolution_step")},
                  "t_factor": num(pdc.run_factor(J)),
                  "used": {"name": USED_NAMES[b.name], "value": num(b.margin)}},
        "step6": step6(row),
        "step7": step7(row, items),
    }


def build(work: Path) -> tuple[dict, pd.DataFrame]:
    """(journeys 데이터, 같은 실행의 items.csv). work 아래에 합성 데이터와 판정 결과를 쓴다."""
    data = work / "data"
    write_dataset(data, [j.make(work) for j in JOURNEYS])
    items = judge(data, work / "out")
    groups = judge_input(data)
    types = {j.key: journey_record(j, items.loc[j.item].to_dict(), groups[j.item], items) for j in JOURNEYS}
    meta = {"generated_by": "python docs/sop/examples/journeys.py (판정: por_doe_compare.py, 기본 인자 r = 0.05)",
            "source": {j.key: j.source for j in JOURNEYS}, "note": "합성 데이터"}
    return {"meta": meta, "order": ORDER, "types": types}, items


def render(data: dict) -> tuple[str, str]:
    body = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
    return body + "\n", JS_HEAD + body + JS_TAIL


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="다시 만들어 커밋된 파일과 다르면 exit 1")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        js_text = render(build(Path(tmp))[0])
    targets = {JSON_PATH: js_text[0], JS_PATH: js_text[1]}
    if a.check:
        stale = [p for p, t in targets.items() if not p.is_file() or p.read_text(encoding="utf-8") != t]
        for p in stale:
            print(f"다름: {p.relative_to(ROOT)}")
        sys.exit(1 if stale else 0)
    for p, t in targets.items():
        p.write_text(t, encoding="utf-8")
        print(f"씀: {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
