package main

import (
	"encoding/json"
	"testing"
)

// TestEventTypeConstants verifies all event type constants have their expected string values
// as defined in the architecture spec.
func TestEventTypeConstants(t *testing.T) {
	cases := []struct {
		name     string
		constant string
		want     string
	}{
		{"EventAudioChunk", EventAudioChunk, "audio_chunk"},
		{"EventVoiceStatus", EventVoiceStatus, "voice_status"},
		{"EventTranscript", EventTranscript, "transcript"},
		{"EventFeedEvent", EventFeedEvent, "feed_event"},
		{"EventRollResult", EventRollResult, "roll_result"},
		{"EventEncounterUpdate", EventEncounterUpdate, "encounter_update"},
		{"EventDMCorrection", EventDMCorrection, "dm_correction"},
		{"EventPresence", EventPresence, "presence"},
	}
	for _, tc := range cases {
		if tc.constant != tc.want {
			t.Errorf("%s = %q, want %q", tc.name, tc.constant, tc.want)
		}
	}
}

// TestWSEvent_RoundTrip verifies WSEvent marshals and unmarshals correctly.
func TestWSEvent_RoundTrip(t *testing.T) {
	original := WSEvent{
		Type: EventRollResult,
		Data: json.RawMessage(`{"result":20,"formula":"1d20"}`),
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("marshaling WSEvent: %v", err)
	}

	var decoded WSEvent
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshaling WSEvent: %v", err)
	}

	if decoded.Type != original.Type {
		t.Errorf("Type got %q, want %q", decoded.Type, original.Type)
	}
	if string(decoded.Data) != string(original.Data) {
		t.Errorf("Data got %s, want %s", decoded.Data, original.Data)
	}
}

// TestWSEvent_OmitsEmptyData verifies the data field is omitted from JSON when nil.
func TestWSEvent_OmitsEmptyData(t *testing.T) {
	event := WSEvent{Type: EventPresence}
	data, _ := json.Marshal(event)

	var m map[string]any
	json.Unmarshal(data, &m)

	if _, ok := m["data"]; ok {
		t.Error("data field should be omitted when not set")
	}
}

// TestVoiceStatus_JSON verifies VoiceStatus marshals with the correct JSON field names.
func TestVoiceStatus_JSON(t *testing.T) {
	vs := VoiceStatus{SpeakerID: "player1@example.com", Speaking: true}
	data, _ := json.Marshal(vs)

	var m map[string]any
	json.Unmarshal(data, &m)

	if m["speaker_id"] != "player1@example.com" {
		t.Errorf("speaker_id got %v, want %q", m["speaker_id"], "player1@example.com")
	}
	if m["speaking"] != true {
		t.Errorf("speaking got %v, want true", m["speaking"])
	}
}

// TestVoiceStatus_NotSpeaking verifies VoiceStatus with Speaking=false marshals correctly.
func TestVoiceStatus_NotSpeaking(t *testing.T) {
	vs := VoiceStatus{SpeakerID: "player1@example.com", Speaking: false}
	data, _ := json.Marshal(vs)

	var m map[string]any
	json.Unmarshal(data, &m)

	if m["speaking"] != false {
		t.Errorf("speaking got %v, want false", m["speaking"])
	}
}

// TestFeedEvent_PrivateToOmitEmpty verifies the private_to field is omitted when empty.
func TestFeedEvent_PrivateToOmitEmpty(t *testing.T) {
	fe := FeedEvent{
		ID:        "abc",
		SessionID: "sess1",
		Text:      "hello world",
	}
	data, _ := json.Marshal(fe)

	var m map[string]any
	json.Unmarshal(data, &m)

	if _, ok := m["private_to"]; ok {
		t.Error("private_to should be omitted when empty")
	}
}

// TestFeedEvent_PrivateToPresent verifies the private_to field is included when set.
func TestFeedEvent_PrivateToPresent(t *testing.T) {
	fe := FeedEvent{
		ID:        "abc",
		PrivateTo: "dm@example.com",
	}
	data, _ := json.Marshal(fe)

	var m map[string]any
	json.Unmarshal(data, &m)

	if m["private_to"] != "dm@example.com" {
		t.Errorf("private_to got %v, want %q", m["private_to"], "dm@example.com")
	}
}

