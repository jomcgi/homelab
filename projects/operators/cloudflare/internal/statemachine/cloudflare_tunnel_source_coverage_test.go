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

// Package statemachine — source-file coverage tests
//
// This file adds coverage for behaviour in the six source files that was not
// exercised by the existing test suite:
//
//  1. cloudflare_tunnel_types.go — exact Validate() error message text for
//     every state that can fail validation; Validate() success paths.
//
//  2. cloudflare_tunnel_phases.go — exact constant string values; AllPhases()
//     length; IsKnownPhase exhaustive + case-sensitive table test.
//
//  3. cloudflare_tunnel_calculator.go — Calculator.Calculate() for
//     PhaseReady with Active=false (status field round-trip); roundtrip tests
//     for ConfiguringIngress, DeletingTunnel, and Unknown states.
//
//  4. cloudflare_tunnel_transitions.go — transition idempotency (calling the
//     same transition twice produces identical results); IsRetryable() for
//     CloudflareTunnelFailed; MarkFailed from all three "creating" states.
//
//  5. cloudflare_tunnel_status.go — SSAPatch clears ManagedFields; SSAPatch
//     for Ready with Active=false; HasSpecChanged direction reversal
//     (observedGeneration > generation).
//
//  6. cloudflare_tunnel_visit.go — FuncVisitor with both a specific handler
//     and Default set (specific wins); Visit() with a non-bool generic
//     parameter (int); concrete full-visitor struct via Visit().
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
// 1. cloudflare_tunnel_types.go — Validate() error messages
// =============================================================================

