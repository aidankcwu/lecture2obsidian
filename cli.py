import os
import sys
from datetime import date
from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env from the project directory before importing modules that need the API key
load_dotenv()

from transcribe import check_ffmpeg, transcribe_audio
from summarize import summarize_transcript
from writer import load_config, write_notes

SUPPORTED_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".webm"}
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _check_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        click.echo(
            "Error: OPENAI_API_KEY is not set.\n"
            "Add it to a .env file in this directory:\n"
            "  echo 'OPENAI_API_KEY=sk-...' > .env"
        )
        sys.exit(1)


@click.group()
def cli():
    """Convert lecture audio recordings into structured Obsidian notes."""


@cli.command()
@click.argument("audio_file", type=click.Path(exists=False))
@click.option("--title", default=None, help="Note title (defaults to filename stem)")
@click.option("--course", default=None, help="Course code/name added as a tag (e.g. COMP182)")
@click.option(
    "--date",
    "note_date",
    default=None,
    help="Date for the note header in YYYY-MM-DD format (defaults to today)",
)
def process(audio_file: str, title: str | None, course: str | None, note_date: str | None):
    """Transcribe AUDIO_FILE and write structured notes to your Obsidian vault."""
    # Validate audio file
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

    # Check prerequisites
    check_ffmpeg()
    _check_api_key()

    # Load config
    config = load_config(CONFIG_PATH)

    # Resolve defaults
    resolved_title = title or audio_path.stem
    resolved_date = note_date or str(date.today())

    model = config.get("summarization", {}).get("model", "gpt-4o-mini")

    # Step 1: Transcribe
    click.echo(f"Transcribing {audio_path.name}...")
    transcript = transcribe_audio(audio_path)
    click.echo(f"  Done. Transcript is {len(transcript.split()):,} words.")

    # Step 2: Summarize
    click.echo("Summarizing transcript...")
    summary = summarize_transcript(transcript, title=resolved_title, course=course, model=model)
    click.echo("  Done.")

    # Step 3: Write to vault
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
    click.echo(f"  Summary note:  {summary_path}")
    click.echo(f"  Raw transcript: {transcript_path}")


@cli.command()
def init():
    """Interactively create a config.yaml for your Obsidian vault."""
    click.echo("Setting up lecture-to-obsidian configuration.\n")

    vault_path = click.prompt(
        "Obsidian vault path (absolute path)",
        default=str(Path.home() / "Documents" / "ObsidianVault"),
    )
    inbox_folder = click.prompt(
        "Inbox folder (where summary notes go)",
        default="1 - Inbox",
    )
    source_folder = click.prompt(
        "Source materials folder (where raw transcripts go)",
        default="2 - Source Materials/Lectures",
    )
    model = click.prompt(
        "Summarization model",
        default="gpt-4o-mini",
    )
    tag_style = click.prompt(
        "Tag style for course tags",
        default="wikilink",
        type=click.Choice(["wikilink", "hashtag"]),
    )

    config_content = (
        f"vault:\n"
        f"  path: \"{vault_path}\"\n"
        f"  inbox_folder: \"{inbox_folder}\"\n"
        f"  source_folder: \"{source_folder}\"\n"
        f"\n"
        f"summarization:\n"
        f"  model: \"{model}\"\n"
        f"  max_section_length: 500\n"
        f"\n"
        f"note_template:\n"
        f"  status: \"#review\"\n"
        f"  tag_style: \"{tag_style}\"\n"
    )

    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        if not click.confirm(f"\nconfig.yaml already exists. Overwrite?"):
            click.echo("Aborted.")
            return

    config_path.write_text(config_content, encoding="utf-8")
    click.echo(f"\nConfig written to {config_path}")
    click.echo("\nNext steps:")
    click.echo("  1. Add your OpenAI API key to .env:  echo 'OPENAI_API_KEY=sk-...' > .env")
    click.echo("  2. Process a lecture:  python cli.py process lecture.mp3 --title 'Lecture 1'")


if __name__ == "__main__":
    cli()
