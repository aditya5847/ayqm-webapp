import { describe, expect, it } from "vitest";
import { transcriptScriptBlocks } from "./transcript";

describe("transcriptScriptBlocks", () => {
  it("groups consecutive segments and resolves mapped speaker names", () => {
    const blocks = transcriptScriptBlocks({ segments: [
      { start: 0, end: 2, speaker: "SPEAKER_00", text: "Hello" },
      { start: 2, end: 4, speaker: "SPEAKER_00", text: "there." },
      { start: 4, end: 6, speaker: "SPEAKER_01", text: "Hi." }
    ] }, {
      SPEAKER_00: { id: "one", name: "Ada" },
      SPEAKER_01: { id: "two", name: "Grace" }
    });

    expect(blocks).toEqual([
      { speakerLabel: "SPEAKER_00", speakerName: "Ada", start: 0, end: 4, text: "Hello there." },
      { speakerLabel: "SPEAKER_01", speakerName: "Grace", start: 4, end: 6, text: "Hi." }
    ]);
  });

  it("uses word-level speaker changes when available", () => {
    const blocks = transcriptScriptBlocks({ segments: [{
      speaker: "SPEAKER_00",
      text: "ignored segment text",
      words: [
        { start: 0, end: 1, speaker: "SPEAKER_00", word: "Question?" },
        { start: 1, end: 2, speaker: "SPEAKER_01", word: "Answer." }
      ]
    }] });

    expect(blocks.map(block => [block.speakerName, block.text])).toEqual([
      ["SPEAKER_00", "Question?"],
      ["SPEAKER_01", "Answer."]
    ]);
  });

  it("handles unknown speakers, missing timestamps, and malformed data", () => {
    expect(transcriptScriptBlocks({ segments: [{ text: "Unattributed" }] })).toEqual([
      { speakerLabel: null, speakerName: "Unknown speaker", start: null, end: null, text: "Unattributed" }
    ]);
    expect(transcriptScriptBlocks({ segments: "invalid" })).toEqual([]);
  });
});
