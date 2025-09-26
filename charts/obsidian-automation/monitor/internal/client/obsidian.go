/*
Copyright 2025.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
)

// ObsidianClient provides an interface to interact with the Obsidian REST API
type ObsidianClient struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

// SyncStatus represents the sync status response from Obsidian
type SyncStatus struct {
	Connected      bool     `json:"connected"`
	LastSyncTime   string   `json:"lastSyncTime"`
	PendingChanges int      `json:"pendingChanges"`
	FailedFiles    []string `json:"failedFiles,omitempty"`
	SyncErrors     []SyncError `json:"syncErrors,omitempty"`
}

// SyncError represents a sync error
type SyncError struct {
	File      string `json:"file"`
	Error     string `json:"error"`
	Timestamp string `json:"timestamp"`
}

// Note represents a note in Obsidian
type Note struct {
	Path     string `json:"path"`
	Content  string `json:"content"`
	Tags     []string `json:"tags,omitempty"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}

// NewObsidianClient creates a new Obsidian API client
func NewObsidianClient(baseURL, apiKey string) *ObsidianClient {
	return &ObsidianClient{
		baseURL: baseURL,
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// GetSyncStatus retrieves the current sync status
func (c *ObsidianClient) GetSyncStatus(ctx context.Context) (*SyncStatus, error) {
	tracer := otel.Tracer("obsidian-client")
	ctx, span := tracer.Start(ctx, "get_sync_status")
	defer span.End()

	span.SetAttributes(attribute.String("endpoint", "/api/sync/status"))

	req, err := c.newRequest(ctx, "GET", "/api/sync/status", nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	var status SyncStatus
	if err := c.doRequest(req, &status); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("failed to get sync status: %w", err)
	}

	span.SetAttributes(
		attribute.Bool("sync.connected", status.Connected),
		attribute.Int("sync.pending_changes", status.PendingChanges),
		attribute.Int("sync.failed_files_count", len(status.FailedFiles)),
	)

	return &status, nil
}

// VerifySync performs an immediate sync verification
func (c *ObsidianClient) VerifySync(ctx context.Context) (*SyncStatus, error) {
	tracer := otel.Tracer("obsidian-client")
	ctx, span := tracer.Start(ctx, "verify_sync")
	defer span.End()

	span.SetAttributes(attribute.String("endpoint", "/api/sync/verify"))

	req, err := c.newRequest(ctx, "POST", "/api/sync/verify", nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	var status SyncStatus
	if err := c.doRequest(req, &status); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("failed to verify sync: %w", err)
	}

	return &status, nil
}

// CreateNote creates a new note for synthetic testing
func (c *ObsidianClient) CreateNote(ctx context.Context, note *Note) error {
	tracer := otel.Tracer("obsidian-client")
	ctx, span := tracer.Start(ctx, "create_note")
	defer span.End()

	span.SetAttributes(
		attribute.String("endpoint", "/api/notes"),
		attribute.String("note.path", note.Path),
		attribute.Int("note.content_length", len(note.Content)),
	)

	req, err := c.newRequest(ctx, "POST", "/api/notes", note)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return fmt.Errorf("failed to create request: %w", err)
	}

	if err := c.doRequest(req, nil); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return fmt.Errorf("failed to create note: %w", err)
	}

	return nil
}

// DeleteNote deletes a note (used for cleanup after synthetic testing)
func (c *ObsidianClient) DeleteNote(ctx context.Context, path string) error {
	tracer := otel.Tracer("obsidian-client")
	ctx, span := tracer.Start(ctx, "delete_note")
	defer span.End()

	endpoint := fmt.Sprintf("/api/notes/%s", path)
	span.SetAttributes(
		attribute.String("endpoint", endpoint),
		attribute.String("note.path", path),
	)

	req, err := c.newRequest(ctx, "DELETE", endpoint, nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return fmt.Errorf("failed to create request: %w", err)
	}

	if err := c.doRequest(req, nil); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return fmt.Errorf("failed to delete note: %w", err)
	}

	return nil
}

// GetNote retrieves a note by path
func (c *ObsidianClient) GetNote(ctx context.Context, path string) (*Note, error) {
	tracer := otel.Tracer("obsidian-client")
	ctx, span := tracer.Start(ctx, "get_note")
	defer span.End()

	endpoint := fmt.Sprintf("/api/notes/%s", path)
	span.SetAttributes(
		attribute.String("endpoint", endpoint),
		attribute.String("note.path", path),
	)

	req, err := c.newRequest(ctx, "GET", endpoint, nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	var note Note
	if err := c.doRequest(req, &note); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return nil, fmt.Errorf("failed to get note: %w", err)
	}

	span.SetAttributes(attribute.Int("note.content_length", len(note.Content)))

	return &note, nil
}

// IsHealthy checks if the API is responding
func (c *ObsidianClient) IsHealthy(ctx context.Context) bool {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	req, err := c.newRequest(ctx, "GET", "/health", nil)
	if err != nil {
		return false
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()

	return resp.StatusCode == http.StatusOK
}

// newRequest creates a new HTTP request with authentication and tracing
func (c *ObsidianClient) newRequest(ctx context.Context, method, endpoint string, body interface{}) (*http.Request, error) {
	var reqBody io.Reader
	if body != nil {
		jsonBody, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		reqBody = bytes.NewBuffer(jsonBody)
	}

	url := c.baseURL + endpoint
	req, err := http.NewRequestWithContext(ctx, method, url, reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to create HTTP request: %w", err)
	}

	// Set authentication header
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "obsidian-sync-monitor/1.0.0")

	return req, nil
}

// doRequest executes the HTTP request and handles the response
func (c *ObsidianClient) doRequest(req *http.Request, result interface{}) error {
	startTime := time.Now()
	resp, err := c.httpClient.Do(req)
	duration := time.Since(startTime)

	if err != nil {
		return fmt.Errorf("HTTP request failed: %w", err)
	}
	defer resp.Body.Close()

	// Log request metrics via context (to be handled by caller)
	if span := otel.SpanFromContext(req.Context()); span.IsRecording() {
		span.SetAttributes(
			attribute.Int("http.status_code", resp.StatusCode),
			attribute.Float64("http.duration_ms", float64(duration.Nanoseconds())/1e6),
		)
	}

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read response body: %w", err)
	}

	if resp.StatusCode >= 400 {
		return fmt.Errorf("API request failed with status %d: %s", resp.StatusCode, string(respBody))
	}

	if result != nil && len(respBody) > 0 {
		if err := json.Unmarshal(respBody, result); err != nil {
			return fmt.Errorf("failed to unmarshal response: %w", err)
		}
	}

	return nil
}

// IsRetryableError determines if an error should trigger a retry
func IsRetryableError(err error) bool {
	if err == nil {
		return false
	}

	// Network timeouts and temporary failures are retryable
	return true // For now, consider most errors retryable
}

// IsNotFoundError checks if the error indicates a resource was not found
func IsNotFoundError(err error) bool {
	if err == nil {
		return false
	}

	// Check if the error message indicates a 404
	return false // Implementation would depend on actual API responses
}