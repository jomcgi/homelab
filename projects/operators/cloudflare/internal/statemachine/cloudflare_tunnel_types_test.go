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

// Package statemachine — unit tests for cloudflare_tunnel_types.go
//
// Covers TunnelIdentity.Validate(), SecretInfo.Validate(), Phase() return values,
// RequeueAfter() durations, Validate() for every concrete state type, and
// Resource() pointer preservation.
package statemachine

import (
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

var _ = Describe("TunnelIdentity.Validate", func() {
	It("fails with 'tunnelID is required' when TunnelID is empty", func() {
		id := TunnelIdentity{}
		err := id.Validate()
		Expect(err).To(MatchError("tunnelID is required"))
	})

	It("succeeds when TunnelID is non-empty", func() {
		id := TunnelIdentity{TunnelID: "any-id"}
		Expect(id.Validate()).To(Succeed())
	})

	It("treats whitespace-only TunnelID as non-empty (no trimming)", func() {
		id := TunnelIdentity{TunnelID: "  "}
		Expect(id.Validate()).To(Succeed())
	})
})

var _ = Describe("SecretInfo.Validate", func() {
	It("fails with 'secretName is required' when SecretName is empty", func() {
		si := SecretInfo{}
		err := si.Validate()
		Expect(err).To(MatchError("secretName is required"))
	})

	It("succeeds when SecretName is non-empty", func() {
		si := SecretInfo{SecretName: "my-secret"}
		Expect(si.Validate()).To(Succeed())
	})
})

var _ = Describe("State Phase() values", func() {
	r := &v1.CloudflareTunnel{}

	DescribeTable("each state returns its documented phase string",
		func(state CloudflareTunnelState, expected string) {
			Expect(state.Phase()).To(Equal(expected))
		},
		Entry("Pending", CloudflareTunnelPending{resource: r}, PhasePending),
		Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: r}, PhaseCreatingTunnel),
		Entry("CreatingSecret", CloudflareTunnelCreatingSecret{resource: r}, PhaseCreatingSecret),
		Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{resource: r}, PhaseConfiguringIngress),
		Entry("Ready", CloudflareTunnelReady{resource: r}, PhaseReady),
		Entry("Failed", CloudflareTunnelFailed{resource: r}, PhaseFailed),
		Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{resource: r}, PhaseDeletingTunnel),
		Entry("Deleted", CloudflareTunnelDeleted{resource: r}, PhaseDeleted),
		Entry("Unknown", CloudflareTunnelUnknown{resource: r}, PhaseUnknown),
	)
})

var _ = Describe("State RequeueAfter() durations", func() {
	r := &v1.CloudflareTunnel{}

	DescribeTable("each state returns its documented requeue interval",
		func(state CloudflareTunnelState, expected time.Duration) {
			Expect(state.RequeueAfter()).To(Equal(expected))
		},
		Entry("Pending → 0 (no requeue)", CloudflareTunnelPending{resource: r}, time.Duration(0)),
		Entry("CreatingTunnel → 5s", CloudflareTunnelCreatingTunnel{resource: r}, 5*time.Second),
		Entry("CreatingSecret → 5s", CloudflareTunnelCreatingSecret{resource: r}, 5*time.Second),
		Entry("ConfiguringIngress → 5s", CloudflareTunnelConfiguringIngress{resource: r}, 5*time.Second),
		Entry("Ready → 5m", CloudflareTunnelReady{resource: r}, 5*time.Minute),
		Entry("Failed → 1m", CloudflareTunnelFailed{resource: r}, 1*time.Minute),
		Entry("DeletingTunnel → 5s", CloudflareTunnelDeletingTunnel{resource: r}, 5*time.Second),
		Entry("Deleted → 0 (terminal)", CloudflareTunnelDeleted{resource: r}, time.Duration(0)),
		Entry("Unknown → 0 (no automatic requeue)", CloudflareTunnelUnknown{resource: r}, time.Duration(0)),
	)
})

var _ = Describe("State Validate()", func() {
	Describe("States that always validate successfully", func() {
		It("CloudflareTunnelPending never fails validation", func() {
			Expect(CloudflareTunnelPending{}.Validate()).To(Succeed())
		})

		It("CloudflareTunnelCreatingTunnel never fails validation", func() {
			Expect(CloudflareTunnelCreatingTunnel{}.Validate()).To(Succeed())
		})

		It("CloudflareTunnelDeleted never fails validation", func() {
			Expect(CloudflareTunnelDeleted{}.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelCreatingSecret", func() {
		It("fails when TunnelID is empty", func() {
			Expect(CloudflareTunnelCreatingSecret{}.Validate()).To(HaveOccurred())
		})

		It("succeeds when TunnelID is set", func() {
			s := CloudflareTunnelCreatingSecret{TunnelIdentity: TunnelIdentity{TunnelID: "t"}}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelConfiguringIngress", func() {
		It("fails when both TunnelID and SecretName are empty", func() {
			err := CloudflareTunnelConfiguringIngress{}.Validate()
			Expect(err).To(MatchError("tunnelID is required"))
		})

		It("fails when TunnelID is set but SecretName is empty", func() {
			s := CloudflareTunnelConfiguringIngress{
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			}
			err := s.Validate()
			Expect(err).To(MatchError("secretName is required"))
		})

		It("succeeds when both TunnelID and SecretName are set", func() {
			s := CloudflareTunnelConfiguringIngress{
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelReady", func() {
		It("fails when TunnelID is empty", func() {
			err := CloudflareTunnelReady{SecretInfo: SecretInfo{SecretName: "s"}}.Validate()
			Expect(err).To(MatchError("tunnelID is required"))
		})

		It("fails when SecretName is empty", func() {
			err := CloudflareTunnelReady{TunnelIdentity: TunnelIdentity{TunnelID: "t"}}.Validate()
			Expect(err).To(MatchError("secretName is required"))
		})

		It("succeeds when both TunnelID and SecretName are set", func() {
			s := CloudflareTunnelReady{
				TunnelIdentity: TunnelIdentity{TunnelID: "t"},
				SecretInfo:     SecretInfo{SecretName: "s"},
			}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelFailed", func() {
		It("fails when LastState is empty (checked before ErrorMessage)", func() {
			err := CloudflareTunnelFailed{ErrorMessage: "boom"}.Validate()
			Expect(err).To(MatchError("lastState is required for lastState state"))
		})

		It("fails when ErrorMessage is empty", func() {
			err := CloudflareTunnelFailed{LastState: "CreatingTunnel"}.Validate()
			Expect(err).To(MatchError("errorMessage is required for errorMessage state"))
		})

		It("succeeds when both LastState and ErrorMessage are set", func() {
			s := CloudflareTunnelFailed{LastState: "x", ErrorMessage: "y"}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelDeletingTunnel", func() {
		It("fails when TunnelID is empty", func() {
			Expect(CloudflareTunnelDeletingTunnel{}.Validate()).To(HaveOccurred())
		})

		It("succeeds when TunnelID is set", func() {
			s := CloudflareTunnelDeletingTunnel{TunnelIdentity: TunnelIdentity{TunnelID: "t"}}
			Expect(s.Validate()).To(Succeed())
		})
	})

	Describe("CloudflareTunnelUnknown", func() {
		It("fails when ObservedPhase is empty", func() {
			err := CloudflareTunnelUnknown{}.Validate()
			Expect(err).To(MatchError("observedPhase is required for observedPhase state"))
		})

		It("succeeds when ObservedPhase is set", func() {
			s := CloudflareTunnelUnknown{ObservedPhase: "Ready"}
			Expect(s.Validate()).To(Succeed())
		})
	})
})

var _ = Describe("State Resource() pointer", func() {
	It("each state returns the same resource pointer it was constructed with", func() {
		r := newTunnel("")
		states := []CloudflareTunnelState{
			CloudflareTunnelPending{resource: r},
			CloudflareTunnelCreatingTunnel{resource: r},
			CloudflareTunnelCreatingSecret{resource: r},
			CloudflareTunnelConfiguringIngress{resource: r},
			CloudflareTunnelReady{resource: r},
			CloudflareTunnelFailed{resource: r},
			CloudflareTunnelDeletingTunnel{resource: r},
			CloudflareTunnelDeleted{resource: r},
			CloudflareTunnelUnknown{resource: r},
		}
		for _, s := range states {
			Expect(s.Resource()).To(BeIdenticalTo(r),
				"state %T should return the same resource pointer", s)
		}
	})
})
