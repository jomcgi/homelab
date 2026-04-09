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

// Package statemachine — unit tests for cloudflare_tunnel_visit.go
//
// Covers the Visit() dispatch function and CloudflareTunnelFuncVisitor
// with various generic type parameters and handler combinations.
package statemachine

import (
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

// visitTestResource is a minimal resource for visit tests.
var visitTestResource = &v1.CloudflareTunnel{}

// allTestStates returns one instance of each concrete state type for table-driven tests.
func allTestStates() []CloudflareTunnelState {
	return []CloudflareTunnelState{
		CloudflareTunnelPending{resource: visitTestResource},
		CloudflareTunnelCreatingTunnel{resource: visitTestResource},
		CloudflareTunnelCreatingSecret{resource: visitTestResource},
		CloudflareTunnelConfiguringIngress{resource: visitTestResource},
		CloudflareTunnelReady{resource: visitTestResource},
		CloudflareTunnelFailed{resource: visitTestResource},
		CloudflareTunnelDeletingTunnel{resource: visitTestResource},
		CloudflareTunnelDeleted{resource: visitTestResource},
		CloudflareTunnelUnknown{resource: visitTestResource},
	}
}

var _ = Describe("Visit function dispatch", func() {
	It("routes each state to the correct visitor method", func() {
		visitor := &phaseRecordingVisitor{}
		states := allTestStates()
		for _, s := range states {
			Visit[string](s, visitor)
		}
		Expect(visitor.phases).To(ConsistOf(
			PhasePending,
			PhaseCreatingTunnel,
			PhaseCreatingSecret,
			PhaseConfiguringIngress,
			PhaseReady,
			PhaseFailed,
			PhaseDeletingTunnel,
			PhaseDeleted,
			PhaseUnknown,
		))
	})

	It("returns the value produced by the visitor method", func() {
		state := CloudflareTunnelPending{resource: visitTestResource}
		result := Visit[int](state, &CloudflareTunnelFuncVisitor[int]{
			OnPending: func(_ CloudflareTunnelPending) int { return 42 },
		})
		Expect(result).To(Equal(42))
	})

	It("works with bool generic parameter", func() {
		state := CloudflareTunnelReady{resource: visitTestResource}
		result := Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnReady: func(_ CloudflareTunnelReady) bool { return true },
		})
		Expect(result).To(BeTrue())
	})

	It("works with string generic parameter", func() {
		state := CloudflareTunnelFailed{
			resource: visitTestResource, LastState: "x", ErrorMessage: "y",
		}
		result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{
			OnFailed: func(s CloudflareTunnelFailed) string { return s.Phase() },
		})
		Expect(result).To(Equal(PhaseFailed))
	})
})

