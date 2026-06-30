import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Headphones,
  Loader2,
  Mic2,
  Pencil,
  Plus,
  RefreshCcw,
  Save,
  Sparkles,
  Trash2,
  Upload
} from "lucide-react";
import {
  ApiError,
  apiAssetUrl,
  createSpeaker,
  deleteSpeaker,
  getEpisode,
  getJob,
  getSpeakerLabels,
  getTranscript,
  getTrivia,
  listEpisodes,
  listSpeakers,
  saveSpeakerMapping,
  startTranscription,
  startTriviaExtraction,
  updateSpeaker,
  uploadEpisode
} from "./api";
import type { Episode, Job, JobAccepted, Speaker, SpeakerLabels, TriviaItem } from "./types";
import { formatDate, formatSeconds, isSpeakerMappingComplete, shouldPollJob, triviaAskerName } from "./workflow";

function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/">
          <Headphones aria-hidden="true" />
          <span>AYQM</span>
        </Link>
        <nav className="nav-list" aria-label="Primary">
          <NavLink to="/" end>
            Episodes
          </NavLink>
          <NavLink to="/upload">Upload</NavLink>
          <NavLink to="/speakers">Speakers</NavLink>
        </nav>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<EpisodesPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/speakers" element={<SpeakersPage />} />
          <Route path="/episodes/:episodeId" element={<EpisodeDetailPage />} />
        </Routes>
      </main>
    </div>
  );
}

