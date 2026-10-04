# Engineering Rules & Guidelines: Self-Correcting Research Agent MVP V1

## 1. Core Philosophy

### The Three Principles

1. **Clarity Over Cleverness**: Write code that is obvious, not impressive. Future maintainers (including you 6 months from now) should understand it within 2 minutes.

2. **Explicit Over Implicit**: Make decisions visible. Don't hide assumptions in clever frameworks or magic configuration. If something can fail, handle it explicitly.

3. **Measurable Over Assumed**: Don't guess whether the system works. Log metrics, measure performance, track errors. Every claim about the system should be backed by data.

---

## 2. What to Build (Must Have)

### Backend Requirements

- [ ] **FastAPI server** with async support (Python 3.11+)
- [ ] **PostgreSQL database** with proper indexing
- [ ] **Redis cache** for session management
- [ ] **Research orchestrator** that drives the core loop
- [ ] **Search integration** (Tavily or Perplexity API)
- [ ] **LLM integration** (Claude, GPT-4, or Gemini)
- [ ] **IKF layer**: Knowledge graph construction from claims
- [ ] **JEV layer**: Hardcoded decision rules (NOT RL in V1)
- [ ] **Contradiction detector**: Identifies conflicting claims
- [ ] **Report generator**: Compiles results into structured output
- [ ] **WebSocket support**: Real-time progress updates
- [ ] **Error handling**: Graceful recovery from API failures

### Frontend Requirements

- [ ] **Next.js 14+** with TypeScript
- [ ] **Research form**: Question input with optional constraints
- [ ] **Progress widget**: Real-time iteration updates
- [ ] **Knowledge graph visualization**: Interactive node-edge display
- [ ] **Evidence table**: Claims with source links and confidence
- [ ] **Report view**: Executive summary, findings, contradictions
- [ ] **Session management**: Create, retrieve, list sessions
- [ ] **Responsive design**: Works on desktop and tablet (mobile optional)

### Database Requirements

- [ ] **Normalized schema**: Users, sessions, sources, claims, knowledge graph
- [ ] **Proper indexing**: No N+1 queries on common operations
- [ ] **Transaction support**: Multi-step operations are atomic
- [ ] **Migrations**: Alembic for schema versioning

---

## 3. What NOT to Build (Explicitly Excluded)

### Do Not Attempt in V1

- ❌ **RL policy training**: No complex reinforcement learning. Use hardcoded heuristics instead.
- ❌ **Autonomous browser control**: Don't try to control user's OS or local browser.
- ❌ **Custom LLM fine-tuning**: Use existing APIs only.
- ❌ **Multi-agent swarms**: Keep it single-agent for V1.
- ❌ **Long-running research** (>10 minutes): Set hard time limits.
- ❌ **Voice interface**: Text-only input in V1.
- ❌ **Mobile app**: Web responsive design only, no native app.
- ❌ **Real-time sync** across users: Single-user sessions in V1.
- ❌ **Sentiment analysis**: Stick to factual claim extraction.
- ❌ **Fake news detection**: Too complex for V1 scope.
- ❌ **Geographic visualization**: Skip maps and spatial rendering.
- ❌ **Export to PDF/Word**: Save as JSON/HTML only.
- ❌ **Collaborative research**: Multi-user research is post-V1.
- ❌ **Authentication system**: Simple API key in V1 (proper auth in V1.1).

### Why Not?

These features would:
- Dramatically increase complexity
- Require weeks of additional engineering
- Introduce novel technical risks
- Distract from core research loop validation
- Make it harder to iterate and improve

**Lock in features first, polish second.**

---

## 4. Code Style & Conventions

### Python (Backend)

#### Naming

```python
# ✅ GOOD: Explicit, descriptive names
class ResearchOrchestrator:
    async def execute_research_iteration(self):
        pass

# ❌ BAD: Vague, abbreviated
class Orchestrator:
    async def execute(self):
        pass

# ✅ GOOD: Function names describe what they do
def extract_claims_from_source(source_content: str) -> List[Claim]:
    pass

# ❌ BAD: Generic verbs that don't clarify intent
def process_text(text: str) -> List[dict]:
    pass
```

