# DevIntel Complete Setup Guide

## 🚀 Overview

DevIntel is a real-time development intelligence system that:
- **Captures** all console logs, errors, and network activity from Chrome
- **Tracks** file changes, git commits, and debugging sessions from VSCode
- **Analyzes** errors using DSPy AI to suggest solutions
- **Visualizes** development patterns in a real-time dashboard
- **Learns** from successful solutions to improve over time

## 📋 Prerequisites

- Python 3.8+
- Node.js 14+ (for VSCode extension)
- Chrome browser
- VSCode
- Homebrew (for macOS) or a package manager for your OS.

## 🛠️ Quick Setup

### 1. Install and Start Services

**Note:** The following instructions are for macOS using Homebrew. If you are on a different OS, please use your respective package manager.

```bash
# Install Redis
brew install redis
brew services start redis

# Install PostgreSQL
brew install postgresql
brew services start postgresql
# Create the database
createdb devintel

# Install Neo4j
brew install neo4j
brew services start neo4j
```

### 2. Install Python Dependencies

### 2. Install Python Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn websockets redis asyncpg neo4j numpy \
            sentence-transformers pgvector pydantic dspy-ai
```

### 3. Configure DSPy

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"

# Create config.py
cat > config.py << 'EOF'
import dspy

# Configure DSPy
dspy.settings.configure(
    lm=dspy.OpenAI(model="gpt-4.1", temperature=0.3)
)
EOF
```

### 4. Start the DevIntel Server

Save all the Python artifacts to their respective files:
- `devintel.py` - Core system (from devintel-system artifact)
- `server.py` - Real-time server (from devintel-realtime-server artifact)

Then start the server:

```bash
python server.py
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     DevIntel server started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 5. Install Chrome Extension

1. Create a new directory `chrome-extension`
2. Save these files from the devintel-enhanced artifact:
   - `manifest.json`
   - `background.js` 
   - `injector.js`
   - `popup.html`
   - `popup.js`

3. Create simple icon files (16x16, 48x48, 128x128 PNG files)

4. Load the extension:
   - Open Chrome and go to `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked"
   - Select your `chrome-extension` directory

5. Pin the DevIntel extension to your toolbar

### 6. Install VSCode Extension

```bash
# Create VSCode extension directory
mkdir vscode-extension && cd vscode-extension

# Initialize package
npm init -y

# Save the extension files:
# - package.json (from VSCODE_PACKAGE)
# - extension.js (from VSCODE_EXTENSION)

# Install VSCode extension dependencies
npm install ws

# Package the extension
npm install -g vsce
vsce package

# Install in VSCode
code --install-extension devintel-vscode-*.vsix
```

## 🎯 Using DevIntel

### Chrome Extension - One-Click Connect

1. **Click the DevIntel icon** in your Chrome toolbar
2. You'll see the connection status turn green
3. **All console logs are now streaming** to DevIntel

Features:
- **Real-time filtering** by event type (errors, logs, network, etc.)
- **Pattern matching** with regex support
- **Export events** as JSON
- **One-click dashboard** access

### VSCode Integration

1. **Open Command Palette** (Cmd/Ctrl + Shift + P)
2. Run `DevIntel: Connect to Server`
3. Your file changes and debugging sessions are now tracked

Commands:
- `DevIntel: Analyze Current File` - Get AI analysis of current file
- `DevIntel: Track File Changes` - Toggle file change tracking
- `DevIntel: Show Dashboard` - Open the web dashboard

### Real-time Dashboard

Open http://localhost:8000/dashboard to see:
- **Live event stream** from all connected sources
- **Session management** - Switch between different sessions
- **Real-time metrics** - Errors, solutions, patterns
- **Event timeline** - Visualize activity over time
- **Solution history** - See what fixes have been suggested

## 📊 Example Workflow

1. **Start coding** in VSCode with DevIntel connected
2. **Open your app** in Chrome with the extension active
3. **Get an error** in the console
4. **See instant solution** in Chrome console with confidence score
5. **Apply fix** directly from VSCode notification
6. **Track success** - DevIntel learns from what works

## 🔧 Advanced Features

### Custom Filters

In the Chrome extension popup, use regex patterns:
```
TypeError.*undefined    # Match TypeErrors with undefined
^GET.*404              # Match 404 network errors
React.*render          # Match React render errors
```

### Session Tags

Tag sessions for better organization:
```javascript
// In your app code
console.log('[FEATURE:auth] User login attempted');
console.log('[PERF] Component render took 150ms');
```

### Git Integration

DevIntel automatically tracks:
- Current branch
- Recent commits
- File changes in git
- Correlates errors with code changes

### Multi-Source Correlation

When an error occurs:
1. Chrome captures the error and stack trace
2. VSCode shows which files were recently edited
3. Git info shows recent commits
4. DSPy analyzes all context to suggest fixes

## 🚨 Troubleshooting

### Connection Issues

1. Verify server is accessible:
   ```bash
   curl http://localhost:8000/sessions
   ```

3. Check Chrome extension console:
   - Right-click extension icon → "Inspect popup"
   - Check for errors in console

### No Events Showing

1. Ensure the website uses HTTP/HTTPS (not file://)
2. Refresh the page after installing extension
3. Check filters aren't hiding events
4. Verify WebSocket connection in Network tab

### VSCode Not Connecting

1. Check server URL in settings:
   ```json
   "devintel.serverUrl": "http://localhost:8000"
   ```

2. Restart VSCode after installing extension
3. Check Output panel → DevIntel for errors

## 📈 Performance Tips

1. **Batch Events**: The system automatically batches events for efficiency
2. **Filter Early**: Use filters to reduce noise
3. **Session Management**: Create new sessions for different features/bugs
4. **Export & Analyze**: Export sessions for offline analysis

## 🔐 Security Notes

- DevIntel runs locally by default
- No data leaves your machine unless configured
- Filter sensitive data in production
- Use environment variables for API keys

## 🎉 Next Steps

1. **Customize DSPy prompts** for your tech stack
2. **Add custom event types** for your framework
3. **Build team dashboards** for shared debugging
4. **Export patterns** to create coding standards
5. **Integrate with CI/CD** for automated analysis

Happy debugging! 🚀