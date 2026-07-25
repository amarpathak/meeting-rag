# Meeting Intelligence

Answers questions about meeting transcripts with grounded citations, and
extracts action items.

## Setup

```bash
cp .env.example .env      # add ANTHROPIC_API_KEY and OPENAI_API_KEY
make up
make health
```

## Status

- [x] Phase 1 — scaffold, schema, health
- [x] Phase 2 — parsing, chunking, embedding, ingest
- [x] Phase 3 — retrieval, answering, refusal path
- [x] Phase 4 — action item extraction
- [ ] Phase 5 — UI
- [x] Phase 6 — evals and tests
- [ ] Phase 7 — writeup
- [x] Bonus — audio → transcript (Gemini multimodal), chains into ingest

## Notes

TODO: rewrite this file properly at the end. Sections required by the brief:
setup, architecture, productionizing, RAG decisions, key technical decisions,
engineering standards followed and skipped, AI tooling approach, what I'd do
differently.
