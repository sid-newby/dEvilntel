# devintel-system.py

## Overview

This file contains the core logic of the DevIntel system. It is responsible for data modeling, storage, and the intelligence layer that analyzes development events and suggests solutions.

## Key Components

### Data Models

-   **`EventType` (Enum):** Defines the different types of events that can be captured (e.g., `LOG`, `ERROR`, `NETWORK`).
-   **`DevEvent` (dataclass):** The core data structure for all captured events. It includes an ID, type, timestamp, session ID, content, stack trace, context, and an optional embedding.
-   **`ErrorContext` (Pydantic BaseModel):** The input model for the DSPy `ErrorAnalyzer`. It includes the error message, stack trace, code context, framework, and recent actions.
-   **`SolutionSuggestion` (Pydantic BaseModel):** The output model for the DSPy `ErrorAnalyzer`. It includes the root cause, suggested solution code, explanation, confidence score, similar cases, and a pattern name.

### DSPy Components

-   **`ErrorAnalyzer` (dspy.Signature):** A DSPy signature for analyzing development errors and suggesting solutions.
-   **`PatternIdentifier` (dspy.Signature):** A DSPy signature for identifying common development patterns and anti-patterns from a list of events.

### `StorageBackend` Class

-   A unified interface for interacting with the different storage backends (Redis, PostgreSQL, and Neo4j).
-   **`initialize()`:** Initializes the connections to all the storage backends and creates the necessary database schemas.
-   **`_init_schemas()`:** Creates the `dev_events` and `solutions` tables in PostgreSQL, including a vector index for similarity search.
-   **`store_event()`:** Stores a `DevEvent` in all the backends:
    -   Streams the event to Redis for real-time processing.
    -   Stores the event in PostgreSQL for vector search.
    -   Creates graph relationships in Neo4j.

### `DevIntelligence` Class

-   The main intelligence layer of the system.
-   **`analyze_error()`:** Analyzes an error event by:
    -   Finding similar errors using vector search.
    -   Getting recent events from the same session.
    -   Using the `ErrorAnalyzer` to suggest a solution.
    -   Storing the solution attempt with the DSPy history.
-   **`identify_patterns()`:** Identifies patterns in a development session using the `PatternIdentifier`.
-   **`_find_similar_errors()`:** Finds similar errors using vector search in PostgreSQL.
-   **`_get_recent_events()`:** Gets recent events from a session from PostgreSQL.
-   **`_store_solution_attempt()`:** Stores a solution attempt in PostgreSQL and creates a relationship in Neo4j.
-   **`_update_pattern_graph()`:** Updates the pattern relationships in Neo4j.

### `ChangelogGenerator` Class

-   **`generate_session_changelog()`:** Generates a comprehensive changelog for a session, including event counts, patterns, metrics, and a timeline.
-   **`_identify_changelog_patterns()`:** Identifies patterns in a list of changelog entries.
-   **`_calculate_success_metrics()`:** Calculates success metrics for solutions in a session.

### `DevIntelAPI` Class

-   The main API for interacting with the DevIntel system.
-   **`ingest_event()`:** Ingests an event, stores it, and analyzes it if it's an error.
-   **`get_patterns()`:** Gets the identified patterns for a session.
-   **`get_changelog()`:** Gets the changelog for a session.
-   **`record_outcome()`:** Records the outcome of a solution for learning.

### `BROWSER_INJECTION_SCRIPT`

A string containing the JavaScript code that is injected into the browser to capture development events. This is a simplified version of the code in `devintel-enhanced.js`.