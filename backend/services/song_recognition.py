import asyncio

# ShazamIO uses the same fingerprinting engine as Shazam — no API key needed
try:
    from shazamio import Shazam
    _SHAZAM_AVAILABLE = True
except ImportError:
    _SHAZAM_AVAILABLE = False


def identify_song(wav_path: str) -> dict | None:
    """
    Identify a song from an audio file using the Shazam engine.

    Sends a short audio fingerprint (not the full file) to Shazam's servers.
    Returns a dict with 'title', 'artist', and optionally 'genre', or None
    if the song could not be identified.
    """
    if not _SHAZAM_AVAILABLE:
        print("[recognition] ShazamIO not installed — skipping identification")
        return None

    try:
        result = asyncio.run(_recognize(wav_path))
        return result
    except Exception as e:
        print(f"[recognition] Shazam lookup failed: {e}")
        return None


async def _recognize(wav_path: str) -> dict | None:
    shazam = Shazam()
    result = await shazam.recognize(wav_path)

    track = result.get("track")
    if not track:
        return None

    return {
        "title":  track.get("title", "Unknown"),
        "artist": track.get("subtitle", "Unknown"),
        "genre":  track.get("genres", {}).get("primary", None),
    }
