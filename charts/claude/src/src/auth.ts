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
const TTYD_AUTH_PORT = 7681;
const TTYD_SHELL_PORT = 7682;

// Terminal state
let authTtydProcess: ChildProcess | null = null;
let shellTtydProcess: ChildProcess | null = null;

// WebSocket server for ttyd terminal proxy (auth terminal)
// Uses proper WebSocket-to-WebSocket proxying
// IMPORTANT: Must accept "tty" subprotocol or ttyd client will reject the connection
// IMPORTANT: Disable compression on server - browser may negotiate it but ttyd doesn't use it
export const ttydAuthWss = new WebSocketServer({
  noServer: true,
  perMessageDeflate: false,
  handleProtocols: (protocols) => {
    if (protocols.has("tty")) {
      return "tty";
    }
    return false;
  },
});

// WebSocket server for shell terminal
export const ttydShellWss = new WebSocketServer({
  noServer: true,
  perMessageDeflate: false,
  handleProtocols: (protocols) => {
    if (protocols.has("tty")) {
      return "tty";
    }
    return false;
  },
});

// Helper function to create ttyd WebSocket proxy connection
function createTtydProxyConnection(
  clientWs: WebSocket,
  port: number,
  name: string,
) {
  console.log(
    `${name}: Client connected, connecting to ttyd on port ${port}...`,
  );

  const ttydWs = new WebSocket(`ws://localhost:${port}/ws`, ["tty"], {
    perMessageDeflate: false,
  });

  ttydWs.binaryType = "arraybuffer";
  let ttydConnected = false;

  ttydWs.on("open", () => {
    console.log(`${name}: Connected to ttyd WebSocket`);
    ttydConnected = true;
  });

  ttydWs.on("message", (data: Buffer, isBinary: boolean) => {
    if (clientWs.readyState === WebSocket.OPEN) {
      clientWs.send(data, { binary: isBinary });
    }
  });

  ttydWs.on("close", (code, reason) => {
    console.log(`${name}: ttyd WebSocket closed: ${code} ${reason}`);
    ttydConnected = false;
    if (clientWs.readyState === WebSocket.OPEN) {
      clientWs.close(code, reason.toString());
    }
  });

  ttydWs.on("error", (err) => {
    console.error(`${name}: ttyd WebSocket error:`, err);
    ttydConnected = false;
    if (clientWs.readyState === WebSocket.OPEN) {
      clientWs.close(1011, "ttyd connection error");
    }
  });

  clientWs.on("message", (data: Buffer, isBinary: boolean) => {
    if (ttydWs.readyState === WebSocket.OPEN) {
      ttydWs.send(data, { binary: isBinary });
    }
  });

  clientWs.on("close", (code, reason) => {
    console.log(`${name}: Client WebSocket closed: ${code} ${reason}`);
    if (ttydConnected || ttydWs.readyState === WebSocket.CONNECTING) {
      ttydWs.close();
    }
  });

  clientWs.on("error", (err) => {
    console.error(`${name}: Client WebSocket error:`, err);
    if (ttydConnected || ttydWs.readyState === WebSocket.CONNECTING) {
      ttydWs.close();
    }
  });
}

ttydAuthWss.on("connection", (clientWs: WebSocket) => {
  createTtydProxyConnection(clientWs, TTYD_AUTH_PORT, "Auth Terminal");
});

ttydShellWss.on("connection", (clientWs: WebSocket) => {
  createTtydProxyConnection(clientWs, TTYD_SHELL_PORT, "Shell Terminal");
});

// Handle WebSocket upgrade for auth terminal
export function handleAuthTtydUpgrade(
  req: IncomingMessage,
  socket: Socket,
  head: Buffer,
) {
  console.log(`WebSocket upgrade request for auth ttyd: ${req.url}`);
  ttydAuthWss.handleUpgrade(req, socket, head, (ws) => {
    ttydAuthWss.emit("connection", ws, req);
  });
}

