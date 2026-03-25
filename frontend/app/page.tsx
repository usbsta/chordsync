"use client";

import { useState, useCallback } from "react";
import UploadZone from "@/components/UploadZone";
import Player from "@/components/Player";
import { submitJob, submitFromSearch, pollJob } from "@/lib/api";
import type { JobResult } from "@/lib/types";

type Mode     = "search" | "upload";
type AppState = "idle" | "loading" | "done" | "error";

const LOADING_STEPS = [
  { icon: "⬇️", msg: "Downloading audio from YouTube..." },
  { icon: "🎸", msg: "Separating guitar, vocals & drums..." },
  { icon: "🎵", msg: "Detecting chord progressions..." },
  { icon: "📝", msg: "Syncing lyrics to audio..." },
  { icon: "✨", msg: "Almost ready..." },
];

export default function HomePage() {
  const [mode, setMode]         = useState<Mode>("search");
  const [state, setState]       = useState<AppState>("idle");
  const [stepIdx, setStepIdx]   = useState(0);
  const [statusMsg, setStatus]  = useState("");
  const [artist, setArtist]     = useState("");
  const [title, setTitle]       = useState("");
  const [result, setResult]     = useState<JobResult | null>(null);
  const [audioUrl, setAudioUrl] = useState("");

  async function runJob(jobId: string) {
    const job = await waitForJob(jobId, (msg, idx) => {
      setStatus(msg);
      setStepIdx(idx);
    });
    if (job.status === "done" && job.result) {
      setResult(job.result);
      setState("done");
    } else {
      throw new Error(job.error ?? "Processing failed");
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!artist.trim() || !title.trim()) return;
    setState("loading");
    setStepIdx(0);
    setStatus(LOADING_STEPS[0].msg);
    try {
      const jobId = await submitFromSearch(artist.trim(), title.trim());
      await runJob(jobId);
    } catch (err) {
      setState("error");
      setStatus(err instanceof Error ? err.message : "Unknown error");
    }
  }

  const handleFile = useCallback(async (file: File) => {
    setState("loading");
    setStepIdx(1);
    setStatus(LOADING_STEPS[1].msg);
    setAudioUrl(URL.createObjectURL(file));
    try {
      const jobId = await submitJob(file, artist.trim(), title.trim());
      await runJob(jobId);
    } catch (err) {
      setState("error");
      setStatus(err instanceof Error ? err.message : "Unknown error");
    }
  }, [artist, title]); // eslint-disable-line react-hooks/exhaustive-deps

  function reset() {
    setState("idle");
    setResult(null);
    setAudioUrl("");
    setStepIdx(0);
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Ambient background glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-violet-900/20 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[200px] bg-amber-900/10 rounded-full blur-3xl" />
      </div>

      <main className="relative max-w-3xl mx-auto px-4 py-12 flex flex-col gap-8">

        {/* ── Header ── */}
        <header className="text-center py-6">
          <div className="flex items-center justify-center gap-3 mb-3">
            <span className="text-5xl drop-shadow-lg">🎸</span>
            <h1 className="text-6xl font-black tracking-tight">
              <span className="text-white">Chord</span>
              <span className="bg-gradient-to-r from-violet-400 to-violet-300 bg-clip-text text-transparent">Sync</span>
            </h1>
          </div>
          <p className="text-zinc-500 text-sm font-medium tracking-widest uppercase">
            Chords &nbsp;·&nbsp; Lyrics &nbsp;·&nbsp; Synchronized
          </p>
          {/* Guitar strings decoration */}
          <div className="flex justify-center gap-3 mt-5">
            {[3, 5, 7, 5, 3].map((h, i) => (
              <div key={i} className="bg-zinc-700 rounded-full" style={{ width: 1 + i * 0.3, height: h * 4 }} />
            ))}
          </div>
        </header>

        {/* ── Input area ── */}
        {(state === "idle" || state === "error") && (
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl p-6 flex flex-col gap-5 shadow-2xl backdrop-blur-sm">

            {/* Mode tabs */}
            <div className="flex bg-zinc-950 rounded-xl p-1 gap-1">
              {(["search", "upload"] as Mode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => { setMode(m); setState("idle"); }}
                  className={`flex-1 py-2.5 rounded-lg text-sm font-semibold transition-all duration-200 ${
                    mode === m
                      ? "bg-violet-600 text-white shadow-lg shadow-violet-900/50"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {m === "search" ? "🔍  Search by name" : "🎵  Upload audio"}
                </button>
              ))}
            </div>

            {/* Artist + title fields */}
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-1.5">
                  Artist{mode === "upload" ? " (optional)" : ""}
                </label>
                <input
                  type="text"
                  value={artist}
                  onChange={(e) => setArtist(e.target.value)}
                  placeholder="e.g. Nirvana"
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500/20 transition-all"
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-1.5">
                  Song title{mode === "upload" ? " (optional)" : ""}
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. About a Girl"
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500/20 transition-all"
                />
              </div>
            </div>

            {mode === "search" && (
              <form onSubmit={handleSearch}>
                <button
                  type="submit"
                  disabled={!artist.trim() || !title.trim()}
                  className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 active:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm tracking-wide transition-all shadow-lg shadow-violet-900/40 hover:shadow-violet-800/60"
                >
                  Find on YouTube &amp; analyze
                </button>
              </form>
            )}

            {mode === "upload" && (
              <UploadZone onFile={handleFile} disabled={false} />
            )}

            {state === "error" && (
              <div className="bg-red-950/40 border border-red-800/50 rounded-xl px-4 py-3">
                <p className="text-red-400 text-sm text-center">{statusMsg}</p>
              </div>
            )}
          </div>
        )}

        {/* ── Loading ── */}
        {state === "loading" && (
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl p-12 flex flex-col items-center gap-6 shadow-2xl backdrop-blur-sm">
            <div className="relative w-20 h-20">
              <div className="absolute inset-0 rounded-full border-4 border-zinc-800" />
              <div className="absolute inset-0 rounded-full border-4 border-violet-500 border-t-transparent animate-spin" />
              <span className="absolute inset-0 flex items-center justify-center text-3xl">
                {LOADING_STEPS[stepIdx]?.icon}
              </span>
            </div>
            <div className="text-center">
              <p className="text-white font-semibold text-lg">{statusMsg}</p>
              <p className="text-zinc-500 text-xs mt-1 tracking-wide">
                Stem separation + ML analysis takes 1–2 min
              </p>
            </div>
            {/* Step progress dots */}
            <div className="flex items-center gap-2">
              {LOADING_STEPS.map((_, i) => (
                <div
                  key={i}
                  className={`h-1.5 rounded-full transition-all duration-500 ${
                    i === stepIdx
                      ? "w-8 bg-violet-500"
                      : i < stepIdx
                      ? "w-2 bg-violet-800"
                      : "w-2 bg-zinc-700"
                  }`}
                />
              ))}
            </div>
          </div>
        )}

        {/* ── Result ── */}
        {state === "done" && result && (
          <>
            <Player audioUrl={audioUrl} result={result} />
            <button
              onClick={reset}
              className="text-zinc-600 hover:text-zinc-400 text-sm text-center transition-colors py-2 tracking-wide"
            >
              ← {mode === "search" ? "Search another song" : "Upload another song"}
            </button>
          </>
        )}

      </main>
    </div>
  );
}

async function waitForJob(
  jobId: string,
  onStep: (msg: string, idx: number) => void
): Promise<Awaited<ReturnType<typeof pollJob>>> {
  let i = 0;
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const job = await pollJob(jobId);
        const idx = i % LOADING_STEPS.length;
        onStep(LOADING_STEPS[idx].msg, idx);
        i++;
        if (job.status === "done" || job.status === "failed") {
          clearInterval(interval);
          resolve(job);
        }
      } catch (err) {
        clearInterval(interval);
        reject(err);
      }
    }, 3000);
  });
}
