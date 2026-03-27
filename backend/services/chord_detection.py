"""
Chord detection service.

Uses madmom's DeepChroma + RNN pipeline when available (much more accurate).
Falls back to the librosa chroma template-matching approach if madmom is not installed
or fails to load (e.g. Python version incompatibility).

madmom approach:
  - DeepChromaProcessor: CNN trained on large datasets to extract pitch-class features
    that are more robust than raw CQT chroma (especially against timbre variation)
  - DeepChromaChordRecognitionProcessor: Bi-directional RNN + HMM that maps the chroma
    sequence to a chord label sequence, learning temporal dependencies between chords

librosa fallback:
  - HPSS to isolate harmonics
  - CQT chroma + median filter smoothing
  - Template matching with minimum duration gate
"""

import numpy as np
import librosa

from models.job import ChordEvent

# ── Try to import madmom ──────────────────────────────────────────────────────
try:
    from madmom.audio.chroma import DeepChromaProcessor
    from madmom.features.chords import DeepChromaChordRecognitionProcessor
    _MADMOM_AVAILABLE = True
except Exception:
    _MADMOM_AVAILABLE = False

# ── Constants for the librosa fallback ───────────────────────────────────────
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

MAJOR_TEMPLATES = np.array([
    [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0],
    [0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0],
    [0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1],
    [1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0],
    [0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1],
    [1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0],
    [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1],
], dtype=float)

MINOR_TEMPLATES = np.array([
    [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0],
    [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0],
    [0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0],
    [0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0],
    [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1],
    [1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0],
    [0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1],
], dtype=float)

MAJOR_TEMPLATES /= np.linalg.norm(MAJOR_TEMPLATES, axis=1, keepdims=True)
MINOR_TEMPLATES /= np.linalg.norm(MINOR_TEMPLATES, axis=1, keepdims=True)


# ── Public entry point ────────────────────────────────────────────────────────

def detect_chords(wav_path: str) -> list[ChordEvent]:
    """
    Detect chords from a WAV file.
    Automatically picks the best available backend.
    """
    if _MADMOM_AVAILABLE:
        print("[chord] Using madmom DeepChroma + RNN pipeline")
        return _detect_with_madmom(wav_path)
    else:
        print("[chord] madmom not available — using librosa fallback")
        return _detect_with_librosa(wav_path)


# ── madmom backend ────────────────────────────────────────────────────────────

def _detect_with_madmom(wav_path: str, tau: float = 3.0) -> list[ChordEvent]:
    """
    madmom pipeline:
      DeepChromaProcessor (CNN) → deep chroma features
      DeepChromaChordRecognitionProcessor (RNN + HMM) → chord segments

    The `tau` parameter controls the HMM transition regularization:
      - Higher tau → fewer chord changes (more stable, may miss fast changes)
      - Lower tau  → more chord changes (more responsive, may flicker on noise)
    Default madmom value is ~100; we use 6 for more responsive tracking.

    Returns one ChordEvent per chord segment (start time + chord label).
    """
    chroma_proc = DeepChromaProcessor()
    chord_proc = DeepChromaChordRecognitionProcessor(tau=tau)

    chroma = chroma_proc(wav_path)
    # raw_chords is an array of [start_sec, end_sec, chord_label]
    raw_chords = chord_proc(chroma)

    events: list[ChordEvent] = []
    last_chord: str | None = None

    for start, _end, label in raw_chords:
        if label == "N":
            continue  # silence segment
        normalized = _normalize_madmom_label(label)
        if normalized != last_chord:
            events.append(ChordEvent(time=round(float(start), 3), chord=normalized))
            last_chord = normalized

    return events


def _normalize_madmom_label(label: str) -> str:
    """
    Convert madmom's chord notation to guitarist-friendly format.
    Examples: "A:min" → "Am", "C:maj" → "C", "F#:min7" → "F#m7"
    """
    if ":" not in label:
        return label

    root, quality = label.split(":", 1)
    quality_map = {
        "maj": "", "min": "m", "dim": "dim", "aug": "aug",
        "maj7": "maj7", "min7": "m7", "dom7": "7", "hdim7": "m7b5",
    }
    return root + quality_map.get(quality, quality)


