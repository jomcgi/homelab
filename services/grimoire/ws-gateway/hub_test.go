package main

import (
	"context"
	"encoding/json"
	"testing"
	"time"
)

// makeTestClient builds a Client without a real WebSocket connection.
// The send channel is buffered so tests can read queued messages.
func makeTestClient(hub *Hub, email string) *Client {
	return &Client{
		hub:   hub,
		conn:  nil, // not used in Hub logic under test
		email: email,
		send:  make(chan []byte, sendBufferSize),
	}
}

// runHub starts Hub.Run in a goroutine and returns a cancel func.
func runHub(h *Hub) (context.Context, context.CancelFunc) {
	ctx, cancel := context.WithCancel(context.Background())
	go h.Run(ctx)
	return ctx, cancel
}

// drainSend reads up to n messages from client.send within timeout.
func drainSend(c *Client, n int, timeout time.Duration) [][]byte {
	var out [][]byte
	deadline := time.After(timeout)
	for len(out) < n {
		select {
		case msg := <-c.send:
			out = append(out, msg)
		case <-deadline:
			return out
		}
	}
	return out
}

// TestHubRegisterAddsClient verifies that registering a client makes it
// visible inside Hub.clients.
func TestHubRegisterAddsClient(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c := makeTestClient(h, "alice@example.com")
	h.register <- c

	// Give the hub goroutine time to process.
	time.Sleep(20 * time.Millisecond)

	h.mu.RLock()
	_, ok := h.clients[c]
	count := h.connCount[c.email]
	h.mu.RUnlock()

	if !ok {
		t.Error("client should be in hub.clients after register")
	}
	if count != 1 {
		t.Errorf("connCount should be 1, got %d", count)
	}
}

// TestHubUnregisterRemovesClient verifies that unregistering removes the client.
func TestHubUnregisterRemovesClient(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c := makeTestClient(h, "bob@example.com")
	h.register <- c
	time.Sleep(20 * time.Millisecond)

	h.unregister <- c
	time.Sleep(20 * time.Millisecond)

	h.mu.RLock()
	_, ok := h.clients[c]
	count := h.connCount[c.email]
	h.mu.RUnlock()

	if ok {
		t.Error("client should not be in hub.clients after unregister")
	}
	if count != 0 {
		t.Errorf("connCount should be 0, got %d", count)
	}
}

// TestHubUnregisterClosesSendChannel verifies the send channel is closed on unregister.
func TestHubUnregisterClosesSendChannel(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c := makeTestClient(h, "carol@example.com")
	h.register <- c
	time.Sleep(20 * time.Millisecond)

	// Drain buffered presence events from registration so the send channel is
	// empty before unregistering; otherwise the closed-channel check below
	// would dequeue a presence message (ok=true) and incorrectly fail.
	for len(c.send) > 0 {
		<-c.send
	}

	h.unregister <- c
	time.Sleep(20 * time.Millisecond)

	// Reading from a closed, empty channel returns the zero value immediately.
	select {
	case _, ok := <-c.send:
		if ok {
			t.Error("send channel should be closed")
		}
	default:
		t.Error("send channel should be closed and readable")
	}
}

// TestHubBroadcastDeliverToAllClients verifies that a broadcast reaches every client.
func TestHubBroadcastDeliverToAllClients(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c1 := makeTestClient(h, "alice@example.com")
	c2 := makeTestClient(h, "bob@example.com")
	h.register <- c1
	h.register <- c2
	time.Sleep(20 * time.Millisecond)

	// Drain presence events buffered during registration so only the broadcast
	// message below appears in the send channels when we assert.
	for _, c := range []*Client{c1, c2} {
		for len(c.send) > 0 {
			<-c.send
		}
	}

	msg := []byte(`{"type":"roll_result","data":{}}`)
	h.broadcast <- msg
	time.Sleep(20 * time.Millisecond)

	// Both clients should have received the message.
	for _, c := range []*Client{c1, c2} {
		select {
		case received := <-c.send:
			if string(received) != string(msg) {
				t.Errorf("client %s received unexpected message: %s", c.email, received)
			}
		default:
			t.Errorf("client %s did not receive broadcast", c.email)
		}
	}
}

// TestHubConnectionLimitRejected verifies maxConnsPerUser is enforced.
func TestHubConnectionLimitRejected(t *testing.T) {
	h := NewHub(nil)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go h.Run(ctx)

	email := "spam@example.com"

	// Register maxConnsPerUser connections — all should succeed.
	var admitted []*Client
	for i := 0; i < maxConnsPerUser; i++ {
		c := makeTestClient(h, email)
		h.register <- c
		time.Sleep(10 * time.Millisecond)
		h.mu.RLock()
		_, ok := h.clients[c]
		h.mu.RUnlock()
		if ok {
			admitted = append(admitted, c)
		}
	}
	if len(admitted) != maxConnsPerUser {
		t.Errorf("expected %d admitted clients, got %d", maxConnsPerUser, len(admitted))
	}

	// One more connection from the same user — should be rejected.
	extra := makeTestClient(h, email)
	h.register <- extra
	time.Sleep(20 * time.Millisecond)

	h.mu.RLock()
	_, ok := h.clients[extra]
	h.mu.RUnlock()

	if ok {
		t.Error("extra client beyond connection limit should not be in hub.clients")
	}
}

