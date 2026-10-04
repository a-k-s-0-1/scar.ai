# System Architecture: Self-Correcting Research Agent MVP V1

## 1. High-Level System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE (Web)                          │
│                          (Next.js + React)                           │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │  Input Form      │  │  Progress Widget │  │  Report Display  │ │
│  │ (Question Entry) │  │  (Live Updates)  │  │  (Graph, Table)  │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘ │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ REST API + WebSocket
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      BACKEND API (FastAPI)                           │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Research Orchestration Layer                   │   │
│  │  - Session Management                                       │   │
│  │  - Research Flow Control                                    │   │
│  │  - Error Handling & Retry Logic                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                               ▼                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │  Search  │  │  Claim   │  │Knowledge │  │ Decision Engine  │   │
│  │ Agent    │  │Extraction│  │ Fusion   │  │ (JEV)            │   │
│  │(Web API) │  │ (LLM)    │  │ (IKF)    │  │ (Hardcoded v1)   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │         Knowledge Graph & State Management                   │  │
│  │  - Entity extraction                                         │  │
│  │  - Relationship mapping                                      │  │
│  │  - Contradiction detection                                   │  │
│  │  - Gap analysis                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Report Generation Engine                        │  │
│  │  - Evidence aggregation                                      │  │
│  │  - Graph visualization prep                                  │  │
│  │  - Citation formatting                                       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│   PostgreSQL   │  │   Redis Cache  │  │ External APIs  │
│   + pgvector   │  │   (Sessions)   │  │ (Search, LLM)  │
│ (Persistent DB)│  │                │  │                │
└────────────────┘  └────────────────┘  └────────────────┘
```

---

## 2. Backend Service Architecture

### 2.1 API Layer (FastAPI)

**File:** `backend/app/main.py`

```
api/
├── routes/
│   ├── research.py        # POST /research, GET /research/{id}
│   ├── sessions.py        # Session CRUD endpoints
│   ├── knowledge.py       # GET /research/{id}/knowledge
│   ├── evidence.py        # GET /research/{id}/evidence
│   └── reports.py         # GET /research/{id}/report
├── schemas/
│   ├── research.py        # Pydantic models for request/response
│   ├── session.py
│   ├── claim.py
│   └── knowledge_graph.py
├── dependencies.py        # Shared dependencies, auth
└── main.py               # App setup, middleware, CORS
```

### 2.2 Core Service Layer

```
services/
├── research_orchestrator.py   # Main research loop coordinator
├── search_agent.py            # Web search execution
├── claim_extractor.py         # LLM-based claim extraction
├── knowledge_fusion.py        # IKF: Knowledge graph construction
├── ikf/                       # IKF 2.0 knowledge layer (pure modules + service)
│   ├── entity_resolution.py   #   canonical entities, alias seeding
│   ├── temporal.py            #   validity windows + recency decay
│   ├── claim_versioning.py    #   versioning vs true contradiction
│   ├── provenance.py          #   per-claim / per-edge provenance + merging
│   ├── evidence.py            #   evidence strength and bands
│   └── service.py             #   the only DB-aware module
├── contradiction_detector.py  # Gap & contradiction detection
├── decision_engine.py         # JEV: Action selection (hardcoded)
├── report_generator.py        # Report compilation
└── session_manager.py         # Session lifecycle
```

### 2.3 Integration Layer

```
integrations/
├── search_api.py              # Web search wrapper (Tavily, Perplexity, etc.)
├── llm_api.py                 # LLM API wrapper (Anthropic, OpenAI, etc.)
├── cache_manager.py           # Redis operations
└── error_handlers.py          # API error mapping
```

### 2.4 Database Layer

```
database/
├── models.py                  # SQLAlchemy ORM models
├── schemas.py                 # Pydantic schemas (data validation)
├── repository.py              # Data access patterns (not raw queries)
└── migrations/                # Alembic migrations
```

---

### 2.1 IKF 2.0 — the knowledge layer

`app/services/ikf/` sits on top of the V1 fusion pipeline and answers questions the
graph could not previously answer: *is this one entity or two?*, *is this a
contradiction or a fact that moved?*, *where did this edge come from?* and *how strong
is this claim, really?*

| Module | Responsibility |
|---|---|
| `entity_resolution.py` | `normalize_entity()` strips punctuation, articles and legal forms; `EntityResolver` adds a conservative similarity gate (0.90, never below four characters) bucketed by first character. `seed()` preloads aliases from long-term memory — the only way acronyms can be resolved. `merges` counts *fuzzy* merges, `aliases_absorbed` counts every surface form folded in, so the risky path is visible in telemetry. |
| `temporal.py` | `extract_validity_window()` parses ranges, quarters, months, `since`/`by` and bare years, falling back to the newest supporting source's date. `recency_score()` is exponential decay with a 540-day half-life; `temporal_relation()` decides concurrent versus ordered. |
| `claim_versioning.py` | `build_version_groups()` groups by resolved subject+predicate and marks a pair as a conflict only when the values disagree (`values_disagree()`, 2 % numeric tolerance) **and** the periods overlap. `VersionGroup.strongest` prefers better evidence, then recency. |
| `provenance.py` | `build_provenance()` collapses duplicate links and counts independent *publishers*; `to_dict()` keeps per-source detail so `merge_provenance()` can union two payloads exactly. |
| `evidence.py` | The five-factor score, its components and its bands. `EvidenceInput`/`EvidenceScore` keep the maths independent of ORM rows. |
| `service.py` | `build_knowledge_index(session_id, db, resolver, seed_aliases)` → `KnowledgeIndex` (evidence map, version groups, resolver, summary stats). Scores are derived, never stored. |

Two integration points matter:

- **The loop** builds the index once per iteration and streams `ikf_updated`; it then
drops contradiction pairs that are temporal versions, and JEV's VERIFY targets the
claim with the *thinnest* evidence in the conflicting pair rather than the first one
listed.
- **The report** recomputes the index from the rows it has already loaded (so the
report can never disagree with itself), attaches `evidence_band`/`evidence_strength`/
`evidence_components`/`independent_sources` to each claim, emits a `versions` timeline,
and orders rule-based findings by evidence instead of by extractor confidence.

## 3. Frontend Application Structure

### 3.1 Project Layout (Next.js)

```
frontend/
├── app/
│   ├── layout.tsx            # Root layout
│   ├── page.tsx              # Home page
│   ├── dashboard/
│   │   ├── page.tsx          # Main dashboard after question submit
│   │   └── [sessionId]/
│   │       ├── page.tsx      # Research session view
│   │       ├── progress.tsx  # Progress component
│   │       ├── knowledge.tsx # Knowledge graph display
│   │       └── report.tsx    # Final report display
│   └── api/
│       └── (handled by backend)
├── components/
│   ├── ResearchForm.tsx      # Question input form
│   ├── ProgressWidget.tsx    # Real-time progress display
│   ├── KnowledgeGraph.tsx    # Interactive graph visualization
│   ├── EvidenceTable.tsx     # Claims + sources table
│   ├── ContradictionView.tsx # Contradiction display
│   ├── ReportView.tsx        # Final report layout
│   └── common/
│       ├── Header.tsx
│       ├── Footer.tsx
│       ├── LoadingSpinner.tsx
│       └── ErrorBoundary.tsx
├── hooks/
│   ├── useResearchSession.ts # Session state management
│   ├── useWebSocket.ts       # Real-time updates
│   └── useFetchReport.ts     # Report fetching
├── lib/
│   ├── api.ts                # API client wrapper
│   ├── constants.ts          # App constants
│   └── utils.ts              # Utility functions
├── styles/
│   └── globals.css           # Global styles (Tailwind)
├── public/
│   └── (static assets)
├── tailwind.config.js        # Tailwind config
├── next.config.js            # Next.js config
└── tsconfig.json
```

### 3.2 Component Hierarchy

```
App
├── Header
│   └── Logo + Navigation
├── ResearchForm
│   ├── QuestionInput
│   ├── DepthSelector
│   └── SubmitButton
└── SessionView (after submit)
    ├── ProgressWidget
    │   ├── StepIndicator
    │   ├── InfoGainMeter
    │   ├── SourceCounter
    │   ├── ClaimCounter
    │   └── TimeElapsed
    ├── ControlPanel
    │   ├── PauseButton
    │   ├── StopButton
    │   └── RefreshButton
    └── ResultTabs
        ├── ReportTab
        │   ├── ExecutiveSummary
        │   ├── EvidenceTable
        │   ├── KeyFindings
        │   └── Sources
        ├── KnowledgeGraphTab
        │   └── InteractiveGraph
        ├── ContradictionsTab
        │   └── ContradictionList
        └── RawDataTab
            └── JSONExport
