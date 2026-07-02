import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle, ArrowLeft, CheckCircle2, CircleDashed, ExternalLink, FileAudio,
  Loader2, Mic2, Pencil, RefreshCcw, Save, Sparkles, Trash2, X
} from "lucide-react";
import { Link, NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import {
  apiAssetUrl, deleteTriviaItem, getEpisode, getJob, getSpeakerLabels,
  getSpeakerMapping, getTranscript, getTrivia, isUnsupportedFeature, listSpeakers,
  rephraseTriviaItem, saveSpeakerMapping, startTranscription, startTriviaExtraction,
  updateEpisode, updateTriviaItem
} from "./api";
import type { Episode, Job, JobAccepted, Speaker, SpeakerLabels, TriviaItem, TriviaUpdateInput } from "./types";
import { transcriptScriptBlocks } from "./transcript";
import { formatDate, formatSeconds, isSpeakerMappingComplete, shouldPollJob, triviaAskerName } from "./workflow";
import { ComingSoon, ErrorMessage, Loading, Notice, QueryState, RequiredLabel, StatusPill } from "./ui";

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
    if (job.data?.status === "succeeded" || job.data?.status === "failed") refreshEpisode(client, episodeId);
  }, [client, episodeId, job.data?.status]);

  return (
    <QueryState query={episode}>
      {item => (
        <div className="episode-workspace">
          <Link className="back-link" to="/admin/episodes"><ArrowLeft size={17} />Back to episodes</Link>
          <header className="episode-workspace-heading">
            <div><p className="eyebrow">Episode {item.episode_number}</p><h1>{item.episode_title}</h1></div>
            <StatusPill value={item.is_published ? "published" : "draft"} />
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
  const labels = useQuery({
    queryKey: ["speaker-labels", episodeId],
    queryFn: () => getSpeakerLabels(episodeId),
    enabled: episode.transcript_status === "completed"
  });
  const mappingComplete = isSpeakerMappingComplete(labels.data, mappingFromLabels(labels.data));
  const transcribe = useMutation({ mutationFn: () => startTranscription(episodeId), onSuccess: accepted => setJob(accepted, setActiveJobId) });
  const extract = useMutation({ mutationFn: () => startTriviaExtraction(episodeId), onSuccess: accepted => setJob(accepted, setActiveJobId) });

  return (
    <>
      <section className="workspace-section">
        <SectionHeading title="Episode overview" />
        <dl className="episode-detail-grid">
          <Detail label="Title">{episode.episode_title}</Detail>
          <Detail label="Episode number">{episode.episode_number}</Detail>
          <Detail label="Description" wide>{episode.episode_description || "Not set"}</Detail>
          <Detail label="Published at">{formatDate(episode.published_at)}</Detail>
          <Detail label="Visibility"><StatusPill value={episode.is_published ? "published" : "draft"} /></Detail>
          <Detail label="Speakers">{episode.speakers.map(speaker => speaker.name).join(", ") || "Not set"}</Detail>
          <Detail label="Source">{episode.source_url ? <a href={episode.source_url} target="_blank" rel="noreferrer">Open episode <ExternalLink size={14} /></a> : "Not set"}</Detail>
          <Detail label="Created">{formatDate(episode.created_at)}</Detail>
          <Detail label="Updated">{formatDate(episode.updated_at)}</Detail>
        </dl>
      </section>
      <section className="workspace-section">
        <SectionHeading icon={<FileAudio />} title="Processing" />
        <div className="summary-grid">
          <Metric label="Transcript" value={<StatusPill value={episode.transcript_status} />} />
          <Metric label="Trivia" value={<StatusPill value={episode.trivia_status} />} />
          <Metric label="Trivia items" value={episode.trivia_count} />
          <Metric label="Speaker mapping" value={mappingComplete ? "Complete" : "Incomplete"} />
        </div>
        {activeJobId && <JobPanel job={job.data} error={job.error} />}
        <div className="action-strip">
          <button className="button primary" type="button" onClick={() => transcribe.mutate()} disabled={transcribe.isPending || shouldPollJob(job.data)}><Mic2 size={16} />Transcribe</button>
          <button className="button" type="button" onClick={() => extract.mutate()} disabled={extract.isPending || shouldPollJob(job.data) || !mappingComplete}><Sparkles size={16} />Extract trivia</button>
          <button className="button ghost" type="button" onClick={() => refreshEpisode(client, episodeId)}><RefreshCcw size={16} />Refresh</button>
        </div>
        {episode.transcript_status === "completed" && !labels.isLoading && !mappingComplete && <Notice>Complete the <Link to={`/admin/episodes/${episodeId}/speaker-mapping`}>speaker mapping</Link> before extracting trivia.</Notice>}
        <ErrorMessage error={labels.error ?? transcribe.error ?? extract.error} />
      </section>
    </>
  );
}

export function EpisodeDetailsTab() {
  const { episode } = useEpisodeWorkspace();
  const client = useQueryClient();
  const allSpeakers = useQuery({ queryKey: ["speakers"], queryFn: listSpeakers });
  const [draft, setDraft] = useState(() => detailsDraft(episode));
  useEffect(() => setDraft(detailsDraft(episode)), [episode]);
  const save = useMutation({
    mutationFn: () => updateEpisode(episode.id, {
      episode_title: draft.title.trim(), episode_number: draft.number,
      episode_description: draft.description.trim() || null,
      published_at: draft.publishedAt || null, source_url: draft.sourceUrl.trim() || null,
      speaker_ids: draft.speakerIds, is_published: draft.published
    }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["episode", episode.id] });
      void client.invalidateQueries({ queryKey: ["episodes"] });
    }
  });

  return (
    <section className="workspace-section">
      <SectionHeading title="Edit episode details" hint="Changes to published episodes appear on the public site immediately." />
      <form className="form-grid" onSubmit={event => { event.preventDefault(); save.mutate(); }}>
        <label className="field"><RequiredLabel>Episode title</RequiredLabel><input required value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
        <label className="field"><RequiredLabel>Episode number</RequiredLabel><input required type="number" min="1" value={draft.number} onChange={event => setDraft({ ...draft, number: Number(event.target.value) })} /></label>
        <label className="field full"><span>Description</span><textarea rows={4} value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
        <label className="field"><span>Published at</span><input type="datetime-local" value={draft.publishedAt} onChange={event => setDraft({ ...draft, publishedAt: event.target.value })} /></label>
        <label className="field"><span>Source URL</span><input type="url" value={draft.sourceUrl} onChange={event => setDraft({ ...draft, sourceUrl: event.target.value })} /></label>
        <fieldset className="field full speaker-picker"><legend>Episode speakers</legend>
          {allSpeakers.isLoading ? <Loading /> : allSpeakers.error ? <ErrorMessage error={allSpeakers.error} /> : <div className="checkbox-grid">{allSpeakers.data?.map(speaker => <label className="check-row" key={speaker.id}><input type="checkbox" checked={draft.speakerIds.includes(speaker.id)} onChange={event => setDraft({ ...draft, speakerIds: event.target.checked ? [...draft.speakerIds, speaker.id] : draft.speakerIds.filter(id => id !== speaker.id) })} />{speaker.name}</label>)}</div>}
        </fieldset>
        <label className="publish-toggle full"><input type="checkbox" checked={draft.published} onChange={event => setDraft({ ...draft, published: event.target.checked })} /><span><strong>Publish this episode</strong><small>Published episodes and their trivia appear on the public site.</small></span></label>
        {save.isSuccess && <div className="full"><Notice kind="success">Episode details saved.</Notice></div>}
        {save.error && isUnsupportedFeature(save.error) ? <div className="full"><ComingSoon feature="Episode editing and publishing" /></div> : <div className="full"><ErrorMessage error={save.error} /></div>}
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
  const { episode, episodeId } = useEpisodeWorkspace();
  const trivia = useQuery({ queryKey: ["trivia", episodeId], queryFn: () => getTrivia(episodeId) });
  return <section className="workspace-section"><SectionHeading title="Extracted trivia" hint={`${episode.trivia_count} items`} /><QueryState query={trivia} empty="No trivia extracted yet.">{items => <div className="admin-trivia-list">{items.map(item => <TriviaItemCard key={item.id} item={item} speakers={episode.speakers} />)}</div>}</QueryState></section>;
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
      <div className="trivia-meta"><span>{item.confidence} confidence</span>{item.keywords.map(keyword => <span key={keyword}>{keyword}</span>)}</div>
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
function detailsDraft(episode: Episode) { return { title: episode.episode_title, number: episode.episode_number, description: episode.episode_description ?? "", publishedAt: episode.published_at?.slice(0, 16) ?? "", sourceUrl: episode.source_url ?? "", speakerIds: episode.speakers.map(speaker => speaker.id), published: episode.is_published ?? false }; }
function triviaDraft(item: TriviaItem): TriviaUpdateInput { return { type: item.type, question: item.question, answer: item.answer, keywords: item.keywords, confidence: item.confidence, asker_speaker_id: item.asker?.id ?? null }; }
function mappingFromLabels(labels?: SpeakerLabels) { return labels ? Object.fromEntries(Object.entries(labels.mappings).map(([label, speaker]) => [label, speaker.id])) : {}; }
function setJob(accepted: JobAccepted, setter: (id: string) => void) { setter(accepted.job_id); }
function timeRange(start: number | null, end: number | null) { if (start === null && end === null) return "Time unavailable"; return `${formatSeconds(start ?? 0)}-${formatSeconds(end ?? start ?? 0)}`; }
function refreshEpisode(client: ReturnType<typeof useQueryClient>, episodeId: string) { [["episode", episodeId], ["episodes"], ["speaker-labels", episodeId], ["speaker-mapping", episodeId], ["transcript", episodeId], ["trivia", episodeId]].forEach(queryKey => void client.invalidateQueries({ queryKey })); }
function SectionHeading({ title, hint, icon }: { title: string; hint?: string; icon?: React.ReactNode }) { return <div className="section-heading"><div>{icon}<h2>{title}</h2></div>{hint && <p>{hint}</p>}</div>; }
function Metric({ label, value }: { label: string; value: React.ReactNode }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
function Detail({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) { return <div className={wide ? "detail-item wide" : "detail-item"}><dt>{label}</dt><dd>{children}</dd></div>; }
function JobPanel({ job, error }: { job?: Job; error: Error | null }) { if (error) return <ErrorMessage error={error} />; if (!job) return <Loading />; return <Notice kind={job.status === "failed" ? "error" : job.status === "succeeded" ? "success" : "info"}>{job.status === "succeeded" ? <CheckCircle2 size={16} /> : job.status === "failed" ? <AlertCircle size={16} /> : <CircleDashed className="spin" size={16} />}{job.kind} is {job.status}{job.error ? `: ${job.error}` : ""}</Notice>; }
