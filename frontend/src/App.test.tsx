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
    render(<PublicTriviaCard item={triviaItem} number={1} />);
    expect(screen.queryByText("Mercury")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    expect(screen.getByText("Mercury")).toBeInTheDocument();
  });

  it("shows a view-specific coming soon state for deferred public endpoints", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not found" }), { status: 404, headers: { "content-type": "application/json" } })));
    renderApp("/episodes");
    expect(await screen.findByRole("heading", { name: "The episode archive" })).toBeInTheDocument();
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
  });

  it("renders the static about page and guest host roll without an API", () => {
    renderApp("/about");
    expect(screen.getByRole("heading", { name: "Meet the hosts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Vineeth Nair" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Aditya Kashyap" })).toBeInTheDocument();
    expect(screen.getByText("Garry Leavy")).toBeInTheDocument();
    expect(screen.getByText("Berty Ashley")).toBeInTheDocument();
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
