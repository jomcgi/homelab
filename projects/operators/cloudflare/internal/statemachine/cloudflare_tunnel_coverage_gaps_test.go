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

// Package statemachine — targeted coverage gap tests
//
// Fills the following gaps not addressed by the existing test files:
//
//  1. AllPhases uniqueness — verifies the slice contains no duplicate entries.
//
//  2. Validate() error-ordering when multiple required fields are simultaneously
//     absent:
//     - CloudflareTunnelFailed: LastState is validated before ErrorMessage.
//     - CloudflareTunnelConfiguringIngress: TunnelIdentity before SecretInfo.
//     - CloudflareTunnelReady: TunnelIdentity before SecretInfo.
//
//  3. IsKnownPhase — additional boundary inputs not present in existing tables:
//     single-space string, "null" literal, quoted phase string, and typo variants.
package statemachine

import (
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

// =============================================================================
// AllPhases — no duplicate entries
// =============================================================================

var _ = Describe("AllPhases no duplicates", func() {
	It("contains no duplicate phase values", func() {
		seen := make(map[string]bool)
		for _, p := range AllPhases() {
			Expect(seen[p]).To(BeFalse(), "phase %q appears more than once in AllPhases()", p)
			seen[p] = true
		}
	})
})

// =============================================================================
// Validate() — error-ordering when multiple required fields are absent at once
// =============================================================================

var _ = Describe("Validate() error ordering with multiple absent fields", func() {
	Describe("CloudflareTunnelFailed — both LastState and ErrorMessage empty", func() {
		// The implementation checks LastState first; when both are absent, the
		// returned error must mention lastState, not errorMessage.
		It("returns a lastState error when both fields are missing", func() {
			s := CloudflareTunnelFailed{} // zero value: LastState="" and ErrorMessage=""
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("lastState"),
				"expected lastState to be reported first because it is validated first in Validate()")
		})
	})

	Describe("CloudflareTunnelConfiguringIngress — both TunnelID and SecretName empty", func() {
		// TunnelIdentity.Validate() is called before SecretInfo.Validate();
		// when both embedded structs are zero, the first error must identify tunnelID.
		It("returns a tunnelID error when both embedded fields are missing", func() {
			s := CloudflareTunnelConfiguringIngress{} // zero value: no TunnelID, no SecretName
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnelID"),
				"expected tunnelID to be reported first because TunnelIdentity is validated before SecretInfo")
		})
	})

	Describe("CloudflareTunnelReady — both TunnelID and SecretName empty", func() {
		// Same ordering contract as ConfiguringIngress.
		It("returns a tunnelID error when both embedded fields are missing", func() {
			s := CloudflareTunnelReady{} // zero value: no TunnelID, no SecretName
			err := s.Validate()
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnelID"),
				"expected tunnelID to be reported first because TunnelIdentity is validated before SecretInfo")
		})
	})
})

// =============================================================================
// IsKnownPhase — additional boundary inputs
// =============================================================================

var _ = Describe("IsKnownPhase additional boundary inputs", func() {
	DescribeTable("returns false for atypical invalid inputs",
		func(phase string) {
			Expect(IsKnownPhase(phase)).To(BeFalse(),
				"IsKnownPhase(%q) should return false", phase)
		},
		// A single space is non-empty but is not the empty-string initial state
		Entry("single space (non-empty, not a valid phase)", " "),
		// Structured strings that might appear in corrupted status data
		Entry("null literal", "null"),
		Entry("quoted Pending (JSON-encoded)", `"Pending"`),
		// Typo variants close to real phase names
		Entry("PendingX (suffix typo)", "PendingX"),
		Entry("Readyy (doubled letter)", "Readyy"),
		Entry("creating-tunnel (hyphenated)", "creating-tunnel"),
	)
})
