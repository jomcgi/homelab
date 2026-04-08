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

package statemachine

import (
	"sync"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

// cloudflare_tunnel_coverage_test.go adds targeted coverage for:
//   - RetryBackoff cap boundary (first cap at RetryCount=6)
//   - Concurrent RetryBackoff calls (mutex safety)
//   - FuncVisitor nil handlers returning zero value (no Default)
//   - FuncVisitor nil handlers falling through to Default
//   - StartDeletion from Pending and CreatingTunnel (no TunnelID propagation)
//   - DeletingTunnel.DeletionComplete field forwarding
//   - TunnelIdentity and SecretInfo Validate error messages verbatim
//   - CloudflareTunnelFailed.IsRetryable always returns true
//   - IngressConfigured with Active=false vs Active=true
//   - ReconfigureIngress preserves both TunnelIdentity and SecretInfo
//   - Full sequential lifecycle sanity check

var _ = Describe("RetryBackoff cap boundary", func() {
	var resource = newTunnel("")

	// base=5s, multiplier=2.0, max=300s
	// cap first reached at RetryCount=6: 5 * 2^6 = 320s > 300s
	It("caps at RetryCount=6 (first cap point)", func() {
		failed := CloudflareTunnelFailed{
			resource:     resource,
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   6,
		}
		// With ±10% jitter on 300s: range [270s, 330s]
		backoff := failed.RetryBackoff()
		Expect(backoff).To(BeNumerically(">=", 270*time.Second),
			"RetryCount=6 backoff should be >= 270s (cap with negative jitter)")
		Expect(backoff).To(BeNumerically("<=", 330*time.Second),
			"RetryCount=6 backoff should be <= 330s (cap with positive jitter)")
	})

	It("RetryCount=5 is below cap (5 * 2^5 = 160s)", func() {
		failed := CloudflareTunnelFailed{
			resource:     resource,
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   5,
		}
		// 160s ± 10% → [144s, 176s]
		backoff := failed.RetryBackoff()
		Expect(backoff).To(BeNumerically(">=", 144*time.Second))
		Expect(backoff).To(BeNumerically("<=", 176*time.Second))
	})

	It("RetryCount=100 stays within jitter of cap", func() {
		failed := CloudflareTunnelFailed{
			resource:     resource,
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   100,
		}
		backoff := failed.RetryBackoff()
		Expect(backoff).To(BeNumerically(">=", 270*time.Second))
		Expect(backoff).To(BeNumerically("<=", 330*time.Second))
	})
})

var _ = Describe("RetryBackoff concurrent mutex safety", func() {
	It("does not race or panic under 50 concurrent goroutines", func() {
		resource := newTunnel("")
		failed := CloudflareTunnelFailed{
			resource:     resource,
			LastState:    "x",
			ErrorMessage: "y",
			RetryCount:   3,
		}

		var wg sync.WaitGroup
		const n = 50
		results := make([]time.Duration, n)

		wg.Add(n)
		for i := 0; i < n; i++ {
			i := i
			go func() {
				defer wg.Done()
				defer GinkgoRecover()
				results[i] = failed.RetryBackoff()
			}()
		}
		wg.Wait()

		// All results must be positive (cap region: 5 * 2^3 = 40s ± 4s)
		for i, d := range results {
			Expect(d).To(BeNumerically(">", 0), "goroutine %d: backoff must be positive", i)
			Expect(d).To(BeNumerically(">=", 36*time.Second), "goroutine %d: backoff at count=3", i)
			Expect(d).To(BeNumerically("<=", 44*time.Second), "goroutine %d: backoff at count=3", i)
		}
	})
})

var _ = Describe("FuncVisitor nil handler zero-value return", func() {
	var resource = newTunnel("")

	// When a specific handler is nil AND Default is nil, the zero value for T is returned.
	DescribeTable("nil handler with no Default returns zero value",
		func(state CloudflareTunnelState) {
			result := Visit[int](state, &CloudflareTunnelFuncVisitor[int]{
				// All handlers nil, no Default
			})
			Expect(result).To(Equal(0))
		},
		Entry("Pending", CloudflareTunnelPending{resource: resource}),
		Entry("CreatingTunnel", CloudflareTunnelCreatingTunnel{resource: resource}),
		Entry("CreatingSecret", CloudflareTunnelCreatingSecret{resource: resource}),
		Entry("ConfiguringIngress", CloudflareTunnelConfiguringIngress{resource: resource}),
		Entry("Ready", CloudflareTunnelReady{resource: resource}),
		Entry("Failed", CloudflareTunnelFailed{resource: resource}),
		Entry("DeletingTunnel", CloudflareTunnelDeletingTunnel{resource: resource}),
		Entry("Deleted", CloudflareTunnelDeleted{resource: resource}),
		Entry("Unknown", CloudflareTunnelUnknown{resource: resource}),
	)

	It("nil handler string type returns empty string", func() {
		state := CloudflareTunnelPending{resource: resource}
		result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{})
		Expect(result).To(Equal(""))
	})

	It("nil handler bool type returns false", func() {
		state := CloudflareTunnelReady{resource: resource}
		result := Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{})
		Expect(result).To(BeFalse())
	})
})

