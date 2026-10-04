# Product Requirements Document: Self-Correcting Research Agent MVP V1

## 1. Project Overview

**Product Name:** Self-Correcting Research Agent

**Vision:** Build an AI-powered research system that autonomously investigates user-defined questions, detects knowledge gaps and contradictions, iteratively refines research, and produces evidence-backed reports with full source attribution.

**Target User:** Researchers, analysts, students, entrepreneurs, and decision-makers who need comprehensive, verified research without manual source hunting.

**V1 Goal:** Establish the core research loop: Question → Search → Knowledge Fusion → Self-Correction → Report

---

## 2. Core Value Proposition

### What Makes This Different

Unlike existing AI search tools that search once and report:

- **Self-Correction**: Detects contradictions and knowledge gaps automatically
- **Structured Knowledge**: Every claim is mapped to sources with confidence levels
- **Iterative Refinement**: Agent decides what to research next based on evidence quality
- **Verification Layer**: Tracks claim certainty and identifies weak evidence
- **Evidence-Driven**: Final report is a knowledge graph, not prose hallucination

### Key Differentiator

This is **not** a chatbot that searches. It's an **autonomous research orchestrator** that:

1. Understands what it doesn't know
2. Decides what to research next
3. Extracts structured claims
4. Detects contradictions
5. Verifies evidence quality
6. Stops when sufficient

---

## 3. User Input Specification

### Minimum Required Input

**Research Question** (required)
- Single text field
- Examples:
  - "Can agricultural waste biomass pellets economically replace coal in Indian thermal power plants?"
  - "Is solar-powered green hydrogen economically viable in India by 2030?"
  - "What are the emerging security threats in quantum computing?"

### Optional Constraints

| Input | Type | Example | Default |
|-------|------|---------|---------|
| Research Depth | Dropdown | Basic / Standard / Deep | Standard |
| Domain | Text | Energy, AI, Healthcare, Finance | Auto-detect |
| Geographic Scope | Text | India, USA, Global | Global |
| Time Range | Date Range | 2020-2026 | Last 5 years |
| Preferred Sources | Multi-select | Papers, Reports, News, Studies | All |
| Maximum Research Time | Slider | 2-10 minutes | 5 min |
| Minimum Sources Required | Number | 5-20 | 10 |
| Output Format | Dropdown | Report / Graph / Both | Report |

### V1 Scope: Keep Input Simple
- Research Question + optional depth
- Constraints are configurable, not mandatory
- Default to sensible values

---

## 4. Core Features (MVP V1)

### Must Have

#### 4.1 Research Initialization
- [ ] User enters research question
- [ ] System validates question quality
- [ ] System generates initial research plan
- [ ] Creates research session with unique ID
- [ ] Displays session tracking UI

#### 4.2 Search & Source Collection
- [ ] Execute web search queries
- [ ] Collect sources with metadata (URL, title, type, date)
- [ ] Parse source content (text extraction)
- [ ] Track source credibility score
- [ ] Store sources in database
- [ ] Avoid duplicate sources

#### 4.3 Knowledge Fusion (IKF Layer)
- [ ] Extract claims from sources
- [ ] Map claims to entities (subject-predicate-object)
- [ ] Track claim confidence (High/Medium/Low)
- [ ] Track claim origin (source ID)
- [ ] Build knowledge graph structure
- [ ] Store claim relationships

#### 4.4 Contradiction & Gap Detection
- [ ] Identify conflicting claims (A supports X, B refutes X)
- [ ] Flag contradictions with supporting evidence
- [ ] Detect knowledge gaps (missing entities/relationships)
- [ ] Generate gap analysis
- [ ] Suggest next research areas

#### 4.5 Decision Layer (JEV)
- [ ] Evaluate current knowledge state
- [ ] Define available actions:
  - SEARCH (new angle)
  - VERIFY (weak claims)
  - EXPAND_QUERY (related topics)
  - LOOK_FOR_PRIMARY_SOURCE
  - CHECK_CONTRADICTION
  - SEARCH_FOR_MISSING_DATA
  - STOP (sufficient evidence)
- [ ] Select next action based on state
- [ ] Log decision reasoning

