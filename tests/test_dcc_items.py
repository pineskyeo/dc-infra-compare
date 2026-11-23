"""dcc.py item --items-file (ITEM 목록 파일) 과 judge --detail (판정 뒤 차이·미결 ITEM 분석)."""
import csv
import filecmp
import shutil
from pathlib import Path

import pytest

import dcc
from test_dcc import cfg, make_paths, por3_data, run_dcc, write_config  # noqa: F401  (fixture 재사용)


def _only_arg(cfg: Path, *argv: str) -> str:
    make_paths(cfg.parent.resolve() / "결과" / "A1", "items.csv")
    a = dcc.build_parser().parse_args(["item", "A1", *argv, "--config", str(cfg)])
    steps = dcc.plan("item", dcc.load_config(cfg)["A1"], a)
    assert [name for name, _ in steps] == ["fail_evidence"]
    args = steps[0][1]
    return args[args.index("--only") + 1]


@pytest.mark.parametrize("content, encoding, expected", [
    ("VT_SHIFT\n\n# 주석 줄\nIOFF_LEAK  # 누설\nRON_CONTACT, VT_SAME\n", "utf-8", "VT_SHIFT,IOFF_LEAK,RON_CONTACT,VT_SAME"),
    ("ITEM,메모\nVT_SHIFT,크다\nIOFF_LEAK,\n", "utf-8-sig", "VT_SHIFT,IOFF_LEAK"),
    ("번호,ID,비고\n1,I0003,x\n2,I0001,y\n", "utf-8", "I0003,I0001"),
    ("ID\tITEM\tverdict_final\nI0001\tVT_SHIFT\t차이\nI0002\tVT_SAME\t동등\n", "utf-8", "VT_SHIFT,VT_SAME"),
    ("ITEM,메모\nVT_SHIFT,문턱 전압\nIOFF_LEAK,누설 전류\n", "cp949", "VT_SHIFT,IOFF_LEAK"),
])
def test_items_file_formats(cfg: Path, tmp_path: Path, content: str, encoding: str, expected: str):
    path = tmp_path / "list.txt"
    path.write_bytes(content.encode(encoding))
    assert _only_arg(cfg, "--items-file", str(path)) == expected


def test_items_file_merges_with_positional_and_drops_duplicates(cfg: Path, tmp_path: Path):
    path = tmp_path / "list.csv"
    path.write_text("ITEM\nIOFF_LEAK\nVT_SHIFT\nRON_CONTACT\nIOFF_LEAK\n", encoding="utf-8")
    assert _only_arg(cfg, "VT_SHIFT,VT_SAME", "VT_SAME", "--items-file", str(path)) == \
        "VT_SHIFT,VT_SAME,IOFF_LEAK,RON_CONTACT"


@pytest.mark.parametrize("argv, message", [
    ([], "ITEM 을 주세요"),
    (["--items-file", "없는파일.txt"], "ITEM 목록 파일이 없습니다"),
])
def test_item_without_items_or_with_missing_file_exits_2(cfg: Path, capsys, argv: list[str], message: str):
    assert dcc.main(["item", "A1", *argv, "--config", str(cfg)]) == 2
    assert message in capsys.readouterr().err
    assert not (cfg.parent / "결과").exists()


ITEMS_CSV = [
    ("I0001", "VT_SHIFT", "차이", "차이"),
    ("I0002", "VT_SAME", "동등", "동등"),
    ("I0003", "IOFF_LEAK", "미결", "미결"),
    ("I0004", "BROKEN", "판정 제외", "판정 제외"),
    ("I0005", "RON_CONTACT", "차이", "동등"),
    ("I0006", "VOS_OFFSET", "동등", "미결"),
]


