# devintel-realtime-server.py

## Overview

This file contains the backend server for the DevIntel project. It is a FastAPI application that provides a real-time WebSocket API for the Chrome Extension and VSCode extension to connect to, as well as a REST API for other clients. The server is responsible for receiving development events, processing them, storing them, and broadcasting results and solutions.

## Key Components

### FastAPI Application (`app`)

- **CORS Middleware:** Allows cross-origin requests from any source, which is necessary for the browser extension to communicate with the server.
- **`startup` event:** Initializes the `DevIntelAPI` when the server starts.

### `ConnectionManager` Class

- Manages WebSocket connections from clients (browsers and VSCode).
- `active_connections`: A dictionary to store active WebSocket connections.
- `session_connections`: A dictionary to group connections by session ID.
- `connection_metadata`: A dictionary to store metadata about each connection (e.g., source, URL, workspace).
- `connect()`: Accepts a new WebSocket connection.
- `disconnect()`: Removes a WebSocket connection.
- `send_personal_message()`: Sends a message to a specific client.
- `broadcast_to_session()`: Broadcasts a message to all clients in a session.
- `set_client_metadata()`: Stores metadata for a client connection.

### `RealtimeEventProcessor` Class

- `process_event()`: Processes a single incoming event. It creates a `DevEvent`, stores it using the `DevIntelAPI`, and broadcasts any solutions or confirmations to the session.
- `process_bulk_events()`: Processes a batch of events.

### WebSocket Endpoints

- **`/ws`:** The main WebSocket endpoint for clients to connect to. It handles different message types:
    - `init`: Initializes a new client connection and stores its metadata.
    - `event`: Processes a single development event.
    - `bulk`: Processes a batch of development events.
    - `query`: Handles real-time queries from clients (e.g., for patterns).
- **`/ws/monitor`:** A WebSocket endpoint for monitoring all active sessions in real-time.

### REST Endpoints

- **`/ingest` (POST):** Allows clients to send a batch of events via a REST API.
- **`/patterns/{session_id}` (GET):** Returns the identified patterns for a given session.
- **`/changelog/{session_id}` (GET):** Returns the changelog for a session.
- **`/outcome/{solution_id}` (POST):** Records the outcome of a suggested solution.
- **`/dashboard` (GET):** Serves the HTML for the enhanced real-time dashboard.
- **`/sessions` (GET):** Returns a list of all active sessions with their metadata.

### `ENHANCED_DASHBOARD_HTML`

A string containing the HTML, CSS, and JavaScript for the real-time dashboard. This is a single-page application that connects to the `/ws/monitor` WebSocket endpoint to display live data about the active sessions.