```

---

## 4. Data Models

### 4.1 Database Schema (PostgreSQL)

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Research Sessions
CREATE TABLE research_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    question TEXT NOT NULL,
    depth VARCHAR(20) DEFAULT 'standard',  -- basic, standard, deep
    domain VARCHAR(100),
    geographic_scope VARCHAR(100),
    time_range VARCHAR(100),
    preferred_sources TEXT[],
    max_research_time_minutes INT DEFAULT 5,
    min_sources_required INT DEFAULT 10,
    output_format VARCHAR(50) DEFAULT 'report',  -- report, graph, both
    status VARCHAR(50) DEFAULT 'initializing',  -- initializing, running, completed, error
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_research_sessions_user_id ON research_sessions(user_id);
CREATE INDEX idx_research_sessions_status ON research_sessions(status);

-- Sources
CREATE TABLE sources (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES research_sessions(id),
    url VARCHAR(2048) NOT NULL,
    title TEXT,
    source_type VARCHAR(50),  -- paper, report, news, article, etc.
    credibility_score FLOAT DEFAULT 0.5,  -- 0.0-1.0
    published_at TIMESTAMP,
    accessed_at TIMESTAMP DEFAULT NOW(),
    content TEXT,  -- Full text of source
    content_hash VARCHAR(64),  -- SHA256 hash for duplicate detection
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_sources_session_id ON sources(session_id);
CREATE INDEX idx_sources_url_hash ON sources(content_hash);

-- Claims
CREATE TABLE claims (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES research_sessions(id),
    claim TEXT NOT NULL,
    subject VARCHAR(255),  -- Entity being claimed about
    predicate VARCHAR(255),  -- Relationship type
    object TEXT,  -- Value/statement
    confidence VARCHAR(50) DEFAULT 'medium',  -- high, medium, low
    status VARCHAR(50) DEFAULT 'active',  -- active, verified, disputed, weak
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_claims_session_id ON claims(session_id);
CREATE INDEX idx_claims_subject_predicate ON claims(subject, predicate);

-- Claim-Source Links
CREATE TABLE claim_sources (
    id UUID PRIMARY KEY,
    claim_id UUID NOT NULL REFERENCES claims(id),
    source_id UUID NOT NULL REFERENCES sources(id),
    support_type VARCHAR(50) DEFAULT 'supports',  -- supports, refutes, neutral
    confidence FLOAT DEFAULT 0.8,  -- 0.0-1.0
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_claim_sources_claim_id ON claim_sources(claim_id);
CREATE INDEX idx_claim_sources_source_id ON claim_sources(source_id);

-- Knowledge Graph Nodes
CREATE TABLE knowledge_nodes (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES research_sessions(id),
    entity TEXT NOT NULL,
    entity_type VARCHAR(100),  -- person, concept, place, product, etc.
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_knowledge_nodes_session_id ON knowledge_nodes(session_id);

-- Knowledge Graph Edges
CREATE TABLE knowledge_edges (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES research_sessions(id),
    source_node_id UUID NOT NULL REFERENCES knowledge_nodes(id),
    target_node_id UUID NOT NULL REFERENCES knowledge_nodes(id),
    relationship_type VARCHAR(100),  -- is_part_of, affects, enables, etc.
    strength FLOAT DEFAULT 0.7,  -- 0.0-1.0 confidence
    supporting_claims TEXT[],  -- Array of claim IDs
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_knowledge_edges_session_id ON knowledge_edges(session_id);

-- Research Actions (for tracking research decisions)
CREATE TABLE research_actions (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES research_sessions(id),
    iteration_number INT,
    action_type VARCHAR(50),  -- SEARCH, VERIFY, EXPAND_QUERY, etc.
    query TEXT,
    result_summary TEXT,
    sources_found INT DEFAULT 0,
    new_claims_extracted INT DEFAULT 0,
    information_gain FLOAT,  -- Metric for RL training
    duration_seconds INT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_research_actions_session_id ON research_actions(session_id);

-- Decisions (for RL training data)
CREATE TABLE decisions (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES research_sessions(id),
    iteration_number INT,
    knowledge_state_summary TEXT,  -- JSON snapshot
    available_actions TEXT[],  -- SEARCH, VERIFY, EXPAND, etc.
    selected_action VARCHAR(50),
    action_reasoning TEXT,
    reward_signal FLOAT,  -- For RL training
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_decisions_session_id ON decisions(session_id);

-- Contradictions
CREATE TABLE contradictions (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES research_sessions(id),
    claim_1_id UUID NOT NULL REFERENCES claims(id),
    claim_2_id UUID NOT NULL REFERENCES claims(id),
    severity VARCHAR(50) DEFAULT 'medium',  -- low, medium, high
    resolved BOOLEAN DEFAULT FALSE,
    resolution_note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_contradictions_session_id ON contradictions(session_id);
```

