// Tests targeting specific functions in calculator, phases, status, transitions,
// types, and visit that complement the existing test suites.
//
// Specifically covers:
//   - SSAPatch Apply patch type verification
//   - HasSpecChanged edge cases (observedGeneration > generation)
//   - RetryBackoff goroutine safety (exercises jitterMu)
//   - AllPhases uniqueness and completeness
//   - Phase constant string values
//   - FuncVisitor individual state dispatch with nil handlers
//   - UpdateObservedGeneration preserves metadata identity

package statemachine

import (
	"sync"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

// =============================================================================
// Phase constant string values
// =============================================================================

var _ = Describe("Phase constant string values", func() {
	DescribeTable("each constant matches its expected string literal",
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

// =============================================================================
// AllPhases — uniqueness and completeness
// =============================================================================

var _ = Describe("AllPhases uniqueness and completeness", func() {
	It("contains no duplicate entries", func() {
		phases := AllPhases()
		seen := make(map[string]bool)
		for _, p := range phases {
			Expect(seen).NotTo(HaveKey(p), "duplicate phase %q", p)
			seen[p] = true
		}
	})

	It("contains exactly 9 phases", func() {
		Expect(AllPhases()).To(HaveLen(9))
	})

	It("every AllPhases entry is recognised by IsKnownPhase", func() {
		for _, p := range AllPhases() {
			Expect(IsKnownPhase(p)).To(BeTrue(), "AllPhases() returned unrecognised phase %q", p)
		}
	})
})

// =============================================================================
// HasSpecChanged — additional edge cases
// =============================================================================

var _ = Describe("HasSpecChanged extra edge cases", func() {
	It("returns false when both generation and observedGeneration are zero", func() {
		r := &v1.CloudflareTunnel{}
		r.Generation = 0
		r.Status.ObservedGeneration = 0
		Expect(HasSpecChanged(r)).To(BeFalse())
	})

	It("returns true when observedGeneration exceeds generation (rollback scenario)", func() {
		r := &v1.CloudflareTunnel{}
		r.Generation = 1
		r.Status.ObservedGeneration = 2
		// Generation != ObservedGeneration → spec considered changed
		Expect(HasSpecChanged(r)).To(BeTrue())
	})

	It("returns true when generation is 1 and observedGeneration is 0 (initial reconcile)", func() {
		r := &v1.CloudflareTunnel{}
		r.Generation = 1
		r.Status.ObservedGeneration = 0
		Expect(HasSpecChanged(r)).To(BeTrue())
	})
})

// =============================================================================
// UpdateObservedGeneration — metadata identity preservation
// =============================================================================

var _ = Describe("UpdateObservedGeneration metadata preservation", func() {
	It("preserves the resource Name and Namespace in the copy", func() {
		r := newTunnel(PhasePending)
		r.Name = "my-tunnel"
		r.Namespace = "production"
		r.Generation = 7

		updated := UpdateObservedGeneration(r)

		Expect(updated.Name).To(Equal("my-tunnel"))
		Expect(updated.Namespace).To(Equal("production"))
		Expect(updated.Status.ObservedGeneration).To(Equal(int64(7)))
	})

	It("does not mutate the original resource's ObservedGeneration", func() {
		r := newTunnel(PhasePending)
		r.Generation = 5
		r.Status.ObservedGeneration = 3

		_ = UpdateObservedGeneration(r)

		Expect(r.Status.ObservedGeneration).To(Equal(int64(3)), "original must be unchanged")
	})
})

// =============================================================================
// SSAPatch — Apply patch type
// =============================================================================

var _ = Describe("SSAPatch patch type", func() {
	It("uses the Apply patch type (SSA)", func() {
		r := newTunnel(PhasePending)
		s := CloudflareTunnelPending{resource: r}

		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		// Server-Side Apply patches carry the "application/apply-patch+yaml" patch type
		Expect(string(patch.Type())).To(Equal("application/apply-patch+yaml"))
	})

	It("does not include ManagedFields in the patch JSON", func() {
		r := newTunnel(PhasePending)
		r.ManagedFields = []metav1.ManagedFieldsEntry{
			{Manager: "old-controller", Operation: "Apply"},
		}
		s := CloudflareTunnelPending{resource: r}

		patch, err := SSAPatch(s)
		Expect(err).NotTo(HaveOccurred())

		// extractPatchData is defined in cloudflare_tunnel_comprehensive_test.go
		data := extractPatchData(patch)
		Expect(string(data)).NotTo(ContainSubstring("managedFields"))
	})
})

// =============================================================================
// RetryBackoff — concurrent goroutine safety
// =============================================================================

var _ = Describe("RetryBackoff goroutine safety", func() {
	It("does not race when called from many goroutines simultaneously", func() {
		const goroutines = 20

		failed := CloudflareTunnelFailed{
			resource:     newTunnel(PhaseFailed),
			LastState:    PhasePending,
			ErrorMessage: "concurrent test",
			RetryCount:   3,
		}

		var wg sync.WaitGroup
		results := make([]time.Duration, goroutines)

		for i := 0; i < goroutines; i++ {
			i := i
			wg.Add(1)
			go func() {
				defer wg.Done()
				results[i] = failed.RetryBackoff()
			}()
		}
		wg.Wait()

		for _, d := range results {
			Expect(d).To(BeNumerically(">", 0), "RetryBackoff must be positive")
		}
	})

	It("returns the same fixed 5s backoff for Unknown from concurrent callers", func() {
		const goroutines = 10
		unknown := CloudflareTunnelUnknown{resource: newTunnel(PhaseUnknown), ObservedPhase: "x"}

		var wg sync.WaitGroup
		results := make([]time.Duration, goroutines)

		for i := 0; i < goroutines; i++ {
			i := i
			wg.Add(1)
			go func() {
				defer wg.Done()
				results[i] = unknown.RetryBackoff()
			}()
		}
		wg.Wait()

		for _, d := range results {
			Expect(d).To(Equal(5 * time.Second))
		}
	})
})

// =============================================================================
// FuncVisitor — individual nil-handler behaviour per state type
// =============================================================================

var _ = Describe("FuncVisitor nil handler per state type returns zero", func() {
	// Each test verifies that when the specific handler is absent (nil) and no
	// Default is set, Visit returns the zero value for T.

	var r *v1.CloudflareTunnel

	BeforeEach(func() {
		r = newTunnel("")
	})

	It("returns zero for CreatingSecret with no handler", func() {
		s := CloudflareTunnelCreatingSecret{resource: r, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}}
		result := Visit[int](s, &CloudflareTunnelFuncVisitor[int]{})
		Expect(result).To(Equal(0))
	})

	It("returns zero for ConfiguringIngress with no handler", func() {
		s := CloudflareTunnelConfiguringIngress{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
			SecretInfo:     SecretInfo{SecretName: "s1"},
		}
		result := Visit[int](s, &CloudflareTunnelFuncVisitor[int]{})
		Expect(result).To(Equal(0))
	})

	It("returns zero for Ready with no handler", func() {
		s := CloudflareTunnelReady{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
			SecretInfo:     SecretInfo{SecretName: "s1"},
		}
		result := Visit[string](s, &CloudflareTunnelFuncVisitor[string]{})
		Expect(result).To(Equal(""))
	})

	It("returns zero for DeletingTunnel with no handler", func() {
		s := CloudflareTunnelDeletingTunnel{resource: r, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}}
		result := Visit[bool](s, &CloudflareTunnelFuncVisitor[bool]{})
		Expect(result).To(BeFalse())
	})

	It("returns zero for Deleted with no handler", func() {
		s := CloudflareTunnelDeleted{resource: r}
		result := Visit[string](s, &CloudflareTunnelFuncVisitor[string]{})
		Expect(result).To(Equal(""))
	})

	It("calls Default for every state type when specific handler is nil", func() {
		states := []CloudflareTunnelState{
			CloudflareTunnelPending{resource: r},
			CloudflareTunnelCreatingTunnel{resource: r},
			CloudflareTunnelCreatingSecret{resource: r, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}},
			CloudflareTunnelConfiguringIngress{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
				SecretInfo:     SecretInfo{SecretName: "s1"},
			},
			CloudflareTunnelReady{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "t1"},
				SecretInfo:     SecretInfo{SecretName: "s1"},
			},
			CloudflareTunnelFailed{resource: r, LastState: PhasePending, ErrorMessage: "e"},
			CloudflareTunnelDeletingTunnel{resource: r, TunnelIdentity: TunnelIdentity{TunnelID: "t1"}},
			CloudflareTunnelDeleted{resource: r},
			CloudflareTunnelUnknown{resource: r, ObservedPhase: "old"},
		}
		for _, state := range states {
			var defaultCalled bool
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				Default: func(_ CloudflareTunnelState) bool {
					defaultCalled = true
					return true
				},
			})
			Expect(defaultCalled).To(BeTrue(), "Default not called for %T", state)
		}
	})
})
