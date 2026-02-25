import queue
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

_SAMPLE_RATE = 16000
_CHANNELS = 1
_DTYPE = "int16"
_BLOCK_SIZE = 1024  # frames per callback


class Recorder:
    """Captures audio from the default microphone using sounddevice.

    Usage:
        recorder = Recorder()
        recorder.start()
        # ... time passes ...
        wav_path = recorder.stop()
    """

    def __init__(self, sample_rate: int = _SAMPLE_RATE) -> None:
        self._sample_rate = sample_rate
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Open the default mic input stream and start capturing audio.

        Raises:
            sd.PortAudioError: If no microphone is available or access is denied.
            RuntimeError: If already recording.
        """
        with self._lock:
            if self._recording:
                raise RuntimeError("Already recording.")

            # Drain the queue from any previous run
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=_CHANNELS,
                dtype=_DTYPE,
                blocksize=_BLOCK_SIZE,
                callback=self._callback,
            )
            self._stream.start()
            self._recording = True

    def stop(self) -> Path:
        """Stop recording and write captured audio to a temporary WAV file.

        Returns:
            Path to the written WAV file.

        Raises:
            RuntimeError: If not currently recording.
            ValueError: If no audio was captured (zero-length recording).
        """
        with self._lock:
            if not self._recording:
                raise RuntimeError("Not currently recording.")
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self._recording = False

        # Collect all queued frames
        frames: list[np.ndarray] = []
        while not self._queue.empty():
            try:
                frames.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not frames:
            raise ValueError("No audio captured — recording was empty.")

        audio_data = np.concatenate(frames, axis=0)

        _, wav_path = tempfile.mkstemp(suffix=".wav", prefix="lecture_")
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(_CHANNELS)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(self._sample_rate)
            wf.writeframes(audio_data.tobytes())

        return Path(wav_path)

    def is_recording(self) -> bool:
        """Return True if currently capturing audio."""
        return self._recording

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time,
        status: sd.CallbackFlags,
    ) -> None:
        """sounddevice callback — called from a background thread."""
        self._queue.put(indata.copy())
