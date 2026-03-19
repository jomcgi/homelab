package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type Task struct {
	Task string `json:"task"`
	Done bool   `json:"done"`
}

type TodoData struct {
	Weekly Task   `json:"weekly"`
	Daily  []Task `json:"daily"`
}

var (
	dataDir           = getEnv("DATA_DIR", "/data")
	staticDir         = getEnv("STATIC_DIR", "/app/static")
	gitRepo           = getEnv("GIT_REPO", "")
	gitRoot           = getEnv("GIT_ROOT", "") // Git repo root, defaults to DATA_DIR
	gitBranch         = getEnv("GIT_BRANCH", "main")
	listenAddr        = getEnv("LISTEN_ADDR", ":8080")
	rollingWindowDays = 14
)

func init() {
	// Default gitRoot to dataDir if not set
	if gitRoot == "" {
		gitRoot = dataDir
	}
}

/*
Data Contract:

GET /api/weekly
Response: { "task": string, "done": bool }

GET /api/daily
Response: [{ "task": string, "done": bool }, ...]

GET /api/dates
Response: string[] - ISO dates (YYYY-MM-DD), sorted asc, max 14 days

GET /{YYYY}/{MM}/{D}.md
Response: Markdown file with ## Weekly and - [x]/[ ] task format

PUT /api/todo
Body: { "weekly": { "task": string, "done": bool }, "daily": [...] }

POST /api/reset/daily - Archives current day, clears daily tasks
POST /api/reset/weekly - Archives current day, clears all tasks
*/

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func startScheduler() {
	loc, err := time.LoadLocation("America/Los_Angeles")
	if err != nil {
		log.Printf("Failed to load timezone, using UTC: %v", err)
		loc = time.UTC
	}

	go func() {
		for {
			now := time.Now().In(loc)

			// Calculate next midnight
			next := time.Date(now.Year(), now.Month(), now.Day()+1, 0, 0, 0, 0, loc)
			sleepDuration := time.Until(next)
			log.Printf("Scheduler: next reset at %s (sleeping %s)", next.Format(time.RFC3339), sleepDuration)
			time.Sleep(sleepDuration)

			// Saturday midnight = end of Friday = weekly reset
			resetTime := time.Now().In(loc)
			if resetTime.Weekday() == time.Saturday {
				log.Println("Scheduler: triggering weekly reset")
				if err := resetWeekly(); err != nil {
					log.Printf("Scheduler: weekly reset failed: %v", err)
				}
			} else {
				log.Println("Scheduler: triggering daily reset")
				if err := resetDaily(); err != nil {
					log.Printf("Scheduler: daily reset failed: %v", err)
				}
			}
		}
	}()
}

func main() {
	// Initialize public directory on startup
	if err := rebuildSite(); err != nil {
		log.Printf("Warning: failed to rebuild site on startup: %v", err)
	}

	// Start internal scheduler
	startScheduler()

	// API routes
	http.HandleFunc("/api/weekly", handleWeekly)
	http.HandleFunc("/api/daily", handleDaily)
	http.HandleFunc("/api/todo", handleTodo)
	http.HandleFunc("/api/reset/daily", handleResetDaily)
	http.HandleFunc("/api/reset/weekly", handleResetWeekly)
	http.HandleFunc("/api/dates", handleDates)

	// Health
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	// Serve edit UI at root for admin service
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			http.ServeFile(w, r, filepath.Join(staticDir, "edit.html"))
			return
		}
		http.NotFound(w, r)
	})

	log.Printf("Starting server on %s", listenAddr)
	log.Fatal(http.ListenAndServe(listenAddr, nil))
}

func handleTodo(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	switch r.Method {
	case http.MethodGet:
		data, err := loadData()
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		json.NewEncoder(w).Encode(data)

	case http.MethodPut:
		var data TodoData
		if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if err := saveData(data); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)

	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func handleWeekly(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	data, err := loadData()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	json.NewEncoder(w).Encode(data.Weekly)
}

func handleDaily(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	data, err := loadData()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	json.NewEncoder(w).Encode(data.Daily)
}

func handleResetDaily(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if err := resetDaily(); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}

func handleResetWeekly(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if err := resetWeekly(); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}

func handleDates(w http.ResponseWriter, r *http.Request) {
	dates, err := collectDates()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(dates)
}

func loadData() (TodoData, error) {
	var data TodoData
	f, err := os.ReadFile(filepath.Join(dataDir, "data.json"))
	if err != nil {
		if os.IsNotExist(err) {
			return TodoData{
				Daily: []Task{{}, {}, {}},
			}, nil
		}
		return data, err
	}
	err = json.Unmarshal(f, &data)
	return data, err
}

func saveData(data TodoData) error {
	f, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dataDir, "data.json"), f, 0o644)
}

func resetDaily() error {
	data, err := loadData()
	if err != nil {
		return err
	}

	// Archive to markdown
	if err := archiveDay(data); err != nil {
		return err
	}

	// Clear daily, keep weekly
	data.Daily = []Task{{}, {}, {}}
	if err := saveData(data); err != nil {
		return err
	}

	// Rebuild and commit
	if err := rebuildSite(); err != nil {
		return err
	}

	return gitCommit("reset: daily")
}

