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

// Package statemachine contains tests targeting specific coverage gaps in:
//   - cloudflare_tunnel_calculator.go  — calculateNormalState default branch
//   - cloudflare_tunnel_status.go      — HasSpecChanged reverse direction, SSAPatch patch type
//   - cloudflare_tunnel_transitions.go — RetryBackoff concurrent safety
//   - cloudflare_tunnel_visit.go       — FuncVisitor nil-handler zero-values for all 9 states
package statemachine

import (
	"encoding/json"
	"sync"
	"time"

	"github.com/go-logr/logr"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

// =============================================================================
// cloudflare_tunnel_calculator.go — calculateNormalState default branch
// =============================================================================
//
// IsKnownPhase returns true for PhaseDeleted and PhaseDeletingTunnel.
// When a resource carries one of those phases but has NO deletion timestamp,
// Calculate() falls through to calculateNormalState() whose switch statement
// has no arm for those phases — triggering the default branch that returns Unknown.

var _ = Describe("Calculator calculateNormalState default branch", func() {
	var calculator *CloudflareTunnelCalculator

	BeforeEach(func() {
		calculator = NewCloudflareTunnelCalculator(logr.Discard())
	})

	Describe("NewCloudflareTunnelCalculator stores the provided logger", func() {
		It("stores a usable logger on the Log field (no panic when used)", func() {
			calc := NewCloudflareTunnelCalculator(logr.Discard())
			Expect(calc).NotTo(BeNil())
			// The stored logger must be usable; calling methods on a zero-value
			// logr.Logger would panic on some implementations.
			Expect(func() {
				_ = calc.Log.WithValues("test-key", "test-value")
			}).NotTo(Panic())
		})
	})

	Describe("PhaseDeleted without deletion timestamp", func() {
		// PhaseDeleted is a known phase, so IsKnownPhase passes.
		// No DeletionTimestamp means calculateNormalState is called.
		// calculateNormalState has no case for PhaseDeleted → hits default → Unknown.
		It("returns Unknown when phase is Deleted but resource has no deletion timestamp", func() {
			r := newTunnel(PhaseDeleted)
			Expect(r.DeletionTimestamp).To(BeNil())

			state := calculator.Calculate(r)

			s, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown from default branch, got %T", state)
			// The ObservedPhase is set to the current Status.Phase.
			Expect(s.ObservedPhase).To(Equal(PhaseDeleted))
		})

		It("preserves the resource pointer in the returned Unknown state", func() {
			r := newTunnel(PhaseDeleted)
			state := calculator.Calculate(r)
			Expect(state.Resource()).To(BeIdenticalTo(r))
		})
	})

	Describe("PhaseDeletingTunnel without deletion timestamp", func() {
		// Same as above: PhaseDeletingTunnel is known but missing from
		// calculateNormalState's switch — default branch returns Unknown.
		It("returns Unknown when phase is DeletingTunnel but resource has no deletion timestamp", func() {
			r := newTunnel(PhaseDeletingTunnel)
			Expect(r.DeletionTimestamp).To(BeNil())

			state := calculator.Calculate(r)

			s, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown from default branch, got %T", state)
			Expect(s.ObservedPhase).To(Equal(PhaseDeletingTunnel))
		})

		It("preserves the resource pointer in the returned Unknown state", func() {
			r := newTunnel(PhaseDeletingTunnel)
			state := calculator.Calculate(r)
			Expect(state.Resource()).To(BeIdenticalTo(r))
		})
	})

	Describe("calculateDeletionState — PhaseDeleted with deletion timestamp", func() {
		// Ensure the deletion fast-path (already in PhaseDeleted) is correctly reached
		// and does NOT go through calculateNormalState.
		It("returns CloudflareTunnelDeleted when phase is Deleted AND deletion timestamp is set", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{Phase: PhaseDeleted})
			ts := metav1.Now()
			r.DeletionTimestamp = &ts

			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelDeleted with deletion timestamp, got %T", state)
		})
	})

	Describe("calculateDeletionState — PhaseDeletingTunnel with deletion timestamp", func() {
		// Ensure the deletion fast-path (already in PhaseDeletingTunnel) skips
		// validation and returns DeletingTunnel even without a TunnelID.
		It("returns DeletingTunnel even when TunnelID is empty (no validation in deletion path)", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase: PhaseDeletingTunnel,
				// TunnelID intentionally omitted
			})
			ts := metav1.Now()
			r.DeletionTimestamp = &ts

			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelDeletingTunnel)
			Expect(ok).To(BeTrue(), "expected DeletingTunnel even with empty TunnelID, got %T", state)
		})
	})
})

