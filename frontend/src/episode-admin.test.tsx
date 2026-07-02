import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { TriviaItemCard } from "./episode-admin";
import type { Episode, TriviaItem } from "./types";

afterEach(() => vi.restoreAllMocks());

describe("episode workspace routing", () => {
  it("redirects the bare episode route to a read-only Overview with back navigation", async () => {
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode: { ...episode, transcript_status: "missing" } })));
    renderApp("/admin/episodes/episode-1");

    expect(await screen.findByRole("link", { name: /Back to episodes/ })).toHaveAttribute("href", "/admin/episodes");
    expect(await screen.findByRole("heading", { name: "Episode overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toHaveClass("active");
    expect(screen.queryByRole("button", { name: "Save details" })).not.toBeInTheDocument();
  });

  it("keeps metadata editing in the Details tab", async () => {
    vi.stubGlobal("fetch", vi.fn(requestRouter({ episode, speakers: episode.speakers })));
    renderApp("/admin/episodes/episode-1/details");

    expect(await screen.findByRole("heading", { name: "Edit episode details" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Details" })).toHaveClass("active");
    expect(screen.getByRole("textbox", { name: /Episode title/ })).toHaveValue("A test episode");
    expect(screen.getByRole("button", { name: "Save details" })).toBeInTheDocument();
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

function requestRouter(data: { episode: Episode; speakers?: Episode["speakers"]; transcript?: Record<string, unknown>; mappings?: Record<string, Episode["speakers"][number]> }) {
  return async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/auth/session")) return json({ authenticated: true });
    if (url.endsWith("/episodes/episode-1/transcript")) return json({ episode_id: "episode-1", transcript: data.transcript ?? {} });
    if (url.endsWith("/episodes/episode-1/speaker-mapping")) return json({ episode_id: "episode-1", mappings: data.mappings ?? {} });
    if (url.endsWith("/episodes/episode-1")) return json(data.episode);
    if (url.endsWith("/speakers")) return json(data.speakers ?? []);
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
  trivia_count: 1, is_published: false, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z"
};

const trivia: TriviaItem = {
  id: "trivia-1", episode_id: "episode-1", type: "question",
  question: "Original question?", answer: "Original answer.", keywords: ["original"],
  timestamps: {}, speaker_diarization: {}, asker: episode.speakers[0], confidence: "high",
  created_at: "2026-01-01T00:00:00Z"
};
