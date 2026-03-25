import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
import aiofiles
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File

from config import settings
from models.job import JobResponse, JobResult, JobStatus, SongInfo
from utils.audio import get_audio_duration, prepare_audio, validate_file_size
from services.chord_detection import detect_chords
from services.transcription import (
    transcribe_audio, words_from_lyrics, parse_lrc, build_events_from_ug_and_lrc,
)
from services.separation import separate_stems, stem_url
from services.chord_lookup import lookup_chords_full, apply_web_chords, parse_ug_chord_sheet
from services.lyrics_lookup import fetch_lyrics, fetch_synced_lyrics
from services.youtube import download_audio

router = APIRouter(prefix="/jobs", tags=["jobs"])

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}

# In-memory job store — good enough for development.
# In production this would be a database or Redis.
_jobs: dict[str, JobResponse] = {}


def _mix_stems_for_chords(stem_paths: dict[str, str], job_id: str, fallback_wav: str = "") -> str:
    """
    Mix the 'guitar' and 'other' stems into a single WAV for chord detection.

    htdemucs_6s is not always reliable about putting guitar in the 'guitar' stem —
    it depends heavily on the genre and recording style. Mixing both captures
    the harmonic content while excluding vocals, drums, and bass (which would
    corrupt the chord features).

    Falls back to fallback_wav (original mix) when stems are not available.
    """
    stems_to_mix = [s for s in ("guitar", "other") if s in stem_paths]

    if not stems_to_mix:
        # No stems available — use the original audio for chord detection
        return fallback_wav or (list(stem_paths.values())[0] if stem_paths else "")

    if len(stems_to_mix) == 1:
        # Only one stem available, use it directly (no mixing needed)
        return stem_paths[stems_to_mix[0]]

    # Load and sum both stems sample-by-sample
    arrays = []
    sr = None
    for name in stems_to_mix:
        audio, file_sr = sf.read(stem_paths[name])
        arrays.append(audio)
        sr = file_sr

    mixed = np.mean(arrays, axis=0)  # average to keep the same amplitude range

    out_path = Path(settings.storage_path) / job_id / "guitar_other_mix.wav"
    sf.write(str(out_path), mixed, sr)
    return str(out_path)


def _run_pipeline(job_id: str, upload_path: str, artist: str = "", title: str = "") -> None:
    """
    Full processing pipeline.

    Lyrics priority (best → worst accuracy):
      1. Musixmatch / LRCLib synced LRC  → timestamps already embedded, no ML needed
      2. Web plain lyrics (chord sites, lyrics.ovh, AZLyrics) + stable-ts alignment
      3. Whisper transcription            → last resort, only when no web text found

    Chords priority:
      1. Web chord sequence (names) + madmom audio (timing boundaries)
      2. Full madmom / librosa audio analysis (when no web data available)
    """
    _jobs[job_id] = JobResponse(job_id=job_id, status=JobStatus.processing)

    try:
        wav_path = prepare_audio(upload_path, job_id)
        duration = get_audio_duration(wav_path)

        # ── Step 1: fetch chords + lyrics from the web ────────────────────────
        lrc_lyrics:   str | None       = None   # time-synced LRC (best quality)
        web_lyrics:   str | None       = None   # plain text (fallback)
        web_sequence: list[str] | None = None
        raw_content:  str | None       = None   # UG raw content with inline chord markers
        chord_set:    set[str] | None  = None
        song_info:    dict | None      = None

        if artist and title:
            song_info = {"artist": artist, "title": title, "genre": None}
            print(f"[{job_id}] Fetching chords + lyrics from web: {artist} — {title}")

            # Synced lyrics first — if found we skip stable-ts and Whisper entirely
            lrc_lyrics = fetch_synced_lyrics(artist, title)

            online = lookup_chords_full(artist, title)
            if online:
                web_sequence = online.get("chord_sequence")
                chord_set    = online.get("chord_set")
                raw_content  = online.get("raw_content")   # UG inline chord+lyric data
                print(f"[{job_id}] Chords from web: {chord_set}")
                # Plain lyrics from chord sites only needed when no LRC available
                if not lrc_lyrics:
                    web_lyrics = online.get("lyrics")
                    if web_lyrics:
                        print(f"[{job_id}] Plain lyrics bundled with chords ({len(web_lyrics.split())} words)")

            # Last plain-text fallback (lyrics.ovh → AZLyrics)
            if not lrc_lyrics and not web_lyrics:
                web_lyrics = fetch_lyrics(artist, title)
                if web_lyrics:
                    print(f"[{job_id}] Plain lyrics from web ({len(web_lyrics.split())} words)")

        # ── Step 2: separate stems (Demucs) — only when web data is incomplete ─
        #
        # Best path (UG + LRC): chords AND timing come entirely from the web.
        # Demucs is skipped to keep the server lightweight; stem mixer won't
        # be available in this case (planned for client-side in a future phase).
        #
        # All other paths still run Demucs when available for cleaner chord
        # detection, but fall back gracefully to the full mix if it fails.
        needs_stems = not (raw_content and lrc_lyrics)

        stem_paths: dict[str, str] = {}
        if needs_stems:
            try:
                print(f"[{job_id}] Separating stems with Demucs...")
                stem_paths = separate_stems(wav_path, job_id)
            except Exception as exc:
                print(f"[{job_id}] Stem separation unavailable ({exc}) — using full mix")

        vocals_path = stem_paths.get("vocals", wav_path)

        if raw_content and lrc_lyrics:
            print(f"[{job_id}] Best path: UG inline chords + LRC timing")
            ug_pairs = parse_ug_chord_sheet(raw_content)
            words, chords = build_events_from_ug_and_lrc(ug_pairs, lrc_lyrics, duration)

        elif lrc_lyrics:
            print(f"[{job_id}] LRC path: synced lyrics + audio chord boundaries")
            words  = parse_lrc(lrc_lyrics, duration)
            chord_source = _mix_stems_for_chords(stem_paths, job_id, fallback_wav=wav_path)
            if web_sequence:
                audio_events = detect_chords(chord_source)
                chords = apply_web_chords(audio_events, web_sequence)
            else:
                chords = detect_chords(chord_source)

        else:
            # No synced lyrics — still need audio for chords
            chord_source = _mix_stems_for_chords(stem_paths, job_id, fallback_wav=wav_path)
            if web_sequence:
                print(f"[{job_id}] Audio boundaries + web chord names")
                audio_events = detect_chords(chord_source)
                chords = apply_web_chords(audio_events, web_sequence)
            else:
                print(f"[{job_id}] No web chords — full audio chord analysis")
                chords = detect_chords(chord_source)

            if web_lyrics:
                print(f"[{job_id}] Aligning plain web lyrics with stable-ts")
                words = words_from_lyrics(web_lyrics, vocals_path)
            else:
                print(f"[{job_id}] No web lyrics — transcribing with Whisper")
                words = transcribe_audio(vocals_path)

        # ── Step 5: build result ──────────────────────────────────────────────
        stems_urls = {name: stem_url(job_id, name) for name in stem_paths}

        result = JobResult(
            job_id=job_id,
            duration=duration,
            chords=chords,
            words=words,
            song=SongInfo(**song_info) if song_info else None,
            chord_set=sorted(chord_set) if chord_set else None,
            stems=stems_urls,
        )

        # Persist result to disk so it survives a server restart
        result_path = Path(settings.storage_path) / job_id / "result.json"
        result_path.write_text(result.model_dump_json(indent=2))

        _jobs[job_id] = JobResponse(job_id=job_id, status=JobStatus.done, result=result)

    except Exception as exc:
        _jobs[job_id] = JobResponse(
            job_id=job_id,
            status=JobStatus.failed,
            error=str(exc),
        )


