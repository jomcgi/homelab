package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"nhooyr.io/websocket"
)

const (
	// writeWait is the time allowed to write a message to the client.
	writeWait = 10 * time.Second

	// pongWait is the time allowed to read the next pong from the client.
	pongWait = 60 * time.Second

	// pingPeriod sends pings at this interval. Must be less than pongWait.
	pingPeriod = (pongWait * 9) / 10

	// maxMessageSize is the maximum message size allowed from a client.
	maxMessageSize = 64 * 1024 // 64 KB (text messages; audio_chunk is handled separately in Phase 3)

	// sendBufferSize is the per-client outbound message buffer.
	sendBufferSize = 256
)

// Client represents a single WebSocket connection from a browser.
type Client struct {
	hub   *Hub
	conn  *websocket.Conn
	email string // Authenticated identity from Cloudflare Access JWT.
	send  chan []byte
}

// NewClient creates a client for the given authenticated connection.
func NewClient(hub *Hub, conn *websocket.Conn, email string) *Client {
	return &Client{
		hub:   hub,
		conn:  conn,
		email: email,
		send:  make(chan []byte, sendBufferSize),
	}
}

// readPump reads messages from the WebSocket connection and dispatches them.
// It runs in its own goroutine per client.
func (c *Client) readPump(ctx context.Context) {
	defer func() {
		c.hub.unregister <- c
		c.conn.Close(websocket.StatusNormalClosure, "")
	}()

	c.conn.SetReadLimit(maxMessageSize)

	for {
		_, message, err := c.conn.Read(ctx)
		if err != nil {
			if websocket.CloseStatus(err) == websocket.StatusNormalClosure ||
				websocket.CloseStatus(err) == websocket.StatusGoingAway {
				slog.Debug("client closed connection", "email", c.email)
			} else {
				slog.Error("read error", "email", c.email, "error", err)
			}
			return
		}

		c.handleMessage(message)
	}
}

// writePump writes messages from the send channel to the WebSocket connection.
// It also sends periodic pings to detect dead connections.
// It runs in its own goroutine per client.
func (c *Client) writePump(ctx context.Context) {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		c.conn.Close(websocket.StatusNormalClosure, "")
	}()

	for {
		select {
		case message, ok := <-c.send:
			if !ok {
				// Hub closed the channel.
				return
			}

			writeCtx, cancel := context.WithTimeout(ctx, writeWait)
			err := c.conn.Write(writeCtx, websocket.MessageText, message)
			cancel()

			if err != nil {
				slog.Error("write error", "email", c.email, "error", err)
				return
			}

		case <-ticker.C:
			pingCtx, cancel := context.WithTimeout(ctx, writeWait)
			err := c.conn.Ping(pingCtx)
			cancel()

			if err != nil {
				slog.Error("ping failed", "email", c.email, "error", err)
				return
			}

		case <-ctx.Done():
			return
		}
	}
}

// handleMessage routes an incoming client message based on its event type.
func (c *Client) handleMessage(raw []byte) {
	var event WSEvent
	if err := json.Unmarshal(raw, &event); err != nil {
		slog.Warn("invalid message from client", "email", c.email, "error", err)
		return
	}

	switch event.Type {
	case EventAudioChunk:
		// Phase 3: proxy PCM audio to Gemini Live session.
		// For now, log and discard.
		slog.Debug("audio_chunk received (Phase 3 stub)", "email", c.email)

	case EventVoiceStatus:
		// Broadcast voice speaking status to all clients.
		var vs VoiceStatus
		if err := json.Unmarshal(event.Data, &vs); err != nil {
			slog.Warn("invalid voice_status payload", "email", c.email, "error", err)
			return
		}
		// Tag with the authenticated sender to prevent spoofing.
		vs.SpeakerID = c.email
		data, err := json.Marshal(vs)
		if err != nil {
			slog.Error("marshal voice status", "email", c.email, "error", err)
			return
		}
		envelope := WSEvent{Type: EventVoiceStatus, Data: data}
		msg, err := json.Marshal(envelope)
		if err != nil {
			slog.Error("marshal voice envelope", "email", c.email, "error", err)
			return
		}
		c.hub.Broadcast(msg)

	case EventDMCorrection, EventEncounterUpdate:
		// DM-only events — tag with authenticated sender for audit trail.
		var tagged map[string]any
		if err := json.Unmarshal(raw, &tagged); err == nil {
			tagged["sender"] = c.email
			if out, err := json.Marshal(tagged); err == nil {
				raw = out
			}
		}
		c.hub.Broadcast(raw)

	case EventFeedEvent, EventRollResult:
		// Tag game events with authenticated sender.
		var tagged map[string]any
		if err := json.Unmarshal(raw, &tagged); err == nil {
			tagged["sender"] = c.email
			if out, err := json.Marshal(tagged); err == nil {
				raw = out
			}
		}
		c.hub.Broadcast(raw)

	default:
		slog.Warn("unknown event type", "email", c.email, "type", event.Type)
	}
}
