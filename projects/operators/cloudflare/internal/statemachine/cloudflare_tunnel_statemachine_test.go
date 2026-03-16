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
	"testing"
	"time"

	"github.com/go-logr/logr"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	v1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func TestStatemachine(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Statemachine Suite")
}

// newTunnel creates a minimal CloudflareTunnel for testing.
func newTunnel(phase string) *v1.CloudflareTunnel {
	return &v1.CloudflareTunnel{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-tunnel",
			Namespace: "default",
		},
		Status: v1.CloudflareTunnelStatus{
			Phase: phase,
		},
	}
}

// newTunnelWithStatus creates a CloudflareTunnel with detailed status fields.
func newTunnelWithStatus(status v1.CloudflareTunnelStatus) *v1.CloudflareTunnel {
	t := newTunnel(status.Phase)
	t.Status = status
	return t
}

// =============================================================================
// Phases
// =============================================================================

var _ = Describe("Phases", func() {
	Describe("AllPhases", func() {
		It("should return all 9 known phases", func() {
			phases := AllPhases()
			Expect(phases).To(HaveLen(9))
			Expect(phases).To(ContainElements(
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
	})

	Describe("IsKnownPhase", func() {
		It("should return true for all known phases", func() {
			for _, phase := range AllPhases() {
				Expect(IsKnownPhase(phase)).To(BeTrue(), "phase %q should be known", phase)
			}
		})

		It("should return true for empty string (initial state)", func() {
			Expect(IsKnownPhase("")).To(BeTrue())
		})

		It("should return false for unknown phase strings", func() {
			Expect(IsKnownPhase("InvalidPhase")).To(BeFalse())
			Expect(IsKnownPhase("pending")).To(BeFalse()) // case-sensitive
			Expect(IsKnownPhase("READY")).To(BeFalse())
			Expect(IsKnownPhase("SomeCorruptedValue")).To(BeFalse())
		})
	})
})

// =============================================================================
// Types / Validate
// =============================================================================

var _ = Describe("State Validate", func() {
	Describe("TunnelIdentity", func() {
		It("should pass validation when TunnelID is set", func() {
			identity := TunnelIdentity{TunnelID: "abc-123"}
			Expect(identity.Validate()).To(Succeed())
		})

		It("should fail validation when TunnelID is empty", func() {
			identity := TunnelIdentity{}
			Expect(identity.Validate()).To(MatchError(ContainSubstring("tunnelID is required")))
		})
	})

	Describe("SecretInfo", func() {
		It("should pass validation when SecretName is set", func() {
			info := SecretInfo{SecretName: "my-secret"}
			Expect(info.Validate()).To(Succeed())
		})

		It("should fail validation when SecretName is empty", func() {
			info := SecretInfo{}
			Expect(info.Validate()).To(MatchError(ContainSubstring("secretName is required")))
		})
	})

	Describe("CloudflareTunnelPending", func() {
		It("should always pass validation", func() {
			s := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
			Expect(s.Validate()).To(Succeed())
		})

		It("should return PhasePending from Phase()", func() {
			s := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
			Expect(s.Phase()).To(Equal(PhasePending))
		})

		It("should return 0 RequeueAfter", func() {
			s := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
			Expect(s.RequeueAfter()).To(Equal(time.Duration(0)))
		})
	})

	Describe("CloudflareTunnelCreatingTunnel", func() {
		It("should always pass validation", func() {
			s := CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
			Expect(s.Validate()).To(Succeed())
		})

		It("should return PhaseCreatingTunnel from Phase()", func() {
			s := CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
			Expect(s.Phase()).To(Equal(PhaseCreatingTunnel))
		})

		It("should requeue after 5s", func() {
			s := CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
			Expect(s.RequeueAfter()).To(Equal(5 * time.Second))
		})
	})

	Describe("CloudflareTunnelCreatingSecret", func() {
		It("should pass validation when TunnelID is set", func() {
			s := CloudflareTunnelCreatingSecret{
				resource:       newTunnel(PhaseCreatingSecret),
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-123"},
			}
			Expect(s.Validate()).To(Succeed())
		})

		It("should fail validation when TunnelID is missing", func() {
			s := CloudflareTunnelCreatingSecret{resource: newTunnel(PhaseCreatingSecret)}
			Expect(s.Validate()).To(MatchError(ContainSubstring("tunnelID is required")))
		})
	})

	Describe("CloudflareTunnelConfiguringIngress", func() {
		It("should pass validation when TunnelID and SecretName are set", func() {
			s := CloudflareTunnelConfiguringIngress{
				resource:       newTunnel(PhaseConfiguringIngress),
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-123"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
			}
			Expect(s.Validate()).To(Succeed())
		})

		It("should fail validation when TunnelID is missing", func() {
			s := CloudflareTunnelConfiguringIngress{
				resource:   newTunnel(PhaseConfiguringIngress),
				SecretInfo: SecretInfo{SecretName: "my-secret"},
			}
			Expect(s.Validate()).To(MatchError(ContainSubstring("tunnelID is required")))
		})

		It("should fail validation when SecretName is missing", func() {
			s := CloudflareTunnelConfiguringIngress{
				resource:       newTunnel(PhaseConfiguringIngress),
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-123"},
			}
			Expect(s.Validate()).To(MatchError(ContainSubstring("secretName is required")))
		})
	})

	Describe("CloudflareTunnelReady", func() {
		It("should pass validation when TunnelID and SecretName are set", func() {
			s := CloudflareTunnelReady{
				resource:       newTunnel(PhaseReady),
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-123"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
			}
			Expect(s.Validate()).To(Succeed())
		})

		It("should fail validation when TunnelID is missing", func() {
			s := CloudflareTunnelReady{
				resource:   newTunnel(PhaseReady),
				SecretInfo: SecretInfo{SecretName: "my-secret"},
			}
			Expect(s.Validate()).To(MatchError(ContainSubstring("tunnelID is required")))
		})

		It("should requeue after 300s", func() {
			s := CloudflareTunnelReady{
				resource:       newTunnel(PhaseReady),
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-123"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
			}
			Expect(s.RequeueAfter()).To(Equal(300 * time.Second))
		})
	})

	Describe("CloudflareTunnelFailed", func() {
		It("should pass validation when LastState and ErrorMessage are set", func() {
			s := CloudflareTunnelFailed{
				resource:     newTunnel(PhaseFailed),
				LastState:    "CreatingTunnel",
				ErrorMessage: "API error",
			}
			Expect(s.Validate()).To(Succeed())
		})

		It("should fail validation when LastState is missing", func() {
			s := CloudflareTunnelFailed{
				resource:     newTunnel(PhaseFailed),
				ErrorMessage: "API error",
			}
			Expect(s.Validate()).To(MatchError(ContainSubstring("lastState is required")))
		})

		It("should fail validation when ErrorMessage is missing", func() {
			s := CloudflareTunnelFailed{
				resource:  newTunnel(PhaseFailed),
				LastState: "CreatingTunnel",
			}
			Expect(s.Validate()).To(MatchError(ContainSubstring("errorMessage is required")))
		})

		It("should requeue after 60s", func() {
			s := CloudflareTunnelFailed{resource: newTunnel(PhaseFailed), LastState: "x", ErrorMessage: "y"}
			Expect(s.RequeueAfter()).To(Equal(60 * time.Second))
		})
	})

	Describe("CloudflareTunnelDeletingTunnel", func() {
		It("should pass validation when TunnelID is set", func() {
			s := CloudflareTunnelDeletingTunnel{
				resource:       newTunnel(PhaseDeletingTunnel),
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-123"},
			}
			Expect(s.Validate()).To(Succeed())
		})

		It("should fail validation when TunnelID is missing", func() {
			s := CloudflareTunnelDeletingTunnel{resource: newTunnel(PhaseDeletingTunnel)}
			Expect(s.Validate()).To(MatchError(ContainSubstring("tunnelID is required")))
		})

		It("should requeue after 5s", func() {
			s := CloudflareTunnelDeletingTunnel{
				resource:       newTunnel(PhaseDeletingTunnel),
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-123"},
			}
			Expect(s.RequeueAfter()).To(Equal(5 * time.Second))
		})
	})

	Describe("CloudflareTunnelDeleted", func() {
		It("should always pass validation", func() {
			s := CloudflareTunnelDeleted{resource: newTunnel(PhaseDeleted)}
			Expect(s.Validate()).To(Succeed())
		})

		It("should return 0 RequeueAfter", func() {
			s := CloudflareTunnelDeleted{resource: newTunnel(PhaseDeleted)}
			Expect(s.RequeueAfter()).To(Equal(time.Duration(0)))
		})
	})

	Describe("CloudflareTunnelUnknown", func() {
		It("should pass validation when ObservedPhase is set", func() {
			s := CloudflareTunnelUnknown{
				resource:      newTunnel(PhaseUnknown),
				ObservedPhase: "SomeOldPhase",
			}
			Expect(s.Validate()).To(Succeed())
		})

		It("should fail validation when ObservedPhase is empty", func() {
			s := CloudflareTunnelUnknown{resource: newTunnel(PhaseUnknown)}
			Expect(s.Validate()).To(MatchError(ContainSubstring("observedPhase is required")))
		})

		It("should return 0 RequeueAfter", func() {
			s := CloudflareTunnelUnknown{resource: newTunnel(PhaseUnknown), ObservedPhase: "x"}
			Expect(s.RequeueAfter()).To(Equal(time.Duration(0)))
		})
	})
})

// =============================================================================
// Transitions
// =============================================================================

var _ = Describe("Transitions", func() {
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		resource = newTunnel("")
	})

	Describe("Pending transitions", func() {
		var pending CloudflareTunnelPending

		BeforeEach(func() {
			pending = CloudflareTunnelPending{resource: resource}
		})

		It("StartCreation should transition to CreatingTunnel", func() {
			next := pending.StartCreation()
			Expect(next.Phase()).To(Equal(PhaseCreatingTunnel))
			Expect(next.Resource()).To(Equal(resource))
		})

		It("StartDeletion should transition to DeletingTunnel", func() {
			next := pending.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.Resource()).To(Equal(resource))
		})
	})

	Describe("CreatingTunnel transitions", func() {
		var creating CloudflareTunnelCreatingTunnel

		BeforeEach(func() {
			creating = CloudflareTunnelCreatingTunnel{resource: resource}
		})

		It("TunnelCreated should transition to CreatingSecret with TunnelID", func() {
			next := creating.TunnelCreated("tunnel-abc")
			Expect(next.Phase()).To(Equal(PhaseCreatingSecret))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("tunnel-abc"))
			Expect(next.Resource()).To(Equal(resource))
		})

		It("MarkFailed should transition to Failed with error details", func() {
			next := creating.MarkFailed("CreatingTunnel", "API error occurred", 1)
			Expect(next.Phase()).To(Equal(PhaseFailed))
			Expect(next.LastState).To(Equal("CreatingTunnel"))
			Expect(next.ErrorMessage).To(Equal("API error occurred"))
			Expect(next.RetryCount).To(Equal(1))
			Expect(next.Resource()).To(Equal(resource))
		})

		It("StartDeletion should transition to DeletingTunnel", func() {
			next := creating.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.Resource()).To(Equal(resource))
			// No tunnel identity since it wasn't set on CreatingTunnel
			Expect(next.TunnelIdentity.TunnelID).To(BeEmpty())
		})
	})

	Describe("CreatingSecret transitions", func() {
		var creatingSecret CloudflareTunnelCreatingSecret

		BeforeEach(func() {
			creatingSecret = CloudflareTunnelCreatingSecret{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-abc"},
			}
		})

		It("SecretCreated should transition to ConfiguringIngress with SecretName", func() {
			next := creatingSecret.SecretCreated("my-tunnel-secret")
			Expect(next.Phase()).To(Equal(PhaseConfiguringIngress))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("tunnel-abc"))
			Expect(next.SecretInfo.SecretName).To(Equal("my-tunnel-secret"))
			Expect(next.Resource()).To(Equal(resource))
		})

		It("MarkFailed should transition to Failed with error details", func() {
			next := creatingSecret.MarkFailed("CreatingSecret", "secret creation failed", 2)
			Expect(next.Phase()).To(Equal(PhaseFailed))
			Expect(next.LastState).To(Equal("CreatingSecret"))
			Expect(next.ErrorMessage).To(Equal("secret creation failed"))
			Expect(next.RetryCount).To(Equal(2))
		})

		It("StartDeletion should transition to DeletingTunnel preserving TunnelID", func() {
			next := creatingSecret.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("tunnel-abc"))
			Expect(next.Resource()).To(Equal(resource))
		})
	})

	Describe("ConfiguringIngress transitions", func() {
		var configuringIngress CloudflareTunnelConfiguringIngress

		BeforeEach(func() {
			configuringIngress = CloudflareTunnelConfiguringIngress{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-abc"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
			}
		})

		It("IngressConfigured should transition to Ready with active=true", func() {
			next := configuringIngress.IngressConfigured(true)
			Expect(next.Phase()).To(Equal(PhaseReady))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("tunnel-abc"))
			Expect(next.SecretInfo.SecretName).To(Equal("my-secret"))
			Expect(next.Active).To(BeTrue())
			Expect(next.Resource()).To(Equal(resource))
		})

		It("IngressConfigured should transition to Ready with active=false", func() {
			next := configuringIngress.IngressConfigured(false)
			Expect(next.Phase()).To(Equal(PhaseReady))
			Expect(next.Active).To(BeFalse())
		})

		It("MarkFailed should transition to Failed with error details", func() {
			next := configuringIngress.MarkFailed("ConfiguringIngress", "ingress config error", 3)
			Expect(next.Phase()).To(Equal(PhaseFailed))
			Expect(next.LastState).To(Equal("ConfiguringIngress"))
			Expect(next.ErrorMessage).To(Equal("ingress config error"))
			Expect(next.RetryCount).To(Equal(3))
		})

		It("StartDeletion should transition to DeletingTunnel preserving TunnelID", func() {
			next := configuringIngress.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("tunnel-abc"))
		})
	})

	Describe("Ready transitions", func() {
		var ready CloudflareTunnelReady

		BeforeEach(func() {
			ready = CloudflareTunnelReady{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-abc"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
				Active:         true,
			}
		})

		It("StartDeletion should transition to DeletingTunnel preserving TunnelID", func() {
			next := ready.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("tunnel-abc"))
			Expect(next.Resource()).To(Equal(resource))
		})

		It("ReconfigureIngress should transition to ConfiguringIngress preserving identity", func() {
			next := ready.ReconfigureIngress()
			Expect(next.Phase()).To(Equal(PhaseConfiguringIngress))
			Expect(next.TunnelIdentity.TunnelID).To(Equal("tunnel-abc"))
			Expect(next.SecretInfo.SecretName).To(Equal("my-secret"))
			Expect(next.Resource()).To(Equal(resource))
		})
	})

	Describe("Failed transitions", func() {
		It("Retry should return Pending when RetryCount < 10", func() {
			failed := CloudflareTunnelFailed{
				resource:     resource,
				LastState:    "CreatingTunnel",
				ErrorMessage: "some error",
				RetryCount:   5,
			}
			next := failed.Retry()
			Expect(next).NotTo(BeNil())
			Expect(next.Phase()).To(Equal(PhasePending))
			Expect(next.Resource()).To(Equal(resource))
		})

		It("Retry should return nil when RetryCount == 10 (guard condition)", func() {
			failed := CloudflareTunnelFailed{
				resource:     resource,
				LastState:    "CreatingTunnel",
				ErrorMessage: "some error",
				RetryCount:   10,
			}
			next := failed.Retry()
			Expect(next).To(BeNil())
		})

		It("Retry should return nil when RetryCount > 10", func() {
			failed := CloudflareTunnelFailed{
				resource:     resource,
				LastState:    "CreatingTunnel",
				ErrorMessage: "some error",
				RetryCount:   15,
			}
			next := failed.Retry()
			Expect(next).To(BeNil())
		})

		It("Retry should succeed when RetryCount == 9", func() {
			failed := CloudflareTunnelFailed{
				resource:     resource,
				LastState:    "CreatingTunnel",
				ErrorMessage: "some error",
				RetryCount:   9,
			}
			next := failed.Retry()
			Expect(next).NotTo(BeNil())
		})

		It("StartDeletion should transition to DeletingTunnel", func() {
			failed := CloudflareTunnelFailed{
				resource:     resource,
				LastState:    "CreatingTunnel",
				ErrorMessage: "some error",
			}
			next := failed.StartDeletion()
			Expect(next.Phase()).To(Equal(PhaseDeletingTunnel))
			Expect(next.Resource()).To(Equal(resource))
		})

		It("IsRetryable should return true", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y"}
			Expect(failed.IsRetryable()).To(BeTrue())
		})

		It("IsMaxRetriesExceeded should return true when RetryCount >= 10", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 10}
			Expect(failed.IsMaxRetriesExceeded()).To(BeTrue())
		})

		It("IsMaxRetriesExceeded should return false when RetryCount < 10", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 9}
			Expect(failed.IsMaxRetriesExceeded()).To(BeFalse())
		})

		It("RetryBackoff should increase with higher RetryCount", func() {
			// Use multiple samples since there's jitter; take the mean over many runs
			low := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 0}
			high := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 5}

			// Average over samples to reduce jitter variance
			const samples = 100
			var lowTotal, highTotal time.Duration
			for i := 0; i < samples; i++ {
				lowTotal += low.RetryBackoff()
				highTotal += high.RetryBackoff()
			}
			Expect(highTotal / samples).To(BeNumerically(">", lowTotal/samples))
		})

		It("RetryBackoff should be capped at 300s", func() {
			maxed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 100}
			for i := 0; i < 20; i++ {
				backoff := maxed.RetryBackoff()
				// With 10% jitter on 300s, max is 330s
				Expect(backoff).To(BeNumerically("<=", 330*time.Second))
			}
		})

		It("RetryBackoff should be positive", func() {
			failed := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y", RetryCount: 0}
			Expect(failed.RetryBackoff()).To(BeNumerically(">", 0))
		})
	})

	Describe("DeletingTunnel transitions", func() {
		It("DeletionComplete should transition to Deleted", func() {
			deleting := CloudflareTunnelDeletingTunnel{
				resource:       resource,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-abc"},
			}
			next := deleting.DeletionComplete()
			Expect(next.Phase()).To(Equal(PhaseDeleted))
			Expect(next.Resource()).To(Equal(resource))
		})
	})

	Describe("Unknown transitions", func() {
		It("Reset should transition to Pending for recovery", func() {
			unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "SomeOldPhase"}
			next := unknown.Reset()
			Expect(next.Phase()).To(Equal(PhasePending))
			Expect(next.Resource()).To(Equal(resource))
		})

		It("IsRetryable should return true", func() {
			unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"}
			Expect(unknown.IsRetryable()).To(BeTrue())
		})

		It("IsMaxRetriesExceeded should always return false", func() {
			unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"}
			Expect(unknown.IsMaxRetriesExceeded()).To(BeFalse())
		})

		It("RetryBackoff should return 5s (base duration)", func() {
			unknown := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"}
			Expect(unknown.RetryBackoff()).To(Equal(5 * time.Second))
		})
	})
})

