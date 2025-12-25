# Epic Technical Specification: AI & Quality Improvements

Date: 2025-12-25
Author: Brent
Epic ID: P10-6
Status: Draft

---

## Overview

Epic P10-6 focuses on **research and documentation** for future AI enhancements in ArgusAI. This epic contains two research stories that investigate potential improvements to the AI analysis pipeline:

1. **Local MCP Server** - Research implementation of a Model Context Protocol server to provide richer context to AI models during event analysis
2. **Query-Adaptive Frame Selection** - Research techniques for selecting the most relevant frames when re-analyzing events with specific queries

This is a **research-only epic** - no implementation is expected. The deliverables are research documents that will inform future development phases.

**PRD Reference:** [PRD-phase10.md](../PRD-phase10.md) - "AI Enhancements" section
**Backlog Items:** IMP-016 (MCP Server), FF-022 (Query-Adaptive Frames)

## Objectives and Scope

### In Scope

- Research and document MCP (Model Context Protocol) specification and implementation patterns
- Evaluate hosting options for local MCP servers (sidecar, embedded, standalone)
- Define context data schema for AI-enhanced event analysis
- Research VL (Vision-Language) model embeddings for frame relevance scoring
- Document query-to-frame matching algorithms
- Assess performance and storage implications

### Out of Scope

- Actual implementation of MCP server
- Implementation of query-adaptive frame selection
- Changes to the existing AI pipeline
- Changes to the event analysis workflow
- Any new API endpoints or database models
- Frontend UI changes

## System Architecture Alignment

This epic produces research documentation only. However, the research should consider integration with the existing ArgusAI architecture:

**Current AI Pipeline Components:**
- `backend/app/services/ai_service.py` - Multi-provider AI service with fallback chain
- `backend/app/services/frame_extraction_service.py` - Frame extraction from video clips
- `backend/app/services/temporal_context_service.py` - CLIP embeddings for similarity search
- `backend/app/models/event.py` - Event model with AI description storage
- `backend/app/models/feedback.py` - User feedback on AI descriptions

**Architecture Constraints:**
- Research should consider embedding in existing Python/FastAPI backend
- MCP server patterns should be compatible with asyncio
- Frame selection research should leverage existing CLIP/SigLIP embeddings
- Any future implementation must maintain <5s p95 event processing latency

## Detailed Design

### Services and Modules

Since this is a research epic, no new services are implemented. However, research documents should outline potential future service structures:

| Potential Component | Purpose | Research Focus |
|---------------------|---------|----------------|
| MCPServer | Local MCP protocol server | Hosting patterns, context schema |
| ContextProvider | Expose entity/feedback data | Data sources, update frequency |
| QueryFrameScorer | Score frames by query relevance | Embedding comparison, algorithms |
| FrameEmbeddingStore | Store/retrieve frame embeddings | Storage format, indexing |

### Data Models and Contracts

**MCP Context Schema (Research Target):**

The research should define what context data would be exposed to AI models:

```json
{
  "context_type": "argusai_event_context",
  "version": "1.0",
  "data": {
    "user_feedback_history": [
      {"event_id": "...", "feedback": "positive|negative", "correction": "..."}
    ],
    "known_entities": [
      {"name": "...", "type": "person|vehicle", "attributes": {...}}
    ],
    "entity_corrections": [
      {"original": "...", "corrected": "...", "confidence": 0.95}
    ],
    "camera_context": {
      "location": "Front Door",
      "typical_activity": ["deliveries", "pedestrians"]
    },
    "time_patterns": {
      "current_hour": 14,
      "typical_activity_level": "medium"
    }
  }
}
```

**Frame Embedding Schema (Research Target):**

```json
{
  "frame_id": "evt-123_frame_001",
  "event_id": "evt-123",
  "embedding": [0.123, -0.456, ...],  // 512 or 768 dimensions
  "model": "clip-vit-base-patch32",
  "timestamp_ms": 1500,
  "quality_score": 0.85
}
```

### APIs and Interfaces

No new APIs are implemented in this epic. Research should document potential future APIs:

**Potential MCP Server Endpoints:**
- `GET /mcp/context/{event_id}` - Retrieve context for event analysis
- `POST /mcp/feedback` - Update context with new feedback
- `GET /mcp/entities` - List known entities with attributes

**Potential Frame Selection Endpoints:**
- `POST /api/v1/events/{id}/smart-reanalyze` - Re-analyze with query-adaptive frames
- `GET /api/v1/events/{id}/frame-relevance?query=...` - Score frame relevance

### Workflows and Sequencing

**MCP-Enhanced Event Analysis (Research Target):**

```
1. Event triggered (motion/smart detection)
2. Frames extracted from video
3. MCP Context Provider queried for:
   - Recent feedback on similar events
   - Known entity patterns
   - Time-of-day context
   - Camera-specific hints
4. AI prompt constructed with MCP context
5. AI model generates description
6. Feedback stored for future context
```

**Query-Adaptive Re-Analysis (Research Target):**

```
1. User requests re-analysis with query (e.g., "Was this a delivery?")
2. Query encoded to embedding using CLIP/SigLIP
3. All event frames scored by cosine similarity to query embedding
4. Top-K most relevant frames selected
5. Re-analysis uses selected frames instead of default sampling
6. Result compared to original for improvement metrics
```

## Non-Functional Requirements

### Performance

- **NFR-P10-6-1:** Research must document expected latency impact of MCP context lookup (<100ms target)
- **NFR-P10-6-2:** Frame embedding generation should be assessed for compute cost
- **NFR-P10-6-3:** Query-adaptive selection must not add more than 200ms to re-analysis

### Security

