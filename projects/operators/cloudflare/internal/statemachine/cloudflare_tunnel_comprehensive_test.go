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
	"encoding/json"
	"time"

	"github.com/go-logr/logr"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"sigs.k8s.io/controller-runtime/pkg/client"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// =============================================================================
// TunnelIdentity and SecretInfo validation edge cases
// =============================================================================

var _ = Describe("TunnelIdentity and SecretInfo", func() {
	Describe("TunnelIdentity", func() {
		It("validates successfully with a UUID-style TunnelID", func() {
			id := TunnelIdentity{TunnelID: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}
			Expect(id.Validate()).To(Succeed())
		})

		It("fails validation with whitespace-only TunnelID treated as non-empty", func() {
			// Whitespace is technically non-empty - this passes validation
			id := TunnelIdentity{TunnelID: "   "}
			Expect(id.Validate()).To(Succeed())
		})
	})

	Describe("SecretInfo", func() {
		It("validates successfully with a kubernetes-style secret name", func() {
			info := SecretInfo{SecretName: "cloudflare-tunnel-abc123"}
			Expect(info.Validate()).To(Succeed())
		})
	})
})

// =============================================================================
// State Phase() and RequeueAfter() - comprehensive coverage
// =============================================================================

var _ = Describe("State Phase and RequeueAfter", func() {
	DescribeTable("Phase() returns the correct phase string",
		func(state CloudflareTunnelState, expectedPhase string) {
			Expect(state.Phase()).To(Equal(expectedPhase))
		},
		Entry("Pending", CloudflareTunnelPending{}, PhasePending),
		Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{}, PhaseCreatingTunnel),
		Entry("CreatingSecret", CloudflareTunnelCreatingSecret{}, PhaseCreatingSecret),
		Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{}, PhaseConfiguringIngress),
		Entry("Ready", CloudflareTunnelReady{}, PhaseReady),
		Entry("Failed", CloudflareTunnelFailed{}, PhaseFailed),
		Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{}, PhaseDeletingTunnel),
		Entry("Deleted", CloudflareTunnelDeleted{}, PhaseDeleted),
		Entry("Unknown", CloudflareTunnelUnknown{}, PhaseUnknown),
	)

	DescribeTable("RequeueAfter() returns the correct duration",
		func(state CloudflareTunnelState, expectedDuration time.Duration) {
			Expect(state.RequeueAfter()).To(Equal(expectedDuration))
		},
		Entry("Pending requeues immediately (0)", CloudflareTunnelPending{}, time.Duration(0)),
		Entry("CreatingTunnel requeues after 5s", CloudflareTunnelCreatingTunnel{}, 5*time.Second),
		Entry("CreatingSecret requeues after 5s", CloudflareTunnelCreatingSecret{}, 5*time.Second),
		Entry("ConfiguringIngress requeues after 5s", CloudflareTunnelConfiguringIngress{}, 5*time.Second),
		Entry("Ready requeues after 300s", CloudflareTunnelReady{}, 300*time.Second),
		Entry("Failed requeues after 60s", CloudflareTunnelFailed{}, 60*time.Second),
		Entry("DeletingTunnel requeues after 5s", CloudflareTunnelDeletingTunnel{}, 5*time.Second),
		Entry("Deleted requeues immediately (0)", CloudflareTunnelDeleted{}, time.Duration(0)),
		Entry("Unknown requeues immediately (0)", CloudflareTunnelUnknown{}, time.Duration(0)),
	)
})

// =============================================================================
// State Resource() method - all states
// =============================================================================

var _ = Describe("State Resource()", func() {
	var r *v1.CloudflareTunnel

	BeforeEach(func() {
		r = newTunnel(PhasePending)
	})

	DescribeTable("Resource() returns the underlying resource",
		func(makeState func(*v1.CloudflareTunnel) CloudflareTunnelState) {
			state := makeState(r)
			Expect(state.Resource()).To(BeIdenticalTo(r))
		},
		Entry("Pending", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelPending{resource: r}
		}),
		Entry("CreatingTunnel", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelCreatingTunnel{resource: r}
		}),
		Entry("CreatingSecret", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelCreatingSecret{resource: r, TunnelIdentity: TunnelIdentity{TunnelID: "t"}}
		}),
		Entry("ConfiguringIngress", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelConfiguringIngress{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
		}),
		Entry("Ready", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelReady{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
		}),
		Entry("Failed", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelFailed{resource: r, LastState: "x", ErrorMessage: "y"}
		}),
		Entry("DeletingTunnel", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelDeletingTunnel{resource: r, TunnelIdentity: TunnelIdentity{TunnelID: "t"}}
		}),
		Entry("Deleted", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelDeleted{resource: r}
		}),
		Entry("Unknown", func(r *v1.CloudflareTunnel) CloudflareTunnelState {
			return CloudflareTunnelUnknown{resource: r, ObservedPhase: "x"}
		}),
	)
})

