# Project Developer Memory & Onboarding Guide

> **Project Name:** Self-Correcting Autonomous Research Agent (V1 complete, V2 offline-RL + memory + frontend shipped)  
> **Core Concepts:** Iterative Knowledge Fusion (**IKF**) & Judgment Evaluation Vector (**JEV**)  
> **Last Updated:** October 2, 2026 (V2 learning layer shipped; secrets redacted)

---

## 1. Executive Summary & Vision

This repository implements an autonomous, self-correcting research agent designed to answer complex research questions by continuously searching the web, extracting atomic factual propositions, constructing a dynamic knowledge graph, detecting contradictions, identifying knowledge gaps, and synthesizing evidence-grounded reports.

Unlike traditional single-shot RAG (Retrieval-Augmented Generation) systems, this agent operates in an **iterative closed loop**:
1. **SearchAgent**: Queries the web (via Tavily API), deduplicates URLs and content hashes, and evaluates domain credibility scores.
2. **ClaimExtractor**: Deconstructs raw source text into atomic factual triples `(subject, predicate, object)` with confidence ratings (`high`, `medium`, `low`).
3. **KnowledgeFusion (IKF)**: Merges entities into canonical knowledge nodes and links relationships with weighted edges to form a growing knowledge graph.
4. **ContradictionDetector**: Analyzes claim pairs with LLM reasoning to detect empirical, factual, or quantitative contradictions and identifies knowledge gaps.
5. **DecisionEngine (JEV)**: Evaluates topic coverage, information gain, and unresolved conflicts to dynamically select the next action (`SEARCH`, `EXTRACT`, `FUSE`, `VERIFY`, `EXPAND_QUERY`, `STOP`).
6. **ReportGenerator**: Compiles the final executive summary, thematic findings, evidence table with numbered citations, and remaining unknowns.

---

## 2. System Status & Verification

