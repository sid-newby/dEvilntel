"""
DevIntel: Development Intelligence System with DSPy Integration
Captures console logs, errors, and dev context to build a knowledge graph of solutions
"""

import json
import asyncio
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

import dspy
from dspy.functional import TypedPredictor
from pydantic import BaseModel, Field
import redis.asyncio as redis
import asyncpg
from neo4j import AsyncGraphDatabase
import numpy as np
from sentence_transformers import SentenceTransformer

# Initialize DSPy with preferred model
dspy.settings.configure(lm=dspy.OpenAI(model="gpt-4.1", temperature=0.3))

# ============= Data Models =============

class EventType(Enum):
    LOG = "log"
    ERROR = "error"
    WARN = "warn"
    NETWORK = "network"
    PERFORMANCE = "performance"
    SOLUTION_ATTEMPT = "solution_attempt"
    SOLUTION_OUTCOME = "solution_outcome"

@dataclass
class DevEvent:
    """Core event structure for all captured development events"""
    id: str
    type: EventType
    timestamp: datetime
    session_id: str
    content: Dict[str, Any]
    stack_trace: Optional[str]
    context: Dict[str, Any]
    embedding: Optional[np.ndarray] = None
    
    def to_changelog_entry(self) -> Dict[str, Any]:
        """Convert to changelog format for graphing"""
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "content": self.content,
            "context": self.context,
            "hash": hashlib.sha256(
                json.dumps(self.content, sort_keys=True).encode()
            ).hexdigest()
        }

# ============= DSPy Components =============

class ErrorContext(BaseModel):
    """Input model for error analysis"""
    error_message: str = Field(desc="The error message")
    stack_trace: str = Field(desc="Stack trace if available")
    code_context: str = Field(desc="Surrounding code context")
    framework: str = Field(desc="Framework being used")
    recent_actions: List[str] = Field(desc="Recent console logs/actions")

class SolutionSuggestion(BaseModel):
    """Output model for suggested solutions"""
    root_cause: str = Field(desc="Identified root cause")
    solution_code: str = Field(desc="Suggested fix code")
    explanation: str = Field(desc="Why this solution should work")
    confidence: float = Field(desc="Confidence score 0-1")
    similar_cases: List[str] = Field(desc="IDs of similar resolved cases")
    pattern_name: str = Field(desc="Common pattern name if identified")

class ErrorAnalyzer(dspy.Signature):
    """Analyze development errors and suggest solutions"""
    error_context: ErrorContext = dspy.InputField()
    solution: SolutionSuggestion = dspy.OutputField()

class PatternIdentifier(dspy.Signature):
    """Identify common development patterns and anti-patterns"""
    events: List[Dict[str, Any]] = dspy.InputField(desc="Recent development events")
    pattern_name: str = dspy.OutputField(desc="Identified pattern name")
    pattern_type: str = dspy.OutputField(desc="Pattern type: smell|solution|practice")
    description: str = dspy.OutputField(desc="Pattern description")

# ============= Storage Layer =============