function EpisodesPage() {
  const episodes = useQuery({ queryKey: ["episodes"], queryFn: listEpisodes });

  return (
    <Page title="Episodes" actions={<Link className="button primary" to="/upload"><Upload size={16} />Upload</Link>}>
      <AsyncState query={episodes} empty="No episodes uploaded yet.">
        {(items) => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Episode</th>
                  <th>Speakers</th>
                  <th>Transcript</th>
                  <th>Trivia</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {items.map((episode) => (
                  <tr key={episode.id}>
                    <td>
                      <Link className="row-title" to={`/episodes/${episode.id}`}>
                        #{episode.episode_number} {episode.episode_title}
                      </Link>
                      {episode.episode_description && <div className="muted clamp">{episode.episode_description}</div>}
                    </td>
                    <td>{episode.speakers.map((speaker) => speaker.name).join(", ")}</td>
                    <td><StatusPill value={episode.transcript_status} /></td>
                    <td>
                      <StatusPill value={episode.trivia_status} />
                      <span className="count">{episode.trivia_count}</span>
                    </td>
                    <td>{formatDate(episode.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncState>
    </Page>
  );
}

function UploadPage() {
  const navigate = useNavigate();
  const speakers = useQuery({ queryKey: ["speakers"], queryFn: listSpeakers });
  const mutation = useMutation({
    mutationFn: uploadEpisode,
    onSuccess: (episode) => navigate(`/episodes/${episode.id}`)
  });

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [number, setNumber] = useState(1);
  const [description, setDescription] = useState("");
  const [publishedAt, setPublishedAt] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [speakerIds, setSpeakerIds] = useState<string[]>([]);
  const [extraMetadata, setExtraMetadata] = useState("{}");
  const [formError, setFormError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    if (!file) {
      setFormError("Choose an audio file.");
      return;
    }
    if (speakerIds.length === 0) {
      setFormError("Select at least one episode speaker.");
      return;
    }

    let parsedMetadata: Record<string, unknown> = {};
    try {
      parsedMetadata = extraMetadata.trim() ? JSON.parse(extraMetadata) : {};
      if (!parsedMetadata || Array.isArray(parsedMetadata) || typeof parsedMetadata !== "object") {
        throw new Error("Extra metadata must be a JSON object.");
      }
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Extra metadata must be valid JSON.");
      return;
    }

    mutation.mutate({
      file,
      episode_title: title,
      episode_number: number,
      episode_description: description,
      published_at: publishedAt,
      source_url: sourceUrl,
      speaker_ids: speakerIds,
      extra_metadata: parsedMetadata
    });
  }

  return (
    <Page title="Upload Episode">
      <form className="form-grid" onSubmit={submit}>
        <label className="field full">
          <span>Audio file</span>
          <input required type="file" accept="audio/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
        <label className="field">
          <span>Episode title</span>
          <input required value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label className="field">
          <span>Episode number</span>
          <input required type="number" min="1" value={number} onChange={(event) => setNumber(Number(event.target.value))} />
        </label>
        <label className="field full">
          <span>Description</span>
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
        </label>
        <label className="field">
          <span>Published at</span>
          <input type="datetime-local" value={publishedAt} onChange={(event) => setPublishedAt(event.target.value)} />
        </label>
        <label className="field">
          <span>Source URL</span>
          <input type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
        </label>
        <fieldset className="field full speaker-picker">
          <legend>Episode speakers</legend>
          <AsyncState query={speakers} empty="Create speakers before uploading episodes.">
            {(items) => (
              <div className="checkbox-grid">
                {items.map((speaker) => (
                  <label key={speaker.id} className="check-row">
                    <input
                      type="checkbox"
                      checked={speakerIds.includes(speaker.id)}
                      onChange={(event) =>
                        setSpeakerIds((current) =>
                          event.target.checked ? [...current, speaker.id] : current.filter((id) => id !== speaker.id)
                        )
                      }
                    />
                    <span>{speaker.name}</span>
                  </label>
                ))}
              </div>
            )}
          </AsyncState>
        </fieldset>
        <label className="field full">
          <span>Extra metadata</span>
          <textarea value={extraMetadata} onChange={(event) => setExtraMetadata(event.target.value)} rows={5} spellCheck={false} />
        </label>
        <ErrorMessage error={formError ?? mutation.error} />
        <div className="form-actions full">
          <button className="button primary" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? <Loader2 className="spin" size={16} /> : <Upload size={16} />}
            Upload episode
          </button>
        </div>
      </form>
    </Page>
  );
}

function SpeakersPage() {
  const queryClient = useQueryClient();
  const speakers = useQuery({ queryKey: ["speakers"], queryFn: listSpeakers });
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: createSpeaker,
    onSuccess: () => {
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["speakers"] });
    }
  });

  return (
    <Page title="Speakers">
      <form
        className="inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) create.mutate(name.trim());
        }}
      >
        <input aria-label="Speaker name" placeholder="Speaker name" value={name} onChange={(event) => setName(event.target.value)} />
        <button className="button primary" type="submit" disabled={create.isPending}>
          <Plus size={16} />Add
        </button>
      </form>
      <ErrorMessage error={create.error} />
      <AsyncState query={speakers} empty="No speakers yet.">
        {(items) => <div className="item-list">{items.map((speaker) => <SpeakerRow key={speaker.id} speaker={speaker} />)}</div>}
      </AsyncState>
    </Page>
  );
}

function SpeakerRow({ speaker }: { speaker: Speaker }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(speaker.name);
  const update = useMutation({
    mutationFn: () => updateSpeaker(speaker.id, name.trim()),
    onSuccess: () => {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["speakers"] });
      void queryClient.invalidateQueries({ queryKey: ["episodes"] });
    }
  });
  const remove = useMutation({
    mutationFn: () => deleteSpeaker(speaker.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["speakers"] })
  });

  return (
    <div className="item-row">
      {editing ? (
        <input value={name} onChange={(event) => setName(event.target.value)} aria-label={`Rename ${speaker.name}`} />
      ) : (
        <strong>{speaker.name}</strong>
      )}
      <div className="row-actions">
        {editing ? (
          <button className="icon-button" type="button" aria-label="Save speaker" onClick={() => update.mutate()} disabled={!name.trim() || update.isPending}>
            <Save size={16} />
          </button>
        ) : (
          <button className="icon-button" type="button" aria-label="Rename speaker" onClick={() => setEditing(true)}>
            <Pencil size={16} />
          </button>
        )}
        <button className="icon-button danger" type="button" aria-label="Delete speaker" onClick={() => remove.mutate()} disabled={remove.isPending}>
          <Trash2 size={16} />
        </button>
      </div>
      <ErrorMessage error={update.error ?? remove.error} compact />
    </div>
  );
}