#### Type Hints

```python
# ✅ GOOD: Always use type hints
async def search(query: str, max_results: int = 10) -> List[Source]:
    """Search web and return sources with metadata."""
    pass

# ❌ BAD: Missing type hints (hard to debug)
async def search(query, max_results=10):
    pass

# ✅ GOOD: Complex types use TypeVar or Union
from typing import Optional, List
def parse_claim(text: str) -> Optional[Claim]:
    pass

def get_result(session_id: str) -> Union[Report, None]:
    pass
```

#### Documentation

```python
# ✅ GOOD: Docstring explains intent, args, returns
async def detect_contradictions(
    claims: List[Claim],
    confidence_threshold: float = 0.6
) -> List[Contradiction]:
    """
    Identify contradictory claims in a knowledge state.
    
    A contradiction is detected when:
    - Two claims have opposing predicates on the same subject
    - Both claims meet the confidence threshold
    
    Args:
        claims: List of extracted claims
        confidence_threshold: Minimum confidence to consider (0.0-1.0)
    
    Returns:
        List of Contradiction objects with supporting evidence
    
    Raises:
        ValueError: If confidence_threshold is outside [0, 1]
    """
    pass

# ❌ BAD: No explanation of logic
def detect_contradictions(claims, confidence_threshold=0.6):
    pass
```

#### Error Handling

```python
# ✅ GOOD: Specific exception handling with context
async def search(query: str) -> List[Source]:
    try:
        response = await search_api.call(query)
        return parse_sources(response)
    except SearchAPITimeoutError as e:
        logger.warning(f"Search API timeout for query '{query}'", exc_info=e)
        raise TimeoutError(f"Search timed out after {e.timeout}s") from e
    except SearchAPIRateLimitError as e:
        logger.info(f"Search API rate limited, backing off {e.retry_after}s")
        await asyncio.sleep(e.retry_after)
        return await search(query)  # Retry once
    except Exception as e:
        logger.error(f"Unexpected search error: {e}", exc_info=e)
        raise

# ❌ BAD: Bare except, silent failures
def search(query):
    try:
        return search_api.call(query)
    except:
        return []  # Silent failure, hard to debug
```

#### Async/Await

```python
# ✅ GOOD: All I/O is async
async def execute_research_iteration(session_id: str) -> IterationResult:
    sources = await search_agent.search(query)
    claims = await claim_extractor.extract(sources)
    graph = await knowledge_fusion.fuse(claims)
    return IterationResult(sources, claims, graph)

# ❌ BAD: Blocking I/O in async function
async def execute_research_iteration(session_id: str):
    sources = search_api_blocking.search(query)  # Blocks event loop!
    claims = extract_claims(sources)
    return (sources, claims)
```

### TypeScript (Frontend)

#### Component Names

```tsx
// ✅ GOOD: Name describes what it renders and its purpose
export function ResearchForm({ onSubmit }: Props): JSX.Element {
  return <form>...</form>;
}

export function ProgressWidget({ sessionId }: Props): JSX.Element {
  return <div>Progress...</div>;
}

// ❌ BAD: Generic names that don't clarify purpose
export function Form({ onSubmit }: Props): JSX.Element {
  return <form>...</form>;
}

export function Widget({ id }: Props): JSX.Element {
  return <div>...</div>;
}
```

#### Props & State

```tsx
// ✅ GOOD: Typed props with clear interface
interface ResearchFormProps {
  onSubmit: (question: ResearchQuestion) => Promise<void>;
  isLoading?: boolean;
  error?: string;
}

export function ResearchForm({
  onSubmit,
  isLoading = false,
  error,
}: ResearchFormProps): JSX.Element {
  // ...
}

// ❌ BAD: Untyped or overly generic props
export function ResearchForm(props: any): JSX.Element {
  // Can't see what props are needed
}
```

