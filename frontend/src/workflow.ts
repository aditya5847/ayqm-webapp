import type { Job, SpeakerLabels, TriviaItem } from "./types";

export function shouldPollJob(job: Job | null | undefined): boolean {
  return job ? job.status === "queued" || job.status === "running" : false;
}

export function isSpeakerMappingComplete(labels: SpeakerLabels | null | undefined, draft: Record<string, string>): boolean {
  if (!labels || labels.labels.length === 0) return false;
  return labels.labels.every((label) => Boolean(draft[label.label]));
}

export function triviaAskerName(item: TriviaItem): string {
  return item.asker?.name ?? "Unmapped speaker";
}

export function formatSeconds(value: number): string {
  if (!Number.isFinite(value)) return "0:00";
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function formatDate(value: string | null): string {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}
