"use client";

import { useRef, useState } from "react";

interface Props {
  onFile: (file: File) => void;
  disabled: boolean;
}

export default function UploadZone({ onFile, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
  }

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`
        w-full border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer
        transition-all duration-200 select-none group
        ${dragging
          ? "border-violet-400 bg-violet-950/30 scale-[1.01]"
          : "border-zinc-700 hover:border-violet-500 hover:bg-zinc-950/50"
        }
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <div className="flex flex-col items-center gap-3">
        <div className={`w-16 h-16 rounded-2xl flex items-center justify-center text-3xl transition-all
          ${dragging ? "bg-violet-900/60 scale-110" : "bg-zinc-800 group-hover:bg-zinc-700"}`}>
          🎸
        </div>
        <div>
          <p className="text-base font-semibold text-zinc-200">
            Drop your audio file here
          </p>
          <p className="text-sm text-zinc-500 mt-1">
            or click to browse — MP3, WAV, FLAC, OGG, M4A · max 50MB
          </p>
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".mp3,.wav,.flac,.ogg,.m4a"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
        disabled={disabled}
      />
    </div>
  );
}
