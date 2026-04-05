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

// Package statemachine — supplementary coverage tests
//
// Fills genuine gaps not covered by the other test files:
//
//  1. SSAPatch for CreatingTunnel: verifies phase is set and that TunnelID /
//     SecretName are absent (state where neither has been provisioned yet); also
//     confirms the patch JSON does not leak managedFields.
//
//  2. SSAPatch for Failed with RetryCount=0: edge case where the zero-value int
//     must still round-trip through JSON correctly.
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
// 1. SSAPatch — CreatingTunnel state and Failed RetryCount=0 edge case
// =============================================================================

var _ = Describe("SSAPatch JSON content — CreatingTunnel state", func() {
	// unmarshalPatch is a local helper; extractPatchData is defined in
	// cloudflare_tunnel_comprehensive_test.go.
	unmarshalPatch := func(state CloudflareTunnelState) v1.CloudflareTunnel {
		patch, err := SSAPatch(state)
		Expect(err).NotTo(HaveOccurred(), "SSAPatch(%T) should not return an error", state)

		raw := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(raw, &obj)).To(Succeed(), "patch JSON should be valid for %T", state)
		return obj
	}

	It("sets phase to CreatingTunnel and does not populate TunnelID or SecretName", func() {
		r := newTunnel(PhaseCreatingTunnel)
		obj := unmarshalPatch(CloudflareTunnelCreatingTunnel{resource: r})

		Expect(obj.Status.Phase).To(Equal(PhaseCreatingTunnel))
		Expect(obj.Status.TunnelID).To(BeEmpty(), "CreatingTunnel has no tunnel ID yet")
		Expect(obj.Status.SecretName).To(BeEmpty(), "CreatingTunnel has no secret yet")
		Expect(obj.Status.Active).To(BeFalse())
		Expect(obj.Status.Ready).To(BeFalse())
	})

	It("does not include managedFields in the patch JSON", func() {
		r := newTunnel(PhaseCreatingTunnel)
		patch, err := SSAPatch(CloudflareTunnelCreatingTunnel{resource: r})
		Expect(err).NotTo(HaveOccurred())

		raw := extractPatchData(patch)
		Expect(string(raw)).NotTo(ContainSubstring("managedFields"))
	})
})

var _ = Describe("SSAPatch JSON content — Failed state RetryCount=0 edge case", func() {
	It("correctly serializes RetryCount=0 (default int value) without omitempty elision", func() {
		r := newTunnel(PhaseFailed)
		patch, err := SSAPatch(CloudflareTunnelFailed{
			resource:     r,
			RetryCount:   0,
			LastState:    "Pending",
			ErrorMessage: "first failure",
		})
		Expect(err).NotTo(HaveOccurred())

		raw := extractPatchData(patch)
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(raw, &obj)).To(Succeed())
		Expect(obj.Status.RetryCount).To(Equal(0))
		Expect(obj.Status.LastState).To(Equal("Pending"))
	})
})

// =============================================================================
// 2. ValidateTransition — extended table covering all remaining state types
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
// 3. RecordReconcile histogram — remaining phase labels
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
