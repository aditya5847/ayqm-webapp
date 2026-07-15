import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle, ArrowLeft, ArrowRight, CheckCircle2, CircleDashed, ExternalLink, FileAudio,
  EyeOff, Globe2, Loader2, Mic2, Pencil, RefreshCcw, Save, Sparkles, Trash2, X
} from "lucide-react";
import { Link, NavLink, Outlet, useNavigate, useOutletContext, useParams } from "react-router-dom";
import {
  apiAssetUrl, applyTriviaCandidate, deleteEpisode, deleteTriviaItem, discardTriviaCandidate, getEpisode,
  getJob, getSpeakerLabels, getSpeakerMapping, getTranscript, getTrivia, getTriviaCandidateReview,
  isUnsupportedFeature, listSpeakers, rephraseTriviaItem, saveSpeakerMapping, startTranscription,
  startTriviaCandidateExtraction, updateEpisode, updateEpisodePublication, updateTriviaItem
} from "./api";
import type { Episode, Job, JobAccepted, Speaker, SpeakerLabels, TriviaItem, TriviaUpdateInput } from "./types";
import { transcriptScriptBlocks } from "./transcript";
import { formatDate, formatSeconds, isSpeakerMappingComplete, shouldPollJob, triviaAskerName } from "./workflow";
import { ComingSoon, ErrorMessage, Loading, Notice, QueryState, RequiredLabel, StatusPill } from "./ui";
import thumbnailUrl from "../references/Podcast Thumbnail.jpg";

interface EpisodeWorkspaceContext {
  episode: Episode;
  episodeId: string;
  activeJobId: string | null;
  job: ReturnType<typeof useQuery<Job, Error>>;
  setActiveJobId: (id: string) => void;
}

const tabs = [
  ["overview", "Overview"],
  ["details", "Details"],
  ["speaker-mapping", "Speaker mapping"],
  ["transcript", "Transcript"],
  ["trivia", "Trivia"]
] as const;

export function EpisodeWorkspaceLayout() {
  const { episodeId = "" } = useParams();
  const client = useQueryClient();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const episode = useQuery({ queryKey: ["episode", episodeId], queryFn: () => getEpisode(episodeId), enabled: Boolean(episodeId) });
  const job = useQuery({
    queryKey: ["job", activeJobId],
    queryFn: () => getJob(activeJobId!),
    enabled: Boolean(activeJobId),
    refetchInterval: query => shouldPollJob(query.state.data as Job | undefined) ? 2000 : false
  });

  useEffect(() => {
    if (episode.data?.active_job?.id) setActiveJobId(episode.data.active_job.id);
  }, [episode.data?.active_job?.id]);

  useEffect(() => {
    if (job.data?.status === "succeeded" || job.data?.status === "failed") refreshEpisode(client, episodeId);
  }, [client, episodeId, job.data?.status]);

  return (
    <QueryState query={episode}>
      {item => (
        <div className="episode-workspace">
          <Link className="back-link" to="/admin/episodes"><ArrowLeft size={17} />Back to episodes</Link>
          <header className="episode-workspace-heading">
            <div><p className="eyebrow">{episodeLabel(item)}</p><h1>{item.episode_title}</h1></div>
            <StatusPill value={item.is_published ? "visible" : "hidden"} />
          </header>
          <nav className="episode-tabs" aria-label="Episode workspace">
            {tabs.map(([path, label]) => <NavLink key={path} to={`/admin/episodes/${episodeId}/${path}`}>{label}</NavLink>)}
          </nav>
          <div className="episode-tab-panel">
            <Outlet context={{ episode: item, episodeId, activeJobId, job, setActiveJobId } satisfies EpisodeWorkspaceContext} />
          </div>
        </div>
      )}
    </QueryState>
  );
}

