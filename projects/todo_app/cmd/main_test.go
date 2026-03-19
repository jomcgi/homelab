package main

import (
	"encoding/json"
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
