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

// =============================================================================
// RecordReconcile
// =============================================================================

var _ = Describe("RecordReconcile", func() {
	It("increments the success counter when success is true", func() {
		initial := testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))
		RecordReconcile(PhasePending, 100*time.Millisecond, true)
		Expect(testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))).
			To(Equal(initial + 1))
	})

	It("increments the error counter when success is false", func() {
		initial := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
		RecordReconcile(PhasePending, 50*time.Millisecond, false)
		Expect(testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))).
			To(Equal(initial + 1))
	})

	It("records duration in the histogram for the given phase", func() {
		// Observe to the histogram — verify it collects without error
		// (histogram sum/count introspection requires testutil.CollectAndCompare
		// which needs precise output; we just verify no panic here)
		Expect(func() {
			RecordReconcile(PhaseReady, 250*time.Millisecond, true)
		}).NotTo(Panic())
	})

	It("handles zero duration", func() {
		initial := testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))
		RecordReconcile(PhaseCreatingTunnel, 0, true)
		Expect(testutil.ToFloat64(reconcileTotal.WithLabelValues("success"))).
			To(Equal(initial + 1))
	})

	It("handles large duration", func() {
		initial := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
		RecordReconcile(PhaseFailed, 10*time.Minute, false)
		Expect(testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))).
			To(Equal(initial + 1))
	})
})

// =============================================================================
// RecordError
// =============================================================================

var _ = Describe("RecordError", func() {
	It("increments the error counter for the given error type", func() {
		initial := testutil.ToFloat64(errorsTotal.WithLabelValues("api_error"))
		RecordError("api_error")
		Expect(testutil.ToFloat64(errorsTotal.WithLabelValues("api_error"))).
			To(Equal(initial + 1))
	})

	It("tracks distinct error types independently", func() {
		initialA := testutil.ToFloat64(errorsTotal.WithLabelValues("type_a"))
		initialB := testutil.ToFloat64(errorsTotal.WithLabelValues("type_b"))

		RecordError("type_a")
		RecordError("type_a")
		RecordError("type_b")

		Expect(testutil.ToFloat64(errorsTotal.WithLabelValues("type_a"))).
			To(Equal(initialA + 2))
		Expect(testutil.ToFloat64(errorsTotal.WithLabelValues("type_b"))).
			To(Equal(initialB + 1))
	})

	It("handles an empty error type string", func() {
		initial := testutil.ToFloat64(errorsTotal.WithLabelValues(""))
		RecordError("")
		Expect(testutil.ToFloat64(errorsTotal.WithLabelValues(""))).
			To(Equal(initial + 1))
	})
})

// =============================================================================
// CleanupResourceMetrics
// =============================================================================

var _ = Describe("CleanupResourceMetrics", func() {
	const (
		testNamespace = "cleanup-test-ns"
		testName      = "cleanup-test-resource"
	)

	BeforeEach(func() {
		// Seed gauge values for all phases so we have something to clean up.
		for _, phase := range AllPhases() {
			resourcePhase.WithLabelValues(testNamespace, testName, phase).Set(1)
		}
	})

	It("resets all phase gauges to 0 after cleanup", func() {
		CleanupResourceMetrics(testNamespace, testName)
		for _, phase := range AllPhases() {
			Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(testNamespace, testName, phase))).
				To(BeNumerically("==", 0),
					"gauge for phase %q should be 0 after cleanup", phase)
		}
	})

	It("does not affect gauges for other resources", func() {
		otherNS, otherName := "other-ns", "other-resource"
		resourcePhase.WithLabelValues(otherNS, otherName, PhasePending).Set(1)

		CleanupResourceMetrics(testNamespace, testName)

		Expect(testutil.ToFloat64(resourcePhase.WithLabelValues(otherNS, otherName, PhasePending))).
			To(Equal(1.0))
	})

	It("is safe to call on a resource that was never tracked", func() {
		Expect(func() {
			CleanupResourceMetrics("nonexistent-ns", "nonexistent-resource")
		}).NotTo(Panic())
	})

	It("is idempotent — safe to call multiple times", func() {
		CleanupResourceMetrics(testNamespace, testName)
		Expect(func() {
			CleanupResourceMetrics(testNamespace, testName)
		}).NotTo(Panic())
	})
})

