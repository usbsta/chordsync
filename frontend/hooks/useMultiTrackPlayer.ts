"use client";

import { useRef, useState, useCallback, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface StemState {
  volume: number;
  muted: boolean;
}

const DEFAULT_VOLUMES: Record<string, number> = {
  guitar: 1.0,
  vocals: 1.0,
  bass:   1.0,
  drums:  0.8,
  piano:  0.9,
  other:  0.7,
};

export function useMultiTrackPlayer(stemUrls: Record<string, string> | null) {
  // All audio nodes live in these refs — never recreated on re-render
  const ctxRef      = useRef<AudioContext | null>(null);
  const buffersRef  = useRef<Record<string, AudioBuffer>>({});
  const gainRefs    = useRef<Record<string, GainNode>>({});
  const sourcesRef  = useRef<Record<string, AudioBufferSourceNode>>({});
  // Generation counter: if load() is called again while a previous call is
  // still awaiting fetches/decodes, the stale call detects the mismatch and
  // discards its results instead of overwriting the refs with stale nodes.
  const loadGenRef  = useRef(0);

  const startedAtRef = useRef(0);   // ctx.currentTime when playback started
  const offsetRef    = useRef(0);   // seek offset in seconds
  const rafRef       = useRef(0);

  const [loaded,      setLoaded]      = useState(false);
  const [playing,     setPlaying]     = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration,    setDuration]    = useState(0);
  const [stems,       setStems]       = useState<Record<string, StemState>>({});

  // ── Load all stems ────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    if (!stemUrls || Object.keys(stemUrls).length === 0) return;

    // Stamp this invocation — if a newer load() starts before this one
    // finishes, we discard our results to avoid mixing nodes from two contexts.
    const generation = ++loadGenRef.current;

    // Close any previous context cleanly before creating a new one
    if (ctxRef.current) {
      await ctxRef.current.close().catch(() => {});
      ctxRef.current = null;
    }

    const ctx = new AudioContext();
    ctxRef.current = ctx;

    const buffers: Record<string, AudioBuffer> = {};
    const gains:   Record<string, GainNode>    = {};
    const initialStems: Record<string, StemState> = {};

    await Promise.all(
      Object.entries(stemUrls).map(async ([name, relUrl]) => {
        const res = await fetch(API_URL + relUrl);
        const arrayBuf = await res.arrayBuffer();

        // decodeAudioData MUST use the context that will play the audio
        const buffer = await ctx.decodeAudioData(arrayBuf);
        buffers[name] = buffer;

        // GainNode created with the same context — no cross-context issues
        const gain = ctx.createGain();
        gain.gain.value = DEFAULT_VOLUMES[name] ?? 1.0;
        gain.connect(ctx.destination);
        gains[name] = gain;

        initialStems[name] = { volume: DEFAULT_VOLUMES[name] ?? 1.0, muted: false };
      })
    );

    // Stale: a newer load() already replaced the context while we were awaiting
    if (generation !== loadGenRef.current) {
      ctx.close().catch(() => {});
      return;
    }

    buffersRef.current = buffers;
    gainRefs.current   = gains;

    const dur = Object.values(buffers)[0]?.duration ?? 0;
    setDuration(dur);
    setStems(initialStems);
    setLoaded(true);
  }, [stemUrls]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── RAF time tracker ──────────────────────────────────────────────────────
  function startRaf() {
    function tick() {
      const ctx = ctxRef.current;
      if (ctx) {
        setCurrentTime(offsetRef.current + (ctx.currentTime - startedAtRef.current));
      }
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
  }
  function stopRaf() { cancelAnimationFrame(rafRef.current); }

  // ── Start source nodes — all from the SAME context as the GainNodes ───────
  function startSources(fromOffset: number) {
    const ctx = ctxRef.current;
    if (!ctx) return;

    // Stop any currently playing sources (null onended first to avoid spurious callbacks)
    Object.values(sourcesRef.current).forEach(src => {
      src.onended = null;
      try { src.stop(); } catch { /* already stopped */ }
    });
    sourcesRef.current = {};

    const newSources: Record<string, AudioBufferSourceNode> = {};
    const names = Object.keys(buffersRef.current);
    let endedCount = 0;

    for (const [name, buffer] of Object.entries(buffersRef.current)) {
      const gain = gainRefs.current[name];
      if (!gain) continue;

      // Both src and gain come from the same ctx → no InvalidAccessError
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(gain);
      src.start(0, fromOffset);

      // When the last source finishes, stop playback cleanly
      src.onended = () => {
        endedCount++;
        if (endedCount === names.length) {
          stopRaf();
          setPlaying(false);
          setCurrentTime(duration);
          offsetRef.current = 0;
        }
      };

      newSources[name] = src;
    }

    sourcesRef.current = newSources;
    startedAtRef.current = ctx.currentTime;
    offsetRef.current    = fromOffset;
  }

  // ── Play / pause ──────────────────────────────────────────────────────────
  const play = useCallback(async () => {
    const ctx = ctxRef.current;
    if (!ctx || !loaded) return;
    if (ctx.state === "suspended") await ctx.resume();
    startSources(offsetRef.current);
    setPlaying(true);
    startRaf();
  }, [loaded]);

  const pause = useCallback(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    offsetRef.current += ctx.currentTime - startedAtRef.current;
    Object.values(sourcesRef.current).forEach(src => {
      src.onended = null;
      try { src.stop(); } catch {}
    });
    sourcesRef.current = {};
    stopRaf();
    setPlaying(false);
  }, []);

  const toggle = useCallback(() => {
    playing ? pause() : play();
  }, [playing, play, pause]);

  // ── Seek ──────────────────────────────────────────────────────────────────
  const seek = useCallback((toSeconds: number) => {
    offsetRef.current = toSeconds;
    setCurrentTime(toSeconds);
    if (playing) {
      startSources(toSeconds);
      startedAtRef.current = ctxRef.current!.currentTime;
    }
  }, [playing]);

  // ── Per-stem volume ───────────────────────────────────────────────────────
  const setStemVolume = useCallback((name: string, volume: number) => {
    const gain = gainRefs.current[name];
    if (!gain) return;
    gain.gain.value = volume;
    setStems(prev => ({ ...prev, [name]: { ...prev[name], volume, muted: volume === 0 } }));
  }, []);

  const toggleMute = useCallback((name: string) => {
    const gain = gainRefs.current[name];
    if (!gain) return;
    setStems(prev => {
      const cur = prev[name];
      const nowMuted = !cur.muted;
      gain.gain.value = nowMuted ? 0 : cur.volume;
      return { ...prev, [name]: { ...cur, muted: nowMuted } };
    });
  }, []);

  // ── Cleanup ───────────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      stopRaf();
      ctxRef.current?.close().catch(() => {});
    };
  }, []);

  return { load, loaded, playing, currentTime, duration, toggle, seek, stems, setStemVolume, toggleMute };
}