export function EpisodeOverviewTab() {
  const { episode, episodeId, activeJobId, job, setActiveJobId } = useEpisodeWorkspace();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const labels = useQuery({
    queryKey: ["speaker-labels", episodeId],
    queryFn: () => getSpeakerLabels(episodeId),
    enabled: episode.transcript_status === "completed"
  });
  const mappingComplete = isSpeakerMappingComplete(labels.data, mappingFromLabels(labels.data));
  const currentJob = job.data ?? episode.active_job ?? undefined;
  const processing = shouldPollJob(currentJob);
  const transcribe = useMutation({ mutationFn: () => startTranscription(episodeId), onSuccess: accepted => setJob(accepted, setActiveJobId) });
  const publication = useMutation({
    mutationFn: () => updateEpisodePublication(episodeId, !(episode.is_published ?? false)),
    onSuccess: updated => {
      client.setQueryData(["episode", episodeId], updated);
      void client.invalidateQueries({ queryKey: ["episodes"] });
      void client.invalidateQueries({ queryKey: ["public"] });
    }
  });
  const remove = useMutation({
    mutationFn: () => deleteEpisode(episodeId),
    onSuccess: () => {
      client.removeQueries({ queryKey: ["episode", episodeId] });
      void client.invalidateQueries({ queryKey: ["episodes"] });
      void client.invalidateQueries({ queryKey: ["public"] });
      navigate("/admin/episodes");
    }
  });
  const deletionConfirmed = deleteConfirmation.trim() === episode.episode_title;

  return (
    <>
      <section className="workspace-section">
        <div className="episode-overview-metadata">
          <dl className="episode-detail-grid">
            <Detail label="Title">{episode.episode_title}</Detail>
            <Detail label="Episode">{episodeLabel(episode)}</Detail>
            <Detail label="Description" wide>{episode.episode_description || "Not set"}</Detail>
            <Detail label="Published at">{formatDate(episode.published_at)}</Detail>
            <Detail label="Speakers">{episode.speakers.map(speaker => speaker.name).join(", ") || "Not set"}</Detail>
            <Detail label="Source">{episode.source_url ? <a href={episode.source_url} target="_blank" rel="noreferrer">Open episode <ExternalLink size={14} /></a> : "Not set"}</Detail>
            <Detail label="Created">{formatDate(episode.created_at)}</Detail>
            <Detail label="Updated">{formatDate(episode.updated_at)}</Detail>
          </dl>
          <AdminEpisodeArtwork episode={episode} />
        </div>
      </section>
      <section className="workspace-section">
        <SectionHeading icon={<FileAudio />} title="Processing" />
        <div className="summary-grid processing-summary-grid">
          <ProcessingMetric label="Transcription" to={`/admin/episodes/${episodeId}/transcript`} value={<StatusPill value={episode.transcript_status} />} />
          <ProcessingMetric label="Speaker mapping" to={`/admin/episodes/${episodeId}/speaker-mapping`} value={<StatusPill value={mappingComplete ? "completed" : "missing"} />} />
          <ProcessingMetric label="Trivia extraction" to={`/admin/episodes/${episodeId}/trivia`} value={<StatusPill value={episode.trivia_status} />} count={episode.trivia_count} />
          <Metric label="Website visibility" value={<StatusPill value={episode.is_published ? "visible" : "hidden"} />} />
        </div>
        {(activeJobId || episode.active_job) && <JobPanel job={currentJob} error={job.error} />}
        <div className="action-strip">
          <button className="button" type="button" onClick={() => transcribe.mutate()} disabled={transcribe.isPending || processing}><Mic2 size={16} />Transcribe</button>
          <button className="button" type="button" onClick={() => navigate(`/admin/episodes/${episodeId}/trivia`)} disabled={processing || !mappingComplete}><Sparkles size={16} />Extract trivia</button>
          <button className="button" type="button" onClick={() => publication.mutate()} disabled={publication.isPending || processing}>{episode.is_published ? <EyeOff size={16} /> : <Globe2 size={16} />}{episode.is_published ? "Hide from website" : "Show on website"}</button>
          <button className="button ghost" type="button" onClick={() => refreshEpisode(client, episodeId)}><RefreshCcw size={16} />Refresh</button>
        </div>
        {episode.transcript_status === "completed" && !labels.isLoading && !mappingComplete && <Notice>Complete the <Link to={`/admin/episodes/${episodeId}/speaker-mapping`}>speaker mapping</Link> before extracting trivia.</Notice>}
        <ErrorMessage error={labels.error ?? transcribe.error ?? publication.error} />
      </section>
      <section className="workspace-section episode-danger-zone">
        <div><SectionHeading icon={<Trash2 />} title="Delete episode" /><p>Delete this episode and all of its stored content.</p></div>
        <button className="button danger-button" type="button" onClick={() => setDeleteOpen(true)} disabled={processing || remove.isPending}><Trash2 size={16} />Delete episode</button>
        <ErrorMessage error={remove.error} />
      </section>
      {deleteOpen && <div className="dialog-backdrop">
        <section className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-episode-title">
          <div className="confirmation-dialog-heading"><div><p className="eyebrow">Permanent action</p><h2 id="delete-episode-title">Delete {episode.episode_title}?</h2></div><button className="icon-button" type="button" aria-label="Close delete dialog" onClick={() => { setDeleteOpen(false); setDeleteConfirmation(""); }}><X size={18} /></button></div>
          <p>Audio, transcript, trivia, speaker mappings, and processing history will be permanently deleted. This cannot be undone.</p>
          <label className="field"><span>Type the episode title to confirm</span><input autoFocus value={deleteConfirmation} onChange={event => setDeleteConfirmation(event.target.value)} /></label>
          <div className="form-actions"><button className="button" type="button" onClick={() => { setDeleteOpen(false); setDeleteConfirmation(""); }}>Cancel</button><button className="button destructive" type="button" onClick={() => remove.mutate()} disabled={!deletionConfirmed || remove.isPending}>{remove.isPending ? <Loader2 className="spin" size={16} /> : <Trash2 size={16} />}Delete permanently</button></div>
        </section>
      </div>}
    </>
  );
}

