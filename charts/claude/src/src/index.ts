import express from "express";
import { WebSocketServer, WebSocket } from "ws";
import { createServer, IncomingMessage } from "http";
import { Socket } from "net";
import { v4 as uuidv4 } from "uuid";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";

import { setupAuthRoutes, handleTtydUpgrade } from "./auth";

const app = express();
app.use(express.json());

const PORT = parseInt(process.env.PORT || "3000", 10);
const HOME = process.env.HOME || "/home/user";
const WORKTREES_DIR = path.join(HOME, ".claude-api", "worktrees"); // Persistent on PVC
const SESSIONS_DIR = path.join(HOME, ".claude-api", "sessions");
const STATIC_DIR = process.env.STATIC_DIR || "/app/public";
const CLAUDE_BIN = path.join(HOME, ".npm-global", "bin", "claude");

// Ensure directories exist
fs.mkdirSync(SESSIONS_DIR, { recursive: true });
fs.mkdirSync(WORKTREES_DIR, { recursive: true });

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

// Setup auth routes (ttyd terminal for /login)
setupAuthRoutes(app);

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
    `Session created: ${id}, Total sessions in memory: ${sessions.size}`
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
    })
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

// WebSocket server for session streaming
const wss = new WebSocketServer({ noServer: true });

// Handle ALL WebSocket upgrades in one place to avoid conflicts
server.on("upgrade", (req: IncomingMessage, socket: Socket, head: Buffer) => {
  const url = req.url || "";
  console.log(`[UPGRADE] Request received: ${url}`);

  if (url.startsWith("/api/auth/terminal/ws")) {
    handleTtydUpgrade(req, socket, head);
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
      `Session ${sessionId} not found. Available sessions: ${Array.from(sessions.keys()).join(", ")}`
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
      `Received message for session ${session.id}: ${JSON.stringify(message).substring(0, 100)}`
    );

    if (message.type === "input") {
      if (session.isProcessing) {
        console.log(
          `Session ${session.id} is already processing, queuing not implemented`
        );
        ws.send(
          JSON.stringify({
            type: "error",
            content: "Please wait for the current response to complete",
          })
        );
        return;
      }

      // Run Claude in print mode with the user's message
      console.log(
        `Running Claude for session ${session.id} with message: ${message.content.substring(0, 50)}...`
      );
      runClaudeMessage(session, message.content);
    }
  });

  ws.on("close", (code, reason) => {
    console.log(
      `Session ${session.id} WebSocket closed: ${code} ${reason.toString()}`
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
      })
    );
    console.log(`Welcome message sent successfully to session ${session.id}`);
  } catch (err) {
    console.error(
      `Failed to send welcome message to session ${session.id}:`,
      err
    );
  }
});

// Run Claude in print mode with a single message (like cui does)
function runClaudeMessage(session: Session, userMessage: string) {
  console.log(
    `Running Claude for session ${session.id} in ${session.workdir}`
  );
  console.log(`Using Claude binary: ${CLAUDE_BIN}`);

  // Ensure workdir exists (may have been cleared if in /tmp after pod restart)
  if (!fs.existsSync(session.workdir)) {
    console.log(`Creating workdir: ${session.workdir}`);
    fs.mkdirSync(session.workdir, { recursive: true });
  }

  session.isProcessing = true;

  // Build args based on whether this is a new conversation or resume
  // cui pattern:
  //   new: -p <message> --output-format stream-json --verbose
  //   resume: --resume <sessionId> <message> --output-format stream-json --verbose
  const args: string[] = [];

  if (session.claudeSessionId) {
    // Resume existing conversation (no -p flag)
    args.push("--resume", session.claudeSessionId);
    args.push(userMessage);
  } else {
    // New conversation with print mode
    args.push("-p");
    args.push(userMessage);
  }

  // Common flags
  args.push("--output-format", "stream-json");
  args.push("--verbose");
  args.push("--dangerously-skip-permissions");

  console.log(`Claude args: ${args.join(" ")}`);

  const claude = spawn(CLAUDE_BIN, args, {
    cwd: session.workdir,
    env: {
      ...process.env,
      HOME,
    },
    stdio: ["inherit", "pipe", "pipe"], // stdin inherit, stdout/stderr piped
  });

  session.process = claude;

  claude.on("spawn", () => {
    console.log(`Claude process spawned with PID ${claude.pid}`);
  });

  claude.on("error", (err) => {
    console.error(`Claude process error: ${err.message}`);
    session.isProcessing = false;
    session.process = undefined;
    broadcast(session, {
      type: "error",
      content: `Process error: ${err.message}`,
    });
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
      } catch {
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
    const msg = event as {
      message?: { content?: Array<{ type: string; text?: string }> };
    };
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
    broadcast(session, {
      type: "error",
      content: err.error?.message || "Unknown error",
    });
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
    })
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
        fs.readFileSync(path.join(SESSIONS_DIR, file), "utf-8")
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