var _ = Describe("FuncVisitor handler precedence over Default", func() {
	var resource = newTunnel("")

	It("specific handler takes precedence over Default", func() {
		state := CloudflareTunnelPending{resource: resource}
		result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{
			OnPending: func(_ CloudflareTunnelPending) string { return "specific" },
			Default:   func(_ CloudflareTunnelState) string { return "default" },
		})
		Expect(result).To(Equal("specific"))
	})

	It("Default is used when specific handler is nil", func() {
		state := CloudflareTunnelCreatingTunnel{resource: resource}
		result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{
			OnPending: func(_ CloudflareTunnelPending) string { return "pending" },
			Default:   func(_ CloudflareTunnelState) string { return "default-fallback" },
		})
		Expect(result).To(Equal("default-fallback"))
	})

	It("Default receives the full state (can call Phase())", func() {
		state := CloudflareTunnelFailed{
			resource:     resource,
			LastState:    "x",
			ErrorMessage: "y",
		}
		result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{
			Default: func(s CloudflareTunnelState) string { return s.Phase() },
		})
		Expect(result).To(Equal(PhaseFailed))
	})
})

var _ = Describe("StartDeletion field propagation", func() {
	var resource = newTunnel("")

	It("Pending.StartDeletion does not propagate a TunnelID (Pending has none)", func() {
		pending := CloudflareTunnelPending{resource: resource}
		dt := pending.StartDeletion()
		Expect(dt.TunnelIdentity.TunnelID).To(BeEmpty())
		Expect(dt.Phase()).To(Equal(PhaseDeletingTunnel))
		Expect(dt.Resource()).To(BeIdenticalTo(resource))
	})

	It("CreatingTunnel.StartDeletion does not propagate a TunnelID (not created yet)", func() {
		ct := CloudflareTunnelCreatingTunnel{resource: resource}
		dt := ct.StartDeletion()
		Expect(dt.TunnelIdentity.TunnelID).To(BeEmpty())
		Expect(dt.Phase()).To(Equal(PhaseDeletingTunnel))
		Expect(dt.Resource()).To(BeIdenticalTo(resource))
	})
})

var _ = Describe("DeletingTunnel.DeletionComplete", func() {
	var resource = newTunnel("")

	It("DeletionComplete transitions to Deleted and preserves resource pointer", func() {
		dt := CloudflareTunnelDeletingTunnel{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid-xyz"},
		}
		deleted := dt.DeletionComplete()
		Expect(deleted.Phase()).To(Equal(PhaseDeleted))
		Expect(deleted.Resource()).To(BeIdenticalTo(resource))
		Expect(deleted.Validate()).To(Succeed())
	})

	It("DeletionComplete works even with empty TunnelID", func() {
		dt := CloudflareTunnelDeletingTunnel{resource: resource}
		deleted := dt.DeletionComplete()
		Expect(deleted.Phase()).To(Equal(PhaseDeleted))
	})
})

var _ = Describe("TunnelIdentity Validate error message", func() {
	It("returns the exact error message for empty TunnelID", func() {
		id := TunnelIdentity{}
		err := id.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("tunnelID is required"))
	})

	It("succeeds when TunnelID is non-empty", func() {
		id := TunnelIdentity{TunnelID: "any-value"}
		Expect(id.Validate()).To(Succeed())
	})
})

