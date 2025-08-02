# devintel-enhanced.js

## Overview

This file contains the core logic for the DevIntel Chrome Extension. It is responsible for injecting a content script into web pages, capturing various development events, and sending them to the DevIntel server for analysis.

## Key Components

### `background.js` (Service Worker)

- **`onInstalled` Listener:** Initializes the extension's storage with default settings for filters and the server endpoint.
- **`onUpdated` Listener:** Injects the `injector.js` content script into tabs when they are fully loaded.
- **`onMessage` Listener:** Forwards captured events from the content script to the popup for real-time viewing.

### `injector.js` (Content Script)

This script is injected into web pages and contains the `DevIntelCapture` class, which is the heart of the event capturing system.

#### `DevIntelCapture` Class

- **`constructor()`:** Initializes the session, buffer, filters, and WebSocket connection.
- **`loadSettings()`:** Loads filter and endpoint settings from Chrome's local storage and listens for changes.
- **`connectWebSocket()`:** Establishes a WebSocket connection to the DevIntel server (`ws://localhost:8000/ws`) and handles connection lifecycle events (open, close, error, message).
- **`init()`:** Sets up all the interceptors for console, errors, network, performance, and DOM mutations.
- **`shouldCapture(type, content)`:** Determines whether an event should be captured based on the current filter settings.
- **`interceptConsole()`:** Wraps `console` methods (`log`, `error`, `warn`, etc.) to capture their arguments and context.
- **`formatArgs(args)`:** Formats the arguments passed to console methods for better analysis, handling Errors, DOM Elements, and Objects.
- **`getCallStack()`:** Retrieves and cleans the call stack for captured events.
- **`interceptErrors()`:** Listens for `window.onerror` and `window.onunhandledrejection` to capture uncaught exceptions and unhandled promise rejections.
- **`interceptNetwork()`:** Wraps `window.fetch` and `XMLHttpRequest` to capture network requests and responses.
- **`interceptPerformance()`:** Uses the `PerformanceObserver` to detect and capture long tasks.
- **`setupMutationObserver()`:** Uses a `MutationObserver` to detect changes in the DOM, specifically looking for React error boundaries.
- **`extractSourceCode(filename, lineNumber)`:** A placeholder for extracting source code around an error.
- **`gatherContext()`:** Collects a rich set of contextual information with each event, including URL, viewport/screen dimensions, memory usage, network connection details, detected framework, and performance timing metrics.
- **`detectFramework()`:** Attempts to identify the JavaScript framework being used on the page (React, Vue, Angular, Svelte, Next, Nuxt).
- **`getFrameworkVersion(framework)`:** Attempts to get the version of the detected framework.
- **`getTimingMetrics()`:** Gathers performance timing metrics from the `Navigation Timing API`.
- **`capture(event)`:** Adds a captured event to the buffer.
- **`flushBuffer()`:** Sends the buffered events to the DevIntel server via the WebSocket connection.
- **`displaySolution(data)`:** Displays a solution received from the server in the console.

### VSCode Integration (`VSCODE_PACKAGE`)

The file also contains a JSON object that appears to be a `package.json` for a VSCode extension. This defines:
- **Commands:** `DevIntel: Connect to Server`, `DevIntel: Analyze Current File`, `DevIntel: Track File Changes`, `DevIntel: Show Dashboard`.
- **Configuration:** Settings for `devintel.serverUrl`, `devintel.autoConnect`, `devintel.trackGitChanges`, and `devintel.fileWatchPatterns`.
- **Views:** A view in the explorer for DevIntel.

### Webpack Configuration (`module.exports`)

The file ends with a `module.exports` object that seems to be a Webpack configuration for building the Chrome and VSCode extensions. It defines the manifest for the Chrome extension, the popup, and the VSCode extension.