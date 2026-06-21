"""Supervisor — relaunches scripts/run_live.py automatically on /restart.

Mirrors the previous bot's convention: when run_live.py exits with code 42
(triggered by Telegram /restart), the supervisor re-spawns it. Any other
exit code (0 = clean stop, non-zero non-42 = crash) is respected and the
supervisor exits too.

Run from the repo root:

    .venv\\Scripts\\python scripts/supervisor.py --dry-run
    .venv\\Scripts\\python scripts/supervisor.py --confirm LIVE

Forwards every argument after the supervisor flags to the child process.
"""

from __future__ import annotations

import io
import signal as os_signal
import subprocess
import sys
import time
from pathlib import Path

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

RESTART_EXIT_CODE = 42
COOLDOWN_SEC = 3
MAX_CONSECUTIVE_CRASHES = 5         # safety: stop if it crashes too often
CRASH_WINDOW_SEC = 600              # 5 crashes in 10 min = halt

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_LIVE = REPO_ROOT / "scripts" / "run_live.py"
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def main(argv: list[str]) -> int:
    child_argv = argv[1:]  # drop supervisor's own script name
    if not PYTHON.exists():
        print(f"[supervisor] python interpreter not found at {PYTHON}",
              file=sys.stderr)
        return 1
    if not RUN_LIVE.exists():
        print(f"[supervisor] run_live.py not found at {RUN_LIVE}",
              file=sys.stderr)
        return 1

    print(f"[supervisor] starting; child argv = {child_argv}")
    crash_times: list[float] = []
    current: subprocess.Popen | None = None  # type: ignore[type-arg]

    def _forward_sigint(_signum, _frame) -> None:  # type: ignore[no-untyped-def]
        print("[supervisor] SIGINT — forwarding to child and exiting")
        if current is not None and current.poll() is None:
            try:
                current.send_signal(os_signal.SIGINT)
                current.wait(timeout=15)
            except Exception:
                current.kill()
        sys.exit(0)

    os_signal.signal(os_signal.SIGINT, _forward_sigint)

    while True:
        cmd = [str(PYTHON), str(RUN_LIVE), *child_argv]
        print(f"[supervisor] spawn: {' '.join(cmd)}")
        current = subprocess.Popen(cmd, cwd=str(REPO_ROOT))
        try:
            rc = current.wait()
        except KeyboardInterrupt:
            _forward_sigint(None, None)
            return 0
        print(f"[supervisor] child exited with code {rc}")

        if rc == 0:
            print("[supervisor] clean stop. exiting.")
            return 0
        if rc == RESTART_EXIT_CODE:
            print(f"[supervisor] restart requested (code {RESTART_EXIT_CODE}). "
                  f"relaunching in {COOLDOWN_SEC}s.")
            time.sleep(COOLDOWN_SEC)
            continue

        # Any other non-zero exit = crash. Apply crash budget.
        now = time.time()
        crash_times.append(now)
        crash_times = [t for t in crash_times if now - t <= CRASH_WINDOW_SEC]
        if len(crash_times) >= MAX_CONSECUTIVE_CRASHES:
            print(f"[supervisor] {len(crash_times)} crashes in "
                  f"{CRASH_WINDOW_SEC}s — halting to avoid restart loop.",
                  file=sys.stderr)
            return 2
        print(f"[supervisor] crash #{len(crash_times)} of "
              f"{MAX_CONSECUTIVE_CRASHES} in window. relaunching "
              f"in {COOLDOWN_SEC}s.")
        time.sleep(COOLDOWN_SEC)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
