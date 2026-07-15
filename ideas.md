# Ideas

Potential future improvements and wishlist items for AYQM.

- Progress bar for upload, transcription, and trivia extraction on the frontend.
- On the admin side, allow for hosts/guests bios and pictures to be updated. Display bio/picture for guests as well.
- Consider separate storage and display treatments for `asked_questions` and `mentioned_trivia`.
- Add support for clip-derived trivia with its own source metadata and optional clip-specific speaker mapping, separate from episode transcript mapping.
- Verify every trivia item against reliable sources and retain its supporting references.
- Add a visitor-facing Donate tab for direct financial support.
- Add a visitor-facing Shop tab for podcast merchandise.
- Create a visitor-facing page for past Sunday Quizzes, including every episode's Visual Connects and SMAQ content.
- Search feature on Trivia
- Build an audio player on the website itself
- Speed up home page latest-episode artwork by adding cached small artwork thumbnails and a lightweight public home endpoint.
- Let visitors submit trivia for future episodes with a question, answer, optional explanation, optional message, and a tag for Vineeth or Aditya; surface submissions in admin so a host can be selected and shown only their relevant trivia.


  Deferred Plan

  - Implement chunked Gemini trivia extraction using the latest in-code prompt/model/settings.
  - Store prompt history separately in docs/trivia-prompt-history.md.
  - Add admin-side re-extraction per episode.
  - New extraction creates a DB-stored candidate, not live trivia.
  - Admin Trivia tab shows old trivia vs new candidate trivia.
  - User can apply candidate to atomically replace live trivia, or discard it.
  - Preview generation does not affect publication; applying replacement marks the episode draft/unpublished.
  - No batch runner needed for the 144 episodes.

  Best Prompt Draft

  You are a strict transcript-grounded trivia extractor and quiz editor.

  Extract high-quality trivia from this podcast transcript chunk from beginning to end. Do not stop early. Aim for high recall while preserving strict transcript grounding and quiz
  quality.

  Return a JSON object matching the provided schema, with a top-level "trivia" array. Each item must be exactly one of:
  - asked_question: a quiz/trivia question actually asked in the episode.
  - mentioned_trivia: a factual claim from the conversation that can be rewritten as a self-contained quiz question.

  Only include facts, questions, answers, and connections that are directly supported by this transcript chunk. Do not add outside knowledge, infer unstated common links, or invent
  missing answers.

  For each item, include the answer, transcript-relative timestamp range, short search keywords, confidence, and speaker diarization labels exactly as they appear in the transcript.

  Question quality guidelines:
  - Avoid repetitive phrasing.
  - Combine sequential facts about the same topic into one stronger multi-layered question when they clearly belong together.
  - Prefer interesting, surprising, or quiz-worthy facts over trivial mentions.
  - Preserve asked questions when possible instead of over-rewriting them.

  When rewriting mentioned trivia, choose the best quiz style only if supported by the transcript:
  - Concealed Star: use when an obscure backstory points to a famous answer. Use generic terms or variables such as "X" to mask the famous entity in the question, and reveal the
  famous entity only in the answer.
  - Common Link: use only when the transcript explicitly connects multiple entities.
  - Surprising Mechanism: use when the interesting part is the mechanism, reason, law, strategy, quirk, or coincidence.

  Do not extract hints, banter, vague claims, incomplete facts, or facts without enough transcript support.