#### 4.6 Self-Correction Loop
- [ ] Iterate: Search → Extract → Fuse → Detect → Decide
- [ ] Track iteration count
- [ ] Monitor information gain per iteration
- [ ] Stop when:
  - Information gain below threshold
  - Knowledge coverage > 80%
  - Contradictions resolved
  - Maximum iterations reached
  - Time limit exceeded

#### 4.7 Report Generation
- [ ] Executive summary (2-3 sentences)
- [ ] Evidence table (Claim → Source → Confidence)
- [ ] Knowledge graph visualization
- [ ] Contradiction analysis
- [ ] Remaining unknowns
- [ ] Full source citations with links
- [ ] Research methodology notes

#### 4.8 Session Management
- [ ] Create, retrieve, list research sessions
- [ ] Track session status (running, completed, error)
- [ ] Store session metadata (timestamps, constraints, results)
- [ ] Allow session resumption (partial support in V1)

### Should Have

- [ ] Progress indicators (% complete, iteration count, steps taken)
- [ ] Real-time session updates (WebSocket or polling)
- [ ] Search history within session (transparent to user)
- [ ] Claim confidence distribution chart
- [ ] Source type breakdown
- [ ] Basic error recovery (re-run failed searches)

### Nice to Have (Post-V1)

- [ ] Voice input
- [ ] Export to PDF/Word
- [ ] Collaborative research (multi-user sessions)
- [ ] Saved research templates
- [ ] Research comparison (side-by-side)
- [ ] RL training dashboard
- [ ] API rate limiting dashboard

### Explicitly Do Not Build Yet

- [ ] Full autonomous browser control
- [ ] OS-level desktop control
- [ ] Multi-agent swarm
- [ ] Complex RL training loop
- [ ] Custom foundation model training
- [ ] Long-running autonomous research (>24 hours)
- [ ] Real-time knowledge sync across users
- [ ] Mobile app (web responsive only)
- [ ] Voice interface
- [ ] Sentiment analysis
- [ ] Fake news detection ML
- [ ] Geographic map visualization

---

## 5. Data Model Overview

### Core Entities

1. **User**: Email, auth, preferences
2. **ResearchSession**: Question, depth, constraints, status
3. **Source**: URL, title, content, credibility score, type
4. **Claim**: Text, confidence, status, extracted from sources
5. **KnowledgeNode**: Entity in the knowledge graph
6. **KnowledgeEdge**: Relationship between nodes
7. **ResearchAction**: Type, query, result, reward
8. **Decision**: State, actions available, action selected, reasoning

### Key Relationships

```
User
  ├── ResearchSession (1:N)
      ├── Source (1:N)
      ├── Claim (1:N)
      │   └── ClaimSource (N:N)
      ├── KnowledgeNode (1:N)
      ├── KnowledgeEdge (1:N)
      ├── ResearchAction (1:N)
      └── Decision (1:N)
```

---

## 6. User Experience Flow

### Session Lifecycle

```
1. Enter Question
   └─> Validate
       └─> Initialize Session

2. Generate Research Plan
   └─> Display initial queries

3. Iterative Research Loop
   ├─> Execute Search
   ├─> Parse Sources
   ├─> Extract Claims
   ├─> Fuse to Knowledge Graph
   ├─> Detect Gaps & Contradictions
   ├─> Decide Next Action
   ├─> Show Progress
   └─> Repeat (until stop condition)

4. Generate Report
   └─> Display Results
       └─> Show Knowledge Graph
       └─> Show Evidence Table
       └─> Show Contradictions
       └─> Show Citations
```

### Visual Feedback

**Real-Time Progress Display:**
- Current research step (e.g., "Searching for recent studies...")
- Iteration counter (Step 3/8)
- Information gain meter (visual bar)
- Source count tracker
- Claim count tracker
- Contradiction alerts (real-time)
- Time elapsed

**Example:**
```
Researching: "Can biomass replace coal in India?"

▶ Step 3: Extracting claims from coal consumption reports...

Progress:
├─ Sources collected: 12
├─ Claims extracted: 24
├─ Knowledge coverage: 65%
├─ Contradictions detected: 2
├─ Time elapsed: 2:15

Next action: Searching for government policy documents...
```

---

## 7. Success Metrics (V1)

### Engineering Metrics

1. **Research Efficiency**: Information Gain / Number of Searches
   - Target: >0.5 new claims per search in early iterations, declining to <0.2 by convergence

