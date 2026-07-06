import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { PublicTriviaCard } from "./public";
import { UploadPage } from "./admin";
import type { TriviaItem } from "./types";

afterEach(() => vi.restoreAllMocks());

describe("public experience", () => {
  it("reveals a trivia answer on request", () => {
    const { container } = render(<PublicTriviaCard item={triviaItem} />);
    expect(container.querySelector(".flashcard-back")).toHaveAttribute("aria-hidden", "true");
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    expect(screen.getByText("Mercury")).toBeInTheDocument();
    expect(container.querySelector(".flashcard-front")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector(".flashcard-back")).toHaveAttribute("aria-hidden", "false");
    expect(screen.getByRole("button", { name: "Show question" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Show question" }));
    expect(screen.getByRole("button", { name: "Reveal answer" })).toHaveFocus();
  });

  it("only attributes trivia to a mapped speaker", () => {
    const { rerender } = render(<PublicTriviaCard item={{ ...triviaItem, asker: null }} />);
    expect(screen.queryByText(/Asked by/)).not.toBeInTheDocument();
    rerender(<PublicTriviaCard item={triviaItem} />);
    expect(screen.getByText("Asked by Ada")).toBeInTheDocument();
  });

  it("shows a view-specific coming soon state for deferred public endpoints", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not found" }), { status: 404, headers: { "content-type": "application/json" } })));
    renderApp("/episodes");
    expect(await screen.findByRole("heading", { name: "The episode archive" })).toBeInTheDocument();
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
  });

  it("reports an API configuration error when the SPA fallback returns HTML", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>frontend</html>", {
      status: 200,
      headers: { "content-type": "text/html" }
    })));
    renderApp("/episodes");
    expect(await screen.findByText(/Set VITE_API_BASE_URL/)).toBeInTheDocument();
  });

  it("renders the about page and guest host episode links", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/public/speakers")) {
        return jsonResponse([
          { id: "speaker-1", name: "Garry Leavy" },
          { id: "speaker-2", name: "Berty Ashley" },
          { id: "speaker-3", name: "Vineeth Nair" }
        ]);
      }
      if (url.endsWith("/public/episodes")) {
        return jsonResponse([
          publicEpisode("episode-12", "A crossword of facts", 12, ["Garry Leavy"]),
          publicEpisode("episode-24", "A very loud clue", 24, ["Berty Ashley"])
        ]);
      }
      return jsonResponse({ detail: "Not found" }, 404);
    }));
    renderApp("/about");
    expect(screen.getByRole("heading", { name: "Meet the hosts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Vineeth Nair" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Aditya Kashyap" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Vineeth Nair" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Aditya Kashyap" })).toBeInTheDocument();
    expect(await screen.findByText("Garry Leavy")).toBeInTheDocument();
    expect(await screen.findByText("Berty Ashley")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "#12" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "#24" })).toBeInTheDocument();
    expect(screen.queryByText("Episode 12")).not.toBeInTheDocument();
  });

  it("does not expose admin navigation on the public site", () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/public/speakers")) return jsonResponse([]);
      if (url.endsWith("/public/episodes")) return jsonResponse([]);
      return jsonResponse({ detail: "Not found" }, 404);
    }));
    renderApp("/about");
    expect(screen.queryByRole("link", { name: /admin/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Podcast admin")).not.toBeInTheDocument();
  });

  it("renders safe episode description HTML without executable markup", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.endsWith("/trivia") ? [] : {
        id: "episode-1", episode_title: "Safe episode", episode_number: 1,
        episode_description: '<p>A <strong>formatted</strong> description.</p><script>alert(1)</script><a href="javascript:alert(1)">Unsafe</a>',
        published_at: "2026-01-01T00:00:00Z", source_url: null, speakers: [], trivia_count: 0
      };
      return jsonResponse(payload);
    }));
    const view = renderApp("/episodes/episode-1");
    expect(await screen.findByText("formatted")).toHaveProperty("tagName", "STRONG");
    expect(view.container.querySelector("script")).not.toBeInTheDocument();
    expect(view.container.querySelector('a[href^="javascript:"]')).not.toBeInTheDocument();
  });

  it("paginates the episode archive through the URL-backed API", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const page = url.includes("page=2") ? 2 : 1;
      return jsonResponse({
        items: [publicEpisode(page === 1 ? "episode-1" : "episode-11", page === 1 ? "First page" : "Second page")],
        page, page_size: 10, total_items: 11, total_pages: 2
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/episodes");
    expect(await screen.findByText("First page")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    expect(await screen.findByText("Second page")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("page=2"), expect.anything());
  });

  it("refreshes four trivia cards while excluding the current set", async () => {
    const first = [1, 2, 3, 4].map(index => trivia(`old-${index}`, `Old question ${index}?`));
    const second = [5, 6, 7, 8].map(index => trivia(`new-${index}`, `New question ${index}?`));
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => jsonResponse(String(input).includes("exclude_id") ? second : first));
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/trivia");
    expect(await screen.findAllByRole("heading", { name: /Old question/ })).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: "Deal four new cards" }));
    expect(await screen.findAllByRole("heading", { name: /New question/ })).toHaveLength(4);
    const refreshUrl = String(fetchMock.mock.calls.at(-1)?.[0]);
    expect(refreshUrl).toContain("exclude_id=old-1");
    expect(refreshUrl).toContain("exclude_id=old-4");
  });
});

describe("admin experience", () => {
  it("marks every mandatory upload field", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: "speaker-1", name: "Ada" }]), { status: 200, headers: { "content-type": "application/json" } })));
    renderWithProviders(<UploadPage />);
    await waitFor(() => expect(screen.getByText("Ada")).toBeInTheDocument());
    expect(screen.getByText("Audio file").parentElement).toHaveTextContent("*");
    expect(screen.getByText("Episode title").parentElement).toHaveTextContent("*");
    expect(screen.getByText("Episode number").parentElement).toHaveTextContent("*");
    expect(screen.getByText("Episode speakers").parentElement).toHaveTextContent("*");
  });

  it("renders the login route independently of the deferred session endpoint", () => {
    renderApp("/admin/login");
    expect(screen.getByRole("heading", { name: "Admin sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/)).toBeRequired();
  });
});

function renderApp(path: string) {
  return renderWithProviders(<App />, path);
}

function renderWithProviders(element: React.ReactNode, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{element}</MemoryRouter></QueryClientProvider>);
}

const triviaItem: TriviaItem = {
  id: "trivia-1",
  episode_id: "episode-1",
  type: "question",
  question: "Which planet is closest to the sun?",
  answer: "Mercury",
  keywords: ["space"],
  timestamps: {},
  speaker_diarization: {},
  asker: { id: "speaker-1", name: "Ada" },
  confidence: "high",
  created_at: "2026-01-01T00:00:00Z"
};

function trivia(id: string, question: string): TriviaItem {
  return { ...triviaItem, id, question };
}

function publicEpisode(id: string, title: string, episodeNumber = 1, speakers: string[] = []) {
  return {
    id, episode_title: title, episode_number: episodeNumber, episode_kind: "main",
    episode_description: "Description", published_at: "2026-01-01T00:00:00Z",
    source_url: null, speakers: speakers.map(name => ({ id: name.toLowerCase().replace(/\s+/g, "-"), name })), trivia_count: 0
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}
