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

## Trivia Search Next Steps

- Step 1 is complete: trivia search now uses DuckDB FTS/BM25 over question, answer, and keywords.
- Re-extract a representative set of episodes with the new keyword-rich Gemini prompt and review public/admin search quality.
- Track common zero-result or weak-result searches before adding more search infrastructure.
- Improve generated or manual keywords first when search misses are caused by sparse metadata.
- Consider vector embeddings only if FTS plus better keywords still misses conceptual searches.
- If vectors are added, use hybrid search: FTS for exact terms and names, vectors for conceptual similarity, and cached query embeddings to avoid repeated model calls.
