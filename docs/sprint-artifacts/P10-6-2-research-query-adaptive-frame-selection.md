# Story P10-6.2: Research Query-Adaptive Frame Selection

Status: done

## Story

As a **developer planning AI enhancements for ArgusAI**,
I want **comprehensive research on query-adaptive frame selection techniques**,
So that **future re-analysis can select the most relevant frames based on user queries, improving AI accuracy for targeted questions**.

## Acceptance Criteria

1. **AC-6.2.1:** Given I read the research document, when I understand query-adaptive selection, then I know how to score frames by query relevance using VL model embeddings

2. **AC-6.2.2:** Given the research evaluates VL model embeddings, when I compare CLIP vs SigLIP vs alternatives, then recommendations are documented with rationale

3. **AC-6.2.3:** Given the research defines embedding storage, when I review storage requirements, then I understand schema, size estimates, and indexing needs

4. **AC-6.2.4:** Given the research considers compute requirements, when I review embedding generation costs, then I know runtime and resource implications

5. **AC-6.2.5:** Given future development begins, when implementation starts, then this research document guides technical approach and design decisions

## Tasks / Subtasks

- [x] Task 1: Research VL Model Embeddings (AC: 1, 2)
  - [x] Subtask 1.1: Review CLIP architecture and embedding generation
  - [x] Subtask 1.2: Evaluate SigLIP as an alternative to CLIP
  - [x] Subtask 1.3: Compare other VL models (BLIP-2, OpenCLIP, etc.)
  - [x] Subtask 1.4: Document embedding dimensions and quality trade-offs
  - [x] Subtask 1.5: Recommend model for ArgusAI with rationale

- [x] Task 2: Design Query-to-Frame Matching Algorithm (AC: 1)
  - [x] Subtask 2.1: Document text query encoding process
  - [x] Subtask 2.2: Define cosine similarity scoring approach
  - [x] Subtask 2.3: Design top-K frame selection algorithm
  - [x] Subtask 2.4: Consider query ambiguity handling strategies
  - [x] Subtask 2.5: Document integration with existing re-analysis flow

- [x] Task 3: Define Embedding Storage Schema (AC: 3)
  - [x] Subtask 3.1: Design frame embedding database schema
  - [x] Subtask 3.2: Estimate storage size per event and at scale
  - [x] Subtask 3.3: Evaluate vector indexing options (faiss, pgvector, etc.)
  - [x] Subtask 3.4: Define embedding lifecycle (generation, TTL, pruning)
  - [x] Subtask 3.5: Document when to generate embeddings (event-time vs on-demand)

- [x] Task 4: Assess Compute and Performance (AC: 4)
  - [x] Subtask 4.1: Estimate embedding generation latency per frame
  - [x] Subtask 4.2: Evaluate CPU vs GPU requirements
  - [x] Subtask 4.3: Document memory footprint for model loading
  - [x] Subtask 4.4: Assess query-adaptive selection overhead (<200ms target)
  - [x] Subtask 4.5: Consider batch processing optimizations

- [x] Task 5: Document Implementation Roadmap (AC: 5)
  - [x] Subtask 5.1: Outline phased implementation approach
  - [x] Subtask 5.2: Identify dependencies on existing services
  - [x] Subtask 5.3: Define MVP vs full implementation scope
  - [x] Subtask 5.4: List open questions for future resolution

- [x] Task 6: Compile Research Document
  - [x] Subtask 6.1: Create docs/research/query-adaptive-frames-research.md
  - [x] Subtask 6.2: Include architecture diagrams (Mermaid)
  - [x] Subtask 6.3: Add code examples where applicable
  - [x] Subtask 6.4: Review against all acceptance criteria

## Dev Notes

### Architecture Context

This story is **research-only** - no implementation is required. The deliverable is a comprehensive research document that will guide future query-adaptive frame selection implementation.

**Current Frame Processing Components:**
- `backend/app/services/frame_extraction_service.py` - Extracts key frames from video clips
- `backend/app/services/embedding_service.py` - CLIP ViT-B/32 embeddings for similarity search
- `backend/app/services/similarity_service.py` - Cosine similarity for event matching
- `backend/app/services/ai_service.py` - Multi-provider AI with frame analysis
- `backend/app/models/event.py` - Event model with frame references

**Key Constraints:**
- Query-adaptive selection must add <200ms to re-analysis workflow
- Should leverage existing CLIP infrastructure where possible
- Must consider storage implications for per-frame embeddings
- Fail gracefully if embeddings unavailable - fall back to uniform sampling

### Query-Adaptive Frame Selection Background

When users re-analyze events with specific queries (e.g., "Was there a package delivery?"), the current uniform frame sampling may miss the most relevant frames. Query-adaptive selection:
1. Encodes the user query as a text embedding
2. Compares query embedding to all frame embeddings
3. Selects top-K most relevant frames for AI analysis
4. Improves accuracy for targeted questions

### Research Areas

1. **VL Model Comparison**: CLIP vs SigLIP vs BLIP-2 vs OpenCLIP
2. **Embedding Dimensions**: 512 (CLIP) vs 768 (SigLIP) vs 1024 (larger models)
3. **Storage Strategy**: Per-frame embeddings vs lazy generation
4. **Query Handling**: Single query vs multi-aspect queries
5. **Fallback Strategy**: When embeddings are unavailable

### Learnings from Previous Story

**From Story P10-6.1 (MCP Server Research):**

- **Document Structure**: Used comprehensive sections with Mermaid diagrams - apply same pattern
- **Trade-off Tables**: Comparison tables effectively communicated options - use for VL model comparison
- **Performance Analysis**: Latency budget table worked well - create similar for frame selection
- **Python Examples**: Code examples helped illustrate integration points - include for embedding service
- **Implementation Roadmap**: 3-phase approach was clear - apply similar structure

[Source: docs/sprint-artifacts/P10-6-1-research-local-mcp-server.md#Dev-Agent-Record]

### References

- [Source: docs/PRD-phase10.md#AI-Enhancements]
- [Source: docs/epics-phase10.md#Story-P10-6.2]
- [Source: docs/sprint-artifacts/tech-spec-epic-P10-6.md#Story-P10-6.2]
- [OpenAI CLIP Paper](https://arxiv.org/abs/2103.00020)
- [SigLIP Paper](https://arxiv.org/abs/2303.15343)
- Backlog: FF-022

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/P10-6-2-research-query-adaptive-frame-selection.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A - Research story, no implementation

### Completion Notes List

- Completed comprehensive VL model comparison (CLIP, SigLIP, OpenCLIP, BLIP-2) with recommendation to use existing CLIP ViT-B/32
- Designed query-to-frame matching algorithm with text encoding, cosine similarity, and top-K selection
- Defined FrameEmbedding database schema with storage estimates (~42MB per 1000 events)
- Analyzed compute requirements confirming <60ms selection overhead (within 200ms budget)
- Created 3-phase implementation roadmap with Python code examples
- All acceptance criteria satisfied through research document

### File List

- docs/research/query-adaptive-frames-research.md (created) - Main research deliverable

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-25 | Story drafted from Epic P10-6 and tech spec |
| 2025-12-25 | Story completed - research document created |
