package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jomcgi/homelab/charts/n8n/syncer/internal/sync"
	"github.com/jomcgi/homelab/charts/n8n/syncer/internal/telemetry"
	"github.com/jomcgi/homelab/pkg/n8n"
)

const (
	serviceName    = "n8n-workflow-syncer"
	serviceVersion = "1.1.0"
)

func main() {
	// Parse command line flags
	var (
		n8nURL         = flag.String("n8n-url", getEnv("N8N_URL", "http://localhost:5678"), "N8N API URL")
		n8nAPIKey      = flag.String("n8n-api-key", getEnv("N8N_API_KEY", ""), "N8N API key")
		workflowDir    = flag.String("workflow-dir", getEnv("WORKFLOW_DIR", "/workflows"), "Directory containing workflow JSON files")
		managedSuffix  = flag.String("managed-suffix", getEnv("MANAGED_SUFFIX", " [git-managed]"), "Suffix to append to managed workflow names")
		managedTag     = flag.String("managed-tag", getEnv("MANAGED_TAG", "gitops-managed"), "Tag to add to managed workflows")
		otlpEndpoint   = flag.String("otlp-endpoint", getEnv("OTLP_ENDPOINT", ""), "OpenTelemetry OTLP endpoint (e.g., signoz:4317)")
		logLevel       = flag.String("log-level", getEnv("LOG_LEVEL", "info"), "Log level (debug, info, warn, error)")
		enableTelemetry = flag.Bool("enable-telemetry", getEnv("ENABLE_TELEMETRY", "true") == "true", "Enable OpenTelemetry tracing")
	)
	flag.Parse()

	// Setup structured logging
	setupLogging(*logLevel)

	slog.Info("starting n8n workflow syncer",
		"version", serviceVersion,
		"n8n_url", *n8nURL,
		"workflow_dir", *workflowDir,
		"managed_suffix", *managedSuffix,
		"managed_tag", *managedTag,
		"telemetry_enabled", *enableTelemetry)

	// Validate required flags
	if *n8nAPIKey == "" {
		slog.Error("N8N_API_KEY is required")
		os.Exit(1)
	}

	// Create context with cancellation
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Handle shutdown signals
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	go func() {
		sig := <-sigCh
		slog.Info("received shutdown signal", "signal", sig)
		cancel()
	}()

	// Setup OpenTelemetry
	var shutdownTelemetry telemetry.Shutdown
	if *enableTelemetry && *otlpEndpoint != "" {
		var err error
		shutdownTelemetry, err = telemetry.Setup(ctx, telemetry.Config{
			ServiceName:    serviceName,
			ServiceVersion: serviceVersion,
			OTLPEndpoint:   *otlpEndpoint,
			Enabled:        true,
		})
		if err != nil {
			slog.Error("failed to setup telemetry", "error", err)
			os.Exit(1)
		}
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			if err := shutdownTelemetry(shutdownCtx); err != nil {
				slog.Error("failed to shutdown telemetry", "error", err)
			}
		}()
	} else {
		slog.Info("OpenTelemetry disabled")
	}

	// Create N8N client
	n8nClient, err := n8n.NewObservableClient(*n8nURL, *n8nAPIKey)
	if err != nil {
		slog.Error("failed to create n8n client", "error", err)
		os.Exit(1)
	}

	// Create syncer
	syncer, syncErr := sync.NewSyncer(sync.Config{
		WorkflowDir:   *workflowDir,
		ManagedSuffix: *managedSuffix,
		ManagedTag:    *managedTag,
		N8NClient:     n8nClient,
	})
	if syncErr != nil {
		slog.Error("failed to create syncer", "error", syncErr)
		os.Exit(1)
	}

	// Perform sync
	slog.Info("starting workflow sync")
	startTime := time.Now()

	result, err := syncer.Sync(ctx)
	if err != nil {
		slog.Error("sync failed", "error", err)
		os.Exit(1)
	}

	duration := time.Since(startTime)

	// Log results
	slog.Info("workflow sync completed",
		"duration_seconds", duration.Seconds(),
		"total_processed", result.TotalProcessed,
		"created", result.Created,
		"updated", result.Updated,
		"failed", result.Failed)

	// Exit with error if any workflows failed
	if result.Failed > 0 {
		slog.Error("some workflows failed to sync", "failed_count", result.Failed)
		for i, err := range result.Errors {
			slog.Error(fmt.Sprintf("error %d", i+1), "error", err)
		}
		os.Exit(1)
	}

	slog.Info("all workflows synced successfully")
}

// setupLogging configures structured logging
func setupLogging(level string) {
	var logLevel slog.Level
	switch level {
	case "debug":
		logLevel = slog.LevelDebug
	case "info":
		logLevel = slog.LevelInfo
	case "warn":
		logLevel = slog.LevelWarn
	case "error":
		logLevel = slog.LevelError
	default:
		logLevel = slog.LevelInfo
	}

	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: logLevel,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			// Rename "msg" to "message" for better compatibility with log aggregators
			if a.Key == slog.MessageKey {
				a.Key = "message"
			}
			return a
		},
	})

	logger := slog.New(handler)
	slog.SetDefault(logger)
}

// getEnv gets an environment variable with a default value
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
