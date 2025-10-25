package telemetry

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
)

// Config holds telemetry configuration
type Config struct {
	ServiceName    string
	ServiceVersion string
	OTLPEndpoint   string
	Enabled        bool
}

// Shutdown is a function that shuts down telemetry
type Shutdown func(context.Context) error

// Setup initializes OpenTelemetry tracing and metrics
func Setup(ctx context.Context, config Config) (Shutdown, error) {
	if !config.Enabled {
		slog.Info("OpenTelemetry disabled, using no-op providers")
		return func(context.Context) error { return nil }, nil
	}

	// Create resource
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(config.ServiceName),
			semconv.ServiceVersion(config.ServiceVersion),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("create resource: %w", err)
	}

	// Create OTLP trace exporter
	traceExporter, err := otlptrace.New(ctx,
		otlptracegrpc.NewClient(
			otlptracegrpc.WithEndpoint(config.OTLPEndpoint),
			otlptracegrpc.WithInsecure(), // SigNoz typically uses insecure gRPC internally
		),
	)
	if err != nil {
		return nil, fmt.Errorf("create trace exporter: %w", err)
	}

	// Create trace provider
	traceProvider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(traceExporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
	)

	// Set global trace provider
	otel.SetTracerProvider(traceProvider)

	slog.Info("OpenTelemetry initialized",
		"service", config.ServiceName,
		"version", config.ServiceVersion,
		"otlp_endpoint", config.OTLPEndpoint)

	// Return shutdown function
	return func(ctx context.Context) error {
		slog.Info("shutting down OpenTelemetry")

		shutdownCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()

		if err := traceProvider.Shutdown(shutdownCtx); err != nil {
			return fmt.Errorf("shutdown trace provider: %w", err)
		}

		return nil
	}, nil
}
