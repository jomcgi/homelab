package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// setupDirs sets dataDir and staticDir to temp directories and returns a cleanup func.
// The static dir is pre-populated with a minimal index.html containing the placeholder.
func setupDirs(t *testing.T) (string, string) {
	t.Helper()
	data := t.TempDir()
	static := t.TempDir()

	// Create minimal index.html with the expected placeholder so rebuildSite() works.
	placeholder := `/*DATES_PLACEHOLDER*/["2025-01-28", "2025-01-29", "2025-01-30"]/*END_PLACEHOLDER*/`
	html := fmt.Sprintf("<html><body>%s</body></html>", placeholder)
	if err := os.WriteFile(filepath.Join(static, "index.html"), []byte(html), 0o644); err != nil {
		t.Fatalf("setup: write index.html: %v", err)
	}

	origData := dataDir
	origStatic := staticDir
	dataDir = data
	staticDir = static
	t.Cleanup(func() {
		dataDir = origData
		staticDir = origStatic
	})

	return data, static
}

// writeTodoData is a helper that writes a TodoData struct to dataDir/data.json.
func writeTodoData(t *testing.T, dir string, d TodoData) {
	t.Helper()
	b, err := json.MarshalIndent(d, "", "  ")
	if err != nil {
		t.Fatalf("writeTodoData marshal: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "data.json"), b, 0o644); err != nil {
		t.Fatalf("writeTodoData write: %v", err)
	}
}

// --- handleTodo ---

func TestHandleTodoGet(t *testing.T) {
	dir, _ := setupDirs(t)

	want := TodoData{
		Weekly: Task{Task: "plan sprint", Done: false},
		Daily:  []Task{{Task: "standup", Done: true}, {Task: "review", Done: false}},
	}
	writeTodoData(t, dir, want)

	req := httptest.NewRequest(http.MethodGet, "/api/todo", nil)
	w := httptest.NewRecorder()
	handleTodo(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var got TodoData
	if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if got.Weekly.Task != want.Weekly.Task {
		t.Errorf("weekly task: got %q, want %q", got.Weekly.Task, want.Weekly.Task)
	}
	if len(got.Daily) != len(want.Daily) {
		t.Errorf("daily len: got %d, want %d", len(got.Daily), len(want.Daily))
	}
}

func TestHandleTodoPut(t *testing.T) {
	_, _ = setupDirs(t)

	payload := TodoData{
		Weekly: Task{Task: "weekly goal", Done: false},
		Daily:  []Task{{Task: "task1", Done: true}},
	}
	b, _ := json.Marshal(payload)

	req := httptest.NewRequest(http.MethodPut, "/api/todo", strings.NewReader(string(b)))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	handleTodo(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestHandleTodoPutInvalidJSON(t *testing.T) {
	_, _ = setupDirs(t)

	req := httptest.NewRequest(http.MethodPut, "/api/todo", strings.NewReader("{invalid json"))
	w := httptest.NewRecorder()
	handleTodo(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleTodoDeleteReturns405(t *testing.T) {
	_, _ = setupDirs(t)

	req := httptest.NewRequest(http.MethodDelete, "/api/todo", nil)
	w := httptest.NewRecorder()
	handleTodo(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}

// --- handleWeekly ---

func TestHandleWeeklyGet(t *testing.T) {
	dir, _ := setupDirs(t)

	stored := TodoData{
		Weekly: Task{Task: "ship feature", Done: true},
		Daily:  []Task{},
	}
	writeTodoData(t, dir, stored)

	req := httptest.NewRequest(http.MethodGet, "/api/weekly", nil)
	w := httptest.NewRecorder()
	handleWeekly(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var got Task
	if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got.Task != stored.Weekly.Task {
		t.Errorf("task: got %q, want %q", got.Task, stored.Weekly.Task)
	}
	if got.Done != stored.Weekly.Done {
		t.Errorf("done: got %v, want %v", got.Done, stored.Weekly.Done)
	}
}

func TestHandleWeeklyPostReturns405(t *testing.T) {
	_, _ = setupDirs(t)

	req := httptest.NewRequest(http.MethodPost, "/api/weekly", nil)
	w := httptest.NewRecorder()
	handleWeekly(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}

// --- handleDaily ---

func TestHandleDailyGet(t *testing.T) {
	dir, _ := setupDirs(t)

	stored := TodoData{
		Daily: []Task{
			{Task: "morning workout", Done: false},
			{Task: "read", Done: true},
			{Task: "write", Done: false},
		},
	}
	writeTodoData(t, dir, stored)

	req := httptest.NewRequest(http.MethodGet, "/api/daily", nil)
	w := httptest.NewRecorder()
	handleDaily(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var got []Task
	if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(got) != len(stored.Daily) {
		t.Errorf("daily len: got %d, want %d", len(got), len(stored.Daily))
	}
	if got[0].Task != stored.Daily[0].Task {
		t.Errorf("daily[0]: got %q, want %q", got[0].Task, stored.Daily[0].Task)
	}
}

func TestHandleDailyPostReturns405(t *testing.T) {
	_, _ = setupDirs(t)

	req := httptest.NewRequest(http.MethodPost, "/api/daily", nil)
	w := httptest.NewRecorder()
	handleDaily(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}

// --- handleResetDaily ---

func TestHandleResetDailyPost(t *testing.T) {
	dir, _ := setupDirs(t)

	// Seed some data so archiveDay has something to write
	writeTodoData(t, dir, TodoData{
		Weekly: Task{Task: "w", Done: false},
		Daily:  []Task{{Task: "d1", Done: true}, {Task: "d2", Done: false}, {Task: "d3", Done: false}},
	})

	req := httptest.NewRequest(http.MethodPost, "/api/reset/daily", nil)
	w := httptest.NewRecorder()
	handleResetDaily(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestHandleResetDailyGetReturns405(t *testing.T) {
	_, _ = setupDirs(t)

	req := httptest.NewRequest(http.MethodGet, "/api/reset/daily", nil)
	w := httptest.NewRecorder()
	handleResetDaily(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}

// --- handleResetWeekly ---

func TestHandleResetWeeklyPost(t *testing.T) {
	dir, _ := setupDirs(t)

	writeTodoData(t, dir, TodoData{
		Weekly: Task{Task: "weekly goal", Done: true},
		Daily:  []Task{{Task: "d1", Done: true}, {Task: "d2", Done: false}, {}},
	})

	req := httptest.NewRequest(http.MethodPost, "/api/reset/weekly", nil)
	w := httptest.NewRecorder()
	handleResetWeekly(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
}

func TestHandleResetWeeklyGetReturns405(t *testing.T) {
	_, _ = setupDirs(t)

	req := httptest.NewRequest(http.MethodGet, "/api/reset/weekly", nil)
	w := httptest.NewRecorder()
	handleResetWeekly(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}

// --- handleDates ---

func TestHandleDatesGetContainsToday(t *testing.T) {
	_, _ = setupDirs(t)

	req := httptest.NewRequest(http.MethodGet, "/api/dates", nil)
	w := httptest.NewRecorder()
	handleDates(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var dates []string
	if err := json.NewDecoder(w.Body).Decode(&dates); err != nil {
		t.Fatalf("decode: %v", err)
	}

	today := time.Now().Format("2006-01-02")
	found := false
	for _, d := range dates {
		if d == today {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("today (%s) not found in dates: %v", today, dates)
	}
}

// --- loadData ---

func TestLoadDataMissingFileReturnsDefault(t *testing.T) {
	dir := t.TempDir()
	origDataDir := dataDir
	dataDir = dir
	defer func() { dataDir = origDataDir }()

	data, err := loadData()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(data.Daily) != 3 {
		t.Errorf("expected 3 daily tasks, got %d", len(data.Daily))
	}
	// All three should be empty structs
	for i, task := range data.Daily {
		if task.Task != "" || task.Done != false {
			t.Errorf("daily[%d] should be empty, got %+v", i, task)
		}
	}
}

// --- saveData + loadData roundtrip ---

func TestSaveAndLoadRoundtrip(t *testing.T) {
	dir := t.TempDir()
	origDataDir := dataDir
	dataDir = dir
	defer func() { dataDir = origDataDir }()

	want := TodoData{
		Weekly: Task{Task: "weekly task", Done: true},
		Daily: []Task{
			{Task: "a", Done: false},
			{Task: "b", Done: true},
			{Task: "c", Done: false},
		},
	}

	if err := saveData(want); err != nil {
		t.Fatalf("saveData: %v", err)
	}

	got, err := loadData()
	if err != nil {
		t.Fatalf("loadData: %v", err)
	}

	if got.Weekly.Task != want.Weekly.Task || got.Weekly.Done != want.Weekly.Done {
		t.Errorf("weekly: got %+v, want %+v", got.Weekly, want.Weekly)
	}
	if len(got.Daily) != len(want.Daily) {
		t.Fatalf("daily len: got %d, want %d", len(got.Daily), len(want.Daily))
	}
	for i := range want.Daily {
		if got.Daily[i] != want.Daily[i] {
			t.Errorf("daily[%d]: got %+v, want %+v", i, got.Daily[i], want.Daily[i])
		}
	}
}

// --- archiveDay ---

func TestArchiveDayMarkdownFormat(t *testing.T) {
	dir := t.TempDir()
	origDataDir := dataDir
	dataDir = dir
	defer func() { dataDir = origDataDir }()

	data := TodoData{
		Weekly: Task{Task: "finish project", Done: false},
		Daily: []Task{
			{Task: "write tests", Done: true},
			{Task: "code review", Done: false},
			{Task: "", Done: false}, // empty task — should not appear
		},
	}

	if err := archiveDay(data); err != nil {
		t.Fatalf("archiveDay: %v", err)
	}

	// Find the written file
	now := time.Now()
	year := now.Format("2006")
	month := now.Format("01")
	day := now.Day()
	path := filepath.Join(dir, year, month, fmt.Sprintf("%d.md", day))

	contents, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read archive file %s: %v", path, err)
	}

	body := string(contents)

	// Check header line
	if !strings.Contains(body, "# ") {
		t.Error("expected markdown H1 header")
	}

	// Check ## Weekly section
	if !strings.Contains(body, "## Weekly") {
		t.Error("expected '## Weekly' section")
	}
	if !strings.Contains(body, "finish project") {
		t.Error("expected weekly task text in output")
	}

	// Check ## Daily section
	if !strings.Contains(body, "## Daily") {
		t.Error("expected '## Daily' section")
	}
	if !strings.Contains(body, "- [x] write tests") {
		t.Error("expected done task '- [x] write tests'")
	}
	if !strings.Contains(body, "- [ ] code review") {
		t.Error("expected undone task '- [ ] code review'")
	}
	// Empty task should not appear
	if strings.Contains(body, "- [ ] \n") || strings.Contains(body, "- [x] \n") {
		t.Error("empty task should not appear in archive")
	}
}

func TestArchiveDayNoneWhenNoWeeklyTask(t *testing.T) {
	dir := t.TempDir()
	origDataDir := dataDir
	dataDir = dir
	defer func() { dataDir = origDataDir }()

	data := TodoData{
		Weekly: Task{Task: "", Done: false},
		Daily:  []Task{},
	}

	if err := archiveDay(data); err != nil {
		t.Fatalf("archiveDay: %v", err)
	}

	now := time.Now()
	path := filepath.Join(dir, now.Format("2006"), now.Format("01"), fmt.Sprintf("%d.md", now.Day()))
	contents, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read file: %v", err)
	}
	if !strings.Contains(string(contents), "(none)") {
		t.Error("expected '(none)' for empty weekly task")
	}
}

// --- collectDates ---

func TestCollectDatesRollingWindow(t *testing.T) {
	dir := t.TempDir()
	origDataDir := dataDir
	origWindow := rollingWindowDays
	dataDir = dir
	rollingWindowDays = 14
	defer func() {
		dataDir = origDataDir
		rollingWindowDays = origWindow
	}()

	now := time.Now()

	// File within the window (5 days ago)
	recentDate := now.AddDate(0, 0, -5)
	recentYear := recentDate.Format("2006")
	recentMonth := recentDate.Format("01")
	recentDay := recentDate.Day()
	recentDir := filepath.Join(dir, recentYear, recentMonth)
	if err := os.MkdirAll(recentDir, 0o755); err != nil {
		t.Fatal(err)
	}
	recentFile := filepath.Join(recentDir, fmt.Sprintf("%d.md", recentDay))
	if err := os.WriteFile(recentFile, []byte("# test\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	// File outside the window (20 days ago)
	oldDate := now.AddDate(0, 0, -20)
	oldYear := oldDate.Format("2006")
	oldMonth := oldDate.Format("01")
	oldDay := oldDate.Day()
	oldDir := filepath.Join(dir, oldYear, oldMonth)
	if err := os.MkdirAll(oldDir, 0o755); err != nil {
		t.Fatal(err)
	}
	oldFile := filepath.Join(oldDir, fmt.Sprintf("%d.md", oldDay))
	if err := os.WriteFile(oldFile, []byte("# old\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	dates, err := collectDates()
	if err != nil {
		t.Fatalf("collectDates: %v", err)
	}

	// Build expected recent date string
	recentDayStr := fmt.Sprintf("%02d", recentDay)
	recentDateStr := fmt.Sprintf("%s-%s-%s", recentYear, recentMonth, recentDayStr)

	oldDayStr := fmt.Sprintf("%02d", oldDay)
	oldDateStr := fmt.Sprintf("%s-%s-%s", oldYear, oldMonth, oldDayStr)

	foundRecent := false
	foundOld := false
	for _, d := range dates {
		if d == recentDateStr {
			foundRecent = true
		}
		if d == oldDateStr {
			foundOld = true
		}
	}

	if !foundRecent {
		t.Errorf("expected recent date %s in results %v", recentDateStr, dates)
	}
	if foundOld {
		t.Errorf("old date %s should be excluded from results %v", oldDateStr, dates)
	}
}

func TestCollectDatesAlwaysAppendsTodayEvenWithNoFiles(t *testing.T) {
	dir := t.TempDir()
	origDataDir := dataDir
	dataDir = dir
	defer func() { dataDir = origDataDir }()

	dates, err := collectDates()
	if err != nil {
		t.Fatalf("collectDates: %v", err)
	}

	today := time.Now().Format("2006-01-02")
	if len(dates) == 0 {
		t.Fatal("expected at least one date (today)")
	}
	last := dates[len(dates)-1]
	if last != today {
		t.Errorf("last date: got %q, want today %q", last, today)
	}
}

// --- getEnv ---

func TestGetEnvReturnsFallbackWhenUnset(t *testing.T) {
	key := "TEST_GETENV_UNSET_XYZ"
	os.Unsetenv(key)
	got := getEnv(key, "default_value")
	if got != "default_value" {
		t.Errorf("expected fallback %q, got %q", "default_value", got)
	}
}

func TestGetEnvReturnsEnvVarWhenSet(t *testing.T) {
	key := "TEST_GETENV_SET_XYZ"
	t.Setenv(key, "from_env")
	got := getEnv(key, "default_value")
	if got != "from_env" {
		t.Errorf("expected %q, got %q", "from_env", got)
	}
}

func TestGetEnvReturnsFallbackWhenSetToEmpty(t *testing.T) {
	key := "TEST_GETENV_EMPTY_XYZ"
	t.Setenv(key, "")
	got := getEnv(key, "fallback")
	if got != "fallback" {
		t.Errorf("empty env var should return fallback, got %q", got)
	}
}

// --- rebuildSite ---

func TestRebuildSiteReplacesPlaceholderAndWritesOutput(t *testing.T) {
	dataD, _ := setupDirs(t)

	if err := rebuildSite(); err != nil {
		t.Fatalf("rebuildSite: %v", err)
	}

	outPath := filepath.Join(dataD, "public", "index.html")
	contents, err := os.ReadFile(outPath)
	if err != nil {
		t.Fatalf("read output index.html: %v", err)
	}

	body := string(contents)
	// Placeholder must be gone
	if strings.Contains(body, "DATES_PLACEHOLDER") {
		t.Error("DATES_PLACEHOLDER should have been replaced")
	}
	// Must still be valid HTML with the wrapper tags
	if !strings.Contains(body, "<html>") {
		t.Error("expected <html> tag in output")
	}
	// Today's date must be injected
	today := time.Now().Format("2006-01-02")
	if !strings.Contains(body, today) {
		t.Errorf("expected today %s in rebuilt index.html, got:\n%s", today, body)
	}
}

func TestRebuildSiteCopiesDataJSON(t *testing.T) {
	dataD, _ := setupDirs(t)

	want := TodoData{
		Weekly: Task{Task: "copy test", Done: false},
		Daily:  []Task{{Task: "d1", Done: true}, {}, {}},
	}
	writeTodoData(t, dataD, want)

	if err := rebuildSite(); err != nil {
		t.Fatalf("rebuildSite: %v", err)
	}

	outPath := filepath.Join(dataD, "public", "data.json")
	raw, err := os.ReadFile(outPath)
	if err != nil {
		t.Fatalf("read public/data.json: %v", err)
	}

	var got TodoData
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatalf("unmarshal public/data.json: %v", err)
	}
	if got.Weekly.Task != want.Weekly.Task {
		t.Errorf("weekly task: got %q, want %q", got.Weekly.Task, want.Weekly.Task)
	}
}

func TestRebuildSiteErrorWhenIndexHTMLMissing(t *testing.T) {
	dataD := t.TempDir()
	staticD := t.TempDir() // no index.html written

	origData := dataDir
	origStatic := staticDir
	dataDir = dataD
	staticDir = staticD
	defer func() {
		dataDir = origData
		staticDir = origStatic
	}()

	if err := rebuildSite(); err == nil {
		t.Error("expected error when index.html is missing, got nil")
	}
}

func TestRebuildSiteCopiesMarkdownFilesWithinWindow(t *testing.T) {
	dataD, _ := setupDirs(t)
	origWindow := rollingWindowDays
	rollingWindowDays = 14
	defer func() { rollingWindowDays = origWindow }()

	// Write a recent markdown file (3 days ago)
	recent := time.Now().AddDate(0, 0, -3)
	recentDir := filepath.Join(dataD, recent.Format("2006"), recent.Format("01"))
	if err := os.MkdirAll(recentDir, 0o755); err != nil {
		t.Fatal(err)
	}
	recentFile := filepath.Join(recentDir, fmt.Sprintf("%d.md", recent.Day()))
	if err := os.WriteFile(recentFile, []byte("# recent\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	// Write an old markdown file (20 days ago) — outside rolling window
	old := time.Now().AddDate(0, 0, -20)
	oldDir := filepath.Join(dataD, old.Format("2006"), old.Format("01"))
	if err := os.MkdirAll(oldDir, 0o755); err != nil {
		t.Fatal(err)
	}
	oldFile := filepath.Join(oldDir, fmt.Sprintf("%d.md", old.Day()))
	if err := os.WriteFile(oldFile, []byte("# old\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := rebuildSite(); err != nil {
		t.Fatalf("rebuildSite: %v", err)
	}

	// Recent file should be in public/
	recentRel := fmt.Sprintf("%s/%s/%d.md", recent.Format("2006"), recent.Format("01"), recent.Day())
	recentPub := filepath.Join(dataD, "public", recentRel)
	if _, err := os.Stat(recentPub); err != nil {
		t.Errorf("recent md not copied to public: %v", err)
	}

	// Old file must NOT be in public/
	oldRel := fmt.Sprintf("%s/%s/%d.md", old.Format("2006"), old.Format("01"), old.Day())
	oldPub := filepath.Join(dataD, "public", oldRel)
	if _, err := os.Stat(oldPub); err == nil {
		t.Errorf("old md outside rolling window should not be in public/")
	}
}

// --- resetDaily ---

func TestResetDailyArchivesAndClearsDailyTasks(t *testing.T) {
	dataD, _ := setupDirs(t)

	initial := TodoData{
		Weekly: Task{Task: "weekly objective", Done: false},
		Daily: []Task{
			{Task: "task A", Done: true},
			{Task: "task B", Done: false},
			{Task: "task C", Done: false},
		},
	}
	writeTodoData(t, dataD, initial)

	if err := resetDaily(); err != nil {
		t.Fatalf("resetDaily: %v", err)
	}

	// data.json should have 3 empty daily slots
	loaded, err := loadData()
	if err != nil {
		t.Fatalf("loadData after resetDaily: %v", err)
	}
	if len(loaded.Daily) != 3 {
		t.Errorf("expected 3 daily tasks, got %d", len(loaded.Daily))
	}
	for i, task := range loaded.Daily {
		if task.Task != "" || task.Done {
			t.Errorf("daily[%d] should be empty after reset, got %+v", i, task)
		}
	}

	// Weekly goal is preserved
	if loaded.Weekly.Task != initial.Weekly.Task {
		t.Errorf("weekly task should be preserved: got %q, want %q", loaded.Weekly.Task, initial.Weekly.Task)
	}
}

func TestResetDailyCreatesArchiveFile(t *testing.T) {
	dataD, _ := setupDirs(t)

	writeTodoData(t, dataD, TodoData{
		Weekly: Task{Task: "weekly", Done: false},
		Daily:  []Task{{Task: "d1", Done: true}, {Task: "d2", Done: false}, {}},
	})

	if err := resetDaily(); err != nil {
		t.Fatalf("resetDaily: %v", err)
	}

	// An archive markdown file for today must exist
	now := time.Now()
	archivePath := filepath.Join(dataD, now.Format("2006"), now.Format("01"), fmt.Sprintf("%d.md", now.Day()))
	if _, err := os.Stat(archivePath); err != nil {
		t.Errorf("archive file not found at %s: %v", archivePath, err)
	}
}

func TestResetDailyRebuildsSite(t *testing.T) {
	dataD, _ := setupDirs(t)
	writeTodoData(t, dataD, TodoData{
		Weekly: Task{Task: "w", Done: false},
		Daily:  []Task{{Task: "d1", Done: false}, {}, {}},
	})

	if err := resetDaily(); err != nil {
		t.Fatalf("resetDaily: %v", err)
	}

	// public/index.html must exist (site was rebuilt)
	pubIndex := filepath.Join(dataD, "public", "index.html")
	if _, err := os.Stat(pubIndex); err != nil {
		t.Errorf("public/index.html not found after resetDaily: %v", err)
	}
}

// --- resetWeekly ---

func TestResetWeeklyArchivesAndClearsAll(t *testing.T) {
	dataD, _ := setupDirs(t)

	initial := TodoData{
		Weekly: Task{Task: "big weekly goal", Done: true},
		Daily: []Task{
			{Task: "day task 1", Done: true},
			{Task: "day task 2", Done: false},
			{},
		},
	}
	writeTodoData(t, dataD, initial)

	if err := resetWeekly(); err != nil {
		t.Fatalf("resetWeekly: %v", err)
	}

	loaded, err := loadData()
	if err != nil {
		t.Fatalf("loadData after resetWeekly: %v", err)
	}

	// Weekly task must be cleared
	if loaded.Weekly.Task != "" || loaded.Weekly.Done {
		t.Errorf("weekly should be cleared after resetWeekly, got %+v", loaded.Weekly)
	}

	// Daily must be 3 empty slots
	if len(loaded.Daily) != 3 {
		t.Errorf("expected 3 daily tasks, got %d", len(loaded.Daily))
	}
	for i, task := range loaded.Daily {
		if task.Task != "" || task.Done {
			t.Errorf("daily[%d] should be empty after weekly reset, got %+v", i, task)
		}
	}
}

func TestResetWeeklyCreatesArchiveFile(t *testing.T) {
	dataD, _ := setupDirs(t)

	writeTodoData(t, dataD, TodoData{
		Weekly: Task{Task: "finish sprint", Done: true},
		Daily:  []Task{{Task: "d1", Done: true}, {Task: "d2", Done: false}, {}},
	})

	if err := resetWeekly(); err != nil {
		t.Fatalf("resetWeekly: %v", err)
	}

	now := time.Now()
	archivePath := filepath.Join(dataD, now.Format("2006"), now.Format("01"), fmt.Sprintf("%d.md", now.Day()))
	if _, err := os.Stat(archivePath); err != nil {
		t.Errorf("archive file not found at %s: %v", archivePath, err)
	}
}

func TestResetWeeklyRebuildsSite(t *testing.T) {
	dataD, _ := setupDirs(t)
	writeTodoData(t, dataD, TodoData{
		Weekly: Task{Task: "sprint goal", Done: false},
		Daily:  []Task{{Task: "d1", Done: false}, {}, {}},
	})

	if err := resetWeekly(); err != nil {
		t.Fatalf("resetWeekly: %v", err)
	}

	pubIndex := filepath.Join(dataD, "public", "index.html")
	if _, err := os.Stat(pubIndex); err != nil {
		t.Errorf("public/index.html not found after resetWeekly: %v", err)
	}
}

// --- handleHealthz ---

// TestHandleHealthzReturns200 verifies the /healthz endpoint returns HTTP 200.
func TestHandleHealthzReturns200(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	w := httptest.NewRecorder()
	handleHealthz(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
}

// TestHandleHealthzPostAlsoReturns200 verifies any HTTP method is accepted by /healthz.
// The handler unconditionally writes 200, so method doesn't matter.
func TestHandleHealthzPostAlsoReturns200(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/healthz", nil)
	w := httptest.NewRecorder()
	handleHealthz(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
}

// --- handleRoot ---

// TestHandleRootServesEditHTML verifies that GET / serves the contents of edit.html.
func TestHandleRootServesEditHTML(t *testing.T) {
	_, static := setupDirs(t)

	editContent := "<html><body>admin edit page</body></html>"
	if err := os.WriteFile(filepath.Join(static, "edit.html"), []byte(editContent), 0o644); err != nil {
		t.Fatalf("write edit.html: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	handleRoot(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if !strings.Contains(w.Body.String(), "admin edit page") {
		t.Errorf("expected edit.html body in response, got: %s", w.Body.String())
	}
}

// TestHandleRootReturns404ForSubpath verifies that any path other than "/"
// results in a 404 Not Found response.
func TestHandleRootReturns404ForSubpath(t *testing.T) {
	_, _ = setupDirs(t)

	for _, path := range []string{"/other", "/api/todo", "/healthz"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		w := httptest.NewRecorder()
		handleRoot(w, req)

		if w.Code != http.StatusNotFound {
			t.Errorf("path %s: expected 404, got %d", path, w.Code)
		}
	}
}

// --- runSchedulerLoop ---

// TestSchedulerLoopCallsWeeklyOnSaturday verifies that runSchedulerLoop invokes
// weeklyFn (not dailyFn) when nowFn reports the current time as a Saturday.
func TestSchedulerLoopCallsWeeklyOnSaturday(t *testing.T) {
	// Saturday: 2026-03-21 is a known Saturday.
	saturday := time.Date(2026, 3, 21, 0, 0, 1, 0, time.UTC)

	weeklyCalled := make(chan struct{}, 1)
	// block keeps the goroutine parked after its first reset call so the loop
	// doesn't spin indefinitely with the no-op sleepFn.
	block := make(chan struct{})

	weeklyFn := func() error {
		weeklyCalled <- struct{}{}
		<-block
		return nil
	}
	dailyFn := func() error {
		t.Error("dailyFn should not be called on Saturday")
		<-block
		return nil
	}

	go runSchedulerLoop(
		time.UTC,
		func() time.Time { return saturday },
		func(time.Duration) {}, // no-op: skip the ~24h midnight sleep
		weeklyFn,
		dailyFn,
	)

	select {
	case <-weeklyCalled:
		// success — weekly reset was triggered
	case <-time.After(2 * time.Second):
		t.Fatal("runSchedulerLoop did not call weeklyFn within timeout")
	}

	close(block) // release the blocked goroutine so it can exit
}

// TestSchedulerLoopCallsDailyOnNonSaturday verifies that runSchedulerLoop invokes
// dailyFn (not weeklyFn) when nowFn reports the current time as a non-Saturday.
func TestSchedulerLoopCallsDailyOnNonSaturday(t *testing.T) {
	// Wednesday: 2026-03-18 is a known Wednesday.
	wednesday := time.Date(2026, 3, 18, 0, 0, 1, 0, time.UTC)

	dailyCalled := make(chan struct{}, 1)
	block := make(chan struct{})

	weeklyFn := func() error {
		t.Error("weeklyFn should not be called on a non-Saturday")
		<-block
		return nil
	}
	dailyFn := func() error {
		dailyCalled <- struct{}{}
		<-block
		return nil
	}

	go runSchedulerLoop(
		time.UTC,
		func() time.Time { return wednesday },
		func(time.Duration) {}, // no-op
		weeklyFn,
		dailyFn,
	)

	select {
	case <-dailyCalled:
		// success — daily reset was triggered
	case <-time.After(2 * time.Second):
		t.Fatal("runSchedulerLoop did not call dailyFn within timeout")
	}

	close(block)
}

// TestSchedulerLoopLogsResetErrorAndContinues verifies that when a reset function
// returns an error, the scheduler logs the failure and continues (does not crash).
// We confirm it by checking that a second tick also fires correctly.
func TestSchedulerLoopLogsResetErrorAndContinues(t *testing.T) {
	// Use a Wednesday so dailyFn is called each tick.
	wednesday := time.Date(2026, 3, 18, 0, 0, 1, 0, time.UTC)

	callCount := 0
	secondCall := make(chan struct{}, 1)
	block := make(chan struct{})

	dailyFn := func() error {
		callCount++
		if callCount == 1 {
			return errors.New("simulated reset failure")
		}
		secondCall <- struct{}{}
		<-block
		return nil
	}

	go runSchedulerLoop(
		time.UTC,
		func() time.Time { return wednesday },
		func(time.Duration) {}, // no-op sleep: loop continues immediately
		func() error { return nil },
		dailyFn,
	)

	select {
	case <-secondCall:
		// scheduler continued after the first error
	case <-time.After(2 * time.Second):
		t.Fatal("scheduler stopped after reset error instead of continuing")
	}

	close(block)
}

// --- handleResetDaily error path ---

// TestHandleResetDailyInternalServerError verifies that handleResetDaily returns
// HTTP 500 when the underlying resetDaily() call fails. This covers the error
// branch in the handler that the happy-path test cannot reach.
// We trigger the failure by writing corrupt JSON to data.json so loadData (the
// first step of resetDaily) returns an error.
func TestHandleResetDailyInternalServerError(t *testing.T) {
	dir, _ := setupDirs(t)
	setupCorruptData(t, dir)

	req := httptest.NewRequest(http.MethodPost, "/api/reset/daily", nil)
	w := httptest.NewRecorder()
	handleResetDaily(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 when resetDaily fails, got %d: %s", w.Code, w.Body.String())
	}
}

// --- handleResetWeekly error path ---

// TestHandleResetWeeklyInternalServerError verifies that handleResetWeekly returns
// HTTP 500 when the underlying resetWeekly() call fails. Mirrors the daily-reset
// test: corrupt data.json makes loadData error which propagates to the handler.
func TestHandleResetWeeklyInternalServerError(t *testing.T) {
	dir, _ := setupDirs(t)
	setupCorruptData(t, dir)

	req := httptest.NewRequest(http.MethodPost, "/api/reset/weekly", nil)
	w := httptest.NewRecorder()
	handleResetWeekly(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 when resetWeekly fails, got %d: %s", w.Code, w.Body.String())
	}
}

// --- handleTodo PUT saveData error path ---

// TestHandleTodoPutSaveDataFailsReturns500 verifies that handleTodo (PUT) returns
// HTTP 500 when saveData fails. We trigger the failure by pointing dataDir at a
// path whose parent directory does not exist, so os.WriteFile cannot create the
// file regardless of the process's privilege level.
func TestHandleTodoPutSaveDataFailsReturns500(t *testing.T) {
	_, _ = setupDirs(t) // sets staticDir; we override dataDir below

	// Override dataDir with a path that cannot be written to.
	origDataDir := dataDir
	dataDir = filepath.Join(t.TempDir(), "nonexistent-subdir")
	t.Cleanup(func() { dataDir = origDataDir })

	payload := TodoData{
		Weekly: Task{Task: "test task", Done: false},
		Daily:  []Task{{Task: "d1", Done: false}, {}, {}},
	}
	b, _ := json.Marshal(payload)

	req := httptest.NewRequest(http.MethodPut, "/api/todo", strings.NewReader(string(b)))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	handleTodo(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 when saveData fails, got %d: %s", w.Code, w.Body.String())
	}
}

// --- startScheduler ---

// TestStartScheduler_DoesNotBlock verifies that startScheduler() returns promptly
// to the caller after spawning its internal goroutine. The goroutine itself waits
// until midnight before acting, so the test completes long before any reset
// function would be invoked.
func TestStartScheduler_DoesNotBlock(t *testing.T) {
	done := make(chan struct{})
	go func() {
		startScheduler()
		close(done)
	}()

	select {
	case <-done:
		// success: startScheduler returned without blocking
	case <-time.After(2 * time.Second):
		t.Fatal("startScheduler blocked for more than 2 seconds; expected it to return immediately after spawning a goroutine")
	}
}
