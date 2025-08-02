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
        
        console.log('[DevIntel] Initialized with session:', this.sessionId);
    }
    
    interceptConsole() {
        ['log', 'error', 'warn', 'debug'].forEach(method => {
            const original = console[method];
            console[method] = (...args) => {
                this.capture({
                    type: method === 'log' ? 'log' : method,
                    content: {
                        message: args.map(arg => 
                            typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
                        ).join(' '),
                        args: args
                    },
                    stack_trace: method === 'error' ? new Error().stack : null,
                    context: this.gatherContext()
                });
                original.apply(console, args);
            };
        });
    }
    
    interceptErrors() {
        window.addEventListener('error', (event) => {
            this.capture({
                type: 'error',
                content: {
                    message: event.message,
                    filename: event.filename,
                    line: event.lineno,
                    column: event.colno
                },
                stack_trace: event.error?.stack,
                context: this.gatherContext()
            });
        });
        
        window.addEventListener('unhandledrejection', (event) => {
            this.capture({
                type: 'error',
                content: {
                    message: 'Unhandled Promise Rejection',
                    reason: event.reason
                },
                stack_trace: event.reason?.stack,
                context: this.gatherContext()
            });
        });
    }
    
    interceptNetwork() {
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            const startTime = performance.now();
            try {
                const response = await originalFetch(...args);
                const duration = performance.now() - startTime;
                
                if (!response.ok) {
                    this.capture({
                        type: 'network',
                        content: {
                            url: args[0],
                            status: response.status,
                            statusText: response.statusText,
                            duration: duration
                        },
                        context: this.gatherContext()
                    });
                }
                
                return response;
            } catch (error) {
                this.capture({
                    type: 'network',
                    content: {
                        url: args[0],
                        error: error.message,
                        duration: performance.now() - startTime
                    },
                    stack_trace: error.stack,
                    context: this.gatherContext()
                });
                throw error;
            }
        };
    }
    
    gatherContext() {
        return {
            url: location.href,
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString(),
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            },
            framework: this.detectFramework(),
            performance: {
                memory: performance.memory,
                navigation: performance.getEntriesByType('navigation')[0]
            }
        };
    }
    
    detectFramework() {
        if (window.React) return { name: 'React', version: window.React.version };
        if (window.Vue) return { name: 'Vue', version: window.Vue.version };
        if (window.angular) return { name: 'Angular', version: window.angular.version };
        if (window.Ember) return { name: 'Ember', version: window.Ember.VERSION };
        return { name: 'vanilla', version: null };
    }
    
    capture(event) {
        this.buffer.push({
            ...event,
            session_id: this.sessionId
        });
        
        if (this.buffer.length >= this.batchSize) {
            this.flush();
        }
    }
    
    async flush() {
        if (this.buffer.length === 0) return;
        
        const events = [...this.buffer];
        this.buffer = [];
        
        try {
            const response = await fetch(`${this.endpoint}/ingest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ events })
            });
            
            if (response.ok) {
                const results = await response.json();
                // Show solutions in console if available
                results.forEach(result => {
                    if (result.solution) {
                        console.log(
                            '%c[DevIntel Solution]%c ' + result.solution.root_cause,
                            'background: #4CAF50; color: white; padding: 2px 4px; border-radius: 2px;',
                            'color: #4CAF50; font-weight: bold;'
                        );
                        console.log('Fix:', result.solution.solution_code);
                        console.log('Confidence:', result.solution.confidence);
                    }
                });
            }
        } catch (error) {
            // Silently fail to not disrupt user experience
            console.debug('[DevIntel] Failed to send events:', error);
        }
    }
    
    startBatchProcessor() {
        setInterval(() => this.flush(), this.flushInterval);
        
        // Flush on page unload
        window.addEventListener('beforeunload', () => this.flush());
    }
}

// Auto-initialize
if (!window.__devIntel) {
    window.__devIntel = new DevIntel();
}
"""

# ============= FastAPI Server Example =============

SERVER_EXAMPLE = """
# server.py - FastAPI server for DevIntel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="DevIntel API")

# CORS for browser extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Initialize DevIntel
devintel = DevIntelAPI()

@app.on_event("startup")
async def startup():
    await devintel.initialize()

@app.post("/ingest")
async def ingest_events(data: dict):
    results = []
    for event in data.get("events", []):
        result = await devintel.ingest_event(event)
        results.append(result)
    return results

@app.get("/patterns/{session_id}")
async def get_patterns(session_id: str):
    return await devintel.get_patterns(session_id)

@app.get("/changelog/{session_id}")
async def get_changelog(session_id: str):
    return await devintel.get_changelog(session_id)

@app.post("/outcome/{solution_id}")
async def record_outcome(solution_id: str, data: dict):
    await devintel.record_outcome(
        solution_id,
        data.get("success", False),
        data.get("metrics", {})
    )
    return {"status": "recorded"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""

# ============= MCP Server Integration =============

MCP_SERVER_INTEGRATION = """
# mcp_devintel.py - MCP Server for DevIntel
import asyncio
from mcp import MCPServer, Tool

class DevIntelMCPServer(MCPServer):
    def __init__(self):
        super().__init__("devintel")
        self.api = DevIntelAPI()
        
    async def initialize(self):
        await self.api.initialize()
        
        # Register tools
        self.register_tool(Tool(
            name="search_errors",
            description="Search for similar errors and solutions",
            parameters={
                "type": "object",
                "properties": {
                    "error_message": {"type": "string"},
                    "stack_trace": {"type": "string"}
                }
            },
            handler=self.search_errors
        ))
        
        self.register_tool(Tool(
            name="get_solution",
            description="Get solution for specific error pattern",
            parameters={
                "type": "object",
                "properties": {
                    "error_id": {"type": "string"}
                }
            },
            handler=self.get_solution
        ))
        
        self.register_tool(Tool(
            name="analyze_patterns",
            description="Analyze patterns in development session",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"}
                }
            },
            handler=self.analyze_patterns
        ))
    
    async def search_errors(self, error_message: str, stack_trace: str = None):
        # Create temporary event for analysis
        event = DevEvent(
            id="temp_search",
            type=EventType.ERROR,
            timestamp=datetime.now(),
            session_id="search",
            content={"message": error_message},
            stack_trace=stack_trace,
            context={}
        )
        
        solution = await self.api.intelligence.analyze_error(event)
        return asdict(solution)
    
    async def get_solution(self, error_id: str):
        # Fetch from storage
        async with self.api.storage.pg_pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT * FROM solutions
                WHERE id = $1
            """, f"sol_{error_id}")
            
            return dict(result) if result else None
    
    async def analyze_patterns(self, session_id: str):
        return await self.api.get_patterns(session_id)

# Run MCP server
if __name__ == "__main__":
    server = DevIntelMCPServer()
    asyncio.run(server.run())
"""