### 4.2 Python Data Classes (Pydantic)

```python
# schemas/research.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ResearchQuestionInput(BaseModel):
    """User input for starting research"""
    question: str
    depth: str = "standard"  # basic, standard, deep
    domain: Optional[str] = None
    geographic_scope: Optional[str] = "global"
    time_range: Optional[str] = None
    preferred_sources: Optional[List[str]] = None
    max_research_time_minutes: int = 5
    min_sources_required: int = 10

class ResearchSessionResponse(BaseModel):
    """Response after starting research"""
    session_id: str
    question: str
    status: str
    started_at: datetime
    estimated_completion_time: int  # seconds

class ClaimModel(BaseModel):
    """Represents a single claim"""
    id: str
    claim: str
    subject: str
    predicate: str
    object: str
    confidence: str  # high, medium, low
    source_ids: List[str]

class SourceModel(BaseModel):
    """Represents a source"""
    id: str
    url: str
    title: str
    source_type: str
    credibility_score: float
    published_at: Optional[datetime]
    snippet: str  # First 200 chars of content

class EvidenceTableRow(BaseModel):
    """Row in evidence table: Claim → Source → Confidence"""
    claim: str
    primary_source: SourceModel
    confidence: str
    supporting_sources: List[SourceModel]

class KnowledgeGraphNode(BaseModel):
    """Node in knowledge graph"""
    id: str
    entity: str
    entity_type: str
    description: Optional[str]
    claim_count: int

class KnowledgeGraphEdge(BaseModel):
    """Edge in knowledge graph"""
    source_node_id: str
    target_node_id: str
    relationship_type: str
    strength: float

class ContradictionItem(BaseModel):
    """Contradiction between two claims"""
    claim_1: ClaimModel
    claim_2: ClaimModel
    severity: str  # low, medium, high
    potential_reason: str
    resolved: bool

class FinalReportResponse(BaseModel):
    """Complete research report"""
    session_id: str
    question: str
    executive_summary: str
    evidence_table: List[EvidenceTableRow]
    knowledge_graph: dict  # nodes + edges
    contradictions: List[ContradictionItem]
    remaining_unknowns: List[str]
    research_methodology: str
    total_sources: int
    total_claims: int
    iterations_performed: int
    total_time_minutes: int
    generated_at: datetime
```

