import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { TriviaItemCard } from "./episode-admin";
import type { Episode, TriviaCandidateReview, TriviaItem } from "./types";

afterEach(() => vi.restoreAllMocks());

describe("episode workspace routing", () => {
  it("redirects the bare episode route to a read-only Overview with back navigation", async () => {
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode: { ...episode, transcript_status: "missing" } })));
    renderApp("/admin/episodes/episode-1");

    expect(await screen.findByRole("link", { name: /Back to episodes/ })).toHaveAttribute("href", "/admin/episodes");
    expect((await screen.findAllByText("Episode 12")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Episode overview" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("link", { name: "Overview" })).toHaveClass("active"));
    expect(await screen.findByRole("img", { name: "A test episode artwork" })).toHaveAttribute("src", "/references/Podcast%20Thumbnail.jpg");
    expect(screen.queryByRole("button", { name: "Save details" })).not.toBeInTheDocument();
  });

  it("keeps metadata editing in the Details tab", async () => {
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode, speakers: episode.speakers })));
    renderApp("/admin/episodes/episode-1/details");

    expect(await screen.findByRole("heading", { name: "Edit episode details" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Details" })).toHaveClass("active");
    expect(screen.getByRole("textbox", { name: /Episode title/ })).toHaveValue("A test episode");
    expect(screen.getByRole("button", { name: "Save details" })).toBeInTheDocument();
    expect(screen.queryByText("Publish this episode")).not.toBeInTheDocument();
  });

  it("shows imported artwork from the authenticated endpoint on Overview", async () => {
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode: { ...episode, artwork_url: "/public/episodes/episode-1/artwork" } })));
    renderApp("/admin/episodes/episode-1/overview");

    expect(await screen.findByRole("img", { name: "A test episode artwork" })).toHaveAttribute("src", "/api/episodes/episode-1/artwork");
  });

  it("publishes from Overview and keeps actions in workflow order", async () => {
    const fetchMock = vi.fn(requestRouter({ episode: { ...episode, transcript_status: "missing" } }));
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/admin/episodes/episode-1/overview");

    const transcribe = await screen.findByRole("button", { name: "Transcribe" });
    const extract = screen.getByRole("button", { name: "Extract trivia" });
    const publish = screen.getByRole("button", { name: "Show on website" });
    const refresh = screen.getByRole("button", { name: "Refresh" });
    expect(transcribe.compareDocumentPosition(extract) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(extract.compareDocumentPosition(publish) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(publish.compareDocumentPosition(refresh) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(publish);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/episodes/episode-1/publication",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ is_published: true }) })
    ));
  });

  it("orders processing metrics and uses the shared completed status style", async () => {
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode })));
    renderApp("/admin/episodes/episode-1/overview");

    const processingGrid = (await screen.findByText("Transcription")).closest(".summary-grid");
    const labels = Array.from(processingGrid?.querySelectorAll(".metric > span") ?? []).map(item => item.textContent);
    expect(labels).toEqual(["Transcription", "Speaker mapping", "Trivia extraction", "Website visibility"]);
    await waitFor(() => expect(processingGrid?.querySelectorAll(".status.completed")).toHaveLength(3));
    expect(processingGrid?.querySelector(".status.hidden")).toHaveTextContent("hidden");
    expect(processingGrid?.querySelector('a[href="/admin/episodes/episode-1/transcript"]')).toBeInTheDocument();
    expect(processingGrid?.querySelector('a[href="/admin/episodes/episode-1/speaker-mapping"]')).toBeInTheDocument();
    expect(processingGrid?.querySelector('a[href="/admin/episodes/episode-1/trivia"]')).toBeInTheDocument();
    expect(screen.getByLabelText("1 trivia item")).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: "Transcribe" })).not.toHaveClass("primary");
  });

  it("hides zero trivia counts in the overview", async () => {
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode: { ...episode, trivia_count: 0 } })));
    renderApp("/admin/episodes/episode-1/overview");

    expect(await screen.findByText("Trivia extraction")).toBeInTheDocument();
    expect(screen.queryByLabelText(/trivia item/i)).not.toBeInTheDocument();
    expect(screen.queryByText("0 items")).not.toBeInTheDocument();
  });

  it("hides zero trivia counts in the episodes table", async () => {
    const listEpisode = { ...episode, trivia_count: 0 };
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode: listEpisode, episodes: [listEpisode] })));
    renderApp("/admin/episodes");

    expect(await screen.findByRole("link", { name: /A test episode/ })).toBeInTheDocument();
    expect(screen.queryByText("0", { selector: ".count" })).not.toBeInTheDocument();
  });

  it("paginates the episodes table at 30 items per page", async () => {
    const firstPage = Array.from({ length: 30 }, (_, index) => ({ ...episode, id: `episode-${index + 1}`, episode_number: index + 1, episode_title: `Episode ${index + 1}` }));
    const secondPage = [{ ...episode, id: "episode-31", episode_number: 31, episode_title: "Episode 31" }];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) return json({ authenticated: true });
      if (url.includes("/episodes?page=2&page_size=30")) return json({ items: secondPage, page: 2, page_size: 30, total_items: 31, total_pages: 2 });
      if (url.includes("/episodes?page=1&page_size=30")) return json({ items: firstPage, page: 1, page_size: 30, total_items: 31, total_pages: 2 });
      return json({ detail: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/admin/episodes");

    expect(await screen.findByRole("link", { name: /#1 Episode 1/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Next/ })).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: /Next/ })[0]);
    expect(await screen.findByRole("link", { name: /#31 Episode 31/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("page=2"), expect.anything());
  });

  it("disables processing, publication, and deletion actions while a job is active", async () => {
    const activeJob = {
      id: "job-1", episode_id: "episode-1", kind: "transcribe" as const, status: "running" as const,
      error: null, created_at: "2026-01-01T00:00:00Z", started_at: null, finished_at: null
    };
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode: { ...episode, transcript_status: "missing", active_job: activeJob } })));
    renderApp("/admin/episodes/episode-1/overview");

    expect(await screen.findByRole("button", { name: "Transcribe" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Show on website" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete episode" })).toBeDisabled();
  });

  it("requires the exact episode title before permanent deletion", async () => {
    const fetchMock = vi.fn(requestRouter({ episode: { ...episode, transcript_status: "missing" } }));
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/admin/episodes/episode-1/overview");

    fireEvent.click(await screen.findByRole("button", { name: "Delete episode" }));
    const confirm = screen.getByRole("button", { name: "Delete permanently" });
    const input = screen.getByRole("textbox", { name: "Type the episode title to confirm" });
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: "a test episode" } });
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: "  A test episode  " } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/episodes/episode-1",
      expect.objectContaining({ method: "DELETE" })
    ));
    expect(await screen.findByRole("heading", { name: "Episodes" })).toBeInTheDocument();
  });

  it("defaults to grouped Script and preserves the JSON transcript view", async () => {
    vi.stubGlobal("fetch", vi.fn(requestRouter({
      episode,
      transcript: { segments: [
        { start: 0, end: 2, speaker: "SPEAKER_00", text: "Hello." },
        { start: 2, end: 4, speaker: "SPEAKER_00", text: "Welcome." }
      ] },
      mappings: { SPEAKER_00: { id: "speaker-1", name: "Ada" } }
    })));
    renderApp("/admin/episodes/episode-1/transcript");

    expect(await screen.findByText("Hello. Welcome.")).toBeInTheDocument();
    expect(screen.getByText("Ada")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Script" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "JSON" }));
    expect(screen.getByText(/"segments"/)).toBeInTheDocument();
  });
});

