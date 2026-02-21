package main

import "encoding/json"

// WSEvent is the envelope for all messages between browser and gateway.
// The Type field determines which payload fields are populated.
type WSEvent struct {
	Type string          `json:"type"`
	Data json.RawMessage `json:"data,omitempty"`
}

// Event type constants matching the architecture spec.
const (
	EventAudioChunk      = "audio_chunk"
	EventVoiceStatus     = "voice_status"
	EventTranscript      = "transcript"
	EventFeedEvent       = "feed_event"
	EventRollResult      = "roll_result"
	EventEncounterUpdate = "encounter_update"
	EventDMCorrection    = "dm_correction"
	EventPresence        = "presence"
)

// VoiceStatus indicates whether a player is currently speaking.
type VoiceStatus struct {
	SpeakerID string `json:"speaker_id"`
	Speaking  bool   `json:"speaking"`
}

// TranscriptEvent carries a Gemini transcription result.
type TranscriptEvent struct {
	SpeakerID      string  `json:"speaker_id"`
	Text           string  `json:"text"`
	Classification string  `json:"classification"`
	Confidence     float64 `json:"confidence"`
}

// FeedEvent is a unified timeline entry (voice transcript, chat, roll, system).
type FeedEvent struct {
	ID             string  `json:"id"`
	SessionID      string  `json:"session_id"`
	SpeakerID      string  `json:"speaker_id"`
	Source         string  `json:"source"` // voice, typed, roll, system
	Classification string  `json:"classification"`
	Confidence     float64 `json:"confidence"`
	Text           string  `json:"text"`
	PrivateTo      string  `json:"private_to,omitempty"`
	RAGTriggered   bool    `json:"rag_triggered,omitempty"`
}

// RollResult carries a dice roll outcome.
type RollResult struct {
	PlayerID string `json:"player_id"`
	Formula  string `json:"formula"`
	Result   int    `json:"result"`
	Context  string `json:"context,omitempty"`
	Private  bool   `json:"private,omitempty"`
}

// EncounterUpdate carries a full encounter state snapshot.
type EncounterUpdate struct {
	ID              string   `json:"id"`
	Name            string   `json:"name"`
	Status          string   `json:"status"`
	Round           int      `json:"round"`
	CurrentTurnID   string   `json:"current_turn_id"`
	InitiativeOrder []string `json:"initiative_order"`
}

// DMCorrection is sent when the DM reclassifies a feed event.
type DMCorrection struct {
	EventID           string `json:"event_id"`
	NewClassification string `json:"new_classification"`
}

// PresenceEvent announces a player coming online or going offline.
type PresenceEvent struct {
	PlayerID string `json:"player_id"`
	Status   string `json:"status"` // "online" or "offline"
}