// =============================================================================
// cloudflare_tunnel_status.go — HasSpecChanged, SSAPatch patch type
// =============================================================================

var _ = Describe("Status helpers — additional edge cases", func() {
	Describe("HasSpecChanged", func() {
		It("returns true when observedGeneration exceeds generation (unusual but valid)", func() {
			// This can occur if generation is reset or status was persisted from a
			// future version of the resource.
			r := newTunnel(PhasePending)
			r.Generation = 1
			r.Status.ObservedGeneration = 5
			Expect(HasSpecChanged(r)).To(BeTrue())
		})

		It("returns false for a brand-new resource (both zero)", func() {
			r := newTunnel(PhasePending)
			// Both Generation and ObservedGeneration default to 0.
			Expect(r.Generation).To(Equal(int64(0)))
			Expect(r.Status.ObservedGeneration).To(Equal(int64(0)))
			Expect(HasSpecChanged(r)).To(BeFalse())
		})

		It("returns true immediately after a spec update (generation incremented)", func() {
			r := newTunnel(PhasePending)
			r.Generation = 1
			r.Status.ObservedGeneration = 0
			Expect(HasSpecChanged(r)).To(BeTrue())
		})
	})

	Describe("SSAPatch patch type", func() {
		// The patch must use the Apply type so Kubernetes performs
		// Server-Side Apply semantics.
		It("creates a patch whose type is the Apply patch type", func() {
			r := newTunnel(PhasePending)
			s := CloudflareTunnelPending{resource: r}
			patch, err := SSAPatch(s)
			Expect(err).NotTo(HaveOccurred())
			Expect(patch.Type()).To(Equal(client.Apply.Type()))
		})

		It("creates a patch whose JSON is valid and contains the resource name and namespace", func() {
			r := newTunnel(PhaseReady)
			r.Name = "my-tunnel"
			r.Namespace = "prod"
			s := CloudflareTunnelReady{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
				SecretInfo:     SecretInfo{SecretName: "sec"},
				Active:         true,
			}
			patch, err := SSAPatch(s)
			Expect(err).NotTo(HaveOccurred())

			data, err := patch.Data(&v1.CloudflareTunnel{})
			Expect(err).NotTo(HaveOccurred())

			var obj v1.CloudflareTunnel
			Expect(json.Unmarshal(data, &obj)).To(Succeed())
			Expect(obj.Name).To(Equal("my-tunnel"))
			Expect(obj.Namespace).To(Equal("prod"))
		})

		It("clears ManagedFields in the patch JSON", func() {
			r := newTunnel(PhasePending)
			r.ManagedFields = []metav1.ManagedFieldsEntry{
				{Manager: "old-manager", Operation: metav1.ManagedFieldsOperationApply},
			}
			s := CloudflareTunnelPending{resource: r}
			patch, err := SSAPatch(s)
			Expect(err).NotTo(HaveOccurred())

			data, err := patch.Data(&v1.CloudflareTunnel{})
			Expect(err).NotTo(HaveOccurred())

			var obj v1.CloudflareTunnel
			Expect(json.Unmarshal(data, &obj)).To(Succeed())
			// ManagedFields must be absent from the SSA patch.
			Expect(obj.ManagedFields).To(BeEmpty())
		})
	})

	Describe("UpdateObservedGeneration preserves all other status fields", func() {
		It("copies phase and other status fields to the updated resource", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:        PhaseReady,
				TunnelID:     "tid-abc",
				SecretName:   "sec-abc",
				ErrorMessage: "",
				RetryCount:   0,
				Active:       true,
				Ready:        true,
			})
			r.Generation = 7
			updated := UpdateObservedGeneration(r)

			Expect(updated.Status.ObservedGeneration).To(Equal(int64(7)))
			// Other status fields must be preserved.
			Expect(updated.Status.Phase).To(Equal(PhaseReady))
			Expect(updated.Status.TunnelID).To(Equal("tid-abc"))
			Expect(updated.Status.SecretName).To(Equal("sec-abc"))
			Expect(updated.Status.Active).To(BeTrue())
			Expect(updated.Status.Ready).To(BeTrue())
		})
	})
})