function AdminEpisodeArtwork({ episode }: { episode: Episode }) {
  const [failed, setFailed] = useState(false);
  const artwork = episode.artwork_url ? apiAssetUrl(`/episodes/${episode.id}/artwork`) : null;
  useEffect(() => setFailed(false), [artwork]);
  return <img className="admin-episode-artwork" src={!failed && artwork ? artwork : thumbnailUrl} alt={`${episode.episode_title} artwork`} onError={() => setFailed(true)} />;
}

export function EpisodeDetailsTab() {
  const { episode } = useEpisodeWorkspace();
  const client = useQueryClient();
  const allSpeakers = useQuery({ queryKey: ["speakers"], queryFn: listSpeakers });
  const [draft, setDraft] = useState(() => detailsDraft(episode));
  useEffect(() => setDraft(detailsDraft(episode)), [episode]);
  const save = useMutation({
    mutationFn: () => updateEpisode(episode.id, {
      episode_title: draft.title.trim(), episode_number: draft.number === "" ? null : draft.number,
      episode_kind: draft.kind,
      episode_description: draft.description.trim() || null,
      published_at: draft.publishedAt || null, source_url: draft.sourceUrl.trim() || null,
      speaker_ids: draft.speakerIds, is_published: episode.is_published ?? false
    }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["episode", episode.id] });
      void client.invalidateQueries({ queryKey: ["episodes"] });
    }
  });

  return (
    <section className="workspace-section">
      <SectionHeading title="Edit episode details" hint="Changes to episodes visible on the website appear immediately." />
      <form className="form-grid" onSubmit={event => { event.preventDefault(); save.mutate(); }}>
        <label className="field"><RequiredLabel>Episode title</RequiredLabel><input required value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
        <label className="field"><span>Episode kind</span><select value={draft.kind} onChange={event => setDraft({ ...draft, kind: event.target.value as NonNullable<Episode["episode_kind"]>, number: event.target.value === "announcement" ? "" : draft.number || 1 })}><option value="main">Main episode</option><option value="mini">Mini episode</option><option value="announcement">Announcement</option></select></label>
        <label className="field">{draft.kind === "announcement" ? <span>Episode number</span> : <RequiredLabel>Episode number</RequiredLabel>}<input required={draft.kind !== "announcement"} type="number" min="1" value={draft.number} onChange={event => setDraft({ ...draft, number: event.target.value ? Number(event.target.value) : "" })} /></label>
        <label className="field full"><span>Description</span><textarea rows={4} value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
        <label className="field"><span>Published at</span><input type="datetime-local" value={draft.publishedAt} onChange={event => setDraft({ ...draft, publishedAt: event.target.value })} /></label>
        <label className="field"><span>Source URL</span><input type="url" value={draft.sourceUrl} onChange={event => setDraft({ ...draft, sourceUrl: event.target.value })} /></label>
        <fieldset className="field full speaker-picker"><legend>Episode speakers</legend>
          {allSpeakers.isLoading ? <Loading /> : allSpeakers.error ? <ErrorMessage error={allSpeakers.error} /> : <div className="checkbox-grid">{allSpeakers.data?.map(speaker => <label className="check-row" key={speaker.id}><input type="checkbox" checked={draft.speakerIds.includes(speaker.id)} onChange={event => setDraft({ ...draft, speakerIds: event.target.checked ? [...draft.speakerIds, speaker.id] : draft.speakerIds.filter(id => id !== speaker.id) })} />{speaker.name}</label>)}</div>}
        </fieldset>
        {save.isSuccess && <div className="full"><Notice kind="success">Episode details saved.</Notice></div>}
        {save.error && isUnsupportedFeature(save.error) ? <div className="full"><ComingSoon feature="Episode editing" /></div> : <div className="full"><ErrorMessage error={save.error} /></div>}
        <div className="form-actions full"><button className="button primary" disabled={save.isPending || !draft.title.trim() || draft.speakerIds.length === 0}><Save size={16} />Save details</button></div>
      </form>
    </section>
  );
}