#### Hooks

```tsx
// ✅ GOOD: Custom hooks for reusable logic
function useResearchSession(sessionId: string) {
  const [session, setSession] = useState<ResearchSession | null>(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    fetchSession(sessionId).then(setSession).finally(() => setLoading(false));
  }, [sessionId]);
  
  return { session, loading };
}

// Usage
function SessionView({ sessionId }: Props) {
  const { session, loading } = useResearchSession(sessionId);
  if (loading) return <Spinner />;
  return <ReportDisplay report={session?.report} />;
}

// ❌ BAD: Logic scattered in multiple components
function SessionView({ sessionId }: Props) {
  const [session, setSession] = useState(null);
  useEffect(() => { fetchSession(sessionId).then(setSession); }, [sessionId]);
  // ... more logic
}

// DuplicateSessionView also has same fetch logic
function DuplicateSessionView({ sessionId }: Props) {
  const [session, setSession] = useState(null);
  useEffect(() => { fetchSession(sessionId).then(setSession); }, [sessionId]);
  // ... duplicate
}
```

#### Error Boundaries

```tsx
// ✅ GOOD: Error boundary for graceful degradation
export function SessionPage() {
  return (
    <ErrorBoundary fallback={<ErrorView />}>
      <SessionContent />
    </ErrorBoundary>
  );
}

// ❌ BAD: No error handling at boundaries
export function SessionPage() {
  return <SessionContent />; // Uncaught errors crash the page
}
```

---

## 5. Database Rules

### Schema Design

```sql
-- ✅ GOOD: Normalized, well-indexed
CREATE TABLE research_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    question TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'initializing',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    CONSTRAINT status_check CHECK (status IN ('initializing', 'running', 'completed', 'error'))
);

CREATE INDEX idx_sessions_user_created ON research_sessions(user_id, created_at DESC);
CREATE INDEX idx_sessions_status ON research_sessions(status);

-- ❌ BAD: Denormalized, no indexes
CREATE TABLE sessions (
    id SERIAL,
    user TEXT,  -- Should be user_id foreign key
    q TEXT,     -- Abbreviated, unclear
    stat VARCHAR(10),  -- No constraint, typos possible
    ts TIMESTAMP
    -- No indexes!
);
```

### Query Patterns

```python
# ✅ GOOD: Use ORM, avoid raw SQL, use proper indexing
async def get_session_claims(session_id: str) -> List[Claim]:
    """Get all claims for a session, leveraging indexes."""
    return await db.query(Claim).where(
        Claim.session_id == session_id
    ).all()

# ❌ BAD: Raw SQL, N+1 queries
def get_session_claims(session_id):
    cursor.execute("SELECT * FROM claims WHERE session_id = %s", (session_id,))
    # Then iterate and query sources for each claim (N+1!)
    for claim in cursor.fetchall():
        sources = cursor.execute("SELECT * FROM sources WHERE id = ?", (claim.source_id,))
```

### Transaction Management

```python
# ✅ GOOD: Explicit transactions for multi-step operations
async def complete_research_session(session_id: str, report: Report):
    """Complete a session and store report in one transaction."""
    async with db.transaction():
        await db.update(ResearchSession).where(
            ResearchSession.id == session_id
        ).set(status="completed", completed_at=now())
        
        report_id = await db.insert(Report).values(
            session_id=session_id,
            content=report.to_json()
        ).returning(Report.id)
        
        return report_id

# ❌ BAD: Separate updates that can fail halfway
def complete_research_session(session_id, report):
    db.update_session(session_id, "completed")
    db.insert_report(session_id, report)
    # If second fails, session is marked complete but report missing!
```

---

## 6. API Design Rules

### Endpoint Conventions

