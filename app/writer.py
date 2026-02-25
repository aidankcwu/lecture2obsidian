import re
import sys
from pathlib import Path

import yaml


def load_config(config_path: Path) -> dict:
    """Load and return the YAML config. Exits with a helpful message if missing."""
    if not config_path.exists():
        print(
            f"Error: config.yaml not found at {config_path}\n"
            "Run `python cli.py init` to create it."
        )
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def safe_filename(title: str) -> str:
    """Convert a title into a safe filename by removing/replacing unsafe characters."""
    # Replace characters not safe for filenames with a dash
    name = re.sub(r'[<>:"/\\|?*]', "-", title)
    # Collapse multiple dashes/spaces and strip leading/trailing whitespace/dashes
    name = re.sub(r"[\s-]+", " ", name).strip(" -")
    return name


def _unique_path(path: Path) -> Path:
    """If path exists, append _1, _2, etc. until we find an unused name."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _format_tag(value: str, style: str) -> str:
    """Format a tag as a wikilink or hashtag based on config tag_style."""
    if style == "hashtag":
        return f"#{value}"
    return f"[[{value}]]"


def write_notes(
    summary: str,
    transcript: str,
    title: str,
    course: str | None,
    date: str,
    config: dict,
) -> tuple[Path, Path]:
    """Write summary and raw transcript files to the Obsidian vault.

    Args:
        summary: Structured Markdown summary content.
        transcript: Raw plain-text transcript.
        title: Lecture title used for headings and filenames.
        course: Optional course code/name used as a tag.
        date: ISO date string (YYYY-MM-DD) for the note header.
        config: Loaded config dict from config.yaml.

    Returns:
        Tuple of (summary_path, transcript_path) as absolute Paths.
    """
    vault_path = Path(config["vault"]["path"]).expanduser()
    inbox_folder = config["vault"].get("inbox_folder", "1 - Inbox")
    source_folder = config["vault"].get("source_folder", "2 - Source Materials/Lectures")
    tag_style = config.get("note_template", {}).get("tag_style", "wikilink")
    status_tag = config.get("note_template", {}).get("status", "#review")

    if not vault_path.exists():
        print(
            f"Warning: Vault path does not exist: {vault_path}\n"
            "Writing files to the current directory instead."
        )
        vault_path = Path.cwd()

    inbox_dir = vault_path / inbox_folder
    source_dir = vault_path / source_folder
    inbox_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    filename_base = safe_filename(title)

    # --- Raw transcript file ---
    transcript_path = _unique_path(source_dir / f"{filename_base} - Transcript.md")
    transcript_content = _build_transcript_note(transcript, title, date)
    transcript_path.write_text(transcript_content, encoding="utf-8")

    # --- Summary note file ---
    summary_path = _unique_path(inbox_dir / f"{filename_base}.md")
    summary_content = _build_summary_note(
        summary=summary,
        title=title,
        date=date,
        course=course,
        transcript_filename=transcript_path.stem,
        tag_style=tag_style,
        status_tag=status_tag,
    )
    summary_path.write_text(summary_content, encoding="utf-8")

    return summary_path, transcript_path


def _build_summary_note(
    summary: str,
    title: str,
    date: str,
    course: str | None,
    transcript_filename: str,
    tag_style: str,
    status_tag: str,
) -> str:
    lines = [date, ""]
    lines.append(f"Status: {status_tag}")
    lines.append("")

    if course:
        tag = _format_tag(course, tag_style)
        lines.append(f"Tags: {tag}")
        lines.append("")

    lines.append(f"Transcript: [[{transcript_filename}]]")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(summary)

    return "\n".join(lines)


def _build_transcript_note(transcript: str, title: str, date: str) -> str:
    lines = [
        date,
        "",
        "Status: #source",
        "",
        f"# {title} - Full Transcript",
        "",
        transcript,
    ]
    return "\n".join(lines)