var _ = Describe("Validate() exact error messages", func() {
	Describe("TunnelIdentity", func() {
		It("returns 'tunnelID is required' when TunnelID is empty", func() {
			id := TunnelIdentity{}
			err := id.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(Equal("tunnelID is required"))
		})

		It("returns nil when TunnelID is non-empty", func() {
			id := TunnelIdentity{TunnelID: "abc"}
			Expect(id.Validate()).To(Succeed())
		})
	})

	Describe("SecretInfo", func() {
		It("returns 'secretName is required' when SecretName is empty", func() {
			si := SecretInfo{}
			err := si.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(Equal("secretName is required"))
		})

		It("returns nil when SecretName is non-empty", func() {
			si := SecretInfo{SecretName: "my-secret"}
			Expect(si.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelFailed.Validate()", func() {
		It("returns an error for missing LastState first", func() {
			s := CloudflareTunnelFailed{ErrorMessage: "boom"}
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			// Validate checks LastState before ErrorMessage
			Expect(err.Error()).To(ContainSubstring("lastState is required"))
		})

		It("returns an error for missing ErrorMessage when LastState is present", func() {
			s := CloudflareTunnelFailed{LastState: "CreatingTunnel"}
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("errorMessage is required"))
		})

		It("succeeds when both LastState and ErrorMessage are set", func() {
			s := CloudflareTunnelFailed{
				LastState:    "CreatingTunnel",
				ErrorMessage: "timeout",
			}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelUnknown.Validate()", func() {
		It("returns an error when ObservedPhase is empty", func() {
			s := CloudflareTunnelUnknown{}
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("observedPhase is required"))
		})

		It("succeeds when ObservedPhase is set", func() {
			s := CloudflareTunnelUnknown{ObservedPhase: "Ready"}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelCreatingSecret.Validate()", func() {
		It("returns error when TunnelID is empty", func() {
			s := CloudflareTunnelCreatingSecret{}
			Expect(s.Validate()).To(HaveOccurred())
		})

		It("succeeds when TunnelID is present", func() {
			s := CloudflareTunnelCreatingSecret{TunnelIdentity: TunnelIdentity{TunnelID: "t123"}}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelDeletingTunnel.Validate()", func() {
		It("returns error when TunnelID is empty", func() {
			s := CloudflareTunnelDeletingTunnel{}
			Expect(s.Validate()).To(HaveOccurred())
		})

		It("succeeds when TunnelID is present", func() {
			s := CloudflareTunnelDeletingTunnel{TunnelIdentity: TunnelIdentity{TunnelID: "t123"}}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("States that always validate successfully", func() {
		It("CloudflareTunnelPending.Validate() always succeeds", func() {
			Expect(CloudflareTunnelPending{}.Validate()).To(Succeed())
		})

		It("CloudflareTunnelCreatingTunnel.Validate() always succeeds", func() {
			Expect(CloudflareTunnelCreatingTunnel{}.Validate()).To(Succeed())
		})

		It("CloudflareTunnelDeleted.Validate() always succeeds", func() {
			Expect(CloudflareTunnelDeleted{}.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelConfiguringIngress.Validate() error ordering", func() {
		It("reports TunnelID error before SecretName error", func() {
			// Both fields missing — TunnelIdentity.Validate() runs first
			s := CloudflareTunnelConfiguringIngress{}
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnelID is required"))
		})

		It("reports SecretName error when TunnelID is present but SecretName is absent", func() {
			s := CloudflareTunnelConfiguringIngress{
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			}
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("secretName is required"))
		})
	})

	Describe("CloudflareTunnelReady.Validate() error ordering", func() {
		It("reports TunnelID error before SecretName error", func() {
			s := CloudflareTunnelReady{}
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnelID is required"))
		})

		It("reports SecretName error when TunnelID is present but SecretName is absent", func() {
			s := CloudflareTunnelReady{
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			}
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("secretName is required"))
		})

		It("succeeds when both TunnelID and SecretName are present", func() {
			s := CloudflareTunnelReady{
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
				SecretInfo:     SecretInfo{SecretName: "sn"},
			}
			Expect(s.Validate()).To(Succeed())
		})
	})
})

// =============================================================================
// 2. cloudflare_tunnel_phases.go — constants, AllPhases, IsKnownPhase
// =============================================================================

var _ = Describe("Phase constants exact string values", func() {
	DescribeTable("each constant equals its documented string",
		func(constant, expected string) {
			Expect(constant).To(Equal(expected))
		},
		Entry("PhasePending", PhasePending, "Pending"),
		Entry("PhaseCreatingTunnel", PhaseCreatingTunnel, "CreatingTunnel"),
		Entry("PhaseCreatingSecret", PhaseCreatingSecret, "CreatingSecret"),
		Entry("PhaseConfiguringIngress", PhaseConfiguringIngress, "ConfiguringIngress"),
		Entry("PhaseReady", PhaseReady, "Ready"),
		Entry("PhaseFailed", PhaseFailed, "Failed"),
		Entry("PhaseDeletingTunnel", PhaseDeletingTunnel, "DeletingTunnel"),
		Entry("PhaseDeleted", PhaseDeleted, "Deleted"),
		Entry("PhaseUnknown", PhaseUnknown, "Unknown"),
	)
})

var _ = Describe("AllPhases", func() {
	It("returns exactly 9 phases", func() {
		Expect(AllPhases()).To(HaveLen(9))
	})

	It("contains all nine known phase constants", func() {
		all := AllPhases()
		Expect(all).To(ContainElements(
			PhasePending, PhaseCreatingTunnel, PhaseCreatingSecret,
			PhaseConfiguringIngress, PhaseReady, PhaseFailed,
			PhaseDeletingTunnel, PhaseDeleted, PhaseUnknown,
		))
	})

	It("has no duplicate entries", func() {
		seen := map[string]struct{}{}
		for _, p := range AllPhases() {
			Expect(seen).NotTo(HaveKey(p), "phase %q appears more than once", p)
			seen[p] = struct{}{}
		}
	})
})

var _ = Describe("IsKnownPhase", func() {
	DescribeTable("known phases return true",
		func(phase string) {
			Expect(IsKnownPhase(phase)).To(BeTrue(), "phase %q should be known", phase)
		},
		Entry("empty string (initial state)", ""),
		Entry("Pending", PhasePending),
		Entry("CreatingTunnel", PhaseCreatingTunnel),
		Entry("CreatingSecret", PhaseCreatingSecret),
		Entry("ConfiguringIngress", PhaseConfiguringIngress),
		Entry("Ready", PhaseReady),
		Entry("Failed", PhaseFailed),
		Entry("DeletingTunnel", PhaseDeletingTunnel),
		Entry("Deleted", PhaseDeleted),
		Entry("Unknown", PhaseUnknown),
	)

	DescribeTable("unknown or misspelled phases return false",
		func(phase string) {
			Expect(IsKnownPhase(phase)).To(BeFalse(), "phase %q should be unknown", phase)
		},
		Entry("lowercase pending", "pending"),
		Entry("lowercase ready", "ready"),
		Entry("ALL CAPS", "READY"),
		Entry("mixed case", "createTunnel"),
		Entry("garbage string", "notastate"),
		Entry("single space", " "),
		Entry("null string", "null"),
		Entry("quoted phase", `"Pending"`),
		Entry("phase with suffix", "ReadyNow"),
		Entry("phase with prefix", "NotReady"),
	)
})

// =============================================================================
// 3. cloudflare_tunnel_calculator.go — Ready Active=false roundtrip +
//    roundtrips for ConfiguringIngress, DeletingTunnel, Unknown
// =============================================================================

var _ = Describe("Calculator state roundtrips", func() {
	var calculator *CloudflareTunnelCalculator

	BeforeEach(func() {
		calculator = NewCloudflareTunnelCalculator(logr.Discard())
	})

	Describe("Ready with Active=false", func() {
		It("Calculate loads Active=false from status", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseReady,
				TunnelID:   "tid-inactive",
				SecretName: "sn-inactive",
				Active:     false, // explicitly false
			})
			state := calculator.Calculate(r)
			ready, ok := state.(CloudflareTunnelReady)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelReady, got %T", state)
			Expect(ready.Active).To(BeFalse(), "Active should be false when status.Active=false")
		})

		It("roundtrip Ready(Active=false): ApplyStatus → Calculate preserves Active=false", func() {
			original := CloudflareTunnelReady{
				resource:       newTunnel(""),
				TunnelIdentity: TunnelIdentity{TunnelID: "rt-tid"},
				SecretInfo:     SecretInfo{SecretName: "rt-secret"},
				Active:         false,
			}
			persisted := original.ApplyStatus()

			state := calculator.Calculate(persisted)
			ready, ok := state.(CloudflareTunnelReady)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelReady after roundtrip, got %T", state)
			Expect(ready.Active).To(BeFalse())
			Expect(ready.TunnelIdentity.TunnelID).To(Equal("rt-tid"))
			Expect(ready.SecretInfo.SecretName).To(Equal("rt-secret"))
		})
	})

	Describe("ConfiguringIngress roundtrip", func() {
		It("ApplyStatus → Calculate preserves TunnelID and SecretName", func() {
			original := CloudflareTunnelConfiguringIngress{
				resource:       newTunnel(""),
				TunnelIdentity: TunnelIdentity{TunnelID: "ci-tid"},
				SecretInfo:     SecretInfo{SecretName: "ci-secret"},
			}
			persisted := original.ApplyStatus()

			state := calculator.Calculate(persisted)
			ci, ok := state.(CloudflareTunnelConfiguringIngress)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelConfiguringIngress, got %T", state)
			Expect(ci.TunnelIdentity.TunnelID).To(Equal("ci-tid"))
			Expect(ci.SecretInfo.SecretName).To(Equal("ci-secret"))
		})
	})

	Describe("DeletingTunnel roundtrip with deletion timestamp", func() {
		It("Calculate returns DeletingTunnel when phase is DeletingTunnel and deletion timestamp is set", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseDeletingTunnel,
				TunnelID: "dt-tid",
			})
			ts := metav1.Now()
			r.DeletionTimestamp = &ts

			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelDeletingTunnel)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelDeletingTunnel, got %T", state)
		})

		It("DeletingTunnel phase without deletion timestamp returns Unknown (default branch)", func() {
			// DeletingTunnel is a known phase but calculateNormalState has no case for it
			r := newTunnel(PhaseDeletingTunnel)
			Expect(r.DeletionTimestamp).To(BeNil())

			state := calculator.Calculate(r)
			unknown, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected Unknown for DeletingTunnel without deletion timestamp, got %T", state)
			Expect(unknown.ObservedPhase).To(Equal(PhaseDeletingTunnel))
		})
	})

	Describe("Unknown roundtrip", func() {
		It("ApplyStatus → Calculate restores Unknown with correct ObservedPhase", func() {
			original := CloudflareTunnelUnknown{
				resource:      newTunnel(""),
				ObservedPhase: "SomeOldBrokenPhase",
			}
			persisted := original.ApplyStatus()

			state := calculator.Calculate(persisted)
			unknown, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown after roundtrip, got %T", state)
			Expect(unknown.ObservedPhase).To(Equal("SomeOldBrokenPhase"))
		})
	})

	Describe("Calculator preserves resource pointer through all normal phases", func() {
		DescribeTable("Calculate returns a state whose Resource() is the input resource",
			func(makeResource func() *v1.CloudflareTunnel) {
				r := makeResource()
				state := calculator.Calculate(r)
				Expect(state.Resource()).To(BeIdenticalTo(r))
			},
			Entry("empty phase", func() *v1.CloudflareTunnel { return newTunnel("") }),
			Entry("Pending", func() *v1.CloudflareTunnel { return newTunnel(PhasePending) }),
			Entry("CreatingTunnel", func() *v1.CloudflareTunnel { return newTunnel(PhaseCreatingTunnel) }),
			Entry("CreatingSecret valid", func() *v1.CloudflareTunnel {
				return newTunnelWithStatus(v1.CloudflareTunnelStatus{Phase: PhaseCreatingSecret, TunnelID: "t"})
			}),
			Entry("CreatingSecret invalid (Unknown)", func() *v1.CloudflareTunnel {
				return newTunnel(PhaseCreatingSecret)
			}),
			Entry("Ready valid", func() *v1.CloudflareTunnel {
				return newTunnelWithStatus(v1.CloudflareTunnelStatus{Phase: PhaseReady, TunnelID: "t", SecretName: "s"})
			}),
		)
	})
})

// =============================================================================
// 4. cloudflare_tunnel_transitions.go — idempotency, IsRetryable, MarkFailed
// =============================================================================

var _ = Describe("Transition idempotency", func() {
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		resource = newTunnel("")
	})

	It("calling StartCreation twice produces identical phases", func() {
		pending := CloudflareTunnelPending{resource: resource}
		s1 := pending.StartCreation()
		s2 := pending.StartCreation()
		Expect(s1.Phase()).To(Equal(s2.Phase()))
	})

	It("calling TunnelCreated twice with the same tunnelID produces identical TunnelID", func() {
		creating := CloudflareTunnelCreatingTunnel{resource: resource}
		s1 := creating.TunnelCreated("my-tunnel")
		s2 := creating.TunnelCreated("my-tunnel")
		Expect(s1.TunnelIdentity.TunnelID).To(Equal(s2.TunnelIdentity.TunnelID))
	})

	It("calling SecretCreated twice with same secretName produces identical SecretName", func() {
		cs := CloudflareTunnelCreatingSecret{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
		}
		s1 := cs.SecretCreated("my-secret")
		s2 := cs.SecretCreated("my-secret")
		Expect(s1.SecretInfo.SecretName).To(Equal(s2.SecretInfo.SecretName))
		Expect(s1.TunnelIdentity.TunnelID).To(Equal(s2.TunnelIdentity.TunnelID))
	})

	It("calling IngressConfigured(true) twice yields Active=true both times", func() {
		ci := CloudflareTunnelConfiguringIngress{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			SecretInfo:     SecretInfo{SecretName: "sn"},
		}
		r1 := ci.IngressConfigured(true)
		r2 := ci.IngressConfigured(true)
		Expect(r1.Active).To(BeTrue())
		Expect(r2.Active).To(BeTrue())
	})

	It("calling DeletionComplete twice yields Deleted phase both times", func() {
		dt := CloudflareTunnelDeletingTunnel{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
		}
		d1 := dt.DeletionComplete()
		d2 := dt.DeletionComplete()
		Expect(d1.Phase()).To(Equal(PhaseDeleted))
		Expect(d2.Phase()).To(Equal(PhaseDeleted))
	})
})

var _ = Describe("IsRetryable for CloudflareTunnelFailed", func() {
	It("always returns true regardless of RetryCount", func() {
		for _, count := range []int{0, 1, 5, 9, 10, 100} {
			s := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "CreatingTunnel",
				ErrorMessage: "err",
				RetryCount:   count,
			}
			Expect(s.IsRetryable()).To(BeTrue(),
				"IsRetryable should be true for RetryCount=%d", count)
		}
	})
})

var _ = Describe("MarkFailed from all three creating states", func() {
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		resource = newTunnel("")
	})

	It("MarkFailed from CreatingTunnel sets all failure fields", func() {
		s := CloudflareTunnelCreatingTunnel{resource: resource}
		f := s.MarkFailed("CreatingTunnel", "api error", 2)
		Expect(f.Phase()).To(Equal(PhaseFailed))
		Expect(f.LastState).To(Equal("CreatingTunnel"))
		Expect(f.ErrorMessage).To(Equal("api error"))
		Expect(f.RetryCount).To(Equal(2))
		Expect(f.Resource()).To(BeIdenticalTo(resource))
	})

	It("MarkFailed from CreatingSecret sets all failure fields and loses TunnelID", func() {
		s := CloudflareTunnelCreatingSecret{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
		}
		f := s.MarkFailed("CreatingSecret", "secret error", 3)
		Expect(f.Phase()).To(Equal(PhaseFailed))
		Expect(f.LastState).To(Equal("CreatingSecret"))
		Expect(f.ErrorMessage).To(Equal("secret error"))
		Expect(f.RetryCount).To(Equal(3))
		// Failed state does not carry TunnelIdentity
	})

	It("MarkFailed from ConfiguringIngress preserves error details", func() {
		s := CloudflareTunnelConfiguringIngress{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			SecretInfo:     SecretInfo{SecretName: "sn"},
		}
		f := s.MarkFailed("ConfiguringIngress", "ingress error", 0)
		Expect(f.Phase()).To(Equal(PhaseFailed))
		Expect(f.LastState).To(Equal("ConfiguringIngress"))
		Expect(f.ErrorMessage).To(Equal("ingress error"))
		Expect(f.RetryCount).To(Equal(0))
	})
})

