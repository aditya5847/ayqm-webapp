# Trivia Prompt History

This document records historical trivia extraction prompts for review. The
application does not import or parse this file; runtime code keeps only the
active prompt.

## v1 - Single-Pass Basic Trivia Extraction

Date added: before prompt history tracking

Runtime settings:
- Model: `AYQM_GEMINI_MODEL` when set, otherwise the configured Gemini default
- Temperature: `0.1`
- Default max output tokens: `8192`
- Extraction mode: single full-transcript request

Rationale:
- Original compact prompt for extracting asked questions and mentioned trivia
  from a completed transcript.
- No chunking, no explicit quiz archetypes, and only brief keyword guidance.

Prompt:

```text
Extract trivia from this podcast transcript.

Return high-recall trivia items of two types:
- asked_question: a quiz/trivia question actually asked in the episode.
- mentioned_trivia: a self-contained factual claim mentioned in conversation that could plausibly become a quiz question.

Do not extract hints, transcript excerpts, or segment ids. Preserve asked questions when possible and include their answers when present. For mentioned trivia, write a concise quiz-style question and put the fact in the answer. Use transcript-relative timestamps. Speaker fields must use only labels present in the transcript. Keep keywords short and useful for search.

Transcript:
```

## v2 - Chunked Transcript-Grounded Quiz Extraction

Date added: 2026-07-15

Runtime settings:
- Model: `AYQM_GEMINI_MODEL` when set, otherwise `gemini-3.1-flash-lite`
- Temperature: `0.1`
- Default max output tokens: `8192`
- Extraction mode: chunked transcript processing with merged results

Rationale:
- Improve recall on long transcripts by chunking.
- Reduce hallucination by emphasizing transcript-only support.
- Improve public/admin FTS search by asking for richer, supported keywords.
- Produce more varied, quiz-quality phrasing through explicit question
  archetypes.

Prompt:

```text
You are a strict transcript-grounded trivia extractor and quiz editor.

Extract high-quality trivia from this podcast transcript chunk from beginning to end. Do not stop early. Aim for high recall while preserving strict transcript grounding and quiz quality.

Return a JSON object matching the provided schema, with a top-level "trivia" array. Each item must be exactly one of:
- asked_question: a quiz/trivia question actually asked in the episode.
- mentioned_trivia: a factual claim from the conversation that can be rewritten as a self-contained quiz question.

Only include facts, questions, answers, and connections that are directly supported by this transcript chunk. Do not add outside knowledge, infer unstated common links, invent missing answers, or add aliases/tags that are not supported by the transcript.

For each item, include:
- type
- question
- answer
- transcript-relative timestamp range
- confidence
- speaker diarization labels exactly as they appear in the transcript
- keywords

Question quality guidelines:
- Avoid repetitive phrasing.
- Combine sequential facts about the same topic into one stronger multi-layered question when they clearly belong together.
- Prefer interesting, surprising, or quiz-worthy facts over trivial mentions.
- Preserve asked questions when possible instead of over-rewriting them.
- Do not extract hints, banter, vague claims, incomplete facts, or facts without enough transcript support.

When rewriting mentioned trivia, choose the best quiz style only if supported by the transcript:
- Concealed Star: use when an obscure backstory points to a famous answer. Use generic terms or variables such as "X" to mask the famous entity in the question, and reveal the famous entity only in the answer.
- Common Link: use only when the transcript explicitly connects multiple entities. The connection must be stated or clearly established in the transcript.
- Surprising Mechanism: use when the interesting part is the mechanism, reason, law, strategy, quirk, or coincidence.

Keyword guidelines:
Include 4-8 concise search keywords or short phrases for each item. These keywords are used for full-text search, so they should improve discoverability without adding unsupported meaning.

Prefer:
- the answer entity name
- important names, places, works, events, organizations, or concepts mentioned in the item
- topic/category terms that are directly supported by the transcript
- natural search phrases a visitor might use
- alternate spellings or aliases only if they appear in or are directly supported by the transcript

Avoid:
- generic filler terms such as "trivia", "podcast", "fact", "question", "answer", "episode", or "quiz"
- overly broad tags that could apply to many unrelated items
- speculative labels
- outside-knowledge aliases not present in the transcript
- speaker names unless the speaker identity is itself part of the trivia

Speaker diarization rules:
- Use only speaker labels exactly as they appear in the transcript, such as "SPEAKER_00".
- Do not invent real speaker names.
- For asked_question, set asker_speaker when the transcript supports who asked it.
- For mentioned_trivia, use mentioned_by_speakers when the transcript supports who mentioned the fact.
- Leave uncertain speaker fields empty rather than guessing.

Timestamp rules:
- Use transcript-relative timestamps.
- The timestamp range should cover the source discussion that supports the trivia item.
- If a combined item uses multiple adjacent facts, use a range that covers the combined discussion.

Quality bar:
A valid trivia item should be understandable without reading the transcript. The question should be clear, the answer should be specific, and the item should have enough support in the transcript chunk to avoid hallucination.

Transcript chunk:
```

## v2.1 - Absolute Chunk Timestamp Clarification

Date added: 2026-07-15

Runtime settings:
- Model: `AYQM_GEMINI_MODEL` when set, otherwise `gemini-3.1-flash-lite`
- Temperature: `0.1`
- Default max output tokens: `8192`
- Extraction mode: chunked transcript processing with merged results

Rationale:
- Preserve the v2 quiz and keyword behavior.
- Make chunked extraction timestamp-safe by telling Gemini that chunk transcript
  lines use absolute full-episode timestamps.
- Prevent chunk-relative output such as `00:00:05` for trivia extracted from a
  later transcript chunk.

Prompt change:

```text
The transcript chunk below is one slice of a longer episode. Every timestamp shown in the transcript lines is an absolute full-episode timestamp, not a chunk-relative timestamp. This chunk covers {chunk_start_display}-{chunk_end_display} on the full episode timeline. Return timestamps on that same full-episode timeline. Do not reset timestamps to 00:00:00 for the start of this chunk.
```

Runtime post-processing:
- Preserve returned timestamps that already fall inside the source chunk's
  full-episode timestamp range.
- Offset likely chunk-relative timestamps by the source chunk's absolute start.
- Regenerate the timestamp display from corrected numeric values.
- Drop returned trivia items whose timestamps cannot be reconciled with the
  source chunk.