// =============================================================================
// cloudflare_tunnel_transitions.go — RetryBackoff concurrent safety
// =============================================================================

var _ = Describe("Transitions — concurrent safety", func() {
	Describe("RetryBackoff concurrent calls do not race or panic", func() {
		It("handles many concurrent callers without data races or panics", func() {
			failed := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "CreatingTunnel",
				ErrorMessage: "timeout",
				RetryCount:   3,
			}

			const goroutines = 50
			var wg sync.WaitGroup
			results := make([]time.Duration, goroutines)

			for i := 0; i < goroutines; i++ {
				wg.Add(1)
				go func(idx int) {
					defer wg.Done()
					results[idx] = failed.RetryBackoff()
				}(i)
			}
			wg.Wait()

			for i, d := range results {
				Expect(d).To(BeNumerically(">", 0),
					"goroutine %d got non-positive backoff: %v", i, d)
			}
		})

		It("Unknown RetryBackoff is always 5s regardless of concurrent calls", func() {
			unknown := CloudflareTunnelUnknown{resource: newTunnel(""), ObservedPhase: "x"}

			const goroutines = 20
			var wg sync.WaitGroup
			results := make([]time.Duration, goroutines)

			for i := 0; i < goroutines; i++ {
				wg.Add(1)
				go func(idx int) {
					defer wg.Done()
					results[idx] = unknown.RetryBackoff()
				}(i)
			}
			wg.Wait()

			for _, d := range results {
				Expect(d).To(Equal(5 * time.Second))
			}
		})
	})

	Describe("RetryBackoff exponential growth between retry counts", func() {
		// Verify the intermediate retry count (RetryCount=2) falls between base and cap.
		It("RetryCount=2 produces ~20s backoff", func() {
			failed := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "x",
				ErrorMessage: "y",
				RetryCount:   2,
			}
			// base=5s * 2^2 = 20s, jitter ±2s
			backoff := failed.RetryBackoff()
			Expect(backoff).To(BeNumerically(">=", 18*time.Second))
			Expect(backoff).To(BeNumerically("<=", 22*time.Second))
		})

		It("RetryCount=5 produces ~160s backoff", func() {
			failed := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "x",
				ErrorMessage: "y",
				RetryCount:   5,
			}
			// base=5s * 2^5 = 160s, jitter ±16s
			backoff := failed.RetryBackoff()
			Expect(backoff).To(BeNumerically(">=", 144*time.Second))
			Expect(backoff).To(BeNumerically("<=", 176*time.Second))
		})
	})

	Describe("IsRetryable for Failed state", func() {
		It("returns true regardless of retry count", func() {
			for _, count := range []int{0, 5, 10, 100} {
				failed := CloudflareTunnelFailed{
					resource:     newTunnel(""),
					LastState:    "x",
					ErrorMessage: "y",
					RetryCount:   count,
				}
				Expect(failed.IsRetryable()).To(BeTrue(),
					"IsRetryable should be true at RetryCount=%d", count)
			}
		})
	})

	Describe("Retry boundary at exactly RetryCount=9 (last allowed retry)", func() {
		It("Retry succeeds at RetryCount=9 and the new Pending state has the same resource", func() {
			r := newTunnel("")
			failed := CloudflareTunnelFailed{
				resource:     r,
				LastState:    "x",
				ErrorMessage: "y",
				RetryCount:   9,
			}
			pending := failed.Retry()
			Expect(pending).NotTo(BeNil())
			Expect(pending.Phase()).To(Equal(PhasePending))
			Expect(pending.Resource()).To(BeIdenticalTo(r))
		})
	})
})

