import { useEffect } from "react";
import { connectWS, disconnectWS } from "@/lib/ws";

/** Connect the WebSocket on mount, disconnect on unmount. */
export function useWebSocket() {
  useEffect(() => {
    connectWS();
    return () => disconnectWS();
  }, []);
}
