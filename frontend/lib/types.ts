export interface ChordEvent {
  time: number;   // seconds from start
  chord: string;  // e.g. "Am", "G", "C"
}

export interface WordEvent {
  start: number;    // seconds
  end: number;      // seconds
  word: string;
  newline?: boolean; // true on the first word of each lyrics line
}

export interface SongInfo {
  title: string;
  artist: string;
  genre: string | null;
}

export interface JobResult {
  job_id: string;
  duration: number;
  chords: ChordEvent[];
  words: WordEvent[];
  song: SongInfo | null;
  chord_set: string[] | null;  // unique chords used in the song
  stems: Record<string, string> | null;
}

export type JobStatus = "pending" | "processing" | "done" | "failed";

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  result: JobResult | null;
  error: string | null;
}
