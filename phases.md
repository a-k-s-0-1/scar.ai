# Development Phases: Self-Correcting Research Agent MVP V1

## Overview

This document breaks V1 development into **5 phases** of increasing complexity. Each phase builds a complete, testable feature that works end-to-end. By the end of Phase 5, you have a shipping MVP.

**Total Estimated Timeline:** 8-12 weeks (depending on team size and experience)

---

## Phase 1: Foundation & Infrastructure (Weeks 1-2)

### Goal
Set up the development environment, database schema, and basic API structure. By the end of this phase, you can:
- Start a research session
- Store sessions in the database
- Retrieve session status
- Deploy locally with Docker Compose

### Deliverables

#### Backend Setup
- [x] FastAPI app with basic project structure
- [x] PostgreSQL database with initial schema
- [x] SQLAlchemy ORM setup with models
- [x] Pydantic schemas for request/response validation
- [x] Basic error handling middleware
- [x] API documentation (OpenAPI/Swagger)
- [x] Environment variable configuration

#### Frontend Setup
- [x] Next.js 14+ project with TypeScript
- [x] Basic layout and navigation
- [x] Simple research form component
- [x] API client wrapper
- [x] Tailwind CSS configured

#### Infrastructure
- [x] Docker Compose with FastAPI, PostgreSQL, Redis
- [x] Development database setup
- [x] Environment variables (.env.example)
- [x] Basic CI with GitHub Actions (linting, type checks)

### Key Tasks

**Backend (3-5 days)**
```python
# app/main.py - Basic FastAPI app
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Research Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

# database/models.py - Core models
from sqlalchemy import Column, String, Timestamp, UUID
from datetime import datetime

class ResearchSession(Base):
    __tablename__ = "research_sessions"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    user_id = Column(UUID, nullable=False)
    question = Column(String, nullable=False)
    status = Column(String, default="initializing")
    created_at = Column(Timestamp, default=datetime.utcnow)
    completed_at = Column(Timestamp, nullable=True)

# api/routes/research.py - Session creation endpoint
@app.post("/api/research/start", response_model=ResearchSessionResponse)
async def start_research(request: ResearchQuestionInput):
    session = await create_session(request.question)
    return ResearchSessionResponse(
        session_id=str(session.id),
        status="initializing",
        estimated_completion_time=300
    )

@app.get("/api/research/{session_id}")
async def get_session(session_id: str):
    session = await fetch_session(session_id)
    return ResearchSessionResponse.from_orm(session)
```

**Frontend (2-3 days)**
```tsx
// app/page.tsx
export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800">
      <Header />
      <ResearchForm />
    </main>
  );
}

// components/forms/ResearchForm.tsx
export function ResearchForm() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    
    const response = await fetch("/api/research/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });
    
    const data = await response.json();
    router.push(`/dashboard/${data.session_id}`);
  };
  
  return (
    <form onSubmit={handleSubmit}>
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask your research question..."
        className="w-full p-4 rounded-lg border border-slate-600"
      />
      <button type="submit" disabled={loading}>
        Start Research
      </button>
    </form>
  );
}
```

### Testing
- [x] API endpoint tests: Create session, retrieve session
- [x] Database tests: Insert/fetch sessions
- [x] Component tests: ResearchForm renders, accepts input
- [x] Integration test: Submit form → create session → redirect

### Acceptance Criteria
- ✅ POST /api/research/start returns valid session ID
- ✅ GET /api/research/{id} returns session details
- ✅ Frontend form submits and redirects to session page
- ✅ Docker Compose starts all services without errors
- ✅ All tests pass
- ✅ Code formatted (black, prettier)
- ✅ No TypeScript errors

---

## Phase 2: Search & Source Collection (Weeks 3-4)

### Goal
Integrate with search API, collect sources, and display progress. By the end:
- Research session executes first search
- Sources are fetched and stored
- Progress updates stream to frontend in real-time
- Multiple search queries can be generated

### Deliverables

#### Backend
- [x] Search API wrapper (Tavily/Perplexity)
- [x] Source model and storage
- [x] Search execution in research loop
- [x] WebSocket connection manager for real-time updates
- [x] Duplicate source detection
- [x] Credibility score estimation

#### Frontend
- [x] SessionView component with tabs
- [x] ProgressWidget with iteration counter
- [x] WebSocket hook for live updates
- [x] Source list display
- [x] Real-time meter: sources found, time elapsed

#### Integration
- [x] Research orchestrator creates search tasks
- [x] One complete iteration (search only) works end-to-end
- [x] Database stores all search results
- [x] Error recovery for search API failures

### Key Tasks