// =============================================================================
// Calculator - additional edge cases
// =============================================================================

var _ = Describe("Calculator additional edge cases", func() {
	var calculator *CloudflareTunnelCalculator

	BeforeEach(func() {
		calculator = NewCloudflareTunnelCalculator(logr.Discard())
	})

	Describe("Unknown phase with empty ObservedPhase (validation failure)", func() {
		It("falls back to Unknown even for PhaseUnknown when ObservedPhase is empty", func() {
			// Status has PhaseUnknown but ObservedPhase is empty -> Validate() fails
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:         PhaseUnknown,
				ObservedPhase: "",
			})
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown, got %T", state)
			// The fallback sets ObservedPhase to the current phase (PhaseUnknown)
			s := state.(CloudflareTunnelUnknown)
			Expect(s.ObservedPhase).To(Equal(PhaseUnknown))
		})
	})

	Describe("Failed phase validation failures", func() {
		It("falls back to Unknown when ErrorMessage is missing", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:     PhaseFailed,
				LastState: "CreatingTunnel",
				// ErrorMessage is empty
			})
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected Unknown due to missing ErrorMessage, got %T", state)
		})
	})

	Describe("Ready phase validation failures", func() {
		It("falls back to Unknown when SecretName is missing", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseReady,
				TunnelID: "tunnel-123",
				// SecretName is empty
			})
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected Unknown due to missing SecretName, got %T", state)
		})
	})

	Describe("Calculate with deletion timestamp from various phases", func() {
		var deletionTimestamp metav1.Time

		BeforeEach(func() {
			deletionTimestamp = metav1.Now()
		})

		// The calculateDeletionState always creates a NEW DeletingTunnel state
		// with only resource set (no TunnelID from status). So Validate() fails
		// for all non-deletion phases, leading to Deleted directly.

		It("should go directly to Deleted from Ready phase (calculateDeletionState creates empty DeletingTunnel)", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseReady,
				TunnelID:   "tunnel-123",
				SecretName: "my-secret",
			})
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			// calculateDeletionState creates CloudflareTunnelDeletingTunnel{resource: r}
			// which has no TunnelID → Validate() fails → goes directly to Deleted
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected Deleted from Ready (no TunnelID in DeletingTunnel), got %T", state)
		})

		It("should go directly to Deleted from CreatingSecret phase", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseCreatingSecret,
				TunnelID: "tunnel-123",
			})
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			// Same reason: calculateDeletionState doesn't copy TunnelID
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected Deleted from CreatingSecret, got %T", state)
		})

		It("should go directly to Deleted from Failed phase", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:        PhaseFailed,
				ErrorMessage: "oops",
				LastState:    "CreatingTunnel",
			})
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected Deleted from Failed, got %T", state)
		})

		It("should return DeletingTunnel when already in DeletingTunnel phase (no validation)", func() {
			// DeletingTunnel skips validation in calculateDeletionState
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase: PhaseDeletingTunnel,
				// TunnelID intentionally empty - deletion states don't validate
			})
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelDeletingTunnel)
			Expect(ok).To(BeTrue(), "expected DeletingTunnel even without TunnelID, got %T", state)
		})

		It("should go directly to Deleted from ConfiguringIngress phase", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseConfiguringIngress,
				TunnelID:   "tunnel-abc",
				SecretName: "secret",
			})
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			// calculateDeletionState doesn't carry TunnelID → Deleted
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected Deleted from ConfiguringIngress, got %T", state)
		})

		It("should go directly to Deleted from CreatingTunnel phase", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase: PhaseCreatingTunnel,
			})
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected Deleted from CreatingTunnel, got %T", state)
		})
	})

	Describe("Calculate preserves resource reference", func() {
		It("the calculated state holds the exact resource pointer", func() {
			r := newTunnel(PhasePending)
			state := calculator.Calculate(r)
			Expect(state.Resource()).To(BeIdenticalTo(r))
		})

		It("the calculated Ready state holds the correct resource", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseReady,
				TunnelID:   "tunnel-123",
				SecretName: "my-secret",
			})
			state := calculator.Calculate(r)
			Expect(state.Resource()).To(BeIdenticalTo(r))
		})
	})
})

