"use client";

import type { StemState } from "@/hooks/useMultiTrackPlayer";

// Display names and emoji for each stem
const STEM_META: Record<string, { label: string; emoji: string; color: string }> = {
  guitar: { label: "Guitar",  emoji: "🎸", color: "text-indigo-400" },
  vocals: { label: "Vocals",  emoji: "🎤", color: "text-pink-400"   },
  bass:   { label: "Bass",    emoji: "🎵", color: "text-yellow-400" },
  drums:  { label: "Drums",   emoji: "🥁", color: "text-red-400"    },
  piano:  { label: "Piano",   emoji: "🎹", color: "text-green-400"  },
  other:  { label: "Other",   emoji: "🎶", color: "text-gray-400"   },
};

interface Props {
  stems: Record<string, StemState>;
  onVolumeChange: (name: string, volume: number) => void;
  onToggleMute: (name: string) => void;
}

export default function StemMixer({ stems, onVolumeChange, onToggleMute }: Props) {
  const stemNames = Object.keys(stems);
  if (stemNames.length === 0) return null;

  return (
    <div className="w-full">
      <p className="text-xs text-gray-600 uppercase tracking-widest mb-3">
        Stem mixer
      </p>

      <div className="grid gap-3">
        {stemNames.map((name) => {
          const meta = STEM_META[name] ?? { label: name, emoji: "🎵", color: "text-gray-400" };
          const state = stems[name];

          return (
            <div key={name} className="flex items-center gap-3">
              {/* Mute button */}
              <button
                onClick={() => onToggleMute(name)}
                title={state.muted ? "Unmute" : "Mute"}
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm transition-all
                  ${state.muted
                    ? "bg-gray-800 opacity-40"
                    : "bg-gray-800 hover:bg-gray-700"
                  }`}
              >
                {meta.emoji}
              </button>

              {/* Label */}
              <span className={`text-sm w-14 font-medium ${state.muted ? "opacity-30" : meta.color}`}>
                {meta.label}
              </span>

              {/* Volume slider */}
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={state.muted ? 0 : state.volume}
                onChange={(e) => onVolumeChange(name, parseFloat(e.target.value))}
                className="flex-1 h-1 accent-indigo-500 cursor-pointer"
              />

              {/* Volume percentage */}
              <span className={`text-xs w-8 text-right tabular-nums ${state.muted ? "opacity-30 text-gray-600" : "text-gray-500"}`}>
                {state.muted ? "0%" : `${Math.round(state.volume * 100)}%`}
              </span>
            </div>
          );
        })}
      </div>

      {/* Quick actions */}
      <div className="flex gap-2 mt-4">
        <button
          onClick={() => stemNames.forEach((n) => onVolumeChange(n, 1))}
          className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
        >
          Reset all
        </button>
        <span className="text-gray-800">·</span>
        <button
          onClick={() => {
            // Solo guitar: full volume on guitar, mute everything else
            stemNames.forEach((n) =>
              onVolumeChange(n, n === "guitar" ? 1 : 0)
            );
          }}
          className="text-xs text-indigo-600 hover:text-indigo-400 transition-colors"
        >
          Solo guitar 🎸
        </button>
        <span className="text-gray-800">·</span>
        <button
          onClick={() => {
            // Practice mode: guitar + vocals only (no drums/bass distraction)
            stemNames.forEach((n) =>
              onVolumeChange(n, n === "guitar" || n === "vocals" ? 1 : 0)
            );
          }}
          className="text-xs text-green-700 hover:text-green-500 transition-colors"
        >
          Practice mode
        </button>
      </div>
    </div>
  );
}
