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

// Package statemachine — unit tests for cloudflare_tunnel_transitions.go
//
// Covers all transitions, guard conditions, Retry/backoff logic, and
// StartDeletion field propagation via table-driven tests.
package statemachine

import (
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

var _ = Describe("Transitions — happy path", func() {
	Describe("Pending transitions", func() {
		It("StartCreation transitions Pending → CreatingTunnel", func() {
			s := CloudflareTunnelPending{resource: newTunnel("")}
			next := s.StartCreation()
			Expect(next.Phase()).To(Equal(PhaseCreatingTunnel))
			Expect(next.Resource()).To(BeIdenticalTo(s.Resource()))
		})

		It("StartDeletion transitions Pending → DeletingTunnel (no TunnelID)", func() {
			s := CloudflareTunnelPending{resource: newTunnel("")}
			next := s.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.TunnelIdentity.TunnelID).To(BeEmpty())
		})
	})

	Describe("CreatingTunnel transitions", func() {
		It("TunnelCreated transitions CreatingTunnel → CreatingSecret with tunnelID", func() {
			s := CloudflareTunnelCreatingTunnel{resource: newTunnel("")}
			next := s.TunnelCreated("new-tid")
			Expect(next.Phase()).To(Equal(PhaseCreatingSecret))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("new-tid"))
		})

		It("MarkFailed transitions CreatingTunnel → Failed", func() {
			s := CloudflareTunnelCreatingTunnel{resource: newTunnel("")}
			next := s.MarkFailed("CreatingTunnel", "API error", 1)
			Expect(next.Phase()).To(Equal(PhaseFailed))
			Expect(next.LastState).To(Equal("CreatingTunnel"))
			Expect(next.ErrorMessage).To(Equal("API error"))
			Expect(next.RetryCount).To(Equal(1))
		})

		It("StartDeletion transitions CreatingTunnel → DeletingTunnel (no TunnelID)", func() {
			s := CloudflareTunnelCreatingTunnel{resource: newTunnel("")}
			next := s.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.TunnelIdentity.TunnelID).To(BeEmpty())
		})
	})

	Describe("CreatingSecret transitions", func() {
		var cs CloudflareTunnelCreatingSecret

		BeforeEach(func() {
			cs = CloudflareTunnelCreatingSecret{
				resource:       newTunnel(""),
				TunnelIdentity: TunnelIdentity{TunnelID: "cs-tid"},
			}
		})

		It("SecretCreated transitions CreatingSecret → ConfiguringIngress with secretName", func() {
			next := cs.SecretCreated("my-secret")
			Expect(next.Phase()).To(Equal(PhaseConfiguringIngress))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("cs-tid"))
			Expect(next.SecretInfo.SecretName).To(Equal("my-secret"))
		})

		It("MarkFailed transitions CreatingSecret → Failed", func() {
			next := cs.MarkFailed("CreatingSecret", "secret error", 2)
			Expect(next.Phase()).To(Equal(PhaseFailed))
			Expect(next.LastState).To(Equal("CreatingSecret"))
			Expect(next.ErrorMessage).To(Equal("secret error"))
			Expect(next.RetryCount).To(Equal(2))
		})

		It("StartDeletion transitions CreatingSecret → DeletingTunnel with TunnelID", func() {
			next := cs.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("cs-tid"))
		})
	})

	Describe("ConfiguringIngress transitions", func() {
		var ci CloudflareTunnelConfiguringIngress

		BeforeEach(func() {
			ci = CloudflareTunnelConfiguringIngress{
				resource:       newTunnel(""),
				TunnelIdentity: TunnelIdentity{TunnelID: "ci-tid"},
				SecretInfo:     SecretInfo{SecretName: "ci-sn"},
			}
		})

		It("IngressConfigured with active=true transitions ConfiguringIngress → Ready", func() {
			next := ci.IngressConfigured(true)
			Expect(next.Phase()).To(Equal(PhaseReady))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("ci-tid"))
			Expect(next.SecretInfo.SecretName).To(Equal("ci-sn"))
			Expect(next.Active).To(BeTrue())
		})

		It("IngressConfigured with active=false transitions ConfiguringIngress → Ready (inactive)", func() {
			next := ci.IngressConfigured(false)
			Expect(next.Phase()).To(Equal(PhaseReady))
			Expect(next.Active).To(BeFalse())
		})

		It("MarkFailed transitions ConfiguringIngress → Failed", func() {
			next := ci.MarkFailed("ConfiguringIngress", "ingress error", 0)
			Expect(next.Phase()).To(Equal(PhaseFailed))
			Expect(next.LastState).To(Equal("ConfiguringIngress"))
		})

		It("StartDeletion transitions ConfiguringIngress → DeletingTunnel with TunnelID", func() {
			next := ci.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("ci-tid"))
		})
	})

	Describe("Ready transitions", func() {
		var ready CloudflareTunnelReady

		BeforeEach(func() {
			ready = CloudflareTunnelReady{
				resource:       newTunnel(""),
				TunnelIdentity: TunnelIdentity{TunnelID: "r-tid"},
				SecretInfo:     SecretInfo{SecretName: "r-sn"},
				Active:         true,
			}
		})

		It("StartDeletion transitions Ready → DeletingTunnel propagating TunnelID", func() {
			next := ready.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("r-tid"))
		})

		It("ReconfigureIngress transitions Ready → ConfiguringIngress preserving TunnelID and SecretName", func() {
			next := ready.ReconfigureIngress()
			Expect(next.Phase()).To(Equal(PhaseConfiguringIngress))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("r-tid"))
			Expect(next.SecretInfo.SecretName).To(Equal("r-sn"))
		})
	})

	Describe("DeletingTunnel transitions", func() {
		It("DeletionComplete transitions DeletingTunnel → Deleted", func() {
			s := CloudflareTunnelDeletingTunnel{
				resource:       newTunnel(""),
				TunnelIdentity: TunnelIdentity{TunnelID: "dt-tid"},
			}
			next := s.DeletionComplete()
			Expect(next.Phase()).To(Equal(PhaseDeleted))
			Expect(next.Resource()).To(BeIdenticalTo(s.Resource()))
		})
	})

	Describe("Failed transitions", func() {
		It("Retry returns a Pending state when RetryCount < 10", func() {
			s := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "x",
				ErrorMessage: "y",
				RetryCount:   5,
			}
			result := s.Retry()
			Expect(result).NotTo(BeNil())
			Expect(result.Phase()).To(Equal(PhasePending))
		})

		It("Retry returns nil when RetryCount == 10 (exactly at max)", func() {
			s := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "x",
				ErrorMessage: "y",
				RetryCount:   10,
			}
			Expect(s.Retry()).To(BeNil())
		})

		It("Retry returns nil when RetryCount > 10", func() {
			s := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "x",
				ErrorMessage: "y",
				RetryCount:   15,
			}
			Expect(s.Retry()).To(BeNil())
		})

		It("StartDeletion transitions Failed → DeletingTunnel", func() {
			s := CloudflareTunnelFailed{
				resource:     newTunnel(""),
				LastState:    "x",
				ErrorMessage: "y",
			}
			next := s.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
		})
	})

	Describe("Unknown transitions", func() {
		It("Reset transitions Unknown → Pending", func() {
			s := CloudflareTunnelUnknown{resource: newTunnel(""), ObservedPhase: "old"}
			next := s.Reset()
			Expect(next.Phase()).To(Equal(PhasePending))
			Expect(next.Resource()).To(BeIdenticalTo(s.Resource()))
		})
	})
})

