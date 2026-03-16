package main

import (
	"encoding/json"
	"testing"
	"time"
)

// TestNewClient_Fields verifies NewClient initializes all required fields correctly.
func TestNewClient_Fields(t *testing.T) {
	h := NewHub(nil)
	c := NewClient(h, nil, "user@example.com")

	if c.hub != h {
		t.Error("hub field not set correctly")
	}
	if c.email != "user@example.com" {
		t.Errorf("email got %q, want %q", c.email, "user@example.com")
	}
	if c.send == nil {
		t.Error("send channel should not be nil")
	}
	if cap(c.send) != sendBufferSize {
		t.Errorf("send buffer size got %d, want %d", cap(c.send), sendBufferSize)
	}
	if c.conn != nil {
		t.Error("conn should be nil when passed nil")
	}
}

// TestHandleMessage_AudioChunk verifies audio_chunk events are silently discarded without broadcast.
func TestHandleMessage_AudioChunk(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c := makeTestClient(h, "player@example.com")
	h.register <- c
	time.Sleep(20 * time.Millisecond)

	// Drain presence events from registration.
	for len(c.send) > 0 {
		<-c.send
	}

	msg, _ := json.Marshal(WSEvent{Type: EventAudioChunk, Data: json.RawMessage(`{}`)})
	c.handleMessage(msg)

	time.Sleep(20 * time.Millisecond)
	if len(c.send) > 0 {
		t.Error("audio_chunk should be silently discarded, but something was sent")
	}
}

// TestHandleMessage_VoiceStatus verifies voice_status events are broadcast and the speaker_id
// is overridden with the authenticated sender's email to prevent spoofing.
func TestHandleMessage_VoiceStatus(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	sender := makeTestClient(h, "speaker@example.com")
	receiver := makeTestClient(h, "listener@example.com")
	h.register <- sender
	h.register <- receiver
	time.Sleep(20 * time.Millisecond)

	// Drain presence events from registration.
	for _, c := range []*Client{sender, receiver} {
		for len(c.send) > 0 {
			<-c.send
		}
	}

	// Send with a spoofed speaker_id — it must be overridden to the authenticated email.
	vsData, _ := json.Marshal(VoiceStatus{SpeakerID: "spoofed@example.com", Speaking: true})
	msg, _ := json.Marshal(WSEvent{Type: EventVoiceStatus, Data: vsData})
	sender.handleMessage(msg)

	time.Sleep(20 * time.Millisecond)

	msgs := drainSend(receiver, 1, 100*time.Millisecond)
	if len(msgs) == 0 {
		t.Fatal("receiver should have received the voice_status broadcast")
	}

	var received WSEvent
	json.Unmarshal(msgs[0], &received)
	if received.Type != EventVoiceStatus {
		t.Errorf("type got %q, want %q", received.Type, EventVoiceStatus)
	}

	var vs VoiceStatus
	json.Unmarshal(received.Data, &vs)
	if vs.SpeakerID != "speaker@example.com" {
		t.Errorf("speaker_id got %q, want %q (authenticated email, not spoofed)", vs.SpeakerID, "speaker@example.com")
	}
	if !vs.Speaking {
		t.Error("speaking should be true")
	}
}

// TestHandleMessage_FeedEvent verifies feed_event messages are tagged with the authenticated
// sender's email and broadcast to all clients.
func TestHandleMessage_FeedEvent(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	sender := makeTestClient(h, "dm@example.com")
	receiver := makeTestClient(h, "player@example.com")
	h.register <- sender
	h.register <- receiver
	time.Sleep(20 * time.Millisecond)

	for _, c := range []*Client{sender, receiver} {
		for len(c.send) > 0 {
			<-c.send
		}
	}

	feData, _ := json.Marshal(FeedEvent{Text: "the dragon breathes fire"})
	msg, _ := json.Marshal(WSEvent{Type: EventFeedEvent, Data: feData})
	sender.handleMessage(msg)

	time.Sleep(20 * time.Millisecond)

	msgs := drainSend(receiver, 1, 100*time.Millisecond)
	if len(msgs) == 0 {
		t.Fatal("receiver should have received the feed_event broadcast")
	}

	var received map[string]any
	json.Unmarshal(msgs[0], &received)
	if received["sender"] != "dm@example.com" {
		t.Errorf("sender field got %v, want %q", received["sender"], "dm@example.com")
	}
}

// TestHandleMessage_RollResult verifies roll_result events are tagged with the sender's email
// and broadcast to all clients.
func TestHandleMessage_RollResult(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	sender := makeTestClient(h, "player@example.com")
	h.register <- sender
	time.Sleep(20 * time.Millisecond)
	for len(sender.send) > 0 {
		<-sender.send
	}

	rrData, _ := json.Marshal(RollResult{Formula: "1d20", Result: 18})
	msg, _ := json.Marshal(WSEvent{Type: EventRollResult, Data: rrData})
	sender.handleMessage(msg)

	time.Sleep(20 * time.Millisecond)

	msgs := drainSend(sender, 1, 100*time.Millisecond)
	if len(msgs) == 0 {
		t.Fatal("sender should receive their own roll_result broadcast")
	}

	var received map[string]any
	json.Unmarshal(msgs[0], &received)
	if received["sender"] != "player@example.com" {
		t.Errorf("sender field got %v, want %q", received["sender"], "player@example.com")
	}
}