export function EpisodeSpeakerMappingTab() {
  const { episode, episodeId } = useEpisodeWorkspace();
  const client = useQueryClient();
  const labels = useQuery({ queryKey: ["speaker-labels", episodeId], queryFn: () => getSpeakerLabels(episodeId), enabled: episode.transcript_status === "completed" });
  const [draft, setDraft] = useState<Record<string, string>>({});
  useEffect(() => { if (labels.data) setDraft(mappingFromLabels(labels.data)); }, [labels.data]);
  const save = useMutation({ mutationFn: () => saveSpeakerMapping(episodeId, draft), onSuccess: () => void client.invalidateQueries({ queryKey: ["speaker-labels", episodeId] }) });

  return (
    <section className="workspace-section">
      <SectionHeading title="Speaker mapping" hint="Map every diarization label before extracting trivia." />
      {episode.transcript_status !== "completed" && <Notice>Run transcription from Overview before mapping speakers.</Notice>}
      {labels.isLoading && <Loading />}<ErrorMessage error={labels.error ?? save.error} />
      {labels.data?.labels.length === 0 && <Notice>No diarized speaker labels were found.</Notice>}
      {labels.data?.labels.map(label => <div className="mapping-row" key={label.label}>
        <div className="label-meta"><strong>{label.label}</strong><span>{label.segment_count} segments · {formatSeconds(label.first_seen)}-{formatSeconds(label.last_seen)}</span><audio controls src={apiAssetUrl(label.sample_clip_url) ?? undefined} /></div>
        <label className="field"><span>Speaker</span><select value={draft[label.label] ?? ""} onChange={event => setDraft({ ...draft, [label.label]: event.target.value })}><option value="">Unmapped</option>{labels.data.speakers.map(speaker => <option value={speaker.id} key={speaker.id}>{speaker.name}</option>)}</select></label>
        <div className="sample-list">{label.samples.map((sample, index) => <div className="sample-row" key={`${label.label}-${index}`}><audio controls src={apiAssetUrl(sample.sample_clip_url) ?? undefined} /><span>{formatSeconds(sample.start)}-{formatSeconds(sample.end)}</span><p>{sample.text}</p></div>)}</div>
      </div>)}
      {save.isSuccess && <Notice kind="success">Speaker mapping saved.</Notice>}
      {labels.data && labels.data.labels.length > 0 && <button className="button primary section-action" type="button" onClick={() => save.mutate()} disabled={save.isPending || !isSpeakerMappingComplete(labels.data, draft)}><Save size={16} />Save mapping</button>}
    </section>
  );
}