var _ = Describe("Retry() boundary conditions", func() {
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		resource = newTunnel("")
	})

	It("Retry() returns non-nil for RetryCount=0", func() {
		f := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 0}
		Expect(f.Retry()).NotTo(BeNil())
	})

	It("Retry() returns non-nil for RetryCount=9 (one below max)", func() {
		f := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 9}
		result := f.Retry()
		Expect(result).NotTo(BeNil())
		Expect(result.Phase()).To(Equal(PhasePending))
	})

	It("Retry() returns nil for RetryCount=10 (exactly at max)", func() {
		f := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 10}
		Expect(f.Retry()).To(BeNil())
	})

	It("Retry() returns nil for RetryCount=11 (above max)", func() {
		f := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 11}
		Expect(f.Retry()).To(BeNil())
	})
})

var _ = Describe("RetryBackoff for Unknown state", func() {
	It("always returns exactly 5s with no jitter", func() {
		u := CloudflareTunnelUnknown{resource: newTunnel(""), ObservedPhase: "x"}
		// Call multiple times — should always be exactly 5s (no random jitter)
		for i := 0; i < 20; i++ {
			Expect(u.RetryBackoff()).To(Equal(5 * time.Second))
		}
	})
})

// =============================================================================
// 5. cloudflare_tunnel_status.go — SSAPatch clears ManagedFields; Ready
//    Active=false in patch; HasSpecChanged direction reversal
// =============================================================================

