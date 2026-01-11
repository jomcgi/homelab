import express, { Request, Response } from "express";
import { WebSocketServer, WebSocket } from "ws";
import { createServer, ServerResponse, IncomingMessage } from "http";
import { Socket } from "net";
import { createProxyMiddleware } from "http-proxy-middleware";
import { v4 as uuidv4 } from "uuid";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";

const app = express();
app.use(express.json());

const PORT = parseInt(process.env.PORT || "3000", 10);
const HOME = process.env.HOME || "/home/user";
const WORKTREES_DIR = "/tmp/claude-worktrees";
const SESSIONS_DIR = path.join(HOME, ".claude-api", "sessions");
const STATIC_DIR = process.env.STATIC_DIR || "/app/public";
const CLAUDE_BIN = path.join(HOME, ".npm-global", "bin", "claude");
const TTYD_PORT = 7681;

// Ensure directories exist
fs.mkdirSync(SESSIONS_DIR, { recursive: true });
fs.mkdirSync(WORKTREES_DIR, { recursive: true });

// Authentication state
let authTtydProcess: ChildProcess | null = null;

interface Session {
  id: string;
  name: string;
  workdir: string;
  createdAt: Date;
  claudeSessionId?: string; // Claude's internal session ID for --resume
  process?: ChildProcess;
  isProcessing: boolean; // Prevent concurrent requests
  wsClients: Set<WebSocket>;
}

const sessions = new Map<string, Session>();

// Health check
app.get("/api/health", (_req, res) => {
  res.json({ status: "ok", sessions: sessions.size });
});

// Auth status - check if Claude is authenticated
app.get("/api/auth/status", (_req, res) => {
  const authFile = path.join(HOME, ".claude", "auth.json");
  const authenticated = fs.existsSync(authFile);

  res.json({
    authenticated,
    terminalActive: authTtydProcess !== null,
  });
});

