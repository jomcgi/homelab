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

// Package statemachine — targeted coverage gap tests
//
// This file fills coverage gaps not addressed by the existing test files:
//
//  1. calculateDeletionState: unrecognised-phase resource with deletion
//     timestamp short-circuits to Unknown (not calculateDeletionState).
//
//  2. RetryBackoff max-cap: RetryCount values well above the cap (7, 8, 100)
//     all produce values near 300s bounded by the 10% jitter.
//     Also fills in counts 3 and 4 which sit between the existing count=2/5
//     and count=9 tests.
//
//  3. SSAPatch for DeletingTunnel with a real TunnelID — verifies the TunnelID
//     is included in the JSON payload.
//
//  4. SSAPatch and ApplyStatus for Deleted — verifies the phase is set and the
//     operation produces a deep copy that does not mutate the original.
//
//  5. IsMaxRetriesExceeded exact boundary: count=9 → false, count=10 → true,
//     combined with Retry() nil/non-nil at the same boundary.
//
//  6. FuncVisitor: Default called for unhandled states even when other specific
//     handlers are registered on the same visitor.
//
//  7. DeletionComplete: resulting Deleted state preserves the resource pointer.
//
//  8. calculateDeletionState — Pending/empty phase with deletion timestamp goes
//     directly to Deleted (no TunnelID → DeletingTunnel.Validate() fails).
package statemachine

import (
	"encoding/json"
	"time"

	"github.com/go-logr/logr"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

// =============================================================================
// calculateDeletionState — unrecognised phase with deletion timestamp
// =============================================================================
//
// Calculate() checks IsKnownPhase() before the deletion-timestamp branch.
// When the phase is unrecognised, it returns Unknown immediately — the
// deletion path (calculateDeletionState) is never entered.

var _ = Describe("Calculate — unrecognised phase with deletion timestamp returns Unknown", func() {
	var calculator *CloudflareTunnelCalculator

	BeforeEach(func() {
		calculator = NewCloudflareTunnelCalculator(logr.Discard())
	})

	It("returns CloudflareTunnelUnknown, not DeletingTunnel or Deleted", func() {
		r := newTunnelWithStatus(v1.CloudflareTunnelStatus{Phase: "BogusPhase"})
		ts := metav1.Now()
		r.DeletionTimestamp = &ts

		state := calculator.Calculate(r)
		u, ok := state.(CloudflareTunnelUnknown)
		Expect(ok).To(BeTrue(), "expected Unknown for unrecognised phase, got %T", state)
		Expect(u.ObservedPhase).To(Equal("BogusPhase"))
	})
})

// =============================================================================
// calculateDeletionState — Pending / empty phase with no TunnelID
// =============================================================================
//
// When a resource is in Pending or empty phase and carries a deletion
// timestamp, calculateDeletionState tries to build a DeletingTunnel state.
// That state's Validate() requires a non-empty TunnelID.  Because Pending
// resources have no TunnelID the validation fails and the calculator falls
// back directly to Deleted.

var _ = Describe("calculateDeletionState — Pending/empty phase goes directly to Deleted", func() {
	var calculator *CloudflareTunnelCalculator

	BeforeEach(func() {
		calculator = NewCloudflareTunnelCalculator(logr.Discard())
	})

	It("returns Deleted when phase is Pending and TunnelID is absent", func() {
		r := newTunnelWithStatus(v1.CloudflareTunnelStatus{Phase: PhasePending})
		ts := metav1.Now()
		r.DeletionTimestamp = &ts

		state := calculator.Calculate(r)
		_, ok := state.(CloudflareTunnelDeleted)
		Expect(ok).To(BeTrue(), "expected Deleted from Pending with no TunnelID, got %T", state)
	})

	It("returns Deleted when phase is empty string and TunnelID is absent", func() {
		r := newTunnel("") // empty phase — treated as initial state
		ts := metav1.Now()
		r.DeletionTimestamp = &ts

		state := calculator.Calculate(r)
		_, ok := state.(CloudflareTunnelDeleted)
		Expect(ok).To(BeTrue(), "expected Deleted from empty phase with no TunnelID, got %T", state)
	})
})

// =============================================================================
// RetryBackoff — max-cap and intermediate values
// =============================================================================
//
// base=5s, multiplier=2, cap=300s, jitter=10%.
// 5s * 2^7 = 640s > 300s → capped → backoff ∈ [270s, 330s].

var _ = Describe("RetryBackoff — max-cap and intermediate values", func() {
	DescribeTable("RetryCount above cap threshold produces ~300s",
		func(count int) {
			failed := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "x",
				ErrorMessage: "y",
				RetryCount:   count,
			}
			backoff := failed.RetryBackoff()
			Expect(backoff).To(BeNumerically(">=", 270*time.Second),
				"RetryCount=%d backoff should be ≥ 270s", count)
			Expect(backoff).To(BeNumerically("<=", 330*time.Second),
				"RetryCount=%d backoff should be ≤ 330s", count)
		},
		Entry("RetryCount=7 (5s*2^7=640s>300s cap)", 7),
		Entry("RetryCount=8 (capped)", 8),
		Entry("RetryCount=100 (far above cap)", 100),
	)

	It("RetryCount=3 produces ~40s (5s * 2^3 = 40s, jitter ±4s)", func() {
		failed := CloudflareTunnelFailed{
			resource:     newTunnel(""),
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   3,
		}
		backoff := failed.RetryBackoff()
		Expect(backoff).To(BeNumerically(">=", 36*time.Second))
		Expect(backoff).To(BeNumerically("<=", 44*time.Second))
	})

	It("RetryCount=4 produces ~80s (5s * 2^4 = 80s, jitter ±8s)", func() {
		failed := CloudflareTunnelFailed{
			resource:     newTunnel(""),
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   4,
		}
		backoff := failed.RetryBackoff()
		Expect(backoff).To(BeNumerically(">=", 72*time.Second))
		Expect(backoff).To(BeNumerically("<=", 88*time.Second))
	})

	It("RetryCount=6 produces ~300s (5s * 2^6 = 320s → capped at 300s ±30s)", func() {
		failed := CloudflareTunnelFailed{
			resource:     newTunnel(""),
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   6,
		}
		backoff := failed.RetryBackoff()
		// 5s * 2^6 = 320s > 300s cap → capped to 300s, jitter ±30s
		Expect(backoff).To(BeNumerically(">=", 270*time.Second))
		Expect(backoff).To(BeNumerically("<=", 330*time.Second))
	})
})