var _ = Describe("SSAPatch clears ManagedFields", func() {
	It("ManagedFields set on the resource are absent from the patch JSON", func() {
		r := newTunnel(PhasePending)
		// Populate ManagedFields to verify they are stripped
		r.ManagedFields = []metav1.ManagedFieldsEntry{
			{
				Manager:    "some-controller",
				Operation:  metav1.ManagedFieldsOperationApply,
				APIVersion: "v1",
			},
		}
		Expect(r.ManagedFields).NotTo(BeEmpty())

		s := CloudflareTunnelPending{resource: r}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.ManagedFields).To(BeEmpty(), "ManagedFields should be cleared in the SSA patch")
	})
})

var _ = Describe("SSAPatch for Ready with Active=false", func() {
	It("patch JSON contains active=false and ready=true", func() {
		r := newTunnel(PhaseReady)
		s := CloudflareTunnelReady{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid-inactive"},
			SecretInfo:     SecretInfo{SecretName: "sn-inactive"},
			Active:         false,
		}
		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		data := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Status.Phase).To(Equal(PhaseReady))
		Expect(obj.Status.Active).To(BeFalse())
		Expect(obj.Status.Ready).To(BeTrue())
		Expect(obj.Status.TunnelID).To(Equal("tid-inactive"))
		Expect(obj.Status.SecretName).To(Equal("sn-inactive"))
	})
})

