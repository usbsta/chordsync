"use client";

import { useEffect, useRef, useState } from "react";
import type { ChordEvent, JobResult, WordEvent } from "@/lib/types";
import { useMultiTrackPlayer } from "@/hooks/useMultiTrackPlayer";
import StemMixer from "./StemMixer";

interface Props {
  audioUrl: string;
  result: JobResult;
}

interface AnnotatedWord {
  word: WordEvent;
  chord: string | null;
}

interface Line {
  words: AnnotatedWord[];
  startTime: number;
  endTime: number;
}

// ── Pre-processing ─────────────────────────────────────────────────────────────

function annotateWordsWithChords(words: WordEvent[], chords: ChordEvent[]): AnnotatedWord[] {
  const annotated: AnnotatedWord[] = words.map((w) => ({ word: w, chord: null }));
  for (const event of chords) {
    let bestIdx = -1;
    let bestDiff = Infinity;
    for (let i = 0; i < words.length; i++) {
      const diff = Math.abs(words[i].start - event.time);
      if (diff < bestDiff && diff < 0.5) { bestDiff = diff; bestIdx = i; }
    }
    if (bestIdx >= 0 && annotated[bestIdx].chord === null) {
      annotated[bestIdx].chord = event.chord;
    }
  }
  return annotated;
}

function groupIntoLines(words: AnnotatedWord[]): Line[] {
  if (words.length === 0) return [];
  const lines: Line[] = [];
  let current: AnnotatedWord[] = [];
  const hasNewlineMarkers = words.some((w) => w.word.newline);

  for (let i = 0; i < words.length; i++) {
    const aw   = words[i];
    const next = words[i + 1];
    const breakAfter = hasNewlineMarkers
      ? (next?.word.newline === true)
      : ((next ? next.word.start - aw.word.end > 0.7 : true) || current.length >= 7);
    current.push(aw);
    if (breakAfter || !next) {
      lines.push({ words: current, startTime: current[0].word.start, endTime: current[current.length - 1].word.end });
      current = [];
    }
  }
  return lines;
}

function getCurrentChord(chords: ChordEvent[], time: number): string {
  let current = chords[0]?.chord ?? "—";
  for (const e of chords) {
    if (e.time <= time) current = e.chord;
    else break;
  }
  return current;
}

