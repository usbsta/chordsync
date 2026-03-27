import asyncio
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.v1.jobs import router as jobs_router, _jobs
from api.v1.songs import router as songs_router
from config import settings

app = FastAPI(
    title="ChordSync API",
    description="Audio processing service: chord detection + lyric transcription",
    version="0.1.0",
)


async def _cleanup_old_jobs() -> None:
    """
    Delete job directories older than 1 hour every 30 minutes.
    Keeps the server storage from accumulating processed audio files.
    """
    while True:
        await asyncio.sleep(1800)
        storage = Path(settings.storage_path)
        if not storage.exists():
            continue
        cutoff = datetime.now() - timedelta(hours=1)
        for job_dir in storage.iterdir():
            if not job_dir.is_dir():
                continue
            if datetime.fromtimestamp(job_dir.stat().st_mtime) < cutoff:
                shutil.rmtree(job_dir, ignore_errors=True)
                _jobs.pop(job_dir.name, None)
                print(f"[cleanup] Removed expired job: {job_dir.name}")


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_cleanup_old_jobs())

# ALLOWED_ORIGINS can be a comma-separated list of URLs in production.
# Defaults to localhost for local development.
_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [o.strip() for o in _origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router, prefix="/api/v1")
app.include_router(songs_router, prefix="/api/v1")

# Serve stem audio files directly — frontend fetches them for the mixer
app.mount("/storage", StaticFiles(directory=settings.storage_path), name="storage")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
