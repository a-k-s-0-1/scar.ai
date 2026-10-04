# IMPLEMENTATION PLAN: Self-Correcting Research Agent MVP V1

> **Generated:** September 26, 2026
> **Status:** Ready to build — decisions locked in
> **Timeline:** 8–12 weeks (solo) / 4–6 weeks (2-person team)

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Search API** | Tavily | Purpose-built for AI agents, structured results, free tier |
| **LLM Strategy** | Hybrid Model Router | Free-tier Gemini Flash + open-source; no vendor lock-in |
| **Deployment** | Vercel (frontend) + Railway (backend) | Simple, git-based, cheap for MVP |
| **Auth** | No auth in V1 | Static API key in header; proper auth in V1.1 |
| **Phase scope** | Full 5-phase master plan | Build all phases sequentially |

---

## LLM Router Strategy (Key Decision)

The system uses a 3-tier model router — no single LLM dependency:

```
Tier 1 — LOCAL (Ollama / free):
  Model: mistral-7b, phi-3-mini, or llama-3.2-3b
  Tasks: Query routing, classification, simple decisions, action selection (JEV)
  Cost: $0

Tier 2 — FREE CLOUD (Gemini Flash via Google AI Studio):
  Model: gemini-1.5-flash (free 15 RPM / 1M tokens/day)
  Tasks: Claim extraction, summarization, gap detection, entity extraction
  Cost: $0 (within free limits)

Tier 3 — BEST FREE (Gemini 1.5 Pro or groq/llama-3.1-70b):
  Model: gemini-1.5-pro (free 2 RPM) or groq llama-3.1-70b-versatile (free)
  Tasks: Contradiction analysis, final report generation, complex reasoning
  Cost: $0 (within free limits)
```

**Router file:** `backend/app/integrations/llm_router.py`
Selects tier based on task type. Falls back to next tier on rate limit.

### Free API Keys Needed
- **Tavily**: https://app.tavily.com — free 1000 req/month
- **Google AI Studio (Gemini)**: https://aistudio.google.com — free tier
- **Groq**: https://console.groq.com — free tier, very fast inference
- **Ollama** (local): https://ollama.ai — run locally for Tier 1

---

## Final Project Structure

