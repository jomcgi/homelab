import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { WebglAddon } from "@xterm/addon-webgl";
import "@xterm/xterm/css/xterm.css";

interface AuthTerminalProps {
  wsUrl: string;
}

/**
 * AuthTerminal - xterm.js terminal component that implements the ttyd protocol
 *
 * ttyd protocol:
 * - On connect: Send JSON auth message with terminal dimensions
 * - Server messages: Prefixed with type ('0' = output, '1' = title)
 * - Client messages: Prefixed with type ('0' = input, '1' = resize)
 */
export function AuthTerminal({ wsUrl }: AuthTerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const webglAddonRef = useRef<WebglAddon | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Create terminal with performance optimizations
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: "#000000",
        foreground: "#ffffff",
        cursor: "#10b981",
        selection: "rgba(255, 255, 255, 0.3)",
      },
      scrollback: 10000,
    });

    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();

    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);
    term.open(containerRef.current);

    // Try WebGL renderer for better performance
    try {
      const webglAddon = new WebglAddon();
      webglAddon.onContextLoss(() => {
        try {
          webglAddon.dispose();
        } catch (err) {
          console.warn("Error disposing WebGL addon on context loss:", err);
        }
        webglAddonRef.current = null;
      });
      term.loadAddon(webglAddon);
      webglAddonRef.current = webglAddon;
    } catch (e) {
      console.warn("WebGL renderer not available, falling back to canvas:", e);
    }

    fitAddon.fit();
    terminalRef.current = term;
    fitAddonRef.current = fitAddon;

    term.write("\x1b[33mConnecting to terminal...\x1b[0m\r\n");

    // Connect to WebSocket with ttyd protocol
    const ws = new WebSocket(wsUrl, ["tty"]);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      term.write("\x1b[32mConnected!\x1b[0m\r\n");

      // ttyd protocol: First message is JSON auth with terminal dimensions
      const authMessage = JSON.stringify({
        AuthToken: "",
        columns: term.cols,
        rows: term.rows,
      });
      ws.send(authMessage);
    };

    ws.onmessage = (event) => {
      // Handle both ArrayBuffer and string data
      let data = event.data;
      if (data instanceof ArrayBuffer) {
        const decoder = new TextDecoder();
        data = decoder.decode(data);
      }

      if (typeof data === "string" && data.length > 0) {
        const messageType = data[0];
        const payload = data.substring(1);

        if (messageType === "0") {
          // OUTPUT: write terminal data
          term.write(payload);
        } else if (messageType === "1") {
          // SET_WINDOW_TITLE: ignore for auth terminal
        }
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      term.write("\r\n\x1b[31mConnection error\x1b[0m\r\n");
    };

    ws.onclose = () => {
      term.write("\r\n\x1b[33mConnection closed\x1b[0m\r\n");
    };

    wsRef.current = ws;

    // Send terminal input to WebSocket
    // ttyd protocol: prefix input with '0' (INPUT message type)
    const encoder = new TextEncoder();
    const dataHandler = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        const encoded = encoder.encode(data);
        const message = new Uint8Array(encoded.length + 1);
        message[0] = 48; // ASCII '0' for ttyd INPUT message type
        message.set(encoded, 1);
        ws.send(message.buffer);
      }
    });

    // Handle window resize
    const resizeHandler = () => {
      fitAddon.fit();

      // Notify ttyd of terminal size change with RESIZE message (type '1')
      if (ws.readyState === WebSocket.OPEN) {
        const resizeJson = JSON.stringify({
          columns: term.cols,
          rows: term.rows,
        });
        const encoded = encoder.encode(resizeJson);
        const resizeMessage = new Uint8Array(encoded.length + 1);
        resizeMessage[0] = 49; // ASCII '1' for ttyd RESIZE message type
        resizeMessage.set(encoded, 1);
        ws.send(resizeMessage.buffer);
      }
    };
    window.addEventListener("resize", resizeHandler);

    // Focus terminal
    term.focus();

    // Cleanup
    return () => {
      window.removeEventListener("resize", resizeHandler);
      dataHandler.dispose();

      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      if (webglAddonRef.current) {
        try {
          webglAddonRef.current.dispose();
        } catch (err) {
          console.warn("Error disposing WebGL addon:", err);
        }
        webglAddonRef.current = null;
      }

      if (terminalRef.current) {
        try {
          terminalRef.current.dispose();
        } catch (err) {
          console.warn("Error disposing terminal:", err);
        }
        terminalRef.current = null;
      }

      fitAddonRef.current = null;
    };
  }, [wsUrl]);

  return (
    <div
      ref={containerRef}
      className="w-full h-[500px] bg-black rounded overflow-hidden"
    />
  );
}