export function EpisodeTranscriptTab() {
  const { episode, episodeId } = useEpisodeWorkspace();
  const [mode, setMode] = useState<"script" | "json">("script");
  const transcript = useQuery({ queryKey: ["transcript", episodeId], queryFn: () => getTranscript(episodeId), enabled: episode.transcript_status === "completed" });
  const mapping = useQuery({ queryKey: ["speaker-mapping", episodeId], queryFn: () => getSpeakerMapping(episodeId), enabled: episode.transcript_status === "completed" });
  const blocks = useMemo(() => transcript.data ? transcriptScriptBlocks(transcript.data.transcript, mapping.data?.mappings) : [], [mapping.data?.mappings, transcript.data]);

  return (
    <section className="workspace-section">
      <div className="transcript-heading"><SectionHeading title="Transcript" /><div className="segmented-control" role="group" aria-label="Transcript view"><button type="button" aria-pressed={mode === "script"} onClick={() => setMode("script")}>Script</button><button type="button" aria-pressed={mode === "json"} onClick={() => setMode("json")}>JSON</button></div></div>
      {episode.transcript_status !== "completed" && <Notice>Run transcription from Overview to create a transcript.</Notice>}
      {transcript.isLoading && <Loading />}<ErrorMessage error={transcript.error ?? mapping.error} />
      {transcript.data && mode === "script" && (blocks.length > 0 ? <div className="script-view">{blocks.map((block, index) => <article className="script-block" key={`${block.speakerLabel}-${block.start}-${index}`}><header><strong>{block.speakerName}</strong><span>{timeRange(block.start, block.end)}</span></header><p>{block.text}</p></article>)}</div> : <Notice>No readable transcript segments were found. Use JSON to inspect the raw transcript.</Notice>)}
      {transcript.data && mode === "json" && <pre className="json-panel">{JSON.stringify(transcript.data.transcript, null, 2)}</pre>}
    </section>
  );
}