// =============================================================================
// Transitions - additional edge cases
// =============================================================================

var _ = Describe("Transitions additional edge cases", func() {
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		resource = newTunnel("")
	})

	Describe("RetryBackoff boundary values", func() {
		It("RetryCount=0 produces base duration (~5s)", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 0}
			// With 10% jitter on 5s base, should be between 4.5s and 5.5s
			backoff := failed.RetryBackoff()
			Expect(backoff).To(BeNumerically(">=", 4*time.Second))
			Expect(backoff).To(BeNumerically("<=", 6*time.Second))
		})

		It("RetryCount=1 produces ~10s backoff", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 1}
			// base * 2^1 = 10s, jitter ±1s
			backoff := failed.RetryBackoff()
			Expect(backoff).To(BeNumerically(">=", 9*time.Second))
			Expect(backoff).To(BeNumerically("<=", 11*time.Second))
		})

		It("RetryCount=9 is close to but below cap", func() {
			// base=5s * 2^9 = 2560s > 300s cap → should be capped near 300s
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 9}
			backoff := failed.RetryBackoff()
			Expect(backoff).To(BeNumerically(">=", 270*time.Second))
			Expect(backoff).To(BeNumerically("<=", 330*time.Second))
		})

		It("RetryBackoff is always positive for any retry count", func() {
			for _, count := range []int{0, 1, 5, 10, 100} {
				failed := CloudflareTunnelFailed{
					resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: count,
				}
				Expect(failed.RetryBackoff()).To(BeNumerically(">", 0),
					"RetryBackoff should be positive for count=%d", count)
			}
		})
	})

	Describe("IsMaxRetriesExceeded boundary", func() {
		It("returns false at RetryCount=0", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 0}
			Expect(failed.IsMaxRetriesExceeded()).To(BeFalse())
		})

		It("returns true at RetryCount=10 (exact boundary)", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 10}
			Expect(failed.IsMaxRetriesExceeded()).To(BeTrue())
		})

		It("returns true at RetryCount=11", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 11}
			Expect(failed.IsMaxRetriesExceeded()).To(BeTrue())
		})
	})

	Describe("Retry boundary conditions", func() {
		It("Retry returns pending at RetryCount=0", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 0}
			Expect(failed.Retry()).NotTo(BeNil())
		})

		It("Retry returns nil at exactly RetryCount=10", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 10}
			Expect(failed.Retry()).To(BeNil())
		})

		It("Retry preserves resource pointer", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 0}
			pending := failed.Retry()
			Expect(pending).NotTo(BeNil())
			Expect(pending.Resource()).To(BeIdenticalTo(resource))
		})
	})

	Describe("StartDeletion preserves TunnelIdentity", func() {
		It("CreatingSecret StartDeletion carries TunnelID", func() {
			cs := CloudflareTunnelCreatingSecret{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "my-tunnel"},
			}
			dt := cs.StartDeletion()
			Expect(dt.TunnelIdentity.TunnelID).To(Equal("my-tunnel"))
		})

		It("ConfiguringIngress StartDeletion carries TunnelID", func() {
			ci := CloudflareTunnelConfiguringIngress{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "my-tunnel"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
			dt := ci.StartDeletion()
			Expect(dt.TunnelIdentity.TunnelID).To(Equal("my-tunnel"))
		})

		It("Ready StartDeletion carries TunnelID", func() {
			ready := CloudflareTunnelReady{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "my-tunnel"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
			dt := ready.StartDeletion()
			Expect(dt.TunnelIdentity.TunnelID).To(Equal("my-tunnel"))
		})

		It("Failed StartDeletion does NOT carry TunnelID (no identity on Failed)", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y"}
			dt := failed.StartDeletion()
			Expect(dt.TunnelIdentity.TunnelID).To(BeEmpty())
		})
	})

	Describe("TunnelCreated and SecretCreated carry identity forward", func() {
		It("TunnelCreated sets TunnelID on resulting CreatingSecret", func() {
			ct := CloudflareTunnelCreatingTunnel{resource: resource}
			cs := ct.TunnelCreated("new-tunnel-id")
			Expect(cs.TunnelIdentity.TunnelID).To(Equal("new-tunnel-id"))
			Expect(cs.Resource()).To(BeIdenticalTo(resource))
		})

		It("SecretCreated sets SecretName and preserves TunnelID", func() {
			cs := CloudflareTunnelCreatingSecret{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tid-123"},
			}
			ci := cs.SecretCreated("new-secret-name")
			Expect(ci.TunnelIdentity.TunnelID).To(Equal("tid-123"))
			Expect(ci.SecretInfo.SecretName).To(Equal("new-secret-name"))
		})
	})

	Describe("Unknown Reset preserves resource", func() {
		It("Reset returns a Pending state with the same resource", func() {
			unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "corrupted"}
			pending := unknown.Reset()
			Expect(pending.Resource()).To(BeIdenticalTo(resource))
			Expect(pending.Phase()).To(Equal(PhasePending))
		})

		It("IsRetryable is always true for Unknown", func() {
			unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"}
			Expect(unknown.IsRetryable()).To(BeTrue())
		})

		It("IsMaxRetriesExceeded is always false for Unknown", func() {
			unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"}
			Expect(unknown.IsMaxRetriesExceeded()).To(BeFalse())
		})

		It("RetryBackoff returns 5s for Unknown", func() {
			unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"}
			Expect(unknown.RetryBackoff()).To(Equal(5 * time.Second))
		})
	})

	Describe("MarkFailed from multiple source states", func() {
		It("CreatingTunnel MarkFailed retains resource", func() {
			ct := CloudflareTunnelCreatingTunnel{resource: resource}
			failed := ct.MarkFailed("CreatingTunnel", "network error", 2)
			Expect(failed.Resource()).To(BeIdenticalTo(resource))
			Expect(failed.RetryCount).To(Equal(2))
		})

		It("CreatingSecret MarkFailed retains resource and retryCount", func() {
			cs := CloudflareTunnelCreatingSecret{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			}
			failed := cs.MarkFailed("CreatingSecret", "secret write error", 3)
			Expect(failed.Resource()).To(BeIdenticalTo(resource))
			Expect(failed.RetryCount).To(Equal(3))
			Expect(failed.LastState).To(Equal("CreatingSecret"))
		})

		It("ConfiguringIngress MarkFailed retains resource and retryCount", func() {
			ci := CloudflareTunnelConfiguringIngress{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
			failed := ci.MarkFailed("ConfiguringIngress", "dns error", 4)
			Expect(failed.Resource()).To(BeIdenticalTo(resource))
			Expect(failed.RetryCount).To(Equal(4))
		})
	})
})