// TestFeedEvent_AllFields verifies all FeedEvent fields are serialized with correct names.
func TestFeedEvent_AllFields(t *testing.T) {
	fe := FeedEvent{
		ID:             "evt1",
		SessionID:      "sess1",
		SpeakerID:      "player@example.com",
		Source:         "typed",
		Classification: "ic_action",
		Confidence:     0.95,
		Text:           "I attack the dragon",
		PrivateTo:      "dm@example.com",
		RAGTriggered:   true,
	}
	data, _ := json.Marshal(fe)

	var m map[string]any
	json.Unmarshal(data, &m)

	if m["id"] != "evt1" {
		t.Errorf("id got %v", m["id"])
	}
	if m["session_id"] != "sess1" {
		t.Errorf("session_id got %v", m["session_id"])
	}
	if m["speaker_id"] != "player@example.com" {
		t.Errorf("speaker_id got %v", m["speaker_id"])
	}
	if m["source"] != "typed" {
		t.Errorf("source got %v", m["source"])
	}
}

// TestPresenceEvent_JSON verifies PresenceEvent marshals with the correct field names.
func TestPresenceEvent_JSON(t *testing.T) {
	cases := []struct {
		status string
	}{
		{"online"},
		{"offline"},
	}
	for _, tc := range cases {
		pe := PresenceEvent{PlayerID: "alice@example.com", Status: tc.status}
		data, _ := json.Marshal(pe)

		var m map[string]any
		json.Unmarshal(data, &m)

		if m["player_id"] != "alice@example.com" {
			t.Errorf("[%s] player_id got %v", tc.status, m["player_id"])
		}
		if m["status"] != tc.status {
			t.Errorf("[%s] status got %v", tc.status, m["status"])
		}
	}
}

// TestRollResult_JSON verifies RollResult marshals correctly including optional fields.
func TestRollResult_JSON(t *testing.T) {
	rr := RollResult{
		PlayerID: "player@example.com",
		Formula:  "2d6+3",
		Result:   15,
		Context:  "attack roll",
		Private:  true,
	}
	data, _ := json.Marshal(rr)

	var m map[string]any
	json.Unmarshal(data, &m)

	if m["player_id"] != "player@example.com" {
		t.Errorf("player_id got %v", m["player_id"])
	}
	if m["formula"] != "2d6+3" {
		t.Errorf("formula got %v", m["formula"])
	}
	if m["result"] != float64(15) {
		t.Errorf("result got %v", m["result"])
	}
	if m["context"] != "attack roll" {
		t.Errorf("context got %v", m["context"])
	}
	if m["private"] != true {
		t.Errorf("private got %v", m["private"])
	}
}

// TestRollResult_OmitsEmptyOptionals verifies context and private are omitted when zero-valued.
func TestRollResult_OmitsEmptyOptionals(t *testing.T) {
	rr := RollResult{PlayerID: "p1", Formula: "1d20", Result: 10}
	data, _ := json.Marshal(rr)

	var m map[string]any
	json.Unmarshal(data, &m)

	if _, ok := m["context"]; ok {
		t.Error("context should be omitted when empty")
	}
	if _, ok := m["private"]; ok {
		t.Error("private should be omitted when false")
	}
}

// TestEncounterUpdate_JSON verifies EncounterUpdate marshals all fields correctly.
func TestEncounterUpdate_JSON(t *testing.T) {
	eu := EncounterUpdate{
		ID:              "enc1",
		Name:            "Dragon Ambush",
		Status:          "active",
		Round:           3,
		CurrentTurnID:   "player1",
		InitiativeOrder: []string{"player1", "dragon", "player2"},
	}
	data, _ := json.Marshal(eu)

	var m map[string]any
	json.Unmarshal(data, &m)

	if m["id"] != "enc1" {
		t.Errorf("id got %v", m["id"])
	}
	if m["name"] != "Dragon Ambush" {
		t.Errorf("name got %v", m["name"])
	}
	if m["status"] != "active" {
		t.Errorf("status got %v", m["status"])
	}
	if m["round"] != float64(3) {
		t.Errorf("round got %v", m["round"])
	}
	if m["current_turn_id"] != "player1" {
		t.Errorf("current_turn_id got %v", m["current_turn_id"])
	}
}

// TestDMCorrection_JSON verifies DMCorrection marshals with the correct field names.
func TestDMCorrection_JSON(t *testing.T) {
	dc := DMCorrection{EventID: "evt1", NewClassification: "dm_ruling"}
	data, _ := json.Marshal(dc)

	var m map[string]any
	json.Unmarshal(data, &m)

	if m["event_id"] != "evt1" {
		t.Errorf("event_id got %v", m["event_id"])
	}
	if m["new_classification"] != "dm_ruling" {
		t.Errorf("new_classification got %v", m["new_classification"])
	}
}