export function EpisodeTriviaTab() {
  const { episode, episodeId, activeJobId, job, setActiveJobId } = useEpisodeWorkspace();
  const client = useQueryClient();
  const review = useQuery({ queryKey: ["trivia-candidate-review", episodeId], queryFn: () => getTriviaCandidateReview(episodeId) });
  const labels = useQuery({
    queryKey: ["speaker-labels", episodeId],
    queryFn: () => getSpeakerLabels(episodeId),
    enabled: episode.transcript_status === "completed"
  });
  const mappingComplete = isSpeakerMappingComplete(labels.data, mappingFromLabels(labels.data));
  const currentJob = job.data ?? episode.active_job ?? undefined;
  const processing = shouldPollJob(currentJob);
  const generate = useMutation({
    mutationFn: () => startTriviaCandidateExtraction(episodeId),
    onSuccess: accepted => {
      setJob(accepted, setActiveJobId);
      void client.invalidateQueries({ queryKey: ["trivia-candidate-review", episodeId] });
    }
  });
  const apply = useMutation({
    mutationFn: (candidateId: string) => applyTriviaCandidate(episodeId, candidateId),
    onSuccess: () => refreshEpisode(client, episodeId)
  });
  const discard = useMutation({
    mutationFn: (candidateId: string) => discardTriviaCandidate(episodeId, candidateId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["trivia-candidate-review", episodeId] });
    }
  });

  useEffect(() => {
    if (job.data?.status === "succeeded" || job.data?.status === "failed") {
      void client.invalidateQueries({ queryKey: ["trivia-candidate-review", episodeId] });
    }
  }, [client, episodeId, job.data?.status]);

  return (
    <section className="workspace-section">
      <div className="section-title-row">
        <SectionHeading title="Extracted trivia" hint={episode.trivia_count > 0 ? `${episode.trivia_count} live items` : undefined} />
        <button className="button primary" type="button" onClick={() => generate.mutate()} disabled={generate.isPending || processing || !mappingComplete}>
          {generate.isPending ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}Generate new extraction
        </button>
      </div>
      {(activeJobId || episode.active_job) && <JobPanel job={currentJob} error={job.error} />}
      {episode.transcript_status === "completed" && !labels.isLoading && !mappingComplete && <Notice>Complete the <Link to={`/admin/episodes/${episodeId}/speaker-mapping`}>speaker mapping</Link> before extracting trivia.</Notice>}
      <ErrorMessage error={labels.error ?? generate.error ?? apply.error ?? discard.error} />
      <QueryState query={review} empty="No trivia extracted yet.">
        {state => {
          const candidate = state.candidate;
          if (candidate && candidate.status === "ready") return (
            <div className="trivia-review">
              <div className="trivia-review-heading">
                <div><p className="eyebrow">Review extraction</p><h2>Current vs new trivia</h2></div>
                <div className="form-actions">
                  <button className="button" type="button" onClick={() => discard.mutate(candidate.id)} disabled={discard.isPending}>Discard</button>
                  <button className="button primary" type="button" onClick={() => apply.mutate(candidate.id)} disabled={apply.isPending}>{apply.isPending ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}Replace with new trivia</button>
                </div>
              </div>
              <div className="trivia-review-grid">
                <TriviaReviewColumn title="Current trivia" items={state.current_trivia} speakers={episode.speakers} editable />
                <TriviaReviewColumn title="New extraction" items={candidate.trivia} speakers={episode.speakers} />
              </div>
            </div>
          );
          if (candidate && candidate.status === "failed") return (
            <>
              <Notice>Latest extraction failed: {candidate.error || "Unknown error"}</Notice>
              <TriviaReviewColumn title="Current trivia" items={state.current_trivia} speakers={episode.speakers} editable />
            </>
          );
          return <TriviaReviewColumn title="Current trivia" items={state.current_trivia} speakers={episode.speakers} editable />;
        }}
      </QueryState>
    </section>
  );
}

function TriviaReviewColumn({ title, items, speakers, editable = false }: { title: string; items: TriviaItem[]; speakers: Speaker[]; editable?: boolean }) {
  return (
    <div className="trivia-review-column">
      <div className="trivia-column-heading"><h3>{title}</h3><span>{items.length} {items.length === 1 ? "item" : "items"}</span></div>
      {items.length ? <div className="admin-trivia-list">{items.map(item => editable ? <TriviaItemCard key={item.id} item={item} speakers={speakers} /> : <TriviaPreviewCard key={item.id} item={item} />)}</div> : <Notice>No trivia extracted yet.</Notice>}
    </div>
  );
}

function TriviaPreviewCard({ item }: { item: TriviaItem }) {
  return (
    <article className="admin-trivia-item trivia-read-card">
      <div className="trivia-editor-header"><div><span>{item.type}</span><strong>{triviaAskerName(item)}</strong></div><span className="muted">{timeRange(Number(item.timestamps.start ?? 0), Number(item.timestamps.end ?? item.timestamps.start ?? 0))}</span></div>
      <h3>{item.question || "Untitled trivia item"}</h3>
      <div className="trivia-answer"><span>Answer</span><p>{item.answer || "No answer provided."}</p></div>
      <div className="trivia-meta"><span className={`confidence-chip confidence-${item.confidence.toLowerCase()}`}>{item.confidence} confidence</span>{item.keywords.map(keyword => <span key={keyword}>{keyword}</span>)}</div>
    </article>
  );
}