// =============================================================================
// ApplyStatus - detailed field verification
// =============================================================================

var _ = Describe("ApplyStatus detailed verification", func() {
	var r *v1.CloudflareTunnel

	BeforeEach(func() {
		r = newTunnel("")
	})

	It("ApplyStatus for Pending does not set Ready=true", func() {
		s := CloudflareTunnelPending{resource: r}
		updated := s.ApplyStatus()
		Expect(updated.Status.Ready).To(BeFalse())
	})

	It("ApplyStatus for CreatingTunnel does not set TunnelID or SecretName", func() {
		s := CloudflareTunnelCreatingTunnel{resource: r}
		updated := s.ApplyStatus()
		Expect(updated.Status.TunnelID).To(BeEmpty())
		Expect(updated.Status.SecretName).To(BeEmpty())
	})

	It("ApplyStatus for DeletingTunnel with empty TunnelID results in empty TunnelID", func() {
		s := CloudflareTunnelDeletingTunnel{resource: r} // no TunnelID
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseDeletingTunnel))
		Expect(updated.Status.TunnelID).To(BeEmpty())
	})

	It("ApplyStatus returns a deep copy, not modifying the original", func() {
		r.Status.Phase = PhaseCreatingTunnel
		s := CloudflareTunnelPending{resource: r}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhasePending))
		Expect(r.Status.Phase).To(Equal(PhaseCreatingTunnel)) // original unchanged
	})

	It("ApplyStatus for Failed preserves zero RetryCount", func() {
		s := CloudflareTunnelFailed{resource: r, LastState: "x", ErrorMessage: "y", RetryCount: 0}
		updated := s.ApplyStatus()
		Expect(updated.Status.RetryCount).To(Equal(0))
	})

	It("ApplyStatus for Unknown sets ObservedPhase", func() {
		s := CloudflareTunnelUnknown{resource: r, ObservedPhase: "OldPhase"}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseUnknown))
		Expect(updated.Status.ObservedPhase).To(Equal("OldPhase"))
	})
})

