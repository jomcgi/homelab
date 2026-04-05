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

// Package statemachine — final coverage gap tests
//
// Fills the remaining gaps not addressed by existing test files:
//
//  1. SSAPatch JSON content verification for states whose JSON payload was
//     previously only checked for nil / non-nil:
//     CreatingTunnel (phase only), CreatingSecret (TunnelID),
//     ConfiguringIngress (TunnelID + SecretName), Failed (error fields),
//     Unknown (ObservedPhase).
//
//  2. FieldManager constant exact value — existing tests only verify it is
//     non-empty; this file checks the precise string value expected by the
//     controller.
//
//  3. ValidateTransition extended table — existing tests cover Pending,
//     CreatingTunnel, and two CreatingSecret variants; this file adds all
//     remaining concrete state types (ConfiguringIngress, Ready, Failed,
//     DeletingTunnel, Deleted, Unknown) in both valid and invalid forms.
//
//  4. RecordReconcile histogram coverage for the three lifecycle phases not
//     present in the existing table: DeletingTunnel, Deleted, Unknown.
package statemachine

import (
	"encoding/json"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"github.com/prometheus/client_golang/prometheus/testutil"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

// =============================================================================
// 1. SSAPatch — JSON content verification for remaining state types
// =============================================================================

var _ = Describe("SSAPatch JSON content for all state types", func() {
	// unmarshalPatch is a local helper that decodes a patch into a CloudflareTunnel.
	// We reuse extractPatchData defined in cloudflare_tunnel_comprehensive_test.go.
	unmarshalPatch := func(state CloudflareTunnelState) v1.CloudflareTunnel {
		patch, err := SSAPatch(state)
		Expect(err).NotTo(HaveOccurred(), "SSAPatch(%T) should not return an error", state)

		raw := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(raw, &obj)).To(Succeed(), "patch JSON should be valid for %T", state)
		return obj
	}

	Describe("CreatingTunnel state", func() {
		It("sets phase to CreatingTunnel and does not set TunnelID or SecretName", func() {
			r := newTunnel(PhaseCreatingTunnel)
			obj := unmarshalPatch(CloudflareTunnelCreatingTunnel{resource: r})

			Expect(obj.Status.Phase).To(Equal(PhaseCreatingTunnel))
			Expect(obj.Status.TunnelID).To(BeEmpty(), "CreatingTunnel has no tunnel ID yet")
			Expect(obj.Status.SecretName).To(BeEmpty(), "CreatingTunnel has no secret yet")
			Expect(obj.Status.Active).To(BeFalse())
			Expect(obj.Status.Ready).To(BeFalse())
		})

		It("clears ManagedFields from the patch JSON", func() {
			r := newTunnel(PhaseCreatingTunnel)
			patch, err := SSAPatch(CloudflareTunnelCreatingTunnel{resource: r})
			Expect(err).NotTo(HaveOccurred())

			raw := extractPatchData(patch)
			Expect(string(raw)).NotTo(ContainSubstring("managedFields"))
		})
	})

	Describe("CreatingSecret state", func() {
		It("includes TunnelID in the patch JSON", func() {
			r := newTunnel(PhaseCreatingSecret)
			obj := unmarshalPatch(CloudflareTunnelCreatingSecret{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "cs-tunnel-id"},
			})

			Expect(obj.Status.Phase).To(Equal(PhaseCreatingSecret))
			Expect(obj.Status.TunnelID).To(Equal("cs-tunnel-id"))
			Expect(obj.Status.SecretName).To(BeEmpty(), "secret not yet created in this phase")
		})
	})

	Describe("ConfiguringIngress state", func() {
		It("includes TunnelID and SecretName in the patch JSON", func() {
			r := newTunnel(PhaseConfiguringIngress)
			obj := unmarshalPatch(CloudflareTunnelConfiguringIngress{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "ci-tunnel-id"},
				SecretInfo:     SecretInfo{SecretName: "ci-secret"},
			})

			Expect(obj.Status.Phase).To(Equal(PhaseConfiguringIngress))
			Expect(obj.Status.TunnelID).To(Equal("ci-tunnel-id"))
			Expect(obj.Status.SecretName).To(Equal("ci-secret"))
			Expect(obj.Status.Ready).To(BeFalse())
		})
	})

	Describe("Failed state", func() {
		It("includes RetryCount, LastState, and ErrorMessage in the patch JSON", func() {
			r := newTunnel(PhaseFailed)
			obj := unmarshalPatch(CloudflareTunnelFailed{
				resource:     r,
				RetryCount:   7,
				LastState:    "CreatingTunnel",
				ErrorMessage: "API timeout",
			})

			Expect(obj.Status.Phase).To(Equal(PhaseFailed))
			Expect(obj.Status.RetryCount).To(Equal(7))
			Expect(obj.Status.LastState).To(Equal("CreatingTunnel"))
			Expect(obj.Status.ErrorMessage).To(Equal("API timeout"))
			// Failed state must not set Ready=true
			Expect(obj.Status.Ready).To(BeFalse())
		})

		It("correctly serializes RetryCount=0 (edge: default int value)", func() {
			r := newTunnel(PhaseFailed)
			obj := unmarshalPatch(CloudflareTunnelFailed{
				resource:     r,
				RetryCount:   0,
				LastState:    "Pending",
				ErrorMessage: "first failure",
			})

			Expect(obj.Status.RetryCount).To(Equal(0))
			Expect(obj.Status.LastState).To(Equal("Pending"))
		})
	})

	Describe("Unknown state", func() {
		It("includes ObservedPhase in the patch JSON", func() {
			r := newTunnel(PhaseUnknown)
			obj := unmarshalPatch(CloudflareTunnelUnknown{
				resource:      r,
				ObservedPhase: "SomeCorruptedPhase",
			})

			Expect(obj.Status.Phase).To(Equal(PhaseUnknown))
			Expect(obj.Status.ObservedPhase).To(Equal("SomeCorruptedPhase"))
			Expect(obj.Status.TunnelID).To(BeEmpty())
			Expect(obj.Status.SecretName).To(BeEmpty())
		})
	})
})

