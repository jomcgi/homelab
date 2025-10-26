package sync

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jomcgi/homelab/pkg/n8n"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"
)

const (
	tracerName = "github.com/jomcgi/homelab/charts/n8n/syncer/sync"
)

// Config holds the syncer configuration
type Config struct {
	WorkflowDir    string
	ManagedSuffix  string
	ManagedTag     string
	N8NClient      *n8n.ObservableClient
}

// Syncer handles workflow synchronization
type Syncer struct {
	config       Config
	tracer       trace.Tracer
	metrics      *metrics
	managedTagID string // Cached ID of the managed tag
}

// metrics holds OpenTelemetry metrics
type metrics struct {
	syncDuration     metric.Float64Histogram
	workflowsSynced  metric.Int64Counter
	workflowsCreated metric.Int64Counter
	workflowsUpdated metric.Int64Counter
	workflowsFailed  metric.Int64Counter
}

// SyncResult contains the results of a sync operation
type SyncResult struct {
	TotalProcessed int
	Created        int
	Updated        int
	Failed         int
	Errors         []error
}

// NewSyncer creates a new workflow syncer
func NewSyncer(config Config) (*Syncer, error) {
	meter := otel.Meter(tracerName)

	syncDuration, err := meter.Float64Histogram(
		"n8n.sync.duration_seconds",
		metric.WithDescription("Duration of workflow sync operations"),
		metric.WithUnit("s"))
	if err != nil {
		return nil, fmt.Errorf("create sync duration metric: %w", err)
	}

	workflowsSynced, err := meter.Int64Counter(
		"n8n.workflows.synced_total",
		metric.WithDescription("Total number of workflows synced"))
	if err != nil {
		return nil, fmt.Errorf("create workflows synced metric: %w", err)
	}

	workflowsCreated, err := meter.Int64Counter(
		"n8n.workflows.created_total",
		metric.WithDescription("Total number of workflows created"))
	if err != nil {
		return nil, fmt.Errorf("create workflows created metric: %w", err)
	}

	workflowsUpdated, err := meter.Int64Counter(
		"n8n.workflows.updated_total",
		metric.WithDescription("Total number of workflows updated"))
	if err != nil {
		return nil, fmt.Errorf("create workflows updated metric: %w", err)
	}

	workflowsFailed, err := meter.Int64Counter(
		"n8n.workflows.failed_total",
		metric.WithDescription("Total number of workflows that failed to sync"))
	if err != nil {
		return nil, fmt.Errorf("create workflows failed metric: %w", err)
	}

	return &Syncer{
		config: config,
		tracer: otel.Tracer(tracerName),
		metrics: &metrics{
			syncDuration:     syncDuration,
			workflowsSynced:  workflowsSynced,
			workflowsCreated: workflowsCreated,
			workflowsUpdated: workflowsUpdated,
			workflowsFailed:  workflowsFailed,
		},
	}, nil
}

