"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const express_1 = __importDefault(require("express"));
const ws_1 = require("ws");
const http_1 = require("http");
const http_proxy_middleware_1 = require("http-proxy-middleware");
const uuid_1 = require("uuid");
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
const app = (0, express_1.default)();
app.use(express_1.default.json());
const PORT = parseInt(process.env.PORT || "3000", 10);
const HOME = process.env.HOME || "/home/user";
const WORKTREES_DIR = "/tmp/claude-worktrees";
const SESSIONS_DIR = path_1.default.join(HOME, ".claude-api", "sessions");
const STATIC_DIR = process.env.STATIC_DIR || "/app/public";
const CLAUDE_BIN = path_1.default.join(HOME, ".npm-global", "bin", "claude");
const TTYD_PORT = 7681;
// Ensure directories exist
fs_1.default.mkdirSync(SESSIONS_DIR, { recursive: true });
fs_1.default.mkdirSync(WORKTREES_DIR, { recursive: true });
// Authentication state
let authTtydProcess = null;
const sessions = new Map();
// Health check
app.get("/api/health", (_req, res) => {
    res.json({ status: "ok", sessions: sessions.size });
});
// Auth status - check if Claude is authenticated
app.get("/api/auth/status", (_req, res) => {
    const authFile = path_1.default.join(HOME, ".claude", "auth.json");
    const authenticated = fs_1.default.existsSync(authFile);
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
        const ttyd = (0, child_process_1.spawn)("ttyd", [
            "-p",
            TTYD_PORT.toString(),
            "-W", // Start immediately
            "-t",
            "titleFixed=Claude Authentication",
            CLAUDE_BIN,
        ], {
            cwd: HOME,
            env: { ...process.env, HOME },
            stdio: ["ignore", "pipe", "pipe"],
        });
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
    }
    catch (err) {
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
const ttydProxy = (0, http_proxy_middleware_1.createProxyMiddleware)({
    target: `http://localhost:${TTYD_PORT}`,
    changeOrigin: true,
    pathRewrite: {
        "^/api/auth/terminal": "", // Remove prefix
    },
    on: {
        error: (err, req, res) => {
            console.error("Proxy error:", err);
            if (res instanceof http_1.ServerResponse) {
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
    const id = (0, uuid_1.v4)();
    const sessionWorkdir = workdir || path_1.default.join(WORKTREES_DIR, id);
    // Create workdir if it doesn't exist
    if (!fs_1.default.existsSync(sessionWorkdir)) {
        fs_1.default.mkdirSync(sessionWorkdir, { recursive: true });
    }
    const session = {
        id,
        name: name || `Session ${id.slice(0, 8)}`,
        workdir: sessionWorkdir,
        createdAt: new Date(),
        wsClients: new Set(),
    };
    sessions.set(id, session);
    // Save session metadata
    const metaPath = path_1.default.join(SESSIONS_DIR, `${id}.json`);
    fs_1.default.writeFileSync(metaPath, JSON.stringify({
        id: session.id,
        name: session.name,
        workdir: session.workdir,
        createdAt: session.createdAt,
    }));
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
    const metaPath = path_1.default.join(SESSIONS_DIR, `${req.params.id}.json`);
    if (fs_1.default.existsSync(metaPath)) {
        fs_1.default.unlinkSync(metaPath);
    }
    res.status(204).send();
});
// Serve static frontend
app.use(express_1.default.static(STATIC_DIR));
// SPA fallback - serve index.html for all non-API routes
app.get("*", (req, res) => {
    if (!req.path.startsWith("/api/")) {
        res.sendFile(path_1.default.join(STATIC_DIR, "index.html"));
    }
    else {
        res.status(404).json({ error: "Not found" });
    }
});
// Create HTTP server
const server = (0, http_1.createServer)(app);
// WebSocket server for ttyd terminal proxy
// Uses proper WebSocket-to-WebSocket proxying (like ttyd-session-manager did with gorilla/websocket)
const ttydWss = new ws_1.WebSocketServer({ noServer: true });
ttydWss.on("connection", (clientWs) => {
    console.log("Client WebSocket connected, connecting to ttyd...");
    // Connect to ttyd using WebSocket protocol with "tty" subprotocol
    const ttydWs = new ws_1.WebSocket(`ws://localhost:${TTYD_PORT}/ws`, ["tty"]);
    // Set binary type to match ttyd expectations
    ttydWs.binaryType = "arraybuffer";
    ttydWs.on("open", () => {
        console.log("Connected to ttyd WebSocket");
    });
    ttydWs.on("message", (data, isBinary) => {
        // Forward ttyd messages to client, preserving binary/text type
        if (clientWs.readyState === ws_1.WebSocket.OPEN) {
            clientWs.send(data, { binary: isBinary });
        }
    });
    ttydWs.on("close", (code, reason) => {
        console.log(`ttyd WebSocket closed: ${code} ${reason}`);
        clientWs.close(code, reason.toString());
    });
    ttydWs.on("error", (err) => {
        console.error("ttyd WebSocket error:", err);
        clientWs.close(1011, "ttyd connection error");
    });
    clientWs.on("message", (data, isBinary) => {
        // Forward client messages to ttyd, preserving binary/text type
        if (ttydWs.readyState === ws_1.WebSocket.OPEN) {
            ttydWs.send(data, { binary: isBinary });
        }
    });
    clientWs.on("close", (code, reason) => {
        console.log(`Client WebSocket closed: ${code} ${reason}`);
        ttydWs.close();
    });
    clientWs.on("error", (err) => {
        console.error("Client WebSocket error:", err);
        ttydWs.close();
    });
});
// Handle WebSocket upgrades for ttyd proxy
server.on("upgrade", (req, socket, head) => {
    if (req.url?.startsWith("/api/auth/terminal/ws")) {
        console.log(`WebSocket upgrade request: ${req.url}`);
        ttydWss.handleUpgrade(req, socket, head, (ws) => {
            ttydWss.emit("connection", ws, req);
        });
    }
});
// WebSocket server for streaming
const wss = new ws_1.WebSocketServer({ server, path: "/ws" });
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
            }
            else {
                console.log(`Warning: session.process.stdin not available`);
            }
        }
    });
    ws.on("close", () => {
        session.wsClients.delete(ws);
    });
    // Send welcome message
    ws.send(JSON.stringify({
        type: "connected",
        sessionId: session.id,
        name: session.name,
        workdir: session.workdir,
    }));
});
function startClaudeProcess(session) {
    console.log(`Starting Claude process for session ${session.id} in ${session.workdir}`);
    console.log(`Using Claude binary: ${CLAUDE_BIN}`);
    // Spawn Claude Code in the session's workdir
    const claude = (0, child_process_1.spawn)(CLAUDE_BIN, ["--dangerously-skip-permissions"], {
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
            if (ws.readyState === ws_1.WebSocket.OPEN) {
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
            if (ws.readyState === ws_1.WebSocket.OPEN) {
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
            if (ws.readyState === ws_1.WebSocket.OPEN) {
                ws.send(message);
            }
        });
        session.process = undefined;
    });
}
// Load existing sessions on startup
function loadSessions() {
    if (!fs_1.default.existsSync(SESSIONS_DIR))
        return;
    const files = fs_1.default.readdirSync(SESSIONS_DIR);
    for (const file of files) {
        if (!file.endsWith(".json"))
            continue;
        try {
            const data = JSON.parse(fs_1.default.readFileSync(path_1.default.join(SESSIONS_DIR, file), "utf-8"));
            sessions.set(data.id, {
                id: data.id,
                name: data.name,
                workdir: data.workdir,
                createdAt: new Date(data.createdAt),
                wsClients: new Set(),
            });
        }
        catch (err) {
            console.error(`Failed to load session ${file}:`, err);
        }
    }
    console.log(`Loaded ${sessions.size} existing sessions`);
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
