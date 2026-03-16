package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestRegisterFeedRoutes verifies all feed routes can be registered without panicking.
func TestRegisterFeedRoutes(t *testing.T) {
	mux := http.NewServeMux()
	registerFeedRoutes(mux, nil)
}

// TestCreateFeedEvent_InvalidJSON verifies that a malformed request body returns 400.
func TestCreateFeedEvent_InvalidJSON(t *testing.T) {
	req := httptest.NewRequest("POST", "/api/sessions/s1/feed", bytes.NewBufferString("not valid json"))
	w := httptest.NewRecorder()

	createFeedEvent(nil)(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
	}
}

// TestCreateFeedEvent_MissingText verifies that a feed event without text returns 400.
func TestCreateFeedEvent_MissingText(t *testing.T) {
	cases := []struct {
		label string
		body  map[string]any
	}{
		{"empty text", map[string]any{"text": "", "campaign_id": "c1"}},
		{"text omitted", map[string]any{"campaign_id": "c1", "source": "typed"}},
	}
	for _, tc := range cases {
		t.Run(tc.label, func(t *testing.T) {
			b, _ := json.Marshal(tc.body)
			req := httptest.NewRequest("POST", "/api/sessions/s1/feed", bytes.NewReader(b))
			w := httptest.NewRecorder()

			createFeedEvent(nil)(w, req)

			if w.Code != http.StatusBadRequest {
				t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
			}
			var resp map[string]string
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("parsing response body: %v", err)
			}
			if resp["error"] != "text is required" {
				t.Errorf("error got %q, want %q", resp["error"], "text is required")
			}
		})
	}
}

// TestCreateFeedEvent_MissingCampaignID verifies that a feed event without campaign_id returns 400.
func TestCreateFeedEvent_MissingCampaignID(t *testing.T) {
	cases := []struct {
		label string
		body  map[string]any
	}{
		{"empty campaign_id", map[string]any{"text": "Hello world", "campaign_id": ""}},
		{"campaign_id omitted", map[string]any{"text": "Hello world"}},
	}
	for _, tc := range cases {
		t.Run(tc.label, func(t *testing.T) {
			b, _ := json.Marshal(tc.body)
			req := httptest.NewRequest("POST", "/api/sessions/s1/feed", bytes.NewReader(b))
			w := httptest.NewRecorder()

			createFeedEvent(nil)(w, req)

			if w.Code != http.StatusBadRequest {
				t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
			}
			var resp map[string]string
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("parsing response body: %v", err)
			}
			if resp["error"] != "campaign_id is required" {
				t.Errorf("error got %q, want %q", resp["error"], "campaign_id is required")
			}
		})
	}
}

// TestReclassifyFeedEvent_InvalidJSON verifies that a malformed request body returns 400.
func TestReclassifyFeedEvent_InvalidJSON(t *testing.T) {
	req := httptest.NewRequest("PATCH", "/api/feed/f1/reclassify", bytes.NewBufferString("not valid json"))
	w := httptest.NewRecorder()

	reclassifyFeedEvent(nil)(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
	}
}

// TestReclassifyFeedEvent_InvalidClassification verifies that unrecognised classifications return 400.
func TestReclassifyFeedEvent_InvalidClassification(t *testing.T) {
	cases := []struct {
		label          string
		classification string
	}{
		{"empty string", ""},
		{"unknown value", "unknown"},
		{"wrong case", "IC_ACTION"},
		{"hyphenated", "dm-narration"},
		{"spaces", "table talk"},
		{"roll type", "roll"},
		{"partial match", "ic_"},
		{"extra suffix", "ic_action_extra"},
	}
	for _, tc := range cases {
		t.Run(tc.label, func(t *testing.T) {
			b, _ := json.Marshal(map[string]string{"new_classification": tc.classification})
			req := httptest.NewRequest("PATCH", "/api/feed/f1/reclassify", bytes.NewReader(b))
			w := httptest.NewRecorder()

			reclassifyFeedEvent(nil)(w, req)

			if w.Code != http.StatusBadRequest {
				t.Errorf("classification %q: status got %d, want %d", tc.classification, w.Code, http.StatusBadRequest)
			}
			var resp map[string]string
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("classification %q: parsing response: %v", tc.classification, err)
			}
			if resp["error"] == "" {
				t.Errorf("classification %q: expected non-empty error message", tc.classification)
			}
		})
	}
}

// TestReclassifyFeedEvent_ValidClassificationPassesValidation verifies that each of the six
// valid feed classifications passes the validation gate. With a nil Firestore client the handler
// proceeds past validation and panics on the first Firestore call; we recover from that panic
// and confirm it was not caused by a 400 validation error.
func TestReclassifyFeedEvent_ValidClassificationPassesValidation(t *testing.T) {
	validClassifications := []string{
		"ic_action",
		"ic_dialogue",
		"rules_question",
		"dm_narration",
		"dm_ruling",
		"table_talk",
	}
	for _, cls := range validClassifications {
		t.Run(cls, func(t *testing.T) {
			b, _ := json.Marshal(map[string]string{"new_classification": cls})
			req := httptest.NewRequest("PATCH", "/api/feed/f1/reclassify", bytes.NewReader(b))
			w := httptest.NewRecorder()

			// A nil Firestore client panics after validation passes. Recover to distinguish
			// that from a genuine 400 (which would indicate the classification was rejected).
			func() {
				defer func() { recover() }() //nolint:errcheck
				reclassifyFeedEvent(nil)(w, req)
			}()

			if w.Code == http.StatusBadRequest {
				var resp map[string]string
				json.Unmarshal(w.Body.Bytes(), &resp) //nolint:errcheck
				t.Errorf("classification %q should be valid but returned 400: %s", cls, resp["error"])
			}
		})
	}
}