var _ = Describe("SecretInfo Validate error message", func() {
	It("returns the exact error message for empty SecretName", func() {
		info := SecretInfo{}
		err := info.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("secretName is required"))
	})

	It("succeeds when SecretName is non-empty", func() {
		info := SecretInfo{SecretName: "my-secret"}
		Expect(info.Validate()).To(Succeed())
	})
})

var _ = Describe("CloudflareTunnelFailed Validate error message ordering", func() {
	var resource = newTunnel("")

	It("returns lastState error when both LastState and ErrorMessage are empty", func() {
		failed := CloudflareTunnelFailed{resource: resource}
		err := failed.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("lastState is required for lastState state"))
	})

	It("returns errorMessage error when only ErrorMessage is missing", func() {
		failed := CloudflareTunnelFailed{
			resource:  resource,
			LastState: "CreatingTunnel",
		}
		err := failed.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("errorMessage is required for errorMessage state"))
	})

	It("succeeds when both LastState and ErrorMessage are present", func() {
		failed := CloudflareTunnelFailed{
			resource:     resource,
			LastState:    "CreatingTunnel",
			ErrorMessage: "timeout",
		}
		Expect(failed.Validate()).To(Succeed())
	})
})

var _ = Describe("CloudflareTunnelUnknown Validate error message", func() {
	var resource = newTunnel("")

	It("returns exact error message when ObservedPhase is empty", func() {
		unknown := CloudflareTunnelUnknown{resource: resource}
		err := unknown.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("observedPhase is required for observedPhase state"))
	})

	It("succeeds when ObservedPhase is non-empty", func() {
		unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "any-phase"}
		Expect(unknown.Validate()).To(Succeed())
	})
})

var _ = Describe("CloudflareTunnelFailed.IsRetryable always true", func() {
	var resource = newTunnel("")

	DescribeTable("IsRetryable returns true regardless of RetryCount",
		func(count int) {
			failed := CloudflareTunnelFailed{
				resource:     resource,
				LastState:    "x",
				ErrorMessage: "y",
				RetryCount:   count,
			}
			Expect(failed.IsRetryable()).To(BeTrue())
		},
		Entry("count=0", 0),
		Entry("count=9", 9),
		Entry("count=10", 10),
		Entry("count=1000", 1000),
	)
})

var _ = Describe("IngressConfigured Active field propagation", func() {
	var resource = newTunnel("")

	It("IngressConfigured with Active=false produces Ready with Active=false", func() {
		ci := CloudflareTunnelConfiguringIngress{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid-1"},
			SecretInfo:     SecretInfo{SecretName: "sec-1"},
		}
		ready := ci.IngressConfigured(false)
		Expect(ready.Active).To(BeFalse())
		Expect(ready.TunnelIdentity.TunnelID).To(Equal("tid-1"))
		Expect(ready.SecretInfo.SecretName).To(Equal("sec-1"))
		Expect(ready.Phase()).To(Equal(PhaseReady))
	})

	It("IngressConfigured with Active=true produces Ready with Active=true", func() {
		ci := CloudflareTunnelConfiguringIngress{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid-2"},
			SecretInfo:     SecretInfo{SecretName: "sec-2"},
		}
		ready := ci.IngressConfigured(true)
		Expect(ready.Active).To(BeTrue())
	})
})

var _ = Describe("ReconfigureIngress preserves both TunnelIdentity and SecretInfo", func() {
	var resource = newTunnel("")

	It("ReconfigureIngress carries TunnelID and SecretName forward", func() {
		ready := CloudflareTunnelReady{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "reconfig-tid"},
			SecretInfo:     SecretInfo{SecretName: "reconfig-secret"},
			Active:         true,
		}
		ci := ready.ReconfigureIngress()
		Expect(ci.Phase()).To(Equal(PhaseConfiguringIngress))
		Expect(ci.TunnelIdentity.TunnelID).To(Equal("reconfig-tid"))
		Expect(ci.SecretInfo.SecretName).To(Equal("reconfig-secret"))
		Expect(ci.Resource()).To(BeIdenticalTo(resource))
	})
})