---

## 5. Research Flow Diagram

### 5.1 Detailed Research Loop

```
START
  │
  ▼
┌─────────────────────────────────┐
│ Initialize Research Session     │
│ - Validate question             │
│ - Generate initial search plan  │
│ - Create DB record              │
│ - Send WebSocket: "initialized" │
└────────┬────────────────────────┘
         │
         ▼
    ┌─────────────────────────────────────┐
    │       RESEARCH ITERATION LOOP       │
    │                                     │
    │  ┌──────────────────────────────┐  │
    │  │ 1. SEARCH                    │  │
    │  │ - Generate search queries    │  │
    │  │ - Call Search API            │  │
    │  │ - Deduplicate sources        │  │
    │  │ - Store in DB                │  │
    │  └──────────────┬───────────────┘  │
    │                 │                   │
    │                 ▼                   │
    │  ┌──────────────────────────────┐  │
    │  │ 2. CLAIM EXTRACTION (IKF)    │  │
    │  │ - Call LLM to extract claims │  │
    │  │ - Subject-Predicate-Object   │  │
    │  │ - Assign confidence level    │  │
    │  │ - Link to source             │  │
    │  │ - Store in DB                │  │
    │  └──────────────┬───────────────┘  │
    │                 │                   │
    │                 ▼                   │
    │  ┌──────────────────────────────┐  │
    │  │ 3. KNOWLEDGE FUSION          │  │
    │  │ - Extract entities           │  │
    │  │ - Build/update knowledge     │  │
    │  │   graph (nodes + edges)      │  │
    │  │ - Merge duplicate claims     │  │
    │  └──────────────┬───────────────┘  │
    │                 │                   │
    │                 ▼                   │
    │  ┌──────────────────────────────┐  │
    │  │ 4. DETECT GAPS &             │  │
    │  │    CONTRADICTIONS            │  │
    │  │ - Find missing entities      │  │
    │  │ - Find opposing claims       │  │
    │  │ - Identify weak evidence     │  │
    │  │ - Store contradiction record │  │
    │  └──────────────┬───────────────┘  │
    │                 │                   │
    │                 ▼                   │
    │  ┌──────────────────────────────┐  │
    │  │ 5. DECISION ENGINE (JEV)     │  │
    │  │ - Evaluate knowledge state   │  │
    │  │ - Hardcoded rules (v1):      │  │
    │  │   * Has contradictions?      │  │
    │  │     → VERIFY                 │  │
    │  │   * Coverage < 65%?          │  │
    │  │     → SEARCH                 │  │
    │  │   * Has gaps?                │  │
    │  │     → EXPAND_QUERY           │  │
    │  │   * Else → STOP              │  │
    │  │ - Log decision (for RL)      │  │
    │  └──────────────┬───────────────┘  │
    │                 │                   │
    │   ┌─────────────┴─────────────┐    │
    │   │                           │    │
    │   ▼ (if STOP condition)       │    │
    │ [Exit loop]               [Continue] (if SEARCH/VERIFY/EXPAND)
    │                               │    │
    │                               ▼    │
    │                         [Back to 1] │
    │                                     │
    └─────────────────────────────────────┘
         │
         ▼ (after STOP)
┌─────────────────────────────────┐
│ 6. GENERATE REPORT              │
│ - Compile executive summary     │
│ - Build evidence table          │
│ - Serialize knowledge graph     │
│ - List contradictions           │
│ - Note unknowns                 │
│ - Format citations              │
│ - Store final report in DB      │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 7. SEND RESULTS TO CLIENT       │
│ - WebSocket: "completed"        │
│ - Return session ID + report ID │
│ - Client fetches full report    │
└────────┬────────────────────────┘
         │
         ▼
       END
```

