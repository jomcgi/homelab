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

// Package statemachine — unit tests for cloudflare_tunnel_calculator.go
//
// Covers Calculator.Calculate() for all phases, deletion path, and unknown
// phase fallback behavior via table-driven tests.
package statemachine

import (
	"github.com/go-logr/logr"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

var _ = Describe("CloudflareTunnelCalculator", func() {
	var calc *CloudflareTunnelCalculator

	BeforeEach(func() {
		calc = NewCloudflareTunnelCalculator(logr.Discard())
	})

	Describe("NewCloudflareTunnelCalculator", func() {
		It("returns a non-nil calculator", func() {
			Expect(calc).NotTo(BeNil())
		})

		It("stores the provided logger", func() {
			Expect(func() {
				calc.Log.Info("test")
			}).NotTo(Panic())
		})
	})

	Describe("Calculate — normal state reconstruction", func() {
		DescribeTable("reconstructs the correct state type for each known phase",
			func(phase string, expectedType interface{}) {
				var r *v1.CloudflareTunnel
				switch phase {
				case PhaseCreatingSecret:
					r = newTunnelWithStatus(v1.CloudflareTunnelStatus{
						Phase:    phase,
						TunnelID: "tid",
					})
				case PhaseConfiguringIngress:
					r = newTunnelWithStatus(v1.CloudflareTunnelStatus{
						Phase:      phase,
						TunnelID:   "tid",
						SecretName: "sn",
					})
				case PhaseReady:
					r = newTunnelWithStatus(v1.CloudflareTunnelStatus{
						Phase:      phase,
						TunnelID:   "tid",
						SecretName: "sn",
					})
				case PhaseFailed:
					r = newTunnelWithStatus(v1.CloudflareTunnelStatus{
						Phase:        phase,
						LastState:    "CreatingTunnel",
						ErrorMessage: "err",
					})
				case PhaseUnknown:
					r = newTunnelWithStatus(v1.CloudflareTunnelStatus{
						Phase:         phase,
						ObservedPhase: "SomeBrokenPhase",
					})
				default:
					r = newTunnel(phase)
				}
				state := calc.Calculate(r)
				Expect(state).To(BeAssignableToTypeOf(expectedType))
			},
			Entry("empty phase → Pending", "", CloudflareTunnelPending{}),
			Entry("Pending", PhasePending, CloudflareTunnelPending{}),
			Entry("CreatingTunnel", PhaseCreatingTunnel, CloudflareTunnelCreatingTunnel{}),
			Entry("CreatingSecret (valid)", PhaseCreatingSecret, CloudflareTunnelCreatingSecret{}),
			Entry("ConfiguringIngress (valid)", PhaseConfiguringIngress, CloudflareTunnelConfiguringIngress{}),
			Entry("Ready (valid)", PhaseReady, CloudflareTunnelReady{}),
			Entry("Failed (valid)", PhaseFailed, CloudflareTunnelFailed{}),
			Entry("Unknown (valid)", PhaseUnknown, CloudflareTunnelUnknown{}),
		)

		It("falls back to Unknown when CreatingSecret has empty TunnelID", func() {
			r := newTunnel(PhaseCreatingSecret) // TunnelID not set
			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "invalid CreatingSecret should produce Unknown, got %T", state)
		})

		It("falls back to Unknown when ConfiguringIngress is missing TunnelID", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseConfiguringIngress,
				SecretName: "sn",
				// TunnelID missing
			})
			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "ConfiguringIngress without TunnelID should produce Unknown, got %T", state)
		})

		It("falls back to Unknown when ConfiguringIngress is missing SecretName", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseConfiguringIngress,
				TunnelID: "tid",
				// SecretName missing
			})
			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "ConfiguringIngress without SecretName should produce Unknown, got %T", state)
		})

		It("falls back to Unknown when Ready is missing TunnelID", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseReady,
				SecretName: "sn",
				// TunnelID missing
			})
			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "Ready without TunnelID should produce Unknown, got %T", state)
		})

		It("falls back to Unknown when Failed is missing LastState", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:        PhaseFailed,
				ErrorMessage: "err",
				// LastState missing
			})
			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "Failed without LastState should produce Unknown, got %T", state)
		})

		It("falls back to Unknown when Failed is missing ErrorMessage", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:     PhaseFailed,
				LastState: "CreatingTunnel",
				// ErrorMessage missing
			})
			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "Failed without ErrorMessage should produce Unknown, got %T", state)
		})

		It("falls back to Unknown for a completely unrecognized phase", func() {
			r := newTunnel("NotARealPhase")
			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "unrecognized phase should produce Unknown, got %T", state)
		})

		It("returns Unknown with ObservedPhase set to the unrecognized phase string", func() {
			r := newTunnel("GarbagePhase")
			state := calc.Calculate(r)
			u, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue())
			Expect(u.ObservedPhase).To(Equal("GarbagePhase"))
		})
	})

	Describe("Calculate — deletion path", func() {
		It("returns DeletingTunnel when phase is DeletingTunnel with deletion timestamp", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseDeletingTunnel,
				TunnelID: "dt-tid",
			})
			ts := metav1.Now()
			r.DeletionTimestamp = &ts

			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelDeletingTunnel)
			Expect(ok).To(BeTrue(), "expected DeletingTunnel, got %T", state)
		})

		It("returns Deleted when phase is Deleted with deletion timestamp", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{Phase: PhaseDeleted})
			ts := metav1.Now()
			r.DeletionTimestamp = &ts

			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected Deleted, got %T", state)
		})

		It("transitions directly to Deleted when TunnelID is absent (no DeletingTunnel validation)", func() {
			// No TunnelID means DeletingTunnel.Validate() would fail → skip to Deleted
			r := newTunnel(PhasePending)
			ts := metav1.Now()
			r.DeletionTimestamp = &ts

			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "no TunnelID should go directly to Deleted, got %T", state)
		})

		It("returns Deleted when deletion timestamp is set and phase is not a deletion phase (calculateDeletionState validation fails without TunnelID populated)", func() {
			// calculateDeletionState creates a fresh CloudflareTunnelDeletingTunnel{resource: r}
			// without populating TunnelIdentity from status — so Validate() fails → Deleted.
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseReady,
				TunnelID: "ready-tid",
			})
			ts := metav1.Now()
			r.DeletionTimestamp = &ts

			state := calc.Calculate(r)
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected Deleted (DeletingTunnel validation fails without TunnelID in state), got %T", state)
		})
	})

	Describe("Calculate — resource pointer preservation", func() {
		It("the state returned by Calculate always has the same resource pointer", func() {
			r := newTunnel(PhasePending)
			state := calc.Calculate(r)
			Expect(state.Resource()).To(BeIdenticalTo(r))
		})
	})
})