class StorageBackend:
    """Unified storage interface for Redis, PostgreSQL, and Neo4j"""
    
    def __init__(self):
        self.redis_client = None
        self.pg_pool = None
        self.neo4j_driver = None
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
    async def initialize(self):
        """Initialize all storage connections"""
        # Redis for real-time streaming
        self.redis_client = await redis.from_url("redis://localhost:6379")
        
        # PostgreSQL with pgvector for similarity search
        self.pg_pool = await asyncpg.create_pool(
            "postgresql://postgres:dev@localhost:5432/devintel"
        )
        
        # Neo4j for relationship graphs
        self.neo4j_driver = AsyncGraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "password")
        )
        
        # Initialize database schemas
        await self._init_schemas()
    
    async def _init_schemas(self):
        """Initialize database schemas"""
        async with self.pg_pool.acquire() as conn:
            await conn.execute("""
                CREATE EXTENSION IF NOT EXISTS vector;
                
                CREATE TABLE IF NOT EXISTS dev_events (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    session_id TEXT NOT NULL,
                    content JSONB NOT NULL,
                    stack_trace TEXT,
                    context JSONB NOT NULL,
                    embedding vector(384),
                    changelog JSONB NOT NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_events_embedding 
                ON dev_events USING ivfflat (embedding vector_cosine_ops);
                
                CREATE TABLE IF NOT EXISTS solutions (
                    id TEXT PRIMARY KEY,
                    error_pattern TEXT NOT NULL,
                    solution_code TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    success_rate FLOAT DEFAULT 0,
                    usage_count INTEGER DEFAULT 0,
                    dspy_history JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
    
    async def store_event(self, event: DevEvent):
        """Store event across all backends"""
        # Generate embedding
        event.embedding = self.embedder.encode(
            f"{event.content.get('message', '')} {event.stack_trace or ''}"
        )
        
        # Stream to Redis for real-time processing
        await self.redis_client.xadd(
            "devintel:stream",
            {
                "event": json.dumps(asdict(event)),
                "type": event.type.value
            }
        )
        
        # Store in PostgreSQL for vector search
        async with self.pg_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO dev_events 
                (id, type, timestamp, session_id, content, stack_trace, context, embedding, changelog)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, 
                event.id, event.type.value, event.timestamp, event.session_id,
                json.dumps(event.content), event.stack_trace, json.dumps(event.context),
                event.embedding.tolist(), json.dumps(event.to_changelog_entry())
            )
        
        # Create graph relationships in Neo4j
        async with self.neo4j_driver.session() as session:
            await session.run("""
                MERGE (e:Event {id: $id})
                SET e.type = $type,
                    e.timestamp = $timestamp,
                    e.session_id = $session_id
                MERGE (s:Session {id: $session_id})
                CREATE (e)-[:BELONGS_TO]->(s)
            """, 
                id=event.id, type=event.type.value, 
                timestamp=event.timestamp.isoformat(), session_id=event.session_id
            )

# ============= Intelligence Layer =============

class DevIntelligence:
    """Main intelligence system using DSPy"""
    
    def __init__(self, storage: StorageBackend):
        self.storage = storage
        self.error_analyzer = TypedPredictor(ErrorAnalyzer)
        self.pattern_identifier = TypedPredictor(PatternIdentifier)
        self.solution_cache = {}
        
    async def analyze_error(self, event: DevEvent) -> SolutionSuggestion:
        """Analyze error and suggest solution using DSPy"""
        # Get similar past errors
        similar_errors = await self._find_similar_errors(event)
        
        # Get recent context
        recent_events = await self._get_recent_events(event.session_id)
        
        # Prepare context for DSPy
        error_context = ErrorContext(
            error_message=event.content.get("message", ""),
            stack_trace=event.stack_trace or "",
            code_context=event.content.get("code_context", ""),
            framework=event.context.get("framework", {}).get("name", "unknown"),
            recent_actions=[e["content"].get("message", "") for e in recent_events[-10:]]
        )
        
        # Use DSPy to analyze and suggest solution
        with dspy.context(track_history=True):
            solution = self.error_analyzer(error_context=error_context)
            
            # Store DSPy history for learning
            history = dspy.settings.get_history()
            await self._store_solution_attempt(event, solution.solution, history)
        
        return solution.solution
    
    async def identify_patterns(self, session_id: str) -> Dict[str, Any]:
        """Identify patterns in development session"""
        events = await self._get_recent_events(session_id, limit=50)
        
        with dspy.context(track_history=True):
            pattern_result = self.pattern_identifier(events=events)
            
        # Update pattern graph
        await self._update_pattern_graph(
            pattern_result.pattern_name,
            pattern_result.pattern_type,
            pattern_result.description,
            session_id
        )
        
        return {
            "pattern": pattern_result.pattern_name,
            "type": pattern_result.pattern_type,
            "description": pattern_result.description
        }
    
    async def _find_similar_errors(self, event: DevEvent) -> List[Dict[str, Any]]:
        """Find similar errors using vector search"""
        async with self.storage.pg_pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT id, content, stack_trace, 
                       1 - (embedding <=> $1::vector) as similarity
                FROM dev_events
                WHERE type = 'error'
                AND id != $2
                ORDER BY embedding <=> $1::vector
                LIMIT 5
            """, event.embedding.tolist(), event.id)
            
            return [dict(r) for r in results]
    
    async def _get_recent_events(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent events from session"""
        async with self.storage.pg_pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT * FROM dev_events
                WHERE session_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
            """, session_id, limit)
            
            return [dict(r) for r in results]
    
    async def _store_solution_attempt(self, event: DevEvent, solution: SolutionSuggestion, dspy_history: Any):
        """Store solution attempt with DSPy history"""
        solution_id = f"sol_{event.id}"
        
        async with self.storage.pg_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO solutions 
                (id, error_pattern, solution_code, explanation, dspy_history)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE
                SET usage_count = solutions.usage_count + 1
            """,
                solution_id, event.content.get("message", ""),
                solution.solution_code, solution.explanation,
                json.dumps({"history": str(dspy_history), "confidence": solution.confidence})
            )
        
        # Create solution relationship in graph
        async with self.storage.neo4j_driver.session() as session:
            await session.run("""
                MATCH (e:Event {id: $error_id})
                MERGE (s:Solution {id: $solution_id})
                SET s.code = $code,
                    s.confidence = $confidence
                CREATE (e)-[:SOLVED_BY {timestamp: $timestamp}]->(s)
            """,
                error_id=event.id, solution_id=solution_id,
                code=solution.solution_code, confidence=solution.confidence,
                timestamp=datetime.now().isoformat()
            )
    
    async def _update_pattern_graph(self, pattern_name: str, pattern_type: str, description: str, session_id: str):
        """Update pattern relationships in graph"""
        async with self.storage.neo4j_driver.session() as session:
            await session.run("""
                MERGE (p:Pattern {name: $name})
                SET p.type = $type,
                    p.description = $description,
                    p.last_seen = $timestamp
                WITH p
                MATCH (s:Session {id: $session_id})
                CREATE (s)-[:EXHIBITS_PATTERN {timestamp: $timestamp}]->(p)
            """,
                name=pattern_name, type=pattern_type, description=description,
                session_id=session_id, timestamp=datetime.now().isoformat()
            )

# ============= Changelog & Reporting =============

class ChangelogGenerator:
    """Generate and track changelogs for graphing"""
    
    def __init__(self, storage: StorageBackend):
        self.storage = storage
    
    async def generate_session_changelog(self, session_id: str) -> Dict[str, Any]:
        """Generate comprehensive changelog for a session"""
        async with self.storage.pg_pool.acquire() as conn:
            events = await conn.fetch("""
                SELECT changelog FROM dev_events
                WHERE session_id = $1
                ORDER BY timestamp
            """, session_id)
            
        # Group by patterns
        patterns = await self._identify_changelog_patterns([e['changelog'] for e in events])
        
        # Generate success metrics
        metrics = await self._calculate_success_metrics(session_id)
        
        return {
            "session_id": session_id,
            "event_count": len(events),
            "patterns": patterns,
            "metrics": metrics,
            "timeline": [e['changelog'] for e in events]
        }
    
    async def _identify_changelog_patterns(self, changelogs: List[Dict]) -> Dict[str, int]:
        """Identify patterns in changelog entries"""
        patterns = {}
        for log in changelogs:
            pattern_key = f"{log['type']}:{log.get('content', {}).get('pattern', 'unknown')}"
            patterns[pattern_key] = patterns.get(pattern_key, 0) + 1
        return patterns
    
    async def _calculate_success_metrics(self, session_id: str) -> Dict[str, Any]:
        """Calculate success metrics for solutions"""
        async with self.storage.neo4j_driver.session() as session:
            result = await session.run("""
                MATCH (s:Session {id: $session_id})-[:BELONGS_TO]-(e:Event)-[:SOLVED_BY]->(sol:Solution)
                OPTIONAL MATCH (sol)-[:RESULTED_IN]->(o:Outcome)
                RETURN COUNT(DISTINCT sol) as solution_count,
                       AVG(sol.confidence) as avg_confidence,
                       COUNT(CASE WHEN o.success = true THEN 1 END) as successful_solutions
            """, session_id=session_id)
            
            record = await result.single()
            return dict(record) if record else {}

# ============= API & Integration =============

class DevIntelAPI:
    """REST API for browser extension and MCP integration"""
    
    def __init__(self):
        self.storage = StorageBackend()
        self.intelligence = DevIntelligence(self.storage)
        self.changelog = ChangelogGenerator(self.storage)
    
    async def initialize(self):
        """Initialize all components"""
        await self.storage.initialize()
    
    async def ingest_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest event from browser extension"""
        # Create DevEvent
        event = DevEvent(
            id=f"evt_{datetime.now().timestamp()}_{raw_event.get('type')}",
            type=EventType(raw_event.get('type', 'log')),
            timestamp=datetime.now(),
            session_id=raw_event.get('session_id'),
            content=raw_event.get('content', {}),
            stack_trace=raw_event.get('stack_trace'),
            context=raw_event.get('context', {})
        )
        
        # Store event
        await self.storage.store_event(event)
        
        # Analyze if error
        if event.type == EventType.ERROR:
            solution = await self.intelligence.analyze_error(event)
            return {
                "event_id": event.id,
                "solution": asdict(solution),
                "changelog": event.to_changelog_entry()
            }
        
        return {
            "event_id": event.id,
            "status": "stored",
            "changelog": event.to_changelog_entry()
        }
    
    async def get_patterns(self, session_id: str) -> Dict[str, Any]:
        """Get identified patterns for session"""
        return await self.intelligence.identify_patterns(session_id)
    
    async def get_changelog(self, session_id: str) -> Dict[str, Any]:
        """Get session changelog for graphing"""
        return await self.changelog.generate_session_changelog(session_id)
    
    async def record_outcome(self, solution_id: str, success: bool, metrics: Dict[str, Any]):
        """Record solution outcome for learning"""
        async with self.storage.neo4j_driver.session() as session:
            await session.run("""
                MATCH (s:Solution {id: $solution_id})
                CREATE (o:Outcome {
                    id: $outcome_id,
                    success: $success,
                    metrics: $metrics,
                    timestamp: $timestamp
                })
                CREATE (s)-[:RESULTED_IN]->(o)
            """,
                solution_id=solution_id,
                outcome_id=f"out_{datetime.now().timestamp()}",
                success=success,
                metrics=json.dumps(metrics),
                timestamp=datetime.now().isoformat()
            )
        
        # Update solution success rate
        async with self.storage.pg_pool.acquire() as conn:
            await conn.execute("""
                UPDATE solutions
                SET success_rate = (
                    SELECT AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)
                    FROM (
                        SELECT (o->>'success')::boolean as success
                        FROM solutions s2, 
                             jsonb_array_elements(
                                 COALESCE(s2.dspy_history->'outcomes', '[]'::jsonb)
                             ) as o
                        WHERE s2.id = solutions.id
                    ) outcomes
                )
                WHERE id = $1
            """, solution_id)