// =============================================================================
// Calculator
// =============================================================================

var _ = Describe("CloudflareTunnelCalculator", func() {
	var calculator *CloudflareTunnelCalculator

	BeforeEach(func() {
		calculator = NewCloudflareTunnelCalculator(logr.Discard())
	})

	Describe("NewCloudflareTunnelCalculator", func() {
		It("should create a calculator", func() {
			Expect(calculator).NotTo(BeNil())
		})
	})

	Describe("Calculate - normal states", func() {
		It("should return Pending for empty phase", func() {
			r := newTunnel("")
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelPending)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelPending, got %T", state)
			Expect(state.Phase()).To(Equal(PhasePending))
		})

		It("should return Pending for Pending phase", func() {
			r := newTunnel(PhasePending)
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelPending)
			Expect(ok).To(BeTrue())
		})

		It("should return CreatingTunnel for CreatingTunnel phase", func() {
			r := newTunnel(PhaseCreatingTunnel)
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelCreatingTunnel)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelCreatingTunnel, got %T", state)
		})

		It("should return CreatingSecret for CreatingSecret phase with valid TunnelID", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseCreatingSecret,
				TunnelID: "tunnel-123",
			})
			state := calculator.Calculate(r)
			s, ok := state.(CloudflareTunnelCreatingSecret)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelCreatingSecret, got %T", state)
			Expect(s.TunnelIdentity.TunnelID).To(Equal("tunnel-123"))
		})

		It("should fall back to Unknown for CreatingSecret phase with missing TunnelID", func() {
			r := newTunnel(PhaseCreatingSecret) // TunnelID is empty
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown due to missing TunnelID, got %T", state)
		})

		It("should return ConfiguringIngress for ConfiguringIngress phase with valid fields", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseConfiguringIngress,
				TunnelID:   "tunnel-123",
				SecretName: "my-secret",
			})
			state := calculator.Calculate(r)
			s, ok := state.(CloudflareTunnelConfiguringIngress)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelConfiguringIngress, got %T", state)
			Expect(s.TunnelIdentity.TunnelID).To(Equal("tunnel-123"))
			Expect(s.SecretInfo.SecretName).To(Equal("my-secret"))
		})

		It("should fall back to Unknown for ConfiguringIngress phase with missing TunnelID", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseConfiguringIngress,
				SecretName: "my-secret",
			})
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown due to missing TunnelID, got %T", state)
		})

		It("should fall back to Unknown for ConfiguringIngress phase with missing SecretName", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseConfiguringIngress,
				TunnelID: "tunnel-123",
			})
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown due to missing SecretName, got %T", state)
		})

		It("should return Ready for Ready phase with valid fields", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseReady,
				TunnelID:   "tunnel-123",
				SecretName: "my-secret",
				Active:     true,
			})
			state := calculator.Calculate(r)
			s, ok := state.(CloudflareTunnelReady)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelReady, got %T", state)
			Expect(s.TunnelIdentity.TunnelID).To(Equal("tunnel-123"))
			Expect(s.SecretInfo.SecretName).To(Equal("my-secret"))
			Expect(s.Active).To(BeTrue())
		})

		It("should fall back to Unknown for Ready phase with missing TunnelID", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:      PhaseReady,
				SecretName: "my-secret",
			})
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown due to missing TunnelID, got %T", state)
		})

		It("should return Failed for Failed phase with valid fields", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:        PhaseFailed,
				LastState:    "CreatingTunnel",
				ErrorMessage: "some error",
				RetryCount:   3,
			})
			state := calculator.Calculate(r)
			s, ok := state.(CloudflareTunnelFailed)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelFailed, got %T", state)
			Expect(s.LastState).To(Equal("CreatingTunnel"))
			Expect(s.ErrorMessage).To(Equal("some error"))
			Expect(s.RetryCount).To(Equal(3))
		})

		It("should fall back to Unknown for Failed phase with missing LastState", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:        PhaseFailed,
				ErrorMessage: "some error",
			})
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown due to missing LastState, got %T", state)
		})

		It("should return Unknown for Unknown phase with valid ObservedPhase", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:         PhaseUnknown,
				ObservedPhase: "SomeCorruptedPhase",
			})
			state := calculator.Calculate(r)
			s, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown, got %T", state)
			Expect(s.ObservedPhase).To(Equal("SomeCorruptedPhase"))
		})

		It("should return Unknown for truly unrecognized phase string", func() {
			r := newTunnel("SomeGarbage")
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown for garbage phase, got %T", state)
		})
	})

	Describe("Calculate - deletion states", func() {
		var deletionTimestamp metav1.Time

		BeforeEach(func() {
			deletionTimestamp = metav1.Now()
		})

		It("should return DeletingTunnel when already in DeletingTunnel phase with DeletionTimestamp", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
				Phase:    PhaseDeletingTunnel,
				TunnelID: "tunnel-123",
			})
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelDeletingTunnel)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelDeletingTunnel, got %T", state)
		})

		It("should return Deleted when already in Deleted phase with DeletionTimestamp", func() {
			r := newTunnelWithStatus(v1.CloudflareTunnelStatus{Phase: PhaseDeleted})
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelDeleted, got %T", state)
		})

		It("should transition to Deleted directly when no TunnelID is available", func() {
			// Empty tunnel (no phase, no TunnelID) with deletion timestamp
			r := newTunnel("")
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			// Without a TunnelID, DeletingTunnel.Validate() fails, so it goes directly to Deleted
			_, ok := state.(CloudflareTunnelDeleted)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelDeleted when no tunnel IDs present, got %T", state)
		})

		It("should not check deletion when phase is unrecognized (returns Unknown)", func() {
			r := newTunnel("SomeGarbage")
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			_, ok := state.(CloudflareTunnelUnknown)
			Expect(ok).To(BeTrue(), "expected CloudflareTunnelUnknown for garbage phase, got %T", state)
		})

		It("should start deletion from Pending phase when DeletionTimestamp set", func() {
			r := newTunnel(PhasePending)
			r.DeletionTimestamp = &deletionTimestamp
			state := calculator.Calculate(r)
			// No TunnelID on Pending → validation fails → Deleted
			_, isDeleted := state.(CloudflareTunnelDeleted)
			Expect(isDeleted).To(BeTrue(), "expected CloudflareTunnelDeleted from Pending with no TunnelID, got %T", state)
		})
	})
})