// Start auth terminal (spawn ttyd)
app.post("/api/auth/start", (_req, res) => {
  // Clean up any existing auth process
  if (authTtydProcess) {
    console.log("Killing existing ttyd process...");
    authTtydProcess.kill();
    authTtydProcess = null;
  }

  try {
    // Spawn ttyd with claude /login
    // -W: Don't wait for initial connection (start immediately)
    // -p: Port to listen on
    // -t: Set terminal type
    console.log(`Starting ttyd on port ${TTYD_PORT}...`);

    // Run claude interactively - user types /login inside the session
    const ttyd = spawn(
      "ttyd",
      [
        "-p",
        TTYD_PORT.toString(),
        "-W", // Start immediately
        "-t",
        "titleFixed=Claude Authentication",
        CLAUDE_BIN,
      ],
      {
        cwd: HOME,
        env: { ...process.env, HOME },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );

    authTtydProcess = ttyd;

    ttyd.stdout.on("data", (data) => {
      console.log(`[ttyd stdout] ${data.toString().trim()}`);
    });

    ttyd.stderr.on("data", (data) => {
      console.log(`[ttyd stderr] ${data.toString().trim()}`);
    });

    ttyd.on("close", (code) => {
      console.log(`ttyd process exited with code ${code}`);
      authTtydProcess = null;
    });

    ttyd.on("error", (err) => {
      console.error(`ttyd process error: ${err}`);
      authTtydProcess = null;
    });

    // Give ttyd a moment to start
    setTimeout(() => {
      res.json({
        success: true,
        message: "Terminal started. Connect to /api/auth/terminal",
        terminalUrl: "/api/auth/terminal",
      });
    }, 500);
  } catch (err) {
    console.error("Failed to start ttyd:", err);
    res.status(500).json({ error: "Failed to start terminal" });
  }
});

// Stop auth terminal
app.post("/api/auth/stop", (_req, res) => {
  if (authTtydProcess) {
    console.log("Stopping ttyd process...");
    authTtydProcess.kill();
    authTtydProcess = null;
  }
  res.json({ success: true });
});

// Proxy to ttyd terminal (HTTP only - WebSocket handled separately)
const ttydProxy = createProxyMiddleware({
  target: `http://localhost:${TTYD_PORT}`,
  changeOrigin: true,
  pathRewrite: {
    "^/api/auth/terminal": "", // Remove prefix
  },
  on: {
    error: (
      err: Error,
      req: Request,
      res: Response | ServerResponse | Socket,
    ) => {
      console.error("Proxy error:", err);
      if (res instanceof ServerResponse) {
        res.writeHead(502);
        res.end("Terminal not available");
      }
    },
  },
});
app.use("/api/auth/terminal", ttydProxy);

// List sessions
app.get("/api/sessions", (_req, res) => {
  const sessionList = Array.from(sessions.values()).map((s) => ({
    id: s.id,
    name: s.name,
    workdir: s.workdir,
    createdAt: s.createdAt,
    active: !!s.process,
  }));
  res.json(sessionList);
});

// Create session
app.post("/api/sessions", (req, res) => {
  const { name, workdir } = req.body;
  const id = uuidv4();
  const sessionWorkdir = workdir || path.join(WORKTREES_DIR, id);

  // Create workdir if it doesn't exist
  if (!fs.existsSync(sessionWorkdir)) {
    fs.mkdirSync(sessionWorkdir, { recursive: true });
  }

  const session: Session = {
    id,
    name: name || `Session ${id.slice(0, 8)}`,
    workdir: sessionWorkdir,
    createdAt: new Date(),
    isProcessing: false,
    wsClients: new Set(),
  };

  sessions.set(id, session);
  console.log(
    `Session created: ${id}, Total sessions in memory: ${sessions.size}`,
  );

  // Save session metadata
  const metaPath = path.join(SESSIONS_DIR, `${id}.json`);
  fs.writeFileSync(
    metaPath,
    JSON.stringify({
      id: session.id,
      name: session.name,
      workdir: session.workdir,
      createdAt: session.createdAt,
    }),
  );

  res.status(201).json({
    id: session.id,
    name: session.name,
    workdir: session.workdir,
    createdAt: session.createdAt,
  });
});

// Get session
app.get("/api/sessions/:id", (req, res) => {
  const session = sessions.get(req.params.id);
  if (!session) {
    return res.status(404).json({ error: "Session not found" });
  }
  res.json({
    id: session.id,
    name: session.name,
    workdir: session.workdir,
    createdAt: session.createdAt,
    active: !!session.process,
  });
});

// Delete session
app.delete("/api/sessions/:id", (req, res) => {
  const session = sessions.get(req.params.id);
  if (!session) {
    return res.status(404).json({ error: "Session not found" });
  }

  // Kill process if running
  if (session.process) {
    session.process.kill();
  }

  // Close WebSocket connections
  session.wsClients.forEach((ws) => ws.close());

  // Remove session
  sessions.delete(req.params.id);

  // Remove metadata file
  const metaPath = path.join(SESSIONS_DIR, `${req.params.id}.json`);
  if (fs.existsSync(metaPath)) {
    fs.unlinkSync(metaPath);
  }

  res.status(204).send();
});

// Serve static frontend
app.use(express.static(STATIC_DIR));

// SPA fallback - serve index.html for all non-API routes
app.get("*", (req, res) => {
  if (!req.path.startsWith("/api/")) {
    res.sendFile(path.join(STATIC_DIR, "index.html"));
  } else {
    res.status(404).json({ error: "Not found" });
  }
});

// Create HTTP server
const server = createServer(app);

// WebSocket server for ttyd terminal proxy
// Uses proper WebSocket-to-WebSocket proxying (like ttyd-session-manager did with gorilla/websocket)
// IMPORTANT: Must accept "tty" subprotocol or ttyd client will reject the connection
// IMPORTANT: Disable compression on server - browser may negotiate it but ttyd doesn't use it
const ttydWss = new WebSocketServer({
  noServer: true,
  perMessageDeflate: false,
  handleProtocols: (protocols) => {
    // Accept "tty" subprotocol if client requests it (ttyd always does)
    if (protocols.has("tty")) {
      return "tty";
    }
    return false;
  },
});

ttydWss.on("connection", (clientWs: WebSocket) => {
  console.log("Client WebSocket connected, connecting to ttyd...");

  // Connect to ttyd using WebSocket protocol with "tty" subprotocol
  // IMPORTANT: Disable perMessageDeflate to avoid compression mismatch with ttyd
  const ttydWs = new WebSocket(`ws://localhost:${TTYD_PORT}/ws`, ["tty"], {
    perMessageDeflate: false,
  });

  // Set binary type to match ttyd expectations
  ttydWs.binaryType = "arraybuffer";

  // Track connection state
  let ttydConnected = false;

  ttydWs.on("open", () => {
    console.log("Connected to ttyd WebSocket");
    ttydConnected = true;
  });

  ttydWs.on("message", (data: Buffer, isBinary: boolean) => {
    // Forward ttyd messages to client, preserving binary/text type
    if (clientWs.readyState === WebSocket.OPEN) {
      clientWs.send(data, { binary: isBinary });
    }
  });

  ttydWs.on("close", (code, reason) => {
    console.log(`ttyd WebSocket closed: ${code} ${reason}`);
    ttydConnected = false;
    if (clientWs.readyState === WebSocket.OPEN) {
      clientWs.close(code, reason.toString());
    }
  });

  ttydWs.on("error", (err) => {
    console.error("ttyd WebSocket error:", err);
    ttydConnected = false;
    if (clientWs.readyState === WebSocket.OPEN) {
      clientWs.close(1011, "ttyd connection error");
    }
  });

  clientWs.on("message", (data: Buffer, isBinary: boolean) => {
    // Forward client messages to ttyd, preserving binary/text type
    if (ttydWs.readyState === WebSocket.OPEN) {
      ttydWs.send(data, { binary: isBinary });
    }
  });

  clientWs.on("close", (code, reason) => {
    console.log(`Client WebSocket closed: ${code} ${reason}`);
    // Only close ttyd connection if it's open or connecting
    if (ttydConnected || ttydWs.readyState === WebSocket.CONNECTING) {
      ttydWs.close();
    }
  });

  clientWs.on("error", (err) => {
    console.error("Client WebSocket error:", err);
    if (ttydConnected || ttydWs.readyState === WebSocket.CONNECTING) {
      ttydWs.close();
    }
  });
});

// WebSocket server for streaming (also noServer to avoid duplicate upgrade handlers)
const wss = new WebSocketServer({ noServer: true });

// Handle ALL WebSocket upgrades in one place to avoid conflicts
// When using { server, path } option, ws library registers its own upgrade handler
// which can conflict with manual handlers and send duplicate responses
server.on("upgrade", (req: IncomingMessage, socket: Socket, head: Buffer) => {
  const url = req.url || "";
  console.log(`[UPGRADE] Request received: ${url}, headers: ${JSON.stringify(req.headers)}`);

  if (url.startsWith("/api/auth/terminal/ws")) {
    console.log(`WebSocket upgrade request for ttyd: ${url}`);
    ttydWss.handleUpgrade(req, socket, head, (ws) => {
      ttydWss.emit("connection", ws, req);
    });
  } else if (url.startsWith("/ws")) {
    console.log(`WebSocket upgrade request for session: ${url}`);
    wss.handleUpgrade(req, socket, head, (ws) => {
      wss.emit("connection", ws, req);
    });
  } else {
    console.log(`Unknown WebSocket upgrade request: ${url}`);
    socket.destroy();
  }
});

wss.on("connection", (ws, req) => {
  console.log(`Session WebSocket connection received, URL: ${req.url}`);

  let url: URL;
  try {
    url = new URL(req.url || "", `http://localhost:${PORT}`);
  } catch (err) {
    console.error(`Failed to parse WebSocket URL: ${req.url}`, err);
    ws.close(4001, "Invalid URL");
    return;
  }

  const sessionId = url.searchParams.get("session");
  console.log(`Session ID from URL: ${sessionId}`);

  if (!sessionId) {
    console.log("Missing session parameter, closing connection");
    ws.close(4000, "Missing session parameter");
    return;
  }

  const session = sessions.get(sessionId);
  if (!session) {
    console.log(
      `Session ${sessionId} not found. Available sessions: ${Array.from(sessions.keys()).join(", ")}`,
    );
    ws.close(4004, "Session not found");
    return;
  }

  console.log(`Session ${sessionId} found, adding client`);

  // Add client to session
  session.wsClients.add(ws);

  ws.on("message", (data) => {
    const message = JSON.parse(data.toString());
    console.log(
      `Received message for session ${session.id}: ${JSON.stringify(message).substring(0, 100)}`,
    );

    if (message.type === "input") {
      if (session.isProcessing) {
        console.log(`Session ${session.id} is already processing, queuing not implemented`);
        ws.send(JSON.stringify({
          type: "error",
          content: "Please wait for the current response to complete",
        }));
        return;
      }

      // Run Claude in print mode with the user's message
      console.log(`Running Claude for session ${session.id} with message: ${message.content.substring(0, 50)}...`);
      runClaudeMessage(session, message.content);
    }
  });

  ws.on("close", (code, reason) => {
    console.log(
      `Session ${session.id} WebSocket closed: ${code} ${reason.toString()}`,
    );
    session.wsClients.delete(ws);
  });

  ws.on("error", (err) => {
    console.error(`Session ${session.id} WebSocket error:`, err);
  });

  // Send welcome message
  console.log(`Sending welcome message to session ${session.id}`);
  try {
    ws.send(
      JSON.stringify({
        type: "connected",
        sessionId: session.id,
        name: session.name,
        workdir: session.workdir,
      }),
    );
    console.log(`Welcome message sent successfully to session ${session.id}`);
  } catch (err) {
    console.error(`Failed to send welcome message to session ${session.id}:`, err);
  }
});

// Run Claude in print mode with a single message (like cui does)
function runClaudeMessage(session: Session, userMessage: string) {
  console.log(
    `Running Claude for session ${session.id} in ${session.workdir}`,
  );
  console.log(`Using Claude binary: ${CLAUDE_BIN}`);

  session.isProcessing = true;

  // Build args for print mode
  // -p: print mode (non-interactive)
  // --output-format stream-json: structured JSONL output
  // --verbose: required with stream-json
  // --dangerously-skip-permissions: skip permission prompts
  const args = [
    "-p", // Print mode
    "--output-format", "stream-json",
    "--verbose",
    "--dangerously-skip-permissions",
  ];

  // If we have a previous Claude session, resume it
  if (session.claudeSessionId) {
    args.push("--resume", session.claudeSessionId);
  }

  // Add the user message as the last argument
  args.push(userMessage);

  console.log(`Claude args: ${args.join(" ")}`);

  const claude = spawn(CLAUDE_BIN, args, {
    cwd: session.workdir,
    env: {
      ...process.env,
      HOME,
    },
    stdio: ["inherit", "pipe", "pipe"], // stdin inherit, stdout/stderr piped
    shell: "/bin/bash", // wolfi container doesn't have /bin/sh
  });

  session.process = claude;

  claude.on("spawn", () => {
    console.log(`Claude process spawned with PID ${claude.pid}`);
  });

  claude.on("error", (err) => {
    console.error(`Claude process error: ${err.message}`);
    session.isProcessing = false;
    session.process = undefined;
    broadcast(session, { type: "error", content: `Process error: ${err.message}` });
  });

  // Buffer for incomplete JSON lines
  let buffer = "";

  // Parse JSONL output from stdout
  claude.stdout.on("data", (data: Buffer) => {
    buffer += data.toString();
    const lines = buffer.split("\n");

    // Keep the last incomplete line in the buffer
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;

      try {
        const event = JSON.parse(line);
        handleClaudeEvent(session, event);
      } catch (err) {
        // Not valid JSON, might be regular output
        console.log(`Claude non-JSON output: ${line.substring(0, 100)}`);
      }
    }
  });

  // Stream stderr to WebSocket clients
  claude.stderr.on("data", (data: Buffer) => {
    const content = data.toString();
    console.log(`Claude stderr: ${content.substring(0, 200)}`);
    // Don't broadcast all stderr - it's often just logging
  });

  // Handle process exit
  claude.on("close", (code) => {
    console.log(`Claude process exited with code ${code}`);
    session.isProcessing = false;
    session.process = undefined;

    // Process any remaining buffer
    if (buffer.trim()) {
      try {
        const event = JSON.parse(buffer);
        handleClaudeEvent(session, event);
      } catch {
        // Ignore
      }
    }

    broadcast(session, { type: "done", code });
  });
}

