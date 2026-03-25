import re
import whisper

from config import settings
from models.job import ChordEvent, WordEvent

# ── LRC parser ────────────────────────────────────────────────────────────────

_LRC_LINE_RE = re.compile(r'\[(\d{1,2}):(\d{2}\.\d+)\]\s*(.*)')


def parse_lrc(lrc_text: str, total_duration: float) -> list[WordEvent]:
    """
    Convert LRC-format synced lyrics into per-word WordEvents.

    LRC format:  [MM:SS.xx] lyric line text

    Each line's time window spans from its own timestamp to the next line's
    timestamp (or total_duration for the last line).  Words within a line are
    distributed uniformly across that window — this is approximate but far more
    accurate than Whisper transcription because the line-start timestamps come
    from Musixmatch/LRCLib ground truth.

    Lines whose text is empty or looks like an instrumental marker ("♪", "...",
    purely punctuation) are skipped so they don't create ghost words.
    """
    lines: list[tuple[float, str]] = []

    for match in _LRC_LINE_RE.finditer(lrc_text):
        minutes  = int(match.group(1))
        seconds  = float(match.group(2))
        text     = match.group(3).strip()
        t_start  = minutes * 60.0 + seconds

        # Skip instrumental / empty lines
        clean = re.sub(r'[♪♩…\.\-\s]', '', text)
        if not clean:
            continue

        lines.append((t_start, text))

    if not lines:
        return []

    events: list[WordEvent] = []

    for i, (t_start, text) in enumerate(lines):
        t_end  = lines[i + 1][0] if i + 1 < len(lines) else total_duration
        words  = text.split()
        n      = len(words)
        step   = (t_end - t_start) / n if n else 0.0

        for j, word in enumerate(words):
            events.append(WordEvent(
                start=round(t_start + j * step, 3),
                end=round(t_start + (j + 1) * step, 3),
                word=word,
                newline=(j == 0),   # first word of each line starts a new lyric row
            ))

    return events


# ── UG inline chords + LRC timing → events ────────────────────────────────────

def build_events_from_ug_and_lrc(
    ug_pairs: list[tuple[str | None, str, bool]],
    lrc_text: str,
    total_duration: float,
) -> tuple[list[WordEvent], list[ChordEvent]]:
    """
    Combine UG chord-word pairs (accurate chord names + word order) with
    LRC line timestamps (accurate timing) to produce synchronized events.

    UG gives us: which chord plays at which word.
    LRC gives us: when each lyric line starts.
    Together: each word has a timestamp AND the correct chord label.
    """
    lrc_lines = _parse_lrc_lines(lrc_text)
    if not lrc_lines:
        # No LRC available — distribute uniformly as last resort
        return _uniform_from_ug(ug_pairs, total_duration)

    # Group UG pairs into lyric lines
    ug_lines = _group_ug_lines(ug_pairs)

    # Match each LRC line to a UG line by text similarity
    lrc_with_ends = [
        (t, lrc_lines[i + 1][0] if i + 1 < len(lrc_lines) else total_duration, text)
        for i, (t, text) in enumerate(lrc_lines)
    ]

    word_events:  list[WordEvent]  = []
    chord_events: list[ChordEvent] = []
    ug_idx = 0

    for t_start, t_end, lrc_text_line in lrc_with_ends:
        if ug_idx >= len(ug_lines):
            break

        # Find the best-matching UG line (greedy, look-ahead of 4)
        lrc_words = set(_normalize(lrc_text_line).split())
        best_idx   = ug_idx
        best_score = -1.0

        for j in range(ug_idx, min(ug_idx + 10, len(ug_lines))):
            ug_text  = " ".join(w for _, w in ug_lines[j])
            ug_words = set(_normalize(ug_text).split())
            score = len(lrc_words & ug_words) / len(lrc_words) if lrc_words else 0.0
            if score > best_score:
                best_score = score
                best_idx   = j

        if best_score < 0.25:
            # No meaningful overlap — LRC line is probably instrumental, skip it
            continue

        line_pairs = ug_lines[best_idx]
        ug_idx     = best_idx + 1

        n    = len(line_pairs)
        step = (t_end - t_start) / n if n else 0.0

        for j, (chord, word) in enumerate(line_pairs):
            w_start = round(t_start + j * step, 3)
            w_end   = round(t_start + (j + 1) * step, 3)
            word_events.append(WordEvent(start=w_start, end=w_end, word=word, newline=(j == 0)))
            if chord:
                chord_events.append(ChordEvent(time=w_start, chord=chord))

    return word_events, chord_events


def _parse_lrc_lines(lrc_text: str) -> list[tuple[float, str]]:
    """Return list of (t_seconds, line_text) from an LRC string, skipping empty/instrumental lines."""
    lines = []
    for m in _LRC_LINE_RE.finditer(lrc_text):
        t    = int(m.group(1)) * 60.0 + float(m.group(2))
        text = m.group(3).strip()
        if text and re.search(r'[A-Za-zÀ-ÿ]{2,}', text):
            lines.append((t, text))
    return lines


def _group_ug_lines(
    pairs: list[tuple[str | None, str, bool]],
) -> list[list[tuple[str | None, str]]]:
    """Split flat (chord, word, is_line_start) list back into per-line sublists."""
    lines: list[list[tuple[str | None, str]]] = []
    current: list[tuple[str | None, str]] = []
    for chord, word, is_start in pairs:
        if is_start and current:
            lines.append(current)
            current = []
        current.append((chord, word))
    if current:
        lines.append(current)
    return lines


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text.strip()