var _ = Describe("HasSpecChanged direction reversal", func() {
	It("returns true when observedGeneration > generation (forward drift)", func() {
		// Unusual but possible if generation was reset
		r := newTunnel(PhasePending)
		r.Generation = 1
		r.Status.ObservedGeneration = 3
		Expect(HasSpecChanged(r)).To(BeTrue())
	})

	It("returns false for a newly created resource (both zero)", func() {
		r := newTunnel("")
		Expect(r.Generation).To(BeZero())
		Expect(r.Status.ObservedGeneration).To(BeZero())
		Expect(HasSpecChanged(r)).To(BeFalse())
	})

	It("HasSpecChanged is pure — does not modify the resource", func() {
		r := newTunnel(PhasePending)
		r.Generation = 4
		r.Status.ObservedGeneration = 2
		before := r.Status.ObservedGeneration
		_ = HasSpecChanged(r)
		Expect(r.Status.ObservedGeneration).To(Equal(before))
	})
})

var _ = Describe("UpdateObservedGeneration deep copy safety", func() {
	It("result has updated observedGeneration while original is unchanged", func() {
		r := newTunnel(PhasePending)
		r.Generation = 7
		r.Status.ObservedGeneration = 0

		updated := UpdateObservedGeneration(r)

		Expect(updated.Status.ObservedGeneration).To(Equal(int64(7)))
		Expect(r.Status.ObservedGeneration).To(Equal(int64(0)), "original must not be mutated")
	})

	It("returns a distinct pointer", func() {
		r := newTunnel(PhasePending)
		updated := UpdateObservedGeneration(r)
		Expect(updated).NotTo(BeIdenticalTo(r))
	})
})