```
✅ GOOD: RESTful, clear intent
POST   /api/research/start          → Begin research
GET    /api/research/{id}           → Get session details
GET    /api/research/{id}/report    → Get final report
GET    /api/research/{id}/knowledge → Get knowledge graph
POST   /api/research/{id}/stop      → Stop research

❌ BAD: Ambiguous, not RESTful
POST   /api/research/begin          → Unclear if "begin" means start or something else
GET    /api/get-session/{id}        → Redundant "get" in endpoint
POST   /api/research/{id}/execute   → What are we executing?
GET    /api/research/{id}/data      → Too vague, what data?
```

### Request/Response

```python
# ✅ GOOD: Clear schema, proper HTTP status
@app.post("/api/research/start", response_model=ResearchSessionResponse)
async def start_research(request: ResearchQuestionInput) -> ResearchSessionResponse:
    """Start a new research session.
    
    Returns 201 if successful, 400 if invalid input.
    """
    if not is_valid_question(request.question):
        raise HTTPException(status_code=400, detail="Question too short or unclear")
    
    session = await create_session(request)
    return ResearchSessionResponse(
        session_id=session.id,
        status="initializing",
        estimated_completion_time=300
    )

# ❌ BAD: Untyped, vague responses
@app.post("/api/research/start")
async def start_research(request):
    session = create_session(request)
    return {"id": session.id}  # Missing status, time estimate, type info
```

### Error Responses

```python
# ✅ GOOD: Consistent error format
@app.post("/api/research/start")
async def start_research(request: ResearchQuestionInput):
    try:
        return await create_session(request)
    except InvalidQuestionError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_question",
                "message": str(e),
                "field": "question"
            }
        )
    except DatabaseError as e:
        logger.error(f"Database error creating session: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_server_error",
                "message": "Failed to create research session"
            }
        )

# ❌ BAD: Inconsistent error formats
@app.post("/api/research/start")
async def start_research(request):
    return {"error": e}  # Vague, unstructured
    # vs
    return {"message": "Something went wrong"}  # No error code
    # vs
    raise Exception(str(e))  # Unhandled exception, 500 error
```

---

## 7. LLM Integration Rules

### Prompting

```python
# ✅ GOOD: Explicit, structured, with examples
def extract_claims_prompt(source_content: str) -> str:
    return f"""
Extract factual claims from the following source text.

Return a JSON array where each object has:
- "claim": The complete claim statement
- "subject": The entity being claimed about
- "predicate": The relationship or property
- "object": The value or target of the relationship
- "confidence": "high", "medium", or "low" based on how clearly stated it is

Example:
Source: "Solar electricity costs have fallen 90% since 2010, from $350/kWh to $35/kWh."

Output:
[
  {{
    "claim": "Solar electricity costs fell from $350/kWh to $35/kWh between 2010 and now",
    "subject": "Solar electricity cost",
    "predicate": "changed",
    "object": "$350/kWh → $35/kWh",
    "confidence": "high"
  }},
  {{
    "claim": "Solar electricity costs have fallen 90%",
    "subject": "Solar electricity cost",
    "predicate": "reduction_percent",
    "object": "90%",
    "confidence": "high"
  }}
]

Now extract claims from this source:

SOURCE:
{source_content}

Return ONLY valid JSON, no other text.
"""

# ❌ BAD: Vague, no structure
def extract_claims_prompt(source_content):
    return f"Extract claims from: {source_content}"
    # What format? How detailed? No examples for LLM to learn from
```

### API Calling

```python
# ✅ GOOD: Error handling, retries, validation
async def extract_claims(content: str) -> List[Claim]:
    """Extract claims from source content."""
    prompt = extract_claims_prompt(content)
    
    for attempt in range(3):  # Retry up to 3 times
        try:
            response = await llm_client.generate(
                model="claude-3-sonnet",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,  # Low temp for factual extraction
                max_tokens=2000
            )
            
            # Parse response
            claims_json = json.loads(response.content)
            claims = [Claim(**claim_data) for claim_data in claims_json]
            
            if not claims:
                logger.warning(f"No claims extracted from content: {content[:100]}")
            
            return claims
            
        except json.JSONDecodeError as e:
            logger.warning(f"LLM returned invalid JSON (attempt {attempt+1}): {response.content}")
            if attempt < 2:
                await asyncio.sleep(1)  # Brief delay before retry
                continue
            else:
                raise ValueError(f"LLM failed to return valid JSON after 3 attempts")
        
        except LLMAPIError as e:
            if "rate_limit" in str(e):
                logger.info(f"Rate limited, waiting 60s (attempt {attempt+1})")
                await asyncio.sleep(60)
                continue
            else:
                raise

# ❌ BAD: No error handling
async def extract_claims(content):
    response = await llm.generate(f"Extract claims: {content}")
    return json.loads(response)  # Crashes on invalid JSON!
```

