"""
Chord timing service.

When chord names come from a reliable web source, we still need timestamps
for when each chord plays. This module uses librosa's beat tracker to find
the musical beat grid, then assigns web chord names to beat positions.

This is more reliable than madmom for names (web is ground truth) and
librosa's beat tracker is very accurate for timing.
"""

import numpy as np
import librosa

from models.job import ChordEvent


def get_chord_events_from_sequence(
    wav_path: str,
    chord_sequence: list[str],
) -> list[ChordEvent]:
    """
    Map a web chord sequence to timestamps using beat tracking.

    Strategy:
      1. Detect beats in the audio with librosa's beat tracker
      2. Compute how many beats per chord change fits the song
         (by comparing total beats vs sequence length × expected repetitions)
      3. Assign web chord names to beat positions
      4. Merge consecutive identical chords

    Most pop/rock songs change chords every 2 or 4 beats.
    We try both and pick whichever produces a chord count closest to the
    web sequence length × a reasonable number of repetitions.
    """
    if not chord_sequence:
        return []

    waveform, sr = librosa.load(wav_path, sr=None, mono=True)
    _, beat_frames = librosa.beat.beat_track(y=waveform, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    if len(beat_times) == 0:
        return []

    n_seq = len(chord_sequence)
    n_beats = len(beat_times)

    # Try different beats-per-chord values and pick the best fit
    best_bpc = _best_beats_per_chord(n_beats, n_seq)

    # Sample one beat every `best_bpc` beats as a chord change point
    change_times = beat_times[::best_bpc]

    events: list[ChordEvent] = []
    for i, t in enumerate(change_times):
        chord = chord_sequence[i % n_seq]
        events.append(ChordEvent(time=round(float(t), 3), chord=chord))

    # Merge consecutive identical chords
    merged = [events[0]] if events else []
    for ev in events[1:]:
        if ev.chord != merged[-1].chord:
            merged.append(ev)

    return merged


def _best_beats_per_chord(n_beats: int, n_seq: int) -> int:
    """
    Find the beats-per-chord value (1, 2, 4, or 8) that produces a
    number of chord events closest to n_seq × estimated repetitions.

    Most songs repeat their progression 3–6 times.
    """
    candidates = [1, 2, 4, 8]
    target = n_seq * 4  # assume ~4 repetitions of the chord progression

    best = 4  # default: change every 4 beats
    best_diff = float("inf")

    for bpc in candidates:
        n_events = n_beats // bpc
        diff = abs(n_events - target)
        if diff < best_diff:
            best_diff = diff
            best = bpc

    return best