def _uniform_from_ug(
    pairs: list[tuple[str | None, str, bool]],
    total_duration: float,
) -> tuple[list[WordEvent], list[ChordEvent]]:
    """Fallback: distribute all words uniformly when no LRC is available."""
    n    = len(pairs)
    step = total_duration / n if n else 0.0
    words:  list[WordEvent]  = []
    chords: list[ChordEvent] = []
    for i, (chord, word, is_start) in enumerate(pairs):
        t = round(i * step, 3)
        words.append(WordEvent(start=t, end=round(t + step, 3), word=word, newline=is_start))
        if chord:
            chords.append(ChordEvent(time=t, chord=chord))
    return words, chords


try:
    import stable_whisper
    _STABLE_TS_AVAILABLE = True
except ImportError:
    _STABLE_TS_AVAILABLE = False

_stable_model: object | None = None


def _get_stable_model() -> object:
    global _stable_model
    if _stable_model is None:
        _stable_model = stable_whisper.load_model(settings.whisper_model)
    return _stable_model


def words_from_lyrics(lyrics_text: str, vocals_path: str) -> list[WordEvent]:
    """
    Align known lyrics to audio without a full blind Whisper transcription.

    Strategy (in order of preference):
      1. stable-ts forced alignment — aligns the known text to audio using
         Whisper's cross-attention; much faster than full transcription because
         there's no beam-search decoding.
      2. Whisper with lyrics as initial_prompt — slower but guaranteed to give
         accurate word-level timestamps; used when stable-ts is not installed
         or alignment fails.

    Line breaks from the original lyrics text are preserved so the display
    matches the verse/chorus structure of the source page.
    """
    structured = _parse_lyrics_structure(lyrics_text)
    if not structured:
        return []

    # ── Option 1: stable-ts forced alignment (fast) ───────────────────────────
    if _STABLE_TS_AVAILABLE:
        try:
            return _align_with_stable_ts(structured, lyrics_text, vocals_path)
        except Exception as exc:
            print(f"[transcription] stable-ts alignment failed ({exc}), using Whisper fallback")

    # ── Option 2: Whisper with lyrics as prompt (accurate, slower) ───────────
    print("[transcription] Running Whisper with web lyrics as guide for timing...")
    whisper_words = transcribe_audio(vocals_path, lyrics_hint=lyrics_text)
    return _attach_newline_markers(whisper_words, structured)


def _parse_lyrics_structure(lyrics_text: str) -> list[tuple[str, bool]]:
    """
    Split lyrics into (word, is_line_start) pairs, preserving line structure.
    Empty lines are skipped; the first word of each non-empty line gets True.
    """
    structured: list[tuple[str, bool]] = []
    for line in lyrics_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        for j, w in enumerate(line.split()):
            structured.append((w, j == 0))
    return structured


def _align_with_stable_ts(
    structured: list[tuple[str, bool]],
    lyrics_text: str,
    vocals_path: str,
) -> list[WordEvent]:
    """
    Use stable-ts forced alignment to get per-word timestamps.
    stable-ts aligns the given text to the audio via Whisper cross-attention.
    """
    model = _get_stable_model()
    result = model.align(vocals_path, lyrics_text)

    aligned: list[tuple[float, float]] = []
    for seg in result.segments:
        for w in seg.words:
            if w.word.strip():
                aligned.append((float(w.start), float(w.end)))

    events: list[WordEvent] = []
    for i, (word, is_line_start) in enumerate(structured):
        if i < len(aligned):
            t_start, t_end = aligned[i]
        else:
            t_start = aligned[-1][1] if aligned else 0.0
            t_end   = t_start + 0.3
        events.append(WordEvent(
            start=round(t_start, 3),
            end=round(t_end, 3),
            word=word,
            newline=is_line_start,
        ))
    return events


def _attach_newline_markers(
    whisper_words: list[WordEvent],
    structured: list[tuple[str, bool]],
) -> list[WordEvent]:
    """
    Add newline=True to the first word of each lyrics line in Whisper output.

    Whisper may output slightly different tokenization than the original text,
    so we match by position rather than by exact word text.
    """
    line_start_indices: set[int] = set()
    pos = 0
    for _, is_start in structured:
        if is_start and pos < len(whisper_words):
            line_start_indices.add(pos)
        pos += 1

    result: list[WordEvent] = []
    for i, w in enumerate(whisper_words):
        result.append(WordEvent(
            start=w.start,
            end=w.end,
            word=w.word,
            newline=(i in line_start_indices),
        ))
    return result

_whisper_model: whisper.Whisper | None = None


def _get_model() -> whisper.Whisper:
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = whisper.load_model(settings.whisper_model)
    return _whisper_model


def transcribe_audio(wav_path: str, lyrics_hint: str | None = None) -> list[WordEvent]:
    """
    Transcribe audio using Whisper and extract word-level timestamps.

    When `lyrics_hint` is provided (e.g. lyrics fetched from the web), it is
    passed as Whisper's `initial_prompt`. This biases the model toward the
    correct words and dramatically improves accuracy — Whisper follows the
    provided text instead of guessing from audio alone.

    Returns a list of WordEvent with start/end times per word.
    """
    model = _get_model()

    kwargs: dict = {
        "word_timestamps": True,
        "verbose": False,
    }
    if lyrics_hint:
        # Truncate to Whisper's context limit (~200 tokens ≈ 800 chars)
        kwargs["initial_prompt"] = lyrics_hint[:800]

    result = model.transcribe(wav_path, **kwargs)

    words: list[WordEvent] = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            word_text = w.get("word", "").strip()
            if not word_text:
                continue
            words.append(WordEvent(
                start=float(w["start"]),
                end=float(w["end"]),
                word=word_text,
            ))

    return words