// TestHubConnectedEmails returns unique emails of connected clients.
func TestHubConnectedEmails(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c1 := makeTestClient(h, "alice@example.com")
	c2 := makeTestClient(h, "alice@example.com") // second connection for same user
	c3 := makeTestClient(h, "bob@example.com")
	h.register <- c1
	h.register <- c2
	h.register <- c3
	time.Sleep(30 * time.Millisecond)

	emails := h.ConnectedEmails()

	seen := make(map[string]bool)
	for _, e := range emails {
		seen[e] = true
	}

	if !seen["alice@example.com"] {
		t.Error("alice@example.com should appear in ConnectedEmails")
	}
	if !seen["bob@example.com"] {
		t.Error("bob@example.com should appear in ConnectedEmails")
	}
	// Each email should appear only once.
	if len(emails) != 2 {
		t.Errorf("ConnectedEmails should deduplicate: expected 2, got %d", len(emails))
	}
}

// TestHubPrivateMessageFilteredToRecipient verifies that private feed_event messages
// are only sent to the sender and the recipient.
func TestHubPrivateMessageFilteredToRecipient(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	sender := makeTestClient(h, "dm@example.com")
	recipient := makeTestClient(h, "player@example.com")
	bystander := makeTestClient(h, "bystander@example.com")

	h.register <- sender
	h.register <- recipient
	h.register <- bystander
	time.Sleep(20 * time.Millisecond)

	// Drain presence events from registration.
	time.Sleep(10 * time.Millisecond)
	for _, c := range []*Client{sender, recipient, bystander} {
		for len(c.send) > 0 {
			<-c.send
		}
	}

	// Build a private feed_event addressed to recipient.
	feedData, _ := json.Marshal(map[string]string{
		"private_to": "player@example.com",
		"speaker_id": "dm@example.com",
	})
	env := WSEvent{Type: EventFeedEvent, Data: feedData}
	envMsg, _ := json.Marshal(env)

	h.broadcast <- envMsg
	time.Sleep(20 * time.Millisecond)

	// Sender and recipient should receive it; bystander should not.
	if len(sender.send) == 0 {
		t.Error("sender should receive their own private message")
	}
	if len(recipient.send) == 0 {
		t.Error("recipient should receive the private message")
	}
	if len(bystander.send) > 0 {
		t.Error("bystander should not receive a private message not addressed to them")
	}
}

// TestHubPublicMessageDeliveredToAll verifies non-private messages reach everyone.
func TestHubPublicMessageDeliveredToAll(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c1 := makeTestClient(h, "alice@example.com")
	c2 := makeTestClient(h, "bob@example.com")
	h.register <- c1
	h.register <- c2
	time.Sleep(20 * time.Millisecond)

	// Drain presence messages.
	for _, c := range []*Client{c1, c2} {
		for len(c.send) > 0 {
			<-c.send
		}
	}

	// Broadcast a non-private roll_result.
	msg := []byte(`{"type":"roll_result","data":{"result":18}}`)
	h.broadcast <- msg
	time.Sleep(20 * time.Millisecond)

	for _, c := range []*Client{c1, c2} {
		if len(c.send) == 0 {
			t.Errorf("client %s should receive public message", c.email)
		}
	}
}

// TestHubContextCancellationStopsRun verifies Run exits cleanly when context is cancelled.
func TestHubContextCancellationStopsRun(t *testing.T) {
	h := NewHub(nil)
	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan struct{})
	go func() {
		h.Run(ctx)
		close(done)
	}()

	cancel()

	select {
	case <-done:
		// Hub stopped cleanly.
	case <-time.After(200 * time.Millisecond):
		t.Error("Hub.Run did not stop after context cancellation")
	}
}

// TestHubClientCountAccurate verifies clientCount matches registered clients.
func TestHubClientCountAccurate(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	if h.clientCount() != 0 {
		t.Error("initial client count should be 0")
	}

	c1 := makeTestClient(h, "alice@example.com")
	c2 := makeTestClient(h, "bob@example.com")
	h.register <- c1
	h.register <- c2
	time.Sleep(20 * time.Millisecond)

	if h.clientCount() != 2 {
		t.Errorf("client count should be 2, got %d", h.clientCount())
	}

	h.unregister <- c1
	time.Sleep(20 * time.Millisecond)

	if h.clientCount() != 1 {
		t.Errorf("client count should be 1 after unregister, got %d", h.clientCount())
	}
}
