export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type JobKind = "transcribe" | "extract_trivia" | "process";

export interface Speaker {
  id: string;
  name: string;
}

export interface Episode {
  id: string;
  episode_title: string;
  episode_number: number;
  episode_description: string | null;
  published_at: string | null;
  source_url: string | null;
  extra_metadata: Record<string, unknown>;
  speakers: Speaker[];
  audio_path: string;
  audio_content_type: string | null;
  transcript_status: string;
  trivia_status: string;
  trivia_count: number;
  is_published?: boolean;
  created_at: string;
  updated_at: string;
}

export interface PublicEpisode {
  id: string;
  episode_title: string;
  episode_number: number;
  episode_description: string | null;
  published_at: string | null;
  source_url: string | null;
  speakers: Speaker[];
  trivia_count: number;
}

export interface AdminSession {
  authenticated: boolean;
}

export interface EpisodeUpdateInput {
  episode_title: string;
  episode_number: number;
  episode_description: string | null;
  published_at: string | null;
  source_url: string | null;
  speaker_ids: string[];
  is_published: boolean;
}

export interface JobAccepted {
  job_id: string;
  episode_id: string;
  status: JobStatus;
}

export interface Job {
  id: string;
  episode_id: string;
  kind: JobKind;
  status: JobStatus;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SpeakerLabelSample {
  start: number;
  end: number;
  text: string;
  sample_clip_url: string | null;
}

export interface SpeakerLabel {
  label: string;
  segment_count: number;
  first_seen: number;
  last_seen: number;
  samples: SpeakerLabelSample[];
  sample_clip_url: string;
}

export interface SpeakerLabels {
  episode_id: string;
  speakers: Speaker[];
  mappings: Record<string, Speaker>;
  labels: SpeakerLabel[];
}

export interface SpeakerMappingResponse {
  episode_id: string;
  mappings: Record<string, Speaker>;
}

export interface TranscriptResponse {
  episode_id: string;
  transcript: Record<string, unknown>;
}

export interface TriviaItem {
  id: string;
  episode_id: string;
  type: string;
  question: string | null;
  answer: string | null;
  keywords: string[];
  timestamps: Record<string, unknown>;
  speaker_diarization: Record<string, unknown>;
  asker: Speaker | null;
  confidence: string;
  created_at: string;
}

export interface TriviaUpdateInput {
  type: string;
  question: string | null;
  answer: string | null;
  keywords: string[];
  confidence: string;
  asker_speaker_id: string | null;
}

export interface TriviaRephraseSuggestion {
  question: string | null;
  answer: string | null;
}

export interface EpisodeUploadInput {
  file: File;
  episode_title: string;
  episode_number: number;
  episode_description?: string;
  published_at?: string;
  source_url?: string;
  speaker_ids: string[];
  extra_metadata?: Record<string, unknown>;
}
