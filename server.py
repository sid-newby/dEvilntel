"""
DevIntel Real-time Server with WebSocket Support
Handles Chrome Extension and VSCode connections with live streaming
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, List, Set
from collections import defaultdict
import logging

# Import our DevIntel components
from devintel import DevIntelAPI, DevEvent, EventType

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DevIntel Real-time Server")

# CORS for browser extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.session_connections: Dict[str, Set[str]] = defaultdict(set)
        self.connection_metadata: Dict[str, Dict] = {}
        
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected")
        
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            
            # Remove from session tracking
            session_id = self.connection_metadata.get(client_id, {}).get('session_id')
            if session_id and session_id in self.session_connections:
                self.session_connections[session_id].discard(client_id)
                
            # Clean up metadata
            if client_id in self.connection_metadata:
                del self.connection_metadata[client_id]
                
            logger.info(f"Client {client_id} disconnected")
    
    async def send_personal_message(self, message: str, client_id: str):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(message)
            except Exception as e:
                logger.error(f"Error sending to {client_id}: {e}")
                self.disconnect(client_id)
    
    async def broadcast_to_session(self, message: str, session_id: str):
        """Broadcast message to all connections in a session"""
        if session_id in self.session_connections:
            disconnected = []
            for client_id in self.session_connections[session_id]:
                try:
                    await self.send_personal_message(message, client_id)
                except:
                    disconnected.append(client_id)
            
            # Clean up disconnected clients
            for client_id in disconnected:
                self.disconnect(client_id)
    
    def set_client_metadata(self, client_id: str, metadata: Dict):
        self.connection_metadata[client_id] = metadata
        session_id = metadata.get('session_id')
        if session_id:
            self.session_connections[session_id].add(client_id)

# Real-time event processor
class RealtimeEventProcessor:
    def __init__(self, devintel_api: DevIntelAPI, connection_manager: ConnectionManager):
        self.api = devintel_api
        self.connection_manager = connection_manager
        self.event_buffer = defaultdict(list)
        self.processing = False
        
    async def process_event(self, event_data: Dict, session_id: str):
        """Process incoming event and broadcast results"""
        try:
            # Create DevEvent
            event = DevEvent(
                id=f"evt_{datetime.now().timestamp()}_{event_data.get('type', 'unknown')}",
                type=EventType(event_data.get('type', 'log')),
                timestamp=datetime.now(),
                session_id=session_id,
                content=event_data.get('content', {}),
                stack_trace=event_data.get('stack', event_data.get('stack_trace')),
                context=event_data.get('context', {})
            )
            
            # Store event
            result = await self.api.ingest_event({
                'type': event.type.value,
                'session_id': session_id,
                'content': event.content,
                'stack_trace': event.stack_trace,
                'context': event.context
            })
            
            # If it's an error with a solution, broadcast it
            if event.type == EventType.ERROR and 'solution' in result:
                await self.connection_manager.broadcast_to_session(
                    json.dumps({
                        'type': 'solution',
                        'eventId': event.id,
                        'solution': result['solution']
                    }),
                    session_id
                )
            
            # Broadcast event confirmation
            await self.connection_manager.broadcast_to_session(
                json.dumps({
                    'type': 'event_processed',
                    'eventId': event.id,
                    'status': 'success'
                }),
                session_id
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing event: {e}")
            await self.connection_manager.broadcast_to_session(
                json.dumps({
                    'type': 'error',
                    'message': str(e)
                }),
                session_id
            )
            return None
    
    async def process_bulk_events(self, events: List[Dict], session_id: str):
        """Process multiple events efficiently"""
        results = []
        for event in events:
            result = await self.process_event(event, session_id)
            if result:
                results.append(result)
        return results

# Initialize components
manager = ConnectionManager()
devintel_api = DevIntelAPI()
event_processor = RealtimeEventProcessor(devintel_api, manager)

@app.on_event("startup")
async def startup():
    await devintel_api.initialize()
    logger.info("DevIntel server started")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(uuid.uuid4())
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message['type'] == 'init':
                # Store client metadata
                manager.set_client_metadata(client_id, {
                    'session_id': message.get('sessionId'),
                    'source': message.get('source', 'browser'),
                    'url': message.get('url'),
                    'workspace': message.get('workspace'),
                    'userAgent': message.get('userAgent')
                })
                
                # Send acknowledgment
                await manager.send_personal_message(
                    json.dumps({
                        'type': 'init_ack',
                        'clientId': client_id,
                        'timestamp': datetime.now().isoformat()
                    }),
                    client_id
                )
                
            elif message['type'] == 'event':
                # Process single event
                session_id = manager.connection_metadata.get(client_id, {}).get('session_id')
                if session_id:
                    await event_processor.process_event(message['event'], session_id)
                    
            elif message['type'] == 'bulk':
                # Process bulk events
                session_id = manager.connection_metadata.get(client_id, {}).get('session_id')
                if session_id:
                    await event_processor.process_bulk_events(message['events'], session_id)
                    
            elif message['type'] == 'query':
                # Handle real-time queries
                session_id = manager.connection_metadata.get(client_id, {}).get('session_id')
                if session_id and message.get('query') == 'patterns':
                    patterns = await devintel_api.get_patterns(session_id)
                    await manager.send_personal_message(
                        json.dumps({
                            'type': 'query_result',
                            'query': 'patterns',
                            'result': patterns
                        }),
                        client_id
                    )
                    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(client_id)

# REST endpoints for non-WebSocket clients
@app.post("/ingest")
async def ingest_events(data: dict):
    """Batch ingest events via REST"""
    results = []
    events = data.get("events", [])
    
    for event in events:
        result = await devintel_api.ingest_event(event)
        results.append(result)
    
    return results

@app.get("/patterns/{session_id}")
async def get_patterns(session_id: str):
    """Get identified patterns for session"""
    return await devintel_api.get_patterns(session_id)

@app.get("/changelog/{session_id}")
async def get_changelog(session_id: str):
    """Get session changelog"""
    return await devintel_api.get_changelog(session_id)

@app.post("/outcome/{solution_id}")
async def record_outcome(solution_id: str, data: dict):
    """Record solution outcome"""
    await devintel_api.record_outcome(
        solution_id,
        data.get("success", False),
        data.get("metrics", {})
    )
    return {"status": "recorded"}

# Enhanced dashboard endpoint
@app.get("/dashboard")
async def dashboard():
    """Serve the enhanced dashboard"""
    return HTMLResponse(content=ENHANCED_DASHBOARD_HTML)

# Session analytics endpoint
@app.get("/sessions")
async def get_active_sessions():
    """Get all active sessions with metadata"""
    sessions = {}
    
    for client_id, metadata in manager.connection_metadata.items():
        session_id = metadata.get('session_id')
        if session_id:
            if session_id not in sessions:
                sessions[session_id] = {
                    'id': session_id,
                    'connections': [],
                    'startTime': None,
                    'eventCount': 0
                }
            
            sessions[session_id]['connections'].append({
                'clientId': client_id,
                'source': metadata.get('source', 'unknown'),
                'url': metadata.get('url'),
                'workspace': metadata.get('workspace')
            })
    
    return list(sessions.values())

# Real-time session monitoring
@app.websocket("/ws/monitor")
async def monitor_endpoint(websocket: WebSocket):
    """WebSocket endpoint for monitoring all sessions"""
    monitor_id = str(uuid.uuid4())
    await manager.connect(websocket, monitor_id)
    
    try:
        # Send initial session data
        sessions = await get_active_sessions()
        await websocket.send_text(json.dumps({
            'type': 'sessions',
            'data': sessions
        }))
        
        # Keep connection alive and send updates
        while True:
            await asyncio.sleep(5)  # Send updates every 5 seconds
            sessions = await get_active_sessions()
            await websocket.send_text(json.dumps({
                'type': 'sessions_update',
                'data': sessions
            }))
            
    except WebSocketDisconnect:
        manager.disconnect(monitor_id)

# Enhanced dashboard HTML with real-time features
ENHANCED_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DevIntel Real-time Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            height: 100vh;
            overflow: hidden;
        }
        
        .dashboard-container {
            display: grid;
            grid-template-columns: 250px 1fr 300px;
            height: 100vh;
        }
        
        .sidebar {
            background: #111;
            border-right: 1px solid #222;
            padding: 20px;
            overflow-y: auto;
        }
        
        .main-content {
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .header {
            background: #111;
            padding: 20px;
            border-bottom: 1px solid #222;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .content-area {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }
        
        .right-panel {
            background: #111;
            border-left: 1px solid #222;
            padding: 20px;
            overflow-y: auto;
        }
        
        .session-card {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .session-card:hover {
            border-color: #667eea;
        }
        
        .session-card.active {
            border-color: #667eea;
            background: #1a1a2e;
        }
        
        .event-stream {
            background: #0f0f0f;
            border: 1px solid #222;
            border-radius: 8px;
            padding: 10px;
            height: 400px;
            overflow-y: auto;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 12px;
        }
        
        .event-line {
            padding: 4px 0;
            border-bottom: 1px solid #1a1a1a;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .event-type-badge {
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
            text-transform: uppercase;
        }
        
        .event-type-badge.error { background: #d32f2f; }
        .event-type-badge.log { background: #2e7d32; }
        .event-type-badge.warn { background: #f57c00; }
        .event-type-badge.network { background: #1976d2; }
        .event-type-badge.file { background: #7b1fa2; }
        .event-type-badge.git { background: #ff6f00; }
        
        .connection-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .connection-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4caf50;
            animation: pulse 2s infinite;
        }
        
        .connection-dot.disconnected {
            background: #f44336;
            animation: none;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .filter-bar {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        
        .filter-input {
            flex: 1;
            padding: 8px 12px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 6px;
            color: #e0e0e0;
            font-size: 13px;
        }
        
        .filter-button {
            padding: 8px 16px;
            background: #222;
            border: 1px solid #333;
            border-radius: 6px;
            color: #e0e0e0;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
    </style>
</head>
<body>
    <div class="dashboard-container">
        <div class="sidebar">
            <h2>Sessions</h2>
            <div id="session-list"></div>
        </div>
        <div class="main-content">
            <div class="header">
                <h1 id="current-session-title">Select a Session</h1>
                <div class="connection-indicator">
                    <div id="connection-dot" class="connection-dot disconnected"></div>
                    <span id="connection-status">Disconnected</span>
                </div>
            </div>
            <div class="content-area">
                <div class="filter-bar">
                    <input type="text" id="filter-input" class="filter-input" placeholder="Filter events (regex supported)...">
                    <button class="filter-button" id="error-filter">Errors</button>
                    <button class="filter-button" id="log-filter">Logs</button>
                    <button class="filter-button" id="network-filter">Network</button>
                    <button class="filter-button" id="clear-filter">Clear</button>
                </div>
                <div class="event-stream" id="event-stream"></div>
            </div>
        </div>
        <div class="right-panel">
            <h2>Details</h2>
            <div id="details-panel">Select an event to see details.</div>
        </div>
    </div>
    <script>
        const sessionList = document.getElementById('session-list');
        const eventStream = document.getElementById('event-stream');
        const detailsPanel = document.getElementById('details-panel');
        const connectionDot = document.getElementById('connection-dot');
        const connectionStatus = document.getElementById('connection-status');
        const currentSessionTitle = document.getElementById('current-session-title');
        
        let monitorSocket;
        let sessionSocket;
        let activeSessionId = null;
        let eventFilter = '';

        function connectMonitor() {
            monitorSocket = new WebSocket('ws://localhost:8000/ws/monitor');

            monitorSocket.onopen = () => {
                connectionDot.classList.remove('disconnected');
                connectionStatus.textContent = 'Connected';
            };

            monitorSocket.onmessage = (event) => {
                const message = JSON.parse(event.data);
                if (message.type === 'sessions' || message.type === 'sessions_update') {
                    updateSessionList(message.data);
                }
            };

            monitorSocket.onclose = () => {
                connectionDot.classList.add('disconnected');
                connectionStatus.textContent = 'Disconnected';
                setTimeout(connectMonitor, 5000);
            };
        }

        function updateSessionList(sessions) {
            sessionList.innerHTML = '';
            sessions.forEach(session => {
                const card = document.createElement('div');
                card.className = `session-card ${session.id === activeSessionId ? 'active' : ''}`;
                card.dataset.sessionId = session.id;
                card.innerHTML = `
                    <strong>${session.id}</strong><br>
                    <small>${session.connections.length} connections</small>
                `;
                card.addEventListener('click', () => selectSession(session.id));
                sessionList.appendChild(card);
            });
        }

        function selectSession(sessionId) {
            if (activeSessionId === sessionId) return;
            
            activeSessionId = sessionId;
            currentSessionTitle.textContent = `Session: ${sessionId}`;
            eventStream.innerHTML = '';
            
            document.querySelectorAll('.session-card').forEach(c => c.classList.remove('active'));
            document.querySelector(`.session-card[data-session-id="${sessionId}"]`).classList.add('active');

            if (sessionSocket) {
                sessionSocket.close();
            }
            
            connectToSession(sessionId);
        }

        function connectToSession(sessionId) {
            sessionSocket = new WebSocket(`ws://localhost:8000/ws`);
            
            sessionSocket.onopen = () => {
                sessionSocket.send(JSON.stringify({
                    type: 'init',
                    sessionId: sessionId,
                    source: 'dashboard'
                }));
            };

            sessionSocket.onmessage = (event) => {
                const message = JSON.parse(event.data);
                if (message.type === 'event_processed' || message.type === 'solution') {
                    addEventToStream(message);
                }
            };
        }
        
        function addEventToStream(event) {
            const eventLine = document.createElement('div');
            eventLine.className = 'event-line';
            
            const eventType = event.type === 'solution' ? 'solution' : event.eventId.split('_');
            
            if (eventFilter && !eventType.match(new RegExp(eventFilter, 'i'))) {
                return;
            }

            eventLine.innerHTML = `
                <span class="event-type-badge ${eventType}">${eventType}</span>
                <span>${event.eventId}</span>
            `;
            eventLine.addEventListener('click', () => showEventDetails(event));
            eventStream.appendChild(eventLine);
            eventStream.scrollTop = eventStream.scrollHeight;
        }

        function showEventDetails(event) {
            detailsPanel.innerHTML = `<pre>${JSON.stringify(event, null, 2)}</pre>`;
        }

        // Init
        connectMonitor();
        
        // Filters
        document.getElementById('filter-input').addEventListener('input', (e) => {
            eventFilter = e.target.value;
            // This is a simple implementation. A more robust one would re-filter existing events.
        });
        document.getElementById('error-filter').addEventListener('click', () => eventFilter = 'error');
        document.getElementById('log-filter').addEventListener('click', () => eventFilter = 'log');
        document.getElementById('network-filter').addEventListener('click', () => eventFilter = 'network');
        document.getElementById('clear-filter').addEventListener('click', () => {
            eventFilter = '';
            document.getElementById('filter-input').value = '';
        });

    </script>
</body>
</html>
"""