# ============= Browser Extension Interface =============

BROWSER_INJECTION_SCRIPT = """
// DevIntel Browser Injection Script
class DevIntel {
    constructor(endpoint = 'http://localhost:8000') {
        this.endpoint = endpoint;
        this.sessionId = this.generateSessionId();
        this.buffer = [];
        this.batchSize = 10;
        this.flushInterval = 5000;
        
        this.init();
    }
    
    generateSessionId() {
        return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
    
    init() {
        this.interceptConsole();
        this.interceptErrors();
        this.interceptNetwork();
        this.startBatchProcessor();
        
        console.log(`%c DevIntel Activated | Session: ${this.sessionId} `, 'background: #667eea; color: white; padding: 2px 5px; border-radius: 3px;');
    }
    
    interceptConsole() {
        const originalConsole = {...console};
        Object.keys(originalConsole).forEach(level => {
            if (typeof originalConsole[level] === 'function') {
                console[level] = (...args) => {
                    originalConsole[level](...args);
                    this.captureEvent('log', {
                        level: level,
                        message: args.map(arg => this.formatArg(arg)).join(' ')
                    });
                };
            }
        });
    }
    
    interceptErrors() {
        window.addEventListener('error', event => {
            this.captureEvent('error', {
                message: event.message,
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
            }, event.error ? event.error.stack : null);
        });
        
        window.addEventListener('unhandledrejection', event => {
            this.captureEvent('error', {
                message: `Unhandled promise rejection: ${event.reason}`,
            }, event.reason ? event.reason.stack : null);
        });
    }
    
    interceptNetwork() {
        const originalFetch = window.fetch;
        window.fetch = (...args) => {
            const startTime = Date.now();
            return originalFetch(...args).then(response => {
                const duration = Date.now() - startTime;
                this.captureEvent('network', {
                    url: response.url,
                    status: response.status,
                    duration: duration,
                    method: args.method || 'GET'
                });
                return response;
            }).catch(error => {
                this.captureEvent('network', {
                    url: args.url,
                    error: error.message,
                    method: args.method || 'GET'
                });
                throw error;
            });
        };
    }
    
    captureEvent(type, content, stack_trace = null) {
        const event = {
            type: type,
            timestamp: new Date().toISOString(),
            session_id: this.sessionId,
            content: content,
            stack_trace: stack_trace,
            context: {
                url: window.location.href,
                userAgent: navigator.userAgent,
                framework: this.detectFramework()
            }
        };
        
        this.buffer.push(event);
        if (this.buffer.length >= this.batchSize) {
            this.flushBuffer();
        }
    }
    
    flushBuffer() {
        if (this.buffer.length === 0) return;
        
        // Use WebSocket if available, otherwise fallback to fetch
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({type: 'bulk', events: this.buffer}));
        } else {
            fetch(`${this.endpoint}/ingest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ events: this.buffer })
            });
        }
        
        this.buffer = [];
    }
    
    startBatchProcessor() {
        setInterval(() => this.flushBuffer(), this.flushInterval);
        
        // Connect WebSocket
        this.ws = new WebSocket(this.endpoint.replace('http', 'ws') + '/ws');
        this.ws.onopen = () => {
            this.ws.send(JSON.stringify({
                type: 'init',
                sessionId: this.sessionId,
                source: 'browser',
                url: window.location.href,
                userAgent: navigator.userAgent
            }));
        };
        
        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            if (message.type === 'solution') {
                this.displaySolution(message);
            }
        };
    }
    
    displaySolution(solutionData) {
        const { solution } = solutionData;
        console.groupCollapsed(`%c DevIntel Solution (Confidence: ${solution.confidence.toFixed(2)}) `, 'background: #2e7d32; color: white; padding: 2px 5px; border-radius: 3px;');
        console.log(`%cRoot Cause:`, 'font-weight: bold;', solution.root_cause);
        console.log(`%cSuggested Fix:`, 'font-weight: bold;');
        console.log(`%c${solution.solution_code}`, 'font-family: monospace; background: #222; padding: 5px; border-radius: 3px;');
        console.log(`%cExplanation:`, 'font-weight: bold;', solution.explanation);
        console.groupEnd();
    }
    
    detectFramework() {
        if (window.React) return { name: 'React', version: window.React.version };
        if (window.Vue) return { name: 'Vue', version: window.Vue.version };
        if (window.angular) return { name: 'Angular', version: window.angular.version.full };
        return { name: 'unknown' };
    }
    
    formatArg(arg) {
        if (arg instanceof Error) {
            return arg.stack || arg.message;
        }
        try {
            return JSON.stringify(arg, null, 2);
        } catch {
            return String(arg);
        }
    }
}

// Initialize DevIntel
if (!window.devIntel) {
    window.devIntel = new DevIntel();
}
"""