// =============================================================================
// 6. cloudflare_tunnel_visit.go — FuncVisitor specific+Default both set;
//    Visit with int return type; full visitor struct
// =============================================================================

var _ = Describe("FuncVisitor: specific handler takes precedence over Default", func() {
	It("calls the specific handler, not Default, when both are set for the matching state", func() {
		specificCalled := false
		defaultCalled := false

		visitor := &CloudflareTunnelFuncVisitor[bool]{
			OnPending: func(_ CloudflareTunnelPending) bool {
				specificCalled = true
				return true
			},
			Default: func(_ CloudflareTunnelState) bool {
				defaultCalled = true
				return false
			},
		}
		state := CloudflareTunnelPending{resource: newTunnel("")}
		result := Visit[bool](state, visitor)

		Expect(result).To(BeTrue())
		Expect(specificCalled).To(BeTrue(), "specific handler should be called")
		Expect(defaultCalled).To(BeFalse(), "Default should not be called when specific handler is present")
	})

	It("falls through to Default for states without a specific handler", func() {
		defaultCalled := false

		visitor := &CloudflareTunnelFuncVisitor[bool]{
			OnPending: func(_ CloudflareTunnelPending) bool { return true },
			Default: func(_ CloudflareTunnelState) bool {
				defaultCalled = true
				return true
			},
		}
		// CreatingTunnel has no specific handler → should use Default
		state := CloudflareTunnelCreatingTunnel{resource: newTunnel("")}
		Visit[bool](state, visitor)

		Expect(defaultCalled).To(BeTrue())
	})
})

