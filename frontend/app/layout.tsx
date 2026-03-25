import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ChordSync — Chords & Lyrics for Guitarists",
  description: "Real-time chord detection and lyrics sync for guitarists",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-zinc-950 text-zinc-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
