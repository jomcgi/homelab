package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// TestPaginationParams_Default verifies the default limit is 50 when no query params are set.
func TestPaginationParams_Default(t *testing.T) {
	req, _ := http.NewRequest("GET", "/", nil)
	limit, cursor := paginationParams(req)
	if limit != 50 {
		t.Errorf("default limit got %d, want 50", limit)
	}
	if cursor != "" {
		t.Errorf("default cursor got %q, want empty", cursor)
	}
}

// TestPaginationParams_ValidLimit verifies a valid limit within [1, 200] is accepted.
func TestPaginationParams_ValidLimit(t *testing.T) {
	req, _ := http.NewRequest("GET", "/?limit=100", nil)
	limit, _ := paginationParams(req)
	if limit != 100 {
		t.Errorf("limit got %d, want 100", limit)
	}
}

// TestPaginationParams_LimitMax verifies the maximum limit of 200 is accepted.
func TestPaginationParams_LimitMax(t *testing.T) {
	req, _ := http.NewRequest("GET", "/?limit=200", nil)
	limit, _ := paginationParams(req)
	if limit != 200 {
		t.Errorf("limit=200 got %d, want 200", limit)
	}
}

// TestPaginationParams_InvalidLimit verifies a non-numeric limit falls back to default 50.
func TestPaginationParams_InvalidLimit(t *testing.T) {
	req, _ := http.NewRequest("GET", "/?limit=abc", nil)
	limit, _ := paginationParams(req)
	if limit != 50 {
		t.Errorf("invalid limit should use default 50, got %d", limit)
	}
}

// TestPaginationParams_LimitTooHigh verifies a limit > 200 falls back to default 50.
func TestPaginationParams_LimitTooHigh(t *testing.T) {
	req, _ := http.NewRequest("GET", "/?limit=201", nil)
	limit, _ := paginationParams(req)
	if limit != 50 {
		t.Errorf("limit > 200 should use default 50, got %d", limit)
	}
}

// TestPaginationParams_LimitZero verifies a limit of 0 falls back to default 50.
func TestPaginationParams_LimitZero(t *testing.T) {
	req, _ := http.NewRequest("GET", "/?limit=0", nil)
	limit, _ := paginationParams(req)
	if limit != 50 {
		t.Errorf("limit=0 should use default 50, got %d", limit)
	}
}

// TestPaginationParams_Cursor verifies the cursor value is extracted correctly.
func TestPaginationParams_Cursor(t *testing.T) {
	req, _ := http.NewRequest("GET", "/?cursor=tok123", nil)
	_, cursor := paginationParams(req)
	if cursor != "tok123" {
		t.Errorf("cursor got %q, want %q", cursor, "tok123")
	}
}

// TestHttpError_WritesJSON verifies httpError returns a JSON error body with the correct status.
func TestHttpError_WritesJSON(t *testing.T) {
	w := httptest.NewRecorder()
	httpError(w, http.StatusBadRequest, "bad request")

	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want %d", w.Code, http.StatusBadRequest)
	}

	var body map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("parsing response body: %v", err)
	}
	if body["error"] != "bad request" {
		t.Errorf("error message got %q, want %q", body["error"], "bad request")
	}
}

// TestWriteJSON_SetsContentType verifies writeJSON sets the Content-Type header to application/json.
func TestWriteJSON_SetsContentType(t *testing.T) {
	w := httptest.NewRecorder()
	writeJSON(w, http.StatusOK, map[string]string{"key": "value"})

	ct := w.Header().Get("Content-Type")
	if ct != "application/json" {
		t.Errorf("Content-Type got %q, want %q", ct, "application/json")
	}
}

// TestWriteJSON_StatusCode verifies writeJSON writes the correct HTTP status code.
func TestWriteJSON_StatusCode(t *testing.T) {
	w := httptest.NewRecorder()
	writeJSON(w, http.StatusCreated, map[string]string{})

	if w.Code != http.StatusCreated {
		t.Errorf("status got %d, want %d", w.Code, http.StatusCreated)
	}
}

// TestWriteJSON_Body verifies writeJSON encodes the value as JSON in the response body.
func TestWriteJSON_Body(t *testing.T) {
	w := httptest.NewRecorder()
	writeJSON(w, http.StatusOK, map[string]any{"id": "abc", "count": 3})

	var result map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil {
		t.Fatalf("parsing body: %v", err)
	}
	if result["id"] != "abc" {
		t.Errorf("id got %v, want %q", result["id"], "abc")
	}
}

// TestNowTimestamp_IsUTC verifies nowTimestamp returns a time in the UTC location.
func TestNowTimestamp_IsUTC(t *testing.T) {
	ts := nowTimestamp()
	if ts.Location() != time.UTC {
		t.Errorf("nowTimestamp should be UTC, got location %v", ts.Location())
	}
}

// TestNowTimestamp_Recent verifies nowTimestamp returns a time close to now.
func TestNowTimestamp_Recent(t *testing.T) {
	before := time.Now().UTC().Add(-time.Second)
	ts := nowTimestamp()
	after := time.Now().UTC().Add(time.Second)

	if ts.Before(before) || ts.After(after) {
		t.Errorf("nowTimestamp %v is not within 1s of now", ts)
	}
}

// TestReadJSON_Valid verifies readJSON parses a valid JSON body into a struct.
func TestReadJSON_Valid(t *testing.T) {
	body := bytes.NewBufferString(`{"name":"test","value":42}`)
	req, _ := http.NewRequest("POST", "/", body)

	var result map[string]any
	if err := readJSON(req, &result); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result["name"] != "test" {
		t.Errorf("name got %v, want %q", result["name"], "test")
	}
	if result["value"] != float64(42) {
		t.Errorf("value got %v, want 42", result["value"])
	}
}

// TestReadJSON_Invalid verifies readJSON returns an error for malformed JSON.
func TestReadJSON_Invalid(t *testing.T) {
	body := bytes.NewBufferString(`not valid json`)
	req, _ := http.NewRequest("POST", "/", body)

	var result map[string]any
	if err := readJSON(req, &result); err == nil {
		t.Error("expected error for invalid JSON, got nil")
	}
}

// TestIsNotFound_RegularError verifies isNotFound returns false for a plain error.
func TestIsNotFound_RegularError(t *testing.T) {
	if isNotFound(errors.New("some error")) {
		t.Error("isNotFound should return false for a plain error")
	}
}

// TestIsNotFound_NilError verifies isNotFound returns false for a nil error.
func TestIsNotFound_NilError(t *testing.T) {
	if isNotFound(nil) {
		t.Error("isNotFound should return false for nil error")
	}
}
