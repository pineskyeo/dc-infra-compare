"""dcc.py: 설정 파일 읽기, 모드별 단계, judge all, 합성 데이터로 judge·item·group 전체 실행."""
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import dcc

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "examples" / "make_por3_data.py"


def write_config(folder: Path, text: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "combos.ini"
    path.write_text(text, encoding="utf-8")
    return path


def make_paths(base: Path, *names: str) -> None:
    for name in names:
        p = base / name
        if p.suffix:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n", encoding="utf-8")
        else:
            p.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def cfg(tmp_path: Path) -> Path:
    base = tmp_path / "cfg"
    make_paths(base, "A/POR1", "A/POR2", "A/POR3", "A/DOE", "B/POR1", "B/POR2", "B/DOE",
               "item_info.csv", "item_info_B.csv", "groups.csv", "blank1", "blank2")
    return write_config(base, """\
[defaults]
out = 결과
level = item_info.csv
groups = groups.csv

[A1]
por = A/POR1
      A/POR2
      A/POR3
doe = A/DOE

[B2]
por = B/POR1
      B/POR2
doe = B/DOE
level = item_info_B.csv
blank = blank1
        blank2
r = 0.1
key = WAFERID,ITEM
""")


def run_dcc(*args, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run([sys.executable, str(ROOT / "dcc.py"), *map(str, args)], cwd=cwd, env=env,
                          check=False, capture_output=True, text=True, encoding="utf-8")


def test_defaults_merge_relative_paths_and_override(cfg: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = cfg.parent.resolve()
    combos = dcc.load_config(cfg)
    assert list(combos) == ["A1", "B2"]
    a1, b2 = combos["A1"], combos["B2"]
    assert a1.por == (base / "A/POR1", base / "A/POR2", base / "A/POR3")
    assert a1.doe == base / "A/DOE"
    assert a1.level == base / "item_info.csv"
    assert a1.groups == b2.groups == base / "groups.csv"
    assert a1.out == base / "결과" / "A1" and b2.out == base / "결과" / "B2"
    assert b2.level == base / "item_info_B.csv"
    assert b2.blank == (base / "blank1", base / "blank2")
    assert (b2.r, b2.key, a1.r, a1.key, a1.encoding) == (0.1, "WAFERID,ITEM", None, None, None)


@pytest.mark.parametrize("text, message", [
    ("[A1]\npor = p1\ndoe = d\n", "POR 은 2회 이상"),
    ("[A1]\npor = p1\n  p2\n", "doe 가 없습니다"),
    ("[A1]\npor = p1\n  p2\ndoe = d\nlevl = x\n", "모르는 키: levl"),
    ("[defaults]\nzzz = 1\n[A1]\npor = p1\n  p2\ndoe = d\n", "[defaults] 모르는 키: zzz"),
    ("[A1]\npor = p1\n  p2\ndoe = d\nr = abc\n", "r 은 숫자"),
    ("[all]\npor = p1\n  p2\ndoe = d\n", "'all' 은 쓸 수 없습니다"),
    ("[A1]\npor = p1\n  p2\ndoe = d\n[A1]\npor = p1\n", "형식 오류"),
])
def test_config_errors_exit_2(tmp_path: Path, capsys, text: str, message: str):
    make_paths(tmp_path, "p1", "p2", "d")
    path = write_config(tmp_path, text)
    assert dcc.main(["judge", "A1", "--config", str(path)]) == 2
    assert message in capsys.readouterr().err


def test_unknown_name_lists_known_names(cfg: Path, capsys):
    assert dcc.main(["judge", "C3", "--config", str(cfg)]) == 2
    assert "모르는 조합 이름: C3 (있는 이름: A1, B2)" in capsys.readouterr().err


def test_missing_config_file(tmp_path: Path, capsys):
    assert dcc.main(["list", "--config", str(tmp_path / "none.ini")]) == 2
    assert "설정 파일이 없습니다" in capsys.readouterr().err


def test_missing_path_checked_before_running(cfg: Path, capsys):
    shutil.rmtree(cfg.parent / "B" / "DOE")
    assert dcc.main(["judge", "all", "--config", str(cfg)]) == 2
    err = capsys.readouterr().err
    assert "[B2] 없는 경로" in err and str((cfg.parent / "B" / "DOE").resolve()) in err
    assert not (cfg.parent / "결과").exists()


def test_group_without_groups_file(tmp_path: Path, capsys):
    make_paths(tmp_path, "p1", "p2", "d")
    path = write_config(tmp_path, "[A1]\npor = p1\n  p2\ndoe = d\n")
    assert dcc.main(["group", "A1", "--config", str(path)]) == 2
    assert "groups 파일이 없습니다" in capsys.readouterr().err


def _plan(cfg: Path, *argv: str) -> list[tuple[str, list[str]]]:
    a = dcc.build_parser().parse_args([*argv, "--config", str(cfg)])
    c = dcc.load_config(cfg)[a.name]
    return dcc.plan(a.cmd, c, a)


def test_plan_judge(cfg: Path):
    base = cfg.parent.resolve()
    out = base / "결과" / "B2"
    raw = ["--por", str(base / "B/POR1"), "--por", str(base / "B/POR2"), "--doe", str(base / "B/DOE"), "--r", "0.1",
           "--level", str(base / "item_info_B.csv"), "--blank", str(base / "blank1"), str(base / "blank2"),
           "--key", "WAFERID,ITEM"]
    assert _plan(cfg, "judge", "B2") == [
        ("por_doe_compare", ["por_doe_compare.py", *raw, "--groups", str(base / "groups.csv"), "--out", str(out)]),
        ("review", ["review.py", "--input", str(out / "items.csv"), "--out", str(out), *raw]),
        ("plot_verdicts", ["plot_verdicts.py", "--items-csv", str(out / "items.csv"), "--summary",
                           "--out", str(out / "plots")]),
        ("loq_check", ["loq_check.py", "--input", str(out / "items.csv"), "--out", str(out), *raw]),
    ]


def test_plan_judge_passes_groups_and_scales_when_scales_set(cfg: Path):
    base = cfg.parent.resolve()
    make_paths(base, "scales.csv")
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("groups = groups.csv\n",
                                                           "groups = groups.csv\nscales = scales.csv\n"),
                   encoding="utf-8")
    assert dcc.load_config(cfg)["A1"].scales == base / "scales.csv"
    args = _plan(cfg, "judge", "A1")[0][1]
    assert args[-6:] == ["--groups", str(base / "groups.csv"), "--scales", str(base / "scales.csv"),
                         "--out", str(base / "결과" / "A1")]


def test_scales_without_groups_is_a_config_error(tmp_path: Path, capsys):
    make_paths(tmp_path, "p1", "p2", "d", "scales.csv")
    path = write_config(tmp_path, "[A1]\npor = p1\n  p2\ndoe = d\nscales = scales.csv\n")
    assert dcc.main(["judge", "A1", "--config", str(path)]) == 2
    assert "scales 에는 groups 가 필요합니다" in capsys.readouterr().err


def test_plan_judge_passes_groups_once_with_scales_and_abs_tol(cfg: Path):
    base = cfg.parent.resolve()
    make_paths(base, "scales.csv", "abs.csv")
    cfg.write_text(cfg.read_text(encoding="utf-8").replace(
        "groups = groups.csv\n", "groups = groups.csv\nscales = scales.csv\nabs_tol = abs.csv\n"), encoding="utf-8")
    args = _plan(cfg, "judge", "A1")[0][1]
    assert args[-8:] == ["--groups", str(base / "groups.csv"), "--scales", str(base / "scales.csv"),
                         "--abs-tol", str(base / "abs.csv"), "--out", str(base / "결과" / "A1")]


def test_abs_tol_without_groups_is_a_config_error(tmp_path: Path, capsys):
    make_paths(tmp_path, "p1", "p2", "d", "abs.csv")
    path = write_config(tmp_path, "[A1]\npor = p1\n  p2\ndoe = d\nabs_tol = abs.csv\n")
    assert dcc.main(["judge", "A1", "--config", str(path)]) == 2
    assert "abs_tol 에는 groups 가 필요합니다" in capsys.readouterr().err


def test_plan_loq_runs_check_then_its_own_report(cfg: Path):
    base = cfg.parent.resolve()
    out = base / "결과" / "A1"
    names = [n for n, _ in _plan(cfg, "loq", "A1")]
    assert names == ["por_doe_compare", "review", "plot_verdicts", "loq_check", "report"], "판정 단계의 loq_check 를 두 번 돌리지 않음"
    make_paths(out, "items.csv")
    (check, check_args), (report, report_args) = _plan(cfg, "loq", "A1", "--anon")
    assert (check, report) == ("loq_check", "report")
    assert check_args[:5] == ["loq_check.py", "--input", str(out / "items.csv"), "--out", str(out)]
    assert report_args[-1] == "--anon"


def test_plan_classes_runs_judge_only_without_items_csv(cfg: Path):
    base = cfg.parent.resolve()
    out = base / "결과" / "A1"
    assert [n for n, _ in _plan(cfg, "classes", "A1")] == ["por_doe_compare", "review", "plot_verdicts", "loq_check", "classes"]
    make_paths(out, "items.csv")
    (name, args), = _plan(cfg, "classes", "A1")
    assert name == "classes"
    assert args[:7] == ["classes.py", "--input", str(out / "items.csv"), "--out", str(out / "classes"),
                        "--groups", str(base / "groups.csv")]
    assert args[7:9] == ["--por", str(base / "A/POR1")]


def test_plan_item_and_group_run_judge_only_without_items_csv(cfg: Path):
    base = cfg.parent.resolve()
    out = base / "결과" / "A1"
    raw = ["--por", str(base / "A/POR1"), "--por", str(base / "A/POR2"), "--por", str(base / "A/POR3"),
           "--doe", str(base / "A/DOE"), "--level", str(base / "item_info.csv")]
    items = str(out / "items.csv")

    assert [n for n, _ in _plan(cfg, "item", "A1", "X1,X2")] == [
        "por_doe_compare", "review", "plot_verdicts", "loq_check", "fail_evidence"]
    make_paths(out, "items.csv")
    assert _plan(cfg, "item", "A1", "X1,X2") == [
        ("fail_evidence", ["fail_evidence.py", "--input", items, "--out", str(out / "item"),
                           "--only", "X1,X2", *raw]),
    ]
    assert _plan(cfg, "item", "A1", "X1", "X2", "--plots")[1] == (
        "plot_verdicts", ["plot_verdicts.py", "--items-csv", items, "--no-summary", "--detail",
                          "--items", "X1,X2", "--out", str(out / "item" / "plots"), *raw])

    groups = str(base / "groups.csv")
    group_plot = ("plot_verdicts", ["plot_verdicts.py", "--items-csv", items, "--summary", "--groups", groups,
                                    "--out", str(out / "group" / "plots")])
    assert _plan(cfg, "group", "A1") == [group_plot]
    before = base / "A" / "before.csv"
    make_paths(base, "A/before.csv")
    compare = [
        ("compare_before_after", ["compare_before_after.py", "compare", str(before), items, "--groups", groups,
                                  "-o", str(out / "compare")]),
        ("group_summary", ["group_summary.py", "--compare", str(out / "compare" / "compare.csv"),
                           "--out", str(out / "compare" / "groups")]),
    ]
    assert _plan(cfg, "group", "A1", "--before", str(before)) == [group_plot, *compare]
    assert _plan(cfg, "compare", "A1", "--before", str(before)) == compare


def test_plan_compare_before_from_flag_or_combo_key(cfg: Path, capsys):
    base = cfg.parent.resolve()
    out = base / "결과" / "A1"
    make_paths(out, "items.csv")
    make_paths(base, "old/items.csv", "flag/items.csv")
    assert dcc.main(["compare", "A1", "--config", str(cfg)]) == 2
    assert "기존 결과가 없습니다: --before" in capsys.readouterr().err
    assert dcc.main(["compare", "A1", "--before", str(base / "none.csv"), "--config", str(cfg)]) == 2
    assert "기존 결과 파일이 없습니다" in capsys.readouterr().err

    cfg.write_text(cfg.read_text(encoding="utf-8").replace("doe = A/DOE\n", "doe = A/DOE\nbefore = old/items.csv\n"),
                   encoding="utf-8")
    steps = _plan(cfg, "compare", "A1")
    assert steps[0][1][1:3] == ["compare", str(base / "old" / "items.csv")]
    assert _plan(cfg, "compare", "A1", "--before", str(base / "flag" / "items.csv"))[0][1][2] == \
        str(base / "flag" / "items.csv")
    assert [n for n, _ in _plan(cfg, "group", "A1")] == ["plot_verdicts", "compare_before_after", "group_summary"]


def test_plan_compare_without_groups_skips_group_summary(tmp_path: Path):
    make_paths(tmp_path, "p1", "p2", "d", "old.csv", "out/A1/items.csv")
    path = write_config(tmp_path, "[A1]\npor = p1\n  p2\ndoe = d\nout = out\nbefore = old.csv\n")
    a = dcc.build_parser().parse_args(["compare", "A1", "--config", str(path)])
    steps = dcc.plan("compare", dcc.load_config(path)["A1"], a)
    assert steps == [("compare_before_after", ["compare_before_after.py", "compare", str(tmp_path / "old.csv"),
                                               str(tmp_path / "out" / "A1" / "items.csv"),
                                               "-o", str(tmp_path / "out" / "A1" / "compare")])]


@pytest.fixture(scope="module")
def por3_data(tmp_path_factory) -> Path:
    data = tmp_path_factory.mktemp("dcc") / "por3"
    proc = subprocess.run([sys.executable, str(GENERATOR), str(data)], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return data


def test_end_to_end_judge_all_item_group(por3_data: Path, tmp_path: Path):
    (por3_data / "empty_doe").mkdir(exist_ok=True)
    with open(por3_data / "groups.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ITEM", "GROUP"])
        w.writerows([["VT_SAME", "A"], ["VT_SHIFT", "B"], ["RON_CONTACT", "A"]])
    path = write_config(tmp_path / "cfg", f"""\
[defaults]
out = 결과
level = {por3_data / "level.csv"}
groups = {por3_data / "groups.csv"}

[BAD]
por = {por3_data / "por_run1"}
      {por3_data / "por_run2"}
doe = {por3_data / "empty_doe"}

[A1]
por = {por3_data / "por_run1"}
      {por3_data / "por_run2"}
      {por3_data / "por_run3"}
doe = {por3_data / "doe"}
blank = {por3_data / "blank"}
blank_map = {por3_data / "blank_map.csv"}
""")
    out = tmp_path / "cfg" / "결과" / "A1"

    proc = run_dcc("list", cwd=path.parent)
    assert proc.returncode == 0, proc.stderr
    assert [line.split()[:2] for line in proc.stdout.splitlines()[1:]] == [["BAD", "2"], ["A1", "3"]]
    print(proc.stdout)

    proc = run_dcc("judge", "all", "--config", path)
    print(proc.stdout)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "[실패] 단계 1/4 por_doe_compare" in proc.stdout
    assert proc.stdout.rstrip().endswith("결과\nBAD  실패 (단계 por_doe_compare, rc=1)\nA1  성공")
    assert (out / "items.csv").is_file() and (out / "plots" / "summary.png").is_file()
    assert (out / "review" / "loq_review.csv").is_file() and (out / "review" / "log_review.png").is_file()
    assert "[단계 1/1] report" in proc.stdout and (out / "report.html").is_file()

    proc = run_dcc("item", "A1", "VT_SHIFT,VT_SAME", "--plots", "--config", path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "por_doe_compare" not in proc.stdout
    item_dirs = [d.name for d in (out / "item" / "items").iterdir() if not d.name.startswith(".")]
    assert sorted(name.split("_", 1)[1] for name in item_dirs) == ["VT_SAME", "VT_SHIFT"], item_dirs
    assert list((out / "item" / "plots").rglob("*.png"))
    assert (out / "item" / "report.html").is_file()

    before = tmp_path / "before.csv"
    shutil.copy(out / "items.csv", before)
    proc = run_dcc("group", "A1", "--before", before, "--config", path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[단계 3/3] group_summary" in proc.stdout
    assert sorted(p.name for p in (out / "group" / "plots").glob("summary_group_*.png"))[:2] == [
        "summary_group_A.png", "summary_group_B.png"]
    assert (out / "compare" / "compare.csv").is_file()
    assert (out / "compare" / "groups" / "group_summary.csv").is_file()
    assert (out / "compare" / "report.html").is_file() and (out / "compare" / "비교.xlsx").is_file()
    assert sorted(p.name for p in (out / "group").iterdir()) == ["plots", "report.html"]

    proc = run_dcc("compare", "A1", "--before", before, "--config", path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[단계 2/2] group_summary" in proc.stdout and "[단계 1/1] report" in proc.stdout
    assert "그룹 파일(--groups)을 주지 않아" not in (out / "group" / "report.html").read_text(encoding="utf-8")

    named = (out / "report.html").read_text(encoding="utf-8")
    proc = run_dcc("report", "A1", "--anon", "--config", path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "por_doe_compare" not in proc.stdout
    anon = (out / "report_anon.html").read_text(encoding="utf-8")
    assert "VT_SHIFT" not in anon and "VT_SHIFT" in named
    assert (out / "report.html").read_text(encoding="utf-8") == named   # 익명본이 실명본을 덮지 않는다
    assert (out / "item" / "report_anon.html").is_file() and (out / "group" / "report_anon.html").is_file()