All 5 development phases from [phases.md](file:///c:/Users/Lenovo/Desktop/JEVxIKF/phases.md) are **100% implemented and verified** (re-verified live on **September 26, 2026**):

| Phase | Milestone | Status | Key Artifacts |
|---|---|---|---|
| **Phase 1** | Foundation & Infrastructure | ✅ Completed | FastAPI, SQLite/PostgreSQL schema, Pydantic schemas, Next.js 16 app |
| **Phase 2** | Search & Source Collection | ✅ Completed | TavilyClient, SearchAgent, WebSocket broadcasting, domain credibility heuristics |
| **Phase 3** | Claim Extraction & IKF | ✅ Completed | ClaimExtractor, KnowledgeFusion, KnowledgeNode/Edge models, evidence table |
| **Phase 4** | Contradiction Detection & JEV | ✅ Completed | ContradictionDetector, DecisionEngine, coverage & information gain metrics |
| **Phase 5** | Report Generation & Polish | ✅ Completed | ReportGenerator, ReportView tab, session history sidebar, GitHub Actions CI |

### Verification Metrics (last verified: 2026-09-26)
- **Backend Test Suite:** 14 automated unit and integration tests passing (`pytest --cov=app`) with **70% code coverage**. Weakest spots: `research_orchestrator.py` (23%) and `metrics.py` (19%).
- **Frontend Code Quality:** ESLint passes with **0 errors, 1 warning** (`react-hooks/set-state-in-effect` at `components/research/SessionHistory.tsx:35` — synchronous `setState` inside a `useEffect`). Pre-existing minor issue; fix by deriving initial state from props or using a keyed remount.
- **Live E2E proof:** 1 completed research session in the local DB (question: *"how to use nanotrch in biotech"*, depth=shallow, 3 iterations, 24 sources, 93 claims, ~5.8 min start→finish) — the full Search → Extract → Fuse → Detect → Decide → Report loop works end-to-end.
- **Services Currently Running (as of 2026-09-26 ~15:11 UTC):**
  - Backend API: `http://localhost:8000` (FastAPI + Uvicorn with hot reload) — `/health` returns `{status: ok}`
  - Frontend UI: `http://localhost:3000` (Next.js 16 App Router) — HTTP 200
- **Repository note:** This project folder is **not a git repository yet** (`git init` has not been run). Before the first commit, make sure `backend/.env` is ignored — see the security warning in §6.

---

## 3. High-Level Architecture

```
[ User Request ] ───> [ Next.js Frontend (port 3000) ]
                              │
                    REST API  │  WebSocket Stream
                              ▼
                   [ FastAPI Backend (port 8000) ]
                              │
     ┌────────────────────────┴────────────────────────┐
     ▼                                                 ▼
[ ResearchOrchestrator ]                      [ Database (SQLite / Postgres) ]
  ├── 1. SearchAgent (Tavily API)                ├── research_sessions
  ├── 2. ClaimExtractor (LLM Tier 2)             ├── sources
  ├── 3. KnowledgeFusion (IKF Layer)             ├── claims & claim_source_links
  ├── 4. ContradictionDetector (LLM Tier 3)      ├── knowledge_nodes & edges
  ├── 5. DecisionEngine (JEV Heuristics)         ├── contradictions
  └── 6. ReportGenerator (LLM Tier 3)            └── decisions (RL training log)
```

---

## 4. Multi-Tier Model Router (`LLMRouter`)

To guarantee resilience against vendor rate limits, outages, and regional API changes, the backend uses a 3-tier routing strategy with automatic cascading fallback defined in [backend/app/integrations/llm_router.py](file:///c:/Users/Lenovo/Desktop/JEVxIKF/backend/app/integrations/llm_router.py):

| Tier | Provider | Default Model | Purpose / Task Types | Fallback Policy |
|---|---|---|---|---|
| **Tier 1** | Local Ollama | `llama3.2:latest` | Lightweight classification, query heuristics (`TaskType.CLASSIFY`) | Falls back to Tier 2 if Ollama is unreachable |
| **Tier 2** | Google Gemini | `gemini-3.8-flash` | Structured claim extraction, summarization (`TaskType.EXTRACT`, `TaskType.SUMMARIZE`) | Falls back to Tier 3 (Groq) on error |
| **Tier 3** | Groq Cloud | `openai/gpt-oss-120b` | High-reasoning contradiction analysis, gap detection, report synthesis (`TaskType.CONTRADICTION`, `TaskType.REASON`, `TaskType.REPORT`) | Falls back to Gemini Flash on error |

### Critical Model Notes
1. **Groq Model Update:** Groq decommissioned older models (`llama-3.1-70b-versatile` and `llama3-70b-8192`). The application currently uses `openai/gpt-oss-120b`.
2. **Gemini REST Client:** Configured to use `gemini-3.8-flash` with direct REST calls via `httpx` and `tenacity` retry decorators for exponential backoff on HTTP 429/503.
3. **Resilience & Rate Limits:** If any provider is overloaded or rate-limited, the orchestrator logs the warning, catches `ExternalAPIError`, and seamlessly cascades to the secondary provider without aborting the research run.

---

## 5. Codebase Directory Structure

```
JEVxIKF/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI for backend pytest & frontend lint
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── research.py  # Session start/stop/status & WebSocket endpoint
│   │   │   │   ├── sessions.py  # Session listing, pagination, deletion
│   │   │   │   ├── evidence.py  # Claims and linked source citations
│   │   │   │   ├── knowledge.py # Graph nodes and edges endpoint
│   │   │   │   └── reports.py   # Final research report fetching & export
│   │   │   ├── schemas/         # Pydantic v2 validation models
│   │   │   ├── dependencies.py  # Database session & API Key auth dependency
│   │   │   └── errors.py        # Centralized HTTP exception handlers
│   │   ├── database/
│   │   │   ├── models.py        # SQLAlchemy declarative ORM models
│   │   │   ├── repository.py    # Clean repository pattern for all DB operations
│   │   │   └── session.py       # Async SQLAlchemy engine & session maker
│   │   ├── integrations/
│   │   │   ├── llm_router.py    # Task-based dynamic multi-LLM router
│   │   │   ├── gemini_client.py # Google Gemini REST API client
│   │   │   ├── groq_client.py   # Groq cloud API client
│   │   │   ├── ollama_client.py # Local Ollama REST client
│   │   │   ├── tavily_client.py # Tavily Web Search API client
│   │   │   ├── cache_manager.py # In-memory / Redis cache abstraction
│   │   │   └── error_handlers.py# Tenacity retry policies
│   │   ├── services/
│   │   │   ├── research_orchestrator.py # Core async loop coordinating all components
│   │   │   ├── search_agent.py          # Tavily search & credibility scoring
│   │   │   ├── claim_extractor.py       # LLM JSON claim extraction
│   │   │   ├── knowledge_fusion.py      # IKF knowledge graph builder
│   │   │   ├── ikf/                     # IKF 2.0: entity_resolution, temporal,
│   │   │   │                            #   claim_versioning, provenance, evidence, service
│   │   │   ├── contradiction_detector.py# Conflicting assertions & gap finder
│   │   │   ├── decision_engine.py       # JEV heuristic action selector
│   │   │   ├── report_generator.py      # Executive summary & report compiler
│   │   │   ├── session_manager.py       # Session lifecycle helper
│   │   │   └── metrics.py               # Information gain, coverage, reward signals
│   │   ├── utils/
│   │   │   ├── helpers.py       # SHA-256 content hashing & domain parsing
│   │   │   ├── logger.py        # Standardized loguru/logging wrapper
│   │   │   ├── parsers.py       # HTML tag stripping & LLM token truncator
│   │   │   └── validators.py    # Question length and quality validator
│   │   ├── ws/
│   │   │   └── managers.py      # ConnectionManager for session WebSocket streaming
│   │   ├── config.py            # Pydantic BaseSettings loading from .env
│   │   └── main.py              # FastAPI app creation, CORS, router mounts
│   ├── tests/                   # 14 comprehensive pytest test suites
│   ├── requirements.txt         # Core dependencies
│   ├── requirements-dev.txt     # Test & linting dependencies (pytest, pytest-cov, ruff)
│   └── research_agent.db        # Development SQLite database (WAL mode)
├── frontend/
│   ├── app/
│   │   ├── layout.tsx           # Root layout with Inter font via next/font/google
│   │   ├── page.tsx             # Single-page shell: home/research/settings/about + top-right menu button
│   │   └── globals.css          # Design-system tokens, glassmorphism, noise overlay, sidebar/menu rules
│   ├── components/
│   │   ├── layout/
│   │   │   └── Sidebar.tsx              # Nav + history + Hide-menu action (off-canvas <=1024px)
│   │   ├── panels/
│   │   │   ├── SettingsPanel.tsx        # Appearance + default depth + connection health
│   │   │   └── AboutPanel.tsx           # Capabilities, pipeline, depth profiles, stack
│   │   ├── research/
│   │   │   ├── ResearchForm.tsx         # Modern interactive question input form
│   │   │   ├── ResearchDashboard.tsx    # Live research execution & report view
│   │   │   ├── ReportView.tsx           # Reading view + PDF export
│   │   │   ├── DashboardStats.tsx       # Metric cards + budget meter
│   │   │   ├── SessionHistory.tsx       # Sidebar with session list & deletion
│   │   │   ├── FacetCoveragePanel.tsx   # Per-dimension coverage (adaptive planner UI)
│   │   │   └── KnowledgeGraphView.tsx   # vis-network interactive graph
│   │   └── ui/
│   │       ├── ActivityFeed.tsx         # Real-time WebSocket event timeline
│   │       ├── Progress.tsx             # Circular SVG & linear coverage progress
│   │       ├── StatusBadge.tsx          # Multi-state badge (running, completed, etc.)
│   │       ├── Skeleton.tsx
│   │       ├── InfoCard.tsx
│   │       └── ThemeToggle.tsx          # legacy: superseded by the Settings theme control
│   ├── lib/
│   │   ├── api.ts               # Authenticated REST client wrapper
│   │   ├── types.ts             # Domain TypeScript interfaces
│   │   ├── useResearchSocket.ts # Resilient WebSocket hook with ping keepalive
│   │   ├── timeline.ts          # Live + replay event ordering
│   │   ├── pdf.ts               # Client-side report export
│   │   ├── facets.ts            # V2 facet-domain helpers
│   │   ├── preferences.ts       # Persisted theme + default depth
│   │   └── theme-script.ts      # No-flash pre-paint theme bootstrap
│   ├── package.json             # Next.js 16 + React 19 dependencies
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   └── postcss.config.mjs        # Tailwind v4 pipeline
├── docker-compose.yml           # Multi-container Docker deployment definition
├── IMPLEMENTATION.md            # Detailed implementation log
├── phases.md                    # Roadmap phases and acceptance criteria
├── prd.md                       # Product Requirements Document
├── architecture.md              # Architectural blueprint (refreshed for V2 changes)
├── DOCUMENTATION.md             # Full project documentation (refreshed for V2 changes)
├── design.md                    # Design notes
├── LEARNINGS.md                 # Lessons learned
├── rules.md                     # Working rules
└── memory.md                    # This document
```

---

## 6. Environment Variables Configuration

> ⚠️ **SECURITY:** Earlier versions of this document contained **real API keys in plaintext** (Tavily, Gemini, Groq). They have been redacted from this doc — the live values belong only in `backend/.env` (gitignored). If this file was ever shared or pushed, **rotate those keys** at [Tavily](https://app.tavily.com), [Google AI Studio](https://aistudio.google.com), and [Groq](https://console.groq.com).

### Backend (`backend/.env`)
```bash
ENVIRONMENT=development
DATABASE_URL=sqlite+aiosqlite:///./research_agent.db
# For PostgreSQL: postgresql+asyncpg://postgres:postgres@localhost:5432/research_agent

REDIS_URL=redis://localhost:6379/0
API_KEY=dev_api_key_jev_ikf_2026
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]

# API Providers (values live only in backend/.env — never commit or paste into docs)
TAVILY_API_KEY=<redacted>
GEMINI_API_KEY=<redacted>
GROQ_API_KEY=<redacted>

# Ollama Local Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:latest
```

### Frontend (`frontend/.env.local`)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## 7. How to Run Locally

### 1. Backend Server
```powershell
cd backend
# Activate virtual environment
.\.venv\Scripts\Activate.ps1
# Run FastAPI server with hot-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- Swagger UI / OpenAPI docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 2. Frontend Application
```powershell
cd frontend
# Run Next.js Turbopack dev server
npm run dev
```
- Open browser at: `http://localhost:3000`

### 3. Run Backend Test Suite
```powershell
cd backend
.\.venv\Scripts\pytest.exe --cov=app --cov-report=term-missing
```

### 4. Run Frontend Linter
```powershell
cd frontend
npx eslint .
```

---

## 8. Database Schema & Data Models

All models inherit from SQLAlchemy declarative base in [backend/app/database/models.py](file:///c:/Users/Lenovo/Desktop/JEVxIKF/backend/app/database/models.py):

1. **`research_sessions`**:
   - `id`: UUID string primary key.
   - `question`: User research query.
   - `depth`: `"shallow"` (3 iterations), `"standard"` (5 iterations), `"deep"` (8 iterations).
   - `status`: `"initializing"`, `"running"`, `"completed"`, `"stopped"`, `"error"`.
   - `current_iteration`: Integer tracking loop count.
   - `final_report`: JSON column storing synthesized executive summary, findings, evidence, contradictions, and citations.

2. **`sources`**:
   - `url`: Fully qualified URL.
   - `title`: Extracted page title.
   - `content`: Cleaned, parsed HTML content.
   - `credibility_score`: 0.0 to 1.0 (academic `.edu`/`.gov` get 0.9+, peer-reviewed sources get 0.95, social media gets 0.3).
   - `content_hash`: SHA-256 for deduplication.

3. **`claims` & `claim_source_links`**:
   - `claim`: Plaintext assertion.
   - `subject`, `predicate`, `object`: Atomic proposition components.
   - `confidence`: `"high"`, `"medium"`, `"low"`.
   - Linked to one or more `sources` via `claim_source_links`.

4. **`knowledge_nodes` & `knowledge_edges`**:
   - Graph representation of entities and relationships used by IKF.

5. **`contradictions`**:
   - Links `claim_1_id` and `claim_2_id`.
   - `severity`: `"high"`, `"medium"`, `"low"`.
   - `resolution_note`: Explanation of the conflict generated by Tier 3 LLM.

6. **`decisions`**:
   - Historical log of JEV actions (`SEARCH`, `EXTRACT`, `FUSE`, `VERIFY`, `EXPAND_QUERY`, `STOP`).
   - Stores knowledge state snapshot, reasoning, and computed `reward_signal` for future RL policy fine-tuning.

---

## 9. Key Technical Nuances & Gotchas

1. **WebSocket Protocol Keepalive**:
   - Client sends `"ping"` every 30 seconds to keep the socket alive through load balancers or proxies.
   - Backend responds immediately with `"pong"`.
2. **React 19 / Next.js State Derivation**:
   - Live metrics (`sources`, `claims`, `nodes`, `coverage`) in `ResearchDashboard.tsx` are computed using `useMemo` directly from the streamed message buffer rather than triggering cascading renders via `setState` in effects.
3. **Session Deletion Cascade**:
   - Deleting a session via `DELETE /api/sessions/{session_id}` cleanly removes all associated sources, claims, claim-source links, graph nodes, edges, contradictions, and logged decisions.
4. **JSON Parsing Resilience**:
   - LLMs occasionally wrap JSON in markdown tags (e.g. ` ```json ... ``` `). All extraction and report synthesis services use regex pattern matching `r"\{.*\}"` and `r"\[.*\]"` with fallback parsing to ensure zero unhandled JSON decode crashes.
5. **Safe Database Concurrency**:
   - The orchestrator opens short-lived `async_session_maker()` contexts per pipeline step and commits eagerly to avoid long-lived database locks.

---

## 10. Current capabilities (headline for About panel and docs)

- Adaptive research planner that decomposes each question into research dimensions and targets the largest useful gap next.
- Negative-result query cache so a dead-end query is not re-paid in the same run.
- One-click synthesis retry that re-runs only the summarization step over stored evidence.
- Per-session LLM call and context budgets with budget telemetry.
- Durable session-event log with client-side replay, including activity timeline for finished runs.
- Coverage-by-dimension panel and facet-targeted query selection.
- Versioned evidence in reports with credibility scores per source.
- Client-side PDF export of finished reports.

## 11. Future Extensibility & Next Steps

When extending this project in future sprints, consider the following areas:
- **Interactive WebGL Graph View:** Integrate `vis-network` or `react-force-graph` on the frontend for visual exploration of `knowledge_nodes` and `knowledge_edges`.
- **Export Formats:** Add PDF and Markdown export endpoints to `/api/research/{session_id}/report`.
- **RL Agent Fine-Tuning:** The `decisions` table already records `(state, action, reward)`. This data can be exported into standard RLlib or Gymnasium formats to replace the heuristic JEV policy with a trained reinforcement learning agent.

## 12. V2 Offline Learning (shipped 2026-10-02)

- **Loop unchanged:** JEV decides every live action. `TrajectoryRecorder`
  (`backend/app/services/rl/recorder.py`) sits beside the loop: one
  `ResearchTransition` per iteration (formal `ResearchState` before/after, named
  `RewardComponents`, observation), plus an `RLPrediction` row and `rl_shadow`
  event logging what the offline policy would have done — **stored, never
  executed**. Every recorder/shadow/memory failure is swallowed and logged.
- **Offline pipeline:** `rl/dataset.py` builds a validated JSONL dataset
  (`state/action/reward/next_state/done`, `DATASET_VERSION v2.0`); `rl/policy.py`
  trains a tabular contextual Monte-Carlo policy (Bayesian shrinkage, JEV fallback
  below 10 samples — deliberately not deep RL); `rl/evaluation.py` compares RL vs
  JEV per session and per action, honestly separating observed from counterfactual
  steps. Tables: `research_transitions`, `rl_policies`, `rl_predictions`,
  `evaluation_runs`, `evaluation_results` (migration `002_learning_layer`).
- **Memory 2.12:** first observation of a fact is stored; later runs supersede or
  conflict it (`memory/versions.py`, statuses active/superseded/conflicting/
  needs_verification) with per-version provenance; `/api/memory/conflicts` and the
  Memory panel surface them; `/api/memory/promote` re-promotes a finished session.
- **UI:** State inspector + Decision inspector tabs on the investigation; RL
  Evaluation and Long-term memory views in the sidebar; replay humanises
  `transition_recorded`, `rl_shadow`, `memory_recalled`, `memory_updated`.
- **Remaining V2 workstream:** the adaptive model router (2.5). Live Tavily runs
  still blocked by the 401 in `backend/.env`.