```
self-correcting-research-agent/
|
+-- backend/
|   +-- app/
|   |   +-- __init__.py
|   |   +-- main.py                         # FastAPI app init, CORS, middleware
|   |   +-- config.py                       # Settings via pydantic-settings
|   |   |
|   |   +-- api/
|   |   |   +-- __init__.py
|   |   |   +-- routes/
|   |   |   |   +-- __init__.py
|   |   |   |   +-- research.py             # POST /research/start, GET /research/{id}
|   |   |   |   +-- sessions.py             # Session CRUD
|   |   |   |   +-- knowledge.py            # GET /research/{id}/knowledge
|   |   |   |   +-- evidence.py             # GET /research/{id}/evidence
|   |   |   |   +-- reports.py              # GET /research/{id}/report
|   |   |   +-- schemas/
|   |   |   |   +-- __init__.py
|   |   |   |   +-- research.py             # ResearchQuestionInput, SessionResponse
|   |   |   |   +-- claim.py                # ClaimModel, ContradictionItem
|   |   |   |   +-- source.py               # SourceModel
|   |   |   |   +-- knowledge.py            # KnowledgeNode, KnowledgeEdge
|   |   |   |   +-- session.py              # SessionSummary
|   |   |   +-- dependencies.py             # get_db(), get_api_key()
|   |   |   +-- errors.py                   # Custom HTTP exceptions
|   |   |
|   |   +-- services/
|   |   |   +-- __init__.py
|   |   |   +-- research_orchestrator.py    # Main research loop driver
|   |   |   +-- search_agent.py             # Tavily wrapper + dedup + credibility
|   |   |   +-- claim_extractor.py          # LLM claim extraction (Tier 2)
|   |   |   +-- knowledge_fusion.py         # IKF: entities + edges + merge
|   |   |   +-- contradiction_detector.py   # Gap + contradiction detection (Tier 3)
|   |   |   +-- decision_engine.py          # JEV: hardcoded rules v1 (Tier 1)
|   |   |   +-- report_generator.py         # Final report compiler (Tier 3)
|   |   |   +-- session_manager.py          # Session lifecycle
|   |   |   +-- metrics.py                  # Reward signal logging
|   |   |
|   |   +-- integrations/
|   |   |   +-- __init__.py
|   |   |   +-- tavily_client.py            # Tavily search API wrapper
|   |   |   +-- llm_router.py               # Model router: Tier 1/2/3 selection
|   |   |   +-- gemini_client.py            # Google Gemini API client
|   |   |   +-- groq_client.py              # Groq API client (llama-3.1-70b)
|   |   |   +-- ollama_client.py            # Ollama local model client
|   |   |   +-- cache_manager.py            # Redis operations
|   |   |   +-- error_handlers.py           # API error mapping + retry logic
|   |   |
|   |   +-- database/
|   |   |   +-- __init__.py
|   |   |   +-- models.py                   # SQLAlchemy ORM models
|   |   |   +-- repository.py               # Data access layer (no raw SQL)
|   |   |   +-- session.py                  # DB session factory
|   |   |   +-- migrations/
|   |   |       +-- alembic.ini
|   |   |       +-- env.py
|   |   |       +-- versions/
|   |   |           +-- 001_initial_schema.py
|   |   |
|   |   +-- utils/
|   |   |   +-- __init__.py
|   |   |   +-- logger.py                   # Structured logging setup
|   |   |   +-- validators.py               # Question quality validation
|   |   |   +-- parsers.py                  # HTML to plain text extraction
|   |   |   +-- helpers.py                  # UUID, hash, time utilities
|   |   |
|   |   +-- ws/
|   |       +-- __init__.py
|   |       +-- managers.py                 # WebSocket connection manager
|   |
|   +-- tests/
|   |   +-- __init__.py
|   |   +-- conftest.py
|   |   +-- test_search_agent.py
|   |   +-- test_claim_extractor.py
|   |   +-- test_knowledge_fusion.py
|   |   +-- test_contradiction_detector.py
|   |   +-- test_decision_engine.py
|   |   +-- test_report_generator.py
|   |
|   +-- requirements.txt
|   +-- requirements-dev.txt
|   +-- Dockerfile
|   +-- .env.example
|   +-- README.md
|
+-- frontend/
|   +-- app/
|   |   +-- layout.tsx
|   |   +-- page.tsx
|   |   +-- globals.css
|   |   +-- dashboard/
|   |       +-- page.tsx
|   |       +-- [sessionId]/
|   |           +-- page.tsx
|   |           +-- layout.tsx
|   |
|   +-- components/
|   |   +-- forms/
|   |   |   +-- ResearchForm.tsx
|   |   +-- session/
|   |   |   +-- ProgressWidget.tsx
|   |   |   +-- ControlPanel.tsx
|   |   |   +-- SessionTimer.tsx
|   |   +-- report/
|   |   |   +-- ExecutiveSummary.tsx
|   |   |   +-- EvidenceTable.tsx
|   |   |   +-- KnowledgeGraph.tsx
|   |   |   +-- ContradictionView.tsx
|   |   |   +-- UnknownsSection.tsx
|   |   |   +-- SourceList.tsx
|   |   +-- common/
|   |   |   +-- Header.tsx
|   |   |   +-- Footer.tsx
|   |   |   +-- LoadingSpinner.tsx
|   |   |   +-- ErrorBoundary.tsx
|   |   |   +-- Toast.tsx
|   |   +-- ui/
|   |       +-- Button.tsx
|   |       +-- Input.tsx
|   |       +-- Badge.tsx
|   |       +-- Card.tsx
|   |       +-- ProgressBar.tsx
|   |       +-- Tabs.tsx
|   |
|   +-- hooks/
|   |   +-- useResearchSession.ts
|   |   +-- useWebSocket.ts
|   |   +-- useFetchReport.ts
|   |   +-- useLocalStorage.ts
|   |
|   +-- lib/
|   |   +-- api.ts
|   |   +-- constants.ts
|   |   +-- utils.ts
|   |   +-- types.ts
|   |
|   +-- .env.example
|   +-- tsconfig.json
|   +-- tailwind.config.ts
|   +-- next.config.js
|   +-- package.json
|
+-- docker-compose.yml
+-- .gitignore
+-- .env.example
+-- README.md
```

