import { useState, useEffect, useRef, useCallback } from "react";

interface Message {
  id: string;
  type: "user" | "assistant" | "error" | "system";
  content: string;
  timestamp: Date;
}

interface Session {
  id: string;
  name: string;
  workdir: string;
  createdAt: string;
  active: boolean;
}

interface AuthStatus {
  authenticated: boolean;
  cliInstalled: boolean;
  authInProgress: boolean;
  authUrl?: string;
}

// Same-origin API - no CORS needed
const API_BASE = "/api";
const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";
const WS_BASE = `${WS_PROTOCOL}//${window.location.host}`;

function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);

  // Auth state
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authCode, setAuthCode] = useState("");
  const [authMessage, setAuthMessage] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Fetch sessions on mount
  useEffect(() => {
    fetchSessions();
    fetchAuthStatus();
  }, []);

  const fetchSessions = async () => {
    try {
      const res = await fetch(`${API_BASE}/sessions`);
      const data = await res.json();
      setSessions(data);
    } catch (err) {
      console.error("Failed to fetch sessions:", err);
    }
  };

  const fetchAuthStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/status`);
      const data = await res.json();
      setAuthStatus(data);
    } catch (err) {
      console.error("Failed to fetch auth status:", err);
    }
  };

  const startAuth = async () => {
    try {
      setAuthMessage("Starting authentication flow...");
      const res = await fetch(`${API_BASE}/auth/start`, { method: "POST" });
      const data = await res.json();
      setAuthMessage(data.message);

      // Poll for auth URL if not immediately available
      if (!data.authUrl) {
        const pollInterval = setInterval(async () => {
          const statusRes = await fetch(`${API_BASE}/auth/status`);
          const status = await statusRes.json();
          setAuthStatus(status);
          if (status.authUrl) {
            clearInterval(pollInterval);
          }
        }, 1000);

        // Stop polling after 10 seconds
        setTimeout(() => clearInterval(pollInterval), 10000);
      } else {
        await fetchAuthStatus();
      }
    } catch (err) {
      console.error("Failed to start auth:", err);
      setAuthMessage("Failed to start authentication flow");
    }
  };

  const completeAuth = async () => {
    if (!authCode.trim()) {
      setAuthMessage("Please enter the authorization code");
      return;
    }

    try {
      setAuthMessage("Completing authentication...");
      const res = await fetch(`${API_BASE}/auth/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: authCode }),
      });
      const data = await res.json();
      setAuthMessage(data.message);

      if (data.success) {
        setAuthCode("");
        setTimeout(() => {
          fetchAuthStatus();
          setShowAuthModal(false);
        }, 2000);
      }
    } catch (err) {
      console.error("Failed to complete auth:", err);
      setAuthMessage("Failed to complete authentication");
    }
  };

  const cancelAuth = async () => {
    try {
      await fetch(`${API_BASE}/auth/cancel`, { method: "POST" });
      await fetchAuthStatus();
      setAuthCode("");
      setAuthMessage("");
    } catch (err) {
      console.error("Failed to cancel auth:", err);
    }
  };

  const createSession = async () => {
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: `Session ${sessions.length + 1}` }),
      });
      const session = await res.json();
      setSessions((prev) => [...prev, session]);
      selectSession(session);
    } catch (err) {
      console.error("Failed to create session:", err);
    }
  };

  const selectSession = useCallback((session: Session) => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    setCurrentSession(session);
    setMessages([]);
    setConnected(false);

    // Connect WebSocket
    const ws = new WebSocket(`${WS_BASE}/ws?session=${session.id}`);

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "connected") {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "system",
            content: `Connected to session: ${data.name}\nWorking directory: ${data.workdir}`,
            timestamp: new Date(),
          },
        ]);
      } else if (data.type === "output") {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "assistant",
            content: data.content,
            timestamp: new Date(),
          },
        ]);
      } else if (data.type === "error") {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "error",
            content: data.content,
            timestamp: new Date(),
          },
        ]);
      }
    };

    ws.onclose = () => {
      setConnected(false);
    };

    ws.onerror = () => {
      setConnected(false);
    };

    wsRef.current = ws;
  }, []);

  const sendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !wsRef.current || !connected) return;

    // Add user message
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        type: "user",
        content: input,
        timestamp: new Date(),
      },
    ]);

    // Send to server
    wsRef.current.send(JSON.stringify({ type: "input", content: input }));
    setInput("");
  };

  const toggleRecording = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        const mediaRecorder = new MediaRecorder(stream);
        const chunks: Blob[] = [];

        mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
        mediaRecorder.onstop = async () => {
          const blob = new Blob(chunks, { type: "audio/webm" });
          // TODO: Send to Gemini for transcription
          console.log("Audio recorded:", blob.size, "bytes");
          stream.getTracks().forEach((track) => track.stop());
        };

        mediaRecorder.start();
        mediaRecorderRef.current = mediaRecorder;
        setIsRecording(true);
      } catch (err) {
        console.error("Failed to start recording:", err);
      }
    }
  };

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <div className="w-64 bg-[#16213e] flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-xl font-bold">Claude Code</h1>
        </div>

        <div className="p-4 space-y-2">
          <button
            onClick={createSession}
            className="w-full py-2 px-4 bg-[#e94560] text-white rounded hover:bg-[#d63d56] transition"
          >
            New Session
          </button>

          <button
            onClick={() => setShowAuthModal(true)}
            className="w-full py-2 px-4 bg-gray-700 text-white rounded hover:bg-gray-600 transition flex items-center justify-center gap-2"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-4 h-4"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z"
              />
            </svg>
            Auth
            {authStatus?.authenticated && (
              <span className="w-2 h-2 rounded-full bg-green-500" />
            )}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => selectSession(session)}
              className={`w-full p-3 text-left hover:bg-[#1a1a2e] transition ${
                currentSession?.id === session.id ? "bg-[#1a1a2e]" : ""
              }`}
            >
              <div className="font-medium truncate">{session.name}</div>
              <div className="text-xs text-gray-400 truncate">
                {session.workdir}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="h-14 bg-[#16213e] flex items-center justify-between px-4 border-b border-gray-700">
          <div>
            {currentSession ? (
              <span>{currentSession.name}</span>
            ) : (
              <span className="text-gray-400">Select or create a session</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                connected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span className="text-sm text-gray-400">
              {connected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`${
                msg.type === "user"
                  ? "ml-auto bg-[#e94560] max-w-[80%]"
                  : msg.type === "error"
                    ? "bg-red-900/50 max-w-[80%]"
                    : msg.type === "system"
                      ? "bg-gray-700/50 text-sm text-gray-300 max-w-full"
                      : "bg-[#16213e] max-w-[80%]"
              } rounded-lg p-3`}
            >
              <pre className="whitespace-pre-wrap font-mono text-sm break-words">
                {msg.content}
              </pre>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <form onSubmit={sendMessage} className="p-4 bg-[#16213e]">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={toggleRecording}
              className={`p-3 rounded-lg ${
                isRecording
                  ? "bg-red-500 animate-pulse"
                  : "bg-gray-700 hover:bg-gray-600"
              } transition`}
              title={isRecording ? "Stop recording" : "Start voice input"}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-5 h-5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
                />
              </svg>
            </button>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                connected ? "Type a message..." : "Connect to a session first"
              }
              disabled={!connected}
              className="flex-1 bg-[#1a1a2e] rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-[#e94560] disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!connected || !input.trim()}
              className="px-6 py-2 bg-[#e94560] rounded-lg hover:bg-[#d63d56] transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </form>
      </div>

      {/* Auth Modal */}
      {showAuthModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#16213e] rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-2xl font-bold">Authentication</h2>
                <button
                  onClick={() => {
                    setShowAuthModal(false);
                    cancelAuth();
                  }}
                  className="text-gray-400 hover:text-white"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                    className="w-6 h-6"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              {/* Auth Status */}
              <div className="mb-6 p-4 bg-[#1a1a2e] rounded">
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-semibold">Status:</span>
                  {authStatus?.authenticated ? (
                    <span className="text-green-400 flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-green-400" />
                      Authenticated
                    </span>
                  ) : (
                    <span className="text-red-400 flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-red-400" />
                      Not Authenticated
                    </span>
                  )}
                </div>
                {authStatus?.cliInstalled && (
                  <div className="text-sm text-gray-400">
                    Claude CLI is installed
                  </div>
                )}
              </div>

              {/* Instructions */}
              {!authStatus?.authInProgress && (
                <div className="mb-6">
                  <h3 className="font-semibold mb-2">
                    {authStatus?.authenticated
                      ? "Re-authenticate Claude CLI"
                      : "Authenticate Claude CLI"}
                  </h3>
                  <p className="text-sm text-gray-400 mb-4">
                    Click the button below to start the authentication flow.
                    You'll be able to scan a QR code or click a link to
                    authorize on any device.
                  </p>
                  <button
                    onClick={startAuth}
                    className="w-full py-3 px-4 bg-[#e94560] text-white rounded hover:bg-[#d63d56] transition"
                  >
                    Start Authentication
                  </button>
                </div>
              )}

              {/* Auth Flow */}
              {authStatus?.authInProgress && (
                <div className="space-y-4">
                  <div>
                    <h3 className="font-semibold mb-2">Step 1: Authorize</h3>
                    {authStatus.authUrl ? (
                      <div className="space-y-4">
                        {/* QR Code */}
                        <div className="bg-white p-4 rounded flex justify-center">
                          <img
                            src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(authStatus.authUrl)}`}
                            alt="Auth QR Code"
                            className="w-48 h-48"
                          />
                        </div>

                        {/* URL Link */}
                        <div className="p-3 bg-[#1a1a2e] rounded">
                          <div className="text-sm text-gray-400 mb-1">
                            Or click the link:
                          </div>
                          <a
                            href={authStatus.authUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[#e94560] hover:underline break-all text-sm"
                          >
                            {authStatus.authUrl}
                          </a>
                        </div>
                      </div>
                    ) : (
                      <div className="text-gray-400">
                        Waiting for authentication URL...
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="font-semibold mb-2">
                      Step 2: Enter Authorization Code
                    </h3>
                    <p className="text-sm text-gray-400 mb-3">
                      After authorizing, paste the code here:
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={authCode}
                        onChange={(e) => setAuthCode(e.target.value)}
                        placeholder="Paste authorization code"
                        className="flex-1 bg-[#1a1a2e] rounded px-4 py-2 focus:outline-none focus:ring-2 focus:ring-[#e94560]"
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            completeAuth();
                          }
                        }}
                      />
                      <button
                        onClick={completeAuth}
                        disabled={!authCode.trim()}
                        className="px-6 py-2 bg-[#e94560] rounded hover:bg-[#d63d56] transition disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Submit
                      </button>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={cancelAuth}
                      className="w-full py-2 px-4 bg-gray-700 text-white rounded hover:bg-gray-600 transition"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Status Message */}
              {authMessage && (
                <div className="mt-4 p-3 bg-[#1a1a2e] rounded text-sm">
                  {authMessage}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
