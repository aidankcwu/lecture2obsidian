import logging
import os
import signal
import subprocess
import sys
import threading
import traceback
from datetime import date, datetime, time
from pathlib import Path

import click
from dotenv import load_dotenv

# Ensure the project root is on sys.path so `app.*` imports resolve when this
# file is run directly (e.g. `python app/cli.py`) as well as via `python -m app.cli`.
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")

from app.notify import send_notification
from app.recorder import Recorder
from app.state import (
    LOG_FILE,
    STATE_DIR,
    clear_state,
    get_recording_info,
    is_recording,
    write_state,
)
from app.summarize import summarize_transcript
from app.transcribe import check_ffmpeg, transcribe_audio
from app.writer import load_config, write_notes

SUPPORTED_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".webm"}
CONFIG_PATH = _ROOT / "config.yaml"


def _check_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        click.echo(
            "Error: OPENAI_API_KEY is not set.\n"
            "Add it to a .env file in this directory:\n"
            "  echo 'OPENAI_API_KEY=sk-...' > .env"
        )
        sys.exit(1)


def _infer_course(config: dict) -> tuple[str, str]:
    """Return (course, title_prefix) based on the current day and time.

    Checks config["schedule"][weekday] entries, matching if the current time
    falls within the scheduled range ± 15 minutes. Falls back to
    config["default_course"] if no match is found.
    """
    schedule = config.get("schedule", {})
    default_course = config.get("default_course", "Lecture")

    now = datetime.now()
    day_name = now.strftime("%A")  # e.g. "Monday"
    day_schedule = schedule.get(day_name, [])

    buffer_minutes = 15

    for entry in day_schedule:
        time_range = entry.get("time", "")
        try:
            start_str, end_str = time_range.split("-")
            start_h, start_m = map(int, start_str.strip().split(":"))
            end_h, end_m = map(int, end_str.strip().split(":"))
        except (ValueError, AttributeError):
            continue

        start_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

        from datetime import timedelta
        window_start = start_dt - timedelta(minutes=buffer_minutes)
        window_end = end_dt + timedelta(minutes=buffer_minutes)

        if window_start <= now <= window_end:
            return entry.get("course", default_course), entry.get("title_prefix", "Lecture")

    return default_course, "Lecture"


def _archive_wav(wav_path: Path, config: dict) -> None:
    """Move WAV to the configured archive directory, or delete it."""
    archive_dir_str = config.get("recording", {}).get("archive_dir")
    if archive_dir_str:
        archive_dir = Path(archive_dir_str).expanduser()
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / wav_path.name
        wav_path.rename(dest)
    else:
        wav_path.unlink(missing_ok=True)


@click.group()
def cli():
    """lecture-to-obsidian: turn lecture audio into Obsidian notes."""


