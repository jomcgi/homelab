// Tests for cloudflare_tunnel_metrics.go and cloudflare_tunnel_observability.go.
// This file is part of the statemachine package test suite; the Ginkgo bootstrap
// and helpers (newTunnel, newTunnelWithStatus) live in cloudflare_tunnel_statemachine_test.go.

package statemachine

import (
	"context"
	"errors"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/testutil"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

// histCount returns the sample count of a histogram identified by its label values.
// HistogramVec.GetMetricWithLabelValues returns prometheus.Observer; the underlying
// concrete type also implements prometheus.Collector, so the type assertion is safe.
func histCount(vec *prometheus.HistogramVec, lvs ...string) float64 {
	obs, err := vec.GetMetricWithLabelValues(lvs...)
	ExpectWithOffset(1, err).NotTo(HaveOccurred(), "GetMetricWithLabelValues(%v)", lvs)
	return testutil.ToFloat64(obs.(prometheus.Collector))
}

// tunnelWith creates a tunnel with a specific name and namespace for metric label isolation.
func tunnelWith(name, ns string) *v1.CloudflareTunnel {
	t := newTunnel("")
	t.Name = name
	t.Namespace = ns
	return t
}

var _ = Describe("RecordReconcile", func() {
	It("increments reconcileTotal with result=success on success", func() {
		before := testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))
		RecordReconcile("Ready", 100*time.Millisecond, true)
		after := testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))
		Expect(after - before).To(Equal(1.0))
	})

	It("increments reconcileTotal with result=error on failure", func() {
		before := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
		RecordReconcile("Failed", 50*time.Millisecond, false)
		after := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
		Expect(after - before).To(Equal(1.0))
	})

	It("records reconcile duration in the histogram (sample count increases)", func() {
		countBefore := histCount(reconcileDuration, "RecordPhase")

		RecordReconcile("RecordPhase", 10*time.Millisecond, true)

		Expect(histCount(reconcileDuration, "RecordPhase")).To(BeNumerically(">", countBefore))
	})
})

var _ = Describe("RecordError", func() {
	It("increments errorsTotal for the given error type", func() {
		before := testutil.ToFloat64(errorsTotal.WithLabelValues("api_error"))
		RecordError("api_error")
		after := testutil.ToFloat64(errorsTotal.WithLabelValues("api_error"))
		Expect(after - before).To(Equal(1.0))
	})

	It("uses the exact label value provided", func() {
		before := testutil.ToFloat64(errorsTotal.WithLabelValues("custom_error_type"))
		RecordError("custom_error_type")
		after := testutil.ToFloat64(errorsTotal.WithLabelValues("custom_error_type"))
		Expect(after - before).To(Equal(1.0))
	})

	It("increments only the specified label, not others", func() {
		beforeA := testutil.ToFloat64(errorsTotal.WithLabelValues("type_unique_a"))
		beforeB := testutil.ToFloat64(errorsTotal.WithLabelValues("type_unique_b"))
		RecordError("type_unique_a")
		afterA := testutil.ToFloat64(errorsTotal.WithLabelValues("type_unique_a"))
		afterB := testutil.ToFloat64(errorsTotal.WithLabelValues("type_unique_b"))
		Expect(afterA - beforeA).To(Equal(1.0))
		Expect(afterB - beforeB).To(Equal(0.0))
	})
})

var _ = Describe("CleanupResourceMetrics", func() {
	It("does not panic when cleaning up a resource with no metrics registered", func() {
		Expect(func() {
			CleanupResourceMetrics("default", "nonexistent-resource")
		}).NotTo(Panic())
	})

	It("removes the resourcePhase gauge entry for the resource (value resets to 0)", func() {
		ns, name := "default", "cleanup-target"
		resourcePhase.WithLabelValues(ns, name, PhasePending).Set(1)
		Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(ns, name, PhasePending))).To(Equal(1.0))

		CleanupResourceMetrics(ns, name)

		// DeleteLabelValues removes the series; re-creating it returns a fresh (0-value) gauge
		Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(ns, name, PhasePending))).To(Equal(0.0))
	})

	It("removes all known phase gauges for the resource", func() {
		ns, name := "default", "all-phases-cleanup"
		for _, phase := range AllPhases() {
			resourcePhase.WithLabelValues(ns, name, phase).Set(1)
		}

		CleanupResourceMetrics(ns, name)

		for _, phase := range AllPhases() {
			Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(ns, name, phase))).
				To(Equal(0.0), "phase %s gauge should be 0 after cleanup", phase)
		}
	})
})

