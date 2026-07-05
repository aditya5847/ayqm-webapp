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

  it("renders the static about page and guest host roll without an API", () => {
    renderApp("/about");
    expect(screen.getByRole("heading", { name: "Meet the hosts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Vineeth Nair" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Aditya Kashyap" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Vineeth Nair" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Aditya Kashyap" })).toBeInTheDocument();
    expect(screen.getByText("Garry Leavy")).toBeInTheDocument();
    expect(screen.getByText("Berty Ashley")).toBeInTheDocument();
  });

  it("does not expose admin navigation on the public site", () => {
    renderApp("/about");
    expect(screen.queryByRole("link", { name: /admin/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Podcast admin")).not.toBeInTheDocument();
  });

  it("layers latest episode artwork over the podcast artwork and removes a failed overlay", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => jsonResponse(String(input).includes("/public/trivia") ? [] : [publicEpisode("episode-1", "Latest show")])));
    renderApp("/");

    expect(screen.getByRole("img", { name: "Are You Quizzing Me podcast artwork" })).toBeInTheDocument();
    const episodeArtwork = await screen.findByRole("img", { name: "Latest show artwork" });
    expect(screen.getByText("Latest episode")).toBeInTheDocument();
    fireEvent.error(episodeArtwork);
    expect(screen.queryByRole("img", { name: "Latest show artwork" })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Are You Quizzing Me podcast artwork" })).toBeInTheDocument();
  });

  it("renders safe episode description HTML without executable markup", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.endsWith("/trivia") ? [] : {
        id: "episode-1", episode_title: "Safe episode", episode_number: 1,
        episode_description: '<p>A <strong>formatted</strong> description.</p><script>alert(1)</script><a href="javascript:alert(1)">Unsafe</a>',
        published_at: "2026-01-01T00:00:00Z", source_url: null,
        artwork_url: "/public/episodes/episode-1/artwork", speakers: [], trivia_count: 0
      };
      return jsonResponse(payload);
    }));
    const view = renderApp("/episodes/episode-1");
    expect(await screen.findByText("formatted")).toHaveProperty("tagName", "STRONG");
    expect(view.container.querySelector("script")).not.toBeInTheDocument();
    expect(view.container.querySelector('a[href^="javascript:"]')).not.toBeInTheDocument();
    const artwork = screen.getByRole("img", { name: "Safe episode artwork" });
    expect(artwork).toHaveAttribute("src", "/api/public/episodes/episode-1/artwork");
    fireEvent.error(artwork);
    expect(artwork.getAttribute("src")).toContain("Podcast%20Thumbnail.jpg");
  });

  it("hides the contact footer from rendered episode descriptions", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.endsWith("/trivia") ? [] : {
        id: "episode-1", episode_title: "Footer episode", episode_number: 1,
        episode_description: "<p>Main episode copy.</p><p>You can reach us at <a href=\"mailto:hello@example.com\">hello@example.com</a></p><p><a href=\"https://www.instagram.com/areyouquizzingme/\">Instagram</a></p>",
        published_at: "2026-01-01T00:00:00Z", source_url: null,
        artwork_url: "/public/episodes/episode-1/artwork", speakers: [], trivia_count: 0
      };
      return jsonResponse(payload);
    }));
    renderApp("/episodes/episode-1");
    expect(await screen.findByText("Main episode copy.")).toBeInTheDocument();
    expect(screen.queryByText(/You can reach us at/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Instagram")).not.toBeInTheDocument();
    expect(screen.queryByText("hello@example.com")).not.toBeInTheDocument();
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

function publicEpisode(id: string, title: string) {
  return {
    id, episode_title: title, episode_number: 1, episode_kind: "main",
    episode_description: "Description", published_at: "2026-01-01T00:00:00Z",
    source_url: null, artwork_url: `/public/episodes/${id}/artwork`, speakers: [], trivia_count: 0
  };
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
}
