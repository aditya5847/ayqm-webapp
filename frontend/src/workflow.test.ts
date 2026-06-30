import { describe, expect, it } from "vitest";
import { buildEpisodeFormData } from "./api";
import { isSpeakerMappingComplete, shouldPollJob, triviaAskerName } from "./workflow";
import type { Job, SpeakerLabels, TriviaItem } from "./types";

describe("frontend workflow helpers", () => {
  it("serializes episode uploads with backend field names and JSON speaker IDs", () => {
    const file = new File(["audio"], "episode.mp3", { type: "audio/mpeg" });
    const form = buildEpisodeFormData({
      file,
      episode_title: "Episode Title",
      episode_number: 7,
      speaker_ids: ["speaker-1", "speaker-2"],
      extra_metadata: { source: "test" }
    });

    expect(form.get("file")).toBe(file);
    expect(form.get("episode_title")).toBe("Episode Title");
    expect(form.get("episode_number")).toBe("7");
    expect(form.get("speaker_ids")).toBe(JSON.stringify(["speaker-1", "speaker-2"]));
    expect(form.get("extra_metadata")).toBe(JSON.stringify({ source: "test" }));
    expect(form.has("title")).toBe(false);
    expect(form.has("show_title")).toBe(false);
  });

  it("keeps trivia extraction blocked until every label has a selected speaker", () => {
    const labels: SpeakerLabels = {
      episode_id: "episode-1",
      speakers: [{ id: "speaker-1", name: "Ada" }],
      mappings: {},
      labels: [
        { label: "SPEAKER_00", segment_count: 2, first_seen: 0, last_seen: 12, samples: [], sample_clip_url: "/sample-0" },
        { label: "SPEAKER_01", segment_count: 1, first_seen: 14, last_seen: 20, samples: [], sample_clip_url: "/sample-1" }
      ]
    };

    expect(isSpeakerMappingComplete(labels, { SPEAKER_00: "speaker-1" })).toBe(false);
    expect(isSpeakerMappingComplete(labels, { SPEAKER_00: "speaker-1", SPEAKER_01: "speaker-1" })).toBe(true);
  });

  it("polls only active jobs", () => {
    const queued: Job = job("queued");
    const running: Job = job("running");
    const succeeded: Job = job("succeeded");
    const failed: Job = job("failed");

    expect(shouldPollJob(queued)).toBe(true);
    expect(shouldPollJob(running)).toBe(true);
    expect(shouldPollJob(succeeded)).toBe(false);
    expect(shouldPollJob(failed)).toBe(false);
  });

  it("uses top-level asker for trivia speaker identity", () => {
    const item: TriviaItem = {
      id: "trivia-1",
      episode_id: "episode-1",
      type: "question",
      question: "Who asked?",
      answer: "Ada",
      keywords: [],
      timestamps: {},
      speaker_diarization: { asker_speaker: "SPEAKER_00" },
      asker: { id: "speaker-1", name: "Ada" },
      confidence: "high",
      created_at: "2026-01-01T00:00:00Z"
    };

    expect(triviaAskerName(item)).toBe("Ada");
  });
});

function job(status: Job["status"]): Job {
  return {
    id: "job-1",
    episode_id: "episode-1",
    kind: "transcribe",
    status,
    error: null,
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null
  };
}