var _ = Describe("Visit() with int generic parameter", func() {
	It("returns the int value from the matching visitor method", func() {
		stateOrder := map[string]int{
			PhasePending:            1,
			PhaseCreatingTunnel:     2,
			PhaseCreatingSecret:     3,
			PhaseConfiguringIngress: 4,
			PhaseReady:              5,
			PhaseFailed:             6,
			PhaseDeletingTunnel:     7,
			PhaseDeleted:            8,
			PhaseUnknown:            9,
		}

		resource := newTunnel("")
		states := []CloudflareTunnelState{
			CloudflareTunnelPending{resource: resource},
			CloudflareTunnelCreatingTunnel{resource: resource},
			CloudflareTunnelCreatingSecret{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}},
			CloudflareTunnelConfiguringIngress{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}, SecretInfo: SecretInfo{SecretName: "s"}},
			CloudflareTunnelReady{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}, SecretInfo: SecretInfo{SecretName: "s"}},
			CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y"},
			CloudflareTunnelDeletingTunnel{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}},
			CloudflareTunnelDeleted{resource: resource},
			CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"},
		}

		visitor := &CloudflareTunnelFuncVisitor[int]{
			OnPending:            func(_ CloudflareTunnelPending) int { return 1 },
			OnCreatingTunnel:     func(_ CloudflareTunnelCreatingTunnel) int { return 2 },
			OnCreatingSecret:     func(_ CloudflareTunnelCreatingSecret) int { return 3 },
			OnConfiguringIngress: func(_ CloudflareTunnelConfiguringIngress) int { return 4 },
			OnReady:              func(_ CloudflareTunnelReady) int { return 5 },
			OnFailed:             func(_ CloudflareTunnelFailed) int { return 6 },
			OnDeletingTunnel:     func(_ CloudflareTunnelDeletingTunnel) int { return 7 },
			OnDeleted:            func(_ CloudflareTunnelDeleted) int { return 8 },
			OnUnknown:            func(_ CloudflareTunnelUnknown) int { return 9 },
		}

		for _, state := range states {
			expected := stateOrder[state.Phase()]
			actual := Visit[int](state, visitor)
			Expect(actual).To(Equal(expected),
				"state %s should return %d, got %d", state.Phase(), expected, actual)
		}
	})
})

// trackingVisitor tracks how many times each VisitX method is called and
// returns the phase string for each state. This implements
// CloudflareTunnelVisitor[string] (distinct from the struct{} countingVisitor
// in cloudflare_tunnel_calculator_status_transitions_visit_test.go).
type trackingVisitor struct {
	pendingCount            int
	creatingTunnelCount     int
	creatingSecretCount     int
	configuringIngressCount int
	readyCount              int
	failedCount             int
	deletingTunnelCount     int
	deletedCount            int
	unknownCount            int
}

func (v *trackingVisitor) VisitPending(_ CloudflareTunnelPending) string {
	v.pendingCount++
	return PhasePending
}

func (v *trackingVisitor) VisitCreatingTunnel(_ CloudflareTunnelCreatingTunnel) string {
	v.creatingTunnelCount++
	return PhaseCreatingTunnel
}

func (v *trackingVisitor) VisitCreatingSecret(_ CloudflareTunnelCreatingSecret) string {
	v.creatingSecretCount++
	return PhaseCreatingSecret
}

func (v *trackingVisitor) VisitConfiguringIngress(_ CloudflareTunnelConfiguringIngress) string {
	v.configuringIngressCount++
	return PhaseConfiguringIngress
}

func (v *trackingVisitor) VisitReady(_ CloudflareTunnelReady) string {
	v.readyCount++
	return PhaseReady
}

func (v *trackingVisitor) VisitFailed(_ CloudflareTunnelFailed) string {
	v.failedCount++
	return PhaseFailed
}

func (v *trackingVisitor) VisitDeletingTunnel(_ CloudflareTunnelDeletingTunnel) string {
	v.deletingTunnelCount++
	return PhaseDeletingTunnel
}

func (v *trackingVisitor) VisitDeleted(_ CloudflareTunnelDeleted) string {
	v.deletedCount++
	return PhaseDeleted
}

func (v *trackingVisitor) VisitUnknown(_ CloudflareTunnelUnknown) string {
	v.unknownCount++
	return PhaseUnknown
}