@router.post("", response_model=JobResponse, status_code=202)
async def submit_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    artist: str = "",
    title: str = "",
) -> JobResponse:
    """
    Accept an audio file upload and start processing it in the background.
    Optionally pass artist and title to look up chords online.
    Returns a job_id to poll for results.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    content = await file.read()
    if not validate_file_size(len(content)):
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_file_size_mb}MB limit.",
        )

    job_id = str(uuid.uuid4())
    job_dir = Path(settings.storage_path) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    upload_path = str(job_dir / f"upload{suffix}")
    async with aiofiles.open(upload_path, "wb") as f:
        await f.write(content)

    _jobs[job_id] = JobResponse(job_id=job_id, status=JobStatus.pending)

    # FastAPI runs this in a thread after sending the 202 response
    background_tasks.add_task(_run_pipeline, job_id, upload_path, artist, title)

    return _jobs[job_id]


class SearchRequest(BaseModel):
    artist: str
    title: str


def _run_pipeline_from_search(job_id: str, artist: str, title: str) -> None:
    """Download audio from YouTube then run the full processing pipeline."""
    _jobs[job_id] = JobResponse(job_id=job_id, status=JobStatus.processing)
    try:
        job_dir = str(Path(settings.storage_path) / job_id)
        print(f"[{job_id}] Downloading: {artist} — {title}")
        upload_path, resolved_artist, resolved_title = download_audio(artist, title, job_dir)
        # Use the YouTube-resolved title (fixes typos in the user query)
        _run_pipeline(job_id, upload_path, resolved_artist, resolved_title)
    except Exception as exc:
        _jobs[job_id] = JobResponse(
            job_id=job_id, status=JobStatus.failed, error=str(exc)
        )


@router.post("/from-search", response_model=JobResponse, status_code=202)
async def submit_from_search(
    background_tasks: BackgroundTasks,
    request: SearchRequest,
) -> JobResponse:
    """
    Search YouTube for the song, download it, and run the full pipeline.
    Returns a job_id to poll — same flow as uploading a file manually.
    """
    if not request.artist.strip() or not request.title.strip():
        raise HTTPException(status_code=400, detail="Artist and title are required.")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobResponse(job_id=job_id, status=JobStatus.pending)

    background_tasks.add_task(
        _run_pipeline_from_search, job_id, request.artist.strip(), request.title.strip()
    )
    return _jobs[job_id]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Poll the status of a processing job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _jobs[job_id]