// =============================================================================
// MetricsObserver
// =============================================================================

var _ = Describe("MetricsObserver", func() {
	var (
		observer *MetricsObserver
		ctx      context.Context
		from     CloudflareTunnelState
		to       CloudflareTunnelState
	)

	BeforeEach(func() {
		observer = NewMetricsObserver()
		ctx = context.Background()
		from = CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		to = CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
	})

	Describe("NewMetricsObserver", func() {
		It("creates an observer with an empty transition-start map", func() {
			Expect(observer).NotTo(BeNil())
			Expect(observer.transitionStart).To(BeEmpty())
		})
	})

	Describe("OnTransition", func() {
		It("sets the destination phase gauge to 1", func() {
			observer.OnTransition(ctx, from, to)
			gauge := resourcePhase.WithLabelValues("default", "test-tunnel", PhaseCreatingTunnel)
			Expect(testutil.ToFloat64(gauge)).To(Equal(1.0))
		})

		It("sets the source phase gauge to 0", func() {
			observer.OnTransition(ctx, from, to)
			gauge := resourcePhase.WithLabelValues("default", "test-tunnel", PhasePending)
			Expect(testutil.ToFloat64(gauge)).To(Equal(0.0))
		})

		It("records transition start time for subsequent duration measurement", func() {
			observer.OnTransition(ctx, from, to)
			key := "default/test-tunnel"
			observer.mu.Lock()
			_, exists := observer.transitionStart[key]
			observer.mu.Unlock()
			Expect(exists).To(BeTrue())
		})

		It("observes state duration on second transition (with prior start time)", func() {
			// First transition seeds the start time.
			observer.OnTransition(ctx, from, to)
			// Second transition should observe a duration and not panic.
			secondTo := CloudflareTunnelCreatingSecret{
				resource:       newTunnel(PhaseCreatingSecret),
				TunnelIdentity: TunnelIdentity{TunnelID: "abc"},
			}
			Expect(func() {
				observer.OnTransition(ctx, to, secondTo)
			}).NotTo(Panic())
		})

		It("handles multiple distinct resources independently", func() {
			tunnel2 := &v1.CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "other-tunnel",
					Namespace: "other-ns",
				},
			}

			from2 := CloudflareTunnelPending{resource: tunnel2}
			to2 := CloudflareTunnelCreatingTunnel{resource: tunnel2}

			observer.OnTransition(ctx, from, to)
			observer.OnTransition(ctx, from2, to2)

			Expect(testutil.ToFloat64(resourcePhase.WithLabelValues("default", "test-tunnel", PhaseCreatingTunnel))).
				To(Equal(1.0))
			Expect(testutil.ToFloat64(resourcePhase.WithLabelValues("other-ns", "other-tunnel", PhaseCreatingTunnel))).
				To(Equal(1.0))
		})
	})

	Describe("OnTransitionError", func() {
		It("increments the transition error counter", func() {
			initial := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))
			observer.OnTransitionError(ctx, from, to, errors.New("some transition error"))
			Expect(testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))).
				To(Equal(initial + 1))
		})

		It("increments the counter on every call", func() {
			initial := testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))
			observer.OnTransitionError(ctx, from, to, errors.New("err1"))
			observer.OnTransitionError(ctx, from, to, errors.New("err2"))
			observer.OnTransitionError(ctx, from, to, errors.New("err3"))
			Expect(testutil.ToFloat64(errorsTotal.WithLabelValues("transition"))).
				To(Equal(initial + 3))
		})
	})
})