---

## Environment Variables

### Root `.env.example`

```env
# Search
TAVILY_API_KEY=tvly-...

# LLM Tier 2 (claim extraction)
GEMINI_API_KEY=AIzaSy...

# LLM Tier 3 (complex reasoning + reports)
GROQ_API_KEY=gsk_...

# Tier 1 Local Ollama (optional, falls back to Gemini Flash)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=phi3:mini

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/research_agent

# Redis
REDIS_URL=redis://localhost:6379

# API Security (static key, no user auth in V1)
API_KEY=change_me_in_production

# App
ENVIRONMENT=development
LOG_LEVEL=INFO
MAX_RESEARCH_TIME_MINUTES=10
MAX_QUERIES_PER_SESSION=50
```

### Frontend `.env.example`

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## Database Schema (Complete SQL)

Migration file: `backend/app/database/migrations/versions/001_initial_schema.py`

```sql
-- Users (placeholder for V1; full auth in V1.1)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Research Sessions
CREATE TABLE research_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    question TEXT NOT NULL,
    depth VARCHAR(20) NOT NULL DEFAULT 'standard',
    domain VARCHAR(100),
    geographic_scope VARCHAR(100) DEFAULT 'global',
    time_range VARCHAR(100),
    max_research_time_minutes INT NOT NULL DEFAULT 5,
    min_sources_required INT NOT NULL DEFAULT 10,
    output_format VARCHAR(50) NOT NULL DEFAULT 'report',
    status VARCHAR(50) NOT NULL DEFAULT 'initializing',
    CONSTRAINT status_check CHECK (status IN ('initializing','running','completed','error','stopped')),
    current_iteration INT DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sessions_status ON research_sessions(status);
CREATE INDEX idx_sessions_user ON research_sessions(user_id, created_at DESC);

-- Sources
CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
    url VARCHAR(2048) NOT NULL,
    title TEXT,
    source_type VARCHAR(50) DEFAULT 'article',
    credibility_score FLOAT NOT NULL DEFAULT 0.5,
    published_at TIMESTAMP,
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    content TEXT,
    content_hash VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sources_session ON sources(session_id);
CREATE INDEX idx_sources_hash ON sources(content_hash);

-- Claims
CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
    claim TEXT NOT NULL,
    subject VARCHAR(255),
    predicate VARCHAR(255),
    object TEXT,
    confidence VARCHAR(50) NOT NULL DEFAULT 'medium',
    CONSTRAINT confidence_check CHECK (confidence IN ('high','medium','low')),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_claims_session ON claims(session_id);
CREATE INDEX idx_claims_subject ON claims(subject, predicate);

-- Claim to Source Links
CREATE TABLE claim_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    support_type VARCHAR(50) NOT NULL DEFAULT 'supports',
    CONSTRAINT support_check CHECK (support_type IN ('supports','refutes','neutral')),
    confidence FLOAT NOT NULL DEFAULT 0.8
);
CREATE INDEX idx_claim_sources_claim ON claim_sources(claim_id);
CREATE INDEX idx_claim_sources_source ON claim_sources(source_id);

-- Knowledge Graph Nodes
CREATE TABLE knowledge_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
    entity TEXT NOT NULL,
    entity_type VARCHAR(100) DEFAULT 'concept',
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_nodes_session ON knowledge_nodes(session_id);

-- Knowledge Graph Edges
CREATE TABLE knowledge_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
    source_node_id UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    relationship_type VARCHAR(100),
    strength FLOAT NOT NULL DEFAULT 0.7,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_edges_session ON knowledge_edges(session_id);

-- Research Actions (for future RL training data)
CREATE TABLE research_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
    iteration_number INT NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    query TEXT,
    result_summary TEXT,
    sources_found INT DEFAULT 0,
    new_claims_extracted INT DEFAULT 0,
    information_gain FLOAT,
    duration_seconds INT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_actions_session ON research_actions(session_id);

-- Decisions (for RL training data)
CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
    iteration_number INT NOT NULL,
    knowledge_state_snapshot JSONB,
    available_actions TEXT[],
    selected_action VARCHAR(50),
    action_reasoning TEXT,
    reward_signal FLOAT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_decisions_session ON decisions(session_id);

-- Contradictions
CREATE TABLE contradictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
    claim_1_id UUID NOT NULL REFERENCES claims(id),
    claim_2_id UUID NOT NULL REFERENCES claims(id),
    severity VARCHAR(50) NOT NULL DEFAULT 'medium',
    CONSTRAINT severity_check CHECK (severity IN ('low','medium','high')),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolution_note TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_contradictions_session ON contradictions(session_id);
```

