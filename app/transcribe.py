import shutil
import sys
import tempfile
from pathlib import Path

import openai


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


def transcribe_audio(audio_path: Path, config: dict | None = None) -> str:
    """Transcribe an audio file, using the backend specified in config.

    The backend is selected by config["transcription"]["backend"]:
      - "local"  → faster-whisper (default, no API call)
      - "api"    → OpenAI Whisper API (fallback, requires OPENAI_API_KEY)

    For the "api" backend, files larger than 24 MB are split automatically.

    Args:
        audio_path: Path to the audio file.
        config: Loaded config dict. If None, defaults to "local" backend.

    Returns:
        Full transcript as a plain text string.
    """
    cfg = config or {}
    transcription_cfg = cfg.get("transcription", {})
    backend = transcription_cfg.get("backend", "local")

    if backend == "api":
        return _transcribe_api(audio_path)

    model_name = transcription_cfg.get("local_model", "base.en")
    return transcribe_local(audio_path, model_name)


def transcribe_local(audio_path: Path, model_name: str = "base.en") -> str:
    """Transcribe using a local faster-whisper model.

    On first run, the model weights are downloaded automatically (~150 MB for
    base.en) to ~/.cache/huggingface/. Subsequent runs use the cached model.

    Args:
        audio_path: Path to the audio file.
        model_name: faster-whisper model name (e.g. "tiny.en", "base.en", "small.en").

    Returns:
        Full transcript as a plain text string.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print(
            "Error: faster-whisper is not installed.\n"
            "Run: pip install faster-whisper"
        )
        sys.exit(1)

    print(f"  Loading local Whisper model '{model_name}' (downloads on first run)...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), beam_size=5)
    return " ".join(segment.text.strip() for segment in segments)


# ---------------------------------------------------------------------------
# OpenAI Whisper API backend (fallback)
# ---------------------------------------------------------------------------

def _transcribe_api(audio_path: Path) -> str:
    """Transcribe using the OpenAI Whisper API. Splits files over 24 MB."""
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
        for chunk_path in chunk_paths:
            chunk_path.unlink(missing_ok=True)
        tmp_dir.rmdir()


def split_audio(audio_path: Path, max_size_mb: int = 24) -> list[Path]:
    """Split an audio file into chunks under the Whisper API size limit."""
    from pydub import AudioSegment  # lazy import — pydub is only needed for the API backend
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