**Backend (4-6 days)**
```python
# integrations/search_api.py
from typing import List
import aiohttp

class SearchAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = None
    
    async def search(self, query: str, max_results: int = 10) -> List[dict]:
        """Search using Tavily or Perplexity API."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tavily.com/search",
                json={"api_key": self.api_key, "query": query}
            ) as resp:
                data = await resp.json()
                return data.get("results", [])

# services/search_agent.py
class SearchAgent:
    def __init__(self, search_api: SearchAPI):
        self.search_api = search_api
        self.queries_used = 0
        self.max_queries = 50
        self.seen_urls = set()
    
    async def search(self, query: str) -> List[Source]:
        """Execute search and deduplicate results."""
        if self.queries_used >= self.max_queries:
            raise RateLimitExceededError(f"Exceeded {self.max_queries} queries")
        
        results = await self.search_api.search(query)
        
        sources = []
        for result in results:
            if result["url"] not in self.seen_urls:
                source = Source(
                    url=result["url"],
                    title=result.get("title", ""),
                    content=result.get("content", ""),
                    credibility_score=self.estimate_credibility(result)
                )
                sources.append(source)
                self.seen_urls.add(result["url"])
        
        self.queries_used += 1
        return sources
    
    def estimate_credibility(self, result: dict) -> float:
        """Simple credibility scoring."""
        score = 0.5
        
        # Boost academic sources
        if ".edu" in result["url"] or "arxiv" in result["url"]:
            score += 0.2
        
        # Boost government sources
        if ".gov" in result["url"]:
            score += 0.2
        
        # Reduce social media, forums
        if any(x in result["url"] for x in ["reddit", "twitter", "facebook"]):
            score -= 0.1
        
        return min(max(score, 0.0), 1.0)

# services/research_orchestrator.py
class ResearchOrchestrator:
    def __init__(self, search_agent: SearchAgent, db: Database):
        self.search_agent = search_agent
        self.db = db
    
    async def execute_iteration(self, session_id: str) -> IterationResult:
        """Execute one research iteration: search → store → decide."""
        session = await self.db.get_session(session_id)
        
        # Step 1: Generate search query
        query = self.generate_search_query(session.question)
        
        # Step 2: Search
        sources = await self.search_agent.search(query)
        
        # Step 3: Store sources
        for source in sources:
            source.session_id = session_id
            await self.db.store_source(source)
        
        return IterationResult(
            sources_found=len(sources),
            claims_extracted=0,  # TODO: Phase 3
            next_action="SEARCH"
        )
    
    def generate_search_query(self, question: str) -> str:
        """Generate first search query from question."""
        # Simple heuristic: use first 5-7 words
        words = question.split()[:7]
        return " ".join(words)

# ws/managers.py
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket
    
    def disconnect(self, session_id: str):
        del self.active_connections[session_id]
    
    async def broadcast(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(message)

# api/routes/research.py (updated)
manager = ConnectionManager()

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(session_id: str, websocket: WebSocket):
    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
    except WebSocketDisconnect:
        manager.disconnect(session_id)
```

**Frontend (3-5 days)**
```tsx
// hooks/useWebSocket.ts
export function useWebSocket(sessionId: string) {
  const [messages, setMessages] = useState<any[]>([]);
  
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);
    
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      setMessages(prev => [...prev, message]);
    };
    
    return () => ws.close();
  }, [sessionId]);
  
  return messages;
}

// components/session/ProgressWidget.tsx
interface ProgressWidgetProps {
  sessionId: string;
}

export function ProgressWidget({ sessionId }: ProgressWidgetProps) {
  const messages = useWebSocket(sessionId);
  const [iteration, setIteration] = useState(0);
  const [sourcesFound, setSourcesFound] = useState(0);
  const [startTime] = useState(Date.now());
  
  useEffect(() => {
    messages.forEach(msg => {
      if (msg.type === "iteration_complete") {
        setIteration(msg.iteration);
        setSourcesFound(msg.sources_found);
      }
    });
  }, [messages]);
  
  const elapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
  
  return (
    <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
      <h3 className="text-lg font-semibold mb-4">Research Progress</h3>
      
      <div className="space-y-4">
        <div>
          <label className="text-sm text-slate-400">Iteration</label>
          <p className="text-2xl font-bold">{iteration}</p>
        </div>
        
        <div>
          <label className="text-sm text-slate-400">Sources Found</label>
          <p className="text-2xl font-bold">{sourcesFound}</p>
        </div>
        
        <div>
          <label className="text-sm text-slate-400">Time Elapsed</label>
          <p className="text-2xl font-bold">{elapsedSeconds}s</p>
        </div>
      </div>
    </div>
  );
}

// app/dashboard/[sessionId]/page.tsx
export default function SessionPage({ params }: { params: { sessionId: string } }) {
  return (
    <div className="grid grid-cols-3 gap-6 p-8">
      <div className="col-span-1">
        <ProgressWidget sessionId={params.sessionId} />
      </div>
      
      <div className="col-span-2">
        <SourceList sessionId={params.sessionId} />
      </div>
    </div>
  );
}
```

### Testing
- [x] Search API wrapper: Mock API, verify parsing
- [x] SearchAgent: Deduplication works, credibility scoring
- [x] WebSocket: Connections manage, messages send correctly
- [x] End-to-end: Submit question → search executes → progress updates

### Acceptance Criteria
- ✅ Search query generated from question
- ✅ Sources fetched and stored in database
- ✅ Duplicate sources are filtered out
- ✅ Credibility score assigned to each source
- ✅ WebSocket sends progress updates in real-time
- ✅ Frontend displays sources and progress
- ✅ Error handling: Search API timeout → retry
- ✅ Rate limiting enforced (max 50 queries)

---

## Phase 3: Claim Extraction & IKF (Weeks 5-6)

### Goal
Extract structured claims from sources, build knowledge graph (IKF layer). By the end:
- LLM extracts claims from source content
- Claims stored with confidence levels
- Knowledge graph built from claims
- Entities and relationships tracked

### Deliverables

#### Backend
- [x] Claim extraction service (LLM-based)
- [x] Claim model and storage
- [x] Knowledge node/edge models
- [x] Knowledge graph builder (IKF)
- [x] Entity extraction and linking
- [x] Prompt engineering for claim extraction

#### Frontend
- [x] Knowledge graph visualization component
- [x] Evidence table: Claims → Sources → Confidence
- [x] Claim detail view with source links
- [x] Graph interaction (pan, zoom, filter)

#### Integration
- [x] Two complete iterations work: search → extract → fuse
- [x] Claims linked to sources
- [x] Knowledge graph updates per iteration

