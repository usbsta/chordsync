import os
import re
import tempfile
from pathlib import Path

try:
    import yt_dlp
    _YTDLP_AVAILABLE = True
except ImportError:
    _YTDLP_AVAILABLE = False


def _write_cookies_file() -> str | None:
    """
    Write YouTube cookies from the YOUTUBE_COOKIES env var to a temp file.
    yt-dlp requires cookies as a file path, not a string.
    Returns the temp file path, or None if no cookies are configured.
    """
    cookies_content = os.getenv("YOUTUBE_COOKIES", "").strip()
    if not cookies_content:
        return None
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tmp.write(cookies_content)
    tmp.flush()
    tmp.close()
    return tmp.name


def download_audio(artist: str, title: str, output_dir: str) -> tuple[str, str, str]:
    """
    Search YouTube for '{artist} {title}', download the best audio result,
    convert it to WAV, and return (wav_path, resolved_artist, resolved_title).

    The resolved artist/title are extracted from the actual YouTube video title,
    so typos or approximate queries are corrected automatically.
    Falls back to the original artist/title if parsing fails.

    Requires yt-dlp and ffmpeg to be installed.
    Uses 'ytsearch1:' to take the first YouTube search result automatically.
    """
    if not _YTDLP_AVAILABLE:
        raise RuntimeError("yt-dlp is not installed. Run: pip install yt-dlp")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    query = f"ytsearch1:{artist} {title} official audio"

    video_info: dict = {}

    cookies_file = _write_cookies_file()

    # Try without cookies first using web_embedded (no PO token, no cookie conflicts).
    # Cookies can interfere with web_embedded and cause it to return no audio formats.
    # tv is only added as fallback when cookies are present (it needs them).
    clients_no_cookies = ["web_embedded"]
    clients_with_cookies = ["tv", "web_embedded"]

    ydl_opts = {
        "format": "bestaudio/best",
        "extractor_args": {
            "youtube": {
                "player_client": clients_with_cookies if cookies_file else clients_no_cookies
            }
        },
        "outtmpl": str(out_dir / "upload.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "0",
        }],
        "quiet": False,
        "verbose": False,
        "no_warnings": False,
    }

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # extract_info with download=False first to grab metadata, then download
        info = ydl.extract_info(query, download=False)
        if info and "entries" in info and info["entries"]:
            video_info = info["entries"][0] or {}
        elif info:
            video_info = info
        ydl.download([query])

    wav_path = out_dir / "upload.wav"
    if not wav_path.exists():
        matches = list(out_dir.glob("*.wav"))
        if not matches:
            raise RuntimeError(f"Download succeeded but no WAV found in {output_dir}")
        wav_path = matches[0]

    resolved_artist, resolved_title = _parse_video_title(
        video_info.get("title", ""),
        video_info.get("artist", ""),
        video_info.get("track", ""),
        artist,
        title,
    )
    print(f"[youtube] Resolved: '{resolved_artist}' — '{resolved_title}'")
    return str(wav_path), resolved_artist, resolved_title


def _parse_video_title(
    yt_title: str,
    yt_artist: str,
    yt_track: str,
    fallback_artist: str,
    fallback_title: str,
) -> tuple[str, str]:
    """
    Extract artist and song title from YouTube metadata.

    yt-dlp populates 'artist' and 'track' fields for music videos from
    YouTube Music metadata. When those are missing we parse the video title
    using common patterns like 'Artist - Song (Official Audio)'.
    """
    # YouTube Music metadata is the most reliable source
    if yt_artist and yt_track:
        return yt_artist.strip(), yt_track.strip()

    if yt_title:
        # Remove common suffixes: (Official Audio), (Official Video), [HD], etc.
        clean = re.sub(
            r'\s*[\(\[](official\s*(audio|video|music\s*video|lyric\s*video)?'
            r'|lyrics?|hd|hq|4k|remaster(ed)?|feat\.?.*?)\s*[\)\]]',
            '', yt_title, flags=re.IGNORECASE,
        ).strip()

        # Most common format: "Artist - Song" or "Artist – Song"
        parts = re.split(r'\s+[-–]\s+', clean, maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

    # Nothing parseable — return the original user query unchanged
    return fallback_artist, fallback_title
