# prototype-devintel-dashboard.html

## Overview

This file contains the HTML, CSS, and JavaScript for the DevIntel dashboard. It is a single-page application that provides a real-time view of the development intelligence data being captured by the system.

## Key Components

### HTML Structure

-   A main `dashboard` container with a `sidebar` and `main-content` area.
-   The `sidebar` contains the logo, navigation links, and the current session ID.
-   The `main-content` area contains different "views" for the overview, errors, patterns, and changelog.
-   Each view has a corresponding `div` with a unique ID (e.g., `overviewView`, `errorsView`).

### CSS Styling

-   A dark theme with a clean, modern aesthetic.
-   Uses CSS Grid for the main layout.
-   Includes styles for various components, such as stat cards, charts, error lists, and a live indicator.
-   Includes keyframe animations for a pulsing live indicator and a loading spinner.

### JavaScript (`DevIntelDashboard` Class)

-   **`constructor()`:** Initializes the API URL, current session ID, charts, and Cytoscape instance.
-   **`getSessionId()`:** Gets the session ID from the URL parameters or generates a new one.
-   **`init()`:** Sets up the navigation, displays the session ID, loads the overview data, and starts the live updates.
-   **`setupNavigation()`:** Sets up the click handlers for the navigation items to switch between the different views.
-   **`displaySessionId()`:** Displays the current session ID in the sidebar.
-   **`loadOverview()`:** Loads the data for the overview view, including the stats and charts.
-   **`loadErrors()`:** Loads the list of errors and their solutions for the errors view.
-   **`loadPatterns()`:** Loads the development patterns and creates a pattern graph using Cytoscape.js.
-   **`loadChangelog()`:** Loads the session changelog and displays it in a timeline format.
--   **`updateStats()`:** Updates the statistics in the overview view.
-   **`createTimelineChart()`:** Creates a timeline chart of events using Chart.js.
-   **`createErrorChart()`:** Creates a chart of error categories using Chart.js.
-   **`createPatternGraph()`:** Creates a graph of development patterns using Cytoscape.js.
-   **`fetchChangelog()`:** Fetches the changelog data from the server.
-   **`fetchPatterns()`:** Fetches the pattern data from the server.
-   **`startLiveUpdates()`:** Sets up a WebSocket connection to the server to receive live updates and refresh the dashboard.
-   **`getEventColor()` and `getEventIcon()`:** Helper functions for styling the changelog timeline.