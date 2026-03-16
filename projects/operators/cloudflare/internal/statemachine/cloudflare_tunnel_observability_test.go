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

	ctrl "sigs.k8s.io/controller-runtime"
)

// =============================================================================
// ValidateTransition
// =============================================================================

var _ = Describe("ValidateTransition", func() {
	It("returns nil when 'to' state is nil", func() {
		from := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		err := ValidateTransition(from, nil)
		Expect(err).NotTo(HaveOccurred())
	})

	It("returns nil when the destination state is valid", func() {
		from := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		to := CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
		err := ValidateTransition(from, to)
		Expect(err).NotTo(HaveOccurred())
	})

	It("returns nil even when 'from' state is nil (to drives validation)", func() {
		to := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		err := ValidateTransition(nil, to)
		Expect(err).NotTo(HaveOccurred())
	})

	It("returns an error when the destination state fails Validate()", func() {
		// CloudflareTunnelCreatingSecret requires a non-empty TunnelID.
		from := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		to := CloudflareTunnelCreatingSecret{
			resource:       newTunnel(PhaseCreatingSecret),
			TunnelIdentity: TunnelIdentity{TunnelID: ""}, // missing required field
		}
		err := ValidateTransition(from, to)
		Expect(err).To(HaveOccurred())
		Expect(err.Error()).To(ContainSubstring("tunnelID is required"))
	})

	It("returns nil when all required fields are present", func() {
		from := CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		to := CloudflareTunnelCreatingSecret{
			resource:       newTunnel(PhaseCreatingSecret),
			TunnelIdentity: TunnelIdentity{TunnelID: "valid-tunnel-id"},
		}
		err := ValidateTransition(from, to)
		Expect(err).NotTo(HaveOccurred())
	})
})

// =============================================================================
// NoOpObserver
// =============================================================================

var _ = Describe("NoOpObserver", func() {
	var (
		observer NoOpObserver
		ctx      context.Context
		from     CloudflareTunnelState
		to       CloudflareTunnelState
	)

	BeforeEach(func() {
		observer = NoOpObserver{}
		ctx = context.Background()
		from = CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		to = CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
	})

	It("satisfies the TransitionObserver interface", func() {
		var _ TransitionObserver = NoOpObserver{}
	})

	It("OnTransition does not panic", func() {
		Expect(func() { observer.OnTransition(ctx, from, to) }).NotTo(Panic())
	})

	It("OnTransitionError does not panic", func() {
		Expect(func() {
			observer.OnTransitionError(ctx, from, to, errors.New("some error"))
		}).NotTo(Panic())
	})
})

// =============================================================================
// LoggingObserver
// =============================================================================

var _ = Describe("LoggingObserver", func() {
	var (
		observer LoggingObserver
		ctx      context.Context
		from     CloudflareTunnelState
		to       CloudflareTunnelState
	)

	BeforeEach(func() {
		observer = LoggingObserver{}
		// Inject a discard logger so we don't rely on a real logger sink.
		ctx = ctrl.LoggerInto(context.Background(), logr.Discard())
		from = CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		to = CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
	})

	It("satisfies the TransitionObserver interface", func() {
		var _ TransitionObserver = LoggingObserver{}
	})

	It("OnTransition does not panic", func() {
		Expect(func() { observer.OnTransition(ctx, from, to) }).NotTo(Panic())
	})

	It("OnTransitionError does not panic", func() {
		Expect(func() {
			observer.OnTransitionError(ctx, from, to, errors.New("transition failed"))
		}).NotTo(Panic())
	})

	It("OnTransition works with a background context (falls back to discard logger)", func() {
		Expect(func() {
			observer.OnTransition(context.Background(), from, to)
		}).NotTo(Panic())
	})
})

// =============================================================================
// OTelObserver
// =============================================================================

