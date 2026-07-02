from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobKind = Literal["transcribe", "extract_trivia", "process"]


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


class EpisodeOut(BaseModel):
    id: str
    episode_title: str
    episode_number: int
    episode_description: str | None = None
    published_at: datetime | None = None
    source_url: str | None = None
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    speakers: list[SpeakerOut] = Field(default_factory=list)
    audio_path: str
    audio_content_type: str | None = None
    transcript_status: str
    trivia_status: str
    trivia_count: int
    is_published: bool
    created_at: datetime
    updated_at: datetime


class JobOut(BaseModel):
    id: str
    episode_id: str
    kind: JobKind
    status: JobStatus
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


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
    episode_number: int = Field(ge=1)
    episode_description: str | None = None
    published_at: datetime | None = None
    source_url: HttpUrl | None = None
    speaker_ids: list[str] = Field(min_length=1)
    is_published: bool


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
    episode_number: int
    episode_description: str | None = None
    published_at: datetime | None = None
    source_url: str | None = None
    speakers: list[SpeakerOut] = Field(default_factory=list)
    trivia_count: int


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
