import React, { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Label } from "../ui/label";
import { AuthTerminal } from "../AuthTerminal";

interface AuthStatus {
  authenticated: boolean;
  terminalActive: boolean;
}

const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";
const WS_BASE = `${WS_PROTOCOL}//${window.location.host}`;
const API_BASE = "/api";

export function ClaudeAuthTab() {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [terminalUrl, setTerminalUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch auth status on mount
  useEffect(() => {
    fetchAuthStatus();
  }, []);

  const fetchAuthStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/status`);
      const data = await res.json();
      setAuthStatus(data);
    } catch (err) {
      console.error("Failed to fetch auth status:", err);
      setError("Failed to fetch authentication status");
    }
  };

  const startTerminal = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/auth/start`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setTerminalUrl(`${WS_BASE}/api/auth/terminal/ws`);
        await fetchAuthStatus();
      } else {
        setError(data.error || "Failed to start terminal");
      }
    } catch (err) {
      console.error("Failed to start auth terminal:", err);
      setError("Failed to start terminal");
    } finally {
      setLoading(false);
    }
  };

  const stopTerminal = async () => {
    try {
      await fetch(`${API_BASE}/auth/stop`, { method: "POST" });
      setTerminalUrl(null);
      await fetchAuthStatus();
    } catch (err) {
      console.error("Failed to stop auth terminal:", err);
    }
  };

  return (
    <div className="px-6 pb-6 overflow-y-auto h-full">
      {/* Auth Status */}
      <div className="py-4">
        <div className="flex items-center justify-between min-h-[60px] py-2">
          <Label className="text-sm text-neutral-900 dark:text-neutral-100 font-normal">
            Claude Authentication
          </Label>
          <div className="text-sm">
            {authStatus === null ? (
              <span className="text-neutral-500">Loading...</span>
            ) : authStatus.authenticated ? (
              <span className="text-green-600 dark:text-green-400 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                Authenticated
              </span>
            ) : (
              <span className="text-red-500 dark:text-red-400 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                Not Authenticated
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Terminal or Start Button */}
      {!terminalUrl ? (
        <div className="py-4">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
            {authStatus?.authenticated
              ? "Re-authenticate Claude CLI"
              : "Authenticate Claude CLI"}
          </h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
            Click below to open an interactive terminal. Run{" "}
            <code className="bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded text-xs font-mono">
              /login
            </code>{" "}
            to authenticate with your Anthropic account.
          </p>
          <Button
            onClick={startTerminal}
            disabled={loading}
            className="w-full bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900 hover:bg-neutral-800 dark:hover:bg-neutral-200"
          >
            {loading ? "Starting..." : "Open Authentication Terminal"}
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="text-sm text-neutral-500 dark:text-neutral-400">
            <p className="mb-2">
              Type{" "}
              <code className="bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded text-xs font-mono">
                /login
              </code>{" "}
              in the terminal below to authenticate.
            </p>
            <p>Follow the prompts. When done, click "Close Terminal" below.</p>
          </div>

          {/* Terminal */}
          <AuthTerminal wsUrl={terminalUrl} />

          <Button
            onClick={stopTerminal}
            variant="outline"
            className="w-full border-green-600 text-green-600 hover:bg-green-50 dark:border-green-400 dark:text-green-400 dark:hover:bg-green-900/20"
          >
            Done - Close Terminal
          </Button>
        </div>
      )}

      {/* Help text */}
      <div className="mt-6 text-xs text-neutral-400 dark:text-neutral-500">
        <p>
          Claude authentication is required to use the Claude Code CLI. Your
          credentials are stored locally on the server and are not shared with
          anyone.
        </p>
      </div>
    </div>
  );
}