# ---------------------------------------------------------------------------
# process — batch mode (existing command, updated imports)
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("audio_file", type=click.Path(exists=False))
@click.option("--title", default=None, help="Note title (defaults to filename stem)")
@click.option("--course", default=None, help="Course code/name added as a tag")
@click.option(
    "--date",
    "note_date",
    default=None,
    help="Date in YYYY-MM-DD format (defaults to today)",
)
def process(audio_file: str, title: str | None, course: str | None, note_date: str | None):
    """Transcribe AUDIO_FILE and write structured notes to your Obsidian vault."""
    audio_path = Path(audio_file)
    if not audio_path.exists():
        click.echo(f"Error: File not found: {audio_path}")
        sys.exit(1)
    if audio_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        click.echo(
            f"Error: Unsupported file type '{audio_path.suffix}'.\n"
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
        sys.exit(1)

    check_ffmpeg()
    _check_api_key()

    config = load_config(CONFIG_PATH)
    resolved_title = title or audio_path.stem
    resolved_date = note_date or str(date.today())
    model = config.get("summarization", {}).get("model", "gpt-4o-mini")

    click.echo(f"Transcribing {audio_path.name}...")
    transcript = transcribe_audio(audio_path, config)
    click.echo(f"  Done. Transcript is {len(transcript.split()):,} words.")

    click.echo("Summarizing transcript...")
    summary = summarize_transcript(transcript, title=resolved_title, course=course, model=model)
    click.echo("  Done.")

    click.echo("Writing notes to vault...")
    summary_path, transcript_path = write_notes(
        summary=summary,
        transcript=transcript,
        title=resolved_title,
        course=course,
        date=resolved_date,
        config=config,
    )

    click.echo("\nDone!")
    click.echo(f"  Summary note:   {summary_path}")
    click.echo(f"  Raw transcript: {transcript_path}")


# ---------------------------------------------------------------------------
# toggle — start or stop a live recording
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--course", default=None, help="Course code/name (overrides schedule detection)")
@click.option("--title", default=None, help="Note title prefix (overrides schedule detection)")
@click.option("--date", "note_date", default=None, help="Date in YYYY-MM-DD format")
def toggle(course: str | None, title: str | None, note_date: str | None):
    """Start or stop a live lecture recording.

    First call starts recording in the background.
    Second call stops recording and runs the full pipeline.
    """
    if is_recording():
        info = get_recording_info()
        pid = info["pid"]
        course_name = info.get("course", "lecture")
        try:
            os.kill(pid, signal.SIGTERM)
            click.echo(f"Stopping recording for {course_name} (PID {pid})...")
            click.echo("Transcription and summarization running in background.")
            click.echo(f"Check {LOG_FILE} for progress. You'll get a notification when done.")
        except ProcessLookupError:
            click.echo("Recording process not found — clearing stale state.")
            clear_state()
        return

    # Not recording — start
    config = load_config(CONFIG_PATH)
    resolved_date = note_date or str(date.today())

    if course and title:
        resolved_course, resolved_title = course, title
    else:
        inferred_course, inferred_title = _infer_course(config)
        resolved_course = course or inferred_course
        resolved_title = title or f"{inferred_title} {resolved_date}"

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_FILE, "a")

    cmd = [
        sys.executable, "-m", "app.cli", "_record",
        "--course", resolved_course,
        "--title", resolved_title,
        "--date", resolved_date,
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(_ROOT),
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )

    write_state(
        pid=proc.pid,
        course=resolved_course,
        title=resolved_title,
        date=resolved_date,
    )

    click.echo(f"Recording started for {resolved_course} (PID {proc.pid})")
    click.echo(f"  Title: {resolved_title}")
    click.echo(f"  Log:   {LOG_FILE}")


# ---------------------------------------------------------------------------
# status — show current recording state
# ---------------------------------------------------------------------------

@cli.command()
def status():
    """Show whether a recording is currently active."""
    if not is_recording():
        click.echo("No active recording.")
        return

    info = get_recording_info()
    course = info.get("course", "Unknown")
    title = info.get("title", "Unknown")
    start_time_str = info.get("start_time", "")

    elapsed_str = ""
    if start_time_str:
        try:
            start_dt = datetime.fromisoformat(start_time_str)
            elapsed = datetime.now() - start_dt
            total_seconds = int(elapsed.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            elapsed_str = f" — {minutes}m {seconds:02d}s elapsed"
        except ValueError:
            pass

    click.echo(f"Recording {course}{elapsed_str}")
    click.echo(f"  Title: {title}")
    click.echo(f"  PID:   {info.get('pid')}")


# ---------------------------------------------------------------------------
# _record — internal command run in the background subprocess
# ---------------------------------------------------------------------------

@cli.command(name="_record", hidden=True)
@click.option("--course", required=True)
@click.option("--title", required=True)
@click.option("--date", "note_date", required=True)
def record_internal(course: str, title: str, note_date: str):
    """Internal: capture audio until SIGTERM, then run the full pipeline."""
    # Set up logging to stdout (which is redirected to LOG_FILE by the parent)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    log = logging.getLogger("lecture2obs")

    stop_event = threading.Event()

    def handle_sigterm(signum, frame):
        log.info("SIGTERM received — stopping recording.")
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_sigterm)

    log.info(f"Starting recorder for course={course!r} title={title!r}")
    recorder = Recorder()
    try:
        recorder.start()
    except Exception as exc:
        log.error(f"Failed to start recorder: {exc}")
        send_notification("❌ lecture-to-obsidian", f"Mic error: {exc}")
        clear_state()
        sys.exit(1)

    log.info("Recording... waiting for SIGTERM.")
    stop_event.wait()

    # --- Pipeline ---
    wav_path: Path | None = None
    try:
        log.info("Stopping recorder and saving WAV...")
        wav_path = recorder.stop()
        log.info(f"WAV saved: {wav_path}")

        config = load_config(CONFIG_PATH)
        model = config.get("summarization", {}).get("model", "gpt-4o-mini")

        log.info("Transcribing...")
        transcript = transcribe_audio(wav_path, config)
        log.info(f"Transcript: {len(transcript.split())} words")

        log.info("Summarizing...")
        summary = summarize_transcript(transcript, title=title, course=course, model=model)
        log.info("Summarization complete.")

        log.info("Writing notes to vault...")
        summary_path, transcript_path = write_notes(
            summary=summary,
            transcript=transcript,
            title=title,
            course=course,
            date=note_date,
            config=config,
        )
        log.info(f"Summary:    {summary_path}")
        log.info(f"Transcript: {transcript_path}")

        _archive_wav(wav_path, config)

        send_notification(
            "✅ lecture-to-obsidian",
            f"{course} notes ready in Inbox",
        )
        log.info("Done.")

    except Exception:
        log.error("Pipeline failed:\n" + traceback.format_exc())
        if wav_path and wav_path.exists():
            log.info(f"WAV preserved at: {wav_path}")
        send_notification(
            "❌ lecture-to-obsidian",
            f"Pipeline failed — check {LOG_FILE}",
        )
        clear_state()
        sys.exit(1)

    clear_state()