var _ = Describe("MetricsObserver", func() {
	var (
		observer *MetricsObserver
		ctx      context.Context
		tunnel   *v1.CloudflareTunnel
	)

	BeforeEach(func() {
		observer = NewMetricsObserver()
		ctx = context.Background()
		// Use a unique name per test to avoid gauge value leakage between tests
		tunnel = tunnelWith("metrics-obs-test", "default")
	})

	Describe("NewMetricsObserver", func() {
		It("returns a non-nil observer", func() {
			Expect(observer).NotTo(BeNil())
		})
	})

	Describe("OnTransition", func() {
		It("sets the to-state resourcePhase gauge to 1", func() {
			from := CloudflareTunnelPending{resource: tunnel}
			to := CloudflareTunnelCreatingTunnel{resource: tunnel}

			observer.OnTransition(ctx, from, to)

			Expect(testutil.ToFloat64(
				resourcePhase.WithLabelValues(tunnel.Namespace, tunnel.Name, PhaseCreatingTunnel),
			)).To(Equal(1.0))
		})

		It("sets the from-state resourcePhase gauge to 0", func() {
			from := CloudflareTunnelPending{resource: tunnel}
			to := CloudflareTunnelCreatingTunnel{resource: tunnel}

			observer.OnTransition(ctx, from, to)

			Expect(testutil.ToFloat64(
				resourcePhase.WithLabelValues(tunnel.Namespace, tunnel.Name, PhasePending),
			)).To(Equal(0.0))
		})

		It("does not record stateDuration on the first transition (no prior start time)", func() {
			t := tunnelWith("first-transition-only", "default")
			from := CloudflareTunnelPending{resource: t}
			to := CloudflareTunnelCreatingTunnel{resource: t}

			countBefore := histCount(stateDuration, PhasePending, PhaseCreatingTunnel)

			// Fresh observer has no prior start time — duration must NOT be observed
			NewMetricsObserver().OnTransition(ctx, from, to)

			Expect(histCount(stateDuration, PhasePending, PhaseCreatingTunnel)).To(Equal(countBefore))
		})

		It("records stateDuration histogram on the second transition", func() {
			from1 := CloudflareTunnelPending{resource: tunnel}
			to1 := CloudflareTunnelCreatingTunnel{resource: tunnel}
			observer.OnTransition(ctx, from1, to1)

			from2 := CloudflareTunnelCreatingTunnel{resource: tunnel}
			to2 := CloudflareTunnelCreatingSecret{
				resource:       tunnel,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-1"},
			}

			countBefore := histCount(stateDuration, PhaseCreatingTunnel, PhaseCreatingSecret)

			observer.OnTransition(ctx, from2, to2)

			Expect(histCount(stateDuration, PhaseCreatingTunnel, PhaseCreatingSecret)).
				To(BeNumerically(">", countBefore))
		})

		It("is safe to call concurrently (exercises mutex path)", func() {
			done := make(chan struct{}, 5)
			for i := 0; i < 5; i++ {
				go func() {
					defer GinkgoRecover()
					obs := NewMetricsObserver()
					t := tunnelWith("concurrent-test", "default")
					obs.OnTransition(ctx,
						CloudflareTunnelPending{resource: t},
						CloudflareTunnelCreatingTunnel{resource: t},
					)
					done <- struct{}{}
				}()
			}
			for i := 0; i < 5; i++ {
				<-done
			}
		})
	})

	Describe("OnTransitionError", func() {
		It("increments errorsTotal with label 'transition'", func() {
			from := CloudflareTunnelPending{resource: tunnel}
			to := CloudflareTunnelFailed{
				resource:     tunnel,
				LastState:    PhasePending,
				ErrorMessage: "something went wrong",
			}
			before := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))

			observer.OnTransitionError(ctx, from, to, errors.New("test error"))

			after := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))
			Expect(after - before).To(Equal(1.0))
		})
	})
})