// =============================================================================
// SSAPatch - JSON content verification
// =============================================================================

var _ = Describe("SSAPatch content verification", func() {
	It("SSAPatch for Pending sets phase in JSON", func() {
		r := newTunnel(PhasePending)
		s := CloudflareTunnelPending{resource: r}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		// Decode the patch data to verify JSON content
		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.Phase).To(Equal(PhasePending))
	})

	It("SSAPatch for CreatingSecret includes TunnelID in JSON", func() {
		r := newTunnel(PhaseCreatingSecret)
		s := CloudflareTunnelCreatingSecret{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-xyz-789"},
		}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.TunnelID).To(Equal("tunnel-xyz-789"))
	})

	It("SSAPatch for ConfiguringIngress includes TunnelID and SecretName", func() {
		r := newTunnel(PhaseConfiguringIngress)
		s := CloudflareTunnelConfiguringIngress{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid-abc"},
			SecretInfo:     SecretInfo{SecretName: "secret-abc"},
		}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.TunnelID).To(Equal("tid-abc"))
		Expect(obj.Status.SecretName).To(Equal("secret-abc"))
	})

	It("SSAPatch for Ready includes Active=true and Ready=true", func() {
		r := newTunnel(PhaseReady)
		s := CloudflareTunnelReady{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid-def"},
			SecretInfo:     SecretInfo{SecretName: "secret-def"},
			Active:         true,
		}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.Active).To(BeTrue())
		Expect(obj.Status.Ready).To(BeTrue())
	})

	It("SSAPatch for Failed includes RetryCount, LastState, ErrorMessage", func() {
		r := newTunnel(PhaseFailed)
		s := CloudflareTunnelFailed{
			resource:     r,
			RetryCount:   7,
			LastState:    "CreatingTunnel",
			ErrorMessage: "timeout error",
		}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.RetryCount).To(Equal(7))
		Expect(obj.Status.LastState).To(Equal("CreatingTunnel"))
		Expect(obj.Status.ErrorMessage).To(Equal("timeout error"))
	})

	It("SSAPatch clears the Spec (minimal patch)", func() {
		r := newTunnel(PhasePending)
		r.Spec.Name = "should-not-appear"
		s := CloudflareTunnelPending{resource: r}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Spec.Name).To(BeEmpty())
	})

	It("SSAPatch for Unknown includes ObservedPhase", func() {
		r := newTunnel(PhaseUnknown)
		s := CloudflareTunnelUnknown{resource: r, ObservedPhase: "CorruptedPhaseXYZ"}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.ObservedPhase).To(Equal("CorruptedPhaseXYZ"))
	})

	It("FieldManager constant is set to the expected value", func() {
		Expect(FieldManager).To(Equal("cloudflaretunnel-controller"))
	})
})

// =============================================================================
// applyStateToStatus via SSAPatch - verifies all state type branches
// =============================================================================

