package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestRegisterCharacterRoutes verifies all character routes can be registered without panicking.
func TestRegisterCharacterRoutes(t *testing.T) {
	mux := http.NewServeMux()
	registerCharacterRoutes(mux, nil)
}

// TestCreateCharacter_InvalidJSON verifies that a malformed request body returns 400.
func TestCreateCharacter_InvalidJSON(t *testing.T) {
	req := httptest.NewRequest("POST", "/api/campaigns/c1/characters", bytes.NewBufferString("not valid json"))
	w := httptest.NewRecorder()

	createCharacter(nil)(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
	}
}

// TestCreateCharacter_MissingName verifies that a character without a name returns 400.
func TestCreateCharacter_MissingName(t *testing.T) {
	cases := []struct {
		label string
		body  map[string]any
	}{
		{"empty name", map[string]any{"name": "", "class": "Fighter"}},
		{"name omitted", map[string]any{"class": "Wizard", "level": 5}},
	}
	for _, tc := range cases {
		t.Run(tc.label, func(t *testing.T) {
			b, _ := json.Marshal(tc.body)
			req := httptest.NewRequest("POST", "/api/campaigns/c1/characters", bytes.NewReader(b))
			w := httptest.NewRecorder()

			createCharacter(nil)(w, req)

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

// TestUpdateCharacter_InvalidJSON verifies that a malformed request body returns 400.
func TestUpdateCharacter_InvalidJSON(t *testing.T) {
	req := httptest.NewRequest("PATCH", "/api/characters/c1", bytes.NewBufferString("not valid json"))
	w := httptest.NewRecorder()

	updateCharacter(nil)(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
	}
}

// TestUpdateCharacter_NoValidFields verifies that a request with no allowed fields returns 400.
func TestUpdateCharacter_NoValidFields(t *testing.T) {
	cases := []struct {
		label string
		body  map[string]any
	}{
		{"empty body", map[string]any{}},
		{"only unknown fields", map[string]any{"unknown_field": "val", "also_bad": 42}},
		{"disallowed field", map[string]any{"campaign_id": "c1", "user_id": "u1"}},
	}
	for _, tc := range cases {
		t.Run(tc.label, func(t *testing.T) {
			b, _ := json.Marshal(tc.body)
			req := httptest.NewRequest("PATCH", "/api/characters/c1", bytes.NewReader(b))
			w := httptest.NewRecorder()

			updateCharacter(nil)(w, req)

			if w.Code != http.StatusBadRequest {
				t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
			}
			var resp map[string]string
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("parsing response body: %v", err)
			}
			if resp["error"] != "no valid fields to update" {
				t.Errorf("error got %q, want %q", resp["error"], "no valid fields to update")
			}
		})
	}
}

// TestUpdateCharacter_AllowedFields verifies that each individually allowed field passes validation.
// With a nil Firestore client the handler will panic/error after passing validation,
// so we use recover to detect that validation succeeded (i.e. no 400 was returned).
func TestUpdateCharacter_AllowedFields(t *testing.T) {
	allowedFields := []string{
		"name", "race", "class", "level",
		"hp", "max_hp", "ac", "abilities",
		"conditions", "spell_slots", "color",
	}
	for _, field := range allowedFields {
		t.Run(field, func(t *testing.T) {
			body := map[string]any{field: "somevalue"}
			b, _ := json.Marshal(body)
			req := httptest.NewRequest("PATCH", "/api/characters/c1", bytes.NewReader(b))
			w := httptest.NewRecorder()

			// With nil Firestore, the handler panics after passing validation.
			// A panic (or non-400 response) means validation accepted the field.
			func() {
				defer func() { recover() }() //nolint:errcheck
				updateCharacter(nil)(w, req)
			}()

			if w.Code == http.StatusBadRequest {
				var resp map[string]string
				json.Unmarshal(w.Body.Bytes(), &resp) //nolint:errcheck
				t.Errorf("field %q should be allowed but got 400: %s", field, resp["error"])
			}
		})
	}
}

// TestCreateLore_InvalidJSON verifies that a malformed request body returns 400.
func TestCreateLore_InvalidJSON(t *testing.T) {
	req := httptest.NewRequest("POST", "/api/characters/c1/lore", bytes.NewBufferString("not valid json"))
	w := httptest.NewRecorder()

	createLore(nil)(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
	}
}

// TestCreateLore_MissingFact verifies that a lore entry without a fact returns 400.
func TestCreateLore_MissingFact(t *testing.T) {
	cases := []struct {
		label string
		body  map[string]any
	}{
		{"empty fact", map[string]any{"fact": "", "source": "session1"}},
		{"fact omitted", map[string]any{"source": "session1"}},
	}
	for _, tc := range cases {
		t.Run(tc.label, func(t *testing.T) {
			b, _ := json.Marshal(tc.body)
			req := httptest.NewRequest("POST", "/api/characters/c1/lore", bytes.NewReader(b))
			w := httptest.NewRecorder()

			createLore(nil)(w, req)

			if w.Code != http.StatusBadRequest {
				t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
			}
			var resp map[string]string
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("parsing response body: %v", err)
			}
			if resp["error"] != "fact is required" {
				t.Errorf("error got %q, want %q", resp["error"], "fact is required")
			}
		})
	}
}
