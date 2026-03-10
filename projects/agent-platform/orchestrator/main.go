package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"k8s.io/client-go/rest"
)

const (
	streamName = "agent-jobs"
	subject    = "agent.jobs"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	natsURL := envOr("NATS_URL", "nats://localhost:4222")
	sandboxNamespace := envOr("SANDBOX_NAMESPACE", "goose-sandboxes")
	sandboxTemplate := envOr("SANDBOX_TEMPLATE", "goose-agent")
	maxRetries, _ := strconv.Atoi(envOr("MAX_RETRIES", "2"))
	maxConcurrent, _ := strconv.Atoi(envOr("MAX_CONCURRENT", "3"))
	httpPort := envOr("HTTP_PORT", "8080")

	inactivityTimeout, err := time.ParseDuration(envOr("JOB_INACTIVITY_TIMEOUT", "10m"))
	if err != nil {
		logger.Error("invalid JOB_INACTIVITY_TIMEOUT", "error", err)
		os.Exit(1)
	}
	maxDuration, err := time.ParseDuration(envOr("JOB_MAX_DURATION", "168h"))
	if err != nil {
		logger.Error("invalid JOB_MAX_DURATION", "error", err)
		os.Exit(1)
	}

	// Connect to NATS.
	nc, err := nats.Connect(natsURL,
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
	)
	if err != nil {
		logger.Error("failed to connect to NATS", "error", err)
		os.Exit(1)
	}
	defer nc.Close()
	logger.Info("connected to NATS", "url", natsURL)

	js, err := jetstream.New(nc)
	if err != nil {
		logger.Error("failed to create JetStream context", "error", err)
		os.Exit(1)
	}

	// Create or update stream.
	_, err = js.CreateOrUpdateStream(ctx, jetstream.StreamConfig{
		Name:      streamName,
		Subjects:  []string{subject},
		Retention: jetstream.WorkQueuePolicy,
		MaxMsgs:   1000,
	})
	if err != nil {
		logger.Error("failed to create stream", "error", err)
		os.Exit(1)
	}

	// Create or update KV bucket.
	kv, err := js.CreateOrUpdateKeyValue(ctx, jetstream.KeyValueConfig{
		Bucket: kvBucket,
		TTL:    7 * 24 * time.Hour,
	})
	if err != nil {
		logger.Error("failed to create KV bucket", "error", err)
		os.Exit(1)
	}

	// Create durable pull consumer.
	cons, err := js.CreateOrUpdateConsumer(ctx, streamName, jetstream.ConsumerConfig{
		Name:          "orchestrator",
		Durable:       "orchestrator",
		AckPolicy:     jetstream.AckExplicitPolicy,
		MaxAckPending: maxConcurrent,
		AckWait:       2 * time.Minute,
	})
	if err != nil {
		logger.Error("failed to create consumer", "error", err)
		os.Exit(1)
	}

	// Try in-cluster Kubernetes config. If unavailable, run in API-only mode.
	var k8sConfig *rest.Config
	k8sConfig, err = rest.InClusterConfig()
	if err != nil {
		logger.Warn("kubernetes in-cluster config not available, sandbox execution disabled", "error", err)
		k8sConfig = nil
	}

	store := NewJobStore(kv, logger)

	var sandbox *SandboxExecutor
	if k8sConfig != nil {
		sandbox, err = NewSandboxExecutor(k8sConfig, sandboxNamespace, sandboxTemplate, inactivityTimeout, logger)
		if err != nil {
			logger.Error("failed to create sandbox executor", "error", err)
			os.Exit(1)
		}
	}

	publish := func(jobID string) error {
		_, err := js.Publish(ctx, subject, []byte(jobID))
		return err
	}

	healthCheck := func() error {
		_, err := kv.Status(ctx)
		return err
	}

	api := NewAPI(store, publish, healthCheck, maxRetries, logger)
	mux := http.NewServeMux()
	api.RegisterRoutes(mux)
	registerUI(mux)

	srv := &http.Server{
		Addr:              ":" + httpPort,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	// Reconcile orphaned jobs before starting the consumer.
	// After a restart, jobs left in RUNNING state may still have active
	// runners (HTTP) or may be truly orphaned. Check runner status first,
	// then reset stale jobs for retry.
	if sandbox != nil {
		reconcileOrphanedJobs(ctx, store, sandbox.dynClient, sandboxNamespace, sandbox.CheckRunnerForClaim, logger)
	}

	// Start consumer if sandbox is available.
	if sandbox != nil {
		consumer := NewConsumer(cons, store, sandbox, maxDuration, logger)
		go consumer.Run(ctx)
	} else {
		logger.Info("running in API-only mode (no sandbox executor)")
	}

	// Graceful shutdown.
	go func() {
		<-ctx.Done()
		logger.Info("shutting down HTTP server")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			logger.Error("HTTP server shutdown error", "error", err)
		}
	}()

	logger.Info("starting HTTP server", "port", httpPort)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Error("HTTP server error", "error", err)
		os.Exit(1)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
