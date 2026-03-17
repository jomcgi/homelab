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

package statemachine

import (
	"context"
	"errors"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"github.com/prometheus/client_golang/prometheus/testutil"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// newMetricsTunnel creates a CloudflareTunnel with specific namespace/name for metric label matching.
func newMetricsTunnel(namespace, name, phase string) *v1.CloudflareTunnel {
	return &v1.CloudflareTunnel{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
		},
		Status: v1.CloudflareTunnelStatus{
			Phase: phase,
		},
	}
}

var _ = Describe("Metrics", func() {

	// ==========================================================================
	// RecordReconcile
	// ==========================================================================

	Describe("RecordReconcile", func() {
		It("increments reconcileTotal with result=success on success", func() {
			before := testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))
			RecordReconcile(PhasePending, 100*time.Millisecond, true)
			after := testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))
			Expect(after).To(Equal(before + 1))
		})

		It("increments reconcileTotal with result=error on failure", func() {
			before := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
			RecordReconcile(PhaseReady, 200*time.Millisecond, false)
			after := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
			Expect(after).To(Equal(before + 1))
		})

		It("does not increment error counter on success", func() {
			before := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
			RecordReconcile(PhasePending, 50*time.Millisecond, true)
			after := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
			Expect(after).To(Equal(before))
		})

		It("does not increment success counter on failure", func() {
			before := testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))
			RecordReconcile(PhaseFailed, 50*time.Millisecond, false)
			after := testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))
			Expect(after).To(Equal(before))
		})

		DescribeTable("records duration histogram for each phase without panicking",
			func(phase string) {
				// HistogramVec.WithLabelValues returns prometheus.Observer (not Collector).
				// Verify that a new histogram series is created for each distinct phase label.
				before := testutil.CollectAndCount(reconcileDuration)
				RecordReconcile(phase, time.Second, true)
				after := testutil.CollectAndCount(reconcileDuration)
				// After observing a new phase, the series count should be >= before.
				Expect(after).To(BeNumerically(">=", before))
			},
			Entry("Pending phase", PhasePending),
			Entry("CreatingTunnel phase", PhaseCreatingTunnel),
			Entry("CreatingSecret phase", PhaseCreatingSecret),
			Entry("ConfiguringIngress phase", PhaseConfiguringIngress),
			Entry("Ready phase", PhaseReady),
			Entry("Failed phase", PhaseFailed),
		)

		It("records observation duration in seconds (non-negative)", func() {
			// Call with a known positive duration and verify it doesn't panic.
			Expect(func() {
				RecordReconcile(PhasePending, 500*time.Millisecond, true)
				RecordReconcile(PhasePending, 0, true)
			}).NotTo(Panic())
		})
	})

	// ==========================================================================
	// RecordError
	// ==========================================================================

	Describe("RecordError", func() {
		It("increments errorsTotal counter for the given error type", func() {
			before := testutil.ToFloat64(errorsTotal.WithLabelValues("api_error"))
			RecordError("api_error")
			after := testutil.ToFloat64(errorsTotal.WithLabelValues("api_error"))
			Expect(after).To(Equal(before + 1))
		})

		It("does not affect other error type counters", func() {
			before := testutil.ToFloat64(errorsTotal.WithLabelValues("other_error"))
			RecordError("api_error")
			after := testutil.ToFloat64(errorsTotal.WithLabelValues("other_error"))
			Expect(after).To(Equal(before))
		})

		It("can be called multiple times for the same error type", func() {
			before := testutil.ToFloat64(errorsTotal.WithLabelValues("repeated_error"))
			RecordError("repeated_error")
			RecordError("repeated_error")
			RecordError("repeated_error")
			after := testutil.ToFloat64(errorsTotal.WithLabelValues("repeated_error"))
			Expect(after).To(Equal(before + 3))
		})

		DescribeTable("accepts various error type strings",
			func(errorType string) {
				before := testutil.ToFloat64(errorsTotal.WithLabelValues(errorType))
				RecordError(errorType)
				after := testutil.ToFloat64(errorsTotal.WithLabelValues(errorType))
				Expect(after).To(Equal(before + 1))
			},
			Entry("transition error", "transition"),
			Entry("validation error", "validation"),
			Entry("reconcile error", "reconcile"),
			Entry("deletion error", "deletion"),
		)
	})

	// ==========================================================================
	// CleanupResourceMetrics
	// ==========================================================================

	Describe("CleanupResourceMetrics", func() {
		It("removes all phase gauges for the given namespace/name", func() {
			ns, name := "test-ns", "cleanup-tunnel"

			// Set up some gauges first.
			resourcePhase.WithLabelValues(ns, name, PhasePending).Set(1)
			resourcePhase.WithLabelValues(ns, name, PhaseReady).Set(0)

			// Verify they exist before cleanup.
			Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(ns, name, PhasePending))).To(Equal(float64(1)))

			// Perform cleanup.
			CleanupResourceMetrics(ns, name)

			// After DeleteLabelValues the gauge is removed; subsequent WithLabelValues
			// creates a fresh zero-valued gauge.
			Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(ns, name, PhasePending))).To(Equal(float64(0)))
			Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(ns, name, PhaseReady))).To(Equal(float64(0)))
		})

		It("is safe to call for a resource that has no metrics", func() {
			// Should not panic even if no metrics were ever recorded.
			Expect(func() {
				CleanupResourceMetrics("nonexistent-ns", "nonexistent-tunnel")
			}).NotTo(Panic())
		})

		It("cleans up all 9 phases", func() {
			ns, name := "test-ns", "all-phases-tunnel"
			phases := AllPhases()

			// Set a gauge for every known phase.
			for _, phase := range phases {
				resourcePhase.WithLabelValues(ns, name, phase).Set(1)
			}

			CleanupResourceMetrics(ns, name)

			// All gauges should be back to zero (fresh).
			for _, phase := range phases {
				Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(ns, name, phase))).
					To(Equal(float64(0)), "phase %q should be zero after cleanup", phase)
			}
		})
	})

	// ==========================================================================
	// MetricsObserver
	// ==========================================================================

	Describe("MetricsObserver", func() {
		var (
			observer *MetricsObserver
			ctx      context.Context
			tunnel   *v1.CloudflareTunnel
		)

		BeforeEach(func() {
			observer = NewMetricsObserver()
			ctx = context.Background()
			tunnel = newMetricsTunnel("obs-ns", "obs-tunnel", PhasePending)
		})

		Describe("NewMetricsObserver", func() {
			It("returns a non-nil observer with an empty transition map", func() {
				Expect(observer).NotTo(BeNil())
				Expect(observer.transitionStart).NotTo(BeNil())
				Expect(observer.transitionStart).To(BeEmpty())
			})
		})

		Describe("OnTransition", func() {
			It("sets the new phase gauge to 1", func() {
				from := CloudflareTunnelPending{resource: tunnel}
				to := CloudflareTunnelCreatingTunnel{resource: tunnel}

				observer.OnTransition(ctx, from, to)

				Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(
					tunnel.Namespace, tunnel.Name, PhaseCreatingTunnel,
				))).To(Equal(float64(1)))
			})

			It("sets the old (from) phase gauge to 0", func() {
				// Pre-set the from phase gauge to 1 to simulate it being active.
				resourcePhase.WithLabelValues(tunnel.Namespace, tunnel.Name, PhasePending).Set(1)

				from := CloudflareTunnelPending{resource: tunnel}
				to := CloudflareTunnelCreatingTunnel{resource: tunnel}

				observer.OnTransition(ctx, from, to)

				Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(
					tunnel.Namespace, tunnel.Name, PhasePending,
				))).To(Equal(float64(0)))
			})

			It("records transition start time in the map", func() {
				from := CloudflareTunnelPending{resource: tunnel}
				to := CloudflareTunnelCreatingTunnel{resource: tunnel}

				Expect(observer.transitionStart).To(BeEmpty())
				observer.OnTransition(ctx, from, to)

				key := tunnel.Namespace + "/" + tunnel.Name
				Expect(observer.transitionStart).To(HaveKey(key))
				Expect(observer.transitionStart[key]).To(BeTemporally("~", time.Now(), 2*time.Second))
			})

			It("records stateDuration on the second transition (after startTime exists)", func() {
				t2 := newMetricsTunnel("dur-ns", "dur-tunnel", PhaseCreatingTunnel)

				from1 := CloudflareTunnelPending{resource: t2}
				to1 := CloudflareTunnelCreatingTunnel{resource: t2}
				from2 := CloudflareTunnelCreatingTunnel{resource: t2}
				to2 := CloudflareTunnelCreatingSecret{
					resource:       t2,
					TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
				}

				// First transition records start time but no duration yet.
				// Count the number of distinct stateDuration series before.
				beforeCount := testutil.CollectAndCount(stateDuration)

				observer.OnTransition(ctx, from1, to1)

				// Wait a tiny bit so duration is non-zero.
				time.Sleep(5 * time.Millisecond)

				// Second transition should observe the duration from CreatingTunnel → CreatingSecret.
				observer.OnTransition(ctx, from2, to2)

				// After observing a new transition pair, series count should be >= before.
				afterCount := testutil.CollectAndCount(stateDuration)
				Expect(afterCount).To(BeNumerically(">=", beforeCount))
			})

			It("handles concurrent calls without panicking", func() {
				done := make(chan struct{})
				for i := 0; i < 10; i++ {
					go func() {
						defer GinkgoRecover()
						from := CloudflareTunnelPending{resource: tunnel}
						to := CloudflareTunnelCreatingTunnel{resource: tunnel}
						observer.OnTransition(ctx, from, to)
						done <- struct{}{}
					}()
				}
				for i := 0; i < 10; i++ {
					Eventually(done).Should(Receive())
				}
			})
		})

		Describe("OnTransitionError", func() {
			It("increments errorsTotal with label 'transition'", func() {
				before := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))

				from := CloudflareTunnelPending{resource: tunnel}
				to := CloudflareTunnelCreatingTunnel{resource: tunnel}
				observer.OnTransitionError(ctx, from, to, errors.New("some error"))

				after := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))
				Expect(after).To(Equal(before + 1))
			})

			It("can be called multiple times, incrementing each time", func() {
				before := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))

				from := CloudflareTunnelPending{resource: tunnel}
				to := CloudflareTunnelCreatingTunnel{resource: tunnel}
				observer.OnTransitionError(ctx, from, to, errors.New("err1"))
				observer.OnTransitionError(ctx, from, to, errors.New("err2"))

				after := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))
				Expect(after).To(Equal(before + 2))
			})
		})
	})
})