// Sync performs the workflow synchronization
func (s *Syncer) Sync(ctx context.Context) (*SyncResult, error) {
	ctx, span := s.tracer.Start(ctx, "sync.Sync")
	defer span.End()

	result := &SyncResult{}

	slog.InfoContext(ctx, "starting workflow sync",
		"workflow_dir", s.config.WorkflowDir,
		"managed_suffix", s.config.ManagedSuffix,
		"managed_tag", s.config.ManagedTag)

	// Wait for N8N to be ready
	if err := s.waitForN8N(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "n8n not ready")
		return nil, fmt.Errorf("wait for n8n: %w", err)
	}

	// Load workflows from filesystem
	workflows, err := s.loadWorkflows(ctx)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to load workflows")
		return nil, fmt.Errorf("load workflows: %w", err)
	}

	if len(workflows) == 0 {
		slog.InfoContext(ctx, "no workflows found to sync")
		span.SetStatus(codes.Ok, "no workflows to sync")
		return result, nil
	}

	span.SetAttributes(attribute.Int("workflows.total", len(workflows)))
	slog.InfoContext(ctx, "found workflows to sync", "count", len(workflows))

	// Get existing workflows from N8N
	workflowList, err := s.config.N8NClient.ListWorkflows(ctx, nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to list existing workflows")
		return nil, fmt.Errorf("list existing workflows: %w", err)
	}

	existingMap := make(map[string]*n8n.Workflow)
	if workflowList.Data != nil {
		for i := range *workflowList.Data {
			wf := &(*workflowList.Data)[i]
			existingMap[wf.Name] = wf
		}
	}

	// Sync each workflow
	for _, wf := range workflows {
		result.TotalProcessed++

		if err := s.syncWorkflow(ctx, wf, existingMap); err != nil {
			result.Failed++
			result.Errors = append(result.Errors, err)
			s.metrics.workflowsFailed.Add(ctx, 1, metric.WithAttributes(
				attribute.String("workflow.name", wf.Name)))
			slog.ErrorContext(ctx, "failed to sync workflow",
				"workflow", wf.Name,
				"error", err)
			continue
		}

		// Check if this was a create or update
		if existingMap[s.getManagedName(wf.Name)] != nil {
			result.Updated++
			s.metrics.workflowsUpdated.Add(ctx, 1, metric.WithAttributes(
				attribute.String("workflow.name", wf.Name)))
		} else {
			result.Created++
			s.metrics.workflowsCreated.Add(ctx, 1, metric.WithAttributes(
				attribute.String("workflow.name", wf.Name)))
		}
	}

	s.metrics.workflowsSynced.Add(ctx, int64(result.TotalProcessed-result.Failed))

	span.SetAttributes(
		attribute.Int("workflows.created", result.Created),
		attribute.Int("workflows.updated", result.Updated),
		attribute.Int("workflows.failed", result.Failed))

	if result.Failed > 0 {
		span.SetStatus(codes.Error, fmt.Sprintf("%d workflows failed to sync", result.Failed))
	} else {
		span.SetStatus(codes.Ok, "all workflows synced successfully")
	}

	slog.InfoContext(ctx, "workflow sync completed",
		"total", result.TotalProcessed,
		"created", result.Created,
		"updated", result.Updated,
		"failed", result.Failed)

	return result, nil
}

// waitForN8N waits for N8N to become ready
func (s *Syncer) waitForN8N(ctx context.Context) error {
	ctx, span := s.tracer.Start(ctx, "sync.waitForN8N")
	defer span.End()

	const maxRetries = 60
	for i := 0; i < maxRetries; i++ {
		if err := s.config.N8NClient.HealthCheck(ctx); err == nil {
			span.SetStatus(codes.Ok, "n8n is ready")
			slog.InfoContext(ctx, "n8n is ready")
			return nil
		}

		if i%10 == 0 {
			slog.InfoContext(ctx, "waiting for n8n to be ready", "attempt", i+1, "max", maxRetries)
		}

		select {
		case <-ctx.Done():
			span.RecordError(ctx.Err())
			span.SetStatus(codes.Error, "context cancelled")
			return ctx.Err()
		case <-time.After(2 * time.Second):
			continue
		}
	}

	err := fmt.Errorf("n8n failed to become ready after %d attempts", maxRetries)
	span.RecordError(err)
	span.SetStatus(codes.Error, "n8n not ready")
	return err
}

// loadWorkflows loads all workflow JSON files from the workflow directory
func (s *Syncer) loadWorkflows(ctx context.Context) ([]*n8n.Workflow, error) {
	ctx, span := s.tracer.Start(ctx, "sync.loadWorkflows")
	defer span.End()

	var workflows []*n8n.Workflow

	entries, err := os.ReadDir(s.config.WorkflowDir)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to read workflow directory")
		return nil, fmt.Errorf("read workflow directory: %w", err)
	}

	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}

		path := filepath.Join(s.config.WorkflowDir, entry.Name())
		data, err := os.ReadFile(path)
		if err != nil {
			span.RecordError(err)
			slog.WarnContext(ctx, "failed to read workflow file", "file", entry.Name(), "error", err)
			continue
		}

		var wf n8n.Workflow
		if err := json.Unmarshal(data, &wf); err != nil {
			span.RecordError(err)
			slog.WarnContext(ctx, "failed to parse workflow file", "file", entry.Name(), "error", err)
			continue
		}

		if wf.Name == "" {
			slog.WarnContext(ctx, "workflow has no name", "file", entry.Name())
			continue
		}

		workflows = append(workflows, &wf)
	}

	span.SetAttributes(attribute.Int("workflows.loaded", len(workflows)))
	span.SetStatus(codes.Ok, "workflows loaded")
	return workflows, nil
}