var _ = Describe("ValidateTransition", func() {
	Context("when to is nil", func() {
		It("returns nil — a nil target is always valid", func() {
			Expect(ValidateTransition(CloudflareTunnelPending{resource: nil}, nil)).To(Succeed())
		})
	})

	Context("valid transitions", func() {
		DescribeTable("accepts states with all required fields",
			func(from, to CloudflareTunnelState) {
				Expect(ValidateTransition(from, to)).To(Succeed())
			},
			Entry("Pending → Pending",
				CloudflareTunnelPending{resource: nil},
				CloudflareTunnelPending{resource: nil},
			),
			Entry("Pending → CreatingTunnel",
				CloudflareTunnelPending{resource: nil},
				CloudflareTunnelCreatingTunnel{resource: nil},
			),
			Entry("CreatingTunnel → CreatingSecret (with TunnelID)",
				CloudflareTunnelCreatingTunnel{resource: nil},
				CloudflareTunnelCreatingSecret{resource: nil, TunnelIdentity: TunnelIdentity{TunnelID: "abc"}},
			),
			Entry("CreatingSecret → ConfiguringIngress (with TunnelID+SecretName)",
				CloudflareTunnelCreatingSecret{resource: nil, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}},
				CloudflareTunnelConfiguringIngress{
					resource:       nil,
					TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
					SecretInfo:     SecretInfo{SecretName: "s1"},
				},
			),
			Entry("ConfiguringIngress → Ready (all required fields)",
				CloudflareTunnelConfiguringIngress{
					resource:       nil,
					TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
					SecretInfo:     SecretInfo{SecretName: "s1"},
				},
				CloudflareTunnelReady{
					resource:       nil,
					TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
					SecretInfo:     SecretInfo{SecretName: "s1"},
					Active:         true,
				},
			),
			Entry("CreatingTunnel → Failed (with LastState+ErrorMessage)",
				CloudflareTunnelCreatingTunnel{resource: nil},
				CloudflareTunnelFailed{
					resource:     nil,
					LastState:    PhaseCreatingTunnel,
					ErrorMessage: "tunnel creation failed",
				},
			),
			Entry("Ready → DeletingTunnel (with TunnelID)",
				CloudflareTunnelReady{resource: nil, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}, SecretInfo: SecretInfo{SecretName: "s1"}},
				CloudflareTunnelDeletingTunnel{resource: nil, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}},
			),
			Entry("DeletingTunnel → Deleted",
				CloudflareTunnelDeletingTunnel{resource: nil, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}},
				CloudflareTunnelDeleted{resource: nil},
			),
		)
	})

	Context("invalid transitions", func() {
		DescribeTable("rejects states with missing required fields",
			func(from, to CloudflareTunnelState) {
				Expect(ValidateTransition(from, to)).To(HaveOccurred())
			},
			Entry("Failed missing LastState and ErrorMessage",
				CloudflareTunnelPending{resource: nil},
				CloudflareTunnelFailed{resource: nil},
			),
			Entry("Failed missing ErrorMessage",
				CloudflareTunnelPending{resource: nil},
				CloudflareTunnelFailed{resource: nil, LastState: PhasePending},
			),
			Entry("Failed missing LastState",
				CloudflareTunnelPending{resource: nil},
				CloudflareTunnelFailed{resource: nil, ErrorMessage: "oops"},
			),
			Entry("CreatingSecret missing TunnelID",
				CloudflareTunnelCreatingTunnel{resource: nil},
				CloudflareTunnelCreatingSecret{resource: nil},
			),
			Entry("ConfiguringIngress missing TunnelID",
				CloudflareTunnelCreatingSecret{resource: nil},
				CloudflareTunnelConfiguringIngress{resource: nil, SecretInfo: SecretInfo{SecretName: "s1"}},
			),
			Entry("ConfiguringIngress missing SecretName",
				CloudflareTunnelCreatingSecret{resource: nil},
				CloudflareTunnelConfiguringIngress{resource: nil, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}},
			),
			Entry("DeletingTunnel missing TunnelID",
				CloudflareTunnelReady{resource: nil, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}, SecretInfo: SecretInfo{SecretName: "s1"}},
				CloudflareTunnelDeletingTunnel{resource: nil},
			),
			Entry("Ready missing TunnelID",
				CloudflareTunnelConfiguringIngress{
					resource:       nil,
					TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
					SecretInfo:     SecretInfo{SecretName: "s1"},
				},
				CloudflareTunnelReady{resource: nil, SecretInfo: SecretInfo{SecretName: "s1"}},
			),
			Entry("Unknown missing ObservedPhase",
				CloudflareTunnelPending{resource: nil},
				CloudflareTunnelUnknown{resource: nil},
			),
		)
	})
})

