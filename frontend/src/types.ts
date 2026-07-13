export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type JobKind = "transcribe" | "extract_trivia" | "process";
export type EpisodeKind = "main" | "mini" | "announcement";

export interface Speaker {
  id: string;
  name: string;
}

export interface PublicSpeaker {
  id: string;
  name: string;
}

export interface Episode {
  id: string;
  episode_title: string;
  episode_number: number | null;
  episode_kind?: EpisodeKind;
  episode_description: string | null;
  published_at: string | null;
  source_url: string | null;
  artwork_url?: string | null;
  extra_metadata: Record<string, unknown>;
  speakers: Speaker[];
  audio_path: string;
  audio_content_type: string | null;
  audio_object_key?: string | null;
  audio_size_bytes?: number | null;
  duration_seconds?: number | null;
  rss_guid?: string | null;
  rss_enclosure_url?: string | null;
  transcript_status: string;
  trivia_status: string;
  trivia_count: number;
  is_published?: boolean;
  active_job: Job | null;
  created_at: string;
  updated_at: string;
}

export interface AdminEpisodePage {
  items: Episode[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface PublicEpisode {
  id: string;
  episode_title: string;
  episode_number: number | null;
  episode_kind?: EpisodeKind;
  episode_description: string | null;
  published_at: string | null;
  source_url: string | null;
  artwork_url: string | null;
  speakers: Speaker[];
  trivia_count: number;
}

export interface PublicEpisodePage {
  items: PublicEpisode[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface AdminSession {
  authenticated: boolean;
}

export interface EpisodeUpdateInput {
  episode_title: string;
  episode_number: number | null;
  episode_kind: EpisodeKind;
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
  progress_stage?: string | null;
  progress_current?: number | null;
  progress_total?: number | null;
  attempts?: number;
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

export interface TriviaSearchEpisode {
  id: string;
  episode_title: string;
  episode_number: number | null;
  episode_kind?: EpisodeKind;
  published_at: string | null;
  is_published: boolean;
}

export interface AdminTriviaSearchResult extends TriviaItem {
  episode: TriviaSearchEpisode;
}

export interface AdminTriviaSearchPage {
  items: AdminTriviaSearchResult[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
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
  onProgress?: (percent: number) => void;
}

export interface DirectUploadTicket {
  episode_id: string;
  object_key: string;
  upload_url: string;
  required_headers: Record<string, string>;
}

export interface FeedImport {
  id: string;
  feed_url: string;
  status: string;
  dry_run: boolean;
  discovered_count: number;
  imported_count: number;
  skipped_count: number;
  failed_count: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SundayQuizQuestion {
  id: string;
  position: number;
  question: string | null;
  correct_answer: string | null;
  incorrect_answers: string[];
  explanation: string | null;
  question_image_url: string | null;
  answer_image_url: string | null;
}

export interface SundayQuiz {
  id: string;
  quiz_date: string;
  theme: string;
  status: "draft" | "published" | string;
  cover_image_url: string | null;
  question_count: number;
  questions: SundayQuizQuestion[];
  created_at: string;
  updated_at: string;
}

export interface SundayQuizCreateInput {
  quiz_date: string;
  theme: string;
}

export interface SundayQuizQuestionInput {
  question: string | null;
  correct_answer: string | null;
  incorrect_answers: string[];
  explanation: string | null;
}

export interface PublicSundayQuizSummary {
  id: string;
  quiz_date: string;
  theme: string;
  question_count: number;
  cover_image_url: string | null;
}

export interface PublicSundayQuizOption {
  id: string;
  text: string;
}

export interface PublicSundayQuizQuestion {
  id: string;
  position: number;
  question: string;
  options: PublicSundayQuizOption[];
  question_image_url: string | null;
}

export interface PublicSundayQuizDetail extends PublicSundayQuizSummary {
  questions: PublicSundayQuizQuestion[];
}

export interface SundayQuizAnswerReview {
  question_id: string;
  position: number;
  selected_option_id: string | null;
  correct_option_id: string;
  selected_option_text: string | null;
  correct_option_text: string;
  correct: boolean;
  explanation: string | null;
  answer_image_url: string | null;
}

export interface SundayQuizAttemptResult {
  score: number;
  total: number;
  review: SundayQuizAnswerReview[];
}