### Cost Awareness

```python
# ✅ GOOD: Be aware of LLM costs
# Use cheaper models where appropriate
async def extract_claims(content: str) -> List[Claim]:
    """Extract claims using fast, cheap model."""
    model = "claude-3-haiku"  # Cheaper than Sonnet
    # ... use this model

async def generate_report(knowledge_graph: KnowledgeGraph) -> str:
    """Generate final report using smarter model."""
    model = "claude-3-sonnet"  # Better quality for final output
    # ... use this model

# ❌ BAD: Always use expensive models
async def extract_claims(content):
    response = await llm.generate_with("gpt-4-turbo", f"Extract: {content}")
    # Expensive, overkill for simple extraction
```

---

## 8. Search API Integration Rules

### Rate Limiting

```python
# ✅ GOOD: Respect API limits
SEARCH_API_RATE_LIMIT = 50  # queries per session

class SearchAgent:
    def __init__(self):
        self.queries_used = 0
        self.max_queries = SEARCH_API_RATE_LIMIT
    
    async def search(self, query: str) -> List[Source]:
        if self.queries_used >= self.max_queries:
            raise RateLimitExceededError(
                f"Exceeded {self.max_queries} queries for this session"
            )
        
        result = await search_api.search(query)
        self.queries_used += 1
        return result

# ❌ BAD: No rate limiting
class SearchAgent:
    async def search(self, query):
        return await search_api.search(query)
    # Can spam search API if called 1000 times!
```

### Deduplication

```python
# ✅ GOOD: Avoid duplicate sources
class SearchAgent:
    def __init__(self):
        self.seen_urls = set()
    
    async def search(self, query: str) -> List[Source]:
        results = await search_api.search(query)
        
        # Filter out URLs we've already processed
        new_sources = [
            src for src in results
            if src.url not in self.seen_urls
        ]
        
        self.seen_urls.update(src.url for src in new_sources)
        return new_sources

# ❌ BAD: No deduplication
async def search(query):
    return await search_api.search(query)
    # May return same URL twice, wasting API credits and processing time
```

---

## 9. Logging & Debugging

### What to Log

```python
# ✅ GOOD: Log meaningful events with context
logger.info(
    "research_iteration_complete",
    extra={
        "session_id": session_id,
        "iteration": 3,
        "sources_found": 5,
        "new_claims": 4,
        "information_gain": 0.8,
        "duration_ms": 1250
    }
)

logger.warning(
    "claim_confidence_low",
    extra={
        "claim_id": claim.id,
        "confidence": 0.3,
        "source_url": source.url
    }
)

# ❌ BAD: Useless logs
logger.info("Processing...")  # Too vague
logger.info(f"Result: {result}")  # What result? Where?
logger.debug("X")  # Meaningless single letter
```

### Never Log Secrets

```python
# ✅ GOOD: Never log API keys or sensitive data
async def call_search_api(query: str, api_key: str) -> dict:
    logger.info(f"Searching: {query}")  # OK
    response = await api.search(query, api_key)
    # Don't log api_key!
    return response

# ❌ BAD: Logged API key!
logger.info(f"API key: {api_key}, query: {query}")  # SECURITY BREACH
```

---

## 10. Testing Requirements

### Unit Tests