// TestHandleMessage_DMCorrection verifies dm_correction events are tagged with the sender's
// email for audit trail and broadcast.
func TestHandleMessage_DMCorrection(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	dm := makeTestClient(h, "dm@example.com")
	h.register <- dm
	time.Sleep(20 * time.Millisecond)
	for len(dm.send) > 0 {
		<-dm.send
	}

	corrData, _ := json.Marshal(DMCorrection{EventID: "evt1", NewClassification: "dm_ruling"})
	msg, _ := json.Marshal(WSEvent{Type: EventDMCorrection, Data: corrData})
	dm.handleMessage(msg)

	time.Sleep(20 * time.Millisecond)

	msgs := drainSend(dm, 1, 100*time.Millisecond)
	if len(msgs) == 0 {
		t.Fatal("DM should receive their own dm_correction broadcast")
	}

	var received map[string]any
	json.Unmarshal(msgs[0], &received)
	if received["sender"] != "dm@example.com" {
		t.Errorf("sender field got %v, want %q", received["sender"], "dm@example.com")
	}
}

// TestHandleMessage_EncounterUpdate verifies encounter_update events are tagged with the
// sender's email for audit trail and broadcast.
func TestHandleMessage_EncounterUpdate(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	dm := makeTestClient(h, "dm@example.com")
	player := makeTestClient(h, "player@example.com")
	h.register <- dm
	h.register <- player
	time.Sleep(20 * time.Millisecond)

	for _, c := range []*Client{dm, player} {
		for len(c.send) > 0 {
			<-c.send
		}
	}

	euData, _ := json.Marshal(EncounterUpdate{
		ID:     "enc1",
		Name:   "Dragon Fight",
		Status: "active",
		Round:  1,
	})
	msg, _ := json.Marshal(WSEvent{Type: EventEncounterUpdate, Data: euData})
	dm.handleMessage(msg)

	time.Sleep(20 * time.Millisecond)

	msgs := drainSend(player, 1, 100*time.Millisecond)
	if len(msgs) == 0 {
		t.Fatal("player should receive the encounter_update broadcast")
	}

	var received map[string]any
	json.Unmarshal(msgs[0], &received)
	if received["sender"] != "dm@example.com" {
		t.Errorf("sender field got %v, want %q", received["sender"], "dm@example.com")
	}
	if received["type"] != EventEncounterUpdate {
		t.Errorf("type got %v, want %q", received["type"], EventEncounterUpdate)
	}
}

// TestHandleMessage_InvalidJSON verifies that a message with invalid JSON is silently dropped.
func TestHandleMessage_InvalidJSON(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c := makeTestClient(h, "user@example.com")
	h.register <- c
	time.Sleep(20 * time.Millisecond)
	for len(c.send) > 0 {
		<-c.send
	}

	c.handleMessage([]byte("this is not valid json {{{"))

	time.Sleep(20 * time.Millisecond)
	if len(c.send) > 0 {
		t.Error("invalid JSON should be silently dropped without broadcasting")
	}
}

// TestHandleMessage_UnknownType verifies that unknown event types are silently dropped.
func TestHandleMessage_UnknownType(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c := makeTestClient(h, "user@example.com")
	h.register <- c
	time.Sleep(20 * time.Millisecond)
	for len(c.send) > 0 {
		<-c.send
	}

	msg, _ := json.Marshal(WSEvent{Type: "unknown_future_event_type"})
	c.handleMessage(msg)

	time.Sleep(20 * time.Millisecond)
	if len(c.send) > 0 {
		t.Error("unknown event type should be silently dropped without broadcasting")
	}
}

// TestHandleMessage_InvalidVoiceStatusPayload verifies that a voice_status event with
// invalid inner payload is dropped without broadcasting.
func TestHandleMessage_InvalidVoiceStatusPayload(t *testing.T) {
	h := NewHub(nil)
	_, cancel := runHub(h)
	defer cancel()

	c := makeTestClient(h, "user@example.com")
	h.register <- c
	time.Sleep(20 * time.Millisecond)
	for len(c.send) > 0 {
		<-c.send
	}

	// The outer JSON is valid but the data value is a JSON string, not an object —
	// json.Unmarshal into VoiceStatus{} will fail.
	raw := []byte(`{"type":"voice_status","data":"not-an-object"}`)
	c.handleMessage(raw)

	time.Sleep(20 * time.Millisecond)
	if len(c.send) > 0 {
		t.Error("invalid voice_status payload should be dropped without broadcasting")
	}
}
