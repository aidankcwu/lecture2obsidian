import subprocess


def send_notification(title: str, message: str) -> None:
    """Send a macOS notification via osascript.

    Silently ignores any errors — notifications are non-critical.
    """
    script = f'display notification "{message}" with title "{title}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass
