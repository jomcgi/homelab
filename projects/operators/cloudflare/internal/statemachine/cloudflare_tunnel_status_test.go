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

// Package statemachine — unit tests for cloudflare_tunnel_status.go
//
// Covers HasSpecChanged, UpdateObservedGeneration, FieldManager, SSAPatch,
// ApplyStatus for every state, and applyStateToStatus indirectly.
package statemachine

import (
	"encoding/json"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

var _ = Describe("HasSpecChanged", func() {
	DescribeTable("correct comparison of Generation vs ObservedGeneration",
		func(generation, observedGeneration int64, expected bool) {
			r := newTunnel(PhasePending)
			r.Generation = generation
			r.Status.ObservedGeneration = observedGeneration
			Expect(HasSpecChanged(r)).To(Equal(expected))
		},
		Entry("both zero → false", int64(0), int64(0), false),
		Entry("generation ahead → true", int64(3), int64(2), true),
		Entry("equal non-zero → false", int64(5), int64(5), false),
		Entry("observedGeneration ahead → true", int64(1), int64(4), true),
	)

	It("does not mutate the resource", func() {
		r := newTunnel(PhasePending)
		r.Generation = 7
		r.Status.ObservedGeneration = 3
		_ = HasSpecChanged(r)
		Expect(r.Generation).To(Equal(int64(7)))
		Expect(r.Status.ObservedGeneration).To(Equal(int64(3)))
	})
})

var _ = Describe("UpdateObservedGeneration", func() {
	It("sets ObservedGeneration to the current Generation", func() {
		r := newTunnel(PhasePending)
		r.Generation = 12
		r.Status.ObservedGeneration = 0
		updated := UpdateObservedGeneration(r)
		Expect(updated.Status.ObservedGeneration).To(Equal(int64(12)))
	})

	It("returns a deep copy — original is not mutated", func() {
		r := newTunnel(PhasePending)
		r.Generation = 5
		r.Status.ObservedGeneration = 1
		updated := UpdateObservedGeneration(r)
		Expect(r.Status.ObservedGeneration).To(Equal(int64(1)), "original should be unchanged")
		Expect(updated).NotTo(BeIdenticalTo(r), "should return a new pointer")
	})

	It("preserves other status fields in the returned copy", func() {
		r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
			Phase:      PhaseReady,
			TunnelID:   "preserve-tid",
			SecretName: "preserve-sn",
			Active:     true,
			Ready:      true,
		})
		r.Generation = 9
		updated := UpdateObservedGeneration(r)
		Expect(updated.Status.Phase).To(Equal(PhaseReady))
		Expect(updated.Status.TunnelID).To(Equal("preserve-tid"))
		Expect(updated.Status.SecretName).To(Equal("preserve-sn"))
		Expect(updated.Status.Active).To(BeTrue())
		Expect(updated.Status.Ready).To(BeTrue())
	})
})

var _ = Describe("FieldManager constant", func() {
	It("equals 'cloudflaretunnel-controller'", func() {
		Expect(FieldManager).To(Equal("cloudflaretunnel-controller"))
	})
})

var _ = Describe("SSAPatch", func() {
	unmarshalSSAPatch := func(state CloudflareTunnelState) v1.CloudflareTunnel {
		patch, err := SSAPatch(state)
		Expect(err).NotTo(HaveOccurred())
		data, err := patch.Data(&v1.CloudflareTunnel{})
		Expect(err).NotTo(HaveOccurred())
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		return obj
	}

	It("returns a patch with Apply type", func() {
		r := newTunnel(PhasePending)
		patch, err := SSAPatch(CloudflareTunnelPending{resource: r})
		Expect(err).NotTo(HaveOccurred())
		Expect(patch.Type()).To(Equal(client.Apply.Type()))
	})

	It("clears ManagedFields from the patch", func() {
		r := newTunnel(PhasePending)
		r.ManagedFields = []metav1.ManagedFieldsEntry{
			{Manager: "some-controller", Operation: metav1.ManagedFieldsOperationApply},
		}
		obj := unmarshalSSAPatch(CloudflareTunnelPending{resource: r})
		Expect(obj.ManagedFields).To(BeEmpty())
	})

	It("clears Spec in the patch", func() {
		r := newTunnel(PhasePending)
		r.Spec.Name = "should-be-cleared"
		patch, err := SSAPatch(CloudflareTunnelPending{resource: r})
		Expect(err).NotTo(HaveOccurred())
		data, err := patch.Data(&v1.CloudflareTunnel{})
		Expect(err).NotTo(HaveOccurred())
		var obj v1.CloudflareTunnel
		Expect(json.Unmarshal(data, &obj)).To(Succeed())
		Expect(obj.Spec.Name).To(BeEmpty(), "spec should be cleared in SSA patch")
	})

	DescribeTable("sets the correct phase in the patch JSON for each state",
		func(state CloudflareTunnelState, expectedPhase string) {
			obj := unmarshalSSAPatch(state)
			Expect(obj.Status.Phase).To(Equal(expectedPhase))
		},
		Entry("Pending", CloudflareTunnelPending{resource: newTunnel("")}, PhasePending),
		Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: newTunnel("")}, PhaseCreatingTunnel),
		Entry("CreatingSecret", CloudflareTunnelCreatingSecret{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
		}, PhaseCreatingSecret),
		Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			SecretInfo:     SecretInfo{SecretName: "sn"},
		}, PhaseConfiguringIngress),
		Entry("Ready", CloudflareTunnelReady{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			SecretInfo:     SecretInfo{SecretName: "sn"},
		}, PhaseReady),
		Entry("Failed", CloudflareTunnelFailed{
			resource:     newTunnel(""),
			LastState:    "x",
			ErrorMessage: "y",
		}, PhaseFailed),
		Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
		}, PhaseDeletingTunnel),
		Entry("Deleted", CloudflareTunnelDeleted{resource: newTunnel("")}, PhaseDeleted),
		Entry("Unknown", CloudflareTunnelUnknown{
			resource:      newTunnel(""),
			ObservedPhase: "old",
		}, PhaseUnknown),
	)

	It("sets TunnelID in CreatingSecret patch", func() {
		obj := unmarshalSSAPatch(CloudflareTunnelCreatingSecret{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "cs-tid"},
		})
		Expect(obj.Status.TunnelID).To(Equal("cs-tid"))
	})

	It("sets TunnelID and SecretName in ConfiguringIngress patch", func() {
		obj := unmarshalSSAPatch(CloudflareTunnelConfiguringIngress{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "ci-tid"},
			SecretInfo:     SecretInfo{SecretName: "ci-sn"},
		})
		Expect(obj.Status.TunnelID).To(Equal("ci-tid"))
		Expect(obj.Status.SecretName).To(Equal("ci-sn"))
	})

	It("sets Active, TunnelID, SecretName, and Ready in Ready patch", func() {
		obj := unmarshalSSAPatch(CloudflareTunnelReady{
			resource:       newTunnel(""),
			TunnelIdentity: TunnelIdentity{TunnelID: "r-tid"},
			SecretInfo:     SecretInfo{SecretName: "r-sn"},
			Active:         true,
		})
		Expect(obj.Status.TunnelID).To(Equal("r-tid"))
		Expect(obj.Status.SecretName).To(Equal("r-sn"))
		Expect(obj.Status.Active).To(BeTrue())
		Expect(obj.Status.Ready).To(BeTrue())
	})

	It("sets RetryCount, LastState, and ErrorMessage in Failed patch", func() {
		obj := unmarshalSSAPatch(CloudflareTunnelFailed{
			resource:     newTunnel(""),
			RetryCount:   5,
			LastState:    "CreatingTunnel",
			ErrorMessage: "timeout",
		})
		Expect(obj.Status.RetryCount).To(Equal(5))
		Expect(obj.Status.LastState).To(Equal("CreatingTunnel"))
		Expect(obj.Status.ErrorMessage).To(Equal("timeout"))
	})

	It("sets ObservedPhase in Unknown patch", func() {
		obj := unmarshalSSAPatch(CloudflareTunnelUnknown{
			resource:      newTunnel(""),
			ObservedPhase: "SomeOldPhase",
		})
		Expect(obj.Status.ObservedPhase).To(Equal("SomeOldPhase"))
	})
})