func resetWeekly() error {
	data, err := loadData()
	if err != nil {
		return err
	}

	// Archive to markdown (captures weekly completion state)
	if err := archiveDay(data); err != nil {
		return err
	}

	// Clear everything
	data = TodoData{
		Daily: []Task{{}, {}, {}},
	}
	if err := saveData(data); err != nil {
		return err
	}

	if err := rebuildSite(); err != nil {
		return err
	}

	return gitCommit("reset: weekly")
}

func archiveDay(data TodoData) error {
	now := time.Now()
	year := now.Format("2006")
	month := now.Format("01")
	day := now.Day()

	dir := filepath.Join(dataDir, year, month)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}

	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("# %s\n\n", now.Format("Monday, January 2")))

	sb.WriteString("## Weekly\n")
	if data.Weekly.Task != "" {
		sb.WriteString(data.Weekly.Task)
	} else {
		sb.WriteString("(none)")
	}
	sb.WriteString("\n\n")

	sb.WriteString("## Daily\n")
	for _, task := range data.Daily {
		if task.Task != "" {
			check := " "
			if task.Done {
				check = "x"
			}
			sb.WriteString(fmt.Sprintf("- [%s] %s\n", check, task.Task))
		}
	}

	path := filepath.Join(dir, fmt.Sprintf("%d.md", day))
	return os.WriteFile(path, []byte(sb.String()), 0o644)
}

func collectDates() ([]string, error) {
	var dates []string
	cutoff := time.Now().AddDate(0, 0, -rollingWindowDays)

	err := filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() && strings.HasSuffix(path, ".md") {
			// Extract date from path: /data/2025/01/29.md -> 2025-01-29
			rel, _ := filepath.Rel(dataDir, path)
			parts := strings.Split(rel, string(os.PathSeparator))
			if len(parts) == 3 {
				year := parts[0]
				month := parts[1]
				day := strings.TrimSuffix(parts[2], ".md")
				if len(day) == 1 {
					day = "0" + day
				}
				dateStr := fmt.Sprintf("%s-%s-%s", year, month, day)

				// Only include dates within rolling window
				if t, err := time.Parse("2006-01-02", dateStr); err == nil && t.After(cutoff) {
					dates = append(dates, dateStr)
				}
			}
		}
		return nil
	})

	sort.Strings(dates)

	// Add today if not present
	today := time.Now().Format("2006-01-02")
	if len(dates) == 0 || dates[len(dates)-1] != today {
		dates = append(dates, today)
	}

	return dates, err
}

func rebuildSite() error {
	dates, err := collectDates()
	if err != nil {
		return err
	}

	// Read template from static dir (bundled in container)
	tmpl, err := os.ReadFile(filepath.Join(staticDir, "index.html"))
	if err != nil {
		return err
	}

	// Inject dates
	datesJSON, _ := json.Marshal(dates)
	content := strings.Replace(
		string(tmpl),
		`/*DATES_PLACEHOLDER*/["2025-01-28", "2025-01-29", "2025-01-30"]/*END_PLACEHOLDER*/`,
		string(datesJSON),
		1,
	)

	// Write to output
	outDir := filepath.Join(dataDir, "public")
	os.MkdirAll(outDir, 0o755)

	if err := os.WriteFile(filepath.Join(outDir, "index.html"), []byte(content), 0o644); err != nil {
		return err
	}

	// Copy data.json
	data, _ := os.ReadFile(filepath.Join(dataDir, "data.json"))
	if err := os.WriteFile(filepath.Join(outDir, "data.json"), data, 0o644); err != nil {
		return err
	}

	// Build set of valid dates for filtering
	validDates := make(map[string]bool)
	for _, d := range dates {
		validDates[d] = true
	}

	// Copy only markdown files within rolling window
	return filepath.Walk(dataDir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return err
		}
		if strings.HasSuffix(path, ".md") {
			rel, _ := filepath.Rel(dataDir, path)
			parts := strings.Split(rel, string(os.PathSeparator))
			if len(parts) == 3 {
				year := parts[0]
				month := parts[1]
				day := strings.TrimSuffix(parts[2], ".md")
				if len(day) == 1 {
					day = "0" + day
				}
				dateStr := fmt.Sprintf("%s-%s-%s", year, month, day)

				// Only copy if within rolling window
				if validDates[dateStr] {
					dest := filepath.Join(outDir, rel)
					os.MkdirAll(filepath.Dir(dest), 0o755)
					content, _ := os.ReadFile(path)
					return os.WriteFile(dest, content, 0o644)
				}
			}
		}
		return nil
	})
}

func gitCommit(msg string) error {
	if gitRepo == "" {
		log.Println("GIT_REPO not set, skipping commit")
		return nil
	}

	cmds := [][]string{
		{"git", "-C", gitRoot, "add", "-A"},
		{"git", "-C", gitRoot, "commit", "-m", msg},
		{"git", "-C", gitRoot, "push", "origin", gitBranch},
	}

	for _, args := range cmds {
		cmd := exec.Command(args[0], args[1:]...)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		if err := cmd.Run(); err != nil {
			// Ignore "nothing to commit"
			if strings.Contains(err.Error(), "exit status 1") && args[3] == "commit" {
				continue
			}
			return err
		}
	}
	return nil
}
