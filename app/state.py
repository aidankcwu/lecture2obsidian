import os
from datetime import datetime
from pathlib import Path

import yaml

STATE_DIR = Path.home() / ".lecture-to-obsidian"
STATE_FILE = STATE_DIR / "recording.pid"
LOG_FILE = STATE_DIR / "record.log"


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def is_recording() -> bool:
    """Return True if a recording process is currently running.

    Checks that the PID file exists and that the process with that PID is
    actually alive. Clears a stale PID file if the process is dead.
    """
    if not STATE_FILE.exists():
        return False
    info = get_recording_info()
    if info is None:
        return False
    pid = info.get("pid")
    if pid is None:
        clear_state()
        return False
    try:
        os.kill(pid, 0)  # Signal 0 just checks if process exists
        return True
    except ProcessLookupError:
        clear_state()
        return False
    except PermissionError:
        # Process exists but owned by another user — treat as running
        return True


def get_recording_info() -> dict | None:
    """Return the recording state dict, or None if no state file exists."""
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def write_state(pid: int, course: str, title: str, date: str) -> None:
    """Write a new recording state file."""
    _ensure_state_dir()
    state = {
        "pid": pid,
        "course": course,
        "title": title,
        "date": date,
        "start_time": datetime.now().isoformat(),
    }
    with open(STATE_FILE, "w") as f:
        yaml.dump(state, f)


def clear_state() -> None:
    """Remove the recording state file if it exists."""
    STATE_FILE.unlink(missing_ok=True)
