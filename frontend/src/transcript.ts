import type { Speaker } from "./types";

export interface TranscriptScriptBlock {
  speakerLabel: string | null;
  speakerName: string;
  start: number | null;
  end: number | null;
  text: string;
}

interface TranscriptUnit {
  speaker: string | null;
  start: number | null;
  end: number | null;
  text: string;
}

export function transcriptScriptBlocks(
  transcript: Record<string, unknown>,
  mappings: Record<string, Speaker> = {}
): TranscriptScriptBlock[] {
  const segments = Array.isArray(transcript.segments) ? transcript.segments : [];
  const units = segments.flatMap(segmentUnits);

  return units.reduce<TranscriptScriptBlock[]>((blocks, unit) => {
    const previous = blocks.at(-1);
    if (previous && previous.speakerLabel === unit.speaker) {
      previous.text = joinText(previous.text, unit.text);
      if (unit.end !== null) previous.end = unit.end;
      return blocks;
    }
    blocks.push({
      speakerLabel: unit.speaker,
      speakerName: unit.speaker ? mappings[unit.speaker]?.name ?? unit.speaker : "Unknown speaker",
      start: unit.start,
      end: unit.end,
      text: unit.text
    });
    return blocks;
  }, []);
}

function segmentUnits(value: unknown): TranscriptUnit[] {
  if (!isRecord(value)) return [];
  const segmentSpeaker = stringValue(value.speaker);
  const words = Array.isArray(value.words) ? value.words : [];
  const wordUnits = words.flatMap((word): TranscriptUnit[] => {
    if (!isRecord(word)) return [];
    const text = stringValue(word.word) ?? stringValue(word.text);
    if (!text?.trim()) return [];
    return [{
      speaker: stringValue(word.speaker) ?? segmentSpeaker,
      start: numberValue(word.start),
      end: numberValue(word.end),
      text: text.trim()
    }];
  });
  if (wordUnits.length > 0) return wordUnits;

  const text = stringValue(value.text);
  if (!text?.trim()) return [];
  return [{
    speaker: segmentSpeaker,
    start: numberValue(value.start),
    end: numberValue(value.end),
    text: text.trim()
  }];
}

function joinText(left: string, right: string): string {
  return `${left} ${right}`.replace(/\s+([,.;:!?])/g, "$1").trim();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