var _ = Describe("Visit() with concrete full visitor struct (string return type)", func() {
	var visitor *trackingVisitor
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		visitor = &trackingVisitor{}
		resource = newTunnel("")
	})

	DescribeTable("Visit dispatches to the correct method and returns Phase()",
		func(state CloudflareTunnelState) {
			result := Visit[string](state, visitor)
			Expect(result).To(Equal(state.Phase()),
				"Visit should return state.Phase() for state %T", state)
		},
		Entry("Pending", CloudflareTunnelPending{resource: &v1.CloudflareTunnel{}}),
		Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: &v1.CloudflareTunnel{}}),
		Entry("CreatingSecret", CloudflareTunnelCreatingSecret{
			resource:       &v1.CloudflareTunnel{},
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
		}),
		Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{
			resource:       &v1.CloudflareTunnel{},
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			SecretInfo:     SecretInfo{SecretName: "s"},
		}),
		Entry("Ready", CloudflareTunnelReady{
			resource:       &v1.CloudflareTunnel{},
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			SecretInfo:     SecretInfo{SecretName: "s"},
		}),
		Entry("Failed", CloudflareTunnelFailed{
			resource:     &v1.CloudflareTunnel{},
			LastState:    "x",
			ErrorMessage: "y",
		}),
		Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{
			resource:       &v1.CloudflareTunnel{},
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
		}),
		Entry("Deleted", CloudflareTunnelDeleted{resource: &v1.CloudflareTunnel{}}),
		Entry("Unknown", CloudflareTunnelUnknown{resource: &v1.CloudflareTunnel{}, ObservedPhase: "x"}),
	)

	It("each state type calls exactly one visitor method exactly once", func() {
		states := []CloudflareTunnelState{
			CloudflareTunnelPending{resource: resource},
			CloudflareTunnelCreatingTunnel{resource: resource},
			CloudflareTunnelCreatingSecret{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}},
			CloudflareTunnelConfiguringIngress{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}, SecretInfo: SecretInfo{SecretName: "s"}},
			CloudflareTunnelReady{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}, SecretInfo: SecretInfo{SecretName: "s"}},
			CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y"},
			CloudflareTunnelDeletingTunnel{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}},
			CloudflareTunnelDeleted{resource: resource},
			CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"},
		}

		for _, state := range states {
			Visit[string](state, visitor)
		}

		Expect(visitor.pendingCount).To(Equal(1))
		Expect(visitor.creatingTunnelCount).To(Equal(1))
		Expect(visitor.creatingSecretCount).To(Equal(1))
		Expect(visitor.configuringIngressCount).To(Equal(1))
		Expect(visitor.readyCount).To(Equal(1))
		Expect(visitor.failedCount).To(Equal(1))
		Expect(visitor.deletingTunnelCount).To(Equal(1))
		Expect(visitor.deletedCount).To(Equal(1))
		Expect(visitor.unknownCount).To(Equal(1))
	})
})

var _ = Describe("FuncVisitor nil handler and Default nil both return zero value", func() {
	DescribeTable("returns zero bool when both specific handler and Default are nil",
		func(state CloudflareTunnelState) {
			visitor := &CloudflareTunnelFuncVisitor[bool]{}
			result := Visit[bool](state, visitor)
			Expect(result).To(BeFalse(), "expected false (zero bool) for %T", state)
		},
		Entry("Pending", CloudflareTunnelPending{resource: &v1.CloudflareTunnel{}}),
		Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: &v1.CloudflareTunnel{}}),
		Entry("CreatingSecret", CloudflareTunnelCreatingSecret{
			resource:       &v1.CloudflareTunnel{},
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
		}),
		Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{
			resource:       &v1.CloudflareTunnel{},
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			SecretInfo:     SecretInfo{SecretName: "s"},
		}),
		Entry("Ready", CloudflareTunnelReady{
			resource:       &v1.CloudflareTunnel{},
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			SecretInfo:     SecretInfo{SecretName: "s"},
		}),
		Entry("Failed", CloudflareTunnelFailed{
			resource:     &v1.CloudflareTunnel{},
			LastState:    "x",
			ErrorMessage: "y",
		}),
		Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{
			resource:       &v1.CloudflareTunnel{},
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
		}),
		Entry("Deleted", CloudflareTunnelDeleted{resource: &v1.CloudflareTunnel{}}),
		Entry("Unknown", CloudflareTunnelUnknown{
			resource:      &v1.CloudflareTunnel{},
			ObservedPhase: "x",
		}),
	)
})
