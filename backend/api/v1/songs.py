from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.chord_lookup import lookup_chord_set
from services.lyrics_lookup import fetch_lyrics

router = APIRouter(prefix="/songs", tags=["songs"])


class SearchResult(BaseModel):
    artist: str
    title: str
    lyrics: str | None = None
    chord_set: list[str] | None = None


@router.get("/search", response_model=SearchResult)
async def search_song(
    artist: str = Query(..., description="Artist name"),
    title:  str = Query(..., description="Song title"),
) -> SearchResult:
    """
    Look up a song's chords and lyrics from public online sources.
    No audio file required — returns a static chord sheet.
    """
    chord_set = lookup_chord_set(artist, title)
    lyrics    = fetch_lyrics(artist, title)

    if not chord_set and not lyrics:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find chords or lyrics for '{title}' by '{artist}'.",
        )

    return SearchResult(
        artist=artist,
        title=title,
        lyrics=lyrics,
        chord_set=sorted(chord_set) if chord_set else None,
    )
