package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

// setupCorruptData writes an invalid JSON file to dataDir/data.json so that
// loadData returns an error, allowing handlers' 500 error paths to be exercised.
func setupCorruptData(t *testing.T, dir string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, "data.json"), []byte("{corrupt json}"), 0o644); err != nil {
		t.Fatalf("setupCorruptData: %v", err)
	}
}

// TestLoadDataReturnsErrorOnInvalidJSON verifies that loadData returns an error
// when data.json exists but contains invalid JSON (e.g., due to file corruption).
// This covers the json.Unmarshal error path that the missing-file test does not.
func TestLoadDataReturnsErrorOnInvalidJSON(t *testing.T) {
	dir := t.TempDir()
	origDataDir := dataDir
	dataDir = dir
	defer func() { dataDir = origDataDir }()

	if err := os.WriteFile(filepath.Join(dir, "data.json"), []byte("{not valid json}"), 0o644); err != nil {
		t.Fatalf("setup: write corrupt data.json: %v", err)
	}

	_, err := loadData()
	if err == nil {
		t.Error("expected error when data.json contains invalid JSON, got nil")
	}
}

// TestHandleWeeklyInternalServerError verifies that handleWeekly returns HTTP 500
// when loadData fails (e.g., due to a corrupted data.json file).
func TestHandleWeeklyInternalServerError(t *testing.T) {
	dir, _ := setupDirs(t)
	setupCorruptData(t, dir)

	req := httptest.NewRequest(http.MethodGet, "/api/weekly", nil)
	w := httptest.NewRecorder()
	handleWeekly(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 when loadData fails, got %d: %s", w.Code, w.Body.String())
	}
}

// TestHandleDailyInternalServerError verifies that handleDaily returns HTTP 500
// when loadData fails (e.g., due to a corrupted data.json file).
func TestHandleDailyInternalServerError(t *testing.T) {
	dir, _ := setupDirs(t)
	setupCorruptData(t, dir)

	req := httptest.NewRequest(http.MethodGet, "/api/daily", nil)
	w := httptest.NewRecorder()
	handleDaily(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 when loadData fails, got %d: %s", w.Code, w.Body.String())
	}
}

// TestHandleTodoGetInternalServerError verifies that handleTodo (GET) returns
// HTTP 500 when loadData fails due to a corrupted data.json file.
func TestHandleTodoGetInternalServerError(t *testing.T) {
	dir, _ := setupDirs(t)
	setupCorruptData(t, dir)

	req := httptest.NewRequest(http.MethodGet, "/api/todo", nil)
	w := httptest.NewRecorder()
	handleTodo(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 when loadData fails, got %d: %s", w.Code, w.Body.String())
	}
}