---

## Phase 1: Foundation & Infrastructure (Weeks 1-2)

**Goal:** Running skeleton — start session, store in DB, retrieve status.

### Backend Tasks (ordered)

1. `requirements.txt` — pin all dependencies
2. `app/config.py` — pydantic-settings reading all env vars
3. `database/models.py` — all SQLAlchemy ORM models
4. `database/session.py` — async engine + session factory (asyncpg)
5. `database/migrations/` — Alembic init + `001_initial_schema.py`
6. `database/repository.py` — `SessionRepository`, `SourceRepository`, `ClaimRepository`
7. `api/schemas/research.py` — `ResearchQuestionInput`, `ResearchSessionResponse`
8. `api/schemas/session.py` — `SessionSummary`
9. `api/dependencies.py` — `get_db()`, `get_api_key()` (validates `X-API-Key` header)
10. `api/errors.py` — `SessionNotFoundError`, `InvalidQuestionError`, handlers
11. `api/routes/research.py` — `POST /api/research/start`, `GET /api/research/{id}`
12. `api/routes/sessions.py` — `GET /api/sessions`, `POST /api/research/{id}/stop`
13. `app/main.py` — wire FastAPI, CORS (localhost:3000), routes, middleware
14. `utils/validators.py` — `validate_question()` (min 10 chars, not empty)
15. `utils/logger.py` — structured JSON logging with session_id in context
16. `Dockerfile` — Python 3.11-slim, uvicorn, non-root user
17. `docker-compose.yml` — FastAPI (8000) + PostgreSQL 15 (5432) + Redis 7 (6379)

### Frontend Tasks (ordered)

1. `npx create-next-app@latest frontend --typescript --tailwind --app --no-src-dir`
2. `lib/types.ts` — `ResearchSession`, `Source`, `Claim`, `Report` TypeScript types
3. `lib/constants.ts` — API_URL, WS_URL, depth options, max time
4. `lib/api.ts` — typed `startResearch()`, `getSession()`, `stopSession()` functions
5. `components/common/Header.tsx` — dark header, slate-900 bg
6. `components/ui/Button.tsx`, `Card.tsx`, `Badge.tsx`, `ProgressBar.tsx`
7. `components/forms/ResearchForm.tsx` — textarea + depth dropdown + submit button
8. `app/page.tsx` — home page with ResearchForm centered
9. `app/dashboard/[sessionId]/page.tsx` — session page shell (shows session ID)