---

## 6. Technology Stack

### Backend

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Framework** | FastAPI (Python 3.11+) | REST API, async support, auto-docs |
| **Database** | PostgreSQL 14+ | Persistent storage, transactions |
| **Vector DB** | pgvector (PostgreSQL extension) | Embeddings for similarity search (future) |
| **ORM** | SQLAlchemy 2.0 | Database abstraction |
| **Cache** | Redis 7+ | Session management, caching |
| **Async Worker** | Celery + Redis | Long-running research tasks |
| **LLM API** | Anthropic / OpenAI | Claim extraction, reasoning |
| **Search API** | Tavily / Perplexity / Google | Web search results |
| **Validation** | Pydantic v2 | Request/response validation |
| **Logging** | Python logging + Sentry | Error tracking |
| **Testing** | pytest + pytest-asyncio | Unit & integration tests |
| **Code Quality** | Black + ruff + mypy | Linting, formatting, type-checking |

### Frontend

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Framework** | Next.js 14+ | React framework, SSR |
| **Language** | TypeScript | Type safety |
| **Styling** | Tailwind CSS | Utility-first CSS |
| **UI Components** | shadcn/ui + Radix | Pre-built accessible components |
| **State Management** | React Context + custom hooks | Session/global state |
| **Real-time** | WebSocket (SockJS fallback) | Live progress updates |
| **Charts/Graphs** | Vis.js or Cytoscape.js | Knowledge graph visualization |
| **Data Tables** | TanStack Table | Evidence table with sorting/filtering |
| **Forms** | React Hook Form + Zod | Form validation |
| **HTTP Client** | TanStack Query (React Query) | API data fetching + caching |
| **Testing** | Vitest + React Testing Library | Component & e2e tests |
| **Deployment** | Vercel | Frontend hosting |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Container** | Docker | Application containerization |
| **Orchestration** | Docker Compose (dev) / K8s (prod) | Service orchestration |
| **Backend Hosting** | Railway / Render / AWS ECS | FastAPI deployment |
| **Database Hosting** | Supabase / AWS RDS | PostgreSQL managed service |
| **Cache Hosting** | Redis Cloud / AWS ElastiCache | Redis managed service |
| **Monitoring** | Datadog / New Relic | Uptime & performance monitoring |
| **Error Tracking** | Sentry | Exception and error logging |
| **CI/CD** | GitHub Actions | Automated testing & deployment |

---

## 7. Deployment Architecture

### 7.1 Development Environment

```
Local machine
├── Docker Compose
│   ├── FastAPI (port 8000)
│   ├── PostgreSQL (port 5432)
│   ├── Redis (port 6379)
│   └── Next.js dev server (port 3000)
├── Environment variables (.env.local)
└── Database migrations (Alembic)
```

### 7.2 Production Environment

```
Frontend (Vercel)
├── Next.js app (SSR)
├── CDN distribution
└── Auto-scaling

API Gateway (AWS / Render)
└── FastAPI backend
    └── Gunicorn + Uvicorn workers

PostgreSQL (Supabase / AWS RDS)
├── Read replica (optional)
└── Automated backups

Redis (Redis Cloud)
├── Session store
└── Cache layer

Monitoring & Logging
├── Sentry (error tracking)
├── Datadog (APM)
└── CloudWatch (logs)
```

### 7.3 Scaling Considerations (Future)

- **Horizontal scaling**: Multiple FastAPI instances behind load balancer
- **Task queue**: Celery for long-running research tasks
- **Database optimization**: Connection pooling, query optimization
- **Cache warming**: Pre-fetch common research patterns
- **CDN**: Cache static assets globally

---

## 8. Folder Structure (Complete)

