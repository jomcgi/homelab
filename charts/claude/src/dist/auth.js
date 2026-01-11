"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.ttydWss = void 0;
exports.handleTtydUpgrade = handleTtydUpgrade;
exports.setupAuthRoutes = setupAuthRoutes;
const ws_1 = require("ws");
const http_1 = require("http");
const http_proxy_middleware_1 = require("http-proxy-middleware");
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
const HOME = process.env.HOME || "/home/user";
const CLAUDE_BIN = path_1.default.join(HOME, ".npm-global", "bin", "claude");
const TTYD_PORT = 7681;
// Authentication state
let authTtydProcess = null;
// WebSocket server for ttyd terminal proxy
// Uses proper WebSocket-to-WebSocket proxying
// IMPORTANT: Must accept "tty" subprotocol or ttyd client will reject the connection
// IMPORTANT: Disable compression on server - browser may negotiate it but ttyd doesn't use it
exports.ttydWss = new ws_1.WebSocketServer({
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
exports.ttydWss.on("connection", (clientWs) => {
    console.log("Client WebSocket connected, connecting to ttyd...");
    // Connect to ttyd using WebSocket protocol with "tty" subprotocol
    // IMPORTANT: Disable perMessageDeflate to avoid compression mismatch with ttyd
    const ttydWs = new ws_1.WebSocket(`ws://localhost:${TTYD_PORT}/ws`, ["tty"], {
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
    ttydWs.on("message", (data, isBinary) => {
        // Forward ttyd messages to client, preserving binary/text type
        if (clientWs.readyState === ws_1.WebSocket.OPEN) {
            clientWs.send(data, { binary: isBinary });
        }
    });
    ttydWs.on("close", (code, reason) => {
        console.log(`ttyd WebSocket closed: ${code} ${reason}`);
        ttydConnected = false;
        if (clientWs.readyState === ws_1.WebSocket.OPEN) {
            clientWs.close(code, reason.toString());
        }
    });
    ttydWs.on("error", (err) => {
        console.error("ttyd WebSocket error:", err);
        ttydConnected = false;
        if (clientWs.readyState === ws_1.WebSocket.OPEN) {
            clientWs.close(1011, "ttyd connection error");
        }
    });
    clientWs.on("message", (data, isBinary) => {
        // Forward client messages to ttyd, preserving binary/text type
        if (ttydWs.readyState === ws_1.WebSocket.OPEN) {
            ttydWs.send(data, { binary: isBinary });
        }
    });
    clientWs.on("close", (code, reason) => {
        console.log(`Client WebSocket closed: ${code} ${reason}`);
        // Only close ttyd connection if it's open or connecting
        if (ttydConnected || ttydWs.readyState === ws_1.WebSocket.CONNECTING) {
            ttydWs.close();
        }
    });
    clientWs.on("error", (err) => {
        console.error("Client WebSocket error:", err);
        if (ttydConnected || ttydWs.readyState === ws_1.WebSocket.CONNECTING) {
            ttydWs.close();
        }
    });
});
// Handle WebSocket upgrade for ttyd
function handleTtydUpgrade(req, socket, head) {
    console.log(`WebSocket upgrade request for ttyd: ${req.url}`);
    exports.ttydWss.handleUpgrade(req, socket, head, (ws) => {
        exports.ttydWss.emit("connection", ws, req);
    });
}
// Setup auth routes on express app
function setupAuthRoutes(app) {
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
            // Spawn ttyd with claude
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
            error: (err, _req, res) => {
                console.error("Proxy error:", err);
                if (res instanceof http_1.ServerResponse) {
                    res.writeHead(502);
                    res.end("Terminal not available");
                }
            },
        },
    });
    app.use("/api/auth/terminal", ttydProxy);
}