function EpisodeDetailPage() {
  const { episodeId } = useParams();
  if (!episodeId) return <Page title="Episode"><Notice kind="error">Missing episode ID.</Notice></Page>;
  return <EpisodeDetail episodeId={episodeId} />;
}

function EpisodeDetail({ episodeId }: { episodeId: string }) {
  const queryClient = useQueryClient();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const episode = useQuery({ queryKey: ["episode", episodeId], queryFn: () => getEpisode(episodeId) });
  const labels = useQuery({
    queryKey: ["speaker-labels", episodeId],
    queryFn: () => getSpeakerLabels(episodeId),
    enabled: episode.data?.transcript_status === "completed"
  });
  const transcript = useQuery({
    queryKey: ["transcript", episodeId],
    queryFn: () => getTranscript(episodeId),
    enabled: episode.data?.transcript_status === "completed"
  });
  const trivia = useQuery({
    queryKey: ["trivia", episodeId],
    queryFn: () => getTrivia(episodeId),
    enabled: episode.data?.trivia_status === "completed" || Number(episode.data?.trivia_count ?? 0) > 0
  });
  const job = useQuery({
    queryKey: ["job", activeJobId],
    queryFn: () => getJob(activeJobId!),
    enabled: Boolean(activeJobId),
    refetchInterval: (query) => (shouldPollJob(query.state.data as Job | undefined) ? 2000 : false)
  });

  useEffect(() => {
    if (job.data?.status === "succeeded" || job.data?.status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["episode", episodeId] });
      void queryClient.invalidateQueries({ queryKey: ["episodes"] });
      void queryClient.invalidateQueries({ queryKey: ["speaker-labels", episodeId] });
      void queryClient.invalidateQueries({ queryKey: ["transcript", episodeId] });
      void queryClient.invalidateQueries({ queryKey: ["trivia", episodeId] });
    }
  }, [episodeId, job.data?.status, queryClient]);

  const startTranscribe = useMutation({
    mutationFn: () => startTranscription(episodeId),
    onSuccess: (accepted) => setActiveJob(accepted, setActiveJobId)
  });
  const startTrivia = useMutation({
    mutationFn: () => startTriviaExtraction(episodeId),
    onSuccess: (accepted) => setActiveJob(accepted, setActiveJobId)
  });

  return (
    <Page title={episode.data ? `#${episode.data.episode_number} ${episode.data.episode_title}` : "Episode"}>
      <AsyncState query={episode}>
        {(item) => (
          <>
            <EpisodeSummary episode={item} />
            {activeJobId && <JobPanel job={job.data} error={job.error} />}
            <div className="action-strip">
              <button className="button primary" type="button" onClick={() => startTranscribe.mutate()} disabled={startTranscribe.isPending || shouldPollJob(job.data)}>
                {startTranscribe.isPending ? <Loader2 className="spin" size={16} /> : <Mic2 size={16} />}
                Transcribe
              </button>
              <button
                className="button"
                type="button"
                onClick={() => startTrivia.mutate()}
                disabled={startTrivia.isPending || shouldPollJob(job.data) || !isSpeakerMappingComplete(labels.data, mappingDraftFromLabels(labels.data))}
              >
                {startTrivia.isPending ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
                Extract trivia
              </button>
              <button className="button ghost" type="button" onClick={() => refreshEpisode(queryClient, episodeId)}>
                <RefreshCcw size={16} />Refresh
              </button>
            </div>
            <ErrorMessage error={startTranscribe.error ?? startTrivia.error} />
            <SpeakerMappingPanel episodeId={episodeId} labels={labels.data} isLoading={labels.isLoading} error={labels.error} />
            <TranscriptPanel query={transcript} />
            <TriviaPanel query={trivia} />
          </>
        )}
      </AsyncState>
    </Page>
  );
}

