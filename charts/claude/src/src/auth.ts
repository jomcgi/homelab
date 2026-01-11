import { Express, Request, Response } from "express";
import { WebSocketServer, WebSocket } from "ws";
import { ServerResponse, IncomingMessage } from "http";
import { Socket } from "net";
import { createProxyMiddleware } from "http-proxy-middleware";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";

const HOME = process.env.HOME || "/home/user";
const CLAUDE_BIN = path.join(HOME, ".npm-global", "bin", "claude");
const TTYD_PORT = 7681;

// Authentication state
let authTtydProcess: ChildProcess | null = null;

// WebSocket server for ttyd terminal proxy
// Uses proper WebSocket-to-WebSocket proxying
// IMPORTANT: Must accept "tty" subprotocol or ttyd client will reject the connection
// IMPORTANT: Disable compression on server - browser may negotiate it but ttyd doesn't use it
export const ttydWss = new WebSocketServer({
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

// Handle WebSocket upgrade for ttyd
export function handleTtydUpgrade(
  req: IncomingMessage,
  socket: Socket,
  head: Buffer,
) {
  console.log(`WebSocket upgrade request for ttyd: ${req.url}`);
  ttydWss.handleUpgrade(req, socket, head, (ws) => {
    ttydWss.emit("connection", ws, req);
  });
}

// Setup auth routes on express app
export function setupAuthRoutes(app: Express) {
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
      // Spawn ttyd with claude
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
        _req: Request,
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
}