// Handle Claude stream-json events
function handleClaudeEvent(session: Session, event: Record<string, unknown>) {
  console.log(`Claude event: ${event.type || "unknown"}`);

  // Extract the Claude session ID for future --resume calls
  if (event.type === "system" && event.subtype === "init") {
    const init = event as { session_id?: string };
    if (init.session_id) {
      session.claudeSessionId = init.session_id;
      console.log(`Captured Claude session ID: ${session.claudeSessionId}`);
      saveSession(session);
    }
  }

  // Forward assistant messages to clients
  if (event.type === "assistant") {
    const msg = event as { message?: { content?: Array<{ type: string; text?: string }> } };
    if (msg.message?.content) {
      for (const block of msg.message.content) {
        if (block.type === "text" && block.text) {
          broadcast(session, { type: "output", content: block.text });
        }
      }
    }
  }

  // Forward content block deltas (streaming text)
  if (event.type === "content_block_delta") {
    const delta = event as { delta?: { type: string; text?: string } };
    if (delta.delta?.type === "text_delta" && delta.delta.text) {
      broadcast(session, { type: "output", content: delta.delta.text });
    }
  }

  // Handle errors
  if (event.type === "error") {
    const err = event as { error?: { message?: string } };
    broadcast(session, { type: "error", content: err.error?.message || "Unknown error" });
  }
}