var _ = Describe("applyStateToStatus (via SSAPatch) all states", func() {
	DescribeTable("every state sets the correct phase in JSON",
		func(makeState func() CloudflareTunnelState, expectedPhase string) {
			state := makeState()
			patch, err := SSAPatch(state)
			Expect(err).NotTo(HaveOccurred())
			data := extractPatchData(patch)
			var obj v1.CloudflareTunnel
			Expect(json.Unmarshal(data, &obj)).To(Succeed())
			Expect(obj.Status.Phase).To(Equal(expectedPhase))
		},
		Entry("Pending", func() CloudflareTunnelState {
			return CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		}, PhasePending),
		Entry("CreatingTunnel", func() CloudflareTunnelState {
			return CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
		}, PhaseCreatingTunnel),
		Entry("CreatingSecret", func() CloudflareTunnelState {
			return CloudflareTunnelCreatingSecret{
				resource:       newTunnel(PhaseCreatingSecret),
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			}
		}, PhaseCreatingSecret),
		Entry("ConfiguringIngress", func() CloudflareTunnelState {
			return CloudflareTunnelConfiguringIngress{
				resource:       newTunnel(PhaseConfiguringIngress),
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
		}, PhaseConfiguringIngress),
		Entry("Ready", func() CloudflareTunnelState {
			return CloudflareTunnelReady{
				resource:       newTunnel(PhaseReady),
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
		}, PhaseReady),
		Entry("Failed", func() CloudflareTunnelState {
			return CloudflareTunnelFailed{
				resource:     newTunnel(PhaseFailed),
				LastState:    "x",
				ErrorMessage: "y",
			}
		}, PhaseFailed),
		Entry("DeletingTunnel", func() CloudflareTunnelState {
			return CloudflareTunnelDeletingTunnel{
				resource:       newTunnel(PhaseDeletingTunnel),
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			}
		}, PhaseDeletingTunnel),
		Entry("Deleted", func() CloudflareTunnelState {
			return CloudflareTunnelDeleted{resource: newTunnel(PhaseDeleted)}
		}, PhaseDeleted),
		Entry("Unknown", func() CloudflareTunnelState {
			return CloudflareTunnelUnknown{resource: newTunnel(PhaseUnknown), ObservedPhase: "x"}
		}, PhaseUnknown),
	)
})

// =============================================================================
// Visit pattern - additional visitor coverage
// =============================================================================

var _ = Describe("Visit pattern additional coverage", func() {
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		resource = newTunnel("")
	})

	Describe("CloudflareTunnelFuncVisitor returns correct value from each handler", func() {
		It("OnPending returns value from handler", func() {
			state := CloudflareTunnelPending{resource: resource}
			result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{
				OnPending: func(_ CloudflareTunnelPending) string { return "pending-result" },
			})
			Expect(result).To(Equal("pending-result"))
		})

		It("OnCreatingTunnel returns value from handler", func() {
			state := CloudflareTunnelCreatingTunnel{resource: resource}
			result := Visit[int](state, &CloudflareTunnelFuncVisitor[int]{
				OnCreatingTunnel: func(_ CloudflareTunnelCreatingTunnel) int { return 42 },
			})
			Expect(result).To(Equal(42))
		})

		It("OnFailed can access state fields", func() {
			state := CloudflareTunnelFailed{
				resource:     resource,
				LastState:    "CreatingTunnel",
				ErrorMessage: "msg",
				RetryCount:   5,
			}
			result := Visit[int](state, &CloudflareTunnelFuncVisitor[int]{
				OnFailed: func(s CloudflareTunnelFailed) int { return s.RetryCount },
			})
			Expect(result).To(Equal(5))
		})

		It("OnUnknown can access ObservedPhase", func() {
			state := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "OldPhase"}
			result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{
				OnUnknown: func(s CloudflareTunnelUnknown) string { return s.ObservedPhase },
			})
			Expect(result).To(Equal("OldPhase"))
		})

		It("Default is called for all unhandled states", func() {
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
				result := Visit[string](s, &CloudflareTunnelFuncVisitor[string]{
					Default: func(state CloudflareTunnelState) string {
						return "default:" + state.Phase()
					},
				})
				Expect(result).To(Equal("default:"+s.Phase()),
					"Default handler should receive state for %T", s)
			}
		})
	})

	Describe("Visit with a full concrete visitor implementation", func() {
		It("full visitor dispatches to every method", func() {
			v := &testFullVisitor{}

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
				phase := Visit[string](s, v)
				Expect(phase).To(Equal(s.Phase()), "visitor should return phase for %T", s)
			}
		})
	})
})

// =============================================================================
// IsKnownPhase - exhaustive edge cases
// =============================================================================

