/**
 * Ships Frontend Server
 *
 * Bun-based server that:
 * - Serves the built Vite app from /public
 * - Proxies /api/* requests to the marine-api
 * - Proxies /ws/* WebSocket connections to the marine-api
 */

const API_URL = process.env.API_URL || "http://marine-api:8000";
const PORT = parseInt(process.env.PORT || "3000", 10);
const PUBLIC_DIR = process.env.PUBLIC_DIR || "./public";

console.log(`Starting ships-frontend server...`);
console.log(`  API_URL: ${API_URL}`);
console.log(`  PORT: ${PORT}`);
console.log(`  PUBLIC_DIR: ${PUBLIC_DIR}`);

const server = Bun.serve({
  port: PORT,
  async fetch(req, server) {
    const url = new URL(req.url);
    const path = url.pathname;

    // WebSocket upgrade for /ws/*
    if (path.startsWith("/ws/")) {
      const apiWsUrl = API_URL.replace(/^http/, "ws") + path;

      if (server.upgrade(req, { data: { apiUrl: apiWsUrl } })) {
        return;
      }
      return new Response("WebSocket upgrade failed", { status: 500 });
    }

    // Proxy /api/* to marine-api
    if (path.startsWith("/api/")) {
      const apiUrl = API_URL + path + url.search;
      try {
        const resp = await fetch(apiUrl, {
          method: req.method,
          headers: req.headers,
          body: req.body,
        });
        return new Response(resp.body, {
          status: resp.status,
          headers: resp.headers,
        });
      } catch (e) {
        console.error(`Proxy error: ${e}`);
        return new Response(JSON.stringify({ error: "API unavailable" }), {
          status: 502,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    // Proxy /health and /ready to marine-api
    if (path === "/health" || path === "/ready") {
      const apiUrl = API_URL + path;
      try {
        const resp = await fetch(apiUrl);
        return new Response(resp.body, {
          status: resp.status,
          headers: resp.headers,
        });
      } catch (e) {
        return new Response(
          JSON.stringify({ status: "unhealthy", error: String(e) }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
    }

    // Serve static files
    let filePath = path === "/" ? "/index.html" : path;
    const file = Bun.file(PUBLIC_DIR + filePath);

    if (await file.exists()) {
      return new Response(file, {
        headers: {
          "Cache-Control": filePath.includes("/assets/")
            ? "public, max-age=31536000, immutable"
            : "no-cache",
        },
      });
    }

    // SPA fallback - serve index.html for client-side routing
    const indexFile = Bun.file(PUBLIC_DIR + "/index.html");
    if (await indexFile.exists()) {
      return new Response(indexFile, {
        headers: { "Cache-Control": "no-cache" },
      });
    }

    return new Response("Not Found", { status: 404 });
  },

  websocket: {
    async open(ws) {
      const { apiUrl } = ws.data as { apiUrl: string };
      console.log(`WebSocket connecting to ${apiUrl}`);

      // Connect to upstream API
      const apiWs = new WebSocket(apiUrl);

      apiWs.onmessage = (event) => {
        ws.send(event.data);
      };

      apiWs.onclose = () => {
        ws.close();
      };

      apiWs.onerror = (e) => {
        console.error(`Upstream WebSocket error: ${e}`);
        ws.close();
      };

      // Store reference for cleanup
      (ws.data as any).apiWs = apiWs;
    },

    message(ws, message) {
      const { apiWs } = ws.data as { apiWs?: WebSocket };
      if (apiWs && apiWs.readyState === WebSocket.OPEN) {
        apiWs.send(message);
      }
    },

    close(ws) {
      const { apiWs } = ws.data as { apiWs?: WebSocket };
      if (apiWs) {
        apiWs.close();
      }
    },
  },
});

console.log(`Server running on http://localhost:${server.port}`);
