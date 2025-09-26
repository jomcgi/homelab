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

package main

import (
	"context"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	"go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.uber.org/zap"

	"github.com/jomcgi/homelab/charts/obsidian-automation/monitor/internal/monitor"
	"github.com/jomcgi/homelab/charts/obsidian-automation/monitor/internal/telemetry"
)

var (
	metricsAddr        = flag.String("metrics-addr", ":8080", "The address the metrics endpoint binds to")
	probeAddr          = flag.String("probe-addr", ":8081", "The address the health probe endpoint binds to")
	obsidianAPIURL     = flag.String("obsidian-api-url", "http://localhost:27124", "The Obsidian REST API URL")
	checkInterval      = flag.Duration("check-interval", 5*time.Minute, "Sync status check interval")
	syntheticInterval  = flag.Duration("synthetic-interval", 5*time.Minute, "Synthetic test interval")
	otlpEndpoint       = flag.String("otlp-endpoint", "", "OpenTelemetry OTLP endpoint (optional)")
	logLevel           = flag.String("log-level", "info", "Log level (debug, info, warn, error)")
)

func main() {
	flag.Parse()

	logger, err := setupLogger(*logLevel)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to setup logger: %v\n", err)
		os.Exit(1)
	}
	defer logger.Sync()

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Initialize OpenTelemetry tracing if endpoint is provided
	var tracerProvider *trace.TracerProvider
	if *otlpEndpoint != "" {
		tp, err := setupTracing(ctx, *otlpEndpoint)
		if err != nil {
			logger.Error("Failed to setup tracing", zap.Error(err))
			os.Exit(1)
		}
		tracerProvider = tp
		defer func() {
			if err := tp.Shutdown(ctx); err != nil {
				logger.Error("Failed to shutdown tracer provider", zap.Error(err))
			}
		}()
	}

	// Get API key from environment
	apiKey := os.Getenv("OBSIDIAN_API_KEY")
	if apiKey == "" {
		logger.Error("OBSIDIAN_API_KEY environment variable is required")
		os.Exit(1)
	}

	// Initialize telemetry
	tel := telemetry.New()

	// Initialize sync monitor
	monitor := monitor.New(monitor.Config{
		ObsidianAPIURL:    *obsidianAPIURL,
		APIKey:            apiKey,
		CheckInterval:     *checkInterval,
		SyntheticInterval: *syntheticInterval,
		Logger:            logger,
		Telemetry:         tel,
	})

	// Start monitor
	monitorCtx, monitorCancel := context.WithCancel(ctx)
	defer monitorCancel()

	go func() {
		if err := monitor.Start(monitorCtx); err != nil {
			logger.Error("Monitor failed", zap.Error(err))
			cancel()
		}
	}()

	// Start metrics server
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if monitor.IsHealthy() {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("OK"))
		} else {
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte("Service Unavailable"))
		}
	})
	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		if monitor.IsReady() {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Ready"))
		} else {
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte("Not Ready"))
		}
	})

	metricsServer := &http.Server{
		Addr:    *metricsAddr,
		Handler: mux,
	}

	probeServer := &http.Server{
		Addr: *probeAddr,
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			switch r.URL.Path {
			case "/health":
				if monitor.IsHealthy() {
					w.WriteHeader(http.StatusOK)
					w.Write([]byte("OK"))
				} else {
					w.WriteHeader(http.StatusServiceUnavailable)
					w.Write([]byte("Service Unavailable"))
				}
			case "/ready":
				if monitor.IsReady() {
					w.WriteHeader(http.StatusOK)
					w.Write([]byte("Ready"))
				} else {
					w.WriteHeader(http.StatusServiceUnavailable)
					w.Write([]byte("Not Ready"))
				}
			default:
				w.WriteHeader(http.StatusNotFound)
				w.Write([]byte("Not Found"))
			}
		}),
	}

	// Start servers
	go func() {
		logger.Info("Starting metrics server", zap.String("addr", *metricsAddr))
		if err := metricsServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("Metrics server failed", zap.Error(err))
			cancel()
		}
	}()

	go func() {
		logger.Info("Starting probe server", zap.String("addr", *probeAddr))
		if err := probeServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("Probe server failed", zap.Error(err))
			cancel()
		}
	}()

	logger.Info("Sync monitor started")

	// Wait for shutdown signal
	<-ctx.Done()
	logger.Info("Shutting down sync monitor")

	// Graceful shutdown
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()

	if err := metricsServer.Shutdown(shutdownCtx); err != nil {
		logger.Error("Failed to shutdown metrics server", zap.Error(err))
	}

	if err := probeServer.Shutdown(shutdownCtx); err != nil {
		logger.Error("Failed to shutdown probe server", zap.Error(err))
	}

	logger.Info("Sync monitor stopped")
}

func setupLogger(level string) (*zap.Logger, error) {
	config := zap.NewProductionConfig()
	config.Level = zap.NewAtomicLevelAt(zapLevel(level))
	return config.Build()
}

func zapLevel(level string) zap.Level {
	switch level {
	case "debug":
		return zap.DebugLevel
	case "info":
		return zap.InfoLevel
	case "warn":
		return zap.WarnLevel
	case "error":
		return zap.ErrorLevel
	default:
		return zap.InfoLevel
	}
}

func setupTracing(ctx context.Context, endpoint string) (*trace.TracerProvider, error) {
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName("obsidian-sync-monitor"),
			semconv.ServiceVersion("1.0.0"),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create resource: %w", err)
	}

	traceExporter, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpoint(endpoint),
		otlptracehttp.WithInsecure(),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create trace exporter: %w", err)
	}

	tracerProvider := trace.NewTracerProvider(
		trace.WithBatcher(traceExporter),
		trace.WithResource(res),
	)

	otel.SetTracerProvider(tracerProvider)

	return tracerProvider, nil
}