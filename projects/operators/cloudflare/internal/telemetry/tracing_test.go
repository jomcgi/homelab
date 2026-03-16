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
	"os"
	"testing"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

func TestTelemetry(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Telemetry Suite")
}

// clearTracingEnv resets all OTEL-related environment variables used by InitializeTracing.
func clearTracingEnv() {
	_ = os.Unsetenv("OTEL_SDK_DISABLED")
	_ = os.Unsetenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	_ = os.Unsetenv("OTEL_SERVICE_NAME")
	_ = os.Unsetenv("OTEL_SERVICE_VERSION")
	_ = os.Unsetenv("OTEL_TRACES_SAMPLER")
	_ = os.Unsetenv("OTEL_TRACES_SAMPLER_ARG")
}

// =============================================================================
// InitializeTracing
// =============================================================================

var _ = Describe("InitializeTracing", func() {
	BeforeEach(func() {
		clearTracingEnv()
	})

	AfterEach(func() {
		clearTracingEnv()
	})

	Context("when OTEL_SDK_DISABLED is true", func() {
		BeforeEach(func() {
			Expect(os.Setenv("OTEL_SDK_DISABLED", "true")).To(Succeed())
		})

		It("returns a no-error no-op provider", func() {
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
		})

		It("does not attempt to connect to any exporter endpoint", func() {
			// Even if an endpoint is set, the SDK disabled flag takes precedence.
			Expect(os.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")).To(Succeed())
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
		})
	})

	Context("when OTEL_EXPORTER_OTLP_ENDPOINT is not set", func() {
		It("returns a no-error no-op provider", func() {
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
		})
	})

	Context("when OTEL_EXPORTER_OTLP_ENDPOINT is configured", func() {
		BeforeEach(func() {
			// Use a local port that is almost certainly not listening.
			// gRPC uses a lazy (non-blocking) dial, so New() returns immediately.
			Expect(os.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:19317")).To(Succeed())
		})

		AfterEach(func() {
			_ = os.Unsetenv("OTEL_EXPORTER_OTLP_ENDPOINT")
		})

		It("returns a tracer provider with default service name", func() {
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = tp.Shutdown(context.Background())
		})

		It("uses a custom service name when OTEL_SERVICE_NAME is set", func() {
			Expect(os.Setenv("OTEL_SERVICE_NAME", "my-custom-service")).To(Succeed())
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = tp.Shutdown(context.Background())
		})

		It("uses a custom service version when OTEL_SERVICE_VERSION is set", func() {
			Expect(os.Setenv("OTEL_SERVICE_VERSION", "v1.2.3")).To(Succeed())
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = tp.Shutdown(context.Background())
		})

		It("returns an error for an invalid OTEL_TRACES_SAMPLER_ARG", func() {
			Expect(os.Setenv("OTEL_TRACES_SAMPLER_ARG", "not-a-float")).To(Succeed())
			_, err := InitializeTracing(context.Background())
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("invalid OTEL_TRACES_SAMPLER_ARG"))
		})

		It("returns an error for an unknown OTEL_TRACES_SAMPLER type", func() {
			Expect(os.Setenv("OTEL_TRACES_SAMPLER", "unknown_sampler")).To(Succeed())
			_, err := InitializeTracing(context.Background())
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("unknown OTEL_TRACES_SAMPLER"))
		})

		DescribeTable("supports all valid sampler types",
			func(samplerType string) {
				Expect(os.Setenv("OTEL_TRACES_SAMPLER", samplerType)).To(Succeed())
				tp, err := InitializeTracing(context.Background())
				Expect(err).NotTo(HaveOccurred(), "sampler type %q should be supported", samplerType)
				Expect(tp).NotTo(BeNil())
				_ = tp.Shutdown(context.Background())
			},
			Entry("always_on", "always_on"),
			Entry("always_off", "always_off"),
			Entry("traceidratio", "traceidratio"),
			Entry("parentbased_always_on", "parentbased_always_on"),
			Entry("parentbased_always_off", "parentbased_always_off"),
			Entry("parentbased_traceidratio", "parentbased_traceidratio"),
		)

		It("uses a custom sample rate from OTEL_TRACES_SAMPLER_ARG", func() {
			Expect(os.Setenv("OTEL_TRACES_SAMPLER", "traceidratio")).To(Succeed())
			Expect(os.Setenv("OTEL_TRACES_SAMPLER_ARG", "0.5")).To(Succeed())
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = tp.Shutdown(context.Background())
		})

		It("uses zero sample rate (never sample)", func() {
			Expect(os.Setenv("OTEL_TRACES_SAMPLER", "traceidratio")).To(Succeed())
			Expect(os.Setenv("OTEL_TRACES_SAMPLER_ARG", "0.0")).To(Succeed())
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = tp.Shutdown(context.Background())
		})
	})
})

// =============================================================================
// Shutdown
// =============================================================================

var _ = Describe("Shutdown", func() {
	It("returns nil for a nil tracer provider", func() {
		err := Shutdown(context.Background(), nil)
		Expect(err).NotTo(HaveOccurred())
	})

	It("gracefully shuts down a no-op provider (no endpoint)", func() {
		clearTracingEnv()
		tp, err := InitializeTracing(context.Background())
		Expect(err).NotTo(HaveOccurred())
		Expect(tp).NotTo(BeNil())

		err = Shutdown(context.Background(), tp)
		Expect(err).NotTo(HaveOccurred())
	})

	It("is safe to call with an already-shut-down provider", func() {
		clearTracingEnv()
		tp, err := InitializeTracing(context.Background())
		Expect(err).NotTo(HaveOccurred())

		Expect(Shutdown(context.Background(), tp)).To(Succeed())
		// Second call may return an error (provider already shut down) — just must not panic.
		Expect(func() { _ = Shutdown(context.Background(), tp) }).NotTo(Panic())
	})
})

// =============================================================================
// GetTracer
// =============================================================================

var _ = Describe("GetTracer", func() {
	It("returns a non-nil tracer for a given name", func() {
		tracer := GetTracer("cloudflare-operator")
		Expect(tracer).NotTo(BeNil())
	})

	It("returns a non-nil tracer for an empty name", func() {
		tracer := GetTracer("")
		Expect(tracer).NotTo(BeNil())
	})

	It("returns distinct tracers for different names", func() {
		t1 := GetTracer("tracer-one")
		t2 := GetTracer("tracer-two")
		// Both should be non-nil; they may or may not be the same underlying object.
		Expect(t1).NotTo(BeNil())
		Expect(t2).NotTo(BeNil())
	})
})
