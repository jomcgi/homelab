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
const CLAUDE_BIN = path.join(HOME, ".npm-global", "bin", "claude");

// Ensure directories exist
fs.mkdirSync(SESSIONS_DIR, { recursive: true });
fs.mkdirSync(WORKTREES_DIR, { recursive: true });

// Authentication state
let authProcess: ChildProcess | null = null;
let authUrl: string | null = null;
let authOutput: string = "";

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

// Auth status - check if Claude is authenticated
app.get("/api/auth/status", async (_req, res) => {
  try {
    // Try to run a simple command to check auth status
    const testProcess = spawn(CLAUDE_BIN, ["--help"], {
      env: { ...process.env, HOME },
      stdio: ["ignore", "pipe", "pipe"],
    });

    let output = "";
    let error = "";

    testProcess.stdout.on("data", (data) => {
      output += data.toString();
    });

    testProcess.stderr.on("data", (data) => {
      error += data.toString();
    });

    testProcess.on("close", (code) => {
      // If help runs successfully, CLI is installed
      // Check if auth file exists
      const authFile = path.join(HOME, ".claude", "auth.json");
      const authenticated = fs.existsSync(authFile);

      res.json({
        authenticated,
        cliInstalled: code === 0,
        authInProgress: authProcess !== null,
        authUrl: authUrl,
      });
    });
  } catch (err) {
    res.status(500).json({ error: "Failed to check auth status" });
  }
});

// Start auth flow
app.post("/api/auth/start", (req, res) => {
  // Clean up any existing auth process
  if (authProcess) {
    authProcess.kill();
    authProcess = null;
  }

  authUrl = null;
  authOutput = "";

  try {
    // Spawn claude /login
    const process = spawn(CLAUDE_BIN, ["/login"], {
      cwd: HOME,
      env: { ...process.env, HOME },
      stdio: ["pipe", "pipe", "pipe"],
    });

    authProcess = process;

    // Capture output to extract auth URL
    process.stdout.on("data", (data) => {
      const output = data.toString();
      authOutput += output;
      console.log(`Auth stdout: ${output}`);

      // Look for the auth URL pattern
      // Claude CLI typically outputs: "Please visit: https://..."
      const urlMatch = output.match(/https:\/\/[^\s]+/);
      if (urlMatch) {
        authUrl = urlMatch[0];
        console.log(`Found auth URL: ${authUrl}`);
      }
    });

    process.stderr.on("data", (data) => {
      const output = data.toString();
      authOutput += output;
      console.log(`Auth stderr: ${output}`);

      // Also check stderr for URL
      const urlMatch = output.match(/https:\/\/[^\s]+/);
      if (urlMatch) {
        authUrl = urlMatch[0];
        console.log(`Found auth URL in stderr: ${authUrl}`);
      }
    });

    process.on("close", (code) => {
      console.log(`Auth process exited with code ${code}`);
      authProcess = null;
    });

    process.on("error", (err) => {
      console.error(`Auth process error: ${err}`);
      authProcess = null;
    });

    // Give it a moment to output the URL
    setTimeout(() => {
      res.json({
        success: true,
        authUrl: authUrl,
        message: authUrl
          ? "Auth flow started. Please visit the URL to authorize."
          : "Auth flow started. Waiting for URL...",
      });
    }, 2000);
  } catch (err) {
    console.error("Failed to start auth:", err);
    res.status(500).json({ error: "Failed to start auth flow" });
  }
});

// Complete auth flow with code
app.post("/api/auth/complete", (req, res) => {
  const { code } = req.body;

  if (!authProcess) {
    return res.status(400).json({ error: "No auth process in progress" });
  }

  if (!code) {
    return res.status(400).json({ error: "Auth code is required" });
  }

  try {
    // Send the code to the waiting process
    authProcess.stdin?.write(code + "\n");

    // Wait a bit for the process to complete
    setTimeout(() => {
      // Check if auth file was created
      const authFile = path.join(HOME, ".claude", "auth.json");
      const success = fs.existsSync(authFile);

      if (success) {
        res.json({
          success: true,
          message: "Authentication successful!",
        });
      } else {
        res.json({
          success: false,
          message: "Authentication may have failed. Please check the code and try again.",
        });
      }

      // Clean up
      authProcess = null;
      authUrl = null;
      authOutput = "";
    }, 3000);
  } catch (err) {
    console.error("Failed to complete auth:", err);
    res.status(500).json({ error: "Failed to complete auth" });
  }
});

// Cancel auth flow
app.post("/api/auth/cancel", (_req, res) => {
  if (authProcess) {
    authProcess.kill();
    authProcess = null;
    authUrl = null;
    authOutput = "";
  }
  res.json({ success: true });
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
    console.log(`Received message for session ${session.id}: ${JSON.stringify(message).substring(0, 100)}`);

    if (message.type === "input") {
      // Start Claude Code process if not running
      if (!session.process) {
        console.log(`Starting new Claude process for session ${session.id}`);
        startClaudeProcess(session);
      }

      // Send input to Claude
      if (session.process?.stdin) {
        console.log(`Writing to Claude stdin: ${message.content}`);
        session.process.stdin.write(message.content + "\n");
      } else {
        console.log(`Warning: session.process.stdin not available`);
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
    }),
  );
});

function startClaudeProcess(session: Session) {
  console.log(`Starting Claude process for session ${session.id} in ${session.workdir}`);
  console.log(`Using Claude binary: ${CLAUDE_BIN}`);

  // Spawn Claude Code in the session's workdir
  const claude = spawn(CLAUDE_BIN, ["--dangerously-skip-permissions"], {
    cwd: session.workdir,
    env: {
      ...process.env,
      HOME,
    },
    stdio: ["pipe", "pipe", "pipe"],
  });

  session.process = claude;

  claude.on("spawn", () => {
    console.log(`Claude process spawned with PID ${claude.pid}`);
  });

  claude.on("error", (err) => {
    console.error(`Claude process error: ${err.message}`);
  });

  // Stream stdout to WebSocket clients
  claude.stdout.on("data", (data) => {
    console.log(`Claude stdout: ${data.toString().substring(0, 100)}...`);
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
    console.log(`Claude stderr: ${data.toString().substring(0, 100)}...`);
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
    console.log(`Claude process exited with code ${code}`);
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
        fs.readFileSync(path.join(SESSIONS_DIR, file), "utf-8"),
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
