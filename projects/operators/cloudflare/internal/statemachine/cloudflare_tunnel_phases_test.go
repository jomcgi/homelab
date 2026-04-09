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

// Package statemachine — unit tests for cloudflare_tunnel_phases.go
//
// Covers phase constants, AllPhases(), and IsKnownPhase() via table-driven tests.
package statemachine

import (
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

var _ = Describe("Phase constants", func() {
	DescribeTable("each Phase* constant has the expected string value",
		func(got, want string) {
			Expect(got).To(Equal(want))
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

var _ = Describe("AllPhases function", func() {
	It("returns a non-empty slice", func() {
		Expect(AllPhases()).NotTo(BeEmpty())
	})

	It("returns exactly 9 phases", func() {
		Expect(AllPhases()).To(HaveLen(9))
	})

	It("contains all Phase* constants", func() {
		all := AllPhases()
		Expect(all).To(ContainElements(
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

	It("contains no duplicates", func() {
		seen := map[string]int{}
		for _, p := range AllPhases() {
			seen[p]++
		}
		for phase, count := range seen {
			Expect(count).To(Equal(1), "phase %q appears %d times", phase, count)
		}
	})

	It("does not include the empty string", func() {
		Expect(AllPhases()).NotTo(ContainElement(""))
	})
})

var _ = Describe("IsKnownPhase function", func() {
	DescribeTable("returns true for all known phases including empty string",
		func(phase string) {
			Expect(IsKnownPhase(phase)).To(BeTrue())
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

	DescribeTable("returns false for unrecognized or misspelled phases",
		func(phase string) {
			Expect(IsKnownPhase(phase)).To(BeFalse())
		},
		Entry("lowercase pending", "pending"),
		Entry("uppercase PENDING", "PENDING"),
		Entry("mixed case createTunnel", "createTunnel"),
		Entry("arbitrary string", "not-a-phase"),
		Entry("single space", " "),
		Entry("phase with suffix", "PendingNow"),
		Entry("phase with prefix", "AlreadyPending"),
		Entry("null literal", "null"),
	)

	It("returns true for all phases returned by AllPhases()", func() {
		for _, p := range AllPhases() {
			Expect(IsKnownPhase(p)).To(BeTrue(), "AllPhases() returned %q which IsKnownPhase does not recognise", p)
		}
	})
})