```
self-correcting-research-agent/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app initialization
│   │   ├── config.py                  # Settings (pydantic-settings)
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── research.py        # POST/GET research endpoints
│   │   │   │   ├── sessions.py        # Session CRUD
│   │   │   │   ├── knowledge.py       # Knowledge graph endpoints
│   │   │   │   ├── evidence.py        # Evidence table endpoints
│   │   │   │   └── reports.py         # Report generation endpoints
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── research.py        # Request/response models
│   │   │   │   ├── claim.py
│   │   │   │   ├── source.py
│   │   │   │   ├── knowledge.py
│   │   │   │   └── session.py
│   │   │   ├── dependencies.py        # Shared dependencies
│   │   │   └── errors.py              # Custom exceptions
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── research_orchestrator.py    # Main research loop
│   │   │   ├── search_agent.py             # Search wrapper
│   │   │   ├── claim_extractor.py          # LLM claim extraction
│   │   │   ├── knowledge_fusion.py         # IKF: Knowledge graph
│   │   │   ├── ikf/                        # IKF 2.0 (entity_resolution, temporal,
│   │   │   │                               #   claim_versioning, provenance, evidence, service)
│   │   │   ├── contradiction_detector.py   # Gap & contradiction
│   │   │   ├── decision_engine.py          # JEV: Action selection
│   │   │   ├── report_generator.py         # Report compilation
│   │   │   ├── session_manager.py          # Session lifecycle
│   │   │   ├── knowledge_graph_builder.py # Graph construction
│   │   │   └── metrics.py                  # Logging metrics
│   │   │
│   │   ├── integrations/
│   │   │   ├── __init__.py
│   │   │   ├── search_api.py          # Web search wrapper
│   │   │   ├── llm_api.py             # LLM API wrapper
│   │   │   ├── cache_manager.py       # Redis operations
│   │   │   └── error_handlers.py      # Error mapping
│   │   │
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── models.py              # SQLAlchemy models
│   │   │   ├── schemas.py             # Pydantic schemas
│   │   │   ├── repository.py          # Data access patterns
│   │   │   ├── session.py             # DB session management
│   │   │   └── migrations/
│   │   │       └── alembic.ini
│   │   │
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── logger.py              # Logging setup
│   │   │   ├── validators.py          # Input validation
│   │   │   ├── parsers.py             # HTML/text parsing
│   │   │   └── helpers.py             # Utility functions
│   │   │
│   │   └── ws/
│   │       ├── __init__.py
│   │       └── managers.py            # WebSocket connection manager
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py                # Pytest fixtures
│   │   ├── test_search_agent.py
│   │   ├── test_claim_extractor.py
│   │   ├── test_knowledge_fusion.py
│   │   ├── test_decision_engine.py
│   │   └── test_report_generator.py
│   │
│   ├── requirements.txt               # Python dependencies
│   ├── requirements-dev.txt           # Dev dependencies
│   ├── Dockerfile
│   ├── .env.example
│   └── README.md
│
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                 # Root layout
│   │   ├── page.tsx                   # Single-page shell: home / research / settings / about
│   │   └── globals.css                # Design-system tokens + sidebar/menu rules
│   │
│   ├── components/                    # no hooks/ directory — state lives in components/lib
│   │   ├── research/
│   │   │   ├── ResearchForm.tsx
│   │   │   ├── ResearchDashboard.tsx  # live run + report view
│   │   │   ├── ReportView.tsx         # reading view + PDF export
│   │   │   ├── DashboardStats.tsx     # metric cards + budget meter
│   │   │   ├── SessionHistory.tsx     # left-menu history list
│   │   │   ├── FacetCoveragePanel.tsx # per-dimension coverage (adaptive planner UI)
│   │   │   └── KnowledgeGraphView.tsx # vis-network rendering
│   │   │
│   │   ├── layout/
│   │   │   └── Sidebar.tsx            # nav + history + Hide-menu action
│   │   │
│   │   ├── panels/
│   │   │   ├── SettingsPanel.tsx      # appearance + default depth + connection
│   │   │   └── AboutPanel.tsx         # what-this-is + current capabilities
│   │   │
│   │   └── ui/
│   │       ├── ActivityFeed.tsx
│   │       ├── StatusBadge.tsx
│   │       ├── Progress.tsx
│   │       ├── Skeleton.tsx
│   │       ├── InfoCard.tsx
│   │       └── ThemeToggle.tsx        # legacy: superseded by the Settings theme control
│   │
│   ├── lib/
│   │   ├── api.ts                     # Authenticated REST + WS client
│   │   ├── types.ts                   # Domain TypeScript types
│   │   ├── useResearchSocket.ts       # WS + replay merge logic
│   │   ├── timeline.ts                # live + persisted event ordering
│   │   ├── pdf.ts                     # client-side report export
│   │   ├── facets.ts                  # facet-domain helpers (+ facets.test.ts)
│   │   ├── preferences.ts             # persisted theme + default depth
│   │   └── theme-script.ts            # no-flash pre-paint theme bootstrap
│   │
│   ├── .env.local
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   └── postcss.config.mjs
│
├── docker-compose.yml                 # Local dev environment
├── Dockerfile                         # For backend
├── .github/
│   └── workflows/
│       ├── test.yml                   # CI tests
│       └── deploy.yml                 # CD deployment
├── docs/
│   ├── API.md                         # API documentation
│   ├── DEPLOYMENT.md
│   ├── CONTRIBUTING.md
│   └── ARCHITECTURE.md
├── .gitignore
├── .env.example
└── README.md                          # Project overview
```

---

## 9. Frontend layout and navigation

The app is a single Next.js page (`app/page.tsx`) with four views: **New research**, **Investigation**, **Settings**, **About**. A left sidebar holds the section navigation, the past-investigations list, and a **Hide menu** action.