var _ = Describe("ApplyStatus", func() {
	It("Pending.ApplyStatus sets phase to Pending", func() {
		r := newTunnel("")
		s := CloudflareTunnelPending{resource: r}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhasePending))
		Expect(updated).NotTo(BeIdenticalTo(r))
	})

	It("CreatingTunnel.ApplyStatus sets phase to CreatingTunnel", func() {
		r := newTunnel("")
		s := CloudflareTunnelCreatingTunnel{resource: r}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseCreatingTunnel))
	})

	It("CreatingSecret.ApplyStatus sets phase and TunnelID", func() {
		r := newTunnel("")
		s := CloudflareTunnelCreatingSecret{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "as-tid"},
		}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseCreatingSecret))
		Expect(updated.Status.TunnelID).To(Equal("as-tid"))
	})

	It("ConfiguringIngress.ApplyStatus sets phase, TunnelID, and SecretName", func() {
		r := newTunnel("")
		s := CloudflareTunnelConfiguringIngress{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "as-tid"},
			SecretInfo:     SecretInfo{SecretName: "as-sn"},
		}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseConfiguringIngress))
		Expect(updated.Status.TunnelID).To(Equal("as-tid"))
		Expect(updated.Status.SecretName).To(Equal("as-sn"))
	})

	It("Ready.ApplyStatus sets phase, TunnelID, SecretName, Active, and Ready=true", func() {
		r := newTunnel("")
		s := CloudflareTunnelReady{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "as-tid"},
			SecretInfo:     SecretInfo{SecretName: "as-sn"},
			Active:         true,
		}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseReady))
		Expect(updated.Status.TunnelID).To(Equal("as-tid"))
		Expect(updated.Status.SecretName).To(Equal("as-sn"))
		Expect(updated.Status.Active).To(BeTrue())
		Expect(updated.Status.Ready).To(BeTrue())
	})

	It("Failed.ApplyStatus sets phase, RetryCount, LastState, and ErrorMessage", func() {
		r := newTunnel("")
		s := CloudflareTunnelFailed{
			resource:     r,
			RetryCount:   3,
			LastState:    "CreatingTunnel",
			ErrorMessage: "some error",
		}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseFailed))
		Expect(updated.Status.RetryCount).To(Equal(3))
		Expect(updated.Status.LastState).To(Equal("CreatingTunnel"))
		Expect(updated.Status.ErrorMessage).To(Equal("some error"))
	})

	It("DeletingTunnel.ApplyStatus sets phase and TunnelID", func() {
		r := newTunnel("")
		s := CloudflareTunnelDeletingTunnel{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "dt-tid"},
		}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseDeletingTunnel))
		Expect(updated.Status.TunnelID).To(Equal("dt-tid"))
	})

	It("Deleted.ApplyStatus sets phase to Deleted", func() {
		r := newTunnel("")
		s := CloudflareTunnelDeleted{resource: r}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseDeleted))
	})

	It("Unknown.ApplyStatus sets phase to Unknown and preserves ObservedPhase", func() {
		r := newTunnel("")
		s := CloudflareTunnelUnknown{resource: r, ObservedPhase: "some-old-phase"}
		updated := s.ApplyStatus()
		Expect(updated.Status.Phase).To(Equal(PhaseUnknown))
		Expect(updated.Status.ObservedPhase).To(Equal("some-old-phase"))
	})

	It("each ApplyStatus returns a deep copy (does not mutate original)", func() {
		r := newTunnel(PhasePending)
		s := CloudflareTunnelPending{resource: r}
		updated := s.ApplyStatus()
		Expect(updated).NotTo(BeIdenticalTo(r))
		// Mutating the result should not affect the original
		updated.Status.Phase = "mutated"
		Expect(r.Status.Phase).NotTo(Equal("mutated"))
	})
})