describe("trivia editing", () => {
  it("starts read-only and cancel restores the saved content", () => {
    renderWithProviders(<TriviaItemCard item={trivia} speakers={episode.speakers} />);
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Draft question?" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel editing" }));
    expect(screen.getByRole("heading", { name: "Original question?" })).toBeInTheDocument();
  });

  it("reviews and applies an AI suggestion before explicit save", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/rephrase")) return json({ question: "Suggested question?", answer: "Suggested answer." });
      if (init?.method === "PATCH") return json({ ...trivia, question: "Suggested question?", answer: "Suggested answer." });
      return json({ detail: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<TriviaItemCard item={trivia} speakers={episode.speakers} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Suggest rephrase" }));
    expect(await screen.findByText("Suggested question?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use suggestion" }));
    expect(screen.getByLabelText("Question")).toHaveValue("Suggested question?");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/trivia/trivia-1", expect.objectContaining({ method: "PATCH" })));
    const patchCall = fetchMock.mock.calls.find(call => call[1]?.method === "PATCH");
    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({ question: "Suggested question?", answer: "Suggested answer." });
  });
});

describe("trivia extraction review", () => {
  it("renders candidate trivia and applies it explicitly", async () => {
    const review: TriviaCandidateReview = {
      episode_id: "episode-1",
      current_trivia: [trivia],
      candidate: {
        id: "candidate-1",
        episode_id: "episode-1",
        job_id: "job-1",
        status: "ready",
        prompt_version: "v2",
        model: "gemini-test",
        transcript_sha256: "hash",
        usage_json: {},
        error: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        applied_at: null,
        trivia: [{ ...trivia, id: "candidate-item-1", question: "Candidate question?", answer: "Candidate answer.", keywords: ["candidate"] }]
      }
    };
    const fetchMock = vi.fn(requestRouter({ episode, candidateReview: review }));
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/admin/episodes/episode-1/trivia");

    expect(await screen.findByRole("heading", { name: "Current vs new trivia" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Original question?" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Candidate question?" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Replace with new trivia" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/episodes/episode-1/trivia-candidates/candidate-1/apply",
      expect.objectContaining({ method: "POST" })
    ));
  });
});

function requestRouter(data: { episode: Episode; episodes?: Episode[]; speakers?: Episode["speakers"]; transcript?: Record<string, unknown>; mappings?: Record<string, Episode["speakers"][number]>; candidateReview?: TriviaCandidateReview }) {
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/auth/session")) return json({ authenticated: true });
    if (url.endsWith("/episodes/episode-1/publication") && init?.method === "PATCH") return json({ ...data.episode, is_published: true });
    if (url.endsWith("/episodes/episode-1/trivia-candidates/candidate-1/apply") && init?.method === "POST") return json(data.candidateReview?.candidate);
    if (url.endsWith("/episodes/episode-1/trivia-candidates/current")) return json(data.candidateReview ?? { episode_id: "episode-1", current_trivia: [trivia], candidate: null });
    if (url.endsWith("/episodes/episode-1") && init?.method === "DELETE") return new Response(null, { status: 204 });
    if (url.endsWith("/episodes/episode-1/transcript")) return json({ episode_id: "episode-1", transcript: data.transcript ?? {} });
    if (url.endsWith("/episodes/episode-1/speaker-labels")) return json({
      episode_id: "episode-1",
      speakers: data.episode.speakers,
      mappings: { SPEAKER_00: data.episode.speakers[0] },
      labels: [{ label: "SPEAKER_00", segment_count: 1, first_seen: 0, last_seen: 1, samples: [], sample_clip_url: "" }]
    });
    if (url.endsWith("/episodes/episode-1/speaker-mapping")) return json({ episode_id: "episode-1", mappings: data.mappings ?? {} });
    if (url.endsWith("/episodes/episode-1")) return json(data.episode);
    if (url.includes("/episodes?") || url.endsWith("/episodes")) {
      return json({
        items: data.episodes ?? [data.episode],
        page: 1,
        page_size: 30,
        total_items: data.episodes?.length ?? 1,
        total_pages: 1
      });
    }
    if (url.endsWith("/speakers")) return json(data.speakers ?? []);
    if (url.endsWith("/jobs/job-1")) return json(data.episode.active_job);
    return json({ detail: "Not found" }, 404);
  };
}

function renderApp(path: string) { return renderWithProviders(<App />, path); }
function renderWithProviders(element: React.ReactNode, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{element}</MemoryRouter></QueryClientProvider>);
}
function json(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }); }

const episode: Episode = {
  id: "episode-1", episode_title: "A test episode", episode_number: 12,
  episode_description: "Description", published_at: "2026-01-01T00:00:00Z",
  source_url: "https://example.com", extra_metadata: {},
  speakers: [{ id: "speaker-1", name: "Ada" }], audio_path: "/tmp/audio.mp3",
  audio_content_type: "audio/mpeg", transcript_status: "completed", trivia_status: "completed",
  trivia_count: 1, is_published: false, active_job: null,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z"
};

const trivia: TriviaItem = {
  id: "trivia-1", episode_id: "episode-1", type: "question",
  question: "Original question?", answer: "Original answer.", keywords: ["original"],
  timestamps: {}, speaker_diarization: {}, asker: episode.speakers[0], confidence: "high",
  created_at: "2026-01-01T00:00:00Z"
};