### Key Tasks

**Backend (5-7 days)**
```python
# services/claim_extractor.py
from anthropic import Anthropic

class ClaimExtractor:
    def __init__(self, llm_client: Anthropic):
        self.llm = llm_client
    
    async def extract(self, sources: List[Source]) -> List[Claim]:
        """Extract claims from sources using LLM."""
        claims = []
        
        for source in sources:
            # Skip if content too long (token limit)
            if len(source.content) > 5000:
                content = source.content[:5000]
            else:
                content = source.content
            
            prompt = self._build_prompt(content)
            
            try:
                response = await self.llm.messages.create(
                    model="claude-3-haiku",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                claims_json = json.loads(response.content[0].text)
                
                for claim_data in claims_json:
                    claim = Claim(
                        subject=claim_data["subject"],
                        predicate=claim_data["predicate"],
                        object=claim_data["object"],
                        confidence=claim_data["confidence"],
                        source_id=source.id
                    )
                    claims.append(claim)
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse claims from {source.url}: {e}")
                continue
            except Exception as e:
                logger.error(f"Claim extraction failed for {source.url}: {e}")
                continue
        
        return claims
    
    def _build_prompt(self, content: str) -> str:
        return f"""Extract factual claims from this text.

Return ONLY a JSON array with this structure:
[
  {{
    "claim": "Complete claim statement",
    "subject": "Entity being claimed about",
    "predicate": "Relationship or property",
    "object": "Value or target",
    "confidence": "high|medium|low"
  }}
]

TEXT:
{content}

Return ONLY valid JSON, no other text."""

# models.py (updated)
from sqlalchemy import ForeignKey, Float

class Claim(Base):
    __tablename__ = "claims"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    session_id = Column(UUID, ForeignKey("research_sessions.id"))
    subject = Column(String)
    predicate = Column(String)
    object = Column(String)
    confidence = Column(String)  # high, medium, low
    source_id = Column(UUID, ForeignKey("sources.id"))
    
class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    session_id = Column(UUID, ForeignKey("research_sessions.id"))
    entity = Column(String)
    entity_type = Column(String)
    description = Column(String, nullable=True)

class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    session_id = Column(UUID, ForeignKey("research_sessions.id"))
    source_node_id = Column(UUID, ForeignKey("knowledge_nodes.id"))
    target_node_id = Column(UUID, ForeignKey("knowledge_nodes.id"))
    relationship_type = Column(String)
    strength = Column(Float, default=0.7)

# services/knowledge_fusion.py
class KnowledgeFusion:
    """IKF: Knowledge Fusion Layer"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def fuse(self, session_id: str, claims: List[Claim]):
        """Fuse claims into knowledge graph."""
        # Step 1: Extract entities (subjects and objects become nodes)
        await self._extract_entities(session_id, claims)
        
        # Step 2: Create relationships (predicates become edges)
        await self._extract_relationships(session_id, claims)
        
        # Step 3: Merge duplicates
        await self._merge_duplicate_nodes(session_id)
    
    async def _extract_entities(self, session_id: str, claims: List[Claim]):
        """Extract unique entities from claims."""
        entities = {}
        
        for claim in claims:
            # Subject is an entity
            if claim.subject not in entities:
                entities[claim.subject] = "concept"
            
            # Object is an entity (if it looks like one)
            if not claim.object.startswith("$") and len(claim.object) < 100:
                if claim.object not in entities:
                    entities[claim.object] = "concept"
        
        # Store nodes
        for entity, entity_type in entities.items():
            node = KnowledgeNode(
                session_id=session_id,
                entity=entity,
                entity_type=entity_type
            )
            await self.db.store_node(node)
    
    async def _extract_relationships(self, session_id: str, claims: List[Claim]):
        """Extract relationships from claims."""
        for claim in claims:
            # Get nodes
            source_node = await self.db.get_node(session_id, claim.subject)
            target_node = await self.db.get_node(session_id, claim.object)
            
            if source_node and target_node:
                # Confidence maps to strength
                strength_map = {"high": 0.9, "medium": 0.7, "low": 0.4}
                strength = strength_map.get(claim.confidence, 0.5)
                
                edge = KnowledgeEdge(
                    session_id=session_id,
                    source_node_id=source_node.id,
                    target_node_id=target_node.id,
                    relationship_type=claim.predicate,
                    strength=strength
                )
                await self.db.store_edge(edge)
    
    async def _merge_duplicate_nodes(self, session_id: str):
        """Merge nodes that refer to the same concept."""
        # Simple approach: exact match merge
        # (Advanced: use embedding similarity in V2)
        nodes = await self.db.get_nodes(session_id)
        
        seen = {}
        for node in nodes:
            normalized = node.entity.lower().strip()
            if normalized in seen:
                # Merge: redirect edges to canonical node
                canonical = seen[normalized]
                await self._redirect_edges(session_id, node.id, canonical.id)
                await self.db.delete_node(node.id)
            else:
                seen[normalized] = node

# services/research_orchestrator.py (updated)
class ResearchOrchestrator:
    def __init__(
        self,
        search_agent: SearchAgent,
        claim_extractor: ClaimExtractor,
        knowledge_fusion: KnowledgeFusion,
        db: Database
    ):
        self.search_agent = search_agent
        self.claim_extractor = claim_extractor
        self.knowledge_fusion = knowledge_fusion
        self.db = db
    
    async def execute_iteration(self, session_id: str) -> IterationResult:
        """Execute one iteration: search → extract → fuse."""
        session = await self.db.get_session(session_id)
        iteration = session.iterations + 1
        
        # Step 1: Search
        query = self.generate_search_query(session.question, iteration)
        sources = await self.search_agent.search(query)
        
        for source in sources:
            source.session_id = session_id
            await self.db.store_source(source)
        
        # Step 2: Extract claims
        claims = await self.claim_extractor.extract(sources)
        
        for claim in claims:
            claim.session_id = session_id
            await self.db.store_claim(claim)
        
        # Step 3: Fuse into knowledge graph
        await self.knowledge_fusion.fuse(session_id, claims)
        
        return IterationResult(
            iteration=iteration,
            sources_found=len(sources),
            claims_extracted=len(claims),
            next_action="SEARCH"  # TODO: Phase 4 (decision engine)
        )
    
    def generate_search_query(self, question: str, iteration: int) -> str:
        """Generate search query that evolves per iteration."""
        base = question
        
        if iteration == 1:
            return base  # Use question directly
        elif iteration == 2:
            return f"{base} recent studies"
        elif iteration == 3:
            return f"{base} economic impact"
        else:
            return f"{base} government policy"
```

