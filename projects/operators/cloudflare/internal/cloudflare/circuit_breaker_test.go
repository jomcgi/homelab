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

package cloudflare

import (
	"context"
	"net/http"
	"time"

	"github.com/cloudflare/cloudflare-go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"github.com/sony/gobreaker"
	"go.opentelemetry.io/otel"
	"golang.org/x/time/rate"
)

// newFastTripBreaker returns a circuit breaker that opens after a single
// consecutive failure, making it easy to drive state transitions in tests.
func newFastTripBreaker(timeout time.Duration) *gobreaker.CircuitBreaker {
	return gobreaker.NewCircuitBreaker(gobreaker.Settings{
		Name:    "test-fast-trip",
		Timeout: timeout,
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			return counts.ConsecutiveFailures >= 1
		},
	})
}

var _ = Describe("Circuit breaker state transitions", func() {
	var (
		ctx     context.Context
		mockAPI *mockCloudflareAPI
		tc      *TunnelClient
	)

	BeforeEach(func() {
		ctx = context.Background()
		mockAPI = &mockCloudflareAPI{}
		tc = &TunnelClient{
			api:            mockAPI,
			limiter:        rate.NewLimiter(rate.Inf, 0),
			circuitBreaker: newFastTripBreaker(50 * time.Millisecond),
			tracer:         otel.GetTracerProvider().Tracer("test"),
		}
	})

	// -----------------------------------------------------------------------
	// CLOSED → OPEN transition
	// -----------------------------------------------------------------------

	Describe("CLOSED → OPEN: retryable 5xx error trips the breaker", func() {
		It("trips the circuit after one consecutive 5xx failure", func() {
			retryableErr := &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, retryableErr
			}

			// First call — 5xx is retryable, so the circuit breaker records a failure.
			_, _, err1 := tc.CreateTunnel(ctx, "account-1", "tunnel-1")
			Expect(err1).To(HaveOccurred())

			// The breaker is now OPEN. The next call should return an ErrOpenState
			// without ever reaching the mock.
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				Fail("mock should not be called when breaker is open")
				return cloudflare.Tunnel{}, nil
			}

			_, _, err2 := tc.CreateTunnel(ctx, "account-1", "tunnel-2")
			Expect(err2).To(HaveOccurred())
			// The wrapped error message contains the tunnel name, but the root cause
			// should be gobreaker.ErrOpenState.
			Expect(err2.Error()).To(ContainSubstring("tunnel-2"))
		})

		It("trips the circuit after a 429 Too Many Requests error", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusTooManyRequests}
			}

			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-1")
			Expect(err).To(HaveOccurred())

			// Breaker is now open; subsequent call short-circuits.
			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{}, nil
			}
			_, _, err2 := tc.CreateTunnel(ctx, "account-1", "tunnel-2")
			Expect(err2).To(HaveOccurred())
			Expect(callCount).To(Equal(0), "mock should not be called when breaker is open")
		})
	})

	// -----------------------------------------------------------------------
	// 4xx errors do NOT trip the breaker
	// -----------------------------------------------------------------------

	Describe("4xx errors do not count toward the trip threshold", func() {
		It("does not open the circuit for a 400 Bad Request (non-retryable)", func() {
			// A 400 is non-retryable. CreateTunnel returns (nil, err) to the circuit
			// breaker as a "success" (circuit counts it as non-failure).
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusBadRequest}
			}

			// Fire two 400 errors; the breaker should remain CLOSED.
			for i := 0; i < 2; i++ {
				_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-bad")
				Expect(err).To(HaveOccurred())
			}

			// Now make the API succeed — if the breaker had opened, this would fail
			// with ErrOpenState instead of reaching the mock.
			successCalled := false
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				successCalled = true
				return cloudflare.Tunnel{ID: "new-tunnel"}, nil
			}

			tunnel, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-ok")
			Expect(err).NotTo(HaveOccurred())
			Expect(successCalled).To(BeTrue(), "mock should be reached — breaker must still be CLOSED")
			Expect(tunnel.ID).To(Equal("new-tunnel"))
		})

		It("does not open the circuit for a 404 Not Found (non-retryable)", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusNotFound}
			}

			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-404")
			Expect(err).To(HaveOccurred())

			// Breaker stays CLOSED — next call with success should reach the mock.
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{ID: "tunnel-ok"}, nil
			}

			tunnel, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-ok")
			Expect(err).NotTo(HaveOccurred())
			Expect(tunnel.ID).To(Equal("tunnel-ok"))
		})

		It("does not open the circuit for a 403 Forbidden", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusForbidden}
			}

			// Multiple 403 errors should NOT trip the breaker.
			for i := 0; i < 3; i++ {
				_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-forbidden")
				Expect(err).To(HaveOccurred())
			}

			successCalled := false
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				successCalled = true
				return cloudflare.Tunnel{ID: "tunnel-ok"}, nil
			}
			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-ok")
			Expect(err).NotTo(HaveOccurred())
			Expect(successCalled).To(BeTrue(), "breaker must remain CLOSED after non-retryable 4xx errors")
		})
	})

	// -----------------------------------------------------------------------
	// OPEN → HALF_OPEN → CLOSED transition
	// -----------------------------------------------------------------------

	Describe("OPEN → HALF_OPEN → CLOSED transition", func() {
		It("allows a probe request after the timeout and resets to CLOSED on success", func() {
			// Use a very short timeout (50 ms) set in BeforeEach so we don't slow tests.
			Expect(tc.circuitBreaker).NotTo(BeNil())

			// Trip the breaker.
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusServiceUnavailable}
			}
			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-trip")
			Expect(err).To(HaveOccurred())

			// Breaker is now OPEN. Immediate calls should fail with open-state error.
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{ID: "ok"}, nil
			}
			_, _, errOpen := tc.CreateTunnel(ctx, "account-1", "probe-early")
			Expect(errOpen).To(HaveOccurred(),
				"call during open period should be rejected by circuit breaker")

			// Wait for the breaker timeout (50 ms) to elapse, moving it to HALF_OPEN.
			time.Sleep(100 * time.Millisecond)

			// HALF_OPEN: the next call is a probe. If it succeeds, breaker resets to CLOSED.
			tunnel, _, errHalfOpen := tc.CreateTunnel(ctx, "account-1", "probe-halfopen")
			Expect(errHalfOpen).NotTo(HaveOccurred(),
				"probe call in HALF_OPEN state should be allowed through and succeed")
			Expect(tunnel.ID).To(Equal("ok"))

			// After a successful probe, the breaker is CLOSED again.
			// Further calls should succeed without any circuit-breaker rejection.
			_, _, errClosed := tc.CreateTunnel(ctx, "account-1", "post-reset")
			Expect(errClosed).NotTo(HaveOccurred(),
				"calls after reset should succeed — breaker is CLOSED again")
		})

		It("stays OPEN when the probe in HALF_OPEN state fails with a retryable error", func() {
			// Trip the breaker.
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusBadGateway}
			}
			_, _, _ = tc.CreateTunnel(ctx, "account-1", "trip")

			// Wait for HALF_OPEN.
			time.Sleep(100 * time.Millisecond)

			// Probe in HALF_OPEN fails — breaker goes back to OPEN.
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusBadGateway}
			}
			_, _, errProbe := tc.CreateTunnel(ctx, "account-1", "probe-fail")
			Expect(errProbe).To(HaveOccurred())

			// Breaker is OPEN again — immediate call should be rejected.
			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{}, nil
			}
			_, _, errAfter := tc.CreateTunnel(ctx, "account-1", "after-fail-probe")
			Expect(errAfter).To(HaveOccurred(), "breaker should re-open after failed probe")
			Expect(callCount).To(Equal(0), "mock must not be called when breaker is open")
		})
	})

	// -----------------------------------------------------------------------
	// Mixed errors: 4xx followed by 5xx still trips the breaker
	// -----------------------------------------------------------------------

	Describe("mixed 4xx and 5xx errors", func() {
		It("trips the breaker when a 5xx follows several 4xx errors", func() {
			// Several 4xx errors — breaker stays CLOSED.
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusBadRequest}
			}
			for i := 0; i < 3; i++ {
				_, _, _ = tc.CreateTunnel(ctx, "account-1", "tunnel-4xx")
			}

			// Now a single 5xx trips the breaker.
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			}
			_, _, err5xx := tc.CreateTunnel(ctx, "account-1", "tunnel-5xx")
			Expect(err5xx).To(HaveOccurred())

			// Breaker is now OPEN.
			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{}, nil
			}
			_, _, errOpen := tc.CreateTunnel(ctx, "account-1", "should-be-blocked")
			Expect(errOpen).To(HaveOccurred())
			Expect(callCount).To(Equal(0))
		})
	})
})
