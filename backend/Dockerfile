FROM python:3.11-slim

# ffmpeg: required by yt-dlp to convert audio to WAV
# libsndfile1: required by soundfile/librosa
# nodejs: required by yt-dlp to solve YouTube signature/n-parameter JS challenges
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-slim.txt .
RUN pip install --no-cache-dir -r requirements-slim.txt

COPY . .

RUN mkdir -p storage

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