var _ = Describe("Transitions — guard conditions and helpers", func() {
	Describe("Failed.IsRetryable", func() {
		It("always returns true regardless of RetryCount", func() {
			for _, count := range []int{0, 5, 9, 10, 100} {
				s := CloudflareTunnelFailed{
					resource: newTunnel(""), LastState: "x", ErrorMessage: "y",
					RetryCount: count,
				}
				Expect(s.IsRetryable()).To(BeTrue())
			}
		})
	})

	Describe("Failed.IsMaxRetriesExceeded", func() {
		DescribeTable("boundary checks at max=10",
			func(count int, expected bool) {
				s := CloudflareTunnelFailed{
					resource: newTunnel(""), LastState: "x", ErrorMessage: "y",
					RetryCount: count,
				}
				Expect(s.IsMaxRetriesExceeded()).To(Equal(expected))
			},
			Entry("count=9 → false", 9, false),
			Entry("count=10 → true", 10, true),
			Entry("count=11 → true", 11, true),
			Entry("count=0 → false", 0, false),
		)
	})

	Describe("Unknown.IsRetryable", func() {
		It("always returns true", func() {
			s := CloudflareTunnelUnknown{resource: newTunnel(""), ObservedPhase: "x"}
			Expect(s.IsRetryable()).To(BeTrue())
		})
	})

	Describe("Unknown.IsMaxRetriesExceeded", func() {
		It("always returns false", func() {
			s := CloudflareTunnelUnknown{resource: newTunnel(""), ObservedPhase: "x"}
			Expect(s.IsMaxRetriesExceeded()).To(BeFalse())
		})
	})
})

var _ = Describe("Transitions — RetryBackoff", func() {
	Describe("Failed.RetryBackoff", func() {
		It("returns a positive duration for RetryCount=0 (base backoff: ~5s)", func() {
			s := CloudflareTunnelFailed{resource: newTunnel(""), LastState: "x", ErrorMessage: "y", RetryCount: 0}
			backoff := s.RetryBackoff()
			Expect(backoff).To(BeNumerically(">", 0))
			// base=5s * 2^0 = 5s, jitter ±0.5s
			Expect(backoff).To(BeNumerically(">=", 4500*time.Millisecond))
			Expect(backoff).To(BeNumerically("<=", 5500*time.Millisecond))
		})

		It("caps at 300s with jitter for high RetryCount", func() {
			s := CloudflareTunnelFailed{resource: newTunnel(""), LastState: "x", ErrorMessage: "y", RetryCount: 100}
			backoff := s.RetryBackoff()
			// cap=300s, jitter ±10% → [270s, 330s]
			Expect(backoff).To(BeNumerically(">=", 270*time.Second))
			Expect(backoff).To(BeNumerically("<=", 330*time.Second))
		})

		It("grows exponentially: RetryCount=1 ~10s, RetryCount=2 ~20s", func() {
			s1 := CloudflareTunnelFailed{resource: newTunnel(""), LastState: "x", ErrorMessage: "y", RetryCount: 1}
			s2 := CloudflareTunnelFailed{resource: newTunnel(""), LastState: "x", ErrorMessage: "y", RetryCount: 2}
			// 5*2^1=10s, 5*2^2=20s - backoff should roughly double
			b1 := s1.RetryBackoff()
			b2 := s2.RetryBackoff()
			Expect(b1).To(BeNumerically(">", 0))
			Expect(b2).To(BeNumerically(">", b1), "RetryCount=2 should have longer backoff than RetryCount=1")
		})
	})

	Describe("Unknown.RetryBackoff", func() {
		It("always returns exactly 5 seconds", func() {
			s := CloudflareTunnelUnknown{resource: newTunnel(""), ObservedPhase: "x"}
			for i := 0; i < 5; i++ {
				Expect(s.RetryBackoff()).To(Equal(5 * time.Second))
			}
		})
	})
})