// =============================================================================
// 2. FieldManager — exact value
// =============================================================================

var _ = Describe("FieldManager constant", func() {
	It("has the exact value 'cloudflaretunnel-controller'", func() {
		Expect(FieldManager).To(Equal("cloudflaretunnel-controller"))
	})

	It("is non-empty (sanity check)", func() {
		Expect(FieldManager).NotTo(BeEmpty())
	})
})

// =============================================================================
// 3. ValidateTransition — extended table covering all remaining state types
// =============================================================================

var _ = Describe("ValidateTransition extended coverage", func() {
	// from is intentionally set to a simple valid state since ValidateTransition
	// only inspects the 'to' state.
	from := CloudflareTunnelPending{resource: &v1.CloudflareTunnel{}}

	DescribeTable("validates every concrete state type — valid cases",
		func(state CloudflareTunnelState) {
			Expect(ValidateTransition(from, state)).To(Succeed())
		},
		Entry("ConfiguringIngress with TunnelID and SecretName", func() CloudflareTunnelState {
			return CloudflareTunnelConfiguringIngress{
				resource:       newTunnel(PhaseConfiguringIngress),
				TunnelIdentity: TunnelIdentity{TunnelID: "vt-tid"},
				SecretInfo:     SecretInfo{SecretName: "vt-secret"},
			}
		}()),
		Entry("Ready with TunnelID and SecretName", func() CloudflareTunnelState {
			return CloudflareTunnelReady{
				resource:       newTunnel(PhaseReady),
				TunnelIdentity: TunnelIdentity{TunnelID: "vt-tid"},
				SecretInfo:     SecretInfo{SecretName: "vt-secret"},
			}
		}()),
		Entry("Failed with LastState and ErrorMessage", func() CloudflareTunnelState {
			return CloudflareTunnelFailed{
				resource:     newTunnel(PhaseFailed),
				LastState:    "CreatingTunnel",
				ErrorMessage: "some error",
			}
		}()),
		Entry("DeletingTunnel with TunnelID", func() CloudflareTunnelState {
			return CloudflareTunnelDeletingTunnel{
				resource:       newTunnel(PhaseDeletingTunnel),
				TunnelIdentity: TunnelIdentity{TunnelID: "vt-tid"},
			}
		}()),
		Entry("Deleted (always valid)", func() CloudflareTunnelState {
			return CloudflareTunnelDeleted{resource: newTunnel(PhaseDeleted)}
		}()),
		Entry("Unknown with ObservedPhase", func() CloudflareTunnelState {
			return CloudflareTunnelUnknown{
				resource:      newTunnel(PhaseUnknown),
				ObservedPhase: "SomeOldPhase",
			}
		}()),
	)

	DescribeTable("validates every concrete state type — invalid cases",
		func(state CloudflareTunnelState) {
			Expect(ValidateTransition(from, state)).To(HaveOccurred())
		},
		Entry("ConfiguringIngress missing TunnelID", func() CloudflareTunnelState {
			return CloudflareTunnelConfiguringIngress{
				resource:   newTunnel(PhaseConfiguringIngress),
				SecretInfo: SecretInfo{SecretName: "secret"},
			}
		}()),
		Entry("ConfiguringIngress missing SecretName", func() CloudflareTunnelState {
			return CloudflareTunnelConfiguringIngress{
				resource:       newTunnel(PhaseConfiguringIngress),
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			}
		}()),
		Entry("Ready missing TunnelID", func() CloudflareTunnelState {
			return CloudflareTunnelReady{
				resource:   newTunnel(PhaseReady),
				SecretInfo: SecretInfo{SecretName: "secret"},
			}
		}()),
		Entry("Ready missing SecretName", func() CloudflareTunnelState {
			return CloudflareTunnelReady{
				resource:       newTunnel(PhaseReady),
				TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			}
		}()),
		Entry("Failed missing LastState", func() CloudflareTunnelState {
			return CloudflareTunnelFailed{
				resource:     newTunnel(PhaseFailed),
				ErrorMessage: "some error",
			}
		}()),
		Entry("Failed missing ErrorMessage", func() CloudflareTunnelState {
			return CloudflareTunnelFailed{
				resource:  newTunnel(PhaseFailed),
				LastState: "CreatingTunnel",
			}
		}()),
		Entry("DeletingTunnel missing TunnelID", func() CloudflareTunnelState {
			return CloudflareTunnelDeletingTunnel{
				resource: newTunnel(PhaseDeletingTunnel),
			}
		}()),
		Entry("Unknown missing ObservedPhase", func() CloudflareTunnelState {
			return CloudflareTunnelUnknown{
				resource: newTunnel(PhaseUnknown),
			}
		}()),
	)

	It("returns nil when 'to' is nil (regardless of 'from' state)", func() {
		Expect(ValidateTransition(from, nil)).To(Succeed())
	})

	It("returns nil for a nil 'from' state when 'to' is valid", func() {
		to := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		Expect(ValidateTransition(nil, to)).To(Succeed())
	})
})

// =============================================================================
// 4. RecordReconcile histogram — remaining phase labels
// =============================================================================

var _ = Describe("RecordReconcile histogram phases (remaining)", func() {
	DescribeTable("records duration histogram for lifecycle phase without panicking",
		func(phase string) {
			before := testutil.CollectAndCount(reconcileDuration)
			RecordReconcile(phase, 50*time.Millisecond, true)
			after := testutil.CollectAndCount(reconcileDuration)
			// After observing a new phase label, the series count should be >= before.
			Expect(after).To(BeNumerically(">=", before))
		},
		Entry("DeletingTunnel phase", PhaseDeletingTunnel),
		Entry("Deleted phase", PhaseDeleted),
		Entry("Unknown phase", PhaseUnknown),
	)

	DescribeTable("records failure result for lifecycle phase without panicking",
		func(phase string) {
			before := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
			RecordReconcile(phase, 100*time.Millisecond, false)
			after := testutil.ToFloat64(reconcileTotal.WithLabelValues("error"))
			Expect(after).To(Equal(before + 1))
		},
		Entry("DeletingTunnel phase on error", PhaseDeletingTunnel),
		Entry("Deleted phase on error", PhaseDeleted),
		Entry("Unknown phase on error", PhaseUnknown),
	)
})
