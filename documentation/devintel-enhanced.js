// ============= Enhanced Chrome Extension =============

// background.js - Service worker for Chrome extension
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ 
    enabled: true,
    filters: {
      types: ['log', 'error', 'warn', 'network'],
      levels: ['all'],
      patterns: []
    },
    endpoint: 'http://localhost:8000'
  });
});

// Listen for tab updates to inject script
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url?.startsWith('http')) {
    chrome.storage.local.get(['enabled'], (result) => {
      if (result.enabled) {
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          files: ['injector.js']
        });
      }
    });
  }
});

// Handle messages from content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'captureEvent') {
    // Forward to popup for real-time view
    chrome.runtime.sendMessage({
      action: 'newEvent',
      event: request.event,
      tab: sender.tab
    });
  }
});

// injector.js - Enhanced content script with filtering
(function() {
  if (window.__devIntelInjected) return;
  window.__devIntelInjected = true;

  class DevIntelCapture {
    constructor() {
      this.sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      this.buffer = [];
      this.filters = { types: ['all'], patterns: [] };
      this.connected = false;
      this.ws = null;
      
      this.loadSettings();
      this.init();
    }
    
    async loadSettings() {
      // Get settings from extension storage
      chrome.storage.local.get(['filters', 'endpoint'], (result) => {
        this.filters = result.filters || this.filters;
        this.endpoint = result.endpoint || 'http://localhost:8000';
        this.connectWebSocket();
      });
      
      // Listen for filter changes
      chrome.storage.onChanged.addListener((changes) => {
        if (changes.filters) {
          this.filters = changes.filters.newValue;
        }
      });
    }
    
    connectWebSocket() {
      try {
        this.ws = new WebSocket('ws://localhost:8000/ws');
        
        this.ws.onopen = () => {
          this.connected = true;
          console.log('%c[DevIntel] Connected to server', 'color: #4CAF50; font-weight: bold');
          this.ws.send(JSON.stringify({
            type: 'init',
            sessionId: this.sessionId,
            url: location.href,
            userAgent: navigator.userAgent
          }));
          
          // Flush any buffered events
          this.flushBuffer();
        };
        
        this.ws.onclose = () => {
          this.connected = false;
          console.log('%c[DevIntel] Disconnected', 'color: #f44336');
          // Reconnect after 5 seconds
          setTimeout(() => this.connectWebSocket(), 5000);
        };
        
        this.ws.onerror = (error) => {
          console.error('[DevIntel] WebSocket error:', error);
        };
        
        this.ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.type === 'solution') {
            this.displaySolution(data);
          }
        };
      } catch (error) {
        console.error('[DevIntel] Failed to connect:', error);
        setTimeout(() => this.connectWebSocket(), 5000);
      }
    }
    
    init() {
      this.interceptConsole();
      this.interceptErrors();
      this.interceptNetwork();
      this.interceptPerformance();
      this.setupMutationObserver();
    }
    
    shouldCapture(type, content) {
      // Check type filter
      if (!this.filters.types.includes('all') && !this.filters.types.includes(type)) {
        return false;
      }
      
      // Check pattern filters
      if (this.filters.patterns.length > 0) {
        const message = typeof content === 'string' ? content : JSON.stringify(content);
        return this.filters.patterns.some(pattern => {
          try {
            return new RegExp(pattern, 'i').test(message);
          } catch (e) {
            return message.includes(pattern);
          }
        });
      }
      
      return true;
    }
    
    interceptConsole() {
      const methods = ['log', 'error', 'warn', 'info', 'debug', 'trace'];
      methods.forEach(method => {
        const original = console[method];
        console[method] = (...args) => {
          const content = args.map(arg => 
            typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
          ).join(' ');
          
          if (this.shouldCapture(method, content)) {
            this.capture({
              type: method,
              content: {
                message: content,
                args: args,
                formatted: this.formatArgs(args)
              },
              stack: method === 'error' ? new Error().stack : this.getCallStack(),
              timestamp: Date.now(),
              context: this.gatherContext()
            });
          }
          
          original.apply(console, args);
        };
      });
    }
    
    formatArgs(args) {
      // Smart formatting for common patterns
      return args.map(arg => {
        if (arg instanceof Error) {
          return {
            type: 'error',
            name: arg.name,
            message: arg.message,
            stack: arg.stack
          };
        } else if (arg instanceof Element) {
          return {
            type: 'element',
            tagName: arg.tagName,
            id: arg.id,
            className: arg.className,
            innerHTML: arg.innerHTML.substring(0, 100)
          };
        } else if (typeof arg === 'object' && arg !== null) {
          return {
            type: 'object',
            preview: JSON.stringify(arg, null, 2).substring(0, 500),
            keys: Object.keys(arg)
          };
        }
        return arg;
      });
    }
    
    getCallStack() {
      const stack = new Error().stack;
      // Parse and clean up stack trace
      return stack.split('\n')
        .slice(3) // Skip Error and internal calls
        .filter(line => !line.includes('DevIntel'))
        .map(line => line.trim())
        .join('\n');
    }
    
    interceptErrors() {
      window.addEventListener('error', (event) => {
        if (this.shouldCapture('error', event.message)) {
          this.capture({
            type: 'error',
            content: {
              message: event.message,
              filename: event.filename,
              line: event.lineno,
              column: event.colno,
              source: this.extractSourceCode(event.filename, event.lineno)
            },
            stack: event.error?.stack,
            timestamp: Date.now(),
            context: this.gatherContext()
          });
        }
      });
      
      window.addEventListener('unhandledrejection', (event) => {
        const message = event.reason?.message || String(event.reason);
        if (this.shouldCapture('error', message)) {
          this.capture({
            type: 'error',
            subtype: 'unhandledRejection',
            content: {
              message: 'Unhandled Promise Rejection',
              reason: message,
              promise: event.promise
            },
            stack: event.reason?.stack,
            timestamp: Date.now(),
            context: this.gatherContext()
          });
        }
      });
    }
    
    interceptNetwork() {
      // Intercept fetch
      const originalFetch = window.fetch;
      window.fetch = async (...args) => {
        const startTime = performance.now();
        const [resource, config] = args;
        const url = typeof resource === 'string' ? resource : resource.url;
        
        try {
          const response = await originalFetch(...args);
          const duration = performance.now() - startTime;
          
          if (this.shouldCapture('network', url)) {
            this.capture({
              type: 'network',
              subtype: 'fetch',
              content: {
                url: url,
                method: config?.method || 'GET',
                status: response.status,
                statusText: response.statusText,
                duration: duration,
                size: response.headers.get('content-length'),
                contentType: response.headers.get('content-type')
              },
              timestamp: Date.now(),
              context: this.gatherContext()
            });
          }
          
          return response;
        } catch (error) {
          if (this.shouldCapture('network', url)) {
            this.capture({
              type: 'network',
              subtype: 'fetch-error',
              content: {
                url: url,
                method: config?.method || 'GET',
                error: error.message,
                duration: performance.now() - startTime
              },
              stack: error.stack,
              timestamp: Date.now(),
              context: this.gatherContext()
            });
          }
          throw error;
        }
      };
      
      // Intercept XMLHttpRequest
      const XHROpen = XMLHttpRequest.prototype.open;
      const XHRSend = XMLHttpRequest.prototype.send;
      
      XMLHttpRequest.prototype.open = function(method, url, ...args) {
        this._devIntel = { method, url, startTime: null };
        return XHROpen.apply(this, [method, url, ...args]);
      };
      
      XMLHttpRequest.prototype.send = function(...args) {
        if (this._devIntel) {
          this._devIntel.startTime = performance.now();
          
          this.addEventListener('loadend', () => {
            const duration = performance.now() - this._devIntel.startTime;
            if (window.__devIntel.shouldCapture('network', this._devIntel.url)) {
              window.__devIntel.capture({
                type: 'network',
                subtype: 'xhr',
                content: {
                  url: this._devIntel.url,
                  method: this._devIntel.method,
                  status: this.status,
                  statusText: this.statusText,
                  duration: duration
                },
                timestamp: Date.now(),
                context: window.__devIntel.gatherContext()
              });
            }
          });
        }
        
        return XHRSend.apply(this, args);
      };
    }
    
    interceptPerformance() {
      // Monitor long tasks
      if ('PerformanceObserver' in window) {
        try {
          const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
              if (entry.duration > 50) { // Long task threshold
                this.capture({
                  type: 'performance',
                  subtype: 'long-task',
                  content: {
                    duration: entry.duration,
                    startTime: entry.startTime,
                    name: entry.name
                  },
                  timestamp: Date.now(),
                  context: this.gatherContext()
                });
              }
            }
          });
          observer.observe({ entryTypes: ['longtask'] });
        } catch (e) {
          // Some browsers don't support longtask
        }
      }
    }
    
    setupMutationObserver() {
      // Track React/Vue component errors
      const observer = new MutationObserver((mutations) => {
        mutations.forEach(mutation => {
          if (mutation.type === 'childList') {
            mutation.addedNodes.forEach(node => {
              if (node.nodeType === Node.ELEMENT_NODE) {
                // Check for React error boundaries
                if (node.classList && node.classList.contains('react-error-boundary')) {
                  this.capture({
                    type: 'error',
                    subtype: 'react-error-boundary',
                    content: {
                      message: 'React Error Boundary triggered',
                      component: node.getAttribute('data-component'),
                      html: node.innerHTML
                    },
                    timestamp: Date.now(),
                    context: this.gatherContext()
                  });
                }
              }
            });
          }
        });
      });
      
      observer.observe(document.body, {
        childList: true,
        subtree: true
      });
    }
    
    extractSourceCode(filename, lineNumber) {
      // Try to extract source code around error
      // This would need source map support for production
      return null; // Placeholder
    }
    
    gatherContext() {
      return {
        url: location.href,
        referrer: document.referrer,
        title: document.title,
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight
        },
        screen: {
          width: screen.width,
          height: screen.height,
          pixelRatio: window.devicePixelRatio
        },
        memory: performance.memory ? {
          used: Math.round(performance.memory.usedJSHeapSize / 1048576),
          total: Math.round(performance.memory.totalJSHeapSize / 1048576),
          limit: Math.round(performance.memory.jsHeapSizeLimit / 1048576)
        } : null,
        connection: navigator.connection ? {
          effectiveType: navigator.connection.effectiveType,
          downlink: navigator.connection.downlink,
          rtt: navigator.connection.rtt
        } : null,
        framework: this.detectFramework(),
        timing: this.getTimingMetrics()
      };
    }
    
    detectFramework() {
      const frameworks = {
        React: () => window.React || document.querySelector('[data-reactroot]'),
        Vue: () => window.Vue || document.querySelector('#app').__vue__,
        Angular: () => window.angular || document.querySelector('[ng-version]'),
        Svelte: () => document.querySelector('[data-svelte]'),
        Next: () => window.__NEXT_DATA__,
        Nuxt: () => window.$nuxt
      };
      
      for (const [name, check] of Object.entries(frameworks)) {
        try {
          if (check()) {
            return {
              name,
              version: this.getFrameworkVersion(name)
            };
          }
        } catch (e) {
          // Continue checking
        }
      }
      
      return { name: 'vanilla', version: null };
    }
    
    getFrameworkVersion(framework) {
      try {
        switch (framework) {
          case 'React':
            return window.React?.version;
          case 'Vue':
            return window.Vue?.version;
          case 'Angular':
            return document.querySelector('[ng-version]')?.getAttribute('ng-version');
          case 'Next':
            return window.__NEXT_DATA__?.buildId;
          default:
            return null;
        }
      } catch (e) {
        return null;
      }
    }
    
    getTimingMetrics() {
      const navigation = performance.getEntriesByType('navigation')[0];
      if (!navigation) return null;
      
      return {
        dns: Math.round(navigation.domainLookupEnd - navigation.domainLookupStart),
        tcp: Math.round(navigation.connectEnd - navigation.connectStart),
        ttfb: Math.round(navigation.responseStart - navigation.requestStart),
        download: Math.round(navigation.responseEnd - navigation.responseStart),
        domInteractive: Math.round(navigation.domInteractive - navigation.fetchStart),
        domComplete: Math.round(navigation.domComplete - navigation.fetchStart),
        loadComplete: Math.round(navigation.loadEventEnd - navigation.fetchStart)
      };
    }
    
    capture(event) {
      // Add to buffer
      this.buffer.push({
        ...event,
        sessionId: this.sessionId,
        id: `evt_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
      });
      
      // Send via WebSocket if connected
      if (this.connected && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          type: 'event',
          event: event
        }));
      }
      
      // Also send to extension popup
      chrome.runtime.sendMessage({
        action: 'captureEvent',
        event: event
      });
      
      // Keep buffer size manageable
      if (this.buffer.length > 1000) {
        this.buffer = this.buffer.slice(-500);
      }
    }
    
    flushBuffer() {
      if (this.connected && this.ws.readyState === WebSocket.OPEN && this.buffer.length > 0) {
        this.ws.send(JSON.stringify({
          type: 'bulk',
          events: this.buffer
        }));
        this.buffer = [];
      }
    }
    
    displaySolution(data) {
      console.group(
        '%c[DevIntel Solution]%c ' + data.solution.root_cause,
        'background: #4CAF50; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold;',
        'color: #4CAF50; font-weight: bold;'
      );
      console.log('%cSuggested Fix:', 'font-weight: bold; color: #2196F3;');
      console.log(data.solution.solution_code);
      console.log('%cExplanation:', 'font-weight: bold; color: #FF9800;');
      console.log(data.solution.explanation);
      console.log('%cConfidence:', 'font-weight: bold;', `${Math.round(data.solution.confidence * 100)}%`);
      console.groupEnd();
    }
  }
  
  // Initialize
  window.__devIntel = new DevIntelCapture();
  
  // Listen for messages from extension
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    switch (request.action) {
      case 'getStatus':
        sendResponse({
          connected: window.__devIntel.connected,
          sessionId: window.__devIntel.sessionId,
          bufferSize: window.__devIntel.buffer.length
        });
        break;
      case 'newSession':
        window.__devIntel.sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        window.__devIntel.buffer = [];
        sendResponse({ success: true });
        break;
      case 'getBuffer':
        sendResponse({ buffer: window.__devIntel.buffer });
        break;
    }
  });
})();

// ============= Chrome Extension Popup =============
// popup.html - Enhanced popup with filters
const POPUP_HTML = `<!DOCTYPE html>
<html>
<head>
  <style>
    body {
      width: 400px;
      min-height: 500px;
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0a0a0a;
      color: #e0e0e0;
    }
    
    .header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 15px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    
    .logo {
      font-size: 20px;
      font-weight: bold;
      color: white;
    }
    
    .status {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #4caf50;
    }
    
    .status-dot.disconnected {
      background: #f44336;
    }
    
    .controls {
      padding: 15px;
      background: #111;
      border-bottom: 1px solid #222;
    }
    
    .filter-group {
      margin-bottom: 10px;
    }
    
    .filter-label {
      font-size: 12px;
      color: #888;
      margin-bottom: 5px;
    }
    
    .filter-chips {
      display: flex;
      gap: 5px;
      flex-wrap: wrap;
    }
    
    .chip {
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 12px;
      background: #222;
      border: 1px solid #333;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .chip.active {
      background: #667eea;
      border-color: #667eea;
    }
    
    .search-box {
      width: 100%;
      padding: 8px 12px;
      background: #1a1a1a;
      border: 1px solid #333;
      border-radius: 6px;
      color: #e0e0e0;
      font-size: 13px;
      margin-top: 10px;
    }
    
    .events-container {
      max-height: 400px;
      overflow-y: auto;
      background: #0a0a0a;
    }
    
    .event-item {
      padding: 10px 15px;
      border-bottom: 1px solid #1a1a1a;
      font-size: 12px;
      transition: background 0.2s;
    }
    
    .event-item:hover {
      background: #111;
    }
    
    .event-type {
      display: inline-block;
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 10px;
      font-weight: bold;
      margin-right: 8px;
    }
    
    .event-type.log { background: #2e7d32; }
    .event-type.error { background: #d32f2f; }
    .event-type.warn { background: #f57c00; }
    .event-type.network { background: #1976d2; }
    .event-type.performance { background: #7b1fa2; }
    
    .event-message {
      color: #ccc;
      margin-top: 4px;
      font-family: 'Monaco', 'Menlo', monospace;
      font-size: 11px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    
    .event-time {
      color: #666;
      font-size: 10px;
      float: right;
    }
    
    .actions {
      padding: 15px;
      background: #111;
      border-top: 1px solid #222;
      display: flex;
      gap: 10px;
    }
    
    .btn {
      flex: 1;
      padding: 8px;
      border: none;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
      background: #222;
      color: #e0e0e0;
    }
    
    .btn:hover {
      background: #333;
    }
    
    .btn.primary {
      background: #667eea;
      color: white;
    }
    
    .btn.primary:hover {
      background: #5a67d8;
    }
    
    .empty-state {
      padding: 40px;
      text-align: center;
      color: #666;
    }
    
    .realtime-indicator {
      display: inline-block;
      width: 6px;
      height: 6px;
      background: #4caf50;
      border-radius: 50%;
      margin-left: 5px;
      animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">DevIntel</div>
    <div class="status">
      <div id="statusDot" class="status-dot"></div>
      <span id="statusText" style="font-size: 12px;">Connecting...</span>
    </div>
  </div>
  
  <div class="controls">
    <div class="filter-group">
      <div class="filter-label">Event Types</div>
      <div class="filter-chips">
        <div class="chip active" data-type="all">All</div>
        <div class="chip" data-type="log">Logs</div>
        <div class="chip" data-type="error">Errors</div>
        <div class="chip" data-type="warn">Warnings</div>
        <div class="chip" data-type="network">Network</div>
        <div class="chip" data-type="performance">Performance</div>
      </div>
    </div>
    <input type="text" class="search-box" placeholder="Filter by pattern or regex..." id="patternFilter">
  </div>
  
  <div class="events-container" id="eventsContainer">
    <div class="empty-state">
      <div style="font-size: 24px; margin-bottom: 10px;">📡</div>
      <div>Waiting for events...</div>
    </div>
  </div>
  
  <div class="actions">
    <button class="btn" id="clearBtn">Clear</button>
    <button class="btn" id="exportBtn">Export</button>
    <button class="btn primary" id="dashboardBtn">Dashboard</button>
  </div>
  
  <script src="popup.js"></script>
</body>
</html>`;

// popup.js - Enhanced popup logic
const POPUP_JS = `
class DevIntelPopup {
  constructor() {
    this.events = [];
    this.filters = {
      types: ['all'],
      pattern: ''
    };
    this.connected = false;
    
    this.init();
  }
  
  init() {
    this.setupEventListeners();
    this.checkConnection();
    this.loadEvents();
    this.startRealtimeUpdates();
  }
  
  setupEventListeners() {
    // Filter chips
    document.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', (e) => {
        const type = e.target.dataset.type;
        
        if (type === 'all') {
          document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
          e.target.classList.add('active');
          this.filters.types = ['all'];
        } else {
          document.querySelector('.chip[data-type="all"]').classList.remove('active');
          e.target.classList.toggle('active');
          
          if (e.target.classList.contains('active')) {
            this.filters.types = this.filters.types.filter(t => t !== 'all');
            if (!this.filters.types.includes(type)) {
              this.filters.types.push(type);
            }
          } else {
            this.filters.types = this.filters.types.filter(t => t !== type);
            if (this.filters.types.length === 0) {
              this.filters.types = ['all'];
              document.querySelector('.chip[data-type="all"]').classList.add('active');
            }
          }
        }
        
        this.saveFilters();
        this.renderEvents();
      });
    });
    
    // Pattern filter
    const patternInput = document.getElementById('patternFilter');
    let debounceTimer;
    patternInput.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        this.filters.pattern = e.target.value;
        this.saveFilters();
        this.renderEvents();
      }, 300);
    });
    
    // Buttons
    document.getElementById('clearBtn').addEventListener('click', () => {
      this.events = [];
      this.renderEvents();
    });
    
    document.getElementById('exportBtn').addEventListener('click', () => {
      this.exportEvents();
    });
    
    document.getElementById('dashboardBtn').addEventListener('click', () => {
      chrome.tabs.create({ url: 'http://localhost:8000/dashboard' });
    });
  }
  
  async checkConnection() {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs[0]) return;
      
      chrome.tabs.sendMessage(tabs[0].id, { action: 'getStatus' }, (response) => {
        if (chrome.runtime.lastError) {
          this.updateStatus(false);
          return;
        }
        
        this.connected = response?.connected || false;
        this.updateStatus(this.connected);
        
        if (response?.sessionId) {
          this.sessionId = response.sessionId;
        }
      });
    });
  }
  
  updateStatus(connected) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    
    if (connected) {
      dot.classList.remove('disconnected');
      text.textContent = 'Connected';
      text.innerHTML = 'Connected<span class="realtime-indicator"></span>';
    } else {
      dot.classList.add('disconnected');
      text.textContent = 'Disconnected';
    }
  }
  
  async loadEvents() {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs[0]) return;
      
      chrome.tabs.sendMessage(tabs[0].id, { action: 'getBuffer' }, (response) => {
        if (response?.buffer) {
          this.events = response.buffer;
          this.renderEvents();
        }
      });
    });
  }
  
  renderEvents() {
    const container = document.getElementById('eventsContainer');
    const filteredEvents = this.filterEvents();
    
    if (filteredEvents.length === 0) {
      container.innerHTML = '<div class="empty-state"><div style="font-size: 24px; margin-bottom: 10px;">🔍</div><div>No events match your filters</div></div>';
      return;
    }
    
    container.innerHTML = filteredEvents.map(event => {
      const time = new Date(event.timestamp).toLocaleTimeString();
      const message = event.content?.message || event.content?.url || 'Unknown event';
      
      return \`
        <div class="event-item">
          <div>
            <span class="event-type \${event.type}">\${event.type.toUpperCase()}</span>
            <span class="event-time">\${time}</span>
          </div>
          <div class="event-message">\${this.escapeHtml(message)}</div>
        </div>
      \`;
    }).join('');
    
    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
  }
  
  filterEvents() {
    return this.events.filter(event => {
      // Type filter
      if (!this.filters.types.includes('all') && !this.filters.types.includes(event.type)) {
        return false;
      }
      
      // Pattern filter
      if (this.filters.pattern) {
        const message = JSON.stringify(event.content).toLowerCase();
        try {
          const regex = new RegExp(this.filters.pattern, 'i');
          return regex.test(message);
        } catch (e) {
          return message.includes(this.filters.pattern.toLowerCase());
        }
      }
      
      return true;
    });
  }
  
  saveFilters() {
    chrome.storage.local.set({ filters: this.filters });
  }
  
  exportEvents() {
    const data = {
      sessionId: this.sessionId,
      exportDate: new Date().toISOString(),
      events: this.filterEvents()
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    chrome.downloads.download({
      url: url,
      filename: \`devintel-export-\${Date.now()}.json\`
    });
  }
  
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
  
  startRealtimeUpdates() {
    // Listen for new events
    chrome.runtime.onMessage.addListener((request) => {
      if (request.action === 'newEvent') {
        this.events.push(request.event);
        if (this.events.length > 1000) {
          this.events = this.events.slice(-500);
        }
        this.renderEvents();
      }
    });
    
    // Check connection every 5 seconds
    setInterval(() => this.checkConnection(), 5000);
  }
}

// Initialize popup
new DevIntelPopup();
`;

// ============= VSCode Extension =============
// package.json for VSCode extension
const VSCODE_PACKAGE = {
  "name": "devintel-vscode",
  "displayName": "DevIntel for VSCode",
  "description": "Real-time development intelligence and error tracking",
  "version": "1.0.0",
  "engines": {
    "vscode": "^1.74.0"
  },
  "categories": ["Debuggers", "Linters", "Other"],
  "activationEvents": [
    "onStartupFinished"
  ],
  "main": "./extension.js",
  "contributes": {
    "commands": [
      {
        "command": "devintel.connect",
        "title": "DevIntel: Connect to Server"
      },
      {
        "command": "devintel.showDashboard",
        "title": "DevIntel: Show Dashboard"
      },
      {
        "command": "devintel.analyzeFile",
        "title": "DevIntel: Analyze Current File"
      },
      {
        "command": "devintel.trackChanges",
        "title": "DevIntel: Track File Changes"
      }
    ],
    "configuration": {
      "title": "DevIntel",
      "properties": {
        "devintel.serverUrl": {
          "type": "string",
          "default": "http://localhost:8000",
          "description": "DevIntel server URL"
        },
        "devintel.autoConnect": {
          "type": "boolean",
          "default": true,
          "description": "Automatically connect on startup"
        },
        "devintel.trackGitChanges": {
          "type": "boolean",
          "default": true,
          "description": "Track git commits and changes"
        },
        "devintel.fileWatchPatterns": {
          "type": "array",
          "default": ["**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx"],
          "description": "File patterns to watch for changes"
        }
      }
    },
    "views": {
      "explorer": [
        {
          "id": "devintelExplorer",
          "name": "DevIntel",
          "icon": "$(pulse)",
          "contextualTitle": "DevIntel Explorer"
        }
      ]
    }
  }
};

// extension.js - VSCode extension main file
const VSCODE_EXTENSION = `
const vscode = require('vscode');
const WebSocket = require('ws');
const { spawn } = require('child_process');
const path = require('path');

class DevIntelExtension {
  constructor(context) {
    this.context = context;
    this.ws = null;
    this.sessionId = \`vscode_\${Date.now()}_\${Math.random().toString(36).substr(2, 9)}\`;
    this.outputChannel = vscode.window.createOutputChannel('DevIntel');
    this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.fileWatcher = null;
    this.gitWatcher = null;
    
    this.init();
  }
  
  init() {
    // Register commands
    this.context.subscriptions.push(
      vscode.commands.registerCommand('devintel.connect', () => this.connect()),
      vscode.commands.registerCommand('devintel.showDashboard', () => this.showDashboard()),
      vscode.commands.registerCommand('devintel.analyzeFile', () => this.analyzeCurrentFile()),
      vscode.commands.registerCommand('devintel.trackChanges', () => this.toggleFileTracking())
    );
    
    // Setup status bar
    this.statusBarItem.text = '$(pulse) DevIntel: Disconnected';
    this.statusBarItem.command = 'devintel.connect';
    this.statusBarItem.show();
    
    // Auto-connect if enabled
    const config = vscode.workspace.getConfiguration('devintel');
    if (config.get('autoConnect')) {
      this.connect();
    }
    
    // Setup file watching
    this.setupFileWatcher();
    
    // Setup git tracking
    if (config.get('trackGitChanges')) {
      this.setupGitTracking();
    }
    
    // Track active editor changes
    vscode.window.onDidChangeActiveTextEditor(editor => {
      if (editor) {
        this.trackFileOpen(editor.document);
      }
    });
    
    // Track document changes
    vscode.workspace.onDidChangeTextDocument(event => {
      this.trackDocumentChange(event);
    });
    
    // Track debugging sessions
    vscode.debug.onDidStartDebugSession(session => {
      this.captureEvent({
        type: 'debug',
        subtype: 'session-start',
        content: {
          name: session.name,
          type: session.type,
          workspace: session.workspaceFolder?.name
        }
      });
    });
    
    // Track terminal commands
    vscode.window.onDidOpenTerminal(terminal => {
      this.trackTerminal(terminal);
    });
  }
  
  connect() {
    const config = vscode.workspace.getConfiguration('devintel');
    const serverUrl = config.get('serverUrl').replace('http', 'ws');
    
    try {
      this.ws = new WebSocket(\`\${serverUrl}/ws\`);
      
      this.ws.on('open', () => {
        this.statusBarItem.text = '$(pulse) DevIntel: Connected';
        this.statusBarItem.color = '#4CAF50';
        this.outputChannel.appendLine('[Connected] DevIntel server connected');
        
        // Send initialization
        this.ws.send(JSON.stringify({
          type: 'init',
          sessionId: this.sessionId,
          source: 'vscode',
          workspace: vscode.workspace.name || 'Unknown',
          folders: vscode.workspace.workspaceFolders?.map(f => f.uri.fsPath) || []
        }));
        
        vscode.window.showInformationMessage('DevIntel connected successfully');
      });
      
      this.ws.on('close', () => {
        this.statusBarItem.text = '$(pulse) DevIntel: Disconnected';
        this.statusBarItem.color = '#F44336';
        this.outputChannel.appendLine('[Disconnected] Connection closed');
        
        // Attempt reconnect after 5 seconds
        setTimeout(() => this.connect(), 5000);
      });
      
      this.ws.on('error', (error) => {
        this.outputChannel.appendLine(\`[Error] \${error.message}\`);
        vscode.window.showErrorMessage(\`DevIntel connection error: \${error.message}\`);
      });
      
      this.ws.on('message', (data) => {
        const message = JSON.parse(data);
        if (message.type === 'solution') {
          this.showSolution(message);
        }
      });
    } catch (error) {
      vscode.window.showErrorMessage(\`Failed to connect to DevIntel: \${error.message}\`);
    }
  }
  
  setupFileWatcher() {
    const config = vscode.workspace.getConfiguration('devintel');
    const patterns = config.get('fileWatchPatterns');
    
    patterns.forEach(pattern => {
      const watcher = vscode.workspace.createFileSystemWatcher(pattern);
      
      watcher.onDidCreate(uri => {
        this.captureEvent({
          type: 'file',
          subtype: 'created',
          content: {
            path: uri.fsPath,
            workspace: vscode.workspace.getWorkspaceFolder(uri)?.name
          }
        });
      });
      
      watcher.onDidChange(uri => {
        this.trackFileChange(uri);
      });
      
      watcher.onDidDelete(uri => {
        this.captureEvent({
          type: 'file',
          subtype: 'deleted',
          content: {
            path: uri.fsPath
          }
        });
      });
      
      this.context.subscriptions.push(watcher);
    });
  }
  
  async trackFileChange(uri) {
    const document = await vscode.workspace.openTextDocument(uri);
    const diagnostics = vscode.languages.getDiagnostics(uri);
    
    // Capture file change with diagnostics
    this.captureEvent({
      type: 'file',
      subtype: 'changed',
      content: {
        path: uri.fsPath,
        language: document.languageId,
        lineCount: document.lineCount,
        diagnostics: diagnostics.map(d => ({
          severity: d.severity,
          message: d.message,
          range: {
            start: { line: d.range.start.line, character: d.range.start.character },
            end: { line: d.range.end.line, character: d.range.end.character }
          },
          source: d.source
        }))
      }
    });
  }
  
  setupGitTracking() {
    // Watch .git directory for changes
    const gitWatcher = vscode.workspace.createFileSystemWatcher('**/.git/**');
    
    // Track commits by watching HEAD changes
    gitWatcher.onDidChange(async (uri) => {
      if (uri.fsPath.endsWith('HEAD') || uri.fsPath.endsWith('index')) {
        const gitInfo = await this.getGitInfo();
        if (gitInfo) {
          this.captureEvent({
            type: 'git',
            subtype: 'activity',
            content: gitInfo
          });
        }
      }
    });
    
    this.context.subscriptions.push(gitWatcher);
  }
  
  async getGitInfo() {
    return new Promise((resolve) => {
      const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!cwd) {
        resolve(null);
        return;
      }
      
      // Get current branch
      const gitBranch = spawn('git', ['branch', '--show-current'], { cwd });
      let branch = '';
      
      gitBranch.stdout.on('data', (data) => {
        branch = data.toString().trim();
      });
      
      gitBranch.on('close', () => {
        // Get last commit
        const gitLog = spawn('git', ['log', '-1', '--pretty=format:%H|%an|%ae|%s'], { cwd });
        let commitInfo = '';
        
        gitLog.stdout.on('data', (data) => {
          commitInfo = data.toString().trim();
        });
        
        gitLog.on('close', () => {
          if (commitInfo) {
            const [hash, author, email, message] = commitInfo.split('|');
            resolve({
              branch,
              lastCommit: {
                hash,
                author,
                email,
                message
              }
            });
          } else {
            resolve(null);
          }
        });
      });
    });
  }
  
  trackTerminal(terminal) {
    // This is a simplified version - in reality, you'd need to use the proposed API
    // or a more complex solution to capture terminal output
    terminal.onDidWriteData(data => {
      if (data.trim() && !data.includes('\\x1b')) { // Skip escape sequences
        this.captureEvent({
          type: 'terminal',
          subtype: 'command',
          content: {
            name: terminal.name,
            data: data.trim()
          }
        });
      }
    });
  }
  
  async analyzeCurrentFile() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active file to analyze');
      return;
    }
    
    const document = editor.document;
    const diagnostics = vscode.languages.getDiagnostics(document.uri);
    
    // Send file for analysis
    this.captureEvent({
      type: 'analysis',
      subtype: 'file-analysis',
      content: {
        path: document.uri.fsPath,
        language: document.languageId,
        content: document.getText(),
        diagnostics: diagnostics.map(d => ({
          severity: d.severity,
          message: d.message,
          line: d.range.start.line,
          character: d.range.start.character
        }))
      }
    });
    
    vscode.window.showInformationMessage(\`Analyzing \${path.basename(document.uri.fsPath)}...\`);
  }
  
  trackFileOpen(document) {
    this.captureEvent({
      type: 'file',
      subtype: 'opened',
      content: {
        path: document.uri.fsPath,
        language: document.languageId,
        lineCount: document.lineCount
      }
    });
  }
  
  trackDocumentChange(event) {
    if (event.contentChanges.length === 0) return;
    
    const change = event.contentChanges[0];
    this.captureEvent({
      type: 'edit',
      subtype: 'text-change',
      content: {
        path: event.document.uri.fsPath,
        change: {
          range: {
            start: { line: change.range.start.line, character: change.range.start.character },
            end: { line: change.range.end.line, character: change.range.end.character }
          },
          text: change.text.substring(0, 100), // Limit text size
          rangeLength: change.rangeLength
        }
      }
    });
  }
  
  captureEvent(event) {
    const fullEvent = {
      ...event,
      timestamp: Date.now(),
      sessionId: this.sessionId,
      context: {
        workspace: vscode.workspace.name,
        platform: process.platform,
        vscodeVersion: vscode.version
      }
    };
    
    // Send via WebSocket if connected
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'event',
        event: fullEvent
      }));
    }
    
    // Log to output channel
    this.outputChannel.appendLine(\`[\${event.type}] \${JSON.stringify(event.content)}\`);
  }
  
  showSolution(message) {
    const solution = message.solution;
    
    // Create webview panel for solution
    const panel = vscode.window.createWebviewPanel(
      'devintelSolution',
      'DevIntel Solution',
      vscode.ViewColumn.Two,
      { enableScripts: true }
    );
    
    panel.webview.html = \`
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body {
            font-family: var(--vscode-font-family);
            padding: 20px;
            line-height: 1.6;
          }
          .solution-header {
            border-bottom: 2px solid var(--vscode-panel-border);
            padding-bottom: 10px;
            margin-bottom: 20px;
          }
          .confidence {
            float: right;
            background: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
          }
          .code-block {
            background: var(--vscode-textCodeBlock-background);
            padding: 15px;
            border-radius: 4px;
            margin: 10px 0;
            overflow-x: auto;
          }
          .explanation {
            background: var(--vscode-textBlockQuote-background);
            border-left: 4px solid var(--vscode-textLink-foreground);
            padding: 10px 15px;
            margin: 15px 0;
          }
          button {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            margin-right: 10px;
          }
          button:hover {
            background: var(--vscode-button-hoverBackground);
          }
        </style>
      </head>
      <body>
        <div class="solution-header">
          <h2>Solution Found</h2>
          <span class="confidence">Confidence: \${Math.round(solution.confidence * 100)}%</span>
        </div>
        
        <h3>Root Cause</h3>
        <p>\${solution.root_cause}</p>
        
        <h3>Suggested Fix</h3>
        <div class="code-block">
          <pre><code>\${solution.solution_code}</code></pre>
        </div>
        
        <h3>Explanation</h3>
        <div class="explanation">
          \${solution.explanation}
        </div>
        
        <div style="margin-top: 20px;">
          <button onclick="applyFix()">Apply Fix</button>
          <button onclick="dismiss()">Dismiss</button>
        </div>
        
        <script>
          const vscode = acquireVsCodeApi();
          
          function applyFix() {
            vscode.postMessage({
              command: 'applyFix',
              code: \${JSON.stringify(solution.solution_code)}
            });
          }
          
          function dismiss() {
            vscode.postMessage({ command: 'dismiss' });
          }
        </script>
      </body>
      </html>
    \`;
    
    // Handle messages from webview
    panel.webview.onDidReceiveMessage(
      message => {
        switch (message.command) {
          case 'applyFix':
            this.applyFixToEditor(message.code);
            panel.dispose();
            break;
          case 'dismiss':
            panel.dispose();
            break;
        }
      },
      undefined,
      this.context.subscriptions
    );
  }
  
  applyFixToEditor(code) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor to apply fix');
      return;
    }
    
    // Insert at cursor position
    editor.edit(editBuilder => {
      editBuilder.insert(editor.selection.active, code);
    });
    
    vscode.window.showInformationMessage('Fix applied successfully');
  }
  
  showDashboard() {
    const config = vscode.workspace.getConfiguration('devintel');
    const dashboardUrl = \`\${config.get('serverUrl')}/dashboard?session=\${this.sessionId}\`;
    vscode.env.openExternal(vscode.Uri.parse(dashboardUrl));
  }
  
  toggleFileTracking() {
    // Implementation for toggling file tracking
    vscode.window.showInformationMessage('File tracking toggled');
  }
}

function activate(context) {
  const extension = new DevIntelExtension(context);
  context.subscriptions.push(extension);
}

function deactivate() {}

module.exports = {
  activate,
  deactivate
};
`;

// Export all components
module.exports = {
  chromeExtension: {
    manifest: {
      "manifest_version": 3,
      "name": "DevIntel - Development Intelligence",
      "version": "2.0.0",
      "description": "Real-time development intelligence with one-click connect",
      "permissions": [
        "storage",
        "tabs",
        "downloads"
      ],
      "host_permissions": [
        "http://localhost:8000/*",
        "<all_urls>"
      ],
      "background": {
        "service_worker": "background.js"
      },
      "content_scripts": [
        {
          "matches": ["<all_urls>"],
          "js": ["injector.js"],
          "run_at": "document_start",
          "all_frames": false
        }
      ],
      "action": {
        "default_popup": "popup.html",
        "default_icon": {
          "16": "icon16.png",
          "48": "icon48.png",
          "128": "icon128.png"
        }
      },
      "icons": {
        "16": "icon16.png",
        "48": "icon48.png",
        "128": "icon128.png"
      }
    },
    popup: {
      html: POPUP_HTML,
      js: POPUP_JS
    }
  },
  vscodeExtension: {
    package: VSCODE_PACKAGE,
    extension: VSCODE_EXTENSION
  }
};