var _ = Describe("CloudflareTunnelFuncVisitor", func() {
	Describe("specific handler is called when set", func() {
		DescribeTable("each state dispatches to its OnXxx handler",
			func(state CloudflareTunnelState) {
				called := false
				visitor := &CloudflareTunnelFuncVisitor[bool]{
					OnPending:            func(_ CloudflareTunnelPending) bool { called = true; return true },
					OnCreatingTunnel:     func(_ CloudflareTunnelCreatingTunnel) bool { called = true; return true },
					OnCreatingSecret:     func(_ CloudflareTunnelCreatingSecret) bool { called = true; return true },
					OnConfiguringIngress: func(_ CloudflareTunnelConfiguringIngress) bool { called = true; return true },
					OnReady:              func(_ CloudflareTunnelReady) bool { called = true; return true },
					OnFailed:             func(_ CloudflareTunnelFailed) bool { called = true; return true },
					OnDeletingTunnel:     func(_ CloudflareTunnelDeletingTunnel) bool { called = true; return true },
					OnDeleted:            func(_ CloudflareTunnelDeleted) bool { called = true; return true },
					OnUnknown:            func(_ CloudflareTunnelUnknown) bool { called = true; return true },
				}
				result := Visit[bool](state, visitor)
				Expect(called).To(BeTrue(), "handler should have been called for %T", state)
				Expect(result).To(BeTrue())
			},
			Entry("Pending", CloudflareTunnelPending{resource: visitTestResource}),
			Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: visitTestResource}),
			Entry("CreatingSecret", CloudflareTunnelCreatingSecret{resource: visitTestResource}),
			Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{resource: visitTestResource}),
			Entry("Ready", CloudflareTunnelReady{resource: visitTestResource}),
			Entry("Failed", CloudflareTunnelFailed{resource: visitTestResource}),
			Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{resource: visitTestResource}),
			Entry("Deleted", CloudflareTunnelDeleted{resource: visitTestResource}),
			Entry("Unknown", CloudflareTunnelUnknown{resource: visitTestResource}),
		)
	})

	Describe("Default fallback", func() {
		It("Default is called when no specific handler is set for the state", func() {
			defaultCalled := false
			state := CloudflareTunnelCreatingTunnel{resource: visitTestResource}
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				OnPending: func(_ CloudflareTunnelPending) bool { return true },
				Default:   func(_ CloudflareTunnelState) bool { defaultCalled = true; return true },
			})
			Expect(defaultCalled).To(BeTrue())
		})

		It("specific handler takes precedence over Default", func() {
			defaultCalled := false
			specificCalled := false
			state := CloudflareTunnelPending{resource: visitTestResource}
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				OnPending: func(_ CloudflareTunnelPending) bool { specificCalled = true; return true },
				Default:   func(_ CloudflareTunnelState) bool { defaultCalled = true; return false },
			})
			Expect(specificCalled).To(BeTrue())
			Expect(defaultCalled).To(BeFalse())
		})

		It("Default receives the original state value (can call Phase())", func() {
			state := CloudflareTunnelReady{resource: visitTestResource}
			var receivedPhase string
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				Default: func(s CloudflareTunnelState) bool {
					receivedPhase = s.Phase()
					return true
				},
			})
			Expect(receivedPhase).To(Equal(PhaseReady))
		})
	})

	Describe("nil handlers return zero values", func() {
		DescribeTable("returns zero int when no handler is set",
			func(state CloudflareTunnelState) {
				result := Visit[int](state, &CloudflareTunnelFuncVisitor[int]{})
				Expect(result).To(Equal(0))
			},
			Entry("Pending", CloudflareTunnelPending{resource: visitTestResource}),
			Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: visitTestResource}),
			Entry("CreatingSecret", CloudflareTunnelCreatingSecret{resource: visitTestResource}),
			Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{resource: visitTestResource}),
			Entry("Ready", CloudflareTunnelReady{resource: visitTestResource}),
			Entry("Failed", CloudflareTunnelFailed{resource: visitTestResource}),
			Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{resource: visitTestResource}),
			Entry("Deleted", CloudflareTunnelDeleted{resource: visitTestResource}),
			Entry("Unknown", CloudflareTunnelUnknown{resource: visitTestResource}),
		)

		DescribeTable("returns empty string when no handler is set",
			func(state CloudflareTunnelState) {
				result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{})
				Expect(result).To(Equal(""))
			},
			Entry("Pending", CloudflareTunnelPending{resource: visitTestResource}),
			Entry("Deleted", CloudflareTunnelDeleted{resource: visitTestResource}),
			Entry("Unknown", CloudflareTunnelUnknown{resource: visitTestResource}),
		)

		DescribeTable("returns false when no handler is set",
			func(state CloudflareTunnelState) {
				result := Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{})
				Expect(result).To(BeFalse())
			},
			Entry("Pending", CloudflareTunnelPending{resource: visitTestResource}),
			Entry("Ready", CloudflareTunnelReady{resource: visitTestResource}),
			Entry("Failed", CloudflareTunnelFailed{resource: visitTestResource}),
		)
	})
})

// phaseRecordingVisitor is a concrete CloudflareTunnelVisitor[string] implementation
// that records the Phase() of each state it visits.
type phaseRecordingVisitor struct {
	phases []string
}

func (v *phaseRecordingVisitor) VisitPending(s CloudflareTunnelPending) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}

func (v *phaseRecordingVisitor) VisitCreatingTunnel(s CloudflareTunnelCreatingTunnel) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}

func (v *phaseRecordingVisitor) VisitCreatingSecret(s CloudflareTunnelCreatingSecret) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}

func (v *phaseRecordingVisitor) VisitConfiguringIngress(s CloudflareTunnelConfiguringIngress) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}

func (v *phaseRecordingVisitor) VisitReady(s CloudflareTunnelReady) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}

func (v *phaseRecordingVisitor) VisitFailed(s CloudflareTunnelFailed) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}

func (v *phaseRecordingVisitor) VisitDeletingTunnel(s CloudflareTunnelDeletingTunnel) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}

func (v *phaseRecordingVisitor) VisitDeleted(s CloudflareTunnelDeleted) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}

func (v *phaseRecordingVisitor) VisitUnknown(s CloudflareTunnelUnknown) string {
	v.phases = append(v.phases, s.Phase())
	return s.Phase()
}