### Python Dependencies (`requirements.txt`)

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
pydantic-settings==2.5.2
sqlalchemy[asyncio]==2.0.35
asyncpg==0.30.0
alembic==1.13.3
redis[asyncio]==5.1.1
httpx==0.27.2
aiohttp==3.10.9
python-dotenv==1.0.1
websockets==13.1
tenacity==9.0.0
beautifulsoup4==4.12.3
lxml==5.3.0
```

### Dev Dependencies (`requirements-dev.txt`)

```
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0
black==24.10.0
ruff==0.6.9
mypy==1.11.2
```

### Phase 1 Acceptance Criteria

- [ ] `POST /api/research/start` returns `{ session_id, status, estimated_time }`
- [ ] `GET /api/research/{id}` returns session details
- [ ] `GET /health` returns `{ status: "ok" }`
- [ ] Frontend form submits and redirects to `/dashboard/{session_id}`
- [ ] `docker-compose up` starts all 3 services without errors
- [ ] `pytest tests/` passes (DB connection + session create/read at minimum)

---

## Phase 2: Search & Source Collection (Weeks 3-4)

**Goal:** Execute Tavily searches, store sources, stream progress via WebSocket.

### Backend Tasks (ordered)

1. `integrations/tavily_client.py`
   - `TavilyClient.search(query, max_results=10)` returning `List[dict]`
   - Handle `429` with exponential backoff via `tenacity` (max 3 retries)
   - Structured result: `{ url, title, content, published_date, score }`

2. `services/search_agent.py`
   - `SearchAgent(session_id, max_queries=50)`
   - `search(query)` — dedup by URL hash, estimate credibility, store sources in DB
   - `estimate_credibility()` — boost `.edu`, `.gov`, `arxiv.org`, `nature.com` (+0.2); penalize `reddit`, `twitter` (-0.1)
   - Raise `RateLimitExceededError` when `queries_used >= max_queries`

3. `ws/managers.py` — `ConnectionManager` with `connect()`, `disconnect()`, `send_progress(session_id, message)`

4. `api/routes/research.py` — add `WebSocket /ws/{session_id}` endpoint

5. `services/research_orchestrator.py` (Phase 2 version):
   - `run_session(session_id)` — main async loop, pushes WS updates
   - `_execute_search_step()` — calls SearchAgent, stores sources, broadcasts
   - Hard-code `next_action = "SEARCH"` (decision engine wired in Phase 4)
   - Launch via `asyncio.create_task()` when session starts

6. `integrations/error_handlers.py` — retry logic, circuit breaker pattern

### Frontend Tasks (ordered)

1. `hooks/useWebSocket.ts` — connects to WS, parses messages, auto-reconnect on disconnect
2. `hooks/useResearchSession.ts` — polls `GET /api/research/{id}` every 5s as WS fallback
3. `components/session/ProgressWidget.tsx` — iteration, sources, claims, time, info-gain bar
4. `components/session/ControlPanel.tsx` — Stop button calling `POST /api/research/{id}/stop`
5. `components/session/SessionTimer.tsx` — elapsed time, formatted MM:SS
6. Update `app/dashboard/[sessionId]/page.tsx` — render ProgressWidget + ControlPanel

### Phase 2 Acceptance Criteria

- [ ] Tavily search executes and returns at least 1 source per query
- [ ] Duplicate sources filtered (same URL)
- [ ] Credibility score assigned (0.0-1.0) to every source
- [ ] WebSocket pushes `{ type: "progress", iteration, sources_count, step }` live
- [ ] Frontend ProgressWidget updates in real-time without page refresh
- [ ] `POST /api/research/{id}/stop` halts the loop gracefully
- [ ] Search API timeout triggers retry with backoff, not crash

---

## Phase 3: Claim Extraction & Knowledge Fusion (Weeks 5-6)

**Goal:** LLM extracts claims from sources; knowledge graph built; IKF layer complete.

### Backend Tasks (ordered)

1. `integrations/gemini_client.py`
   - `GeminiClient.generate(prompt, model="gemini-1.5-flash", temperature=0.2)`
   - Handle rate limit (15 RPM) with `tenacity` + 60s wait on `429`

2. `integrations/groq_client.py`
   - `GroqClient.generate(prompt, model="llama-3.1-70b-versatile", temperature=0.2)`
   - Handle Groq free tier limits

3. `integrations/ollama_client.py`
   - `OllamaClient.generate(prompt, model="phi3:mini")`
   - Graceful skip if Ollama not running (falls back to Tier 2)

4. `integrations/llm_router.py`
   - `LLMRouter.route(task_type)` returns correct client
   - Task types: `"classify"` → Tier 1, `"extract"` → Tier 2, `"reason"` → Tier 3
   - `LLMRouter.generate(task_type, prompt)` with automatic tier fallback on rate limit

5. `services/claim_extractor.py`
   - `ClaimExtractor.extract(sources: List[Source])` using Tier 2
   - Truncate source content to 4000 chars before LLM call
   - Prompt: structured JSON with subject/predicate/object/confidence
   - Validate JSON response; retry up to 3x on malformed JSON
   - Return `List[Claim]`

6. `services/knowledge_fusion.py`
   - `KnowledgeFusion.fuse(session_id, claims)`
   - `_extract_entities()` — subjects + well-formed objects → `KnowledgeNode` rows
   - `_extract_relationships()` — predicates + confidence → `KnowledgeEdge` rows
   - `_merge_duplicate_nodes()` — lowercase exact-match dedup (embedding merge in V2)

7. Update `services/research_orchestrator.py` — add extraction + fusion after search step

8. `api/routes/knowledge.py` — `GET /api/research/{id}/knowledge` returns `{ nodes, edges }`

9. `api/routes/evidence.py` — `GET /api/research/{id}/evidence` returns `{ claims, sources }`

### Frontend Tasks (ordered)

1. Install: `npm install vis-network vis-data @tanstack/react-table`
2. `components/report/KnowledgeGraph.tsx` — vis-network with physics, pan/zoom, node labels
3. `components/report/EvidenceTable.tsx` — TanStack table, sortable by confidence
4. `components/ui/Badge.tsx` — color-coded: emerald (high), amber (medium), red (low)
5. Update session page — add tabs: Progress / Knowledge / Evidence
6. Wire Knowledge tab to `GET /api/research/{id}/knowledge`
7. Wire Evidence tab to `GET /api/research/{id}/evidence`

### Phase 3 Acceptance Criteria

- [ ] Claims extracted from at least 1 source per iteration with valid subject/predicate/object
- [ ] All claims stored in DB with confidence level
- [ ] Knowledge graph nodes created for unique entities
- [ ] Knowledge graph edges created for claim relationships
- [ ] Duplicate nodes merged (case-insensitive)
- [ ] `GET /knowledge` returns graph JSON renderable by vis-network
- [ ] LLM router falls back Tier 1 → 2 → 3 on rate limit automatically
- [ ] Malformed LLM JSON → retry, not crash

---

## Phase 4: Contradiction Detection & Decision Engine (Weeks 7-8)

**Goal:** Detect contradictions, wire JEV decision rules, close the self-correction loop.

### Backend Tasks (ordered)

1. `services/contradiction_detector.py`
   - `ContradictionDetector.detect(session_id)` using Tier 3 (Groq)
   - Strategy: find claims with same `subject + predicate` but conflicting `object`
   - Confirm genuine contradiction with LLM prompt (avoid false positives)
   - Store `Contradiction` rows with severity (high/medium/low)
   - `detect_gaps()` — identify subjects mentioned but with <2 supporting claims
   - Return `ContradictionReport { contradictions, gaps, coverage_estimate }`

2. `services/decision_engine.py` — JEV hardcoded rules for V1:
   ```python
   def select_action(state: KnowledgeState) -> ActionType:
       if state.unresolved_contradictions > 0:
           return ActionType.VERIFY
       elif state.coverage_estimate < 0.65:
           return ActionType.SEARCH
       elif len(state.gaps) > 0:
           return ActionType.EXPAND_QUERY
       elif state.iteration >= state.max_iterations:
           return ActionType.STOP
       elif state.information_gain < 0.2:
           return ActionType.STOP
       else:
           return ActionType.SEARCH
   ```
   - Log `Decision` row with reward signal per iteration

3. `services/metrics.py` — compute and log reward:
   ```
   reward = information_gain + (avg_credibility * avg_confidence)
            - (unresolved_contradictions * 5)
            - (duplicate_ratio * 2)
            - 0.1  # action cost
   ```

4. Update `services/research_orchestrator.py` — full loop:
   Search → Extract → Fuse → Detect → Decide → [loop or stop]
   Query generation uses detected gaps as follow-up search terms.

5. `api/routes/evidence.py` — add `GET /api/research/{id}/contradictions`

6. Update `GET /api/research/{id}` — include `coverage_estimate`, `contradiction_count`

### Frontend Tasks (ordered)

1. `components/report/ContradictionView.tsx` — list with severity badges, claim 1 vs claim 2, source links
2. Add Contradictions tab to session page
3. Update ProgressWidget — add coverage %, contradiction count, current decision
4. Add WS message handler for `"contradiction_detected"` — show alert in real-time
5. Add WS message handler for `"decision_made"` — show reasoning in progress view

### Phase 4 Acceptance Criteria

- [ ] Contradictions detected when two claims conflict on same subject/predicate
- [ ] Decision engine selects correct action for every knowledge state
- [ ] Full research loop iterates: search → extract → fuse → detect → decide → repeat
- [ ] Loop stops when: coverage > 80%, info gain < 0.2, max iterations, or time limit hit
- [ ] Each decision logged with reward signal
- [ ] `GET /api/research/{id}/contradictions` returns structured list
- [ ] Frontend shows contradiction count and decision reasoning in real-time

---

## Phase 5: Report Generation & Final Polish (Weeks 9-10)

**Goal:** Generate structured final report, polish UI, test 20+ real questions.

### Backend Tasks (ordered)

1. `services/report_generator.py` (uses Tier 3):
   - `generate_executive_summary(session_id)` — 2-3 sentence summary from top claims
   - `build_evidence_table(session_id)` — claims ranked by confidence, source links
   - `list_contradictions(session_id)` — unresolved contradictions with context
   - `list_unknowns(session_id)` — gaps not resolved by session end
   - `format_citations(session_id)` — numbered list with URLs + titles
   - `compile_report(session_id)` — assembles `FinalReport` dataclass, stores as JSONB

2. Migration `002_add_report_data.py` — add `report_data JSONB` column to `research_sessions`

3. `api/routes/reports.py` — `GET /api/research/{id}/report` — returns full report JSON

4. `api/routes/sessions.py` — `GET /api/sessions` — paginated list with status, question, timestamps

5. `utils/parsers.py` — improve HTML to clean text (BeautifulSoup, strip nav/ads/scripts)

6. Full error handling audit — every endpoint covered with proper HTTP status codes

7. Request timeout middleware — hard kill sessions exceeding `MAX_RESEARCH_TIME_MINUTES`

8. Structured logging audit — all services log timing, counts, errors

### Frontend Tasks (ordered)

1. `components/report/ExecutiveSummary.tsx` — prominent summary card
2. `components/report/SourceList.tsx` — numbered citations, credibility score badge, external link icon
3. `components/report/UnknownsSection.tsx` — "What we couldn't determine" section
4. Complete session page tabs: Report / Knowledge / Contradictions / Evidence
5. `hooks/useFetchReport.ts` — polls `GET /report` until `status === "completed"`
6. Export JSON button — downloads full report as `.json` file
7. `app/dashboard/page.tsx` — recent sessions list (question, status, date, duration)
8. Mobile responsive audit — all components at 768px and 375px
9. Loading skeletons for all async data sections
10. 404 and 500 error pages

### Phase 5 Acceptance Criteria

- [ ] Report generated for 95%+ of submitted test questions
- [ ] Executive summary is 2-3 sentences, factually accurate
- [ ] Evidence table shows at least 10 claims for standard depth
- [ ] All claims have at least 1 source citation
- [ ] Session list loads all past sessions
- [ ] JSON export downloads valid file
- [ ] Tested manually with 20 real research questions
- [ ] `tsc --noEmit` passes (zero TypeScript errors)
- [ ] `mypy app/` passes (zero type errors)
- [ ] `ruff check` + `black --check` pass
- [ ] `pytest` passes with at least 70% coverage

---

## API Endpoint Summary

| Method | Path | Phase | Description |
|--------|------|-------|-------------|
| GET | `/health` | 1 | Liveness check |
| POST | `/api/research/start` | 1 | Start new research session |
| GET | `/api/research/{id}` | 1 | Get session status and metadata |
| POST | `/api/research/{id}/stop` | 2 | Stop running session |
| WS | `/ws/{session_id}` | 2 | Real-time progress stream |
| GET | `/api/research/{id}/knowledge` | 3 | Knowledge graph nodes and edges |
| GET | `/api/research/{id}/evidence` | 3 | Claims and sources |
| GET | `/api/research/{id}/contradictions` | 4 | Contradiction list |
| GET | `/api/research/{id}/report` | 5 | Full final report |
| GET | `/api/sessions` | 5 | Paginated session list |

**Auth:** All endpoints (except `/health`) require `X-API-Key: {API_KEY}` header.

---

## WebSocket Message Types (Server to Client)

```typescript
{ type: "initialized", session_id: string, estimated_time_seconds: number }
{ type: "search_started", iteration: number, query: string }
{ type: "sources_found", iteration: number, count: number, new_count: number }
{ type: "extraction_started", iteration: number, sources_count: number }
{ type: "claims_extracted", iteration: number, count: number, new_count: number }
{ type: "knowledge_updated", nodes: number, edges: number }
{ type: "contradiction_detected", count: number, severity: "low" | "medium" | "high" }
{ type: "decision_made", action: string, reasoning: string, coverage: number }
{ type: "iteration_complete", iteration: number, information_gain: number }
{ type: "completed", report_ready: true, total_claims: number, total_sources: number }
{ type: "error", message: string, recoverable: boolean }
{ type: "stopped", by: "user" | "timeout" | "convergence" }
```

---

## Deployment

### Local Development

```bash
# Copy env file and fill in API keys
cp .env.example .env

# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec backend alembic upgrade head

# Start frontend
cd frontend && cp .env.example .env.local && npm install && npm run dev

# Run backend tests
docker-compose exec backend pytest tests/ --cov=app --cov-report=term-missing
```

### Production: Frontend to Vercel

```bash
cd frontend
vercel --prod
# Set in Vercel dashboard:
# NEXT_PUBLIC_API_URL=https://your-app.railway.app
# NEXT_PUBLIC_WS_URL=wss://your-app.railway.app
```

### Production: Backend to Railway

```
1. Connect GitHub repo to Railway
2. New Service → Deploy from GitHub (select repo, set root to /)
3. Railway detects Dockerfile automatically
4. Add PostgreSQL plugin → copy DATABASE_URL to env vars
5. Add Redis plugin → copy REDIS_URL to env vars
6. Set all other env vars from .env.example in Railway dashboard
7. Railway auto-deploys on push to main branch
```

---

## Known Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Gemini Flash rate limit (15 RPM free) | LLM router falls back to Groq; add 4s delay between extractions |
| Groq free tier daily limits | Cache LLM results by content hash to avoid re-extraction |
| Tavily 1000 req/month free limit | Keep max_queries=15/session in dev; increase for prod paid plan |
| Ollama not running locally | Router skips Tier 1, goes directly to Gemini Flash |
| vis-network slow on large graphs | Cap nodes rendered to 50; paginate/cluster edges |
| Railway cold starts on free plan | Use Railway hobby plan ($5/mo) or add health check pinger |

---

## Pre-Launch Checklist

- [ ] All 5 phases complete and acceptance criteria met
- [ ] 20+ real research questions tested manually
- [ ] Zero hardcoded API keys in source code
- [ ] `.env.example` documents every required variable with description
- [ ] `pytest` passes with 70%+ coverage
- [ ] `tsc --noEmit` passes (no TypeScript errors)
- [ ] `ruff check` and `black --check` pass
- [ ] `mypy app/` passes (no type errors)
- [ ] 90%+ of test sessions complete in under 8 minutes
- [ ] Error handling verified: Search API down → graceful user message
- [ ] Error handling verified: LLM rate limited → retry + fallback works
- [ ] Knowledge graph renders on 0 nodes (empty state handled)
- [ ] Mobile layout works at 768px
- [ ] `.gitignore` excludes `.env`, `__pycache__`, `node_modules`, `.next`
- [ ] README written with quickstart instructions

---

## Post-V1 Roadmap

| Version | Features |
|---------|---------|
| V1.1 | JWT auth + user accounts, PDF export, light mode, better stopping heuristics |
| V1.2 | pgvector embedding-based duplicate merging, query diversity scoring |
| V2 | RL policy replacing hardcoded JEV decision engine, long-term session memory |
| V3 | Multi-agent research, custom reward learning, collaborative sessions |
