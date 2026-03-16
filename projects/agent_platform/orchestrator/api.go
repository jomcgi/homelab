package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"
)

const (
	maxMaxRetries = 10
	defaultSource = "api"
)

// API provides HTTP handlers for the job orchestration service.
type API struct {
	store             Store
	publish           func(jobID string) error // publishes job ID to JetStream, nil = no-op
	healthCheck       func() error             // checks backing store connectivity
	defaultMaxRetries int
	inferenceURL      string
	logger            *slog.Logger
}

// NewAPI creates a new API with the given store, publish function, and logger.
func NewAPI(store Store, publish func(string) error, healthCheck func() error, defaultMaxRetries int, inferenceURL string, logger *slog.Logger) *API {
	return &API{store: store, publish: publish, healthCheck: healthCheck, defaultMaxRetries: defaultMaxRetries, inferenceURL: inferenceURL, logger: logger}
}

// RegisterRoutes adds all API routes to the given ServeMux.
func (a *API) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /jobs", a.handleSubmit)
	mux.HandleFunc("GET /jobs", a.handleList)
	mux.HandleFunc("GET /jobs/{id}", a.handleGet)
	mux.HandleFunc("POST /jobs/{id}/cancel", a.handleCancel)
	mux.HandleFunc("GET /jobs/{id}/output", a.handleOutput)
	mux.HandleFunc("POST /jobs/{id}/summarize", a.handleSummarize)
	mux.HandleFunc("GET /health", a.handleHealth)
}

func (a *API) handleSubmit(w http.ResponseWriter, r *http.Request) {
	var req SubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		a.writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if strings.TrimSpace(req.Task) == "" {
		a.writeError(w, http.StatusBadRequest, "task is required")
		return
	}

	maxRetries := a.defaultMaxRetries
	if req.MaxRetries != nil {
		maxRetries = *req.MaxRetries
		if maxRetries < 0 {
			maxRetries = 0
		}
		if maxRetries > maxMaxRetries {
			maxRetries = maxMaxRetries
		}
	}

	source := req.Source
	if source == "" {
		source = defaultSource
	}

	now := time.Now().UTC()
	id, err := ulid.New(ulid.Timestamp(now), rand.Reader)
	if err != nil {
		a.logger.Error("failed to generate job ID", "error", err)
		a.writeError(w, http.StatusInternalServerError, "failed to generate job ID")
		return
	}

	job := &JobRecord{
		ID:         id.String(),
		Task:       req.Task,
		Status:     JobPending,
		CreatedAt:  now,
		UpdatedAt:  now,
		MaxRetries: maxRetries,
		Source:     source,
		Tags:       req.Tags,
		Attempts:   []Attempt{},
	}

	if err := a.store.Put(r.Context(), job); err != nil {
		a.logger.Error("failed to store job", "error", err)
		a.writeError(w, http.StatusInternalServerError, "failed to store job")
		return
	}

	if a.publish != nil {
		if err := a.publish(job.ID); err != nil {
			a.logger.Error("failed to publish job", "id", job.ID, "error", err)
			// Roll back the KV entry so we don't leave a ghost job.
			_ = a.store.Delete(r.Context(), job.ID)
			a.writeError(w, http.StatusInternalServerError, "failed to enqueue job")
			return
		}
	}

	a.writeJSON(w, http.StatusAccepted, SubmitResponse{
		ID:        job.ID,
		Status:    job.Status,
		CreatedAt: job.CreatedAt,
	})
}

func (a *API) handleList(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	var statusFilter []string
	if s := q.Get("status"); s != "" {
		statusFilter = strings.Split(s, ",")
	}

	limit := 20
	if l := q.Get("limit"); l != "" {
		if v, err := strconv.Atoi(l); err == nil && v > 0 {
			limit = v
		}
	}
	if limit > 100 {
		limit = 100
	}

	offset := 0
	if o := q.Get("offset"); o != "" {
		if v, err := strconv.Atoi(o); err == nil && v >= 0 {
			offset = v
		}
	}

	var tagFilter []string
	if t := q.Get("tags"); t != "" {
		tagFilter = strings.Split(t, ",")
	}

	jobs, total, err := a.store.List(r.Context(), statusFilter, tagFilter, limit, offset)
	if err != nil {
		a.logger.Error("failed to list jobs", "error", err)
		a.writeError(w, http.StatusInternalServerError, "failed to list jobs")
		return
	}

	if jobs == nil {
		jobs = []JobRecord{}
	}

	a.writeJSON(w, http.StatusOK, ListResponse{
		Jobs:  jobs,
		Total: total,
	})
}

func (a *API) handleGet(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	job, err := a.store.Get(r.Context(), id)
	if err != nil || job == nil {
		a.writeError(w, http.StatusNotFound, "job not found")
		return
	}
	a.writeJSON(w, http.StatusOK, job)
}