The menu button is the only way to reopen the sidebar and it sits at the **top-right** of the header. It is on screen exactly while the menu is hidden, so pressing it always reveals the menu and can never look like a dead control. Two independent pieces of state drive this: `navOpen` for the drawer and `navCollapsed` for the desktop panel. Above 1024px the sidebar is part of the layout and `.app-shell.nav-collapsed .sidebar { display: none }` hands the freed width to the main column; at 1024px and below it becomes an off-canvas drawer (`translateX(-100%)` with `visibility: hidden`, which also keeps the closed drawer out of the tab order) that slides in over a backdrop. `matchMedia("(max-width: 1024px)")` is consulted at click time to decide which of the two the reader meant, so one button serves both layouts.

Theme control lives in **Appearance** inside Settings, not in the header. Settings holds **Appearance** (light / dark / match system), **Default research depth** (quick / standard / deep, persisted and preselected on the new-research form) and **Connection** (API base URL, live `/health` probe with a re-check button, and a link to the API docs). The About panel lists what the agent can do today: adaptive facet-aware planning, negative-result query caching, one-click synthesis retry, per-session LLM budgets, durable session-event replay, and versioned evidence in the report.

## 10. API Endpoints

### Research Management

```
POST /api/research/start
  Request: { question, depth, domain, ... }
  Response: { session_id, status, estimated_time }

GET /api/research/{session_id}
  Response: { session_id, question, status, progress, ... }

GET /api/research/{session_id}/status
  Response: { status, current_step, iteration, sources_count, claims_count }

POST /api/research/{session_id}/stop
  Response: { session_id, status: "stopped" }

POST /api/research/{session_id}/pause
  Response: { session_id, status: "paused" }
```

### Report & Knowledge

```
GET /api/research/{session_id}/report
  Response: Full report object (JSON)

GET /api/research/{session_id}/knowledge
  Response: { nodes: [...], edges: [...] }

GET /api/research/{session_id}/evidence
  Response: { claims: [...], sources: [...] }

GET /api/research/{session_id}/contradictions
  Response: { contradictions: [...] }
```

### WebSocket

```
WebSocket /ws/{session_id}
  Messages (client ← server):
  - { type: "progress", iteration: 3, step: "claim extraction", ... }
  - { type: "sources_found", count: 12 }
  - { type: "claims_extracted", count: 24 }
  - { type: "completed", report_id: "..." }
  - { type: "error", message: "..." }
```

---

## 11. Error Handling Strategy

### Error Categories

| Type | Example | Handling |
|------|---------|----------|
| **Search API fails** | Rate limit / timeout | Retry with exponential backoff, use cached results |
| **LLM API fails** | Token limit / service down | Fallback to heuristic extraction, log for manual review |
| **DB connection fails** | DB unreachable | Graceful degradation, inform user, queue for retry |
| **Malformed input** | Invalid question | Return 400 with helpful error message |
| **Session not found** | Unknown session ID | Return 404 |
| **Research timeout** | >10 min elapsed | Stop gracefully, return partial results |
| **Bad source content** | Unparseable HTML | Skip source, continue research |

### Error Recovery

```python
# Example: Search API retry with exponential backoff
async def search_with_retry(query, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await search_api.search(query)
        except SearchAPIError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"Search failed after {max_retries} retries: {query}")
                raise  # Last attempt failed, propagate error
```

---

## 12. Concurrency & Performance

### Backend Concurrency

- **FastAPI async/await**: All I/O operations (API calls, DB, Redis) are async
- **Worker pool**: Celery + Redis for compute-heavy tasks (NLP, graph construction)
- **Database connections**: SQLAlchemy with async support + connection pooling
- **Rate limiting**: Built-in rate limiter on search API calls

### Frontend Optimization

- **Code splitting**: Next.js automatic route-based splitting
- **Image optimization**: Next.js Image component with lazy loading
- **Caching**: React Query for HTTP caching + browser cache
- **Incremental Static Regeneration (ISR)**: Cache reports after generation

---

## 13. Security Considerations

- **Input validation**: All user inputs validated via Pydantic
- **API keys**: Stored in environment variables, never committed
- **CORS**: Restrict to frontend domain
- **Rate limiting**: Prevent abuse via request throttling
- **SQL injection**: SQLAlchemy parameterized queries prevent injection
- **XSS prevention**: React escapes content by default
- **Authentication**: JWT tokens (post-V1)
- **HTTPS only**: All API communication encrypted

---

## 14. Monitoring & Observability

### Logging

```python
# Structured logging with context
logger.info(
    "research_iteration_completed",
    extra={
        "session_id": session_id,
        "iteration": 3,
        "claims_extracted": 7,
        "new_claims": 5,
        "information_gain": 0.71
    }
)
```

### Metrics to Track

- Session completion rate (%)
- Average time per iteration (seconds)
- Sources per session
- Claims per session
- Contradiction detection rate
- Error rate by endpoint
- API latency (search, LLM)
- Database query latency

