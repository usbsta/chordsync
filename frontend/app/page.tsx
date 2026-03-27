"use client";

import { useState, useCallback } from "react";
import UploadZone from "@/components/UploadZone";
import Player from "@/components/Player";
import { submitJob, pollJob } from "@/lib/api";
import type { JobResult } from "@/lib/types";

type AppState = "idle" | "loading" | "done" | "error";

const LOADING_STEPS = [
  { icon: "🎸", msg: "Separating guitar, vocals & drums..." },
  { icon: "🎵", msg: "Detecting chord progressions..." },
  { icon: "📝", msg: "Syncing lyrics to audio..." },
  { icon: "✨", msg: "Almost ready..." },
];

function parseFilename(filename: string): { artist: string; title: string } {
  const name = filename.replace(/\.[^/.]+$/, "").trim();
  // Match "Artist - Title" or "Artist – Title", ignoring leading track numbers
  const match = name.match(/^(?:\d+[\s._-]+)?(.+?)\s+[-–]\s+(.+)$/);
  if (match) {
    const artist = match[1].trim();
    // Strip trailing parentheticals like (Remastered), [Official], etc.
    const title = match[2]
      .replace(/\s*[\(\[](?:remaster(?:ed)?|official|hd|hq|live|feat\.?|ft\.?)[^\)\]]*[\)\]]/gi, "")
      .trim();
    return { artist, title };
  }
  return { artist: "", title: name };
}

export default function HomePage() {
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

  const handleFile = useCallback(async (file: File) => {
    // Auto-fill artist/title from filename if the fields are empty
    const parsed = parseFilename(file.name);
    const resolvedArtist = artist.trim() || parsed.artist;
    const resolvedTitle  = title.trim()  || parsed.title;
    setArtist(resolvedArtist);
    setTitle(resolvedTitle);

    setState("loading");
    setStepIdx(0);
    setStatus(LOADING_STEPS[0].msg);
    setAudioUrl(URL.createObjectURL(file));
    try {
      const jobId = await submitJob(file, resolvedArtist, resolvedTitle);
      await runJob(jobId);
    } catch (err) {
      setState("error");
      setStatus(err instanceof Error ? err.message : "Unknown error");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artist, title]);

  function reset() {
    setState("idle");
    setResult(null);
    setAudioUrl("");
    setStepIdx(0);
    setArtist("");
    setTitle("");
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
          <div className="flex justify-center gap-3 mt-5">
            {[3, 5, 7, 5, 3].map((h, i) => (
              <div key={i} className="bg-zinc-700 rounded-full" style={{ width: 1 + i * 0.3, height: h * 4 }} />
            ))}
          </div>
        </header>

        {/* ── Input area ── */}
        {(state === "idle" || state === "error") && (
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl p-6 flex flex-col gap-5 shadow-2xl backdrop-blur-sm">

            {/* Artist + title fields */}
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-1.5">
                  Artist <span className="normal-case font-normal">(optional)</span>
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
                  Song title <span className="normal-case font-normal">(optional)</span>
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

            <p className="text-zinc-600 text-xs text-center -mt-2">
              Artist &amp; title are detected automatically from the filename — or fill them in for better chord &amp; lyric lookup
            </p>

            <UploadZone onFile={handleFile} disabled={false} />

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
              ← Upload another song
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
