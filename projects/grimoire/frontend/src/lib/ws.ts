import type { WSEvent, FeedEvent } from "@/types";
import { useStore } from "./store";

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let connectionId = 0;

function getWSUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export function connectWS(): void {
  if (
    socket?.readyState === WebSocket.OPEN ||
    socket?.readyState === WebSocket.CONNECTING
  )
    return;

  const myId = ++connectionId;
  const ws = new WebSocket(getWSUrl());
  socket = ws;

  ws.onopen = () => {
    if (myId !== connectionId) {
      ws.close();
      return;
    }
    useStore.getState().setConnected(true);
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onmessage = (ev) => {
    if (myId !== connectionId) return;
    try {
      const msg: WSEvent = JSON.parse(ev.data);
      handleWSMessage(msg);
    } catch {
      // Binary audio data or unparseable message
    }
  };

  ws.onclose = () => {
    if (myId !== connectionId) return;
    useStore.getState().setConnected(false);
    socket = null;
    scheduleReconnect();
  };

  ws.onerror = () => {
    if (myId !== connectionId) return;
    ws.close();
  };
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWS();
  }, 2000);
}

function handleWSMessage(msg: WSEvent): void {
  const store = useStore.getState();

  switch (msg.type) {
    case "feed_event":
    case "transcript":
      store.addFeedEvent(msg.event);
      break;
    case "roll_result":
      store.addFeedEvent({
        id: crypto.randomUUID(),
        who: msg.player ?? msg.character ?? "Unknown",
        time: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        source: "roll",
        roll: msg.roll,
      });
      break;
    case "voice_status":
      store.setSpeaking(msg.speaker_id, msg.speaking);
      break;
    case "presence":
      // Could update online indicators
      break;
  }
}

export function sendWSMessage(event: WSEvent): void {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(event));
  }
}

export function sendAudioChunk(data: ArrayBuffer): void {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(data);
  }
}

export function disconnectWS(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  socket?.close();
  socket = null;
}
