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
	"context"
	"errors"

	"github.com/go-logr/logr"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"go.opentelemetry.io/otel"
)

var _ = Describe("Observability", func() {
	// Helper states backed by real resources.
	var (
		ctx  context.Context
		from CloudflareTunnelState
		to   CloudflareTunnelState
		toV  CloudflareTunnelState // a state whose Validate() returns non-nil
	)

	BeforeEach(func() {
		// Provide a logger so LoggingObserver's ctrl.LoggerFrom(ctx) doesn't panic.
		ctx = logr.NewContext(context.Background(), logr.Discard())

		tunnel := newTunnel(PhasePending)
		from = CloudflareTunnelPending{resource: tunnel}
		to = CloudflareTunnelCreatingTunnel{resource: tunnel}
		// CloudflareTunnelCreatingSecret requires TunnelID; leaving it empty makes Validate() fail.
		toV = CloudflareTunnelCreatingSecret{resource: tunnel}
	})

	// ==========================================================================
	// ValidateTransition
	// ==========================================================================

	Describe("ValidateTransition", func() {
		It("returns nil when 'to' state is nil", func() {
			err := ValidateTransition(from, nil)
			Expect(err).NotTo(HaveOccurred())
		})

		It("returns nil when the target state is valid", func() {
			err := ValidateTransition(from, to)
			Expect(err).NotTo(HaveOccurred())
		})

		It("returns an error when the target state is invalid", func() {
			// toV is a CloudflareTunnelCreatingSecret with no TunnelID — Validate() must fail.
			err := ValidateTransition(from, toV)
			Expect(err).To(HaveOccurred())
		})

		It("ignores the 'from' state for validation purposes", func() {
			// Even if from is nil, the result depends solely on 'to'.
			err := ValidateTransition(nil, to)
			Expect(err).NotTo(HaveOccurred())
		})

		DescribeTable("validates every concrete state type",
			func(state CloudflareTunnelState, expectError bool) {
				err := ValidateTransition(from, state)
				if expectError {
					Expect(err).To(HaveOccurred())
				} else {
					Expect(err).NotTo(HaveOccurred())
				}
			},
			Entry("Pending (always valid)", func() CloudflareTunnelState {
				return CloudflareTunnelPending{resource: newTunnel(PhasePending)}
			}(), false),
			Entry("CreatingTunnel (always valid)", func() CloudflareTunnelState {
				return CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
			}(), false),
			Entry("CreatingSecret missing TunnelID", func() CloudflareTunnelState {
				return CloudflareTunnelCreatingSecret{resource: newTunnel(PhaseCreatingSecret)}
			}(), true),
			Entry("CreatingSecret with TunnelID", func() CloudflareTunnelState {
				return CloudflareTunnelCreatingSecret{
					resource:       newTunnel(PhaseCreatingSecret),
					TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
				}
			}(), false),
		)
	})

	// ==========================================================================
	// NoOpObserver
	// ==========================================================================

	Describe("NoOpObserver", func() {
		var obs NoOpObserver

		It("implements TransitionObserver", func() {
			var _ TransitionObserver = obs
		})

		It("OnTransition does nothing and does not panic", func() {
			Expect(func() {
				obs.OnTransition(ctx, from, to)
			}).NotTo(Panic())
		})

		It("OnTransitionError does nothing and does not panic", func() {
			Expect(func() {
				obs.OnTransitionError(ctx, from, to, errors.New("boom"))
			}).NotTo(Panic())
		})
	})

	// ==========================================================================
	// LoggingObserver
	// ==========================================================================

	Describe("LoggingObserver", func() {
		var obs LoggingObserver

		It("implements TransitionObserver", func() {
			var _ TransitionObserver = obs
		})

		It("OnTransition logs without panicking", func() {
			Expect(func() {
				obs.OnTransition(ctx, from, to)
			}).NotTo(Panic())
		})

		It("OnTransitionError logs without panicking", func() {
			Expect(func() {
				obs.OnTransitionError(ctx, from, to, errors.New("test error"))
			}).NotTo(Panic())
		})

		It("works with various from/to state combinations", func() {
			combinations := []struct {
				from, to CloudflareTunnelState
			}{
				{
					CloudflareTunnelPending{resource: newTunnel(PhasePending)},
					CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)},
				},
				{
					CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)},
					CloudflareTunnelCreatingSecret{
						resource:       newTunnel(PhaseCreatingSecret),
						TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
					},
				},
				{
					CloudflareTunnelReady{
						resource:       newTunnel(PhaseReady),
						TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
						SecretInfo:     SecretInfo{SecretName: "sec"},
					},
					CloudflareTunnelDeletingTunnel{
						resource:       newTunnel(PhaseDeletingTunnel),
						TunnelIdentity: TunnelIdentity{TunnelID: "tid"},
					},
				},
			}

			for _, c := range combinations {
				Expect(func() {
					obs.OnTransition(ctx, c.from, c.to)
				}).NotTo(Panic())
				Expect(func() {
					obs.OnTransitionError(ctx, c.from, c.to, errors.New("err"))
				}).NotTo(Panic())
			}
		})
	})

	// ==========================================================================
	// OTelObserver
	// ==========================================================================

	Describe("OTelObserver", func() {
		var obs *OTelObserver

		BeforeEach(func() {
			// Use the global (no-op) tracer so no real OTel backend is needed.
			obs = NewOTelObserver("test-tracer")
		})

		It("implements TransitionObserver", func() {
			var _ TransitionObserver = obs
		})

		It("NewOTelObserver returns a non-nil observer", func() {
			Expect(obs).NotTo(BeNil())
		})

		It("OnTransition creates a span without panicking", func() {
			Expect(func() {
				obs.OnTransition(ctx, from, to)
			}).NotTo(Panic())
		})

		It("OnTransitionError creates a span with error without panicking", func() {
			Expect(func() {
				obs.OnTransitionError(ctx, from, to, errors.New("transition failed"))
			}).NotTo(Panic())
		})

		It("uses the provided tracer name via the global OTel provider", func() {
			// Confirm the observer uses the global tracer provider's tracer.
			named := NewOTelObserver("my-controller")
			Expect(named).NotTo(BeNil())
			// The tracer field should be set (non-nil).
			Expect(named.tracer).To(Equal(otel.Tracer("my-controller")))
		})
	})

	// ==========================================================================
	// CompositeObserver
	// ==========================================================================

	Describe("CompositeObserver", func() {
		It("implements TransitionObserver", func() {
			var _ TransitionObserver = CompositeObserver{}
		})

		It("OnTransition calls all child observers", func() {
			var called []string
			recorder := &recordingObserver{calls: &called}

			obs := CompositeObserver{
				recorder,
				recorder,
			}
			obs.OnTransition(ctx, from, to)

			Expect(called).To(HaveLen(2))
			Expect(called).To(ConsistOf("OnTransition", "OnTransition"))
		})

		It("OnTransitionError calls all child observers", func() {
			var called []string
			recorder := &recordingObserver{calls: &called}

			obs := CompositeObserver{recorder, recorder}
			obs.OnTransitionError(ctx, from, to, errors.New("boom"))

			Expect(called).To(HaveLen(2))
			Expect(called).To(ConsistOf("OnTransitionError", "OnTransitionError"))
		})

		It("handles an empty composite observer without panicking", func() {
			obs := CompositeObserver{}
			Expect(func() {
				obs.OnTransition(ctx, from, to)
				obs.OnTransitionError(ctx, from, to, errors.New("e"))
			}).NotTo(Panic())
		})

		It("calls observers in order", func() {
			var order []int
			obs := CompositeObserver{
				&indexObserver{idx: 1, order: &order},
				&indexObserver{idx: 2, order: &order},
				&indexObserver{idx: 3, order: &order},
			}
			obs.OnTransition(ctx, from, to)
			Expect(order).To(Equal([]int{1, 2, 3}))
		})

		It("composes NoOp, Logging, and Metrics observers without panicking", func() {
			obs := CompositeObserver{
				NoOpObserver{},
				LoggingObserver{},
				NewMetricsObserver(),
			}
			Expect(func() {
				obs.OnTransition(ctx, from, to)
				obs.OnTransitionError(ctx, from, to, errors.New("e"))
			}).NotTo(Panic())
		})
	})
})

// =============================================================================
// Test helpers
// =============================================================================

// recordingObserver records which methods were called.
type recordingObserver struct {
	calls *[]string
}

func (r *recordingObserver) OnTransition(_ context.Context, _, _ CloudflareTunnelState) {
	*r.calls = append(*r.calls, "OnTransition")
}

func (r *recordingObserver) OnTransitionError(_ context.Context, _, _ CloudflareTunnelState, _ error) {
	*r.calls = append(*r.calls, "OnTransitionError")
}

// indexObserver records call order by index.
type indexObserver struct {
	idx   int
	order *[]int
}

func (i *indexObserver) OnTransition(_ context.Context, _, _ CloudflareTunnelState) {
	*i.order = append(*i.order, i.idx)
}

func (i *indexObserver) OnTransitionError(_ context.Context, _, _ CloudflareTunnelState, _ error) {
	*i.order = append(*i.order, i.idx)
}