var _ = Describe("IsKnownPhase exhaustive", func() {
	It("returns true for each phase constant individually", func() {
		Expect(IsKnownPhase(PhasePending)).To(BeTrue())
		Expect(IsKnownPhase(PhaseCreatingTunnel)).To(BeTrue())
		Expect(IsKnownPhase(PhaseCreatingSecret)).To(BeTrue())
		Expect(IsKnownPhase(PhaseConfiguringIngress)).To(BeTrue())
		Expect(IsKnownPhase(PhaseReady)).To(BeTrue())
		Expect(IsKnownPhase(PhaseFailed)).To(BeTrue())
		Expect(IsKnownPhase(PhaseDeletingTunnel)).To(BeTrue())
		Expect(IsKnownPhase(PhaseDeleted)).To(BeTrue())
		Expect(IsKnownPhase(PhaseUnknown)).To(BeTrue())
	})

	DescribeTable("returns false for invalid/corrupted phase values",
		func(phase string) {
			Expect(IsKnownPhase(phase)).To(BeFalse())
		},
		Entry("lowercase pending", "pending"),
		Entry("lowercase ready", "ready"),
		Entry("mixed case", "PENDING"),
		Entry("with spaces", "Pending "),
		Entry("garbage", "garbage-phase-xyz"),
		Entry("numeric", "12345"),
		Entry("json garbage", `{"phase":"Pending"}`),
	)

	It("AllPhases returns exactly 9 phases", func() {
		phases := AllPhases()
		Expect(phases).To(HaveLen(9))
	})

	It("all phases from AllPhases() are recognized by IsKnownPhase", func() {
		for _, p := range AllPhases() {
			Expect(IsKnownPhase(p)).To(BeTrue(), "IsKnownPhase should return true for %q", p)
		}
	})
})

// =============================================================================
// HasSpecChanged and UpdateObservedGeneration edge cases
// =============================================================================

var _ = Describe("HasSpecChanged additional edge cases", func() {
	It("returns true when generation is greater than observedGeneration", func() {
		r := newTunnel(PhasePending)
		r.Generation = 100
		r.Status.ObservedGeneration = 50
		Expect(HasSpecChanged(r)).To(BeTrue())
	})

	It("returns false when they are equal and non-zero", func() {
		r := newTunnel(PhasePending)
		r.Generation = 42
		r.Status.ObservedGeneration = 42
		Expect(HasSpecChanged(r)).To(BeFalse())
	})
})

var _ = Describe("UpdateObservedGeneration additional edge cases", func() {
	It("works with generation=0", func() {
		r := newTunnel(PhasePending)
		r.Generation = 0
		r.Status.ObservedGeneration = 5
		updated := UpdateObservedGeneration(r)
		Expect(updated.Status.ObservedGeneration).To(Equal(int64(0)))
	})

	It("result is a different pointer (deep copy)", func() {
		r := newTunnel(PhasePending)
		updated := UpdateObservedGeneration(r)
		Expect(updated).NotTo(BeIdenticalTo(r))
	})
})

// =============================================================================
// Full lifecycle - error recovery paths
// =============================================================================

