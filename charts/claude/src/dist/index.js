"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const express_1 = __importDefault(require("express"));
const ws_1 = require("ws");
const http_1 = require("http");
const uuid_1 = require("uuid");
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
const auth_1 = require("./auth");
const app = (0, express_1.default)();
app.use(express_1.default.json());
const PORT = parseInt(process.env.PORT || "3000", 10);
const HOME = process.env.HOME || "/home/user";
const WORKTREES_DIR = path_1.default.join(HOME, ".claude-api", "worktrees"); // Persistent on PVC
const SESSIONS_DIR = path_1.default.join(HOME, ".claude-api", "sessions");
const STATIC_DIR = process.env.STATIC_DIR || "/app/public";
const CLAUDE_BIN = path_1.default.join(HOME, ".npm-global", "bin", "claude");
// Ensure directories exist
fs_1.default.mkdirSync(SESSIONS_DIR, { recursive: true });
fs_1.default.mkdirSync(WORKTREES_DIR, { recursive: true });
const sessions = new Map();
// Health check
app.get("/api/health", (_req, res) => {
    res.json({ status: "ok", sessions: sessions.size });
});
// Setup auth routes (ttyd terminal for /login)
(0, auth_1.setupAuthRoutes)(app);
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
        isProcessing: false,
        wsClients: new Set(),
    };
    sessions.set(id, session);
    console.log(`Session created: ${id}, Total sessions in memory: ${sessions.size}`);
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
// WebSocket server for session streaming
const wss = new ws_1.WebSocketServer({ noServer: true });
// Handle ALL WebSocket upgrades in one place to avoid conflicts
server.on("upgrade", (req, socket, head) => {
    const url = req.url || "";
    console.log(`[UPGRADE] Request received: ${url}`);
    if (url.startsWith("/api/auth/terminal/ws")) {
        (0, auth_1.handleTtydUpgrade)(req, socket, head);
    }
    else if (url.startsWith("/ws")) {
        console.log(`WebSocket upgrade request for session: ${url}`);
        wss.handleUpgrade(req, socket, head, (ws) => {
            wss.emit("connection", ws, req);
        });
    }
    else {
        console.log(`Unknown WebSocket upgrade request: ${url}`);
        socket.destroy();
    }
});
wss.on("connection", (ws, req) => {
    console.log(`Session WebSocket connection received, URL: ${req.url}`);
    let url;
    try {
        url = new URL(req.url || "", `http://localhost:${PORT}`);
    }
    catch (err) {
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
        console.log(`Session ${sessionId} not found. Available sessions: ${Array.from(sessions.keys()).join(", ")}`);
        ws.close(4004, "Session not found");
        return;
    }
    console.log(`Session ${sessionId} found, adding client`);
    // Add client to session
    session.wsClients.add(ws);
    ws.on("message", (data) => {
        const message = JSON.parse(data.toString());
        console.log(`Received message for session ${session.id}: ${JSON.stringify(message).substring(0, 100)}`);
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
        console.log(`Session ${session.id} WebSocket closed: ${code} ${reason.toString()}`);
        session.wsClients.delete(ws);
    });
    ws.on("error", (err) => {
        console.error(`Session ${session.id} WebSocket error:`, err);
    });
    // Send welcome message
    console.log(`Sending welcome message to session ${session.id}`);
    try {
        ws.send(JSON.stringify({
            type: "connected",
            sessionId: session.id,
            name: session.name,
            workdir: session.workdir,
        }));
        console.log(`Welcome message sent successfully to session ${session.id}`);
    }
    catch (err) {
        console.error(`Failed to send welcome message to session ${session.id}:`, err);
    }
});
// Run Claude in print mode with a single message (like cui does)
function runClaudeMessage(session, userMessage) {
    console.log(`Running Claude for session ${session.id} in ${session.workdir}`);
    console.log(`Using Claude binary: ${CLAUDE_BIN}`);
    // Ensure workdir exists (may have been cleared if in /tmp after pod restart)
    if (!fs_1.default.existsSync(session.workdir)) {
        console.log(`Creating workdir: ${session.workdir}`);
        fs_1.default.mkdirSync(session.workdir, { recursive: true });
    }
    session.isProcessing = true;
    // Build args based on whether this is a new conversation or resume
    // cui pattern:
    //   new: -p <message> --output-format stream-json --verbose
    //   resume: --resume <sessionId> <message> --output-format stream-json --verbose
    const args = [];
    if (session.claudeSessionId) {
        // Resume existing conversation (no -p flag)
        args.push("--resume", session.claudeSessionId);
        args.push(userMessage);
    }
    else {
        // New conversation with print mode
        args.push("-p");
        args.push(userMessage);
    }
    // Common flags
    args.push("--output-format", "stream-json");
    args.push("--verbose");
    args.push("--dangerously-skip-permissions");
    console.log(`Claude args: ${args.join(" ")}`);
    const claude = (0, child_process_1.spawn)(CLAUDE_BIN, args, {
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
    claude.stdout.on("data", (data) => {
        buffer += data.toString();
        const lines = buffer.split("\n");
        // Keep the last incomplete line in the buffer
        buffer = lines.pop() || "";
        for (const line of lines) {
            if (!line.trim())
                continue;
            try {
                const event = JSON.parse(line);
                handleClaudeEvent(session, event);
            }
            catch {
                // Not valid JSON, might be regular output
                console.log(`Claude non-JSON output: ${line.substring(0, 100)}`);
            }
        }
    });
    // Stream stderr to WebSocket clients
    claude.stderr.on("data", (data) => {
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
            }
            catch {
                // Ignore
            }
        }
        broadcast(session, { type: "done", code });
    });
}
// Handle Claude stream-json events
function handleClaudeEvent(session, event) {
    console.log(`Claude event: ${event.type || "unknown"}`);
    // Extract the Claude session ID for future --resume calls
    if (event.type === "system" && event.subtype === "init") {
        const init = event;
        if (init.session_id) {
            session.claudeSessionId = init.session_id;
            console.log(`Captured Claude session ID: ${session.claudeSessionId}`);
            saveSession(session);
        }
    }
    // Forward assistant messages to clients
    if (event.type === "assistant") {
        const msg = event;
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
        const delta = event;
        if (delta.delta?.type === "text_delta" && delta.delta.text) {
            broadcast(session, { type: "output", content: delta.delta.text });
        }
    }
    // Handle errors
    if (event.type === "error") {
        const err = event;
        broadcast(session, {
            type: "error",
            content: err.error?.message || "Unknown error",
        });
    }
}
// Broadcast message to all session clients
function broadcast(session, message) {
    const data = JSON.stringify(message);
    session.wsClients.forEach((ws) => {
        if (ws.readyState === ws_1.WebSocket.OPEN) {
            ws.send(data);
        }
    });
}
// Save session metadata to disk
function saveSession(session) {
    const metaPath = path_1.default.join(SESSIONS_DIR, `${session.id}.json`);
    fs_1.default.writeFileSync(metaPath, JSON.stringify({
        id: session.id,
        name: session.name,
        workdir: session.workdir,
        createdAt: session.createdAt,
        claudeSessionId: session.claudeSessionId,
    }));
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
                claudeSessionId: data.claudeSessionId,
                isProcessing: false,
                wsClients: new Set(),
            });
        }
        catch (err) {
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