// =============================================================================
// Visit pattern
// =============================================================================

var _ = Describe("Visit", func() {
	var resource *v1.CloudflareTunnel

	BeforeEach(func() {
		resource = newTunnel("")
	})

	It("should dispatch Pending to VisitPending", func() {
		state := CloudflareTunnelPending{resource: resource}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnPending: func(_ CloudflareTunnelPending) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	It("should dispatch CreatingTunnel to VisitCreatingTunnel", func() {
		state := CloudflareTunnelCreatingTunnel{resource: resource}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnCreatingTunnel: func(_ CloudflareTunnelCreatingTunnel) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	It("should dispatch CreatingSecret to VisitCreatingSecret", func() {
		state := CloudflareTunnelCreatingSecret{resource: resource, TunnelIdentity: TunnelIdentity{TunnelID: "t"}}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnCreatingSecret: func(_ CloudflareTunnelCreatingSecret) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	It("should dispatch ConfiguringIngress to VisitConfiguringIngress", func() {
		state := CloudflareTunnelConfiguringIngress{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			SecretInfo:     SecretInfo{SecretName: "s"},
		}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnConfiguringIngress: func(_ CloudflareTunnelConfiguringIngress) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	It("should dispatch Ready to VisitReady", func() {
		state := CloudflareTunnelReady{
			resource:       resource,
			TunnelIdentity: TunnelIdentity{TunnelID: "t"},
			SecretInfo:     SecretInfo{SecretName: "s"},
		}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnReady: func(_ CloudflareTunnelReady) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	It("should dispatch Failed to VisitFailed", func() {
		state := CloudflareTunnelFailed{resource: resource, LastState: "x", ErrorMessage: "y"}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnFailed: func(_ CloudflareTunnelFailed) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	It("should dispatch DeletingTunnel to VisitDeletingTunnel", func() {
		state := CloudflareTunnelDeletingTunnel{resource: resource}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnDeletingTunnel: func(_ CloudflareTunnelDeletingTunnel) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	It("should dispatch Deleted to VisitDeleted", func() {
		state := CloudflareTunnelDeleted{resource: resource}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnDeleted: func(_ CloudflareTunnelDeleted) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	It("should dispatch Unknown to VisitUnknown", func() {
		state := CloudflareTunnelUnknown{resource: resource, ObservedPhase: "x"}
		called := false
		Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
			OnUnknown: func(_ CloudflareTunnelUnknown) bool { called = true; return true },
		})
		Expect(called).To(BeTrue())
	})

	Describe("FuncVisitor default fallback", func() {
		It("should call Default when specific handler is nil", func() {
			state := CloudflareTunnelPending{resource: resource}
			defaultCalled := false
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				Default: func(_ CloudflareTunnelState) bool { defaultCalled = true; return true },
			})
			Expect(defaultCalled).To(BeTrue())
		})

		It("should prefer specific handler over Default", func() {
			state := CloudflareTunnelPending{resource: resource}
			specificCalled := false
			defaultCalled := false
			Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{
				OnPending: func(_ CloudflareTunnelPending) bool { specificCalled = true; return true },
				Default:   func(_ CloudflareTunnelState) bool { defaultCalled = true; return true },
			})
			Expect(specificCalled).To(BeTrue())
			Expect(defaultCalled).To(BeFalse())
		})

		It("should return zero value when no handlers set", func() {
			state := CloudflareTunnelPending{resource: resource}
			result := Visit[bool](state, &CloudflareTunnelFuncVisitor[bool]{})
			Expect(result).To(BeFalse()) // zero value for bool
		})

		It("should return zero string when no handlers set", func() {
			state := CloudflareTunnelPending{resource: resource}
			result := Visit[string](state, &CloudflareTunnelFuncVisitor[string]{})
			Expect(result).To(Equal(""))
		})

		It("Default fallback works for all state types", func() {
			states := []CloudflareTunnelState{
				CloudflareTunnelPending{resource: resource},
				CloudflareTunnelCreatingTunnel{resource: resource},
				CloudflareTunnelCreatingSecret{resource: resource},
				CloudflareTunnelConfiguringIngress{resource: resource},
				CloudflareTunnelReady{resource: resource},
				CloudflareTunnelFailed{resource: resource},
				CloudflareTunnelDeletingTunnel{resource: resource},
				CloudflareTunnelDeleted{resource: resource},
				CloudflareTunnelUnknown{resource: resource},
			}
			for _, s := range states {
				called := false
				Visit[bool](s, &CloudflareTunnelFuncVisitor[bool]{
					Default: func(_ CloudflareTunnelState) bool { called = true; return true },
				})
				Expect(called).To(BeTrue(), "Default not called for state %T", s)
			}
		})
	})

	Describe("Visit returns correct value", func() {
		It("should return the phase name via visitor", func() {
			states := []CloudflareTunnelState{
				CloudflareTunnelPending{resource: resource},
				CloudflareTunnelCreatingTunnel{resource: resource},
				CloudflareTunnelReady{resource: resource},
			}
			for _, s := range states {
				phase := Visit[string](s, &CloudflareTunnelFuncVisitor[string]{
					Default: func(st CloudflareTunnelState) string { return st.Phase() },
				})
				Expect(phase).To(Equal(s.Phase()))
			}
		})
	})
})

// =============================================================================
// Status helpers
// =============================================================================

var _ = Describe("Status helpers", func() {
	Describe("HasSpecChanged", func() {
		It("should return true when generation != observedGeneration", func() {
			r := newTunnel(PhasePending)
			r.Generation = 2
			r.Status.ObservedGeneration = 1
			Expect(HasSpecChanged(r)).To(BeTrue())
		})

		It("should return false when generation == observedGeneration", func() {
			r := newTunnel(PhasePending)
			r.Generation = 3
			r.Status.ObservedGeneration = 3
			Expect(HasSpecChanged(r)).To(BeFalse())
		})

		It("should return false when both are zero (new resource)", func() {
			r := newTunnel(PhasePending)
			Expect(HasSpecChanged(r)).To(BeFalse())
		})
	})

	Describe("UpdateObservedGeneration", func() {
		It("should set observedGeneration to current generation", func() {
			r := newTunnel(PhasePending)
			r.Generation = 5
			r.Status.ObservedGeneration = 3
			updated := UpdateObservedGeneration(r)
			Expect(updated.Status.ObservedGeneration).To(Equal(int64(5)))
		})

		It("should not modify the original resource (deep copy)", func() {
			r := newTunnel(PhasePending)
			r.Generation = 5
			r.Status.ObservedGeneration = 3
			_ = UpdateObservedGeneration(r)
			Expect(r.Status.ObservedGeneration).To(Equal(int64(3))) // original unchanged
		})
	})

	Describe("ApplyStatus", func() {
		It("Pending should set Phase to Pending", func() {
			r := newTunnel("")
			s := CloudflareTunnelPending{resource: r}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhasePending))
		})

		It("CreatingTunnel should set Phase to CreatingTunnel", func() {
			r := newTunnel("")
			s := CloudflareTunnelCreatingTunnel{resource: r}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhaseCreatingTunnel))
		})

		It("CreatingSecret should set Phase and TunnelID", func() {
			r := newTunnel("")
			s := CloudflareTunnelCreatingSecret{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-xyz"},
			}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhaseCreatingSecret))
			Expect(updated.Status.TunnelID).To(Equal("tunnel-xyz"))
		})

		It("ConfiguringIngress should set Phase, TunnelID, and SecretName", func() {
			r := newTunnel("")
			s := CloudflareTunnelConfiguringIngress{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-xyz"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
			}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhaseConfiguringIngress))
			Expect(updated.Status.TunnelID).To(Equal("tunnel-xyz"))
			Expect(updated.Status.SecretName).To(Equal("my-secret"))
		})

		It("Ready should set Phase, TunnelID, SecretName, Active, and Ready=true", func() {
			r := newTunnel("")
			s := CloudflareTunnelReady{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-xyz"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
				Active:         true,
			}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhaseReady))
			Expect(updated.Status.TunnelID).To(Equal("tunnel-xyz"))
			Expect(updated.Status.SecretName).To(Equal("my-secret"))
			Expect(updated.Status.Active).To(BeTrue())
			Expect(updated.Status.Ready).To(BeTrue())
		})

		It("Ready with Active=false should set Active=false", func() {
			r := newTunnel("")
			s := CloudflareTunnelReady{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-xyz"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
				Active:         false,
			}
			updated := s.ApplyStatus()
			Expect(updated.Status.Active).To(BeFalse())
			Expect(updated.Status.Ready).To(BeTrue())
		})

		It("Failed should set Phase, RetryCount, LastState, and ErrorMessage", func() {
			r := newTunnel("")
			s := CloudflareTunnelFailed{
				resource:     r,
				RetryCount:   5,
				LastState:    "CreatingTunnel",
				ErrorMessage: "error details",
			}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhaseFailed))
			Expect(updated.Status.RetryCount).To(Equal(5))
			Expect(updated.Status.LastState).To(Equal("CreatingTunnel"))
			Expect(updated.Status.ErrorMessage).To(Equal("error details"))
		})

		It("DeletingTunnel should set Phase and TunnelID", func() {
			r := newTunnel("")
			s := CloudflareTunnelDeletingTunnel{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-xyz"},
			}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhaseDeletingTunnel))
			Expect(updated.Status.TunnelID).To(Equal("tunnel-xyz"))
		})

		It("Deleted should set Phase to Deleted", func() {
			r := newTunnel("")
			s := CloudflareTunnelDeleted{resource: r}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhaseDeleted))
		})

		It("Unknown should set Phase and ObservedPhase", func() {
			r := newTunnel("")
			s := CloudflareTunnelUnknown{
				resource:      r,
				ObservedPhase: "OldCorruptedPhase",
			}
			updated := s.ApplyStatus()
			Expect(updated.Status.Phase).To(Equal(PhaseUnknown))
			Expect(updated.Status.ObservedPhase).To(Equal("OldCorruptedPhase"))
		})

		It("ApplyStatus should not modify the original resource (deep copy)", func() {
			r := newTunnel("")
			s := CloudflareTunnelPending{resource: r}
			updated := s.ApplyStatus()
			Expect(updated).NotTo(BeIdenticalTo(r))
			Expect(r.Status.Phase).To(BeEmpty()) // original unchanged
		})
	})

	Describe("SSAPatch", func() {
		It("should create a valid patch for Pending state", func() {
			r := newTunnel(PhasePending)
			s := CloudflareTunnelPending{resource: r}
			patch, err := SSAPatch(s)
			Expect(err).NotTo(HaveOccurred())
			Expect(patch).NotTo(BeNil())
		})

		It("should create a valid patch for Ready state", func() {
			r := newTunnel(PhaseReady)
			s := CloudflareTunnelReady{
				resource:       r,
				TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-xyz"},
				SecretInfo:     SecretInfo{SecretName: "my-secret"},
				Active:         true,
			}
			patch, err := SSAPatch(s)
			Expect(err).NotTo(HaveOccurred())
			Expect(patch).NotTo(BeNil())
		})

		It("should create a valid patch for Failed state", func() {
			r := newTunnel(PhaseFailed)
			s := CloudflareTunnelFailed{
				resource:     r,
				LastState:    "CreatingTunnel",
				ErrorMessage: "something went wrong",
				RetryCount:   2,
			}
			patch, err := SSAPatch(s)
			Expect(err).NotTo(HaveOccurred())
			Expect(patch).NotTo(BeNil())
		})

		It("FieldManager should be a non-empty string", func() {
			Expect(FieldManager).NotTo(BeEmpty())
		})
	})
})

