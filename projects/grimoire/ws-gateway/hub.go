package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"sync"

	"nhooyr.io/websocket"
)

// Hub manages all active WebSocket client connections and coordinates
// broadcasting messages. It is designed to work with Redis pub/sub so that
// multiple gateway replicas can relay events to all connected clients.
const maxConnsPerUser = 5

type Hub struct {
	mu        sync.RWMutex
	clients   map[*Client]bool
	connCount map[string]int // email -> active connection count

	register   chan *Client
	unregister chan *Client
	broadcast  chan []byte

	redis *RedisRelay
}

// NewHub creates a Hub wired to the given RedisRelay.
// Pass nil for redis to run without cross-replica messaging (single-replica mode).
func NewHub(redis *RedisRelay) *Hub {
	return &Hub{
		clients:    make(map[*Client]bool),
		connCount:  make(map[string]int),
		register:   make(chan *Client),
		unregister: make(chan *Client),
		broadcast:  make(chan []byte, 256),
		redis:      redis,
	}
}

// Run processes register, unregister, and broadcast events.
// It should be started as a goroutine.
func (h *Hub) Run(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			h.mu.Lock()
			for c := range h.clients {
				if c.conn != nil {
					c.conn.Close(websocket.StatusGoingAway, "server shutting down")
				}
				close(c.send)
				delete(h.clients, c)
			}
			h.mu.Unlock()
			return

		case client := <-h.register:
			h.mu.Lock()
			if h.connCount[client.email] >= maxConnsPerUser {
				h.mu.Unlock()
				slog.Warn("connection limit exceeded", "email", client.email)
				if client.conn != nil {
					client.conn.Close(websocket.StatusTryAgainLater, "too many connections")
				}
				continue
			}
			h.clients[client] = true
			h.connCount[client.email]++
			h.mu.Unlock()

			slog.Info("client connected", "email", client.email, "clients", h.clientCount())
			h.broadcastPresence(client.email, "online")

		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				close(client.send)
				h.connCount[client.email]--
				if h.connCount[client.email] <= 0 {
					delete(h.connCount, client.email)
				}
			}
			h.mu.Unlock()

			slog.Info("client disconnected", "email", client.email, "clients", h.clientCount())
			h.broadcastPresence(client.email, "offline")

		case message := <-h.broadcast:
			h.distributeLocal(message)
		}
	}
}

// Broadcast sends a message to all connected clients via Redis pub/sub.
// If Redis is unavailable, falls back to local-only distribution.
func (h *Hub) Broadcast(msg []byte) {
	if h.redis != nil {
		if err := h.redis.Publish(msg); err != nil {
			slog.Error("redis publish failed, falling back to local", "error", err)
			h.distributeLocal(msg)
		}
		return
	}
	h.distributeLocal(msg)
}

// HandleRedisMessage is called by RedisRelay when a message arrives on the
// subscription channel. It distributes the message to local clients.
func (h *Hub) HandleRedisMessage(msg []byte) {
	h.distributeLocal(msg)
}

// distributeLocal sends a message to all locally connected clients,
// enforcing PrivateTo filtering for private messages.
func (h *Hub) distributeLocal(message []byte) {
	// Check if this is a private message.
	var envelope WSEvent
	var privateTo, senderID string
	if json.Unmarshal(message, &envelope) == nil && envelope.Type == EventFeedEvent {
		var feed struct {
			PrivateTo string `json:"private_to"`
			SpeakerID string `json:"speaker_id"`
		}
		if json.Unmarshal(envelope.Data, &feed) == nil {
			privateTo = feed.PrivateTo
			senderID = feed.SpeakerID
		}
	}

	h.mu.RLock()
	defer h.mu.RUnlock()

	for client := range h.clients {
		// Enforce PrivateTo: only deliver to the recipient and sender.
		if privateTo != "" && client.email != privateTo && client.email != senderID {
			continue
		}
		select {
		case client.send <- message:
		default:
			slog.Warn("dropping message for slow client", "email", client.email)
		}
	}
}

// broadcastPresence emits a presence event for the given player.
func (h *Hub) broadcastPresence(email, status string) {
	pe := PresenceEvent{
		PlayerID: email,
		Status:   status,
	}
	data, err := json.Marshal(pe)
	if err != nil {
		return
	}
	env := WSEvent{Type: EventPresence, Data: data}
	msg, err := json.Marshal(env)
	if err != nil {
		return
	}
	h.Broadcast(msg)
}

// clientCount returns the number of connected clients.
func (h *Hub) clientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}

// ConnectedEmails returns the emails of all connected clients.
func (h *Hub) ConnectedEmails() []string {
	h.mu.RLock()
	defer h.mu.RUnlock()

	seen := make(map[string]bool)
	for c := range h.clients {
		seen[c.email] = true
	}
	emails := make([]string, 0, len(seen))
	for e := range seen {
		emails = append(emails, e)
	}
	return emails
}