```python
# ✅ GOOD: Test business logic in isolation
import pytest

@pytest.mark.asyncio
async def test_extract_claims_returns_valid_claims():
    """Test that claim extraction returns properly structured claims."""
    content = "Solar costs fell 90% from $350 to $35 per kWh."
    claims = await extract_claims(content)
    
    assert len(claims) >= 1
    assert all(isinstance(c, Claim) for c in claims)
    assert all(c.subject and c.predicate and c.object for c in claims)

@pytest.mark.asyncio
async def test_extract_claims_with_empty_content():
    """Test that empty content returns empty claims."""
    claims = await extract_claims("")
    assert claims == []

@pytest.mark.asyncio
async def test_detect_contradictions_identifies_opposing_claims():
    """Test that contradictions are correctly identified."""
    claim_a = Claim(subject="Cost", predicate="is", object="high", confidence="high")
    claim_b = Claim(subject="Cost", predicate="is", object="low", confidence="high")
    
    contradictions = detect_contradictions([claim_a, claim_b])
    assert len(contradictions) == 1

# ❌ BAD: Test doesn't verify anything
def test_extract_claims():
    result = extract_claims("text")
    assert result  # Too vague, could pass with wrong output
```

### Integration Tests

```python
# ✅ GOOD: Test end-to-end flow
@pytest.mark.asyncio
async def test_research_iteration_flow():
    """Test complete research iteration: search → extract → fuse → decide."""
    session = await create_test_session("Should AI be regulated?")
    
    # Execute one iteration
    iteration = await research_orchestrator.execute_iteration(session.id)
    
    # Verify expected state changes
    assert iteration.sources_found > 0
    assert iteration.claims_extracted > 0
    assert iteration.next_action in ["SEARCH", "VERIFY", "EXPAND", "STOP"]

# ❌ BAD: Only tests one component in isolation
def test_search_agent():
    sources = search_agent.search("test")
    assert len(sources) > 0
    # Doesn't test the full research loop
```

### Coverage Target

- **Minimum**: 70% code coverage
- **Target**: 80% coverage for business logic
- **Critical**: 100% coverage for decision engine, contradiction detector

---

## 11. Performance & Scalability Rules

### Response Time Targets

| Operation | Target | Limit |
|-----------|--------|-------|
| Start research | <500ms | 1s |
| Search query | <2s | 5s |
| Claim extraction | <3s | 10s |
| Knowledge fusion | <2s | 5s |
| Report generation | <1s | 3s |
| Full iteration | <10s | 20s |
| Full session (all iterations) | <8 min | 10 min |

### Database Query Rules

```python
# ✅ GOOD: Efficient queries
async def get_session_summary(session_id: str) -> SessionSummary:
    """Get summary with single efficient query."""
    result = await db.query(
        ResearchSession,
        func.count(Claim.id).label("claim_count"),
        func.count(Source.id).label("source_count")
    ).outerjoin(Claim).outerjoin(Source).group_by(ResearchSession.id).filter(
        ResearchSession.id == session_id
    ).first()
    
    return SessionSummary.from_orm(result)

# ❌ BAD: N+1 queries
def get_session_summary(session_id):
    session = db.query(ResearchSession).filter_by(id=session_id).first()
    claims = db.query(Claim).filter_by(session_id=session_id).all()  # Query 1
    sources = db.query(Source).filter_by(session_id=session_id).all()  # Query 2
    # If you loop through claims, each iteration queries associated sources...
    return SessionSummary(session, len(claims), len(sources))
```

### Caching Strategy

```python
# ✅ GOOD: Cache expensive operations
@cache.cached(timeout=300)  # 5 minutes
async def get_credibility_model() -> CredibilityModel:
    """Load credibility model once, reuse for all sessions."""
    return await load_model("credibility.pkl")

# Use for session-specific data
async def get_session_knowledge(session_id: str) -> KnowledgeGraph:
    cache_key = f"knowledge:{session_id}"
    cached = await cache.get(cache_key)
    if cached:
        return KnowledgeGraph.from_json(cached)
    
    knowledge = await build_knowledge_graph(session_id)
    await cache.set(cache_key, knowledge.to_json(), timeout=3600)
    return knowledge

# ❌ BAD: No caching of expensive operations
async def get_credibility_model():
    return await load_model("credibility.pkl")  # Loads every time!
```