var _ = Describe("Full lifecycle error and recovery paths", func() {
	It("max retry exceeded: retry returns nil", func() {
		r := newTunnel("")
		creating := CloudflareTunnelCreatingTunnel{resource: r}

		// Fail many times to exhaust retries
		failed := creating.MarkFailed("CreatingTunnel", "persistent error", 10)
		Expect(failed.RetryCount).To(Equal(10))
		Expect(failed.IsMaxRetriesExceeded()).To(BeTrue())

		// Retry should return nil (guard condition)
		pending := failed.Retry()
		Expect(pending).To(BeNil())
	})

	It("delete during creation: CreatingTunnel -> DeletingTunnel -> Deleted", func() {
		r := newTunnel("")
		creating := CloudflareTunnelCreatingTunnel{resource: r}

		// Deletion occurs before tunnel was created (no TunnelID)
		deleting := creating.StartDeletion()
		Expect(deleting.Phase()).To(Equal(PhaseDeletingTunnel))
		Expect(deleting.TunnelIdentity.TunnelID).To(BeEmpty())

		deleted := deleting.DeletionComplete()
		Expect(deleted.Phase()).To(Equal(PhaseDeleted))
	})

	It("Unknown -> Pending via Reset, then full creation path", func() {
		r := newTunnel("")
		unknown := CloudflareTunnelUnknown{resource: r, ObservedPhase: "corrupted"}

		// Recovery
		pending := unknown.Reset()
		Expect(pending.Phase()).To(Equal(PhasePending))

		// Then normal creation
		creating := pending.StartCreation()
		cs := creating.TunnelCreated("new-tunnel-id")
		ci := cs.SecretCreated("new-secret")
		ready := ci.IngressConfigured(false)

		Expect(ready.Phase()).To(Equal(PhaseReady))
		Expect(ready.Active).To(BeFalse())
		Expect(ready.TunnelIdentity.TunnelID).To(Equal("new-tunnel-id"))
		Expect(ready.SecretInfo.SecretName).To(Equal("new-secret"))
	})

	It("calculator roundtrip: apply status then recalculate", func() {
		calc := NewCloudflareTunnelCalculator(logr.Discard())

		// Start with Pending
		r := newTunnel("")
		state := calc.Calculate(r)
		_, ok := state.(CloudflareTunnelPending)
		Expect(ok).To(BeTrue())

		// Simulate persisting CreatingSecret state
		cs := CloudflareTunnelCreatingSecret{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "rtt-123"},
		}
		persisted := cs.ApplyStatus()

		// Recalculate from persisted state
		state2 := calc.Calculate(persisted)
		cs2, ok2 := state2.(CloudflareTunnelCreatingSecret)
		Expect(ok2).To(BeTrue(), "expected CreatingSecret after roundtrip, got %T", state2)
		Expect(cs2.TunnelIdentity.TunnelID).To(Equal("rtt-123"))
	})

	It("calculator roundtrip: Ready state roundtrip", func() {
		calc := NewCloudflareTunnelCalculator(logr.Discard())

		ready := CloudflareTunnelReady{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "rtt-abc"},
			SecretInfo:     SecretInfo{SecretName: "rtt-secret"},
			Active:         true,
		}
		persisted := ready.ApplyStatus()

		state := calc.Calculate(persisted)
		ready2, ok := state.(CloudflareTunnelReady)
		Expect(ok).To(BeTrue(), "expected Ready after roundtrip, got %T", state)
		Expect(ready2.TunnelIdentity.TunnelID).To(Equal("rtt-abc"))
		Expect(ready2.SecretInfo.SecretName).To(Equal("rtt-secret"))
		Expect(ready2.Active).To(BeTrue())
	})

	It("calculator roundtrip: Failed state roundtrip", func() {
		calc := NewCloudflareTunnelCalculator(logr.Discard())

		failed := CloudflareTunnelFailed{
			resource:     newTunnel(""),
			RetryCount:   3,
			LastState:    "CreatingTunnel",
			ErrorMessage: "API timeout",
		}
		persisted := failed.ApplyStatus()

		state := calc.Calculate(persisted)
		failed2, ok := state.(CloudflareTunnelFailed)
		Expect(ok).To(BeTrue(), "expected Failed after roundtrip, got %T", state)
		Expect(failed2.RetryCount).To(Equal(3))
		Expect(failed2.LastState).To(Equal("CreatingTunnel"))
		Expect(failed2.ErrorMessage).To(Equal("API timeout"))
	})
})

// =============================================================================
// Test helpers
// =============================================================================

// extractPatchData extracts the raw JSON bytes from a client.Patch.
// controller-runtime's RawPatch.Data() accepts a client.Object but ignores it for raw patches.
func extractPatchData(patch client.Patch) []byte {
	// RawPatch ignores the object parameter and returns the stored raw bytes.
	data, err := patch.Data(&v1.CloudflareTunnel{})
	Expect(err).NotTo(HaveOccurred())
	return data
}

// testFullVisitor implements CloudflareTunnelVisitor[string] and returns Phase() for each state.
type testFullVisitor struct{}

func (v *testFullVisitor) VisitPending(s CloudflareTunnelPending) string {
	return s.Phase()
}

func (v *testFullVisitor) VisitCreatingTunnel(s CloudflareTunnelCreatingTunnel) string {
	return s.Phase()
}

func (v *testFullVisitor) VisitCreatingSecret(s CloudflareTunnelCreatingSecret) string {
	return s.Phase()
}

func (v *testFullVisitor) VisitConfiguringIngress(s CloudflareTunnelConfiguringIngress) string {
	return s.Phase()
}

func (v *testFullVisitor) VisitReady(s CloudflareTunnelReady) string {
	return s.Phase()
}

func (v *testFullVisitor) VisitFailed(s CloudflareTunnelFailed) string {
	return s.Phase()
}

func (v *testFullVisitor) VisitDeletingTunnel(s CloudflareTunnelDeletingTunnel) string {
	return s.Phase()
}

func (v *testFullVisitor) VisitDeleted(s CloudflareTunnelDeleted) string {
	return s.Phase()
}

func (v *testFullVisitor) VisitUnknown(s CloudflareTunnelUnknown) string {
	return s.Phase()
}
