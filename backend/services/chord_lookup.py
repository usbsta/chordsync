"""
Chord lookup service.

Tries multiple reliable chord sites in priority order.
Returns:
  - chord_set:      unique chords used in the song (for constraining audio analysis)
  - chord_sequence: ordered list of chords as they appear (for alignment, may have repeats)
  - lyrics:         plain lyrics text when the source provides it alongside chords (optional)
"""

import json
import re
import unicodedata
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from models.job import ChordEvent

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Chord name regex — covers major, minor, 7ths, sus, add, etc.
_CHORD_RE = re.compile(
    r'\b([A-G][#b]?'
    r'(?:maj7?|min7?|m7?|dim7?|aug|sus[24]?|add9?|7|9|11|13)?)'
    r'(?=\s|$|\|)'
)

_MIN_UNIQUE_CHORDS = 3


# ── Public API ────────────────────────────────────────────────────────────────

def lookup_chord_set(artist: str, title: str) -> set[str] | None:
    """Return the set of unique chord names used in the song, or None."""
    result = _lookup(artist, title)
    return result["chord_set"] if result else None


def lookup_chords_full(artist: str, title: str) -> dict | None:
    """
    Return {'chord_set': set, 'chord_sequence': list, 'lyrics': str|None} or None.
    chord_sequence is the ordered list of chords as they appear in the song
    (including repeats across sections), useful for timing alignment.
    lyrics is the plain song text when the source provides it (e.g. lacuerda.net).
    """
    return _lookup(artist, title)


def apply_web_chords(
    audio_events: list[ChordEvent],
    web_sequence: list[str],
) -> list[ChordEvent]:
    """
    Use audio timing + web chord names to build accurate chord events.

    Audio analysis is good at detecting WHEN chords change but not always WHAT
    chord it is. Online chord charts have accurate names but no timestamps.
    This function combines both: audio gives the timing, web gives the names.

    The web sequence is cycled if the audio detects more changes than the
    sequence has entries — this works well for songs with repeating progressions.

    Consecutive duplicates are merged after cycling.
    """
    if not web_sequence or not audio_events:
        return audio_events

    n = len(web_sequence)
    raw = [
        ChordEvent(time=ev.time, chord=web_sequence[i % n])
        for i, ev in enumerate(audio_events)
    ]

    # Merge consecutive identical chords created by the cycling
    merged = [raw[0]]
    for ev in raw[1:]:
        if ev.chord != merged[-1].chord:
            merged.append(ev)

    return merged


def constrain_chords_to_set(
    events: list[ChordEvent],
    valid_chords: set[str],
) -> list[ChordEvent]:
    """
    Fallback: replace each detected chord with the nearest chord from the
    valid set. Used when we have a chord set but no ordered sequence.
    """
    if not valid_chords:
        return events

    corrected = [
        ChordEvent(
            time=ev.time,
            chord=ev.chord if ev.chord in valid_chords else _nearest_chord(ev.chord, valid_chords)
        )
        for ev in events
    ]

    merged = [corrected[0]] if corrected else []
    for ev in corrected[1:]:
        if ev.chord != merged[-1].chord:
            merged.append(ev)

    return merged


# ── Site-specific scrapers (tried in order) ───────────────────────────────────

