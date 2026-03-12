package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
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

	// GitHub config for improvement agents
	githubToken := os.Getenv("GITHUB_TOKEN")
	githubRepo := envOr("GITHUB_REPO", "jomcgi/homelab")
	githubBranch := envOr("GITHUB_BRANCH", "main")
	botAuthors := strings.Split(envOr("BOT_AUTHORS", "ci-format-bot,argocd-image-updater,chart-version-bot"), ",")

	testCoverageInterval := envDurationOr("TEST_COVERAGE_INTERVAL", 1*time.Hour)
	readmeFreshnessInterval := envDurationOr("README_FRESHNESS_INTERVAL", 168*time.Hour)
	rulesInterval := envDurationOr("RULES_INTERVAL", 24*time.Hour)
	prFixInterval := envDurationOr("PR_FIX_INTERVAL", 1*time.Hour)
	prFixStaleThreshold := envDurationOr("PR_FIX_STALE_THRESHOLD", 1*time.Hour)

	githubClient := NewGitHubClient("https://api.github.com", githubToken, githubRepo)

	gate := NewGitActivityGate(githubClient, orchestrator, botAuthors, githubBranch)

	agents := []Agent{
		patrol,
		NewTestCoverageAgent(gate, escalator, testCoverageInterval),
		NewReadmeFreshnessAgent(gate, escalator, readmeFreshnessInterval),
		NewRulesAgent(gate, escalator, rulesInterval),
		NewPRFixAgent(githubClient, orchestrator, escalator, prFixInterval, prFixStaleThreshold),
	}

	runner := NewRunner(agents)

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

	slog.Info("cluster-agents starting",
		"agent_count", len(agents),
		"patrol_interval", patrolInterval,
		"test_coverage_interval", testCoverageInterval,
		"readme_freshness_interval", readmeFreshnessInterval,
		"rules_interval", rulesInterval,
		"pr_fix_interval", prFixInterval,
		"pr_fix_stale_threshold", prFixStaleThreshold,
	)
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
