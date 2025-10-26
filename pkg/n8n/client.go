package n8n

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const tracerName = "github.com/jomcgi/homelab/pkg/n8n"

// ObservableClient wraps the generated n8n client with observability (tracing, logging)
type ObservableClient struct {
	*ClientWithResponses
	tracer trace.Tracer
	logger *slog.Logger
}

// NewObservableClient creates a new n8n API client with observability support
func NewObservableClient(baseURL, apiKey string, opts ...ClientOption) (*ObservableClient, error) {
	// Add API key authentication via request editor
	requestEditorFn := func(ctx context.Context, req *http.Request) error {
		req.Header.Set("X-N8N-API-KEY", apiKey)
		return nil
	}

	// Combine with user-provided options
	allOpts := append([]ClientOption{
		WithRequestEditorFn(requestEditorFn),
	}, opts...)

	// Create the generated client
	client, err := NewClientWithResponses(baseURL, allOpts...)
	if err != nil {
		return nil, fmt.Errorf("create n8n client: %w", err)
	}

	return &ObservableClient{
		ClientWithResponses: client,
		tracer:             otel.Tracer(tracerName),
		logger:             slog.Default(),
	}, nil
}

// WithLogger sets a custom logger for the client
func (c *ObservableClient) WithLogger(logger *slog.Logger) *ObservableClient {
	c.logger = logger
	return c
}

// formatErrorResponse creates a detailed error message from an API response
func formatErrorResponse(statusCode int, body []byte) string {
	bodyPreview := string(body)
	if len(bodyPreview) > 500 {
		bodyPreview = bodyPreview[:500] + "..."
	}
	return fmt.Sprintf("status %d: %s", statusCode, bodyPreview)
}

// ListWorkflows retrieves all workflows with tracing and logging
func (c *ObservableClient) ListWorkflows(ctx context.Context, params *GetWorkflowsParams) (*WorkflowList, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.ListWorkflows")
	defer span.End()

	resp, err := c.GetWorkflowsWithResponse(ctx, params)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to list workflows")
		return nil, fmt.Errorf("list workflows: %w", err)
	}

	if resp.JSON200 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("list workflows failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "list workflows failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body))
		return nil, err
	}

	count := 0
	if resp.JSON200.Data != nil {
		count = len(*resp.JSON200.Data)
	}

	span.SetAttributes(attribute.Int("workflow.count", count))
	span.SetStatus(codes.Ok, "workflows listed successfully")
	c.logger.InfoContext(ctx, "listed workflows", "count", count)

	return resp.JSON200, nil
}

// CreateWorkflow creates a new workflow with tracing and logging
func (c *ObservableClient) CreateWorkflow(ctx context.Context, workflow Workflow) (*Workflow, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.CreateWorkflow",
		trace.WithAttributes(attribute.String("workflow.name", workflow.Name)))
	defer span.End()

	resp, err := c.PostWorkflowsWithResponse(ctx, workflow)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create workflow")
		return nil, fmt.Errorf("create workflow: %w", err)
	}

	if resp.JSON200 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("create workflow failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "create workflow failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body),
			"workflow_name", workflow.Name)
		return nil, err
	}

	workflowID := ""
	if resp.JSON200.Id != nil {
		workflowID = *resp.JSON200.Id
	}

	span.SetAttributes(attribute.String("workflow.id", workflowID))
	span.SetStatus(codes.Ok, "workflow created successfully")
	c.logger.InfoContext(ctx, "created workflow",
		"name", workflow.Name,
		"id", workflowID)

	return resp.JSON200, nil
}

// UpdateWorkflow updates an existing workflow with tracing and logging
func (c *ObservableClient) UpdateWorkflow(ctx context.Context, id string, workflow Workflow) (*Workflow, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.UpdateWorkflow",
		trace.WithAttributes(
			attribute.String("workflow.id", id),
			attribute.String("workflow.name", workflow.Name)))
	defer span.End()

	resp, err := c.PutWorkflowsIdWithResponse(ctx, id, workflow)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to update workflow")
		return nil, fmt.Errorf("update workflow: %w", err)
	}

	if resp.JSON200 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("update workflow failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "update workflow failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body),
			"workflow_id", id)
		return nil, err
	}

	span.SetStatus(codes.Ok, "workflow updated successfully")
	c.logger.InfoContext(ctx, "updated workflow",
		"name", workflow.Name,
		"id", id)

	return resp.JSON200, nil
}

// ListTags retrieves all tags with tracing and logging
func (c *ObservableClient) ListTags(ctx context.Context, params *GetTagsParams) (*TagList, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.ListTags")
	defer span.End()

	resp, err := c.GetTagsWithResponse(ctx, params)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to list tags")
		return nil, fmt.Errorf("list tags: %w", err)
	}

	if resp.JSON200 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("list tags failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "list tags failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body))
		return nil, err
	}

	count := 0
	if resp.JSON200.Data != nil {
		count = len(*resp.JSON200.Data)
	}

	span.SetAttributes(attribute.Int("tag.count", count))
	span.SetStatus(codes.Ok, "tags listed successfully")
	c.logger.InfoContext(ctx, "listed tags", "count", count)

	return resp.JSON200, nil
}

