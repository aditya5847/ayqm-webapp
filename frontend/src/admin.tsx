import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, LayoutDashboard, Loader2, LogOut, Pencil, Plus, Save, Trash2, Upload, Users } from "lucide-react";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  createSpeaker, deleteSpeaker, getAdminSession, isUnsupportedFeature,
  listEpisodes, listSpeakers, loginAdmin, logoutAdmin, updateSpeaker, uploadEpisode
} from "./api";
import type { Speaker } from "./types";
import { formatDate } from "./workflow";
import { ComingSoon, ErrorMessage, Loading, QueryState, RequiredLabel, StatusPill } from "./ui";
import logoUrl from "../references/Logo.png";

export function AdminGate() {
  const location = useLocation();
  const session = useQuery({ queryKey: ["admin", "session"], queryFn: getAdminSession, retry: false });
  if (session.isLoading) return <div className="centered-state"><Loading /></div>;
  if (session.error && isUnsupportedFeature(session.error)) return <AdminFrame><ComingSoon feature="The secure admin workspace" /></AdminFrame>;
  if (session.error && "status" in session.error && session.error.status === 401) return <Navigate to="/admin/login" state={{ from: location.pathname }} replace />;
  if (session.error) return <AdminFrame><ErrorMessage error={session.error} /></AdminFrame>;
  if (!session.data?.authenticated) return <Navigate to="/admin/login" replace />;
  return <AdminLayout />;
}

export function AdminLoginPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => loginAdmin(password),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["admin", "session"] }); navigate("/admin/episodes"); }
  });
  return <div className="login-shell"><Link to="/" className="login-logo"><img src={logoUrl} alt="Are You Quizzing Me?" /></Link><form className="login-panel" onSubmit={event => { event.preventDefault(); login.mutate(); }}><p className="eyebrow">Podcast operations</p><h1>Admin sign in</h1><p>Manage episodes, speakers, transcripts, and trivia.</p><label className="field"><RequiredLabel>Password</RequiredLabel><input type="password" required autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} /></label>{login.error && isUnsupportedFeature(login.error) ? <ComingSoon feature="Admin sign in" /> : <ErrorMessage error={login.error} />}<button className="button primary" type="submit" disabled={login.isPending}>{login.isPending && <Loader2 className="spin" size={17} />}Sign in</button></form></div>;
}

function AdminFrame({ children }: { children: React.ReactNode }) {
  return <div className="admin-shell"><aside className="admin-sidebar"><Link className="admin-brand" to="/"><img src={logoUrl} alt="Are You Quizzing Me?" /></Link></aside><main className="admin-main">{children}</main></div>;
}

function AdminLayout() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const logout = useMutation({ mutationFn: logoutAdmin, onSuccess: () => { client.clear(); navigate("/admin/login"); } });
  return <div className="admin-shell"><aside className="admin-sidebar"><Link className="admin-brand" to="/"><img src={logoUrl} alt="Are You Quizzing Me?" /></Link><p className="workspace-label">Admin workspace</p><nav className="admin-nav" aria-label="Admin navigation"><NavLink to="/admin/episodes"><LayoutDashboard size={18} />Episodes</NavLink><NavLink to="/admin/episodes/new"><Upload size={18} />Upload</NavLink><NavLink to="/admin/speakers"><Users size={18} />Speakers</NavLink></nav><div className="admin-sidebar-bottom"><Link to="/">View public site <ExternalLink size={15} /></Link><button type="button" onClick={() => logout.mutate()}><LogOut size={16} />Sign out</button></div></aside><main className="admin-main"><Outlet /></main></div>;
}