// =============================================================================
// cloudflare_tunnel_visit.go — FuncVisitor nil-handler zero-values for all types
// =============================================================================

var _ = Describe("Visit — FuncVisitor nil handler zero-value returns", func() {
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		resource = newTunnel("")
	})

	// When neither a specific handler nor Default is set, FuncVisitor must return
	// the zero value of the type parameter T.

	DescribeTable("returns zero int when no handler is set",
		func(state CloudflareTunnelState) {
			result := Visit[int](state, &CloudflareTunnelFuncVisitor[int]{})
			Expect(result).To(Equal(0))
		},
		Entry("Pending", CloudflareTunnelPending{resource: nil}),
		Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: nil}),
		Entry("CreatingSecret", CloudflareTunnelCreatingSecret{resource: nil}),
		Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{resource: nil}),
		Entry("Ready", CloudflareTunnelReady{resource: nil}),
		Entry("Failed", CloudflareTunnelFailed{resource: nil}),
		Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{resource: nil}),
		Entry("Deleted", CloudflareTunnelDeleted{resource: nil}),
		Entry("Unknown", CloudflareTunnelUnknown{resource: nil}),
	)

	DescribeTable("returns zero string when no handler is set",
		func(state CloudflareTunnelState) {
			result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{})
			Expect(result).To(Equal(""))
		},
		Entry("Pending", CloudflareTunnelPending{resource: nil}),
		Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: nil}),
		Entry("CreatingSecret", CloudflareTunnelCreatingSecret{resource: nil}),
		Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{resource: nil}),
		Entry("Ready", CloudflareTunnelReady{resource: nil}),
		Entry("Failed", CloudflareTunnelFailed{resource: nil}),
		Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{resource: nil}),
		Entry("Deleted", CloudflareTunnelDeleted{resource: nil}),
		Entry("Unknown", CloudflareTunnelUnknown{resource: nil}),
	)

	Describe("FuncVisitor specific handler takes precedence over Default", func() {
		It("calls OnCreatingSecret when set, ignores Default", func() {
			state := CloudflareTunnelCreatingSecret{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			}
			specificCalled := false
			defaultCalled := false

			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				OnCreatingSecret: func(_ CloudflareTunnelCreatingSecret) bool {
					specificCalled = true
					return true
				},
				Default: func(_ CloudflareTunnelState) bool {
					defaultCalled = true
					return false
				},
			})

			Expect(specificCalled).To(BeTrue())
			Expect(defaultCalled).To(BeFalse())
		})

		It("calls OnConfiguringIngress when set, ignores Default", func() {
			state := CloudflareTunnelConfiguringIngress{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
				SecretInfo:     SecretInfo{SecretName: "sec"},
			}
			specificCalled := false
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				OnConfiguringIngress: func(_ CloudflareTunnelConfiguringIngress) bool {
					specificCalled = true
					return true
				},
				Default: func(_ CloudflareTunnelState) bool {
					Fail("Default should not be called when specific handler is set")
					return false
				},
			})
			Expect(specificCalled).To(BeTrue())
		})

		It("calls OnDeletingTunnel when set, ignores Default", func() {
			state := CloudflareTunnelDeletingTunnel{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			}
			specificCalled := false
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				OnDeletingTunnel: func(_ CloudflareTunnelDeletingTunnel) bool {
					specificCalled = true
					return true
				},
				Default: func(_ CloudflareTunnelState) bool {
					Fail("Default should not be called when specific handler is set")
					return false
				},
			})
			Expect(specificCalled).To(BeTrue())
		})

		It("calls OnDeleted when set, ignores Default", func() {
			state := CloudflareTunnelDeleted{resource: resource}
			specificCalled := false
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				OnDeleted: func(_ CloudflareTunnelDeleted) bool {
					specificCalled = true
					return true
				},
				Default: func(_ CloudflareTunnelState) bool {
					Fail("Default should not be called when specific handler is set")
					return false
				},
			})
			Expect(specificCalled).To(BeTrue())
		})
	})

	Describe("FuncVisitor Default receives the correct concrete state", func() {
		It("Default receives the original Pending state (not a copy)", func() {
			state := CloudflareTunnelPending{resource: resource}
			var received CloudflareTunnelState
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				Default: func(s CloudflareTunnelState) bool {
					received = s
					return true
				},
			})
			Expect(received).To(Equal(state))
		})

		It("Default receives the original Unknown state with ObservedPhase", func() {
			state := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "OldPhase"}
			var received CloudflareTunnelState
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				Default: func(s CloudflareTunnelState) bool {
					received = s
					return true
				},
			})
			u, ok := received.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue())
			Expect(u.ObservedPhase).To(Equal("OldPhase"))
		})
	})

	Describe("CloudflareTunnelVisitor interface — exhaustive concrete visitor", func() {
		// Verify that Visit correctly routes to all 9 visitor methods.
		It("routes every state to its corresponding Visit method", func() {
			v := &countingVisitor{}
			states := []CloudflareTunnelState{
				CloudflareTunnelPending{resource: resource},
				CloudflareTunnelCreatingTunnel{resource: resource},
				CloudflareTunnelCreatingSecret{resource: resource},
				CloudflareTunnelConfiguringIngress{resource: resource},
				CloudflareTunnelReady{resource: resource},
				CloudflareTunnelFailed{resource: resource},
				CloudflareTunnelDeletingTunnel{resource: resource},
				CloudflareTunnelDeleted{resource: resource},
				CloudflareTunnelUnknown{resource: resource},
			}

			for _, s := range states {
				Visit[struct{}](s, v)
			}

			Expect(v.pending).To(Equal(1))
			Expect(v.creatingTunnel).To(Equal(1))
			Expect(v.creatingSecret).To(Equal(1))
			Expect(v.configuringIngress).To(Equal(1))
			Expect(v.ready).To(Equal(1))
			Expect(v.failed).To(Equal(1))
			Expect(v.deletingTunnel).To(Equal(1))
			Expect(v.deleted).To(Equal(1))
			Expect(v.unknown).To(Equal(1))
		})
	})
})