// CreateTag creates a new tag with tracing and logging
func (c *ObservableClient) CreateTag(ctx context.Context, tag Tag) (*Tag, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.CreateTag",
		trace.WithAttributes(attribute.String("tag.name", tag.Name)))
	defer span.End()

	resp, err := c.PostTagsWithResponse(ctx, tag)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create tag")
		return nil, fmt.Errorf("create tag: %w", err)
	}

	if resp.JSON201 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("create tag failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "create tag failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body),
			"tag_name", tag.Name)
		return nil, err
	}

	tagID := ""
	if resp.JSON201.Id != nil {
		tagID = *resp.JSON201.Id
	}

	span.SetAttributes(attribute.String("tag.id", tagID))
	span.SetStatus(codes.Ok, "tag created successfully")
	c.logger.InfoContext(ctx, "created tag",
		"name", tag.Name,
		"id", tagID)

	return resp.JSON201, nil
}

// GetWorkflowTags retrieves tags for a specific workflow
func (c *ObservableClient) GetWorkflowTags(ctx context.Context, workflowID string) ([]Tag, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.GetWorkflowTags",
		trace.WithAttributes(attribute.String("workflow.id", workflowID)))
	defer span.End()

	resp, err := c.GetWorkflowsIdTagsWithResponse(ctx, workflowID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get workflow tags")
		return nil, fmt.Errorf("get workflow tags: %w", err)
	}

	if resp.JSON200 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("get workflow tags failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "get workflow tags failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body),
			"workflow_id", workflowID)
		return nil, err
	}

	count := len(*resp.JSON200)
	span.SetAttributes(attribute.Int("tag.count", count))
	span.SetStatus(codes.Ok, "workflow tags retrieved successfully")
	c.logger.InfoContext(ctx, "got workflow tags",
		"workflow_id", workflowID,
		"count", count)

	return *resp.JSON200, nil
}

// UpdateWorkflowTags updates the tags for a specific workflow
func (c *ObservableClient) UpdateWorkflowTags(ctx context.Context, workflowID string, tagIDs TagIds) ([]Tag, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.UpdateWorkflowTags",
		trace.WithAttributes(
			attribute.String("workflow.id", workflowID),
			attribute.Int("tag.count", len(tagIDs))))
	defer span.End()

	resp, err := c.PutWorkflowsIdTagsWithResponse(ctx, workflowID, tagIDs)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to update workflow tags")
		return nil, fmt.Errorf("update workflow tags: %w", err)
	}

	if resp.JSON200 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("update workflow tags failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "update workflow tags failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body),
			"workflow_id", workflowID)
		return nil, err
	}

	span.SetStatus(codes.Ok, "workflow tags updated successfully")
	c.logger.InfoContext(ctx, "updated workflow tags",
		"workflow_id", workflowID,
		"tag_count", len(*resp.JSON200))

	return *resp.JSON200, nil
}

// ActivateWorkflow activates a workflow with tracing and logging
func (c *ObservableClient) ActivateWorkflow(ctx context.Context, workflowID string) (*Workflow, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.ActivateWorkflow",
		trace.WithAttributes(attribute.String("workflow.id", workflowID)))
	defer span.End()

	resp, err := c.PostWorkflowsIdActivateWithResponse(ctx, workflowID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to activate workflow")
		return nil, fmt.Errorf("activate workflow: %w", err)
	}

	if resp.JSON200 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("activate workflow failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "activate workflow failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body),
			"workflow_id", workflowID)
		return nil, err
	}

	span.SetStatus(codes.Ok, "workflow activated successfully")
	c.logger.InfoContext(ctx, "activated workflow",
		"workflow_id", workflowID)

	return resp.JSON200, nil
}

// DeactivateWorkflow deactivates a workflow with tracing and logging
func (c *ObservableClient) DeactivateWorkflow(ctx context.Context, workflowID string) (*Workflow, error) {
	ctx, span := c.tracer.Start(ctx, "n8n.DeactivateWorkflow",
		trace.WithAttributes(attribute.String("workflow.id", workflowID)))
	defer span.End()

	resp, err := c.PostWorkflowsIdDeactivateWithResponse(ctx, workflowID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to deactivate workflow")
		return nil, fmt.Errorf("deactivate workflow: %w", err)
	}

	if resp.JSON200 == nil {
		errMsg := formatErrorResponse(resp.StatusCode(), resp.Body)
		err := fmt.Errorf("deactivate workflow failed: %s", errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, "unexpected response")
		c.logger.ErrorContext(ctx, "deactivate workflow failed",
			"status", resp.StatusCode(),
			"body", string(resp.Body),
			"workflow_id", workflowID)
		return nil, err
	}

	span.SetStatus(codes.Ok, "workflow deactivated successfully")
	c.logger.InfoContext(ctx, "deactivated workflow",
		"workflow_id", workflowID)

	return resp.JSON200, nil
}

// HealthCheck verifies the n8n API is accessible by attempting to list workflows
func (c *ObservableClient) HealthCheck(ctx context.Context) error {
	ctx, span := c.tracer.Start(ctx, "n8n.HealthCheck")
	defer span.End()

	// Try to list workflows with a limit of 1 as a health check
	limit := Limit(1)
	params := &GetWorkflowsParams{
		Limit: &limit,
	}

	_, err := c.ListWorkflows(ctx, params)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "health check failed")
		return fmt.Errorf("health check request: %w", err)
	}

	span.SetStatus(codes.Ok, "n8n is healthy")
	c.logger.InfoContext(ctx, "n8n is healthy")
	return nil
}