// =============================================================================
// Full state machine lifecycle integration test
// =============================================================================

var _ = Describe("Full lifecycle integration", func() {
	It("should traverse the happy path: Pending → Ready", func() {
		r := newTunnel("")
		calculator := NewCloudflareTunnelCalculator(logr.Discard())

		// Start: empty resource → Pending
		state := calculator.Calculate(r)
		pending, ok := state.(CloudflareTunnelPending)
		Expect(ok).To(BeTrue())

		// Pending → CreatingTunnel
		creating := pending.StartCreation()
		Expect(creating.Phase()).To(Equal(PhaseCreatingTunnel))

		// CreatingTunnel → CreatingSecret
		creatingSecret := creating.TunnelCreated("tunnel-abc-123")
		Expect(creatingSecret.Phase()).To(Equal(PhaseCreatingSecret))
		Expect(creatingSecret.TunnelIdentity.TunnelID).To(Equal("tunnel-abc-123"))

		// CreatingSecret → ConfiguringIngress
		configuringIngress := creatingSecret.SecretCreated("my-tunnel-secret")
		Expect(configuringIngress.Phase()).To(Equal(PhaseConfiguringIngress))
		Expect(configuringIngress.TunnelIdentity.TunnelID).To(Equal("tunnel-abc-123"))
		Expect(configuringIngress.SecretInfo.SecretName).To(Equal("my-tunnel-secret"))

		// ConfiguringIngress → Ready
		ready := configuringIngress.IngressConfigured(true)
		Expect(ready.Phase()).To(Equal(PhaseReady))
		Expect(ready.TunnelIdentity.TunnelID).To(Equal("tunnel-abc-123"))
		Expect(ready.SecretInfo.SecretName).To(Equal("my-tunnel-secret"))
		Expect(ready.Active).To(BeTrue())
	})

	It("should traverse the deletion path: Ready → Deleted", func() {
		r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
			Phase:      PhaseReady,
			TunnelID:   "tunnel-abc-123",
			SecretName: "my-tunnel-secret",
			Active:     true,
		})
		ready := CloudflareTunnelReady{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-abc-123"},
			SecretInfo:     SecretInfo{SecretName: "my-tunnel-secret"},
			Active:         true,
		}

		// Ready → DeletingTunnel
		deleting := ready.StartDeletion()
		Expect(deleting.Phase()).To(Equal(PhaseDeletingTunnel))
		Expect(deleting.TunnelIdentity.TunnelID).To(Equal("tunnel-abc-123"))

		// DeletingTunnel → Deleted
		deleted := deleting.DeletionComplete()
		Expect(deleted.Phase()).To(Equal(PhaseDeleted))
	})

	It("should traverse the retry path: CreatingTunnel → Failed → Pending", func() {
		r := newTunnel("")
		creating := CloudflareTunnelCreatingTunnel{resource: r}

		// CreatingTunnel → Failed
		failed := creating.MarkFailed("CreatingTunnel", "API timeout", 1)
		Expect(failed.Phase()).To(Equal(PhaseFailed))
		Expect(failed.RetryCount).To(Equal(1))

		// Failed → Pending (retry)
		pending := failed.Retry()
		Expect(pending).NotTo(BeNil())
		Expect(pending.Phase()).To(Equal(PhasePending))
	})

	It("should traverse the reconfigure path: Ready → ConfiguringIngress → Ready", func() {
		r := newTunnel("")
		ready := CloudflareTunnelReady{
			resource:       r,
			TunnelIdentity: TunnelIdentity{TunnelID: "tunnel-abc"},
			SecretInfo:     SecretInfo{SecretName: "my-secret"},
			Active:         true,
		}

		// Ready → ConfiguringIngress
		configuring := ready.ReconfigureIngress()
		Expect(configuring.Phase()).To(Equal(PhaseConfiguringIngress))
		Expect(configuring.TunnelIdentity.TunnelID).To(Equal("tunnel-abc"))

		// ConfiguringIngress → Ready again
		readyAgain := configuring.IngressConfigured(true)
		Expect(readyAgain.Phase()).To(Equal(PhaseReady))
	})

	It("should recover from Unknown via Reset: Unknown → Pending", func() {
		r := newTunnelWithStatus(v1.CloudflareTunnelStatus{
			Phase:         PhaseUnknown,
			ObservedPhase: "SomeCorruptedPhase",
		})
		unknown := CloudflareTunnelUnknown{resource: r, ObservedPhase: "SomeCorruptedPhase"}

		pending := unknown.Reset()
		Expect(pending.Phase()).To(Equal(PhasePending))
	})
})
