import sys
import subprocess
from pathlib import Path

from config import settings

# Stems produced by the 6-stem model
STEM_NAMES = ["guitar", "vocals", "drums", "bass", "piano", "other"]

# Demucs model — htdemucs_6s separates guitar as its own stem
# htdemucs (4-stem) groups guitar inside "other"; 6s is what we need
MODEL_NAME = "htdemucs_6s"


def separate_stems(wav_path: str, job_id: str) -> dict[str, str]:
    """
    Run Demucs on a WAV file to separate it into individual stems.

    Demucs htdemucs_6s outputs 6 stems:
      guitar, vocals, drums, bass, piano, other

    Playing all stems together at full volume recreates the original mix.
    The user can then isolate or boost individual instruments.

    Output files land at:
      storage/{job_id}/stems/{MODEL_NAME}/audio/{stem}.wav

    Returns a dict mapping stem name → absolute file path.
    Downloads the model (~800MB) on first run — subsequent runs are cached.
    """
    stems_out = Path(settings.storage_path) / job_id / "stems"
    stems_out.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable, "-m", "demucs",
            "--name", MODEL_NAME,
            "--out", str(stems_out),
            wav_path,
        ],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        # Surface the real demucs error so it shows up in the API response
        raise RuntimeError(
            f"Demucs failed (exit {proc.returncode}):\n"
            f"STDOUT: {proc.stdout[-2000:]}\n"
            f"STDERR: {proc.stderr[-2000:]}"
        )

    # Demucs names the subfolder after the input file stem ("audio")
    track_name = Path(wav_path).stem
    output_dir = stems_out / MODEL_NAME / track_name

    result: dict[str, str] = {}
    for stem in STEM_NAMES:
        path = output_dir / f"{stem}.wav"
        if path.exists():
            result[stem] = str(path)

    return result


def stem_url(job_id: str, stem_name: str) -> str:
    """
    Build the HTTP URL at which a stem file is served.
    FastAPI mounts /storage as a static directory.
    """
    return f"/storage/{job_id}/stems/{MODEL_NAME}/audio/{stem_name}.wav"
