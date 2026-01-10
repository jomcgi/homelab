import express from "express";
import { WebSocketServer, WebSocket } from "ws";
import { createServer } from "http";
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

// Ensure directories exist
fs.mkdirSync(SESSIONS_DIR, { recursive: true });
fs.mkdirSync(WORKTREES_DIR, { recursive: true });

interface Session {
  id: string;
  name: string;
  workdir: string;
  createdAt: Date;
  process?: ChildProcess;
  wsClients: Set<WebSocket>;
}

const sessions = new Map<string, Session>();

// Health check
app.get("/api/health", (_req, res) => {
  res.json({ status: "ok", sessions: sessions.size });
});

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
    wsClients: new Set(),
  };

  sessions.set(id, session);

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

// WebSocket server for streaming
const wss = new WebSocketServer({ server, path: "/ws" });

wss.on("connection", (ws, req) => {
  const url = new URL(req.url || "", `http://localhost:${PORT}`);
  const sessionId = url.searchParams.get("session");

  if (!sessionId) {
    ws.close(4000, "Missing session parameter");
    return;
  }

  const session = sessions.get(sessionId);
  if (!session) {
    ws.close(4004, "Session not found");
    return;
  }

  // Add client to session
  session.wsClients.add(ws);

  ws.on("message", (data) => {
    const message = JSON.parse(data.toString());

    if (message.type === "input") {
      // Start Claude Code process if not running
      if (!session.process) {
        startClaudeProcess(session);
      }

      // Send input to Claude
      if (session.process?.stdin) {
        session.process.stdin.write(message.content + "\n");
      }
    }
  });

  ws.on("close", () => {
    session.wsClients.delete(ws);
  });

  // Send welcome message
  ws.send(
    JSON.stringify({
      type: "connected",
      sessionId: session.id,
      name: session.name,
      workdir: session.workdir,
    })
  );
});

function startClaudeProcess(session: Session) {
  // Spawn Claude Code in the session's workdir
  const claude = spawn("claude", ["--dangerously-skip-permissions"], {
    cwd: session.workdir,
    env: {
      ...process.env,
      HOME,
    },
    stdio: ["pipe", "pipe", "pipe"],
  });

  session.process = claude;

  // Stream stdout to WebSocket clients
  claude.stdout.on("data", (data) => {
    const message = JSON.stringify({
      type: "output",
      content: data.toString(),
    });
    session.wsClients.forEach((ws) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(message);
      }
    });
  });

  // Stream stderr to WebSocket clients
  claude.stderr.on("data", (data) => {
    const message = JSON.stringify({
      type: "error",
      content: data.toString(),
    });
    session.wsClients.forEach((ws) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(message);
      }
    });
  });

  // Handle process exit
  claude.on("close", (code) => {
    const message = JSON.stringify({
      type: "exit",
      code,
    });
    session.wsClients.forEach((ws) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(message);
      }
    });
    session.process = undefined;
  });
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
        wsClients: new Set(),
      });
    } catch (err) {
      console.error(`Failed to load session ${file}:`, err);
    }
  }
  console.log(`Loaded ${sessions.size} existing sessions`);
}

loadSessions();

server.listen(PORT, () => {
  console.log(`Claude API server listening on port ${PORT}`);
  console.log(`Serving static files from ${STATIC_DIR}`);
});
