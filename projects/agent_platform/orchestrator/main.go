package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"math"
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
	reconcileInterval, err := time.ParseDuration(envOr("RECONCILE_INTERVAL", "60s"))
	if err != nil {
		logger.Error("invalid RECONCILE_INTERVAL", "error", err)
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

	// Set up JetStream resources with retry. During rolling deployments,
	// NATS may not be fully ready when the orchestrator starts — retrying
	// with backoff avoids a crash loop.
	kv, cons, err := setupJetStream(ctx, js, maxConcurrent, logger)
	if err != nil {
		logger.Error("failed to set up JetStream resources", "error", err)
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

	inferenceURL := envOr("INFERENCE_URL", "")
	inferenceModel := envOr("INFERENCE_MODEL", "")

	var summarizer *Summarizer
	if inferenceURL != "" {
		summarizer = NewSummarizer(inferenceURL, inferenceModel, logger)
		logger.Info("summarizer enabled", "url", inferenceURL, "model", inferenceModel)
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

	// Reconcile orphaned jobs before starting the consumer, then
	// continue reconciling periodically. After a restart, the initial
	// pass may find runners still active ("running") and leave them
	// alone. The periodic loop catches those jobs once the runner
	// finishes — without it, completed jobs stay stuck in RUNNING
	// forever because the consumer only processes PENDING jobs.
	if sandbox != nil {
		reconcileOrphanedJobs(ctx, store, sandbox.dynClient, sandboxNamespace, sandbox.CheckRunnerForClaim, sandbox.FetchOutputForClaim, maxDuration, logger)
		go runPeriodicReconcile(ctx, reconcileInterval, store, sandbox, sandboxNamespace, maxDuration, logger)
	}

	// Start consumer if sandbox is available.
	if sandbox != nil {
		consumer := NewConsumer(cons, store, sandbox, publish, summarizer, maxDuration, logger)
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

// jetStreamSetup is the subset of jetstream.JetStream needed for resource setup.
type jetStreamSetup interface {
	CreateOrUpdateStream(ctx context.Context, cfg jetstream.StreamConfig) (jetstream.Stream, error)
	CreateOrUpdateKeyValue(ctx context.Context, cfg jetstream.KeyValueConfig) (jetstream.KeyValue, error)
	CreateOrUpdateConsumer(ctx context.Context, stream string, cfg jetstream.ConsumerConfig) (jetstream.Consumer, error)
}

func setupJetStream(ctx context.Context, js jetStreamSetup, maxConcurrent int, logger *slog.Logger) (jetstream.KeyValue, jetstream.Consumer, error) {
	const maxAttempts = 10

	var (
		kv   jetstream.KeyValue
		cons jetstream.Consumer
	)

	for attempt := range maxAttempts {
		if err := ctx.Err(); err != nil {
			return nil, nil, err
		}

		setupCtx, cancel := context.WithTimeout(ctx, 10*time.Second)

		_, err := js.CreateOrUpdateStream(setupCtx, jetstream.StreamConfig{
			Name:      streamName,
			Subjects:  []string{subject},
			Retention: jetstream.WorkQueuePolicy,
			MaxMsgs:   1000,
		})
		if err != nil {
			cancel()
			if errors.Is(err, context.Canceled) {
				return nil, nil, err
			}
			backoff := time.Duration(math.Min(float64(time.Second)*math.Pow(2, float64(attempt)), float64(30*time.Second)))
			logger.Warn("JetStream not ready, retrying", "attempt", attempt+1, "backoff", backoff, "error", err)
			select {
			case <-time.After(backoff):
				continue
			case <-ctx.Done():
				return nil, nil, ctx.Err()
			}
		}

		kv, err = js.CreateOrUpdateKeyValue(setupCtx, jetstream.KeyValueConfig{
			Bucket: kvBucket,
			TTL:    7 * 24 * time.Hour,
		})
		if err != nil {
			cancel()
			return nil, nil, fmt.Errorf("create KV bucket: %w", err)
		}

		cons, err = js.CreateOrUpdateConsumer(setupCtx, streamName, jetstream.ConsumerConfig{
			Name:          "orchestrator",
			Durable:       "orchestrator",
			AckPolicy:     jetstream.AckExplicitPolicy,
			MaxAckPending: maxConcurrent,
			AckWait:       2 * time.Minute,
		})
		cancel()
		if err != nil {
			return nil, nil, fmt.Errorf("create consumer: %w", err)
		}

		return kv, cons, nil
	}

	return nil, nil, fmt.Errorf("JetStream setup failed after %d attempts", maxAttempts)
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// runPeriodicReconcile runs reconcileOrphanedJobs on a ticker until ctx is
// cancelled. This catches jobs whose runners finish after the startup
// reconciliation pass — without it, those jobs stay RUNNING forever.
func runPeriodicReconcile(ctx context.Context, interval time.Duration, store Store, sandbox *SandboxExecutor, namespace string, maxDuration time.Duration, logger *slog.Logger) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	logger.Info("periodic reconciler started", "interval", interval)

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			reconcileOrphanedJobs(ctx, store, sandbox.dynClient, namespace, sandbox.CheckRunnerForClaim, sandbox.FetchOutputForClaim, maxDuration, logger)
		}
	}
}
