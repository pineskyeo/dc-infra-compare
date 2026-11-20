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
    assert "[단계 4/4] plot_verdicts" in proc.stdout
    assert "생성 파일" in proc.stdout
    assert "items.csv" in proc.stdout


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
    assert "[단계 6/6] group_summary" in proc.stdout
    assert (out / "compare" / "compare.csv").is_file()
    assert [p for p in (out / "groups").rglob("*") if p.is_file()]


def test_run_all_groups_requires_before(por3_data: Path, tmp_path: Path):
    proc = run_script(RUN_ALL, [*compare_args(por3_data, tmp_path / "out"), "--groups", tmp_path / "g.csv"])
    assert proc.returncode != 0
    assert "--before" in proc.stderr


def test_run_all_stops_at_failed_step(por3_data: Path, tmp_path: Path):
    out = tmp_path / "out"
    proc = run_script(RUN_ALL, compare_args(por3_data, out), {"RUN_ALL_FAIL_STEP": "fail_evidence"})
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, _detail(proc)
    assert "[실패] 단계 3/4 fail_evidence" in combined
    assert "rc=3" in combined
    assert "[단계 4/4]" not in combined
    assert not (out / "plots").exists()
    assert "생성 파일" not in combined