# ── librosa fallback ──────────────────────────────────────────────────────────

def _detect_with_librosa(
    wav_path: str,
    hop_seconds: float = 0.1,
    smooth_frames: int = 15,
    min_chord_duration: float = 0.8,
) -> list[ChordEvent]:
    """
    Fallback chord detector using librosa:
      1. HPSS — isolate harmonic layer, discard drums/transients
      2. CQT chroma on harmonic signal
      3. Median filter to smooth frame-level noise
      4. Template matching (cosine similarity) against major/minor templates
      5. Minimum duration gate — chords shorter than min_chord_duration are merged
    """
    # 22050 Hz is standard for chord detection and halves memory vs 44100 Hz originals.
    # Cap at 2 minutes — chord progressions repeat, so we get full coverage without
    # loading the entire song. Avoids OOM on Railway Hobby's limited RAM.
    waveform, sr = librosa.load(wav_path, sr=22050, mono=True,
                                duration=120.0)
    hop_length = int(hop_seconds * sr)

    # Skip HPSS — it duplicates the entire waveform in memory and the accuracy
    # gain over raw CQT chroma is marginal for the librosa fallback path.
    chroma = librosa.feature.chroma_cqt(y=waveform, sr=sr, hop_length=hop_length)
    chroma_smooth = _median_filter(chroma, smooth_frames)

    n_frames = chroma_smooth.shape[1]
    frame_chords = [_best_template_match(chroma_smooth[:, i]) for i in range(n_frames)]

    return _min_duration_gate(frame_chords, sr, hop_length, min_chord_duration)


def _median_filter(chroma: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return chroma
    half = width // 2
    n = chroma.shape[1]
    out = np.empty_like(chroma)
    for i in range(n):
        out[:, i] = np.median(chroma[:, max(0, i - half):min(n, i + half + 1)], axis=1)
    return out


def _best_template_match(chroma_vec: np.ndarray) -> str:
    norm = np.linalg.norm(chroma_vec)
    if norm < 1e-6:
        return "N"
    unit = chroma_vec / norm
    maj_scores = MAJOR_TEMPLATES @ unit
    min_scores = MINOR_TEMPLATES @ unit
    bm = int(np.argmax(maj_scores))
    bn = int(np.argmax(min_scores))
    return NOTES[bm] if maj_scores[bm] >= min_scores[bn] else NOTES[bn] + "m"


def _min_duration_gate(
    frame_chords: list[str], sr: int, hop_length: int, min_duration: float
) -> list[ChordEvent]:
    if not frame_chords:
        return []

    spf = hop_length / sr  # seconds per frame
    min_frames = int(min_duration / spf)

    # Collapse identical consecutive frames into segments
    segments: list[tuple[str, int]] = []
    prev, start = frame_chords[0], 0
    for i in range(1, len(frame_chords)):
        if frame_chords[i] != prev:
            segments.append((prev, start))
            prev, start = frame_chords[i], i
    segments.append((prev, start))

    # Add sentinel to know segment lengths
    end_frames = [segments[i + 1][1] for i in range(len(segments) - 1)] + [len(frame_chords)]

    # Merge short segments into their predecessor
    filtered: list[tuple[str, int]] = []
    for (chord, start_f), end_f in zip(segments, end_frames):
        if chord == "N":
            continue
        duration = end_f - start_f
        if duration < min_frames and filtered:
            pass  # keep predecessor, skip this short segment
        else:
            filtered.append((chord, start_f))

    # Emit events only on actual chord changes
    events: list[ChordEvent] = []
    last: str | None = None
    for chord, start_f in filtered:
        if chord != last:
            events.append(ChordEvent(time=round(start_f * spf, 3), chord=chord))
            last = chord

    return events