// =============================================================================
// SSAPatch — DeletingTunnel with non-empty TunnelID
// =============================================================================

var _ = Describe("SSAPatch — DeletingTunnel with TunnelID in patch JSON", func() {
	It("includes the TunnelID in the patch JSON for DeletingTunnel", func() {
		r := newTunnel(PhaseDeletingTunnel)
		r.Name = "deleting-tunnel"
		s := CloudflareTunnelDeletingTunnel{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "cfid-delete-me"},
		}

		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data, err := patch.Data(&v1.CloudflareTunnel{})
		Expect(err).NotTo(HaveOccurred())

		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.Phase).To(Equal(PhaseDeletingTunnel))
		Expect(obj.Status.TunnelID).To(Equal("cfid-delete-me"))
	})
})

// =============================================================================
// SSAPatch — Deleted state JSON
// =============================================================================

var _ = Describe("SSAPatch — Deleted state produces valid JSON", func() {
	It("sets phase to Deleted and includes name/namespace in the JSON", func() {
		r := newTunnel(PhaseDeleted)
		r.Name = "fully-deleted-tunnel"
		r.Namespace = "gone"
		s := CloudflareTunnelDeleted{resource: r}

		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data, err := patch.Data(&v1.CloudflareTunnel{})
		Expect(err).NotTo(HaveOccurred())

		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.Phase).To(Equal(PhaseDeleted))
		Expect(obj.Name).To(Equal("fully-deleted-tunnel"))
		Expect(obj.Namespace).To(Equal("gone"))
	})
})

// =============================================================================
// ApplyStatus — Deleted state (deep copy, phase only)
// =============================================================================

var _ = Describe("ApplyStatus — Deleted state", func() {
	It("sets phase to Deleted and does not mutate the original resource", func() {
		r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
			Phase:    PhaseDeletingTunnel,
			TunnelID: "old-tid",
		})
		s := CloudflareTunnelDeleted{resource: r}
		updated := s.ApplyStatus()

		Expect(updated.Status.Phase).To(Equal(PhaseDeleted))
		Expect(r.Status.Phase).To(Equal(PhaseDeletingTunnel), "original resource must not be mutated")
	})

	It("returns a different pointer than the original resource (deep copy)", func() {
		r := newTunnel("")
		s := CloudflareTunnelDeleted{resource: r}
		updated := s.ApplyStatus()
		Expect(updated).NotTo(BeIdenticalTo(r))
	})
})

// =============================================================================
// IsMaxRetriesExceeded — exact boundary at count=9 and count=10
// =============================================================================