**Frontend (2-3 days)**
```tsx
// components/report/KnowledgeGraph.tsx
import { Vis } from "vis-network";

interface GraphData {
  nodes: Array<{ id: string; label: string; title: string }>;
  edges: Array<{ from: string; to: string; label: string }>;
}

export function KnowledgeGraphView({ sessionId }: { sessionId: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Vis.Network | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  
  useEffect(() => {
    // Fetch knowledge graph
    fetch(`/api/research/${sessionId}/knowledge`)
      .then(r => r.json())
      .then(setGraphData);
  }, [sessionId]);
  
  useEffect(() => {
    if (!graphData || !containerRef.current) return;
    
    const options = {
      physics: {
        enabled: true,
        stabilization: { iterations: 200 }
      },
      interaction: { navigationButtons: true, keyboard: true }
    };
    
    networkRef.current = new Vis.Network(
      containerRef.current,
      graphData,
      options
    );
  }, [graphData]);
  
  return <div ref={containerRef} style={{ height: "600px" }} />;
}

// components/report/EvidenceTable.tsx
interface Evidence {
  claim: string;
  sources: Array<{ title: string; url: string }>;
  confidence: string;
}

export function EvidenceTable({ sessionId }: { sessionId: string }) {
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  
  useEffect(() => {
    fetch(`/api/research/${sessionId}/evidence`)
      .then(r => r.json())
      .then(data => setEvidence(data.evidence));
  }, [sessionId]);
  
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-slate-700">
          <th className="text-left p-4">Claim</th>
          <th className="text-left p-4">Sources</th>
          <th className="text-left p-4">Confidence</th>
        </tr>
      </thead>
      <tbody>
        {evidence.map((row, idx) => (
          <tr key={idx} className="border-b border-slate-700 hover:bg-slate-800">
            <td className="p-4">{row.claim}</td>
            <td className="p-4">
              {row.sources.map((src, i) => (
                <a
                  key={i}
                  href={src.url}
                  target="_blank"
                  className="text-blue-400 hover:underline mr-2"
                >
                  {src.title}
                </a>
              ))}
            </td>
            <td className="p-4">
              <span className={`px-2 py-1 rounded text-sm ${
                row.confidence === "high"
                  ? "bg-green-900 text-green-200"
                  : row.confidence === "medium"
                  ? "bg-yellow-900 text-yellow-200"
                  : "bg-red-900 text-red-200"
              }`}>
                {row.confidence}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### Testing
- [x] Claim extraction: Mock LLM, verify JSON parsing
- [x] Knowledge fusion: Entities extracted, relationships created
- [x] Duplicate merging: Entities with same name merged
- [x] End-to-end: Search → Extract → Graph visualization

### Acceptance Criteria
- ✅ Claims extracted from sources with LLM
- ✅ Claims have subject, predicate, object, confidence
- ✅ Knowledge nodes created for unique entities
- ✅ Knowledge edges created for relationships
- ✅ Graph visualization renders correctly
- ✅ Evidence table shows claims with sources
- ✅ Error recovery: LLM timeout → continue without claims

---

## Phase 4: Contradiction Detection & JEV (Weeks 7-8)

### Goal
Detect contradictions, identify knowledge gaps, implement decision engine. By the end:
- Contradictions automatically detected
- Knowledge gaps identified
- JEV (decision engine) selects next action
- Self-correction loop begins

### Deliverables

#### Backend
- [x] Contradiction detection service
- [x] Knowledge gap analysis
- [x] Decision engine (JEV) with hardcoded heuristics
- [x] Metrics calculation (coverage, information gain)
- [x] Stopping condition logic

#### Frontend
- [x] Contradiction display with severity
- [x] Coverage meter
- [x] Decision reasoning display
- [x] Iteration steps with actions taken

#### Integration
- [x] Full research loop: Search → Extract → Fuse → Detect → Decide → Repeat
- [x] Stopping condition triggers report generation
- [x] Self-correction visible to user

### Key Tasks

**Backend (5-7 days)**
```python
# services/contradiction_detector.py
class ContradictionDetector:
    """Detects contradictions in knowledge state."""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def detect(self, session_id: str) -> List[Contradiction]:
        """Find contradictory claims."""
        claims = await self.db.get_claims(session_id)
        contradictions = []
        
        # Compare all pairs of claims
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i+1:]:
                if self._are_contradictory(claim1, claim2):
                    contradiction = Contradiction(
                        session_id=session_id,
                        claim_1_id=claim1.id,
                        claim_2_id=claim2.id,
                        severity=self._assess_severity(claim1, claim2)
                    )
                    contradictions.append(contradiction)
                    await self.db.store_contradiction(contradiction)
        
        return contradictions
    
    def _are_contradictory(self, claim1: Claim, claim2: Claim) -> bool:
        """Check if two claims contradict."""
        # Simple heuristic: same subject, different objects
        if claim1.subject == claim2.subject and \
           claim1.predicate == claim2.predicate and \
           claim1.object != claim2.object:
            return True
        
        # More sophisticated: opposite predicates
        opposite_predicates = {
            "increases": "decreases",
            "supports": "refutes",
            "viable": "not viable"
        }
        
        if claim1.subject == claim2.subject and \
           opposite_predicates.get(claim1.predicate) == claim2.predicate:
            return True
        
        return False
    
    def _assess_severity(self, claim1: Claim, claim2: Claim) -> str:
        """Rate contradiction severity."""
        # High confidence contradictions are severe
        if claim1.confidence == "high" and claim2.confidence == "high":
            return "high"
        elif claim1.confidence == "low" or claim2.confidence == "low":
            return "low"
        else:
            return "medium"