function EpisodeSummary({ episode }: { episode: Episode }) {
  return (
    <section className="summary-grid" aria-label="Episode summary">
      <Metric label="Transcript" value={<StatusPill value={episode.transcript_status} />} />
      <Metric label="Trivia" value={<StatusPill value={episode.trivia_status} />} />
      <Metric label="Trivia items" value={episode.trivia_count} />
      <Metric label="Speakers" value={episode.speakers.map((speaker) => speaker.name).join(", ")} />
      <Metric label="Published" value={formatDate(episode.published_at)} />
      <Metric label="Updated" value={formatDate(episode.updated_at)} />
    </section>
  );
}

function SpeakerMappingPanel({
  episodeId,
  labels,
  isLoading,
  error
}: {
  episodeId: string;
  labels: SpeakerLabels | undefined;
  isLoading: boolean;
  error: Error | null;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    if (labels) setDraft(mappingDraftFromLabels(labels));
  }, [labels]);

  const save = useMutation({
    mutationFn: () => saveSpeakerMapping(episodeId, draft),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["speaker-labels", episodeId] });
    }
  });

  return (
    <Section title="Speaker Mapping" hint="Map every detected diarization label before extracting trivia.">
      {isLoading && <LoadingRow />}
      <ErrorMessage error={error ?? save.error} />
      {!isLoading && !labels && !error && <Notice>Run transcription before mapping speakers.</Notice>}
      {labels && labels.labels.length === 0 && <Notice>No diarized speaker labels were found.</Notice>}
      {labels && labels.labels.length > 0 && (
        <>
          <div className="mapping-list">
            {labels.labels.map((label) => (
              <div className="mapping-row" key={label.label}>
                <div className="label-meta">
                  <strong>{label.label}</strong>
                  <span>{label.segment_count} segments, {formatSeconds(label.first_seen)}-{formatSeconds(label.last_seen)}</span>
                  <audio controls src={apiAssetUrl(label.sample_clip_url) ?? undefined} />
                </div>
                <label className="field compact">
                  <span>Speaker</span>
                  <select value={draft[label.label] ?? ""} onChange={(event) => setDraft((current) => ({ ...current, [label.label]: event.target.value }))}>
                    <option value="">Unmapped</option>
                    {labels.speakers.map((speaker) => (
                      <option key={speaker.id} value={speaker.id}>{speaker.name}</option>
                    ))}
                  </select>
                </label>
                <div className="sample-list">
                  {label.samples.map((sample, index) => (
                    <div className="sample-row" key={`${label.label}-${index}`}>
                      <audio controls src={apiAssetUrl(sample.sample_clip_url) ?? undefined} />
                      <span>{formatSeconds(sample.start)}-{formatSeconds(sample.end)}</span>
                      <p>{sample.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="form-actions">
            <button className="button primary" type="button" onClick={() => save.mutate()} disabled={!isSpeakerMappingComplete(labels, draft) || save.isPending}>
              {save.isPending ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
              Save mapping
            </button>
            {!isSpeakerMappingComplete(labels, draft) && <span className="muted">All labels must be mapped.</span>}
          </div>
        </>
      )}
    </Section>
  );
}

function TranscriptPanel({ query }: { query: ReturnType<typeof useQuery<unknown, Error, { transcript: Record<string, unknown> }>> }) {
  return (
    <Section title="Transcript">
      {query.isLoading && <LoadingRow />}
      <ErrorMessage error={query.error} />
      {query.data ? <pre className="json-panel">{JSON.stringify(query.data.transcript, null, 2)}</pre> : !query.isLoading && !query.error && <Notice>No transcript available.</Notice>}
    </Section>
  );
}

function TriviaPanel({ query }: { query: ReturnType<typeof useQuery<TriviaItem[], Error>> }) {
  return (
    <Section title="Trivia">
      {query.isLoading && <LoadingRow />}
      <ErrorMessage error={query.error} />
      {query.data && query.data.length > 0 ? (
        <div className="trivia-grid">
          {query.data.map((item) => <TriviaCard key={item.id} item={item} />)}
        </div>
      ) : (
        !query.isLoading && !query.error && <Notice>No trivia extracted yet.</Notice>
      )}
    </Section>
  );
}

export function TriviaCard({ item }: { item: TriviaItem }) {
  return (
    <article className="trivia-card">
      <div className="card-topline">
        <span>{item.type}</span>
        <span>{item.confidence}</span>
      </div>
      <h3>{item.question ?? "Untitled trivia item"}</h3>
      {item.answer && <p>{item.answer}</p>}
      <div className="tag-row">
        <span className="tag">{triviaAskerName(item)}</span>
        {item.keywords.map((keyword) => <span className="tag" key={keyword}>{keyword}</span>)}
      </div>
    </article>
  );
}

function JobPanel({ job, error }: { job: Job | undefined; error: Error | null }) {
  if (error) return <ErrorMessage error={error} />;
  if (!job) return <Notice><Loader2 className="spin inline-icon" size={16} />Waiting for job status.</Notice>;
  return (
    <Notice kind={job.status === "failed" ? "error" : job.status === "succeeded" ? "success" : "info"}>
      <JobIcon status={job.status} /> {job.kind} is {job.status}
      {job.error ? `: ${job.error}` : ""}
    </Notice>
  );
}

function Page({ title, actions, children }: { title: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Podcast operations</p>
          <h1>{title}</h1>
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </header>
      {children}
    </>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="section">
      <div className="section-header">
        <h2>{title}</h2>
        {hint && <p>{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value || "Not set"}</strong>
    </div>
  );
}

function AsyncState<T>({
  query,
  empty,
  children
}: {
  query: { data?: T; isLoading: boolean; error: Error | null };
  empty?: string;
  children: (data: T) => React.ReactNode;
}) {
  if (query.isLoading) return <LoadingRow />;
  if (query.error) return <ErrorMessage error={query.error} />;
  if (Array.isArray(query.data) && query.data.length === 0) return <Notice>{empty ?? "Nothing to show."}</Notice>;
  if (!query.data) return <Notice>{empty ?? "Nothing to show."}</Notice>;
  return children(query.data);
}

function StatusPill({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  return <span className={`status ${normalized}`}>{value}</span>;
}

function Notice({ children, kind = "info" }: { children: React.ReactNode; kind?: "info" | "success" | "error" }) {
  return <div className={`notice ${kind}`}>{children}</div>;
}

function LoadingRow() {
  return <Notice><Loader2 className="spin inline-icon" size={16} />Loading</Notice>;
}

function ErrorMessage({ error, compact = false }: { error: unknown; compact?: boolean }) {
  if (!error) return null;
  const message = error instanceof ApiError || error instanceof Error ? error.message : String(error);
  return <div className={compact ? "error compact-error" : "error"}><AlertCircle size={16} />{message}</div>;
}

function JobIcon({ status }: { status: Job["status"] }) {
  if (status === "succeeded") return <CheckCircle2 className="inline-icon" size={16} />;
  if (status === "failed") return <AlertCircle className="inline-icon" size={16} />;
  return <CircleDashed className="inline-icon spin" size={16} />;
}

function mappingDraftFromLabels(labels: SpeakerLabels | undefined): Record<string, string> {
  if (!labels) return {};
  return Object.fromEntries(Object.entries(labels.mappings).map(([label, speaker]) => [label, speaker.id]));
}

function setActiveJob(accepted: JobAccepted, setActiveJobId: (id: string) => void) {
  setActiveJobId(accepted.job_id);
}

function refreshEpisode(queryClient: ReturnType<typeof useQueryClient>, episodeId: string) {
  void queryClient.invalidateQueries({ queryKey: ["episode", episodeId] });
  void queryClient.invalidateQueries({ queryKey: ["episodes"] });
  void queryClient.invalidateQueries({ queryKey: ["speaker-labels", episodeId] });
  void queryClient.invalidateQueries({ queryKey: ["transcript", episodeId] });
  void queryClient.invalidateQueries({ queryKey: ["trivia", episodeId] });
}

export default App;
