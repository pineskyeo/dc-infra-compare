"""repo 안 스크립트 하나를 별도 프로세스로 실행하는 단계 실행기 (run_all.py, dcc.py 공용)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _env() -> dict:
    env = os.environ.copy()
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + old if old else "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_step(n: int, total: int, name: str, script_args: list[str], *,
             show_cmd: bool = False, fail: bool = False) -> subprocess.CompletedProcess:
    """`[단계 n/total] name` 을 찍고 스크립트를 실행한다. 실패하면 명령, rc, stderr 끝 20줄을 찍는다.
    fail 이면 스크립트 대신 rc=3 으로 끝나는 프로세스를 실행한다 (테스트용)."""
    print(f"[단계 {n}/{total}] {name}", flush=True)
    cmd = [sys.executable, str(ROOT / script_args[0]), *script_args[1:]]
    if show_cmd:
        print(f"  $ {subprocess.list2cmdline(cmd)}", flush=True)
    if fail:
        cmd = [sys.executable, "-c", "import sys; sys.exit(3)"]
    proc = subprocess.run(cmd, cwd=ROOT, env=_env(), check=False, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(f"[실패] 단계 {n}/{total} {name}: {subprocess.list2cmdline(cmd)}")
        print(f"rc={proc.returncode}")
        for line in (proc.stderr or "").splitlines()[-20:]:
            print(line)
        sys.stdout.flush()
    return proc