export function TriviaItemCard({ item, speakers }: { item: TriviaItem; speakers: Speaker[] }) {
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => triviaDraft(item));
  const [suggestion, setSuggestion] = useState<{ question: string | null; answer: string | null } | null>(null);
  useEffect(() => { if (!editing) setDraft(triviaDraft(item)); }, [editing, item]);
  const save = useMutation({ mutationFn: () => updateTriviaItem(item.id, draft), onSuccess: () => { setEditing(false); setSuggestion(null); void client.invalidateQueries({ queryKey: ["trivia", item.episode_id] }); void client.invalidateQueries({ queryKey: ["episode", item.episode_id] }); } });
  const remove = useMutation({ mutationFn: () => deleteTriviaItem(item.id), onSuccess: () => { void client.invalidateQueries({ queryKey: ["trivia", item.episode_id] }); void client.invalidateQueries({ queryKey: ["episode", item.episode_id] }); } });
  const rephrase = useMutation({ mutationFn: () => rephraseTriviaItem(item.id), onSuccess: setSuggestion });
  const unsupported = [save.error, remove.error, rephrase.error].find(isUnsupportedFeature);

  if (!editing) return (
    <article className="admin-trivia-item trivia-read-card">
      <div className="trivia-editor-header"><div><span>{item.type}</span><strong>{triviaAskerName(item)}</strong></div><button className="button compact-button" type="button" onClick={() => setEditing(true)}><Pencil size={15} />Edit</button></div>
      <h3>{item.question || "Untitled trivia item"}</h3>
      <div className="trivia-answer"><span>Answer</span><p>{item.answer || "No answer provided."}</p></div>
      <div className="trivia-meta"><span className={`confidence-chip confidence-${item.confidence.toLowerCase()}`}>{item.confidence} confidence</span>{item.keywords.map(keyword => <span key={keyword}>{keyword}</span>)}</div>
    </article>
  );

  return (
    <article className="admin-trivia-item trivia-edit-card">
      <div className="trivia-editor-header"><div><span>Editing</span><strong>{triviaAskerName(item)}</strong></div><button className="icon-button" type="button" aria-label="Cancel editing" onClick={() => { setDraft(triviaDraft(item)); setSuggestion(null); setEditing(false); }}><X size={16} /></button></div>
      <div className="form-grid">
        <label className="field full"><span>Question</span><textarea rows={2} value={draft.question ?? ""} onChange={event => setDraft({ ...draft, question: event.target.value || null })} /></label>
        <label className="field full"><span>Answer</span><textarea rows={2} value={draft.answer ?? ""} onChange={event => setDraft({ ...draft, answer: event.target.value || null })} /></label>
        <label className="field"><span>Type</span><input value={draft.type} onChange={event => setDraft({ ...draft, type: event.target.value })} /></label>
        <label className="field"><span>Confidence</span><input value={draft.confidence} onChange={event => setDraft({ ...draft, confidence: event.target.value })} /></label>
        <label className="field"><span>Asker</span><select value={draft.asker_speaker_id ?? ""} onChange={event => setDraft({ ...draft, asker_speaker_id: event.target.value || null })}><option value="">Unmapped</option>{speakers.map(speaker => <option key={speaker.id} value={speaker.id}>{speaker.name}</option>)}</select></label>
        <label className="field"><span>Keywords</span><input value={draft.keywords.join(", ")} onChange={event => setDraft({ ...draft, keywords: event.target.value.split(",").map(word => word.trim()).filter(Boolean) })} /></label>
      </div>
      <div className="form-actions trivia-edit-actions"><button className="button primary" type="button" onClick={() => save.mutate()} disabled={save.isPending}><Save size={16} />Save changes</button><button className="button" type="button" onClick={() => rephrase.mutate()} disabled={rephrase.isPending}><Sparkles size={16} />Suggest rephrase</button><button className="button danger-button" type="button" onClick={() => { if (window.confirm("Delete this trivia item?")) remove.mutate(); }} disabled={remove.isPending}><Trash2 size={16} />Delete</button></div>
      {suggestion && <div className="suggestion-panel"><p className="eyebrow">AI suggestion</p><h4>{suggestion.question}</h4><p>{suggestion.answer}</p><button className="button" type="button" onClick={() => { setDraft({ ...draft, question: suggestion.question, answer: suggestion.answer }); setSuggestion(null); }}>Use suggestion</button></div>}
      {unsupported ? <ComingSoon feature="Trivia editing and AI rephrasing" /> : <ErrorMessage error={save.error ?? remove.error ?? rephrase.error} />}
    </article>
  );
}