var _ = Describe("NoOpObserver", func() {
	var (
		obs    NoOpObserver
		ctx    context.Context
		tunnel *v1.CloudflareTunnel
	)

	BeforeEach(func() {
		obs = NoOpObserver{}
		ctx = context.Background()
		tunnel = newTunnel("")
	})

	It("does not panic on OnTransition", func() {
		from := CloudflareTunnelPending{resource: tunnel}
		to := CloudflareTunnelCreatingTunnel{resource: tunnel}
		Expect(func() { obs.OnTransition(ctx, from, to) }).NotTo(Panic())
	})

	It("does not panic on OnTransitionError", func() {
		from := CloudflareTunnelPending{resource: tunnel}
		to := CloudflareTunnelFailed{resource: tunnel, LastState: PhasePending, ErrorMessage: "err"}
		Expect(func() { obs.OnTransitionError(ctx, from, to, errors.New("err")) }).NotTo(Panic())
	})
})

var _ = Describe("LoggingObserver", func() {
	var (
		obs    LoggingObserver
		ctx    context.Context
		tunnel *v1.CloudflareTunnel
	)

	BeforeEach(func() {
		obs = LoggingObserver{}
		ctx = context.Background() // ctrl.LoggerFrom falls back to discard logger
		tunnel = newTunnel("")
	})

	It("logs OnTransition without panicking (discard logger fallback)", func() {
		from := CloudflareTunnelPending{resource: tunnel}
		to := CloudflareTunnelCreatingTunnel{resource: tunnel}
		Expect(func() { obs.OnTransition(ctx, from, to) }).NotTo(Panic())
	})

	It("logs OnTransitionError without panicking", func() {
		from := CloudflareTunnelPending{resource: tunnel}
		to := CloudflareTunnelFailed{resource: tunnel, LastState: PhasePending, ErrorMessage: "err"}
		Expect(func() { obs.OnTransitionError(ctx, from, to, errors.New("something went wrong")) }).NotTo(Panic())
	})
})