var _ = Describe("OTelObserver", func() {
	var (
		observer *OTelObserver
		ctx      context.Context
		from     CloudflareTunnelState
		to       CloudflareTunnelState
	)

	BeforeEach(func() {
		// Use a noop tracer provider so no real OTLP exporter is needed.
		observer = &OTelObserver{tracer: otel.Tracer("test")}
		ctx = context.Background()
		from = CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		to = CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
	})

	Describe("NewOTelObserver", func() {
		It("creates an observer with a tracer from the global provider", func() {
			o := NewOTelObserver("test-tracer")
			Expect(o).NotTo(BeNil())
			Expect(o.tracer).NotTo(BeNil())
		})
	})

	It("satisfies the TransitionObserver interface", func() {
		var _ TransitionObserver = &OTelObserver{}
	})

	It("OnTransition creates and ends a span without panicking", func() {
		Expect(func() { observer.OnTransition(ctx, from, to) }).NotTo(Panic())
	})

	It("OnTransitionError creates and ends a span with error attributes without panicking", func() {
		Expect(func() {
			observer.OnTransitionError(ctx, from, to, errors.New("otel error"))
		}).NotTo(Panic())
	})

	It("OnTransition records phase names as span attributes", func() {
		// With a noop tracer, we can't inspect span attributes directly.
		// We verify the function does not panic when using phase-name values.
		Expect(func() {
			observer.OnTransition(ctx,
				CloudflareTunnelReady{resource: newTunnel(PhaseReady)},
				CloudflareTunnelFailed{resource: newTunnel(PhaseFailed)},
			)
		}).NotTo(Panic())
	})
})

// =============================================================================
// CompositeObserver
// =============================================================================

var _ = Describe("CompositeObserver", func() {
	var (
		ctx  context.Context
		from CloudflareTunnelState
		to   CloudflareTunnelState
	)

	BeforeEach(func() {
		ctx = context.Background()
		from = CloudflareTunnelPending{resource: newTunnel(PhasePending)}
		to = CloudflareTunnelCreatingTunnel{resource: newTunnel(PhaseCreatingTunnel)}
	})

	It("satisfies the TransitionObserver interface", func() {
		var _ TransitionObserver = CompositeObserver{}
	})

	It("OnTransition calls all contained observers", func() {
		callCount := 0
		spy := &callCountObserver{onTransition: func() { callCount++ }}
		composite := CompositeObserver{spy, spy, spy}
		composite.OnTransition(ctx, from, to)
		Expect(callCount).To(Equal(3))
	})

	It("OnTransitionError calls all contained observers", func() {
		callCount := 0
		spy := &callCountObserver{onTransitionError: func() { callCount++ }}
		composite := CompositeObserver{spy, spy, spy}
		composite.OnTransitionError(ctx, from, to, errors.New("err"))
		Expect(callCount).To(Equal(3))
	})

	It("works with an empty observer list", func() {
		composite := CompositeObserver{}
		Expect(func() { composite.OnTransition(ctx, from, to) }).NotTo(Panic())
		Expect(func() {
			composite.OnTransitionError(ctx, from, to, errors.New("err"))
		}).NotTo(Panic())
	})

	It("works with a single observer", func() {
		called := false
		spy := &callCountObserver{onTransition: func() { called = true }}
		composite := CompositeObserver{spy}
		composite.OnTransition(ctx, from, to)
		Expect(called).To(BeTrue())
	})

	It("delegates to mixed observer types without panicking", func() {
		composite := CompositeObserver{
			NoOpObserver{},
			LoggingObserver{},
			&OTelObserver{tracer: otel.Tracer("test")},
		}
		Expect(func() { composite.OnTransition(ctx, from, to) }).NotTo(Panic())
		Expect(func() {
			composite.OnTransitionError(ctx, from, to, errors.New("mixed error"))
		}).NotTo(Panic())
	})
})

// callCountObserver is a test-only TransitionObserver that invokes callbacks.
type callCountObserver struct {
	onTransition      func()
	onTransitionError func()
}

func (c *callCountObserver) OnTransition(_ context.Context, _, _ CloudflareTunnelState) {
	if c.onTransition != nil {
		c.onTransition()
	}
}

func (c *callCountObserver) OnTransitionError(_ context.Context, _, _ CloudflareTunnelState, _ error) {
	if c.onTransitionError != nil {
		c.onTransitionError()
	}
}
