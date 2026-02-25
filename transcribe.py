import shutil
import sys
import tempfile
from pathlib import Path

import openai
from pydub import AudioSegment


def check_ffmpeg() -> None:
    """Verify ffmpeg is available on PATH. Exits with a helpful message if not."""
    if shutil.which("ffmpeg") is None:
        print(
            "Error: ffmpeg is not installed or not on your PATH.\n"
            "Install it before running this tool:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Ubuntu: sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )
        sys.exit(1)


def split_audio(audio_path: Path, max_size_mb: int = 24) -> list[Path]:
    """Split an audio file into chunks under the Whisper API size limit.

    Args:
        audio_path: Path to the source audio file.
        max_size_mb: Maximum size in MB per chunk (default 24, leaving headroom under 25 MB limit).

    Returns:
        List of Paths pointing to the temporary chunk files.
    """
    audio = AudioSegment.from_file(str(audio_path))
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    num_chunks = int(file_size_mb / max_size_mb) + 1
    chunk_duration_ms = len(audio) // num_chunks

    tmp_dir = Path(tempfile.mkdtemp(prefix="lecture2obs_"))
    chunk_paths: list[Path] = []

    for i in range(num_chunks):
        start_ms = i * chunk_duration_ms
        end_ms = start_ms + chunk_duration_ms if i < num_chunks - 1 else len(audio)
        chunk = audio[start_ms:end_ms]

        chunk_path = tmp_dir / f"chunk_{i:03d}{audio_path.suffix}"
        chunk.export(str(chunk_path), format=audio_path.suffix.lstrip("."))
        chunk_paths.append(chunk_path)

    return chunk_paths


def transcribe_audio(audio_path: Path) -> str:
    """Transcribe an audio file using the OpenAI Whisper API.

    Automatically splits files larger than 24 MB into chunks and
    concatenates the resulting transcripts.

    Args:
        audio_path: Path to the audio file (mp3, m4a, wav, etc.).

    Returns:
        Full transcript as a plain text string.
    """
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)

    if file_size_mb <= 24:
        return _transcribe_single(audio_path)

    print(f"  File is {file_size_mb:.1f} MB — splitting into chunks for Whisper API...")
    chunk_paths = split_audio(audio_path)
    tmp_dir = chunk_paths[0].parent

    try:
        parts: list[str] = []
        for i, chunk_path in enumerate(chunk_paths, 1):
            print(f"  Transcribing chunk {i}/{len(chunk_paths)}...")
            parts.append(_transcribe_single(chunk_path))
        return " ".join(parts)
    finally:
        # Clean up temp files
        for chunk_path in chunk_paths:
            chunk_path.unlink(missing_ok=True)
        tmp_dir.rmdir()


def _transcribe_single(audio_path: Path) -> str:
    """Transcribe a single audio file under 25 MB using the Whisper API."""
    try:
        with open(audio_path, "rb") as f:
            response = openai.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )
        return response
    except openai.AuthenticationError:
        print("Error: Invalid OpenAI API key. Check OPENAI_API_KEY in your .env file.")
        sys.exit(1)
    except openai.OpenAIError as e:
        print(f"Error: Whisper API call failed — {e}")
        sys.exit(1)