var _ = Describe("CloudflareTunnelConfiguringIngress Validate error ordering", func() {
	var resource = newTunnel("")

	It("returns TunnelID error first when both TunnelID and SecretName are missing", func() {
		ci := CloudflareTunnelConfiguringIngress{resource: resource}
		err := ci.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("tunnelID is required"))
	})

	It("returns SecretName error when only SecretName is missing", func() {
		ci := CloudflareTunnelConfiguringIngress{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
		}
		err := ci.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("secretName is required"))
	})

	It("succeeds when both TunnelID and SecretName are set", func() {
		ci := CloudflareTunnelConfiguringIngress{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
			SecretInfo:     SecretInfo{SecretName: "sec"},
		}
		Expect(ci.Validate()).To(Succeed())
	})
})

var _ = Describe("CloudflareTunnelReady Validate error ordering", func() {
	var resource = newTunnel("")

	It("returns TunnelID error first when both fields missing", func() {
		ready := CloudflareTunnelReady{resource: resource}
		err := ready.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("tunnelID is required"))
	})

	It("returns SecretName error when only SecretName is missing", func() {
		ready := CloudflareTunnelReady{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
		}
		err := ready.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("secretName is required"))
	})
})

var _ = Describe("CloudflareTunnelDeletingTunnel Validate", func() {
	var resource = newTunnel("")

	It("fails validation when TunnelID is empty", func() {
		dt := CloudflareTunnelDeletingTunnel{resource: resource}
		err := dt.Validate()
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(Equal("tunnelID is required"))
	})

	It("succeeds when TunnelID is set", func() {
		dt := CloudflareTunnelDeletingTunnel{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "valid-tid"},
		}
		Expect(dt.Validate()).To(Succeed())
	})
})

var _ = Describe("Full sequential lifecycle", func() {
	It("traverses Pending -> Ready -> DeletingTunnel -> Deleted", func() {
		r := newTunnel("")

		// Pending
		pending := CloudflareTunnelPending{resource: r}
		Expect(pending.Phase()).To(Equal(PhasePending))
		Expect(pending.Validate()).To(Succeed())

		// CreatingTunnel
		creating := pending.StartCreation()
		Expect(creating.Phase()).To(Equal(PhaseCreatingTunnel))

		// CreatingSecret
		cs := creating.TunnelCreated("lifecycle-tid")
		Expect(cs.Phase()).To(Equal(PhaseCreatingSecret))
		Expect(cs.TunnelIdentity.TunnelID).To(Equal("lifecycle-tid"))
		Expect(cs.Validate()).To(Succeed())

		// ConfiguringIngress
		ci := cs.SecretCreated("lifecycle-secret")
		Expect(ci.Phase()).To(Equal(PhaseConfiguringIngress))
		Expect(ci.TunnelIdentity.TunnelID).To(Equal("lifecycle-tid"))
		Expect(ci.SecretInfo.SecretName).To(Equal("lifecycle-secret"))
		Expect(ci.Validate()).To(Succeed())

		// Ready
		ready := ci.IngressConfigured(true)
		Expect(ready.Phase()).To(Equal(PhaseReady))
		Expect(ready.Active).To(BeTrue())
		Expect(ready.Validate()).To(Succeed())

		// DeletingTunnel (from Ready carries TunnelID)
		deleting := ready.StartDeletion()
		Expect(deleting.Phase()).To(Equal(PhaseDeletingTunnel))
		Expect(deleting.TunnelIdentity.TunnelID).To(Equal("lifecycle-tid"))

		// Deleted
		deleted := deleting.DeletionComplete()
		Expect(deleted.Phase()).To(Equal(PhaseDeleted))
		Expect(deleted.Validate()).To(Succeed())
		Expect(deleted.RequeueAfter()).To(Equal(time.Duration(0)))
	})

	It("traverses failed path with max retries, then deletion", func() {
		r := newTunnel("")
		creating := CloudflareTunnelCreatingTunnel{resource: r}

		// Fail repeatedly to hit max
		failed := creating.MarkFailed("CreatingTunnel", "persistent failure", 9)
		Expect(failed.IsMaxRetriesExceeded()).To(BeFalse())

		// One more retry increments
		failed2 := creating.MarkFailed("CreatingTunnel", "persistent failure", 10)
		Expect(failed2.IsMaxRetriesExceeded()).To(BeTrue())
		Expect(failed2.Retry()).To(BeNil())

		// Can still delete
		deleting := failed2.StartDeletion()
		Expect(deleting.Phase()).To(Equal(PhaseDeletingTunnel))
	})
})