---

## 12. Error Handling Hierarchy

### Be Specific About Errors

```python
# ✅ GOOD: Specific exceptions with context
class ResearchError(Exception):
    """Base research error."""
    pass

class SearchAPIError(ResearchError):
    """Search API failed."""
    pass

class SearchAPIRateLimitError(SearchAPIError):
    """Rate limit exceeded."""
    def __init__(self, retry_after: int):
        self.retry_after = retry_after

class SearchAPITimeoutError(SearchAPIError):
    """Search timed out."""
    def __init__(self, timeout: float):
        self.timeout = timeout

# Handle with precision
try:
    results = await search(query)
except SearchAPIRateLimitError as e:
    await asyncio.sleep(e.retry_after)
    return await search(query)  # Retry
except SearchAPITimeoutError as e:
    logger.warning(f"Search timed out after {e.timeout}s")
    return []  # Return empty, continue with what we have
except SearchAPIError as e:
    logger.error(f"Search API error: {e}")
    raise

# ❌ BAD: Broad exception handling
try:
    results = await search(query)
except Exception as e:
    logger.error(f"Error: {e}")
    return []
    # Can't distinguish between rate limit and real error
```

### Failure Modes

```python
# ✅ GOOD: Graceful degradation
async def execute_iteration(session_id: str) -> IterationResult:
    """Execute iteration, gracefully handling partial failures."""
    
    sources = await search_agent.search(query)
    if not sources:
        logger.warning(f"No sources found for query: {query}")
        return IterationResult(sources=[], claims=[], next_action="STOP")
    
    try:
        claims = await claim_extractor.extract(sources)
    except LLMAPIError as e:
        logger.warning(f"Claim extraction failed: {e}, continuing with 0 claims")
        claims = []
    
    if not claims and not sources:
        return IterationResult(sources=sources, claims=[], next_action="STOP")
    
    graph = await knowledge_fusion.fuse(claims)
    return IterationResult(sources=sources, claims=claims, next_action=decide_next(graph))

# ❌ BAD: Single failure kills entire iteration
async def execute_iteration(session_id):
    sources = search_agent.search(query)  # Fails → whole iteration fails
    claims = claim_extractor.extract(sources)
    graph = knowledge_fusion.fuse(claims)
    # If any step fails, exception bubbles up
```

---

## 13. Configuration & Secrets Management

### Environment Variables

```python
# ✅ GOOD: Centralized config, sensible defaults
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Keys (required, no defaults)
    ANTHROPIC_API_KEY: str
    SEARCH_API_KEY: str
    
    # Optional with defaults
    SEARCH_RATE_LIMIT: int = 50
    MAX_RESEARCH_TIME_MINUTES: int = 10
    RESEARCH_TIMEOUT_SECONDS: int = 600
    
    # Database
    DATABASE_URL: str = "postgresql://localhost/research"
    DATABASE_POOL_SIZE: int = 20
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"

# ❌ BAD: Scattered config values
API_KEY = os.getenv("ANTHROPIC_API_KEY")  # No default, could be None
SEARCH_LIMIT = 50  # Hardcoded, can't change
DATABASE_URL = "postgresql://localhost/research"  # Hardcoded
```

### Never Commit Secrets

```bash
# ✅ GOOD: .gitignore
.env
.env.local
*.pem
secrets/

# ✅ GOOD: Use .env.example
# .env.example (safe to commit)
ANTHROPIC_API_KEY=sk_test_placeholder
SEARCH_API_KEY=your_key_here

# ❌ BAD: Secrets in code
api_key = "sk-proj-real-secret-key-12345"  # NEVER!
```

---

## 14. Documentation Standards

### Code Comments

