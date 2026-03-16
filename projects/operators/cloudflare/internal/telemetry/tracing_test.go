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

package telemetry_test

import (
	"context"
	"os"
	"testing"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

func TestTelemetry(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Telemetry Suite")
}

// clearOtelEnv unsets all OTEL env vars that InitializeTracing reads so that
// each test starts from a predictable baseline.
func clearOtelEnv() {
	for _, key := range []string{
		"OTEL_SDK_DISABLED",
		"OTEL_EXPORTER_OTLP_ENDPOINT",
		"OTEL_SERVICE_NAME",
		"OTEL_SERVICE_VERSION",
		"OTEL_TRACES_SAMPLER",
		"OTEL_TRACES_SAMPLER_ARG",
	} {
		orig, wasSet := os.LookupEnv(key)
		DeferCleanup(func() {
			if wasSet {
				os.Setenv(key, orig) //nolint:errcheck
			} else {
				os.Unsetenv(key) //nolint:errcheck
			}
		})
		os.Unsetenv(key) //nolint:errcheck
	}
}

var _ = Describe("InitializeTracing", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
		clearOtelEnv()
	})

	Context("when OTEL_SDK_DISABLED=true", func() {
		It("returns a TracerProvider and no error without connecting to any endpoint", func() {
			os.Setenv("OTEL_SDK_DISABLED", "true")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			Expect(telemetry.Shutdown(ctx, tp)).To(Succeed())
		})
	})

	Context("when OTEL_EXPORTER_OTLP_ENDPOINT is empty", func() {
		It("returns a noop TracerProvider and no error (tracing disabled without endpoint)", func() {
			// All vars unset — no endpoint means tracing is disabled
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			Expect(telemetry.Shutdown(ctx, tp)).To(Succeed())
		})
	})

	Context("when OTEL_TRACES_SAMPLER_ARG is not a valid float", func() {
		It("returns an error mentioning OTEL_TRACES_SAMPLER_ARG", func() {
			os.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
			os.Setenv("OTEL_TRACES_SAMPLER_ARG", "not-a-float")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("OTEL_TRACES_SAMPLER_ARG"))
			Expect(tp).To(BeNil())
		})
	})

	Context("when OTEL_TRACES_SAMPLER is an unknown type", func() {
		It("returns an error mentioning the unknown sampler", func() {
			os.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
			os.Setenv("OTEL_TRACES_SAMPLER", "unknown_sampler_type")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("unknown_sampler_type"))
			Expect(tp).To(BeNil())
		})
	})

	Context("with a valid endpoint and explicit sampler types", func() {
		// gRPC uses lazy dialing by default (no grpc.WithBlock), so
		// otlptracegrpc.New() returns immediately even with an unreachable endpoint.
		DescribeTable("returns a configured provider without error",
			func(samplerType string) {
				os.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
				os.Setenv("OTEL_TRACES_SAMPLER", samplerType)
				os.Setenv("OTEL_TRACES_SAMPLER_ARG", "0.5")
				tp, err := telemetry.InitializeTracing(ctx)
				Expect(err).NotTo(HaveOccurred())
				Expect(tp).NotTo(BeNil())
				// Shutdown cleanly to release the background gRPC dial
				_ = telemetry.Shutdown(ctx, tp)
			},
			Entry("always_on sampler", "always_on"),
			Entry("always_off sampler", "always_off"),
			Entry("traceidratio sampler", "traceidratio"),
			Entry("parentbased_always_on sampler", "parentbased_always_on"),
			Entry("parentbased_always_off sampler", "parentbased_always_off"),
			Entry("parentbased_traceidratio sampler (default)", "parentbased_traceidratio"),
		)
	})

	Context("default service name and version defaults", func() {
		It("succeeds when OTEL_SERVICE_NAME is not set (uses 'cloudflare-operator')", func() {
			// SDK disabled path — just confirm no error when service name is absent
			os.Setenv("OTEL_SDK_DISABLED", "true")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = telemetry.Shutdown(ctx, tp)
		})

		It("succeeds when OTEL_SERVICE_VERSION is not set (uses 'dev')", func() {
			os.Setenv("OTEL_SDK_DISABLED", "true")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = telemetry.Shutdown(ctx, tp)
		})

		It("accepts a custom OTEL_SERVICE_NAME when provided", func() {
			os.Setenv("OTEL_SDK_DISABLED", "true")
			os.Setenv("OTEL_SERVICE_NAME", "my-custom-operator")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = telemetry.Shutdown(ctx, tp)
		})

		It("accepts a custom OTEL_SERVICE_VERSION when provided", func() {
			os.Setenv("OTEL_SDK_DISABLED", "true")
			os.Setenv("OTEL_SERVICE_VERSION", "v1.2.3")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = telemetry.Shutdown(ctx, tp)
		})
	})

	Context("OTEL_SDK_DISABLED edge cases", func() {
		It("does NOT disable when OTEL_SDK_DISABLED is 'false'", func() {
			// 'false' is not 'true' so the function proceeds past the early-return
			// With no endpoint set, it returns a noop provider (no error)
			os.Setenv("OTEL_SDK_DISABLED", "false")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = telemetry.Shutdown(ctx, tp)
		})

		It("does NOT disable when OTEL_SDK_DISABLED is '1'", func() {
			os.Setenv("OTEL_SDK_DISABLED", "1")
			tp, err := telemetry.InitializeTracing(ctx)
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())
			_ = telemetry.Shutdown(ctx, tp)
		})
	})
})

var _ = Describe("Shutdown", func() {
	It("returns nil when given a nil TracerProvider", func() {
		Expect(telemetry.Shutdown(context.Background(), nil)).To(Succeed())
	})

	It("shuts down a real TracerProvider without error", func() {
		os.Setenv("OTEL_SDK_DISABLED", "true")
		defer os.Unsetenv("OTEL_SDK_DISABLED")
		tp, err := telemetry.InitializeTracing(context.Background())
		Expect(err).NotTo(HaveOccurred())
		Expect(telemetry.Shutdown(context.Background(), tp)).To(Succeed())
	})
})

var _ = Describe("GetTracer", func() {
	It("returns a non-nil tracer for a named component", func() {
		tracer := telemetry.GetTracer("test-component")
		Expect(tracer).NotTo(BeNil())
	})

	It("returns a non-nil tracer for an empty name", func() {
		tracer := telemetry.GetTracer("")
		Expect(tracer).NotTo(BeNil())
	})

	It("returns different-looking tracers for different names (both non-nil)", func() {
		t1 := telemetry.GetTracer("component-a")
		t2 := telemetry.GetTracer("component-b")
		Expect(t1).NotTo(BeNil())
		Expect(t2).NotTo(BeNil())
	})
})