# services/decision_engine.py
class DecisionEngine:
    """JEV: Knowledge Fusion Evaluation and Value-based decision making"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def select_action(self, session_id: str) -> str:
        """Decide next action based on knowledge state."""
        state = await self._evaluate_state(session_id)
        
        # Decision logic (hardcoded heuristics for V1)
        if state["unresolved_contradictions"] > 0:
            return "VERIFY"
        elif state["coverage"] < 0.65:
            return "SEARCH"
        elif state["has_knowledge_gaps"]:
            return "EXPAND_QUERY"
        else:
            return "STOP"
    
    async def _evaluate_state(self, session_id: str) -> dict:
        """Evaluate current knowledge state."""
        claims = await self.db.get_claims(session_id)
        contradictions = await self.db.get_contradictions(session_id)
        nodes = await self.db.get_nodes(session_id)
        
        # Coverage: what % of important entities are covered
        coverage = self._calculate_coverage(claims, nodes)
        
        # Information gain from last iteration
        last_action = await self.db.get_last_action(session_id)
        info_gain = last_action.information_gain if last_action else 0
        
        # Gaps: missing entities needed to answer question
        gaps = await self._find_knowledge_gaps(session_id)
        
        # Unresolved contradictions
        unresolved = sum(1 for c in contradictions if not c.resolved)
        
        return {
            "coverage": coverage,
            "information_gain": info_gain,
            "has_knowledge_gaps": len(gaps) > 0,
            "unresolved_contradictions": unresolved,
            "claim_count": len(claims),
            "contradiction_count": len(contradictions),
            "node_count": len(nodes)
        }
    
    def _calculate_coverage(self, claims: List[Claim], nodes: List[KnowledgeNode]) -> float:
        """Estimate coverage of important concepts."""
        if not nodes:
            return 0.0
        
        # Simple heuristic: % of nodes with >= 2 claims
        nodes_with_evidence = sum(
            1 for node in nodes
            if sum(1 for c in claims if c.subject == node.entity) >= 2
        )
        
        return nodes_with_evidence / len(nodes)
    
    async def _find_knowledge_gaps(self, session_id: str) -> List[str]:
        """Identify missing information needed."""
        session = await self.db.get_session(session_id)
        claims = await self.db.get_claims(session_id)
        
        gaps = []
        
        # Common missing dimensions for research
        dimensions = ["cost", "timeline", "feasibility", "impact", "policy", "technology"]
        
        covered_dimensions = set(
            claim.predicate.lower() for claim in claims
        )
        
        for dim in dimensions:
            if dim not in covered_dimensions:
                gaps.append(dim)
        
        return gaps[:3]  # Return top 3 gaps

# services/research_orchestrator.py (updated)
class ResearchOrchestrator:
    def __init__(
        self,
        search_agent: SearchAgent,
        claim_extractor: ClaimExtractor,
        knowledge_fusion: KnowledgeFusion,
        contradiction_detector: ContradictionDetector,
        decision_engine: DecisionEngine,
        db: Database,
        connection_manager: ConnectionManager
    ):
        self.search_agent = search_agent
        self.claim_extractor = claim_extractor
        self.knowledge_fusion = knowledge_fusion
        self.contradiction_detector = contradiction_detector
        self.decision_engine = decision_engine
        self.db = db
        self.conn = connection_manager
    
    async def run_research(self, session_id: str, max_iterations: int = 8):
        """Run complete research loop until stopping condition."""
        session = await self.db.get_session(session_id)
        
        try:
            iteration = 0
            start_time = datetime.utcnow()
            
            while iteration < max_iterations:
                iteration += 1
                
                # Execute one iteration
                result = await self.execute_iteration(session_id, iteration)
                
                # Broadcast progress
                await self.conn.broadcast(session_id, {
                    "type": "iteration_complete",
                    "iteration": iteration,
                    "sources_found": result.sources_found,
                    "claims_extracted": result.claims_extracted,
                    "next_action": result.next_action
                })
                
                # Check stopping conditions
                elapsed = (datetime.utcnow() - start_time).total_seconds() / 60
                
                if elapsed > 10:  # 10 minute timeout
                    logger.info(f"Research timeout for session {session_id}")
                    break
                
                if result.next_action == "STOP":
                    logger.info(f"Research complete for session {session_id}")
                    break
                
                # Brief delay before next iteration
                await asyncio.sleep(0.5)
            
            # Generate final report
            await self.generate_report(session_id)
            
        except Exception as e:
            logger.error(f"Research error for session {session_id}: {e}")
            await self.conn.broadcast(session_id, {
                "type": "error",
                "message": str(e)
            })
    
    async def execute_iteration(
        self,
        session_id: str,
        iteration: int
    ) -> IterationResult:
        """Execute single iteration."""
        # 1. Search
        query = self.generate_search_query(session_id, iteration)
        sources = await self.search_agent.search(query)
        
        for source in sources:
            source.session_id = session_id
            await self.db.store_source(source)
        
        # 2. Extract claims
        claims = await self.claim_extractor.extract(sources)
        
        for claim in claims:
            claim.session_id = session_id
            await self.db.store_claim(claim)
        
        # 3. Fuse knowledge
        await self.knowledge_fusion.fuse(session_id, claims)
        
        # 4. Detect contradictions
        contradictions = await self.contradiction_detector.detect(session_id)
        
        # 5. Decide next action
        action = await self.decision_engine.select_action(session_id)
        
        # Log action for RL training
        await self.db.store_action(ResearchAction(
            session_id=session_id,
            iteration_number=iteration,
            action_type=action,
            query=query,
            sources_found=len(sources),
            new_claims_extracted=len(claims),
            information_gain=0.7  # TODO: compute actual value
        ))
        
        return IterationResult(
            iteration=iteration,
            sources_found=len(sources),
            claims_extracted=len(claims),
            contradictions_found=len(contradictions),
            next_action=action
        )
```

**Frontend (2 days)**
```tsx
// components/session/ContradictionView.tsx
interface Contradiction {
  claim_1: string;
  claim_2: string;
  severity: "high" | "medium" | "low";
  resolved: boolean;
}

export function ContradictionView({ sessionId }: { sessionId: string }) {
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);
  
  useEffect(() => {
    fetch(`/api/research/${sessionId}/contradictions`)
      .then(r => r.json())
      .then(data => setContradictions(data.contradictions));
  }, [sessionId]);
  
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">Contradictions Found</h3>
      
      {contradictions.length === 0 ? (
        <p className="text-slate-400">No contradictions detected</p>
      ) : (
        contradictions.map((contradiction, idx) => (
          <div
            key={idx}
            className={`p-4 rounded border-l-4 ${
              contradiction.severity === "high"
                ? "border-red-500 bg-red-900/20"
                : contradiction.severity === "medium"
                ? "border-yellow-500 bg-yellow-900/20"
                : "border-blue-500 bg-blue-900/20"
            }`}
          >
            <p className="font-semibold">Claim 1: {contradiction.claim_1}</p>
            <p className="font-semibold">Claim 2: {contradiction.claim_2}</p>
            <p className="text-sm text-slate-400 mt-2">
              Status: {contradiction.resolved ? "Resolved" : "Unresolved"}
            </p>
          </div>
        ))
      )}
    </div>
  );
}

// components/session/CoverageWidget.tsx
export function CoverageWidget({ sessionId }: { sessionId: string }) {
  const [coverage, setCoverage] = useState(0);
  
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);
    
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "coverage_update") {
        setCoverage(msg.coverage * 100);
      }
    };
    
    return () => ws.close();
  }, [sessionId]);
  
  return (
    <div className="bg-slate-800 p-6 rounded-lg">
      <h3 className="text-sm font-semibold text-slate-400 mb-2">Knowledge Coverage</h3>
      <div className="w-full bg-slate-700 rounded-full h-4">
        <div
          className="bg-blue-500 h-4 rounded-full transition-all"
          style={{ width: `${coverage}%` }}
        />
      </div>
      <p className="text-2xl font-bold mt-4">{coverage.toFixed(0)}%</p>
    </div>
  );
}
```

### Testing
- [x] Contradiction detection: Opposite claims identified
- [x] Decision engine: Correct action selected for each state
- [x] Stopping condition: Loop terminates appropriately
- [x] End-to-end: Multiple iterations complete with self-correction

### Acceptance Criteria
- ✅ Contradictions automatically detected
- ✅ Knowledge gaps identified
- ✅ Decision engine selects appropriate next action
- ✅ Coverage meter accurate (65%+ coverage triggers STOP)
- ✅ Self-correction loop runs: S → E → F → D → S
- ✅ Research terminates at correct stopping condition
- ✅ Full session completes in <10 minutes

---

## Phase 5: Report Generation & Polish (Weeks 9-12)

### Goal
Generate final reports, optimize performance, test thoroughly, prepare for launch. By the end:
- Beautiful, well-formatted reports
- All features working end-to-end
- Performance tuned
- Documentation complete
- Ready to ship

### Deliverables

#### Backend
- [x] Report generation service
- [x] Report serialization (JSON, HTML export)
- [x] API endpoints for all features
- [x] Comprehensive error handling
- [x] Performance optimization
- [x] Database query optimization

#### Frontend
- [x] Final report layout
- [x] Executive summary component
- [x] Interactive report viewing
- [x] Report export (JSON, HTML)
- [x] UI polish and refinement
- [x] Dark mode optimized
- [x] Loading states perfected

#### QA & Deployment
- [x] Comprehensive testing (20+ research scenarios)
- [x] Performance benchmarking
- [x] Security review
- [x] Deployment guide
- [x] User documentation
- [x] API documentation (OpenAPI)
- [x] CI/CD pipeline configured

### Key Tasks

**Backend (3-4 days)**
```python
# services/report_generator.py
class ReportGenerator:
    def __init__(self, db: Database):
        self.db = db
    
    async def generate_report(self, session_id: str) -> Report:
        """Generate comprehensive final report."""
        session = await self.db.get_session(session_id)
        claims = await self.db.get_claims(session_id)
        sources = await self.db.get_sources(session_id)
        graph = await self._build_graph(session_id)
        contradictions = await self.db.get_contradictions(session_id)
        
        return Report(
            session_id=session_id,
            question=session.question,
            executive_summary=self._summarize(claims),
            evidence_table=self._build_evidence_table(claims, sources),
            knowledge_graph=graph,
            contradictions=contradictions,
            unknowns=self._identify_unknowns(claims),
            methodology=self._generate_methodology(session),
            sources=sources,
            generated_at=datetime.utcnow()
        )
    
    def _summarize(self, claims: List[Claim]) -> str:
        """Generate executive summary from claims."""
        high_confidence_claims = [
            c for c in claims if c.confidence == "high"
        ]
        
        if not high_confidence_claims:
            return "Insufficient evidence to answer question."
        
        # Simple heuristic: combine top 3 high-confidence claims
        summary_claims = high_confidence_claims[:3]
        summary = " ".join(c.claim for c in summary_claims)
        
        return summary
    
    def _build_evidence_table(
        self,
        claims: List[Claim],
        sources: List[Source]
    ) -> List[EvidenceRow]:
        """Build evidence table: Claim → Sources → Confidence."""
        rows = []
        
        for claim in sorted(
            claims,
            key=lambda c: {"high": 0, "medium": 1, "low": 2}.get(c.confidence, 3)
        ):
            source = next((s for s in sources if s.id == claim.source_id), None)
            
            if source:
                rows.append(EvidenceRow(
                    claim=claim.claim,
                    source=source,
                    confidence=claim.confidence
                ))
        
        return rows
    
    async def _build_graph(self, session_id: str) -> dict:
        """Serialize knowledge graph for visualization."""
        nodes = await self.db.get_nodes(session_id)
        edges = await self.db.get_edges(session_id)
        
        return {
            "nodes": [
                {"id": str(n.id), "label": n.entity, "type": n.entity_type}
                for n in nodes
            ],
            "edges": [
                {
                    "from": str(e.source_node_id),
                    "to": str(e.target_node_id),
                    "label": e.relationship_type,
                    "strength": e.strength
                }
                for e in edges
            ]
        }
    
    def _identify_unknowns(self, claims: List[Claim]) -> List[str]:
        """Identify remaining unknowns."""
        unknowns = [
            "Economic viability at scale",
            "Long-term environmental impact",
            "Regulatory timeline",
            "Technology maturation curve"
        ]
        return unknowns[:3]
    
    def _generate_methodology(self, session: ResearchSession) -> str:
        """Describe research methodology."""
        return f"""
