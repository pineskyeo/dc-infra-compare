"""run_all.py 전체 흐름 테스트 (examples/make_por3_data.py 합성 데이터)."""
import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "examples" / "make_por3_data.py"
RUN_ALL = ROOT / "run_all.py"


def run_script(script: Path, args, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """test_refactor.run_script와 같은 방식(복사본). check=False로 rc를 테스트에서 본다."""
    env = os.environ.copy()
    old_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + old_pythonpath if old_pythonpath else "")
    env.pop("RUN_ALL_FAIL_STEP", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(script), *[str(arg) for arg in args]],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def por3_data(tmp_path: Path) -> Path:
    data = tmp_path / "por3"
    proc = run_script(GENERATOR, [data])
    assert proc.returncode == 0, proc.stderr
    return data


def compare_args(data: Path, out: Path) -> list:
    return [
        "--por", data / "por_run1",
        "--por", data / "por_run2",
        "--por", data / "por_run3",
        "--doe", data / "doe",
        "--r", "0.05",
        "--level", data / "level.csv",
        "--blank", data / "blank",
        "--blank-map", data / "blank_map.csv",
        "--key", "WAFERID,COORD_X_Y,ITEM",
        "--encoding", "auto",
        "--out", out,
    ]


def _detail(proc: subprocess.CompletedProcess) -> str:
    return f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


def test_run_all_success(por3_data: Path, tmp_path: Path):
    out = tmp_path / "out"
    proc = run_script(RUN_ALL, compare_args(por3_data, out))
    assert proc.returncode == 0, _detail(proc)
    assert (out / "items.csv").is_file()
    assert (out / "fail_evidence" / "fail_evidence.csv").is_file()
    assert (out / "summary_items.txt").is_file()
    assert list((out / "plots").glob("*.png"))
    assert "[단계 5/5] plot_verdicts" in proc.stdout
    assert "생성 파일" in proc.stdout
    assert "items.csv" in proc.stdout
    assert [p for p in (out / "log_compare").iterdir() if p.is_file()]

    # 원데이터 인자를 fail_evidence 에도 넘기므로 대상 ITEM 폴더마다 raw.csv 가 있다.
    assert (out / "fail_evidence" / "items_index.csv").is_file()
    items_root = out / "fail_evidence" / "items"
    item_dirs = [d for d in items_root.iterdir() if d.is_dir()] if items_root.is_dir() else []
    for d in item_dirs:
        assert (d / "raw.csv").is_file(), d.name
    if item_dirs:
        assert "ITEM 하나의 die별 원데이터" in proc.stdout


def test_describe_summarize_outputs():
    import run_all

    assert run_all.describe("summary.txt") == "공유용 판정 요약 (ITEM 이름 없음, summarize 출력)"
    assert run_all.describe("item_map.csv") == "익명 번호 ↔ 실제 ITEM 대응표 (공유하지 말 것)"
    assert run_all.describe("fail_evidence/summary.txt") == "Fail 근거 요약"


def test_describe_fail_evidence_item_folders_and_log_compare():
    import run_all

    assert run_all.describe("fail_evidence/items_index.csv") == "ITEM별 근거 폴더 목록"
    assert run_all.describe("fail_evidence/items/differ_A1/summary.csv") == "ITEM 하나의 판정 열 전체"
    assert run_all.describe("fail_evidence/items/differ_A1/raw.csv") == "ITEM 하나의 die별 원데이터"
    assert run_all.describe("fail_evidence/items/differ_A1/item_view.png") == "ITEM 하나의 근거 그림"
    assert run_all.describe("log_compare/log_compare.csv") != "산출물"
    assert run_all.describe("log_compare/log_compare.png") != "산출물"


def test_run_all_before_and_groups(por3_data: Path, tmp_path: Path):
    first = tmp_path / "first"
    proc = run_script(RUN_ALL, compare_args(por3_data, first))
    assert proc.returncode == 0, _detail(proc)

    with open(first / "items.csv", encoding="utf-8-sig", newline="") as f:
        items = sorted({row["ITEM"] for row in csv.DictReader(f)})
    assert items
    groups = tmp_path / "groups.csv"
    with open(groups, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ITEM", "GROUP"])
        for i, item in enumerate(items):
            w.writerow([item, "A" if i % 2 == 0 else "B"])

    out = tmp_path / "out"
    proc = run_script(RUN_ALL, [*compare_args(por3_data, out),
                                "--before", first / "items.csv", "--groups", groups])
    assert proc.returncode == 0, _detail(proc)
    assert "[단계 7/7] group_summary" in proc.stdout
    assert (out / "compare" / "compare.csv").is_file()
    assert [p for p in (out / "groups").rglob("*") if p.is_file()]
    assert sorted(p.name for p in (out / "plots").glob("summary_group_*.png")) == [
        "summary_group_A.png", "summary_group_B.png",
    ]


def _planned(tmp_path: Path, *extra: str) -> dict:
    import run_all

    ap = run_all.build_parser()
    a = ap.parse_args(["--por", "p1", "--por", "p2", "--doe", "d", *extra])
    return {name: args for name, args, _ in run_all.plan_steps(ap, a, tmp_path / "out")}


def test_run_all_groups_without_before_passes_groups_to_plot_verdicts(tmp_path: Path):
    groups = str((tmp_path / "g.csv").resolve())
    steps = _planned(tmp_path, "--groups", str(tmp_path / "g.csv"))
    plot = steps["plot_verdicts"]
    assert plot[plot.index("--groups") + 1] == groups
    assert "group_summary" not in steps and "compare_before_after" not in steps

    steps = _planned(tmp_path, "--groups", groups, "--before", str(tmp_path / "b.csv"))
    assert "--groups" in steps["plot_verdicts"] and "group_summary" in steps

    assert "--groups" not in _planned(tmp_path)["plot_verdicts"]


def test_plan_fail_evidence_gets_raw_args_and_log_compare_step(tmp_path: Path):
    import run_all

    ap = run_all.build_parser()
    a = ap.parse_args(["--por", "p1", "--por", "p2", "--doe", "d", "--blank", "b",
                       "--before", str(tmp_path / "b.csv")])
    plan = run_all.plan_steps(ap, a, tmp_path / "out")
    names = [name for name, _, _ in plan]
    steps = {name: args for name, args, _ in plan}

    fe = steps["fail_evidence"]
    assert fe.count("--por") == 2 and "--doe" in fe and "--blank" in fe
    assert fe[fe.index("--doe") + 1] == str(Path("d").resolve())
    assert "--compare" not in fe  # compare 단계가 뒤에 있으니 넘기지 않는다

    assert steps["log_compare"] == ["log_compare.py", str(tmp_path / "out" / "items.csv"),
                                    "--out", str(tmp_path / "out" / "log_compare")]
    assert names.index("summarize") + 1 == names.index("log_compare")


def test_raw_forward_args_drops_unknown_options():
    import run_all

    args = ["--por", "/a", "/b", "--zzz-unknown", "1", "--doe", "/d", "--r", "0.05"]
    assert run_all.raw_forward_args(args) == ["--por", "/a", "/b", "--doe", "/d", "--r", "0.05"]


def test_run_all_stops_at_failed_step(por3_data: Path, tmp_path: Path):
    out = tmp_path / "out"
    proc = run_script(RUN_ALL, compare_args(por3_data, out), {"RUN_ALL_FAIL_STEP": "fail_evidence"})
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, _detail(proc)
    assert "[실패] 단계 4/5 fail_evidence" in combined
    assert "rc=3" in combined
    assert "[단계 5/5]" not in combined
    assert not (out / "plots").exists()
    assert "생성 파일" not in combined
