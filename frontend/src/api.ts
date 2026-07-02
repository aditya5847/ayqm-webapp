import type {
  AdminSession,
  Episode,
  EpisodeUpdateInput,
  EpisodeUploadInput,
  Job,
  JobAccepted,
  PublicEpisode,
  Speaker,
  SpeakerLabels,
  SpeakerMappingResponse,
  TranscriptResponse,
  TriviaItem,
  TriviaRephraseSuggestion,
  TriviaUpdateInput
} from "./types";

const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(formatApiDetail(detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function isUnsupportedFeature(error: unknown): boolean {
  return error instanceof ApiError && [404, 405, 501].includes(error.status);
}

export function apiAssetUrl(path: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path}`;
}

export function buildEpisodeFormData(input: EpisodeUploadInput): FormData {
  const form = new FormData();
  form.set("file", input.file);
  form.set("episode_title", input.episode_title.trim());
  form.set("episode_number", String(input.episode_number));
  form.set("speaker_ids", JSON.stringify(input.speaker_ids));

  setOptionalField(form, "episode_description", input.episode_description);
  setOptionalField(form, "published_at", input.published_at);
  setOptionalField(form, "source_url", input.source_url);
  if (input.extra_metadata && Object.keys(input.extra_metadata).length > 0) {
    form.set("extra_metadata", JSON.stringify(input.extra_metadata));
  }
  return form;
}

export async function listSpeakers(): Promise<Speaker[]> {
  return request<Speaker[]>("/speakers");
}

export async function createSpeaker(name: string): Promise<Speaker> {
  return request<Speaker>("/speakers", {
    method: "POST",
    body: JSON.stringify({ name })
  });
}

export async function updateSpeaker(speakerId: string, name: string): Promise<Speaker> {
  return request<Speaker>(`/speakers/${speakerId}`, {
    method: "PATCH",
    body: JSON.stringify({ name })
  });
}

export async function deleteSpeaker(speakerId: string): Promise<void> {
  await request<void>(`/speakers/${speakerId}`, { method: "DELETE" });
}

export async function listEpisodes(): Promise<Episode[]> {
  return request<Episode[]>("/episodes");
}

export async function listPublicEpisodes(): Promise<PublicEpisode[]> {
  return request<PublicEpisode[]>("/public/episodes");
}

export async function getPublicEpisode(episodeId: string): Promise<PublicEpisode> {
  return request<PublicEpisode>(`/public/episodes/${episodeId}`);
}

export async function getPublicEpisodeTrivia(episodeId: string): Promise<TriviaItem[]> {
  return request<TriviaItem[]>(`/public/episodes/${episodeId}/trivia`);
}

export async function listPublicTrivia(limit = 24, offset = 0): Promise<TriviaItem[]> {
  return request<TriviaItem[]>(`/public/trivia?limit=${limit}&offset=${offset}`);
}

export async function getEpisode(episodeId: string): Promise<Episode> {
  return request<Episode>(`/episodes/${episodeId}`);
}

export async function uploadEpisode(input: EpisodeUploadInput): Promise<Episode> {
  return request<Episode>("/episodes", {
    method: "POST",
    body: buildEpisodeFormData(input)
  });
}

export async function updateEpisode(episodeId: string, input: EpisodeUpdateInput): Promise<Episode> {
  return request<Episode>(`/episodes/${episodeId}`, {
    method: "PATCH",
    body: JSON.stringify(input)
  });
}

export async function startTranscription(episodeId: string): Promise<JobAccepted> {
  return request<JobAccepted>(`/episodes/${episodeId}/transcribe`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function startTriviaExtraction(episodeId: string): Promise<JobAccepted> {
  return request<JobAccepted>(`/episodes/${episodeId}/extract-trivia`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${jobId}`);
}

export async function getTranscript(episodeId: string): Promise<TranscriptResponse> {
  return request<TranscriptResponse>(`/episodes/${episodeId}/transcript`);
}

export async function getTrivia(episodeId: string): Promise<TriviaItem[]> {
  return request<TriviaItem[]>(`/episodes/${episodeId}/trivia`);
}

export async function updateTriviaItem(triviaId: string, input: TriviaUpdateInput): Promise<TriviaItem> {
  return request<TriviaItem>(`/trivia/${triviaId}`, {
    method: "PATCH",
    body: JSON.stringify(input)
  });
}

export async function deleteTriviaItem(triviaId: string): Promise<void> {
  await request<void>(`/trivia/${triviaId}`, { method: "DELETE" });
}

export async function rephraseTriviaItem(triviaId: string): Promise<TriviaRephraseSuggestion> {
  return request<TriviaRephraseSuggestion>(`/trivia/${triviaId}/rephrase`, { method: "POST" });
}

export async function getAdminSession(): Promise<AdminSession> {
  return request<AdminSession>("/auth/session");
}

export async function loginAdmin(password: string): Promise<AdminSession> {
  return request<AdminSession>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ password })
  });
}

export async function logoutAdmin(): Promise<void> {
  await request<void>("/auth/logout", { method: "POST" });
}

export async function getSpeakerLabels(episodeId: string): Promise<SpeakerLabels> {
  return request<SpeakerLabels>(`/episodes/${episodeId}/speaker-labels`);
}

export async function saveSpeakerMapping(
  episodeId: string,
  mappings: Record<string, string>
): Promise<SpeakerMappingResponse> {
  return request<SpeakerMappingResponse>(`/episodes/${episodeId}/speaker-mapping`, {
    method: "PUT",
    body: JSON.stringify({ mappings })
  });
}

export async function getSpeakerMapping(episodeId: string): Promise<SpeakerMappingResponse> {
  return request<SpeakerMappingResponse>(`/episodes/${episodeId}/speaker-mapping`);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include"
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    throw new ApiError(response.status, payload);
  }

  return payload as T;
}

function setOptionalField(form: FormData, key: string, value: string | undefined): void {
  const trimmed = value?.trim();
  if (trimmed) {
    form.set(key, trimmed);
  }
}

function formatApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "detail" in detail) {
    return formatApiDetail((detail as { detail: unknown }).detail);
  }
  if (Array.isArray(detail)) {
    return detail.map(formatApiDetail).join(", ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "Request failed";
}
