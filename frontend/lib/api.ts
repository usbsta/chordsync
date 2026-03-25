import type { JobResponse } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Upload an audio file and return the job_id
export async function submitJob(file: File, artist = "", title = ""): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  if (artist) form.append("artist", artist);
  if (title)  form.append("title", title);

  const res = await fetch(`${API_URL}/api/v1/jobs`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Upload failed");
  }

  const data: JobResponse = await res.json();
  return data.job_id;
}

// Poll job status until done or failed
export async function pollJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`${API_URL}/api/v1/jobs/${jobId}`);
  if (!res.ok) throw new Error("Failed to fetch job status");
  return res.json();
}

// Search YouTube for a song and start the full processing pipeline
export async function submitFromSearch(artist: string, title: string): Promise<string> {
  const res = await fetch(`${API_URL}/api/v1/jobs/from-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ artist, title }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Search failed");
  }
  const data: JobResponse = await res.json();
  return data.job_id;
}
