from enum import Enum
from typing import Optional
from pydantic import BaseModel


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class ChordEvent(BaseModel):
    """A chord detected at a specific time in the audio."""
    time: float    # seconds from the start
    chord: str     # e.g. "Am", "G", "C", "F#m"


class WordEvent(BaseModel):
    """A transcribed word with its start and end time."""
    start: float        # seconds
    end: float          # seconds
    word: str
    newline: bool = False   # True on the first word of each lyrics line (for display)


class SongInfo(BaseModel):
    """Metadata about the identified song."""
    title: str
    artist: str
    genre: str | None = None


class JobResult(BaseModel):
    """Full result returned when a job is done."""
    job_id: str
    duration: float              # total audio duration in seconds
    chords: list[ChordEvent]
    words: list[WordEvent]
    song: SongInfo | None = None          # identified song info, if found
    chord_set: list[str] | None = None   # unique chords used in the song
    stems: dict[str, str] | None = None  # stem_name → URL


class JobResponse(BaseModel):
    """Response returned after submitting a job or polling its status."""
    job_id: str
    status: JobStatus
    result: Optional[JobResult] = None
    error: Optional[str] = None