function useEpisodeWorkspace() { return useOutletContext<EpisodeWorkspaceContext>(); }
function detailsDraft(episode: Episode) { return { title: episode.episode_title, number: episode.episode_number ?? "" as number | "", kind: episode.episode_kind ?? "main", description: episode.episode_description ?? "", publishedAt: episode.published_at?.slice(0, 16) ?? "", sourceUrl: episode.source_url ?? "", speakerIds: episode.speakers.map(speaker => speaker.id) }; }
function triviaDraft(item: TriviaItem): TriviaUpdateInput { return { type: item.type, question: item.question, answer: item.answer, keywords: item.keywords, confidence: item.confidence, asker_speaker_id: item.asker?.id ?? null }; }
function mappingFromLabels(labels?: SpeakerLabels) { return labels ? Object.fromEntries(Object.entries(labels.mappings).map(([label, speaker]) => [label, speaker.id])) : {}; }
function setJob(accepted: JobAccepted, setter: (id: string) => void) { setter(accepted.job_id); }
function timeRange(start: number | null, end: number | null) { if (start === null && end === null) return "Time unavailable"; return `${formatSeconds(start ?? 0)}-${formatSeconds(end ?? start ?? 0)}`; }
function refreshEpisode(client: ReturnType<typeof useQueryClient>, episodeId: string) { [["episode", episodeId], ["episodes"], ["public"], ["speaker-labels", episodeId], ["speaker-mapping", episodeId], ["transcript", episodeId], ["trivia", episodeId], ["trivia-candidate-review", episodeId]].forEach(queryKey => void client.invalidateQueries({ queryKey })); }
function SectionHeading({ title, hint, icon }: { title: string; hint?: string; icon?: React.ReactNode }) { return <div className="section-heading"><div>{icon}<h2>{title}</h2></div>{hint && <p>{hint}</p>}</div>; }
function Metric({ label, value }: { label: string; value: React.ReactNode }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
function ProcessingMetric({ label, value, to, count = 0 }: { label: string; value: React.ReactNode; to: string; count?: number }) { return <Link className="metric processing-metric" to={to}><span>{label}</span><strong>{value}{count > 0 && <span className="metric-count" aria-label={`${count} trivia ${count === 1 ? "item" : "items"}`}>{count}</span>}</strong><ArrowRight aria-hidden="true" /></Link>; }
function Detail({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) { return <div className={wide ? "detail-item wide" : "detail-item"}><dt>{label}</dt><dd>{children}</dd></div>; }
function JobPanel({ job, error }: { job?: Job; error: Error | null }) { if (error) return <ErrorMessage error={error} />; if (!job) return <Loading />; const percent = job.progress_current != null && job.progress_total ? Math.min(100, Math.round(job.progress_current / job.progress_total * 100)) : null; return <div className="job-progress"><Notice kind={job.status === "failed" ? "error" : job.status === "succeeded" ? "success" : "info"}>{job.status === "succeeded" ? <CheckCircle2 size={16} /> : job.status === "failed" ? <AlertCircle size={16} /> : <CircleDashed className="spin" size={16} />}{job.progress_stage || job.kind} is {job.status}{job.error ? `: ${job.error}` : ""}</Notice>{percent !== null && <progress max="100" value={percent} />}</div>; }
function episodeLabel(episode: Episode) { if (episode.episode_kind === "announcement") return "Announcement"; if (episode.episode_kind === "mini") return `Mini episode ${episode.episode_number}`; return `Episode ${episode.episode_number}`; }