export function AdminEpisodesPage() {
  const episodes = useQuery({ queryKey: ["episodes"], queryFn: listEpisodes });
  return <AdminPage title="Episodes" actions={<Link className="button primary" to="/admin/episodes/new"><Upload size={16} />Upload episode</Link>}><QueryState query={episodes} empty="No episodes uploaded yet.">{items => <div className="table-wrap"><table><thead><tr><th>Episode</th><th>Visibility</th><th>Transcript</th><th>Trivia</th><th>Updated</th></tr></thead><tbody>{items.map(episode => <tr key={episode.id}><td><Link className="row-title" to={`/admin/episodes/${episode.id}`}>#{episode.episode_number} {episode.episode_title}</Link><div className="muted clamp">{episode.episode_description}</div></td><td><StatusPill value={episode.is_published ? "published" : "draft"} /></td><td><StatusPill value={episode.transcript_status} /></td><td><StatusPill value={episode.trivia_status} /> <span className="count">{episode.trivia_count}</span></td><td>{formatDate(episode.updated_at)}</td></tr>)}</tbody></table></div>}</QueryState></AdminPage>;
}

export function UploadPage() {
  const navigate = useNavigate();
  const speakers = useQuery({ queryKey: ["speakers"], queryFn: listSpeakers });
  const mutation = useMutation({ mutationFn: uploadEpisode, onSuccess: episode => navigate(`/admin/episodes/${episode.id}`) });
  const [file, setFile] = useState<File | null>(null); const [title, setTitle] = useState(""); const [number, setNumber] = useState(1);
  const [description, setDescription] = useState(""); const [publishedAt, setPublishedAt] = useState(""); const [sourceUrl, setSourceUrl] = useState("");
  const [speakerIds, setSpeakerIds] = useState<string[]>([]); const [extraMetadata, setExtraMetadata] = useState("{}"); const [formError, setFormError] = useState<string | null>(null);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setFormError(null);
    if (!file) return setFormError("Choose an audio file.");
    if (speakerIds.length === 0) return setFormError("Select at least one episode speaker.");
    let parsedMetadata: Record<string, unknown> = {};
    try { parsedMetadata = extraMetadata.trim() ? JSON.parse(extraMetadata) : {}; if (!parsedMetadata || Array.isArray(parsedMetadata) || typeof parsedMetadata !== "object") throw new Error("Extra metadata must be a JSON object."); }
    catch (error) { return setFormError(error instanceof Error ? error.message : "Extra metadata must be valid JSON."); }
    mutation.mutate({ file, episode_title: title, episode_number: number, episode_description: description, published_at: publishedAt, source_url: sourceUrl, speaker_ids: speakerIds, extra_metadata: parsedMetadata });
  }
  return <AdminPage title="Upload episode"><form className="form-grid" onSubmit={submit}><label className="field full"><RequiredLabel>Audio file</RequiredLabel><input required type="file" accept="audio/*" onChange={event => setFile(event.target.files?.[0] ?? null)} /></label><label className="field"><RequiredLabel>Episode title</RequiredLabel><input required value={title} onChange={event => setTitle(event.target.value)} /></label><label className="field"><RequiredLabel>Episode number</RequiredLabel><input required type="number" min="1" value={number} onChange={event => setNumber(Number(event.target.value))} /></label><label className="field full"><span>Description</span><textarea rows={4} value={description} onChange={event => setDescription(event.target.value)} /></label><label className="field"><span>Published at</span><input type="datetime-local" value={publishedAt} onChange={event => setPublishedAt(event.target.value)} /></label><label className="field"><span>Source URL</span><input type="url" value={sourceUrl} onChange={event => setSourceUrl(event.target.value)} /></label><fieldset className="field full speaker-picker"><legend><RequiredLabel>Episode speakers</RequiredLabel></legend><QueryState query={speakers} empty="Create speakers before uploading episodes.">{items => <div className="checkbox-grid">{items.map(speaker => <label className="check-row" key={speaker.id}><input type="checkbox" checked={speakerIds.includes(speaker.id)} onChange={event => setSpeakerIds(current => event.target.checked ? [...current, speaker.id] : current.filter(id => id !== speaker.id))} /><span>{speaker.name}</span></label>)}</div>}</QueryState></fieldset><label className="field full"><span>Extra metadata (JSON)</span><textarea rows={5} value={extraMetadata} onChange={event => setExtraMetadata(event.target.value)} spellCheck={false} /></label><div className="full"><ErrorMessage error={formError ?? mutation.error} /></div><div className="form-actions full"><button className="button primary" disabled={mutation.isPending}>{mutation.isPending ? <Loader2 className="spin" size={16} /> : <Upload size={16} />}Upload episode</button></div></form></AdminPage>;
}

export function SpeakersPage() {
  const client = useQueryClient(); const speakers = useQuery({ queryKey: ["speakers"], queryFn: listSpeakers }); const [name, setName] = useState("");
  const create = useMutation({ mutationFn: () => createSpeaker(name.trim()), onSuccess: () => { setName(""); void client.invalidateQueries({ queryKey: ["speakers"] }); } });
  return <AdminPage title="Speakers"><form className="inline-form" onSubmit={event => { event.preventDefault(); if (name.trim()) create.mutate(); }}><input aria-label="Speaker name" placeholder="Speaker name" value={name} onChange={event => setName(event.target.value)} /><button className="button primary" disabled={!name.trim() || create.isPending}><Plus size={16} />Add speaker</button></form><ErrorMessage error={create.error} /><QueryState query={speakers} empty="No speakers yet.">{items => <div className="item-list">{items.map(speaker => <SpeakerRow key={speaker.id} speaker={speaker} />)}</div>}</QueryState></AdminPage>;
}

function SpeakerRow({ speaker }: { speaker: Speaker }) {
  const client = useQueryClient(); const [editing, setEditing] = useState(false); const [name, setName] = useState(speaker.name);
  const update = useMutation({ mutationFn: () => updateSpeaker(speaker.id, name.trim()), onSuccess: () => { setEditing(false); void client.invalidateQueries({ queryKey: ["speakers"] }); } });
  const remove = useMutation({ mutationFn: () => deleteSpeaker(speaker.id), onSuccess: () => void client.invalidateQueries({ queryKey: ["speakers"] }) });
  return <div className="item-row">{editing ? <input aria-label={`Rename ${speaker.name}`} value={name} onChange={event => setName(event.target.value)} /> : <strong>{speaker.name}</strong>}<div className="row-actions">{editing ? <button className="icon-button" aria-label="Save speaker" onClick={() => update.mutate()} disabled={!name.trim()}><Save size={16} /></button> : <button className="icon-button" aria-label="Rename speaker" onClick={() => setEditing(true)}><Pencil size={16} /></button>}<button className="icon-button danger" aria-label="Delete speaker" onClick={() => remove.mutate()}><Trash2 size={16} /></button></div><ErrorMessage compact error={update.error ?? remove.error} /></div>;
}

function AdminPage({ title, actions, children }: { title: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return <><header className="admin-page-header"><div><p className="eyebrow">Podcast operations</p><h1>{title}</h1></div>{actions}</header>{children}</>;
}