function getCurrentLineIndex(lines: Line[], time: number): number {
  let idx = 0;
  for (let i = 0; i < lines.length; i++) {
    if (time >= lines[i].startTime) idx = i;
    else break;
  }
  return idx;
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function Player({ audioUrl, result }: Props) {
  const activeLineRef = useRef<HTMLDivElement>(null);
  const player        = useMultiTrackPlayer(result.stems ?? null);
  const audioRef      = useRef<HTMLAudioElement>(null);
  const [fallbackTime, setFallbackTime]       = useState(0);
  const [fallbackPlaying, setFallbackPlaying] = useState(false);

  const [audioDuration, setAudioDuration] = useState<number>(result.duration ?? 0);

  const hasStemsFallback = !result.stems;
  const currentTime = hasStemsFallback ? fallbackTime : player.currentTime;
  const duration    = hasStemsFallback ? audioDuration : player.duration;
  const playing     = hasStemsFallback ? fallbackPlaying : player.playing;

  const lines = useRef<Line[]>([]);
  if (lines.current.length === 0 && result.words.length > 0) {
    lines.current = groupIntoLines(annotateWordsWithChords(result.words, result.chords));
  }

  useEffect(() => {
    if (result.stems) player.load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!hasStemsFallback) return;
    const audio = audioRef.current;
    if (!audio) return;
    const onTime     = () => setFallbackTime(audio.currentTime);
    const onPlay     = () => setFallbackPlaying(true);
    const onPause    = () => setFallbackPlaying(false);
    // Read duration from the audio element — result.duration may be absent or 0
    const onMetadata = () => { if (audio.duration > 0) setAudioDuration(audio.duration); };
    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("loadedmetadata", onMetadata);
    // Fire immediately if already loaded
    if (audio.readyState >= 1 && audio.duration > 0) setAudioDuration(audio.duration);
    return () => {
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("loadedmetadata", onMetadata);
    };
  }, [hasStemsFallback]);

  const lineIdx = getCurrentLineIndex(lines.current, currentTime);
  useEffect(() => {
    activeLineRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [lineIdx]);

  function togglePlay() {
    if (hasStemsFallback) {
      const audio = audioRef.current;
      if (!audio) return;
      playing ? audio.pause() : audio.play();
    } else {
      player.toggle();
    }
  }

  function handleSeek(ratio: number) {
    const t = ratio * duration;
    if (hasStemsFallback) {
      const audio = audioRef.current;
      if (audio) audio.currentTime = t;
    } else {
      player.seek(t);
    }
  }

  const chord    = getCurrentChord(result.chords, currentTime);
  const progress = duration > 0 ? Math.min((currentTime / duration) * 100, 100) : 0;

  return (
    <div className="flex flex-col gap-4">
      {hasStemsFallback && <audio ref={audioRef} src={audioUrl} />}

      {/* ── Song info card ── */}
      <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl p-5 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          {/* Album art placeholder */}
          <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-violet-900 to-zinc-800 flex items-center justify-center text-2xl flex-shrink-0 shadow-lg">
            🎵
          </div>
          <div className="flex-1 min-w-0">
            {result.song ? (
              <>
                <p className="text-white font-bold text-lg leading-tight truncate">{result.song.title}</p>
                <p className="text-zinc-400 text-sm truncate">{result.song.artist}</p>
              </>
            ) : (
              <p className="text-zinc-400 text-sm italic">Unknown song</p>
            )}
            {result.chord_set && (
              <p className="text-violet-500 text-xs mt-0.5 truncate">
                {result.chord_set.join("  ·  ")}
              </p>
            )}
          </div>
          {/* Current chord — prominent */}
          <div className="text-right flex-shrink-0">
            <p className="text-xs text-zinc-600 uppercase tracking-widest mb-0.5">Now</p>
            <p className="text-4xl font-black text-amber-400 tabular-nums leading-none" style={{
              textShadow: "0 0 30px rgba(251,191,36,0.4)"
            }}>
              {chord}
            </p>
          </div>
        </div>
      </div>

      {/* ── Lyrics ── */}
      <div
        className="bg-zinc-900/60 border border-zinc-800 rounded-2xl overflow-hidden backdrop-blur-sm"
        style={{
          maskImage: "linear-gradient(to bottom, transparent 0%, black 15%, black 85%, transparent 100%)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 15%, black 85%, transparent 100%)",
        }}
      >
        <div className="h-72 overflow-hidden">
          <div className="flex flex-col items-center gap-7 py-28 px-4">
            {lines.current.length === 0 ? (
              <p className="text-zinc-600 italic text-sm">No lyrics detected</p>
            ) : (
              lines.current.map((line, li) => {
                const isActive = li === lineIdx;
                const isPast   = li < lineIdx;
                return (
                  <div
                    key={li}
                    ref={isActive ? activeLineRef : null}
                    className={`flex flex-wrap justify-center gap-x-2 gap-y-4 transition-all duration-500
                      ${isActive ? "opacity-100 scale-100" : isPast ? "opacity-20 scale-95" : "opacity-25 scale-95"}`}
                  >
                    {line.words.map((aw, wi) => {
                      const isActiveWord = isActive && currentTime >= aw.word.start && currentTime <= aw.word.end;
                      return (
                        <div key={wi} className="flex flex-col items-start gap-0.5">
                          <span className={`text-xs font-bold tracking-wide h-4 transition-colors ${
                            isActive ? "text-violet-400" : "text-violet-800"
                          }`}>
                            {aw.chord ?? ""}
                          </span>
                          <span className={`font-semibold leading-tight transition-all duration-100 ${
                            isActive
                              ? isActiveWord
                                ? "text-amber-300 text-2xl"
                                : "text-white text-xl"
                              : isPast
                              ? "text-zinc-600 text-lg"
                              : "text-zinc-500 text-lg"
                          }`}>
                            {aw.word.word}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* ── Playback controls card ── */}
      <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl px-5 py-4 flex flex-col gap-3 backdrop-blur-sm">
        {/* Progress bar */}
        <div
          className="w-full h-1.5 bg-zinc-800 rounded-full cursor-pointer group relative"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            handleSeek((e.clientX - rect.left) / rect.width);
          }}
        >
          <div
            className="h-1.5 bg-gradient-to-r from-violet-600 to-violet-400 rounded-full relative transition-none"
            style={{ width: `${progress}%` }}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3.5 h-3.5 bg-white rounded-full shadow-md opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </div>

        {/* Time + play button */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-500 tabular-nums w-10">{formatTime(currentTime)}</span>

          <button
            onClick={togglePlay}
            disabled={!!result.stems && !player.loaded}
            className="w-12 h-12 rounded-full bg-violet-600 hover:bg-violet-500 active:bg-violet-700 flex items-center justify-center text-white text-lg transition-all shadow-lg shadow-violet-900/60 disabled:opacity-40 hover:scale-105 active:scale-95"
          >
            {result.stems && !player.loaded ? (
              <span className="text-sm animate-spin">⏳</span>
            ) : playing ? "⏸" : "▶"}
          </button>

          <span className="text-xs text-zinc-500 tabular-nums w-10 text-right">{formatTime(duration)}</span>
        </div>
      </div>

      {/* ── Stem mixer ── */}
      {result.stems && (
        <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl p-5 backdrop-blur-sm">
          <StemMixer
            stems={player.stems}
            onVolumeChange={player.setStemVolume}
            onToggleMute={player.toggleMute}
          />
        </div>
      )}

      {/* ── Chord map ── */}
      <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl p-5 backdrop-blur-sm">
        <p className="text-xs font-bold text-zinc-600 uppercase tracking-widest mb-3">Chord progression</p>
        <div className="flex gap-1.5 flex-wrap">
          {result.chords
            .filter((_, i) => i === 0 || result.chords[i].chord !== result.chords[i - 1].chord)
            .map((event, i, arr) => {
              const isActive = currentTime >= event.time &&
                (i === arr.length - 1 || currentTime < arr[i + 1].time);
              return (
                <button
                  key={i}
                  onClick={() => handleSeek(event.time / duration)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-mono font-bold transition-all ${
                    isActive
                      ? "bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/50 scale-105"
                      : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
                  }`}
                >
                  {event.chord}
                </button>
              );
            })}
        </div>
      </div>
    </div>
  );
}
