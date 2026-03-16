package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestRegisterCampaignRoutes verifies all campaign routes can be registered without panicking.
// Passing nil for the Firestore client is safe because handlers only access Firestore when invoked.
func TestRegisterCampaignRoutes(t *testing.T) {
	mux := http.NewServeMux()
	registerCampaignRoutes(mux, nil)
}

// TestCreateCampaign_InvalidJSON verifies that a malformed request body returns 400.
func TestCreateCampaign_InvalidJSON(t *testing.T) {
	req := httptest.NewRequest("POST", "/api/campaigns", bytes.NewBufferString("not valid json"))
	w := httptest.NewRecorder()

	createCampaign(nil)(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
	}
}

// TestCreateCampaign_MissingName verifies that a campaign without a name returns 400.
func TestCreateCampaign_MissingName(t *testing.T) {
	cases := []struct {
		name string
		body map[string]any
	}{
		{"empty name", map[string]any{"name": "", "system": "dnd5e"}},
		{"name omitted", map[string]any{"system": "pf2e"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			b, _ := json.Marshal(tc.body)
			req := httptest.NewRequest("POST", "/api/campaigns", bytes.NewReader(b))
			w := httptest.NewRecorder()

			createCampaign(nil)(w, req)

			if w.Code != http.StatusBadRequest {
				t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
			}
			var resp map[string]string
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("parsing response body: %v", err)
			}
			if resp["error"] != "name is required" {
				t.Errorf("error got %q, want %q", resp["error"], "name is required")
			}
		})
	}
}

// TestCreateCampaign_EmptyBody verifies that an entirely empty body (no JSON at all) returns 400.
func TestCreateCampaign_EmptyBody(t *testing.T) {
	req := httptest.NewRequest("POST", "/api/campaigns", bytes.NewBufferString(""))
	w := httptest.NewRecorder()

	createCampaign(nil)(w, req)

	// Empty body is invalid JSON, expect 400.
	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
	}
}
