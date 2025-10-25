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

package telemetry

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

// InitializeTracing sets up OpenTelemetry tracing using standard OTEL environment variables:
//
// - OTEL_SDK_DISABLED (default: false) - Set to "true" to disable tracing entirely
// - OTEL_EXPORTER_OTLP_ENDPOINT (required if enabled) - OTLP endpoint (e.g., "otel-collector:4317")
// - OTEL_SERVICE_NAME (default: "cloudflare-operator") - Service name
// - OTEL_SERVICE_VERSION (default: "dev") - Service version
// - OTEL_TRACES_SAMPLER (default: "parentbased_traceidratio") - Sampler type
// - OTEL_TRACES_SAMPLER_ARG (default: "1.0") - Sampler argument (e.g., "0.1" for 10%)
func InitializeTracing(ctx context.Context) (*sdktrace.TracerProvider, error) {
	// Check if SDK is disabled via standard env var
	if os.Getenv("OTEL_SDK_DISABLED") == "true" {
		return sdktrace.NewTracerProvider(), nil
	}

	// Get OTLP endpoint from standard env var
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		// Tracing is disabled if no endpoint is configured
		return sdktrace.NewTracerProvider(), nil
	}

	// Get service name and version from standard env vars
	serviceName := os.Getenv("OTEL_SERVICE_NAME")
	if serviceName == "" {
		serviceName = "cloudflare-operator"
	}

	serviceVersion := os.Getenv("OTEL_SERVICE_VERSION")
	if serviceVersion == "" {
		serviceVersion = "dev"
	}

	// Get sampler configuration from standard env vars
	samplerType := os.Getenv("OTEL_TRACES_SAMPLER")
	if samplerType == "" {
		samplerType = "parentbased_traceidratio"
	}

	samplerArg := os.Getenv("OTEL_TRACES_SAMPLER_ARG")
	if samplerArg == "" {
		samplerArg = "1.0" // 100% sampling by default
	}

	// Parse sampler argument
	sampleRate, err := strconv.ParseFloat(samplerArg, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid OTEL_TRACES_SAMPLER_ARG %q: %w", samplerArg, err)
	}

	// Create OTLP exporter - uses OTEL_EXPORTER_OTLP_* env vars automatically
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(endpoint),
		otlptracegrpc.WithInsecure(), // Use OTEL_EXPORTER_OTLP_INSECURE=false for TLS
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create OTLP exporter: %w", err)
	}

	// Create resource with service information using schemaless attributes
	// to avoid schema version conflicts between dependencies
	res, err := resource.Merge(
		resource.Default(),
		resource.NewSchemaless(
			attribute.String("service.name", serviceName),
			attribute.String("service.version", serviceVersion),
			attribute.String("k8s.operator.type", "custom-controller"),
			attribute.String("k8s.operator.name", "cloudflare-operator"),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create resource: %w", err)
	}

	// Create sampler based on configuration
	var sampler sdktrace.Sampler
	switch samplerType {
	case "always_on":
		sampler = sdktrace.AlwaysSample()
	case "always_off":
		sampler = sdktrace.NeverSample()
	case "traceidratio":
		sampler = sdktrace.TraceIDRatioBased(sampleRate)
	case "parentbased_always_on":
		sampler = sdktrace.ParentBased(sdktrace.AlwaysSample())
	case "parentbased_always_off":
		sampler = sdktrace.ParentBased(sdktrace.NeverSample())
	case "parentbased_traceidratio":
		sampler = sdktrace.ParentBased(sdktrace.TraceIDRatioBased(sampleRate))
	default:
		return nil, fmt.Errorf("unknown OTEL_TRACES_SAMPLER: %s", samplerType)
	}

	// Create tracer provider
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sampler),
	)

	// Set global tracer provider
	otel.SetTracerProvider(tp)

	return tp, nil
}

// Shutdown gracefully shuts down the tracer provider
func Shutdown(ctx context.Context, tp *sdktrace.TracerProvider) error {
	if tp == nil {
		return nil
	}

	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	if err := tp.Shutdown(ctx); err != nil {
		return fmt.Errorf("failed to shutdown tracer provider: %w", err)
	}

	return nil
}

// GetTracer returns a tracer for the given name
func GetTracer(name string) trace.Tracer {
	return otel.Tracer(name)
}