- **NFR-P10-6-4:** MCP context should not expose sensitive user data without authentication
- **NFR-P10-6-5:** Embeddings should not be reversible to original images

### Reliability/Availability

- **NFR-P10-6-6:** MCP server failure should not block event processing (fail open)
- **NFR-P10-6-7:** Cached embeddings should have TTL and invalidation strategy

### Observability

- **NFR-P10-6-8:** Research should recommend metrics for context usage tracking
- **NFR-P10-6-9:** Frame selection decisions should be loggable for debugging

## Dependencies and Integrations

### Current Dependencies (No Changes Required)

| Package | Version | Purpose |
|---------|---------|---------|
| sentence-transformers | >=2.2.0 | CLIP embeddings (already installed) |
| openai | >=1.54.0 | GPT models for analysis |
| anthropic | >=0.39.0 | Claude models for analysis |
| google-generativeai | >=0.8.0 | Gemini models for analysis |

### Potential Future Dependencies (Research Targets)

| Package | Purpose | Notes |
|---------|---------|-------|
| mcp-python | MCP protocol implementation | Evaluate Anthropic's MCP SDK |
| faiss-cpu | Vector similarity search | For efficient embedding lookup |
| transformers | Alternative embedding models | SigLIP, etc. |

## Acceptance Criteria (Authoritative)

### Story P10-6.1: Research Local MCP Server

1. **AC-6.1.1:** Given I read the research document, when I understand MCP server patterns, then I know implementation options for ArgusAI
2. **AC-6.1.2:** Given the research evaluates hosting options, when I review sidecar vs embedded vs standalone, then trade-offs are clearly documented
3. **AC-6.1.3:** Given the research defines context data schema, when I see what data to expose, then I understand entity corrections, feedback history, and camera context structures
4. **AC-6.1.4:** Given the research assesses performance impact, when I review latency estimates, then I know if MCP adds acceptable overhead
5. **AC-6.1.5:** Given future development begins, when implementation starts, then this research document guides design decisions

### Story P10-6.2: Research Query-Adaptive Frame Selection

1. **AC-6.2.1:** Given I read the research document, when I understand query-adaptive selection, then I know how to score frames by query relevance
2. **AC-6.2.2:** Given the research evaluates VL model embeddings, when I compare CLIP vs SigLIP vs alternatives, then recommendations are documented with rationale
3. **AC-6.2.3:** Given the research defines embedding storage, when I review storage requirements, then I understand schema, size, and indexing needs
4. **AC-6.2.4:** Given the research considers compute requirements, when I review embedding generation costs, then I know runtime and resource implications
5. **AC-6.2.5:** Given future development begins, when implementation starts, then this research document guides technical approach

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC-6.1.1 | MCP Context Schema | MCPServer (future) | Review document for completeness |
| AC-6.1.2 | Workflows - MCP-Enhanced | MCPServer (future) | Validate hosting options are documented |
| AC-6.1.3 | Data Models - MCP Context | ContextProvider (future) | Schema includes all mentioned data types |
| AC-6.1.4 | NFR Performance | MCPServer (future) | Latency estimates provided |
| AC-6.1.5 | Full document | All | Document exists and is actionable |
| AC-6.2.1 | Workflows - Query-Adaptive | QueryFrameScorer (future) | Scoring algorithm documented |
| AC-6.2.2 | Data Models - Frame Embedding | FrameEmbeddingStore (future) | Model comparison documented |
| AC-6.2.3 | Data Models - Frame Embedding | FrameEmbeddingStore (future) | Storage schema defined |
| AC-6.2.4 | NFR Performance | QueryFrameScorer (future) | Compute estimates provided |
| AC-6.2.5 | Full document | All | Document exists and is actionable |

## Risks, Assumptions, Open Questions

### Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|------------|--------|------------|
| R1 | MCP specification may evolve | Medium | Low | Pin to specific MCP version in research |
| R2 | VL embedding quality varies | Medium | Medium | Test multiple models, document recommendations |
| R3 | Storage costs for embeddings may be high | Low | Medium | Document approximate sizes, consider pruning |
| R4 | Research may not lead to implementation | Medium | Low | Keep research scope focused and actionable |

### Assumptions

- **A1:** MCP (Model Context Protocol) is suitable for this use case
- **A2:** Existing CLIP embeddings from temporal context service can inform frame selection
- **A3:** Research findings will be implemented in a future phase
- **A4:** Research can be completed without external API access or testing

### Open Questions

- **Q1:** Should MCP server run as sidecar or embedded in backend process?
- **Q2:** What is the optimal embedding dimension for frame relevance (512 vs 768)?
- **Q3:** Should frame embeddings be generated at event time or on-demand?
- **Q4:** How to handle query ambiguity (e.g., "delivery" could mean package or food)?

## Test Strategy Summary

Since this is a research epic, there is no code to test. Validation focuses on document quality:

### Research Document Review Criteria

1. **Completeness:** All acceptance criteria addressed
2. **Actionability:** Implementation guidance is specific enough to act upon
3. **Technical Accuracy:** Patterns and algorithms are correctly described
4. **Trade-off Analysis:** Options are compared with pros/cons
5. **Future Compatibility:** Recommendations align with ArgusAI architecture

### Deliverables

| Story | Deliverable | Location |
|-------|-------------|----------|
| P10-6.1 | MCP Server Research Document | `docs/research/mcp-server-research.md` |
| P10-6.2 | Query-Adaptive Frames Research | `docs/research/query-adaptive-frames-research.md` |

### Review Process

1. Author creates research document following acceptance criteria
2. Self-review against AC checklist
3. Document placed in `docs/research/` directory
4. Story marked complete when document passes AC

---

_Tech spec generated for Epic P10-6: AI & Quality Improvements_
_This is a research-only epic - no implementation required_
