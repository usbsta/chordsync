# ChordSync — CLAUDE.md

## Project Overview

ChordSync is a web application for guitarists that analyzes audio files and displays
detected chords synchronized with lyrics in real time — like a karaoke experience,
but oriented toward chord learning and guitar practice.

The user uploads a song, the backend processes it (chord detection + lyric transcription),
and the frontend plays it back showing chords and lyrics scrolling in sync with the audio.

---

## Architecture

```
chordsync/
├── frontend/          # Next.js app (TypeScript + Tailwind CSS)
│   ├── app/           # Next.js App Router pages
│   ├── components/    # Reusable UI components
│   ├── hooks/         # Custom React hooks (audio playback, sync)
│   └── lib/           # Utilities (time formatting, chord parsing, etc.)
│
├── backend/           # Python FastAPI service
│   ├── api/           # Route handlers
│   ├── services/      # Business logic (chord detection, transcription)
│   ├── models/        # ML model loading and inference
│   └── utils/         # Audio helpers (loading, resampling, etc.)
│
└── CLAUDE.md
```

---

## Tech Stack

### Frontend
- **Framework**: Next.js 14+ with App Router
- **Language**: TypeScript (strict mode)
- **Styling**: Tailwind CSS
- **Audio playback**: Web Audio API (via custom hooks)
- **State management**: Zustand (lightweight, works well with audio state)
- **HTTP client**: fetch / SWR for polling job status

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Audio loading**: librosa, soundfile
- **Chord detection**: madmom or a custom trained model (CQT + CNN/RNN)
- **Lyrics transcription**: OpenAI Whisper (local or API)
- **Lyrics alignment**: forced alignment via WhisperX or aeneas
- **Task queue**: Celery + Redis (for async audio processing jobs)
- **Storage**: local filesystem or S3-compatible (MinIO for local dev)

---

## Key Features (Roadmap)

1. **Audio upload** — drag & drop or file picker, supports MP3/WAV/FLAC
2. **Chord detection** — frame-level chord recognition, displayed as guitar chord names (Am, G, C, F...)
3. **Lyric transcription** — automatic via Whisper, with timestamps per word
4. **Synchronized display** — scrolling lyrics + chord markers above the relevant syllable, karaoke style
5. **Chord diagrams** — optional visual guitar chord fingering diagrams on hover
6. **Playback controls** — play/pause, seek, speed control (0.5x–1.5x)
7. **Export** — export chords + lyrics as .txt or .pdf for practice

---

## Coding Conventions

### General
- All code in **English** (variables, functions, comments, commits)
- Comments explain *why*, not *what*
- No commented-out dead code in commits
- Prefer explicit over clever

### TypeScript (Frontend)
- Strict TypeScript: no `any`, use proper interfaces/types
- File naming: `kebab-case` for files, `PascalCase` for components
- Each component in its own file
- Custom hooks prefixed with `use` (e.g., `useAudioSync`)
- Avoid `useEffect` chains — prefer derived state or Zustand

### Python (Backend)
- Follow PEP 8
- Type hints on all function signatures
- Use `async def` for all FastAPI route handlers
- Pydantic models for all request/response schemas
- No global mutable state — pass dependencies via FastAPI DI

### API Design
- RESTful endpoints under `/api/v1/`
- POST `/api/v1/jobs` — submit audio for processing
- GET `/api/v1/jobs/{job_id}` — poll job status and retrieve results
- Results include: chord timeline `[{time, chord}]` + word timeline `[{start, end, word}]`

---

## Audio Processing Pipeline

```
Audio file
    │
    ▼
Resample to 22050 Hz (mono)
    │
    ├──► Chord Detection
    │       CQT features → model inference → chord labels per frame
    │       Output: [{time_sec: 0.0, chord: "Am"}, ...]
    │
    └──► Lyrics Transcription + Alignment
            Whisper transcription → word-level timestamps
            Output: [{start: 0.0, end: 0.4, word: "Yesterday"}, ...]
    │
    ▼
Merge timelines → JSON result stored per job_id
```

---

## Data Formats

### Chord Timeline
```json
[
  { "time": 0.0,  "chord": "Am" },
  { "time": 2.3,  "chord": "F"  },
  { "time": 4.1,  "chord": "C"  },
  { "time": 5.8,  "chord": "G"  }
]
```

### Word Timeline
```json
[
  { "start": 0.0, "end": 0.3, "word": "Yesterday" },
  { "start": 0.4, "end": 0.6, "word": "all"       }
]
```

---

## Development Setup

### Frontend
```bash
cd frontend
npm install
npm run dev        # starts at http://localhost:3000
```

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Redis (required for job queue)
```bash
docker run -p 6379:6379 redis:alpine
```

### Celery worker
```bash
cd backend
celery -A worker worker --loglevel=info
```

---

## Environment Variables

### Frontend (`frontend/.env.local`)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Backend (`backend/.env`)
```
REDIS_URL=redis://localhost:6379
STORAGE_PATH=./storage
WHISPER_MODEL=base          # tiny | base | small | medium | large
MAX_FILE_SIZE_MB=50
```

---

## Communication Language

- User communicates in **Spanish**
- All code, comments, commits, and file names in **English**
- Explanations and answers to the user in **Spanish**

---

## Notes for Claude

- The user has a background in AI and audio processing — technical depth is welcome
- Prefer accuracy over simplicity in the ML/audio pipeline
- When suggesting ML approaches, explain trade-offs (accuracy vs. latency vs. complexity)
- Keep the frontend simple and functional first — polish later
- Audio sync is the hardest part: prioritize getting timestamps right before worrying about UI beauty
