import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.v1.jobs import router as jobs_router
from api.v1.songs import router as songs_router
from config import settings  # noqa: E402 — used in app.mount below

app = FastAPI(
    title="ChordSync API",
    description="Audio processing service: chord detection + lyric transcription",
    version="0.1.0",
)

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