// =============================================================================
// Test helpers
// =============================================================================

// countingVisitor implements CloudflareTunnelVisitor[struct{}] and counts
// how many times each method was called — used to verify exhaustive dispatch.
type countingVisitor struct {
	pending            int
	creatingTunnel     int
	creatingSecret     int
	configuringIngress int
	ready              int
	failed             int
	deletingTunnel     int
	deleted            int
	unknown            int
}

func (v *countingVisitor) VisitPending(_ CloudflareTunnelPending) struct{} {
	v.pending++
	return struct{}{}
}
func (v *countingVisitor) VisitCreatingTunnel(_ CloudflareTunnelCreatingTunnel) struct{} {
	v.creatingTunnel++
	return struct{}{}
}
func (v *countingVisitor) VisitCreatingSecret(_ CloudflareTunnelCreatingSecret) struct{} {
	v.creatingSecret++
	return struct{}{}
}
func (v *countingVisitor) VisitConfiguringIngress(_ CloudflareTunnelConfiguringIngress) struct{} {
	v.configuringIngress++
	return struct{}{}
}
func (v *countingVisitor) VisitReady(_ CloudflareTunnelReady) struct{} {
	v.ready++
	return struct{}{}
}
func (v *countingVisitor) VisitFailed(_ CloudflareTunnelFailed) struct{} {
	v.failed++
	return struct{}{}
}
func (v *countingVisitor) VisitDeletingTunnel(_ CloudflareTunnelDeletingTunnel) struct{} {
	v.deletingTunnel++
	return struct{}{}
}
func (v *countingVisitor) VisitDeleted(_ CloudflareTunnelDeleted) struct{} {
	v.deleted++
	return struct{}{}
}
func (v *countingVisitor) VisitUnknown(_ CloudflareTunnelUnknown) struct{} {
	v.unknown++
	return struct{}{}
}