### Alerts

- Session timeout (>10 min)
- Search API failures (>3 retries)
- LLM API degradation (slow response)
- Database connection pool exhausted
- Redis out of memory
- High error rate (>5% of requests)

---

**Document Version:** 2.1  
**Last Updated:** October 2, 2026  
**Owner:** MASTER  
**Status:** V1 complete · V2 offline-learning layer, long-term memory and V2 frontend shipped · adaptive model router remaining.

---

## V2 Learning Layer (shipped 2026-10-02)

JEV remains the live decision maker. The learning layer sits beside the loop and
never replaces it; every failure inside it is swallowed and logged (`never break a
run` contract), and the research loop cannot tell whether the layer is healthy or
absent.

```
RESEARCH LOOP (JEV controls)
   │  decision + execution
   ├──▶ TrajectoryRecorder (services/rl/recorder.py)
   │       ├─ transition per iteration → research_transitions
   │       ├─ reward components (services/rl/rewards.py)
   │       └─ shadow prediction → rl_predictions  (logged, NEVER executed)
   │
   ├──▶ memory versioning (services/memory/versions.py) → long_term_memories
   │
   └──▶ events: transition_recorded, rl_shadow, memory_recalled, memory_updated

OFFLINE (no live impact)
   research_transitions ──▶ build_dataset (rl/dataset.py) ──▶ JSONL
        └──▶ TabularPolicy.train (rl/policy.py) ──▶ rl_policies
                  └──▶ evaluate (rl/evaluation.py) ──▶ evaluation_runs/results
                            └──▶ JEV vs RL metrics → /api/evaluation/*
```

Components:

- **ResearchState** (`rl/research_state.py`) — frozen, deterministic, JSON
  round-trippable aggregate of iteration, coverage, gaps, contradictions, budgets
  and the previous action/reward; `state_hash()`/`state_key()` for dedupe,
  `state_bytes` stays in the hundreds (no raw source content ever stored).
- **Action space** (`rl/actions.py`) — `SEARCH`/`VERIFY`/`EXPAND_QUERY`/`STOP` are
  executable; `SEARCH_NEW_FACET`, `SEARCH_PRIMARY_SOURCE`, `SEARCH_RECENT_SOURCE`,
  `SEARCH_COUNTER_EVIDENCE`, `COMPARE_SOURCES`, `REVISIT_WEAK_CLAIM` are declared
  with `executable=False` so a future executor shares one vocabulary.
- **Reward** (`rl/rewards.py`) — named components (`information_gain_reward`,
  `evidence_quality_reward`, `coverage_gain_reward`, `contradiction_resolution_reward`,
  `source_diversity_reward` minus redundancy / low-quality-source / unnecessary-action /
  time / budget / unresolved-contradiction penalties). With only V1 terms present it
  reproduces the V1 signal exactly (`total == v1_reward`); `explain_components()`
  powers the UI's reward explanation.
- **Dataset** (`rl/dataset.py`) — validated `state/action/reward/next_state/done`
  records, dedupe, iteration-order checks, incomplete-session filtering, JSONL
  import/export; `DATASET_VERSION = "v2.0"`.
- **History backfill** (`rl/service.backfill_history`) — reconstructs transitions
  for completed sessions that predate the recorder by replaying stored
  decisions/sources/claims through `compute_reward_components`. It encodes V1
  decision semantics: the run opens with an unconditional SEARCH whose outcome is
  the state *before* decision 1; decision *k* is logged at the end of iteration *k*
  and selects the action executed in iteration *k+1*; the terminal STOP executes
  nothing. Idempotent, per-session fault-isolated, and flagged in the observation
  (`backfilled`, `reconstructed_from`); verified against the dev DB — 8 sessions →
  31 clean transitions, 0 validator drops — and exposed via
  `POST /api/evaluation/dataset/backfill` plus a `backfill` flag on dataset build.
- **Policy** (`rl/policy.py`) — `ActionPolicy` protocol; `JevPolicy` baseline;
  `TabularPolicy` = contextual Monte-Carlo action values over discretised state
  features with Bayesian shrinkage (default 2.0), defers to JEV below 10 samples,
  tie-breaks by JEV priority. Deliberately *not* deep RL; the protocol is the seam
  a future PyTorch policy would implement without touching the loop.
- **Evaluation** (`rl/evaluation.py`) — replays historical states; honestly splits
  observed vs counterfactual vs unestimable steps and attaches notes, per-session and
  per-action slices with sample sizes.

New tables (migration `002_learning_layer`): `research_transitions`, `rl_policies`,
`rl_predictions`, `evaluation_runs`, `evaluation_results`. New endpoints live under
`/api/research/{id}/trajectory|decisions|predictions|state` and
`/api/evaluation/*`; all inherit the existing API-key auth, rate limits and error
envelope.