def _ddg_urls(query: str, site: str = "") -> list[str]:
    """
    Search DuckDuckGo Lite and return real URLs (decoding their redirect wrappers).
    DuckDuckGo wraps results as //duckduckgo.com/l/?uddg=<encoded_url> — we decode those.
    """
    params = {"q": f"site:{site} {query}" if site else query}
    res = requests.get("https://lite.duckduckgo.com/lite/", params=params, headers=_HEADERS, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    urls = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc:
            uddg = parse_qs(parsed.query).get("uddg", [None])[0]
            if uddg:
                href = unquote(uddg)
        if href.startswith("http") and "duckduckgo" not in href:
            urls.append(href)
    return urls


def _try_lacuerda(query: str) -> dict | None:
    """
    lacuerda.net / acordes.lacuerda.net — Spanish chord/lyrics database.
    Inline format: [Am]word [F]word ... so one request gives both chords and lyrics.
    Uses DuckDuckGo to find the right song URL, then scrapes the page.
    """
    urls = _ddg_urls(query, site="lacuerda.net")
    if not urls:
        return None

    song_res = requests.get(urls[0], headers=_HEADERS, timeout=10)
    if not song_res.ok:
        return None

    song_soup = BeautifulSoup(song_res.text, "html.parser")

    # lacuerda.net stores the tab in a <pre> or a div with class "tab" / "cifra"
    content_block = (
        song_soup.find("pre") or
        song_soup.find("div", class_="tab") or
        song_soup.find("div", class_="cifra") or
        song_soup.find("div", id="tab")
    )
    if not content_block:
        return None

    raw_text = content_block.get_text()

    # Extract chord sequence from [Chord] markers (lacuerda inline format)
    chord_sequence = re.findall(r'\[([A-G][#b]?(?:maj7?|min7?|m7?|dim7?|aug|sus[24]?|add9?|7|9|11|13)?)\]', raw_text)

    lyrics_text = _extract_clean_lyrics(raw_text)
    result = _build_result(chord_sequence)
    if result and lyrics_text:
        result["lyrics"] = lyrics_text
    return result

def _lookup(artist: str, title: str) -> dict | None:
    """Try each source in priority order, return the first valid result."""
    slug_artist = _slugify(artist)
    slug_title  = _slugify(title)
    query       = f"{artist} {title}"

    sources = [
        # lacuerda.net — Spanish-friendly, provides chords + lyrics together
        lambda: _try_lacuerda(query),
        # Ultimate Guitar — best coverage for English songs
        lambda: _try_ultimate_guitar(artist, title),
        lambda: _try_cifraclub(slug_artist, slug_title),
        lambda: _try_azchords(slug_artist, slug_title),
        lambda: _try_duckduckgo(query),
    ]

    for source in sources:
        try:
            result = source()
            if result and len(result.get("chord_set", set())) >= _MIN_UNIQUE_CHORDS:
                print(f"[chord_lookup] Found {len(result['chord_set'])} chords: {result['chord_set']}")
                return result
        except Exception as e:
            print(f"[chord_lookup] Source failed: {e}")

    print("[chord_lookup] No reliable chord data found")
    return None


def _try_ultimate_guitar(artist: str, title: str) -> dict | None:
    """
    Ultimate Guitar — largest English chord database.

    UG renders pages as a React app but embeds all data as JSON inside a
    `div.js-store[data-content]` attribute, so no JS execution needed.

    Chord format in content: [ch]Am[/ch]word [ch]F[/ch]word
    Lyrics and chords are interspersed — we strip [ch] markers for plain lyrics.
    """
    search_url = (
        "https://www.ultimate-guitar.com/search.php"
        f"?search_type=title&value={quote_plus(artist + ' ' + title)}&type=Chords"
    )
    res = requests.get(search_url, headers=_HEADERS, timeout=12)
    if not res.ok:
        return None

    soup = BeautifulSoup(res.text, "html.parser")
    store = soup.find("div", class_="js-store")
    if not store:
        return None

    try:
        data = json.loads(store["data-content"])
        results = data["store"]["page"]["data"]["results"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None

    # Pick the first Chords result (not Tab, Bass, etc.)
    tab_url = None
    for item in results:
        if isinstance(item, dict) and item.get("type") == "Chords":
            tab_url = item.get("tab_url") or item.get("marketing_type")
            if tab_url:
                break

    if not tab_url:
        return None

    tab_res = requests.get(tab_url, headers=_HEADERS, timeout=12)
    if not tab_res.ok:
        return None

    tab_soup = BeautifulSoup(tab_res.text, "html.parser")
    tab_store = tab_soup.find("div", class_="js-store")
    if not tab_store:
        return None

    try:
        tab_data = json.loads(tab_store["data-content"])
        content = tab_data["store"]["page"]["data"]["tab_view"]["wiki_tab"]["content"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None

    # Extract chord sequence from [ch]Chord[/ch] markers
    chord_sequence = re.findall(r'\[ch\]([A-G][#b]?(?:maj7?|min7?|m7?|dim7?|aug|sus[24]?|add9?|7|9|11|13)?)\[/ch\]', content)

    lyrics_text = _extract_clean_lyrics(content)
    result = _build_result(chord_sequence)
    if result:
        if lyrics_text:
            result["lyrics"] = lyrics_text
        # Preserve raw content so callers can parse inline chord-word positions
        result["raw_content"] = content
        result["content_format"] = "ug"
    return result


def _try_cifraclub(slug_artist: str, slug_title: str) -> dict | None:
    """
    CifraClub (cifraclub.com.br) — largest chord database in Portuguese/Spanish/English.
    URL pattern: https://www.cifraclub.com.br/{artist}/{title}/
    Returns chords + clean lyrics (chord-only lines stripped out).
    """
    url = f"https://www.cifraclub.com.br/{slug_artist}/{slug_title}/"
    res = requests.get(url, headers=_HEADERS, timeout=10)
    if not res.ok:
        return None

    soup = BeautifulSoup(res.text, "html.parser")

    # Chords are in <b> tags inside the tab block
    chord_tags = soup.select(".cifra_cnt b, pre b")
    sequence = [tag.get_text(strip=True) for tag in chord_tags if _CHORD_RE.match(tag.get_text(strip=True))]
    if not sequence:
        sequence = _extract_sequence(soup.get_text())

    result = _build_result(sequence)
    if not result:
        return None

    # Extract lyrics: use the tab block, remove chord-only lines and section labels
    tab_block = soup.select_one(".cifra_cnt, pre")
    if tab_block:
        lyrics_text = _extract_clean_lyrics(tab_block.get_text())
        if lyrics_text:
            result["lyrics"] = lyrics_text

    return result


def _try_azchords(slug_artist: str, slug_title: str) -> dict | None:
    """
    AZChords — clean HTML, good English song coverage.
    Searches via their search endpoint.
    """
    search_url = f"https://www.azchords.com/search/?q={quote_plus(slug_artist + ' ' + slug_title)}"
    res = requests.get(search_url, headers=_HEADERS, timeout=10)
    if not res.ok:
        return None

    soup = BeautifulSoup(res.text, "html.parser")

    # Find first song result link
    link = soup.select_one("table.table a[href*='/tabs/']")
    if not link:
        return None

    song_url = "https://www.azchords.com" + link["href"]
    song_res = requests.get(song_url, headers=_HEADERS, timeout=10)
    if not song_res.ok:
        return None

    song_soup = BeautifulSoup(song_res.text, "html.parser")
    pre = song_soup.find("pre")
    if not pre:
        return None

    sequence = _extract_sequence(pre.get_text())
    return _build_result(sequence)


def _try_duckduckgo(query: str) -> dict | None:
    """Fallback: generic web search and parse any chord page found."""
    urls = _ddg_urls(f"{query} chords guitar")

    for url in urls[:5]:
        try:
            page = requests.get(url, headers=_HEADERS, timeout=8)
            page_soup = BeautifulSoup(page.text, "html.parser")
            for tag in page_soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            sequence = _extract_sequence(page_soup.get_text())
            result = _build_result(sequence)
            if result and len(result["chord_set"]) >= _MIN_UNIQUE_CHORDS:
                return result
        except Exception:
            continue

    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_clean_lyrics(raw_text: str) -> str | None:
    """
    Extract plain lyrics from a raw chord-sheet text block.

    Removes:
      - Inline chord markers:  [Am], [ch]Am[/ch]
      - Chord-only lines:      C  G  Am  F  /  ( C - G )x2
      - Section labels:        [Intro], [Verso], [Chorus], [Refrão], etc.
      - Metadata lines:        tom:, key:, capo:, bpm:
    """
    # Remove inline chord markers before processing lines
    text = re.sub(r'\[ch\][^\[]*\[/ch\]', '', raw_text)           # UG: [ch]Am[/ch]
    text = re.sub(r'\[/?(?:tab|verse|chorus|bridge|intro|outro)[^\]]*\]', '', text, flags=re.IGNORECASE)

    lyrics_lines: list[str] = []
    for line in text.splitlines():
        # Remove inline [Chord] markers (lacuerda / cifraclub format)
        clean = re.sub(r'\[[A-G][#b]?[^\]]*\]', '', line).strip()
        if not clean:
            continue
        # Remove section label prefix [Intro], [VERSO], [Refrão], etc.
        clean = re.sub(r'^\[.{1,25}\]\s*', '', clean).strip()
        if not clean:
            continue
        # Skip metadata lines
        if re.match(r'^(tom|key|capo|bpm|afinacao|tuning)\s*:', clean, re.IGNORECASE):
            continue
        # Skip lines with no real words (require ≥2 consecutive letters so "x1" is filtered)
        if not re.search(r'[a-zA-ZáéíóúàèìòùãõñüçÁÉÍÓÚÀÈÌÒÙÃÕÑÜÇ]{2,}', clean):
            continue
        # Normalise chord-separator characters, then check if all tokens are chords
        tokens = [t for t in re.sub(r'[()|\-x\d]', ' ', clean).split() if t]
        if tokens and all(_CHORD_RE.fullmatch(t) for t in tokens):
            continue
        lyrics_lines.append(clean)

    return "\n".join(lyrics_lines) if lyrics_lines else None


def _extract_sequence(text: str) -> list[str]:
    """Extract ordered chord names from raw text (tab/chord sheet format)."""
    return _CHORD_RE.findall(text)


def _build_result(sequence: list[str]) -> dict | None:
    if not sequence:
        return None

    # Count occurrences — filter single mentions that are likely false positives
    counts: dict[str, int] = {}
    for c in sequence:
        counts[c] = counts.get(c, 0) + 1

    chord_set = {c for c, n in counts.items() if n >= 2}
    if not chord_set:
        return None

    # Chord sequence only includes chords that passed the frequency filter
    filtered_sequence = [c for c in sequence if c in chord_set]

    return {
        "chord_set":      chord_set,
        "chord_sequence": filtered_sequence,
    }


def _slugify(text: str) -> str:
    """Convert 'The Beatles' → 'the-beatles' for URL construction."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


# ── Chord distance / nearest chord ────────────────────────────────────────────

_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_ENHARMONIC = {
    "Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#",
    "Ab": "G#", "Bb": "A#", "Cb": "B",
}


def _root_and_quality(chord: str) -> tuple[str, str]:
    m = re.match(r'^([A-G][#b]?)(.*)', chord)
    if not m:
        return chord, ""
    root = _ENHARMONIC.get(m.group(1), m.group(1))
    return root, m.group(2)


def _semitone_distance(a: str, b: str) -> int:
    try:
        d = abs(_NOTES.index(a) - _NOTES.index(b))
        return min(d, 12 - d)
    except ValueError:
        return 6


def _nearest_chord(chord: str, valid_chords: set[str]) -> str:
    root, quality = _root_and_quality(chord)
    is_minor = bool(re.search(r'\bm(?!aj)', quality))

    def score(c: str) -> tuple[int, int]:
        cr, cq = _root_and_quality(c)
        c_minor = bool(re.search(r'\bm(?!aj)', cq))
        semi = _semitone_distance(root, cr)
        penalty = 0 if is_minor == c_minor else 3
        return (semi + penalty, semi)

    return min(valid_chords, key=score)


# ── UG chord sheet parser ─────────────────────────────────────────────────────

_UG_CHORD_TAG = re.compile(
    r'\[ch\]([A-G][#b]?(?:maj7?|min7?|m7?|dim7?|aug|sus[24]?|add9?|7|9|11|13)?(?:/[A-G][#b]?)?)\[/ch\]'
)
_GUITAR_TAB_LINE = re.compile(r'[eEBGDAd]\s*\|[-0-9hpb/\\|]+')
_REAL_WORD = re.compile(r'[A-Za-zÀ-ÿ]{3,}')


def parse_ug_chord_sheet(raw_content: str) -> list[tuple[str | None, str, bool]]:
    """
    Parse a UG chord sheet (raw wiki_tab content) into (chord, word, is_line_start) pairs.

    UG stores chord sheets as [tab]...[/tab] blocks where chords appear on a
    dedicated line ABOVE the lyric line, positioned to show where each chord
    starts. Character position in the chord line maps to character position in
    the lyric line (monospace alignment).

    Returns one tuple per lyric word:
      chord         — chord that starts at this word, or None
      word          — the word text (punctuation included)
      is_line_start — True for the first word of each lyric line
    """
    result: list[tuple[str | None, str, bool]] = []

    for tab_match in re.finditer(r'\[tab\](.*?)\[/tab\]', raw_content, re.DOTALL):
        block_pairs = _parse_tab_block(tab_match.group(1))
        result.extend(block_pairs)

    return result


def _parse_tab_block(block: str) -> list[tuple[str | None, str, bool]]:
    """Process one [tab]...[/tab] block."""
    lines = block.strip().splitlines()
    result: list[tuple[str | None, str, bool]] = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Skip guitar tablature lines (e|---, B|---, etc.)
        if _GUITAR_TAB_LINE.search(line):
            i += 1
            continue

        has_chords = bool(_UG_CHORD_TAG.search(line))
        clean      = _UG_CHORD_TAG.sub("", line).strip()
        has_lyrics = bool(_REAL_WORD.search(clean))

        # Skip section labels like [Intro], [Verse 1], [Chorus], [Bridge]
        if re.match(r'^\[.{1,25}\]$', clean):
            i += 1
            continue

        # Skip chord-box diagram lines like "D/A    x-0-4-2-3-2"
        if re.search(r'[0-9x]-[0-9x]-[0-9x]', clean):
            i += 1
            continue

        if has_chords and not has_lyrics:
            # Pure chord line → look at next non-tab line for lyrics
            j = i + 1
            while j < len(lines) and _GUITAR_TAB_LINE.search(lines[j]):
                j += 1

            if j < len(lines):
                next_line  = lines[j].rstrip()
                next_clean = _UG_CHORD_TAG.sub("", next_line).strip()
                next_has_lyrics = bool(_REAL_WORD.search(next_clean))
                next_has_chords = bool(_UG_CHORD_TAG.search(next_line))

                if next_has_lyrics and not next_has_chords:
                    # Classic format: chord line above lyric line
                    pairs = _match_chords_to_lyrics(line, next_line)
                    for k, (chord, word) in enumerate(pairs):
                        result.append((chord, word, k == 0))
                    i = j + 1
                    continue

        elif has_chords and has_lyrics:
            # Inline format: [ch]Am[/ch]word on the same line
            pairs = _parse_inline_line(line)
            for k, (chord, word) in enumerate(pairs):
                result.append((chord, word, k == 0))

        elif has_lyrics:
            # Plain lyric line (no chords on this line)
            for k, word in enumerate(clean.split()):
                result.append((None, word, k == 0))

        i += 1

    return result


def _match_chords_to_lyrics(chord_line: str, lyric_line: str) -> list[tuple[str | None, str]]:
    """
    Map chords from a chord line to words in the lyric line using visual column position.

    Uses a greedy sequential approach: iterate words left-to-right; assign the next
    unassigned chord to a word when the chord's visual column is within 5 characters
    of the word's start column.  This handles the ±1 column drift common in UG sheets
    (e.g. "Bm" at col 6 paired with "boy" starting at col 5).
    """
    # Build (visual_column, chord) list — chord tags are invisible so they don't advance col
    chord_cols: list[tuple[int, str]] = []
    col = 0
    pos = 0
    s   = chord_line
    while pos < len(s):
        m = _UG_CHORD_TAG.match(s, pos)
        if m:
            chord_cols.append((col, m.group(1)))
            pos = m.end()
        else:
            col += 1
            pos += 1

    words = [(m.start(), m.group()) for m in re.finditer(r'\S+', lyric_line)]
    if not words:
        return []

    result: list[tuple[str | None, str]] = [(None, w) for _, w in words]
    ci = 0  # next unassigned chord index

    for wi, (wcol, _) in enumerate(words):
        if ci >= len(chord_cols):
            break
        ccol, cname = chord_cols[ci]
        if abs(wcol - ccol) <= 5:
            result[wi] = (cname, words[wi][1])
            ci += 1

    return result


def _parse_inline_line(line: str) -> list[tuple[str | None, str]]:
    """Parse inline [ch]Am[/ch]word format into (chord, word) pairs."""
    parts = re.split(r'(\[ch\][^\[]*\[/ch\])', line)
    pending: str | None = None
    pairs: list[tuple[str | None, str]] = []

    for part in parts:
        m = _UG_CHORD_TAG.fullmatch(part.strip())
        if m:
            pending = m.group(1)
        else:
            for i, word in enumerate(part.split()):
                if re.search(r'[A-Za-zÀ-ÿ0-9]', word):
                    pairs.append((pending if i == 0 else None, word))
                    if i == 0:
                        pending = None

    return pairs