def _fake_runs(monkeypatch, rows) -> list[tuple[str, str, list]]:
    """run_combo 대신: judge 면 items.csv 를 rows 로 쓰고, 호출 (조합, 모드, 단계) 를 기록한다."""
    calls = []

    def fake(c, mode, steps):
        calls.append((c.name, mode, steps))
        if mode == "judge":
            c.out.mkdir(parents=True, exist_ok=True)
            with open(c.items_csv, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ID", "ITEM", "verdict", "verdict_final"])
                w.writerows(rows)
        return None

    monkeypatch.setattr(dcc, "run_combo", fake)
    return calls


def test_judge_detail_selects_verdict_final_diff_and_pending(cfg: Path, monkeypatch, capsys):
    calls = _fake_runs(monkeypatch, ITEMS_CSV)
    assert dcc.main(["judge", "A1", "--detail", "--config", str(cfg)]) == 0
    assert [(n, m) for n, m, _ in calls] == [("A1", "judge"), ("A1", "item"), ("A1", "report")]
    (name, args), = calls[1][2]
    assert name == "fail_evidence"
    assert args[args.index("--only") + 1] == "VT_SHIFT,IOFF_LEAK,VOS_OFFSET"
    assert "차이·미결 ITEM 3개" in capsys.readouterr().out


def test_judge_detail_without_diff_or_pending_skips_item(cfg: Path, monkeypatch, capsys):
    calls = _fake_runs(monkeypatch, [r for r in ITEMS_CSV if r[3] not in ("차이", "미결")])
    assert dcc.main(["judge", "all", "--detail", "--config", str(cfg)]) == 0
    assert [(n, m) for n, m, _ in calls] == [("A1", "judge"), ("A1", "report"), ("B2", "judge"), ("B2", "report")]
    out = capsys.readouterr().out
    assert "[A1] 차이·미결 ITEM 이 없어" in out and "[B2] 차이·미결 ITEM 이 없어" in out


def test_judge_without_detail_runs_no_item(cfg: Path, monkeypatch):
    calls = _fake_runs(monkeypatch, ITEMS_CSV)
    assert dcc.main(["judge", "A1", "--config", str(cfg)]) == 0
    assert [m for _, m, _ in calls] == ["judge", "report"]   # 판정 뒤 리포트만, item 분석 없음


def _por3_config(por3_data: Path, folder: Path) -> Path:
    (por3_data / "empty_doe").mkdir(exist_ok=True)
    return write_config(folder, f"""\
[defaults]
out = 결과
level = {por3_data / "level.csv"}

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


def _item_folders(out: Path) -> list[str]:
    return sorted(d.name.split("_", 1)[1] for d in (out / "item" / "items").iterdir() if not d.name.startswith("."))


def test_end_to_end_judge_all_detail_and_items_file(por3_data: Path, tmp_path: Path):
    path = _por3_config(por3_data, tmp_path / "cfg")
    out = tmp_path / "cfg" / "결과" / "A1"

    proc = run_dcc("judge", "all", "--detail", "--config", path)
    print(proc.stdout)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert proc.stdout.rstrip().endswith("결과\nBAD  실패 (단계 por_doe_compare, rc=1)\nA1  성공")
    with open(out / "items.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    targets = sorted(r["ITEM"] for r in rows if r["verdict_final"] in ("차이", "미결"))
    assert targets and len(targets) < len(rows), [(r["ITEM"], r["verdict_final"]) for r in rows]
    assert _item_folders(out) == targets
    assert f"[A1] 차이·미결 ITEM {len(targets)}개 item 분석" in proc.stdout

    shutil.rmtree(out / "item")
    proc = run_dcc("item", "A1", "VT_SHIFT,IOFF_LEAK,VT_SAME", "--config", path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    by_comma = tmp_path / "by_comma"
    shutil.move(out / "item", by_comma)

    items_file = tmp_path / "볼항목.csv"
    items_file.write_bytes("ITEM,메모\nVT_SHIFT,크다\nIOFF_LEAK,\nVT_SAME,\n".encode("cp949"))
    proc = run_dcc("item", "A1", "--items-file", items_file, "--config", path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    files = sorted(p.relative_to(by_comma) for p in by_comma.rglob("*") if p.is_file())
    assert files == sorted(p.relative_to(out / "item") for p in (out / "item").rglob("*") if p.is_file())
    assert files
    _, mismatch, errors = filecmp.cmpfiles(by_comma, out / "item", [str(f) for f in files], shallow=False)
    assert (mismatch, errors) == ([], [])