// syncWorkflow syncs a single workflow to N8N
func (s *Syncer) syncWorkflow(ctx context.Context, wf *n8n.Workflow, existingMap map[string]*n8n.Workflow) error {
	ctx, span := s.tracer.Start(ctx, "sync.syncWorkflow",
		trace.WithAttributes(attribute.String("workflow.name", wf.Name)))
	defer span.End()

	// Clean the workflow (remove instance-specific data)
	s.cleanWorkflow(wf)

	// Add managed suffix to name
	managedName := s.getManagedName(wf.Name)
	wf.Name = managedName

	slog.InfoContext(ctx, "syncing workflow",
		"original_name", strings.TrimSuffix(managedName, s.config.ManagedSuffix),
		"managed_name", managedName)

	// Check if workflow already exists
	if existing := existingMap[managedName]; existing != nil {
		// Update existing workflow
		existingID := ""
		if existing.Id != nil {
			existingID = *existing.Id
		}
		slog.InfoContext(ctx, "updating existing workflow", "id", existingID)
		span.SetAttributes(
			attribute.String("operation", "update"),
			attribute.String("workflow.id", existingID))

		_, err := s.config.N8NClient.UpdateWorkflow(ctx, existingID, *wf)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, "failed to update workflow")
			return fmt.Errorf("update workflow: %w", err)
		}

		// Ensure the workflow has the managed tag (in case it was removed manually)
		if err := s.ensureWorkflowHasManagedTag(ctx, existingID); err != nil {
			slog.WarnContext(ctx, "failed to ensure managed tag on updated workflow",
				"workflow_id", existingID,
				"error", err)
			// Don't fail the sync if tags can't be added
		}

		span.SetStatus(codes.Ok, "workflow updated")
		return nil
	}

	// Create new workflow
	slog.InfoContext(ctx, "creating new workflow")
	span.SetAttributes(attribute.String("operation", "create"))

	// Tags cannot be set during workflow creation - they must be added via the dedicated tags API
	wf.Tags = nil

	created, err := s.config.N8NClient.CreateWorkflow(ctx, *wf)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create workflow")
		return fmt.Errorf("create workflow: %w", err)
	}

	createdID := ""
	if created.Id != nil {
		createdID = *created.Id
	}
	span.SetAttributes(attribute.String("workflow.id", createdID))

	// Add the managed tag to the newly created workflow
	if err := s.ensureWorkflowHasManagedTag(ctx, createdID); err != nil {
		slog.WarnContext(ctx, "failed to add managed tag to workflow",
			"workflow_id", createdID,
			"error", err)
		// Don't fail the sync if tags can't be added - the workflow is created successfully
	}

	span.SetStatus(codes.Ok, "workflow created")
	return nil
}

// cleanWorkflow removes instance-specific data from a workflow
func (s *Syncer) cleanWorkflow(wf *n8n.Workflow) {
	// Remove ID (will be assigned by N8N or preserved on update)
	wf.Id = nil

	// Remove webhookId from all nodes
	// webhookId is an instance-specific identifier that is regenerated by n8n on workflow import,
	// so it must be removed to avoid persisting instance-specific data.
	for i := range wf.Nodes {
		wf.Nodes[i].WebhookId = nil
	}
}

// getManagedName returns the managed name for a workflow
func (s *Syncer) getManagedName(originalName string) string {
	return originalName + s.config.ManagedSuffix
}