2. **Evidence Quality**: % of Claims Backed by Sources
   - Target: >90% of final report claims have direct source attribution

3. **Self-Correction Rate**: % of Detected Contradictions → Triggered Research
   - Target: >80% of contradictions trigger follow-up searches

4. **Redundancy**: % of Searches Producing Duplicate Information
   - Target: <15% redundancy by iteration 5

5. **Stopping Efficiency**: Stopping at Sufficient Evidence (not endless search)
   - Target: Algorithm stops within optimal iteration range (not too early, not too late)

### Quality Metrics

1. **Accuracy**: Compare final claims against human-curated reference answers
   - Target: >75% of major claims match reference set

2. **Completeness**: Coverage of key topics for the question
   - Target: >80% of important dimensions are addressed

3. **Contradiction Resolution**: Contradictions resolved vs. unresolved
   - Target: >70% of contradictions resolved with reasoning

### User Metrics

1. **Time to Report**: Total time from question to final report
   - Target: 2-8 minutes for standard depth, <15 minutes for deep

2. **Session Completion Rate**: % of sessions that generate a report
   - Target: >90%

3. **User Satisfaction** (post-V1, via feedback): Is the report useful?

---

## 8. Technical Constraints & Assumptions

### Constraints

- **Search API**: Rate limited to ~50 queries per session
- **Time Limit**: 10 minute maximum per research session
- **Database**: PostgreSQL with pgvector for embeddings
- **Scalability**: Support ~100 concurrent users initially
- **Latency**: 80% of sessions complete within 8 minutes
- **Uptime**: 99.5% uptime target

### Assumptions

- Users will ask well-formed research questions (not gibberish)
- Web search APIs are available and reliable
- Sources are text-based (no video, image-only sources in V1)
- English language primarily (expansion later)
- Users trust LLM claim extraction (with manual override in V2)

---

## 9. RL Integration Notes (Experimental in V1)

### Do Not Spend Engineering Effort on RL in V1

The RL component is **optional and experimental** in V1. Focus on:

1. Building the research loop first (non-RL baseline)
2. Hardcoding decision rules using if/else heuristics
3. Collecting data for future RL training

### RL Placeholder for V1

```python
def select_next_action(knowledge_state):
    """
    Hardcoded decision logic.
    Later: replaced by RL policy.
    """
    if has_contradictions(knowledge_state):
        return "VERIFY"
    elif coverage < 0.65:
        return "SEARCH"
    elif has_gaps(knowledge_state):
        return "EXPAND_QUERY"
    else:
        return "STOP"
```

### Reward Function (Logging Only)

Track these metrics for future RL training:

```
information_gain = new_claims - duplicate_claims
quality_bonus = avg_source_credibility * claim_confidence
contradiction_penalty = unresolved_contradictions * -5
redundancy_penalty = duplicate_info_ratio * -2
action_cost = -0.1  # Small cost per search

reward = information_gain + quality_bonus - contradiction_penalty - redundancy_penalty - action_cost
```

Log rewards per action for offline RL training post-V1.

---

## 10. Glossary

| Term | Definition |
|------|-----------|
| **Research Session** | Single research task with unique ID, question, and results |
| **Claim** | A factual statement extracted from a source (subject-predicate-object) |
| **IKF** | Knowledge Fusion layer - structures claims into a knowledge graph |
| **JEV** | Decision layer - bounded, explicit action selection (not free-form LLM) |
| **Knowledge Graph** | Network of entities and relationships extracted from sources |
| **Information Gain** | New, non-redundant claims added per search |
| **Contradiction** | Two sources supporting opposite claims on the same entity/topic |
| **Knowledge Gap** | Missing information needed to answer the question |
| **Credibility Score** | Quality ranking of a source (0.0-1.0) |
| **Confidence Level** | Certainty of a claim (High/Medium/Low) based on evidence |
| **Self-Correction** | Iterative refinement triggered by gaps or contradictions |

---

## 11. V1 Release Checklist

### Before Launch

- [ ] All "Must Have" features implemented
- [ ] Database schema finalized and migrated
- [ ] Search API integration tested
- [ ] LLM API integration tested
- [ ] Knowledge graph construction working
- [ ] Report generation working end-to-end
- [ ] Error handling for all failure modes
- [ ] Frontend responsive design verified
- [ ] Security: API keys not exposed, input sanitized
- [ ] Performance: Session completes <8 min 95% of time
- [ ] Documentation: API docs, deployment guide, user guide
- [ ] Bug testing: 20+ real research questions tested manually