```python
# ✅ GOOD: Explain WHY, not WHAT
def select_next_action(knowledge_state: KnowledgeState) -> str:
    """
    Select the next research action based on knowledge quality.
    
    Decision logic (JEV):
    - If contradictions exist, resolve them first (VERIFY)
    - If coverage < 65%, expand search (SEARCH)
    - If knowledge gaps detected, target them (EXPAND_QUERY)
    - Otherwise, stop (STOP)
    
    This greedy heuristic prioritizes contradiction resolution
    and coverage expansion, which empirically yields better reports.
    """
    if has_contradictions(knowledge_state):
        return "VERIFY"
    elif coverage(knowledge_state) < 0.65:
        return "SEARCH"
    elif has_gaps(knowledge_state):
        return "EXPAND_QUERY"
    else:
        return "STOP"

# ❌ BAD: Comments state the obvious
def select_next_action(state):
    # Check if contradictions exist
    if has_contradictions(state):  # Obviously checking!
        return "VERIFY"  # Obviously returning VERIFY!
```

### README Documentation

```markdown
# Self-Correcting Research Agent

## What It Does
[Clear explanation of the system's purpose]

## Quick Start
1. Clone repo
2. Configure environment (.env)
3. Run: `docker-compose up`
4. Open http://localhost:3000

## Architecture
[Link to architecture.md]

## Development
[How to set up dev environment, run tests]

## Deployment
[How to deploy to production]

## Troubleshooting
[Common issues and solutions]
```

---

## 15. Deployment Checklist

Before deploying to production:

- [ ] All tests pass (`pytest` + `npm test`)
- [ ] Code linted and formatted (`black`, `ruff`, `prettier`)
- [ ] Type checks pass (`mypy`, `tsc`)
- [ ] Environment variables documented in `.env.example`
- [ ] Database migrations tested on clean DB
- [ ] Error monitoring configured (Sentry)
- [ ] Performance monitored (Datadog / New Relic)
- [ ] API rate limiting configured
- [ ] CORS configured properly
- [ ] HTTPS enforced
- [ ] Input validation on all endpoints
- [ ] API docs generated and readable
- [ ] Secrets never logged
- [ ] Database backups automated
- [ ] Rollback plan prepared

---

## 16. Anti-Patterns to Avoid

### Don't Do These

| Anti-Pattern | Why Bad | Better Approach |
|---|---|---|
| Global state in modules | Hard to test, unpredictable | Dependency injection, context managers |
| Monolithic functions >200 lines | Hard to understand, untestable | Split into smaller, named functions |
| Magic strings/numbers | Unclear meaning, hard to maintain | Named constants with clear purpose |
| Async/sync mixing | Causes deadlocks, slow operations | All async or all sync, be consistent |
| Silent failures | Hidden bugs, hard to debug | Explicit error handling with logging |
| Tight coupling to APIs | Hard to test, vendor lock-in | Adapter pattern, dependency injection |
| Premature optimization | Wastes time, adds complexity | Profile first, optimize where it matters |
| TODO comments | Never get addressed, clutter code | Create issues instead, fix or remove |

---

## 17. Success Criteria Checklist

A V1 implementation is ready if:

- [ ] **All "Must Have" features** from PRD implemented
- [ ] **Code is readable**: Any developer can understand it in 2 minutes
- [ ] **Tests pass**: 70%+ coverage, critical paths at 100%
- [ ] **Errors are handled**: No unhandled exceptions, graceful degradation
- [ ] **Performance meets targets**: 95% of sessions <8 minutes
- [ ] **Database is clean**: No N+1 queries, proper indexing
- [ ] **APIs are documented**: OpenAPI/Swagger docs generated
- [ ] **Deployment works**: Can deploy to production with one command
- [ ] **Monitoring is set up**: Errors and performance tracked
- [ ] **Security reviewed**: No secrets logged, input validated
- [ ] **README is complete**: New dev can start in 15 minutes

---

**Document Version:** 1.0  
**Last Updated:** September 26, 2026  
**Owner:** MASTER  
**Status:** Ready for Development