This report was generated through autonomous research using:
- Question: {session.question}
- Research depth: {session.depth}
- Max time: {session.max_research_time_minutes} minutes
- Minimum sources: {session.min_sources_required}

The research agent iteratively:
1. Searched for relevant sources
2. Extracted factual claims
3. Built a knowledge graph
4. Detected contradictions
5. Identified gaps
6. Decided on next search direction
7. Repeated until sufficient evidence was gathered

All claims in this report are directly sourced and linked.
"""

# api/routes/reports.py
@app.get("/api/research/{session_id}/report")
async def get_report(session_id: str):
    """Get final research report."""
    session = await db.get_session(session_id)
    
    if session.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Research not yet completed"
        )
    
    report = await report_generator.generate_report(session_id)
    return report

# Add more endpoints
@app.get("/api/research/{session_id}/report/export-html")
async def export_report_html(session_id: str):
    """Export report as HTML."""
    report = await get_report(session_id)
    html = report_to_html(report)
    return HTMLResponse(content=html)

@app.get("/api/research/{session_id}/report/export-json")
async def export_report_json(session_id: str):
    """Export report as JSON."""
    report = await get_report(session_id)
    return JSONResponse(content=report.dict())
```

**Frontend (4-5 days)**
```tsx
// app/dashboard/[sessionId]/report.tsx
import { ReportLayout } from "@/components/report/ReportLayout";
import { ExecutiveSummary } from "@/components/report/ExecutiveSummary";
import { EvidenceTable } from "@/components/report/EvidenceTable";
import { KnowledgeGraphView } from "@/components/report/KnowledgeGraph";
import { ContradictionView } from "@/components/report/ContradictionView";
import { UnknownsSection } from "@/components/report/UnknownsSection";
import { SourceList } from "@/components/report/SourceList";

interface Tabs {
  report: boolean;
  knowledge: boolean;
  contradictions: boolean;
  raw: boolean;
}

export default function ReportPage({
  params,
}: {
  params: { sessionId: string };
}) {
  const [activeTab, setActiveTab] = useState<keyof Tabs>("report");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/research/${params.sessionId}/report`)
      .then((r) => r.json())
      .then((data) => {
        setReport(data);
        setLoading(false);
      });
  }, [params.sessionId]);

  if (loading) {
    return <LoadingSpinner />;
  }

  if (!report) {
    return <ErrorView message="Failed to load report" />;
  }

  return (
    <ReportLayout>
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">{report.question}</h1>
        <p className="text-slate-400">
          Generated on {new Date(report.generated_at).toLocaleDateString()}
        </p>
      </div>

      <div className="flex gap-4 mb-8 border-b border-slate-700">
        {(["report", "knowledge", "contradictions", "raw"] as const).map(
          (tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 font-semibold ${
                activeTab === tab
                  ? "text-blue-400 border-b-2 border-blue-400"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          )
        )}
      </div>

      <div className="mb-8">
        {activeTab === "report" && (
          <>
            <ExecutiveSummary summary={report.executive_summary} />
            <div className="mt-8">
              <h2 className="text-2xl font-bold mb-4">Evidence</h2>
              <EvidenceTable evidence={report.evidence_table} />
            </div>
            <div className="mt-8">
              <h2 className="text-2xl font-bold mb-4">Key Findings</h2>
              <SourceList sources={report.sources} />
            </div>
            <div className="mt-8">
              <h2 className="text-2xl font-bold mb-4">Remaining Questions</h2>
              <UnknownsSection unknowns={report.unknowns} />
            </div>
          </>
        )}

        {activeTab === "knowledge" && (
          <KnowledgeGraphView graph={report.knowledge_graph} />
        )}

        {activeTab === "contradictions" && (
          <ContradictionView contradictions={report.contradictions} />
        )}

        {activeTab === "raw" && (
          <pre className="bg-slate-900 p-4 rounded overflow-x-auto text-sm">
            {JSON.stringify(report, null, 2)}
          </pre>
        )}
      </div>

      <div className="flex gap-4 mt-12">
        <button className="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded font-semibold">
          Export as JSON
        </button>
        <button className="px-6 py-2 bg-slate-700 hover:bg-slate-600 rounded font-semibold">
          Export as HTML
        </button>
        <button className="px-6 py-2 bg-slate-700 hover:bg-slate-600 rounded font-semibold">
          Share
        </button>
      </div>
    </ReportLayout>
  );
}

// components/report/ExecutiveSummary.tsx
export function ExecutiveSummary({ summary }: { summary: string }) {
  return (
    <div className="bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-700/30 p-6 rounded-lg">
      <h2 className="text-2xl font-bold mb-4">Executive Summary</h2>
      <p className="text-lg text-slate-200 leading-relaxed">{summary}</p>
    </div>
  );
}
```

**Testing & QA (3-4 days)**
```python
# tests/test_full_research_flow.py
import pytest

RESEARCH_SCENARIOS = [
    "Can biomass pellets replace coal in Indian power plants?",
    "Is solar green hydrogen economically viable in India by 2030?",
    "What are the emerging threats in quantum computing security?",
    "How has AI regulation evolved globally since 2023?",
    "What is the current state of battery technology adoption?",
]

@pytest.mark.asyncio
async def test_full_research_flow():
    """Test complete research from question to report."""
    for question in RESEARCH_SCENARIOS:
        session = await start_research(question)
        
        # Run research
        await research_orchestrator.run_research(session.id)
        
        # Verify completion
        report = await report_generator.generate_report(session.id)
        
        assert report.question == question
        assert len(report.evidence_table) >= 10, "Need at least 10 claims"
        assert report.executive_summary, "Summary not generated"
        assert len(report.sources) >= 10, "Need at least 10 sources"
        assert report.knowledge_graph["nodes"], "Knowledge graph empty"

@pytest.mark.asyncio
async def test_performance_targets():
    """Verify performance meets targets."""
    question = "What is blockchain technology?"
    session = await start_research(question)
    
    start = time.time()
    await research_orchestrator.run_research(session.id)
    elapsed = time.time() - start
    
    assert elapsed < 8 * 60, f"Research took {elapsed}s, target <480s"

@pytest.mark.asyncio
async def test_error_recovery():
    """Test graceful error recovery."""
    # Mock API failure
    with patch.object(search_api, "search", side_effect=TimeoutError):
        session = await start_research("test question")
        
        # Should still complete with graceful degradation
        report = await report_generator.generate_report(session.id)
        assert report is not None
```

**Documentation (1-2 days)**
- [x] API documentation (OpenAPI/Swagger)
- [x] User guide with examples
- [x] Deployment guide (local + production)
- [x] Architecture decision records (ADRs)
- [x] Troubleshooting guide
- [x] Contributing guidelines

### Acceptance Criteria
- ✅ Report generated successfully for all test scenarios
- ✅ Report contains executive summary, evidence, graph, sources
- ✅ All endpoints working and documented
- ✅ Performance: 95% of sessions <8 minutes
- ✅ Error rate: <1% (test 100 sessions)
- ✅ Code coverage: >70%
- ✅ All tests pass
- ✅ Documentation complete and accurate
- ✅ Deployment working (Docker, local & cloud)
- ✅ Security review completed
- ✅ Ready for production launch

---

## Overall Timeline

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| 1: Foundation | 2 weeks | Basic API + DB + form |
| 2: Search | 2 weeks | Search integration + WebSocket |
| 3: IKF | 2 weeks | Claim extraction + Knowledge graph |
| 4: JEV | 2 weeks | Contradiction detection + Decision engine |
| 5: Polish | 3-4 weeks | Report generation + testing + docs |
| **Total** | **8-12 weeks** | **Shipping MVP** |

---

## Success Metrics by Phase

### Phase 1 ✓
- Development environment working
- Basic CRUD endpoints functional
- Frontend can create session

### Phase 2 ✓
- Search executes successfully
- Sources collected and stored
- Real-time progress updates to UI

### Phase 3 ✓
- Claims extracted from sources
- Knowledge graph built
- Evidence table renders correctly

### Phase 4 ✓
- Contradictions detected
- Self-correction loop working
- Research terminates appropriately

### Phase 5 ✓
- Beautiful reports generated
- All features integrated
- Performance meets targets
- Documentation complete
- **SHIP! 🚀**

---

**Document Version:** 1.0  
**Last Updated:** September 26, 2026  
**Owner:** MASTER  
**Status:** Ready for Implementation