// getOrCreateManagedTag ensures the managed tag exists and returns its ID
func (s *Syncer) getOrCreateManagedTag(ctx context.Context) (string, error) {
	ctx, span := s.tracer.Start(ctx, "sync.getOrCreateManagedTag")
	defer span.End()

	// Return cached tag ID if available
	if s.managedTagID != "" {
		span.SetStatus(codes.Ok, "using cached tag ID")
		return s.managedTagID, nil
	}

	// List all tags to find the managed tag
	tagList, err := s.config.N8NClient.ListTags(ctx, nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to list tags")
		return "", fmt.Errorf("list tags: %w", err)
	}

	// Check if the managed tag already exists
	if tagList.Data != nil {
		for _, tag := range *tagList.Data {
			if tag.Name == s.config.ManagedTag {
				tagID := ""
				if tag.Id != nil {
					tagID = *tag.Id
				}
				s.managedTagID = tagID
				span.SetAttributes(attribute.String("tag.id", tagID))
				span.SetStatus(codes.Ok, "found existing managed tag")
				slog.InfoContext(ctx, "found existing managed tag", "tag_id", tagID, "tag_name", tag.Name)
				return tagID, nil
			}
		}
	}

	// Create the managed tag if it doesn't exist
	slog.InfoContext(ctx, "creating managed tag", "tag_name", s.config.ManagedTag)
	created, err := s.config.N8NClient.CreateTag(ctx, n8n.Tag{
		Name: s.config.ManagedTag,
	})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create tag")
		return "", fmt.Errorf("create tag: %w", err)
	}

	createdTagID := ""
	if created.Id != nil {
		createdTagID = *created.Id
	}
	s.managedTagID = createdTagID
	span.SetAttributes(attribute.String("tag.id", createdTagID))
	span.SetStatus(codes.Ok, "created managed tag")
	slog.InfoContext(ctx, "created managed tag", "tag_id", createdTagID, "tag_name", created.Name)

	return createdTagID, nil
}

// ensureWorkflowHasManagedTag ensures the workflow has the managed tag
func (s *Syncer) ensureWorkflowHasManagedTag(ctx context.Context, workflowID string) error {
	ctx, span := s.tracer.Start(ctx, "sync.ensureWorkflowHasManagedTag",
		trace.WithAttributes(attribute.String("workflow.id", workflowID)))
	defer span.End()

	// Get or create the managed tag
	tagID, err := s.getOrCreateManagedTag(ctx)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get managed tag")
		return fmt.Errorf("get managed tag: %w", err)
	}

	// Get current workflow tags
	currentTags, err := s.config.N8NClient.GetWorkflowTags(ctx, workflowID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get workflow tags")
		return fmt.Errorf("get workflow tags: %w", err)
	}

	// Check if the workflow already has the managed tag
	hasTag := false
	tagIDs := make(n8n.TagIds, 0, len(currentTags)+1)
	for _, tag := range currentTags {
		currentTagID := ""
		if tag.Id != nil {
			currentTagID = *tag.Id
		}
		tagIDs = append(tagIDs, struct {
			Id string `json:"id"`
		}{Id: currentTagID})
		if currentTagID == tagID {
			hasTag = true
		}
	}

	if hasTag {
		span.SetStatus(codes.Ok, "workflow already has managed tag")
		slog.InfoContext(ctx, "workflow already has managed tag", "workflow_id", workflowID)
		return nil
	}

	// Add the managed tag to the workflow
	tagIDs = append(tagIDs, struct {
		Id string `json:"id"`
	}{Id: tagID})
	_, err = s.config.N8NClient.UpdateWorkflowTags(ctx, workflowID, tagIDs)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to update workflow tags")
		return fmt.Errorf("update workflow tags: %w", err)
	}

	span.SetStatus(codes.Ok, "added managed tag to workflow")
	slog.InfoContext(ctx, "added managed tag to workflow", "workflow_id", workflowID, "tag_id", tagID)

	return nil
}
