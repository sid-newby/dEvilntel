# devintel-setup-guide.md

## Overview

This file is a comprehensive guide to setting up the DevIntel system. It provides a step-by-step process for installing and configuring all the necessary components, including the backend services, Python dependencies, Chrome Extension, and VSCode Extension.

## Key Sections

### Prerequisites

Lists the required software for setting up the DevIntel system:
- Docker & Docker Compose
- Python 3.8+
- Node.js 14+
- Chrome browser
- VSCode

### Quick Setup

Provides a detailed, step-by-step guide to getting the system running:

1.  **Clone and Start Services:**
    -   Instructions for creating a project directory.
    -   A `docker-compose.yml` file for running the backend services (Redis, PostgreSQL with pgvector, and Neo4j).
    -   The command to start the services using `docker-compose up -d`.

2.  **Install Python Dependencies:**
    -   Instructions for creating a Python virtual environment.
    -   A `pip install` command to install all the necessary Python libraries, including `fastapi`, `dspy-ai`, and the database drivers.

3.  **Configure DSPy:**
    -   Instructions for setting the `OPENAI_API_KEY` environment variable.
    -   A `config.py` file for configuring DSPy to use the OpenAI gpt-4.1 model.

4.  **Start the DevIntel Server:**
    -   Instructions for saving the Python artifacts (`devintel.py` and `server.py`).
    -   The command to start the server (`python server.py`).

5.  **Install Chrome Extension:**
    -   Instructions for creating the extension directory and saving the necessary files (`manifest.json`, `background.js`, etc.).
    -   Steps for loading the extension in Chrome's developer mode.

6.  **Install VSCode Extension:**
    -   Instructions for creating the extension directory and initializing an `npm` package.
    -   Instructions for saving the `package.json` and `extension.js` files.
    -   Commands for packaging and installing the VSCode extension.

### Using DevIntel

Explains how to use the system once it's set up:
-   **Chrome Extension:** How to connect to the server and use the real-time filtering and dashboard access features.
-   **VSCode Integration:** How to use the available commands in the VSCode command palette.
-   **Real-time Dashboard:** What to expect from the dashboard at `http://localhost:8000/dashboard`.

### Example Workflow

Describes a typical workflow for a developer using DevIntel.

### Advanced Features

-   **Custom Filters:** How to use regex patterns in the Chrome extension to filter events.
-   **Session Tags:** How to tag sessions for better organization.
-   **Git Integration:** How DevIntel automatically tracks Git information.
-   **Multi-Source Correlation:** How DevIntel combines information from different sources to provide better solutions.

### Troubleshooting

Provides solutions for common problems:
-   Connection issues.
-   No events showing up.
-   VSCode not connecting.

### Performance Tips

Offers advice for optimizing the performance of the system.

### Security Notes

Provides important security considerations, such as running the system locally and filtering sensitive data.

### Next Steps

Suggests ways to extend and customize the DevIntel system.