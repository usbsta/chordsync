import re
import unicodedata

import requests
from bs4 import BeautifulSoup, Comment

try:
    import syncedlyrics as _syncedlyrics
    _SYNCEDLYRICS_AVAILABLE = True
except ImportError:
    _SYNCEDLYRICS_AVAILABLE = False

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_MIN_WORDS = 10


def fetch_synced_lyrics(artist: str, title: str) -> str | None:
    """
    Fetch time-synced lyrics in LRC format.

    Tries (in order): Musixmatch, LRCLib, NetEase — all via the `syncedlyrics`
    library which handles auth/scraping for each provider transparently.

    LRC format: [MM:SS.xx] line of lyrics
    Returns the raw LRC string, or None if no synced version is found.
    """
    if not _SYNCEDLYRICS_AVAILABLE:
        print("[lyrics] syncedlyrics not installed — skipping synced lookup")
        return None

    try:
        # syncedlyrics expects the query as "{title} {artist}"
        lrc = _syncedlyrics.search(f"{title} {artist}")
        if lrc and lrc.strip():
            print(f"[lyrics] Synced LRC found for: {title} — {artist}")
            return lrc
    except Exception as e:
        print(f"[lyrics] syncedlyrics search failed: {e}")

    return None


def fetch_lyrics(artist: str, title: str) -> str | None:
    """
    Fetch song lyrics from multiple sources, in priority order.
    Returns the first result with enough words, or None.
    """
    for fetcher in [_from_lyrics_ovh, _from_azlyrics]:
        try:
            result = fetcher(artist, title)
            if result and len(result.split()) >= _MIN_WORDS:
                return result
        except Exception as e:
            print(f"[lyrics] {fetcher.__name__} failed: {e}")
    return None


def _from_lyrics_ovh(artist: str, title: str) -> str | None:
    """lyrics.ovh — free public API, no key required."""
    res = requests.get(
        f"https://api.lyrics.ovh/v1/{artist}/{title}",
        headers=_HEADERS,
        timeout=10,
    )
    if res.ok:
        res.encoding = res.apparent_encoding or "utf-8"
        return res.json().get("lyrics")
    return None


def _from_azlyrics(artist: str, title: str) -> str | None:
    """
    AZLyrics — very wide English-song coverage, no API key needed.

    URL pattern: azlyrics.com/lyrics/{artist_nohyphens}/{title_nohyphens}.html
    The lyrics live in an unclassed <div> that immediately follows the
    licensing comment ("Usage of azlyrics.com content by any third-party...").
    """
    slug_artist = re.sub(r"[^a-z0-9]", "", _slugify(artist))
    slug_title  = re.sub(r"[^a-z0-9]", "", _slugify(title))
    url = f"https://www.azlyrics.com/lyrics/{slug_artist}/{slug_title}.html"

    res = requests.get(url, headers=_HEADERS, timeout=10)
    if not res.ok:
        return None

    soup = BeautifulSoup(res.text, "html.parser")

    # The lyrics block follows the "Sorry about that" licensing comment
    for node in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "Sorry about that" in node:
            lyrics_div = node.find_next_sibling("div")
            if lyrics_div:
                return lyrics_div.get_text("\n").strip()

    return None


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")