func (a *API) handleCancel(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	job, err := a.store.Get(r.Context(), id)
	if err != nil || job == nil {
		a.writeError(w, http.StatusNotFound, "job not found")
		return
	}

	if job.Status != JobPending && job.Status != JobRunning {
		a.writeError(w, http.StatusConflict, "job cannot be cancelled in status "+string(job.Status))
		return
	}

	job.Status = JobCancelled
	if err := a.store.Put(r.Context(), job); err != nil {
		a.logger.Error("failed to update job", "id", id, "error", err)
		a.writeError(w, http.StatusInternalServerError, "failed to update job")
		return
	}

	a.writeJSON(w, http.StatusOK, job)
}

func (a *API) handleOutput(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	job, err := a.store.Get(r.Context(), id)
	if err != nil || job == nil {
		a.writeError(w, http.StatusNotFound, "job not found")
		return
	}

	if len(job.Attempts) == 0 {
		a.writeError(w, http.StatusNotFound, "no output available")
		return
	}

	latest := job.Attempts[len(job.Attempts)-1]
	a.writeJSON(w, http.StatusOK, OutputResponse{
		Attempt:   latest.Number,
		ExitCode:  latest.ExitCode,
		Output:    latest.Output,
		Truncated: latest.Truncated,
		Result:    latest.Result,
	})
}

func (a *API) handleHealth(w http.ResponseWriter, _ *http.Request) {
	if a.healthCheck != nil {
		if err := a.healthCheck(); err != nil {
			a.writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "unhealthy", "error": err.Error()})
			return
		}
	}
	a.writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (a *API) handleSummarize(w http.ResponseWriter, r *http.Request) {
	if a.inferenceURL == "" {
		a.writeError(w, http.StatusServiceUnavailable, "inference not configured")
		return
	}

	id := r.PathValue("id")
	job, err := a.store.Get(r.Context(), id)
	if err != nil || job == nil {
		a.writeError(w, http.StatusNotFound, "job not found")
		return
	}

	if len(job.Plan) == 0 {
		a.writeError(w, http.StatusUnprocessableEntity, "job has no plan")
		return
	}

	// Build prompt from job task and plan steps.
	var sb strings.Builder
	sb.WriteString("Job task: ")
	sb.WriteString(job.Task)
	sb.WriteString("\n\nPlan steps:\n")
	for i, step := range job.Plan {
		fmt.Fprintf(&sb, "%d. [%s] %s (agent: %s)\n", i+1, step.Status, step.Description, step.Agent)
	}

	reqBody := map[string]any{
		"model": "qwen3.5-35b-a3b",
		"messages": []map[string]string{
			{"role": "system", "content": "You summarize agent job plans. Respond with JSON containing \"title\" (short, max 10 words) and \"summary\" (1-2 sentences)."},
			{"role": "user", "content": sb.String()},
		},
		"temperature": 0.3,
		"max_tokens":  256,
		"response_format": map[string]any{
			"type": "json_schema",
			"json_schema": map[string]any{
				"name":   "summary_response",
				"strict": true,
				"schema": map[string]any{
					"type": "object",
					"properties": map[string]any{
						"title":   map[string]string{"type": "string"},
						"summary": map[string]string{"type": "string"},
					},
					"required":             []string{"title", "summary"},
					"additionalProperties": false,
				},
			},
		},
	}

	body, err := json.Marshal(reqBody)
	if err != nil {
		a.writeError(w, http.StatusInternalServerError, "failed to build request")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, a.inferenceURL+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		a.writeError(w, http.StatusInternalServerError, "failed to create request")
		return
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(httpReq)
	if err != nil {
		a.logger.Error("inference request failed", "error", err)
		a.writeError(w, http.StatusBadGateway, "inference request failed")
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		a.logger.Error("inference returned non-200", "status", resp.StatusCode)
		a.writeError(w, http.StatusBadGateway, "inference returned error")
		return
	}

	var chatResp struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&chatResp); err != nil {
		a.writeError(w, http.StatusBadGateway, "failed to parse inference response")
		return
	}

	if len(chatResp.Choices) == 0 {
		a.writeError(w, http.StatusBadGateway, "no choices in inference response")
		return
	}

	var result SummarizeResponse
	if err := json.Unmarshal([]byte(chatResp.Choices[0].Message.Content), &result); err != nil {
		a.logger.Error("failed to parse summary JSON", "content", chatResp.Choices[0].Message.Content, "error", err)
		a.writeError(w, http.StatusBadGateway, "failed to parse summary")
		return
	}

	a.writeJSON(w, http.StatusOK, result)
}

func (a *API) writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		a.logger.Error("failed to write response", "error", err)
	}
}

func (a *API) writeError(w http.ResponseWriter, status int, msg string) {
	a.writeJSON(w, status, map[string]string{"error": msg})
}
