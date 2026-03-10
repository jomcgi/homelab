package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	signozURL := envOr("SIGNOZ_URL", "http://signoz.signoz.svc.cluster.local:8080")
	signozToken := os.Getenv("SIGNOZ_API_KEY")
	orchestratorURL := envOr("ORCHESTRATOR_URL", "http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080")
	httpPort := envOr("HTTP_PORT", "8080")
	patrolInterval := envDurationOr("PATROL_INTERVAL", 1*time.Hour)

	collector := NewAlertCollector(signozURL, signozToken)
	orchestrator := NewOrchestratorClient(orchestratorURL)
	escalator := NewEscalator(orchestrator)

	patrol := NewPatrolAgent(collector, escalator, patrolInterval)
	runner := NewRunner([]Agent{patrol})

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})

	srv := &http.Server{Addr: ":" + httpPort, Handler: mux}
	go func() {
		slog.Info("http server starting", "port", httpPort)
		if err := srv.ListenAndServe(); err != http.ErrServerClosed {
			slog.Error("http server error", "error", err)
		}
	}()

	slog.Info("cluster-agents starting", "patrol_interval", patrolInterval)
	runner.Run(ctx)

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	srv.Shutdown(shutdownCtx)
	slog.Info("cluster-agents stopped")
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envDurationOr(key string, fallback time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			slog.Warn("invalid duration, using default", "key", key, "value", v, "default", fallback)
			return fallback
		}
		return d
	}
	return fallback
}
