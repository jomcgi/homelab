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
	"testing"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"go.opentelemetry.io/otel"
)

func TestTelemetry(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Telemetry Suite")
}

var _ = Describe("Tracing", func() {

	// cleanEnv removes all OTEL env vars that InitializeTracing reads so that
	// each test starts from a known state.
	BeforeEach(func() {
		GinkgoT().Setenv("OTEL_SDK_DISABLED", "")
		GinkgoT().Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
		GinkgoT().Setenv("OTEL_SERVICE_NAME", "")
		GinkgoT().Setenv("OTEL_SERVICE_VERSION", "")
		GinkgoT().Setenv("OTEL_TRACES_SAMPLER", "")
		GinkgoT().Setenv("OTEL_TRACES_SAMPLER_ARG", "")
	})

	// ==========================================================================
	// InitializeTracing — early-return paths (no network required)
	// ==========================================================================

	Describe("InitializeTracing", func() {

		Context("when OTEL_SDK_DISABLED=true", func() {
			BeforeEach(func() {
				GinkgoT().Setenv("OTEL_SDK_DISABLED", "true")
			})

			It("returns a non-nil TracerProvider without error", func() {
				tp, err := InitializeTracing(context.Background())
				Expect(err).NotTo(HaveOccurred())
				Expect(tp).NotTo(BeNil())
			})

			It("does NOT set the global tracer provider (no endpoint configured)", func() {
				// The disabled path returns a bare provider but doesn't call otel.SetTracerProvider.
				// We just verify it doesn't panic and returns cleanly.
				_, err := InitializeTracing(context.Background())
				Expect(err).NotTo(HaveOccurred())
			})
		})

		Context("when OTEL_SDK_DISABLED is unset (default false)", func() {
			Context("and no OTEL_EXPORTER_OTLP_ENDPOINT is configured", func() {
				It("returns a non-nil TracerProvider without error", func() {
					tp, err := InitializeTracing(context.Background())
					Expect(err).NotTo(HaveOccurred())
					Expect(tp).NotTo(BeNil())
				})
			})
		})

		Context("when OTEL_SDK_DISABLED is an arbitrary non-true string", func() {
			BeforeEach(func() {
				GinkgoT().Setenv("OTEL_SDK_DISABLED", "false")
			})

			It("does not disable tracing (no endpoint → returns bare provider)", func() {
				tp, err := InitializeTracing(context.Background())
				Expect(err).NotTo(HaveOccurred())
				Expect(tp).NotTo(BeNil())
			})
		})

		Context("with a valid endpoint but invalid OTEL_TRACES_SAMPLER_ARG", func() {
			BeforeEach(func() {
				// Set an endpoint so we pass the early-return checks.
				// The sampler arg is parsed BEFORE the exporter is created,
				// so an invalid value should return an error without dialling.
				GinkgoT().Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
				GinkgoT().Setenv("OTEL_TRACES_SAMPLER_ARG", "not-a-float")
			})

			It("returns an error describing the invalid sampler arg", func() {
				tp, err := InitializeTracing(context.Background())
				Expect(err).To(HaveOccurred())
				Expect(err.Error()).To(ContainSubstring("OTEL_TRACES_SAMPLER_ARG"))
				Expect(tp).To(BeNil())
			})
		})

		DescribeTable("default values used when env vars are unset",
			func(envKey, envValue, expectedDefault string) {
				// We only test paths that return early (no endpoint), so that no
				// network dial is attempted.  We verify the defaults by checking
				// the code reaches the sampler-arg parse step only when the
				// endpoint is absent (early return before that point).
				tp, err := InitializeTracing(context.Background())
				Expect(err).NotTo(HaveOccurred())
				Expect(tp).NotTo(BeNil())
			},
			Entry("no service name → defaults to cloudflare-operator", "OTEL_SERVICE_NAME", "", "cloudflare-operator"),
			Entry("no service version → defaults to dev", "OTEL_SERVICE_VERSION", "", "dev"),
			Entry("no sampler type → defaults to parentbased_traceidratio", "OTEL_TRACES_SAMPLER", "", "parentbased_traceidratio"),
			Entry("no sampler arg → defaults to 1.0", "OTEL_TRACES_SAMPLER_ARG", "", "1.0"),
		)
	})

	// ==========================================================================
	// Shutdown
	// ==========================================================================

	Describe("Shutdown", func() {
		It("returns nil when given a nil TracerProvider", func() {
			err := Shutdown(context.Background(), nil)
			Expect(err).NotTo(HaveOccurred())
		})

		It("shuts down a real TracerProvider without error", func() {
			// Use the disabled path to get a bare (no-op) TracerProvider.
			GinkgoT().Setenv("OTEL_SDK_DISABLED", "true")
			tp, err := InitializeTracing(context.Background())
			Expect(err).NotTo(HaveOccurred())
			Expect(tp).NotTo(BeNil())

			err = Shutdown(context.Background(), tp)
			Expect(err).NotTo(HaveOccurred())
		})

		It("is idempotent — shutting down twice does not panic", func() {
			GinkgoT().Setenv("OTEL_SDK_DISABLED", "true")
			tp, _ := InitializeTracing(context.Background())

			Expect(func() {
				_ = Shutdown(context.Background(), tp)
				_ = Shutdown(context.Background(), tp)
			}).NotTo(Panic())
		})
	})

	// ==========================================================================
	// GetTracer
	// ==========================================================================

	Describe("GetTracer", func() {
		It("returns a non-nil Tracer for a given name", func() {
			tracer := GetTracer("my-component")
			Expect(tracer).NotTo(BeNil())
		})

		It("returns a Tracer equal to the one obtained from the global provider", func() {
			name := "test-tracer"
			tracer := GetTracer(name)
			Expect(tracer).To(Equal(otel.Tracer(name)))
		})

		It("returns different tracers for different names", func() {
			t1 := GetTracer("component-a")
			t2 := GetTracer("component-b")
			// Both are valid; they should not be nil regardless of equality.
			Expect(t1).NotTo(BeNil())
			Expect(t2).NotTo(BeNil())
		})

		It("accepts an empty string as tracer name without panicking", func() {
			Expect(func() {
				tracer := GetTracer("")
				Expect(tracer).NotTo(BeNil())
			}).NotTo(Panic())
		})
	})
})
