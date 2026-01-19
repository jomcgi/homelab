import { useEffect, useRef, useCallback, useState } from "react";
import type { StreamEvent } from "../types";
import { getAuthToken } from "../../hooks/useAuth";

interface UseStreamingOptions {
  onMessage: (event: StreamEvent) => void;
  onError?: (error: Error) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

export function useStreaming(
  streamingId: string | null,
  options: UseStreamingOptions,
) {
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [shouldReconnect, setShouldReconnect] = useState(true);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(
    null,
  );
  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const reconnectAttemptsRef = useRef(0);
  const optionsRef = useRef(options);

  // Keep options ref up to date
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const disconnect = useCallback((isIntentional = true) => {
    if (isIntentional) {
      setShouldReconnect(false); // Mark as intentional disconnect
      reconnectAttemptsRef.current = 0; // Reset retry counter
      clearTimeout(reconnectTimeoutRef.current);
    }

    if (readerRef.current) {
      readerRef.current.cancel().catch(() => {});
      readerRef.current = null;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    setIsConnected((prev) => {
      if (prev) {
        optionsRef.current.onDisconnect?.();
      }
      return false;
    });
    setIsReconnecting(false);
  }, []);

  const connect = useCallback(async () => {
    // Guard against multiple connections
    if (!streamingId || readerRef.current || abortControllerRef.current) {
      return;
    }

    setShouldReconnect(true); // Reset to allow reconnection

    try {
      abortControllerRef.current = new AbortController();

      // Get auth token for Bearer authorization
      const authToken = getAuthToken();
      const headers: Record<string, string> = {};

      // Add Bearer token if available
      if (authToken) {
        headers.Authorization = `Bearer ${authToken}`;
      }

      const response = await fetch(`/api/stream/${streamingId}`, {
        signal: abortControllerRef.current.signal,
        headers,
      });

      if (!response.ok) {
        throw new Error(`Stream connection failed: ${response.status}`);
      }

      if (!response.body) {
        throw new Error("No response body");
      }

      const reader = response.body.getReader();
      readerRef.current = reader;
      setIsConnected(true);
      setIsReconnecting(false);
      reconnectAttemptsRef.current = 0; // Reset on successful connection
      optionsRef.current.onConnect?.();

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const decoded = decoder.decode(value, { stream: true });
        buffer += decoded;

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.trim()) {
            try {
              // Handle SSE format: remove "data: " prefix
              let jsonLine = line;
              if (line.startsWith("data: ")) {
                jsonLine = line.substring(6);
              }

              // Skip SSE comments (lines starting with :)
              if (line.startsWith(":")) {
                continue;
              }

              const event = JSON.parse(jsonLine) as StreamEvent;
              optionsRef.current.onMessage(event);
            } catch (err) {
              console.error("Failed to parse stream message:", line, err);
            }
          }
        }
      }
    } catch (error: any) {
      if (error.name !== "AbortError") {
        console.error("Stream error:", error);

        // Only report transient errors to user, not reconnection attempts
        if (reconnectAttemptsRef.current === 0) {
          optionsRef.current.onError?.(error);
        }
      }
    } finally {
      const wasIntentional = !shouldReconnect;
      disconnect(false); // Don't reset reconnect state

      // Auto-reconnect if unintentional and page visible
      if (
        !wasIntentional &&
        document.visibilityState === "visible" &&
        streamingId &&
        navigator.onLine // Check if browser is online
      ) {
        reconnectAttemptsRef.current++;

        // Exponential backoff: 2s, 4s, 8s, 16s, max 30s
        const delay = Math.min(
          2000 * Math.pow(2, reconnectAttemptsRef.current - 1),
          30000,
        );

        setIsReconnecting(true);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    }
  }, [streamingId, disconnect]);

  useEffect(() => {
    if (streamingId) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [streamingId]); // Only depend on streamingId, not the callbacks

  // Handle visibility change and online/offline for reconnection
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (
        document.visibilityState === "visible" &&
        !isConnected &&
        shouldReconnect &&
        streamingId &&
        navigator.onLine
      ) {
        clearTimeout(reconnectTimeoutRef.current);
        setIsReconnecting(true);
        connect();
      }
    };

    const handleOnline = () => {
      // Immediately try to reconnect when coming back online
      if (!isConnected && shouldReconnect && streamingId) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectAttemptsRef.current = 0; // Reset attempts on network recovery
        setIsReconnecting(true);
        connect();
      }
    };

    const handleOffline = () => {
      // Clear any pending reconnection attempts when going offline
      clearTimeout(reconnectTimeoutRef.current);
      setIsReconnecting(false);
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      clearTimeout(reconnectTimeoutRef.current);
    };
  }, [isConnected, shouldReconnect, streamingId, connect]);

  return {
    isConnected,
    isReconnecting,
    connect,
    disconnect,
  };
}