### Post-V1 Roadmap

**V1.1**: RL foundation + better stopping heuristics
**V1.2**: Export to PDF, research templates
**V2**: Multi-agent research, long-term memory
**V3**: Custom reward learning, advanced NLP

---

## 12. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Search API rate limits | Research halts | Queue searches, implement backoff, cache results |
| Low-quality sources | Poor claims | Credibility filtering, manual source whitelist |
| Hallucinated claims | False conclusions | Require source backing, highlight low-confidence claims |
| Infinite loop | Session never ends | Hard iteration limit, information gain threshold |
| User asks off-topic Q | Wasted resources | Question validation, refuse unsupported domains |
| LLM slow/errors | Poor UX | Timeout handling, fallback to heuristics |
| DB failures | Data loss | Transaction logging, backups every 6 hours |

---

## 13. Success Criteria for V1

The MVP is successful if:

1. **Functional**: System completes research and generates a report for 95% of submitted questions
2. **Self-Correcting**: Detects and responds to ≥70% of actual contradictions in test questions
3. **Useful**: Report contains ≥10 distinct, well-sourced claims per standard question
4. **Efficient**: Completes within 2-10 minutes for 90% of sessions
5. **Accurate**: ≥75% of final claims align with human evaluation
6. **Reliable**: No crashes; graceful error handling for all failure modes
7. **Transparent**: User sees progress, reasoning, sources, and confidence levels

---

## 14. Open Questions for Design Phase

1. Should we support multiple languages in V1, or English-only?
2. Should users be able to interrupt/pause a research session?
3. Should we show the knowledge graph during research, or only in final report?
4. How granular should we make "iteration steps" in the UI? (Too detailed = noise)
5. Should we allow users to add manual sources/claims to the knowledge graph?
6. Should there be a "confidence threshold" filter before generating the report?

---

## 15. Appendix: Example Research Scenario

**User Question:** "Is solar-powered green hydrogen economically viable in India by 2030?"

**V1 System Behavior:**

```
[User submits question]

INITIALIZATION
├─ Question validated ✓
├─ Initial plan generated: 6 search angles
├─ Session ID: sess_a7f9d2

RESEARCH LOOP

Iteration 1: Search for baseline costs
├─ Query: "hydrogen production cost India 2024"
├─ Found: 4 sources
├─ Extracted claims: 8
├─ Coverage: 35%

Iteration 2: Solar electricity costs
├─ Query: "solar electricity cost India 2024"
├─ Found: 3 sources (1 duplicate)
├─ Extracted claims: 5
├─ New claims: 4
├─ Coverage: 52%

Iteration 3: Electrolyzer costs
├─ Query: "electrolyzer cost trends 2024-2026"
├─ Found: 5 sources
├─ Extracted claims: 6
├─ New claims: 5
├─ Coverage: 64%

Iteration 4: Detected contradiction
├─ Study A: $5/kg hydrogen
├─ Study B: $8/kg hydrogen
├─ Reason detected: Different solar price assumptions
├─ Triggering follow-up search...
├─ Query: "hydrogen cost sensitivity analysis solar price"
├─ Found: 2 sources
├─ Contradiction status: Partially resolved

Iteration 5: Government incentives
├─ Query: "India green hydrogen policy targets 2030"
├─ Found: 3 sources
├─ Extracted claims: 7
├─ Coverage: 81%

STOPPING CONDITION
├─ Information gain: <0.3 claims per search (declining)
├─ Coverage: 81% (above target)
├─ Contradictions: 1 resolved, 1 minor
├─ Action: STOP

REPORT GENERATION
├─ Claims verified: 31/34 (91%)
├─ Sources cited: 18
├─ Knowledge graph nodes: 12
├─ Key findings:
│  └─ Viable by 2030 IF solar costs reach $2/kWh (likely)
│  └─ AND electrolyzer costs drop 40% (in progress)
│  └─ Government support critical (multiple sources)

[Report displays with graph, evidence table, citations]
```

---

**Document Version:** 1.0  
**Last Updated:** September 26, 2026  
**Owner:** MASTER  
**Status:** Ready for Design Phase
