# devintel-setup.json

## Overview

This file is a JSON representation of the DevIntel project's setup configuration. It contains the necessary information to set up the backend services, Python dependencies, and browser extension.

## Key Sections

### `docker-compose.yml`

-   **`version`**: "3.8"
-   **`services`**:
    -   **`redis`**: An in-memory data store, used for real-time streaming.
    -   **`postgres`**: A PostgreSQL database with the `pgvector` extension for vector similarity search.
    -   **`neo4j`**: A graph database for storing and querying relationships between development events.

### `requirements.txt`

A list of Python dependencies required for the project, including:
-   `dspy-ai`: For AI-powered error analysis and solution suggestion.
-   `fastapi`: For building the web server.
-   `uvicorn`: For running the FastAPI server.
-   `redis[hiredis]`: For connecting to the Redis server.
-   `asyncpg`: For connecting to the PostgreSQL server.
-   `neo4j`: For connecting to the Neo4j server.
-   `numpy`: For numerical operations.
-   `sentence-transformers`: for creating embeddings from text.
-   `pgvector`: For working with vectors in PostgreSQL.
-   `pydantic`: For data validation.

### `browser-extension/manifest.json`

The manifest for the Chrome extension, which defines:
-   **`manifest_version`**: 3
-   **`name`**: "DevIntel"
-   **`version`**: "1.0.0"
-   **`description`**: "Development Intelligence System"
-   **`permissions`**: `storage` and `tabs`.
-   **`host_permissions`**: `http://localhost:8000/*`.
-   **`content_scripts`**: Injects `devintel.js` into all URLs.
-   **`action`**: Defines `popup.html` as the default popup.

### `browser-extension/popup.html`

The HTML for the Chrome extension's popup, which includes:
-   A status display to show the connection status.
-   A session ID display.
-   Buttons to view the dashboard and create a new session.

### `browser-extension/popup.js`

The JavaScript for the Chrome extension's popup, which:
-   Checks the connection status and updates the UI.
-   Opens the dashboard in a new tab when the "View Dashboard" button is clicked.
-   Sends a message to the content script to create a new session when the "New Session" button is clicked.

### `setup.sh`

A shell script to automate the setup process, which:
-   Starts the Docker services.
-   Installs the Python dependencies.
-   Initializes DSPy.
-   Starts the DevIntel server.

### `example_usage.py`

An example Python script that demonstrates how to use the `DevIntelAPI` to:
-   Initialize the API.
-   Simulate an error event.
-   Ingest the error and get a solution.
-   Check for identified patterns.
-   Get the changelog for a session.