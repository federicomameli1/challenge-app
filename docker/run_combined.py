from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Iterable, Optional

"""
Run the backend and nginx together in a single container.
"""

CHILDREN: list[subprocess.Popen[str]] = []


def _start_process(command: list[str]) -> subprocess.Popen[str]:
    return subprocess.Popen(command)


def _terminate_children(processes: Iterable[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()

    deadline = time.time() + 10
    for process in processes:
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.1)

    for process in processes:
        if process.poll() is None:
            process.kill()


def _handle_signal(signum: int, _frame: Optional[object]) -> None:
    _terminate_children(CHILDREN)
    sys.exit(128 + signum)


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    backend = _start_process(
        [
            "uvicorn",
            "backend.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            os.getenv("BACKEND_PORT", "8001"),
        ]
    )
    nginx = _start_process(["nginx", "-g", "daemon off;"])

    CHILDREN.extend([backend, nginx])

    while True:
        for process in CHILDREN:
            code = process.poll()
            if code is not None:
                _terminate_children(CHILDREN)
                return code
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
