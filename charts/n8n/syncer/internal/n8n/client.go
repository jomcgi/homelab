package n8n

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	tracerName = "github.com/jomcgi/homelab/charts/n8n/syncer/n8n"
)

// Client represents an N8N API client
type Client struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
	tracer     trace.Tracer
}

// Workflow represents an N8N workflow
type Workflow struct {
	ID          string                 `json:"id,omitempty"`
	Name        string                 `json:"name"`
	Active      bool                   `json:"active,omitempty"`
	Nodes       []map[string]any       `json:"nodes"`
	Connections map[string]any         `json:"connections"`
	Settings    map[string]any         `json:"settings,omitempty"`
	StaticData  map[string]any         `json:"staticData,omitempty"`
	Tags        []map[string]any       `json:"tags,omitempty"`
	PinData     map[string]any         `json:"pinData,omitempty"`
	VersionId   string                 `json:"versionId,omitempty"`
}

// WorkflowList represents the response from listing workflows
type WorkflowList struct {
	Data []Workflow `json:"data"`
}

// NewClient creates a new N8N API client
func NewClient(baseURL, apiKey string) *Client {
	return &Client{
		baseURL: baseURL,
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		tracer: otel.Tracer(tracerName),
	}
}

// HealthCheck verifies the N8N API is accessible
func (c *Client) HealthCheck(ctx context.Context) error {
	ctx, span := c.tracer.Start(ctx, "n8n.HealthCheck")
	defer span.End()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/healthz", nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create request")
		return fmt.Errorf("create health check request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "health check failed")
		return fmt.Errorf("health check request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		span.SetStatus(codes.Error, fmt.Sprintf("unexpected status: %d", resp.StatusCode))
		return fmt.Errorf("health check returned status %d", resp.StatusCode)
	}

	span.SetStatus(codes.Ok, "n8n is healthy")
	return nil
}

// ListWorkflows retrieves all workflows from N8N
func (c *Client) ListWorkflows(ctx context.Context) ([]Workflow, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.ListWorkflows")
	defer span.End()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/api/v1/workflows", nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create request")
		return nil, fmt.Errorf("create list request: %w", err)
	}

	req.Header.Set("X-N8N-API-KEY", c.apiKey)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "list request failed")
		return nil, fmt.Errorf("list workflows request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		span.SetStatus(codes.Error, fmt.Sprintf("unexpected status: %d", resp.StatusCode))
		span.SetAttributes(attribute.String("response.body", string(body)))
		return nil, fmt.Errorf("list workflows returned status %d: %s", resp.StatusCode, string(body))
	}

	var result WorkflowList
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to decode response")
		return nil, fmt.Errorf("decode workflow list: %w", err)
	}

	span.SetAttributes(attribute.Int("workflow.count", len(result.Data)))
	span.SetStatus(codes.Ok, "workflows listed successfully")
	slog.InfoContext(ctx, "listed workflows", "count", len(result.Data))

	return result.Data, nil
}

// CreateWorkflow creates a new workflow in N8N
func (c *Client) CreateWorkflow(ctx context.Context, workflow *Workflow) (*Workflow, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.CreateWorkflow",
		trace.WithAttributes(attribute.String("workflow.name", workflow.Name)))
	defer span.End()

	body, err := json.Marshal(workflow)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to marshal workflow")
		return nil, fmt.Errorf("marshal workflow: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/api/v1/workflows", bytes.NewReader(body))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create request")
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("X-N8N-API-KEY", c.apiKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "create request failed")
		return nil, fmt.Errorf("create workflow request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		span.SetStatus(codes.Error, fmt.Sprintf("unexpected status: %d", resp.StatusCode))
		span.SetAttributes(attribute.String("response.body", string(body)))
		return nil, fmt.Errorf("create workflow returned status %d: %s", resp.StatusCode, string(body))
	}

	var created Workflow
	if err := json.NewDecoder(resp.Body).Decode(&created); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to decode response")
		return nil, fmt.Errorf("decode created workflow: %w", err)
	}

	span.SetAttributes(attribute.String("workflow.id", created.ID))
	span.SetStatus(codes.Ok, "workflow created successfully")
	slog.InfoContext(ctx, "created workflow",
		"name", created.Name,
		"id", created.ID)

	return &created, nil
}

// UpdateWorkflow updates an existing workflow in N8N
func (c *Client) UpdateWorkflow(ctx context.Context, id string, workflow *Workflow) (*Workflow, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.UpdateWorkflow",
		trace.WithAttributes(
			attribute.String("workflow.id", id),
			attribute.String("workflow.name", workflow.Name)))
	defer span.End()

	// Ensure the workflow has the correct ID for update
	workflow.ID = id

	body, err := json.Marshal(workflow)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to marshal workflow")
		return nil, fmt.Errorf("marshal workflow: %w", err)
	}

	url := fmt.Sprintf("%s/api/v1/workflows/%s", c.baseURL, id)
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, url, bytes.NewReader(body))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create request")
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("X-N8N-API-KEY", c.apiKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "update request failed")
		return nil, fmt.Errorf("update workflow request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		span.SetStatus(codes.Error, fmt.Sprintf("unexpected status: %d", resp.StatusCode))
		span.SetAttributes(attribute.String("response.body", string(body)))
		return nil, fmt.Errorf("update workflow returned status %d: %s", resp.StatusCode, string(body))
	}

	var updated Workflow
	if err := json.NewDecoder(resp.Body).Decode(&updated); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to decode response")
		return nil, fmt.Errorf("decode updated workflow: %w", err)
	}

	span.SetStatus(codes.Ok, "workflow updated successfully")
	slog.InfoContext(ctx, "updated workflow",
		"name", updated.Name,
		"id", updated.ID)

	return &updated, nil
}