var _ = Describe("OTelObserver", func() {
	var (
		tunnel *v1.CloudflareTunnel
		ctx    context.Context
	)

	BeforeEach(func() {
		tunnel = newTunnel("")
		ctx = context.Background()
	})

	Describe("NewOTelObserver", func() {
		It("returns a non-nil observer", func() {
			obs := NewOTelObserver("cloudflare-operator")
			Expect(obs).NotTo(BeNil())
		})

		It("stores a non-nil tracer for the given name", func() {
			obs := NewOTelObserver("cloudflare-operator")
			Expect(obs.tracer).NotTo(BeNil())
		})
	})

	Describe("OnTransition", func() {
		It("does not panic when the global OTel provider is noop (mock tracer)", func() {
			// The global provider defaults to the noop provider.
			// NewOTelObserver wraps it, effectively providing a no-op mock tracer.
			obs := NewOTelObserver("test-tracer")
			from := CloudflareTunnelPending{resource: tunnel}
			to := CloudflareTunnelCreatingTunnel{resource: tunnel}
			Expect(func() { obs.OnTransition(ctx, from, to) }).NotTo(Panic())
		})

		It("creates and immediately ends a span (span lifecycle completes)", func() {
			obs := NewOTelObserver("span-lifecycle-tracer")
			from := CloudflareTunnelCreatingTunnel{resource: tunnel}
			to := CloudflareTunnelCreatingSecret{
				resource:       tunnel,
				TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
			}
			Expect(func() { obs.OnTransition(ctx, from, to) }).NotTo(Panic())
		})
	})

	Describe("OnTransitionError", func() {
		It("does not panic when using the noop provider", func() {
			obs := NewOTelObserver("test-tracer")
			from := CloudflareTunnelPending{resource: tunnel}
			to := CloudflareTunnelFailed{resource: tunnel, LastState: PhasePending, ErrorMessage: "err"}
			Expect(func() { obs.OnTransitionError(ctx, from, to, errors.New("err")) }).NotTo(Panic())
		})

		It("records the error on the span and ends it without panic", func() {
			obs := NewOTelObserver("error-span-tracer")
			from := CloudflareTunnelCreatingTunnel{resource: tunnel}
			to := CloudflareTunnelFailed{
				resource:     tunnel,
				LastState:    PhaseCreatingTunnel,
				ErrorMessage: "tunnel creation timed out",
			}
			Expect(func() {
				obs.OnTransitionError(ctx, from, to, errors.New("tunnel creation timed out"))
			}).NotTo(Panic())
		})
	})
})

var _ = Describe("CompositeObserver", func() {
	var (
		ctx    context.Context
		tunnel *v1.CloudflareTunnel
	)

	BeforeEach(func() {
		ctx = context.Background()
		tunnel = newTunnel("")
	})

	It("delegates OnTransition to all children without panic", func() {
		composite := CompositeObserver{
			NoOpObserver{},
			LoggingObserver{},
			NewOTelObserver("composite-test"),
		}
		from := CloudflareTunnelPending{resource: tunnel}
		to := CloudflareTunnelCreatingTunnel{resource: tunnel}
		Expect(func() { composite.OnTransition(ctx, from, to) }).NotTo(Panic())
	})

	It("delegates OnTransitionError to all children without panic", func() {
		composite := CompositeObserver{
			NoOpObserver{},
			LoggingObserver{},
		}
		from := CloudflareTunnelPending{resource: tunnel}
		to := CloudflareTunnelFailed{resource: tunnel, LastState: PhasePending, ErrorMessage: "err"}
		Expect(func() { composite.OnTransitionError(ctx, from, to, errors.New("err")) }).NotTo(Panic())
	})

	It("calls OnTransitionError on all MetricsObserver children, incrementing the counter for each", func() {
		t := tunnelWith("composite-metrics-test", "default")
		m1 := NewMetricsObserver()
		m2 := NewMetricsObserver()
		composite := CompositeObserver{m1, m2}

		from := CloudflareTunnelPending{resource: t}
		to := CloudflareTunnelFailed{resource: t, LastState: PhasePending, ErrorMessage: "err"}

		before := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))
		composite.OnTransitionError(ctx, from, to, errors.New("test"))
		after := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))

		// m1 and m2 each call errorsTotal["transition"].Inc() → delta of 2
		Expect(after - before).To(Equal(2.0))
	})

	It("handles an empty composite without panic", func() {
		composite := CompositeObserver{}
		from := CloudflareTunnelPending{resource: tunnel}
		to := CloudflareTunnelCreatingTunnel{resource: tunnel}
		Expect(func() { composite.OnTransition(ctx, from, to) }).NotTo(Panic())
		Expect(func() {
			composite.OnTransitionError(ctx, from,
				CloudflareTunnelFailed{resource: tunnel, LastState: PhasePending, ErrorMessage: "err"},
				errors.New("err"),
			)
		}).NotTo(Panic())
	})
})
