from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobKind = Literal["transcribe", "extract_trivia", "process"]
EpisodeKind = Literal["main", "mini", "announcement"]


class AdminLogin(BaseModel):
    password: str = Field(min_length=1)


class AdminSession(BaseModel):
    authenticated: bool


class EpisodeMetadata(BaseModel):
    episode_title: str = Field(min_length=1)
    episode_number: int = Field(ge=1)
    episode_description: str | None = None
    published_at: datetime | None = None
    source_url: HttpUrl | None = None
    speaker_ids: list[str] = Field(min_length=1)
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class SpeakerCreate(BaseModel):
    name: str = Field(min_length=1)


class SpeakerUpdate(BaseModel):
    name: str = Field(min_length=1)


class SpeakerOut(BaseModel):
    id: str
    name: str


class SpeakerMappingIn(BaseModel):
    mappings: dict[str, str] = Field(default_factory=dict)


class SpeakerMappingOut(BaseModel):
    episode_id: str
    mappings: dict[str, SpeakerOut] = Field(default_factory=dict)


class SpeakerLabelSample(BaseModel):
    start: float
    end: float
    text: str
    sample_clip_url: str | None = None


class SpeakerLabelOut(BaseModel):
    label: str
    segment_count: int
    first_seen: float
    last_seen: float
    samples: list[SpeakerLabelSample] = Field(default_factory=list)
    sample_clip_url: str


class SpeakerLabelsOut(BaseModel):
    episode_id: str
    speakers: list[SpeakerOut] = Field(default_factory=list)
    mappings: dict[str, SpeakerOut] = Field(default_factory=dict)
    labels: list[SpeakerLabelOut] = Field(default_factory=list)


class AskerOut(BaseModel):
    id: str
    name: str


class JobOut(BaseModel):
    id: str
    episode_id: str
    kind: JobKind
    status: JobStatus
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress_stage: str | None = None
    progress_current: float | None = None
    progress_total: float | None = None
    attempts: int = 0


class EpisodeOut(BaseModel):
    id: str
    episode_title: str
    episode_number: int | None
    episode_kind: EpisodeKind = "main"
    episode_description: str | None = None
    published_at: datetime | None = None
    source_url: str | None = None
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    speakers: list[SpeakerOut] = Field(default_factory=list)
    audio_path: str
    audio_content_type: str | None = None
    audio_object_key: str | None = None
    audio_size_bytes: int | None = None
    duration_seconds: float | None = None
    rss_guid: str | None = None
    rss_enclosure_url: str | None = None
    transcript_status: str
    trivia_status: str
    trivia_count: int
    is_published: bool
    active_job: JobOut | None = None
    created_at: datetime
    updated_at: datetime


class JobAccepted(BaseModel):
    job_id: str
    episode_id: str
    status: JobStatus = "queued"


class TranscriptionRequest(BaseModel):
    model_name: str | None = None
    device: str | None = None
    compute_type: str | None = None
    batch_size: int | None = Field(default=None, ge=1)
    diarize: bool = True
    hf_token: str | None = None
    min_speakers: int | None = Field(default=None, ge=1)
    max_speakers: int | None = Field(default=None, ge=1)


class TriviaExtractionRequest(BaseModel):
    model: str | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)


class ProcessRequest(BaseModel):
    transcription: TranscriptionRequest = Field(default_factory=TranscriptionRequest)
    trivia: TriviaExtractionRequest = Field(default_factory=TriviaExtractionRequest)


class TranscriptOut(BaseModel):
    episode_id: str
    transcript: dict[str, Any]


class TriviaItemOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    episode_id: str
    type: str
    question: str | None = None
    answer: str | None = None
    keywords: list[str] = Field(default_factory=list)
    timestamps: dict[str, Any]
    speaker_diarization: dict[str, Any] = Field(default_factory=dict)
    asker: AskerOut | None = None
    confidence: str
    created_at: datetime


class EpisodeUpdate(BaseModel):
    episode_title: str = Field(min_length=1)
    episode_number: int | None = Field(default=None, ge=1)
    episode_kind: EpisodeKind = "main"
    episode_description: str | None = None
    published_at: datetime | None = None
    source_url: HttpUrl | None = None
    speaker_ids: list[str] = Field(min_length=1)
    is_published: bool

    @model_validator(mode="after")
    def numbered_content_requires_number(self):
        if self.episode_kind != "announcement" and self.episode_number is None:
            raise ValueError("episode_number is required for main and mini episodes")
        return self


class EpisodePublicationUpdate(BaseModel):
    is_published: bool


class DirectUploadCreate(BaseModel):
    episode_title: str = Field(min_length=1)
    episode_number: int = Field(ge=1)
    episode_description: str | None = None
    published_at: datetime | None = None
    source_url: HttpUrl | None = None
    speaker_ids: list[str] = Field(min_length=1)
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)


class DirectUploadTicket(BaseModel):
    episode_id: str
    object_key: str
    upload_url: str
    required_headers: dict[str, str]


class DirectUploadComplete(BaseModel):
    sha256: str | None = None


class TriviaItemUpdate(BaseModel):
    type: str | None = None
    question: str | None = None
    answer: str | None = None
    keywords: list[str] | None = None
    confidence: str | None = None
    asker_speaker_id: str | None = None


class TriviaRephraseOut(BaseModel):
    question: str | None = None
    answer: str | None = None


class PublicEpisodeOut(BaseModel):
    id: str
    episode_title: str
    episode_number: int | None
    episode_kind: EpisodeKind = "main"
    episode_description: str | None = None
    published_at: datetime | None = None
    source_url: str | None = None
    speakers: list[SpeakerOut] = Field(default_factory=list)
    trivia_count: int


class WorkerProgress(BaseModel):
    stage: str = Field(min_length=1)
    current: float | None = Field(default=None, ge=0)
    total: float | None = Field(default=None, gt=0)


class WorkerJobClaim(BaseModel):
    worker_name: str = Field(min_length=1)


class WorkerJobLease(BaseModel):
    job: JobOut
    lease_token: str
    audio_url: str
    audio_content_type: str | None = None
    transcription: TranscriptionRequest


class WorkerUploadRequest(BaseModel):
    lease_token: str


class WorkerTranscriptUpload(BaseModel):
    transcript_object_key: str
    transcript_upload_url: str
    transcript_upload_headers: dict[str, str]


class WorkerHeartbeat(BaseModel):
    lease_token: str
    progress: WorkerProgress


class WorkerComplete(BaseModel):
    lease_token: str
    transcript_object_key: str
    transcript_sha256: str | None = None


class WorkerFailure(BaseModel):
    lease_token: str
    error: str = Field(min_length=1)


class FeedImportRequest(BaseModel):
    feed_url: HttpUrl | None = None
    dry_run: bool = False


class FeedImportOut(BaseModel):
    id: str
    feed_url: str
    status: str
    dry_run: bool
    discovered_count: int
    imported_count: int
    skipped_count: int
    failed_count: int
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PublicTriviaItemOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    episode_id: str
    type: str
    question: str | None = None
    answer: str | None = None
    keywords: list[str] = Field(default_factory=list)
    timestamps: dict[str, Any]
    asker: AskerOut | None = None
    confidence: str
    created_at: datetime