// Handle WebSocket upgrade for shell terminal
export function handleShellTtydUpgrade(
  req: IncomingMessage,
  socket: Socket,
  head: Buffer,
) {
  console.log(`WebSocket upgrade request for shell ttyd: ${req.url}`);
  ttydShellWss.handleUpgrade(req, socket, head, (ws) => {
    ttydShellWss.emit("connection", ws, req);
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

  // Start auth terminal (spawn ttyd with claude)
  app.post("/api/auth/start", (_req, res) => {
    if (authTtydProcess) {
      console.log("Killing existing auth ttyd process...");
      authTtydProcess.kill();
      authTtydProcess = null;
    }

    try {
      console.log(`Starting auth ttyd on port ${TTYD_AUTH_PORT}...`);

      const ttyd = spawn(
        "ttyd",
        [
          "-p",
          TTYD_AUTH_PORT.toString(),
          "-W",
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
        console.log(`[auth-ttyd stdout] ${data.toString().trim()}`);
      });

      ttyd.stderr.on("data", (data) => {
        console.log(`[auth-ttyd stderr] ${data.toString().trim()}`);
      });

      ttyd.on("close", (code) => {
        console.log(`Auth ttyd process exited with code ${code}`);
        authTtydProcess = null;
      });

      ttyd.on("error", (err) => {
        console.error(`Auth ttyd process error: ${err}`);
        authTtydProcess = null;
      });

      setTimeout(() => {
        res.json({
          success: true,
          message: "Terminal started. Connect to /api/auth/terminal",
          terminalUrl: "/api/auth/terminal",
        });
      }, 500);
    } catch (err) {
      console.error("Failed to start auth ttyd:", err);
      res.status(500).json({ error: "Failed to start terminal" });
    }
  });

  // Stop auth terminal
  app.post("/api/auth/stop", (_req, res) => {
    if (authTtydProcess) {
      console.log("Stopping auth ttyd process...");
      authTtydProcess.kill();
      authTtydProcess = null;
    }
    res.json({ success: true });
  });

  // Proxy to auth ttyd terminal (HTTP only - WebSocket handled separately)
  const authTtydProxy = createProxyMiddleware({
    target: `http://localhost:${TTYD_AUTH_PORT}`,
    changeOrigin: true,
    pathRewrite: {
      "^/api/auth/terminal": "",
    },
    on: {
      error: (
        err: Error,
        _req: Request,
        res: Response | ServerResponse | Socket,
      ) => {
        console.error("Auth proxy error:", err);
        if (res instanceof ServerResponse) {
          res.writeHead(502);
          res.end("Terminal not available");
        }
      },
    },
  });
  app.use("/api/auth/terminal", authTtydProxy);

  // ========== Shell Terminal Routes ==========

  // Shell status
  app.get("/api/shell/status", (_req, res) => {
    res.json({
      active: shellTtydProcess !== null,
    });
  });

  // Start shell terminal (spawn ttyd with bash)
  app.post("/api/shell/start", (_req, res) => {
    if (shellTtydProcess) {
      console.log("Killing existing shell ttyd process...");
      shellTtydProcess.kill();
      shellTtydProcess = null;
    }

    try {
      console.log(`Starting shell ttyd on port ${TTYD_SHELL_PORT}...`);

      const ttyd = spawn(
        "ttyd",
        [
          "-p",
          TTYD_SHELL_PORT.toString(),
          "-W",
          "-t",
          "titleFixed=Shell Terminal",
          "/bin/bash",
        ],
        {
          cwd: HOME,
          env: { ...process.env, HOME },
          stdio: ["ignore", "pipe", "pipe"],
        },
      );

      shellTtydProcess = ttyd;

      ttyd.stdout.on("data", (data) => {
        console.log(`[shell-ttyd stdout] ${data.toString().trim()}`);
      });

      ttyd.stderr.on("data", (data) => {
        console.log(`[shell-ttyd stderr] ${data.toString().trim()}`);
      });

      ttyd.on("close", (code) => {
        console.log(`Shell ttyd process exited with code ${code}`);
        shellTtydProcess = null;
      });

      ttyd.on("error", (err) => {
        console.error(`Shell ttyd process error: ${err}`);
        shellTtydProcess = null;
      });

      setTimeout(() => {
        res.json({
          success: true,
          message: "Shell terminal started. Connect to /api/shell/terminal",
          terminalUrl: "/api/shell/terminal",
        });
      }, 500);
    } catch (err) {
      console.error("Failed to start shell ttyd:", err);
      res.status(500).json({ error: "Failed to start terminal" });
    }
  });

  // Stop shell terminal
  app.post("/api/shell/stop", (_req, res) => {
    if (shellTtydProcess) {
      console.log("Stopping shell ttyd process...");
      shellTtydProcess.kill();
      shellTtydProcess = null;
    }
    res.json({ success: true });
  });

  // Proxy to shell ttyd terminal (HTTP only - WebSocket handled separately)
  const shellTtydProxy = createProxyMiddleware({
    target: `http://localhost:${TTYD_SHELL_PORT}`,
    changeOrigin: true,
    pathRewrite: {
      "^/api/shell/terminal": "",
    },
    on: {
      error: (
        err: Error,
        _req: Request,
        res: Response | ServerResponse | Socket,
      ) => {
        console.error("Shell proxy error:", err);
        if (res instanceof ServerResponse) {
          res.writeHead(502);
          res.end("Terminal not available");
        }
      },
    },
  });
  app.use("/api/shell/terminal", shellTtydProxy);
}