// Broadcast message to all session clients
function broadcast(session: Session, message: Record<string, unknown>) {
  const data = JSON.stringify(message);
  session.wsClients.forEach((ws) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(data);
    }
  });
}

// Save session metadata to disk
function saveSession(session: Session) {
  const metaPath = path.join(SESSIONS_DIR, `${session.id}.json`);
  fs.writeFileSync(
    metaPath,
    JSON.stringify({
      id: session.id,
      name: session.name,
      workdir: session.workdir,
      createdAt: session.createdAt,
      claudeSessionId: session.claudeSessionId,
    }),
  );
}

// Load existing sessions on startup
function loadSessions() {
  if (!fs.existsSync(SESSIONS_DIR)) return;

  const files = fs.readdirSync(SESSIONS_DIR);
  for (const file of files) {
    if (!file.endsWith(".json")) continue;

    try {
      const data = JSON.parse(
        fs.readFileSync(path.join(SESSIONS_DIR, file), "utf-8"),
      );
      sessions.set(data.id, {
        id: data.id,
        name: data.name,
        workdir: data.workdir,
        createdAt: new Date(data.createdAt),
        claudeSessionId: data.claudeSessionId,
        isProcessing: false,
        wsClients: new Set(),
      });
    } catch (err) {
      console.error(`Failed to load session ${file}:`, err);
    }
  }
  console.log(`Loaded ${sessions.size} existing sessions`);
  console.log(`Session IDs: ${Array.from(sessions.keys()).join(", ")}`);
}

loadSessions();

// Disable server-level timeouts for WebSocket support
server.timeout = 0;
server.keepAliveTimeout = 0;
server.headersTimeout = 0;

server.listen(PORT, () => {
  console.log(`Claude API server listening on port ${PORT}`);
  console.log(`Serving static files from ${STATIC_DIR}`);
});
