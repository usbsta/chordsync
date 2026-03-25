import os
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from config import settings


def load_audio_mono(file_path: str) -> tuple[np.ndarray, int]:
    """
    Load an audio file and convert it to mono at the target sample rate.
    Returns (waveform, sample_rate).
    """
    waveform, sr = librosa.load(file_path, sr=settings.target_sample_rate, mono=True)
    return waveform, sr


def save_as_wav(waveform: np.ndarray, sample_rate: int, output_path: str) -> None:
    """
    Save a numpy waveform to a WAV file.
    Whisper and madmom work best with WAV input.
    """
    sf.write(output_path, waveform, sample_rate)


def get_audio_duration(file_path: str) -> float:
    """Return the duration of an audio file in seconds without loading it fully."""
    return librosa.get_duration(path=file_path)


def prepare_audio(source_path: str, job_id: str) -> str:
    """
    Load and normalize an uploaded audio file, save a clean WAV copy,
    and return the path to the WAV file.

    This WAV file is used as shared input for both the chord detector
    and the Whisper transcription step.
    """
    waveform, sr = load_audio_mono(source_path)

    wav_dir = Path(settings.storage_path) / job_id
    wav_dir.mkdir(parents=True, exist_ok=True)
    wav_path = str(wav_dir / "audio.wav")

    save_as_wav(waveform, sr, wav_path)
    return wav_path


def validate_file_size(file_size_bytes: int) -> bool:
    """Return False if the file exceeds the configured max size."""
    limit = settings.max_file_size_mb * 1024 * 1024
    return file_size_bytes <= limit
