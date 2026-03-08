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

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	natsURL := envOr("NATS_URL", "nats://nats.nats.svc.cluster.local:4222")
	llmURL := envOr("LLM_URL", "http://llama-cpp.llama-cpp.svc.cluster.local:8080")
	llmModel := envOr("LLM_MODEL", "default")
	argocdURL := envOr("ARGOCD_URL", "http://argocd-server.argocd.svc.cluster.local")
	argocdToken := os.Getenv("ARGOCD_TOKEN")
	orchestratorURL := envOr("ORCHESTRATOR_URL", "http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080")
	githubToken := os.Getenv("GITHUB_TOKEN")
	githubRepo := envOr("GITHUB_REPO", "jomcgi/homelab")
	httpPort := envOr("HTTP_PORT", "8080")
	patrolInterval := envDurationOr("PATROL_INTERVAL", 5*time.Minute)

	nc, err := nats.Connect(natsURL)
	if err != nil {
		slog.Error("failed to connect to NATS", "error", err)
		os.Exit(1)
	}
	defer nc.Close()

	js, err := jetstream.New(nc)
	if err != nil {
		slog.Error("failed to create jetstream context", "error", err)
		os.Exit(1)
	}

	kv, err := js.CreateOrUpdateKeyValue(ctx, jetstream.KeyValueConfig{
		Bucket: "cluster-agents-findings",
		TTL:    48 * time.Hour,
	})
	if err != nil {
		slog.Error("failed to create KV bucket", "error", err)
		os.Exit(1)
	}

	k8sConfig, err := rest.InClusterConfig()
	if err != nil {
		slog.Error("failed to get in-cluster config", "error", err)
		os.Exit(1)
	}
	k8sClient, err := kubernetes.NewForConfig(k8sConfig)
	if err != nil {
		slog.Error("failed to create kubernetes client", "error", err)
		os.Exit(1)
	}

	store := NewNATSFindingsStore(kv)
	llm := NewLLMClient(llmURL, llmModel)

	var github *GitHubClient
	if githubToken != "" {
		github = NewGitHubClient(githubToken, githubRepo)
	}
	orchestrator := NewOrchestratorClient(orchestratorURL)
	escalator := NewEscalator(store, github, orchestrator)

	collectors := []collector{
		NewK8sCollector(k8sClient),
		NewArgoCDCollector(argocdURL, argocdToken),
	}

	patrol := NewPatrolAgent(collectors, llm, escalator, patrolInterval)
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