var _ = Describe("IsMaxRetriesExceeded — exact boundary", func() {
	It("returns false at RetryCount=9 (last allowed retry)", func() {
		failed := CloudflareTunnelFailed{
			resource:     newTunnel(""),
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   9,
		}
		Expect(failed.IsMaxRetriesExceeded()).To(BeFalse())
	})

	It("returns true at RetryCount=10 (first disallowed retry)", func() {
		failed := CloudflareTunnelFailed{
			resource:     newTunnel(""),
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   10,
		}
		Expect(failed.IsMaxRetriesExceeded()).To(BeTrue())
	})

	It("Retry() returns non-nil at RetryCount=9 (guard passes)", func() {
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

	It("Retry() returns nil at RetryCount=10 (guard fails)", func() {
		failed := CloudflareTunnelFailed{
			resource:     newTunnel(""),
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   10,
		}
		Expect(failed.Retry()).To(BeNil())
	})
})

// =============================================================================
// FuncVisitor — Default invoked for unhandled states when other handlers exist
// =============================================================================

var _ = Describe("FuncVisitor — Default called for unhandled states when other handlers present", func() {
	It("calls Default for CreatingTunnel when only OnPending is registered", func() {
		state := CloudflareTunnelCreatingTunnel{resource: newTunnel("")}
		var defaultCalled bool
		result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{
			OnPending: func(_ CloudflareTunnelPending) string {
				Fail("OnPending must not be invoked for CreatingTunnel")
				return ""
			},
			Default: func(s CloudflareTunnelState) string {
				defaultCalled = true
				return "fallback"
			},
		})
		Expect(defaultCalled).To(BeTrue())
		Expect(result).To(Equal("fallback"))
	})

	It("calls Default for Ready when only OnFailed and OnDeleted are registered", func() {
		state := CloudflareTunnelReady{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			SecretInfo:     SecretInfo{SecretName: "s"},
		}
		var defaultCalled bool
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnFailed: func(_ CloudflareTunnelFailed) bool {
				Fail("OnFailed must not be invoked for Ready")
				return false
			},
			OnDeleted: func(_ CloudflareTunnelDeleted) bool {
				Fail("OnDeleted must not be invoked for Ready")
				return false
			},
			Default: func(_ CloudflareTunnelState) bool {
				defaultCalled = true
				return true
			},
		})
		Expect(defaultCalled).To(BeTrue())
	})

	It("calls Default for Unknown when only OnPending and OnReady are registered", func() {
		state := CloudflareTunnelUnknown{resource: newTunnel(""), ObservedPhase: "corrupted"}
		var defaultReceived CloudflareTunnelState
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnPending: func(_ CloudflareTunnelPending) bool { return false },
			OnReady:   func(_ CloudflareTunnelReady) bool { return false },
			Default: func(s CloudflareTunnelState) bool {
				defaultReceived = s
				return true
			},
		})
		u, ok := defaultReceived.(CloudflareTunnelUnknown)
		Expect(ok).To(BeTrue())
		Expect(u.ObservedPhase).To(Equal("corrupted"))
	})
})

// =============================================================================
// DeletionComplete — resource pointer and phase
// =============================================================================

var _ = Describe("DeletionComplete — resulting Deleted state", func() {
	It("preserves the original resource pointer", func() {
		r := newTunnel(PhaseDeletingTunnel)
		deleting := CloudflareTunnelDeletingTunnel{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "cfid-del"},
		}
		deleted := deleting.DeletionComplete()
		Expect(deleted.Resource()).To(BeIdenticalTo(r))
	})

	It("returns a state with phase Deleted", func() {
		r := newTunnel(PhaseDeletingTunnel)
		deleting := CloudflareTunnelDeletingTunnel{resource: r}
		deleted := deleting.DeletionComplete()
		Expect(deleted.Phase()).To(Equal(PhaseDeleted))
	})

	It("Validate() passes on the resulting Deleted state (no required fields)", func() {
		r := newTunnel(PhaseDeletingTunnel)
		deleting := CloudflareTunnelDeletingTunnel{resource: r}
		deleted := deleting.DeletionComplete()
		Expect(deleted.Validate()).To(Succeed())
	})
})

// =============================================================================
// applyStateToStatus — DeletingTunnel with a populated TunnelID
// =============================================================================

var _ = Describe("applyStateToStatus — DeletingTunnel TunnelID propagation", func() {
	It("sets TunnelID in status when the DeletingTunnel state carries one", func() {
		r := newTunnel(PhaseDeletingTunnel)
		s := CloudflareTunnelDeletingTunnel{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid-in-deletion"},
		}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseDeletingTunnel))
		Expect(updated.Status.TunnelID).To(Equal("tid-in-deletion"))
	})
})