# ---------------------------------------------------------------------------
# init — interactive setup
# ---------------------------------------------------------------------------

@cli.command()
def init():
    """Interactively create a config.yaml for your Obsidian vault."""
    click.echo("Setting up lecture-to-obsidian configuration.\n")

    vault_path = click.prompt(
        "Obsidian vault path (absolute path)",
        default=str(Path.home() / "Documents" / "ObsidianVault"),
    )
    inbox_folder = click.prompt("Inbox folder", default="1 - Inbox")
    source_folder = click.prompt(
        "Source materials folder", default="2 - Source Materials/Lectures"
    )
    model = click.prompt("Summarization model", default="gpt-4o-mini")
    tag_style = click.prompt(
        "Tag style",
        default="wikilink",
        type=click.Choice(["wikilink", "hashtag"]),
    )
    transcription_backend = click.prompt(
        "Transcription backend",
        default="local",
        type=click.Choice(["local", "api"]),
    )
    local_model = "base.en"
    if transcription_backend == "local":
        local_model = click.prompt(
            "Local Whisper model",
            default="base.en",
            type=click.Choice(["tiny.en", "base.en", "small.en", "medium.en"]),
        )
    archive_dir = click.prompt(
        "Archive directory for recorded WAV files (leave blank to delete after processing)",
        default="",
    )

    config_lines = [
        f'vault:\n  path: "{vault_path}"\n'
        f'  inbox_folder: "{inbox_folder}"\n'
        f'  source_folder: "{source_folder}"\n',
        f'summarization:\n  model: "{model}"\n  max_section_length: 500\n',
        f'note_template:\n  status: "#review"\n  tag_style: "{tag_style}"\n',
        f'transcription:\n  backend: "{transcription_backend}"\n  local_model: "{local_model}"\n',
    ]
    if archive_dir:
        config_lines.append(f'recording:\n  archive_dir: "{archive_dir}"\n')

    config_lines.append(
        "# Uncomment and edit to enable schedule-based course detection:\n"
        "# schedule:\n"
        "#   Monday:\n"
        "#     - time: \"09:00-10:15\"\n"
        "#       course: \"CS 301\"\n"
        "#       title_prefix: \"Data Structures\"\n"
        "# default_course: \"Lecture\"\n"
    )

    config_content = "\n".join(config_lines)

    config_path = CONFIG_PATH
    if config_path.exists():
        if not click.confirm(f"\nconfig.yaml already exists. Overwrite?"):
            click.echo("Aborted.")
            return

    config_path.write_text(config_content, encoding="utf-8")
    click.echo(f"\nConfig written to {config_path}")
    click.echo("\nNext steps:")
    click.echo("  1. Add your OpenAI API key:  echo 'OPENAI_API_KEY=sk-...' > .env")
    click.echo("  2. Toggle a recording:        python -m app.cli toggle")
    click.echo("  3. Check status:              python -m app.cli status")


if __name__ == "__main__":
    cli()
