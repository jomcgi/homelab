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

// Package cloudflare — circuit breaker behaviour tests.
//
// NOTE on the 4xx / non-retryable error behaviour:
//
// The comment in client.go's CreateTunnel says:
//
//	// Non-retryable errors (4xx) return error but don't affect circuit state
//
// However, the implementation returns (nil, err) unconditionally for all
// errors — gobreaker treats any non-nil error return from Execute as a
// failure regardless of the error type.  As a result, 4xx errors currently
// DO trip the circuit breaker, contrary to the stated intent.
//
// The tests below pin the ACTUAL current behaviour.  A fix would require
// returning (resultCarryingErr, nil) from the Execute closure for non-retryable
// errors so that gobreaker does not count them as failures.
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
	// CLOSED → OPEN transition: retryable 5xx errors trip the breaker
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
			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{}, nil
			}

			_, _, err2 := tc.CreateTunnel(ctx, "account-1", "tunnel-2")
			Expect(err2).To(HaveOccurred())
			Expect(callCount).To(Equal(0), "mock should not be called when breaker is open")
			// The wrapped error message contains the tunnel name.
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

		It("trips the circuit after a 502 Bad Gateway error", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusBadGateway}
			}

			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-1")
			Expect(err).To(HaveOccurred())

			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{}, nil
			}
			_, _, err2 := tc.CreateTunnel(ctx, "account-1", "tunnel-2")
			Expect(err2).To(HaveOccurred())
			Expect(callCount).To(Equal(0))
		})
	})

	// -----------------------------------------------------------------------
	// 4xx errors — current actual behaviour
	//
	// Despite the comment in client.go, the current implementation returns
	// (nil, err) unconditionally, so gobreaker counts 4xx errors as failures
	// and the circuit opens.  These tests pin that behaviour.
	// -----------------------------------------------------------------------

	Describe("4xx errors — actual current behaviour (breaker is tripped)", func() {
		// BUG: The comment in CreateTunnel says non-retryable 4xx errors should
		// NOT count as circuit-breaker failures, but the implementation returns
		// (nil, err) to gobreaker which counts every non-nil error as a failure.
		// These tests document the current (buggy) behaviour.

		It("trips the breaker after a single 400 Bad Request (current behaviour)", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusBadRequest}
			}

			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-bad")
			Expect(err).To(HaveOccurred())

			// Breaker is now OPEN (contrary to the comment in production code).
			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{}, nil
			}
			_, _, err2 := tc.CreateTunnel(ctx, "account-1", "tunnel-ok")
			Expect(err2).To(HaveOccurred(),
				"breaker IS opened by 4xx in current implementation (known bug)")
			Expect(callCount).To(Equal(0))
		})

		It("trips the breaker after a 404 Not Found", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusNotFound}
			}

			_, _, _ = tc.CreateTunnel(ctx, "account-1", "tunnel-404")

			// Breaker is OPEN.
			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{}, nil
			}
			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-ok")
			Expect(err).To(HaveOccurred(),
				"breaker IS opened by 404 in current implementation (known bug)")
			Expect(callCount).To(Equal(0))
		})

		It("trips the breaker after a 403 Forbidden", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusForbidden}
			}

			_, _, _ = tc.CreateTunnel(ctx, "account-1", "tunnel-forbidden")

			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{}, nil
			}
			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-ok")
			Expect(err).To(HaveOccurred(),
				"breaker IS opened by 403 in current implementation (known bug)")
			Expect(callCount).To(Equal(0))
		})
	})

	// -----------------------------------------------------------------------
	// OPEN → HALF_OPEN → CLOSED transition
	// -----------------------------------------------------------------------

	Describe("OPEN → HALF_OPEN → CLOSED transition", func() {
		It("allows a probe request after the timeout and resets to CLOSED on success", func() {
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
	// Success path: breaker stays CLOSED when all calls succeed
	// -----------------------------------------------------------------------

	Describe("CLOSED state is maintained on success", func() {
		It("stays CLOSED after multiple successful calls", func() {
			callCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				callCount++
				return cloudflare.Tunnel{ID: "t-" + params.Name}, nil
			}

			for i := 0; i < 5; i++ {
				_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-ok")
				Expect(err).NotTo(HaveOccurred())
			}

			Expect(callCount).To(Equal(5), "all 5 calls should reach the mock — breaker is CLOSED")
		})
	})

	// -----------------------------------------------------------------------
	// Production ReadyToTrip threshold: ConsecutiveFailures >= 5
	//
	// NewTunnelClient creates a circuit breaker with threshold 5. All other
	// tests use a fast-trip breaker (threshold 1) for convenience. These tests
	// verify the production threshold directly by calling NewTunnelClient and
	// swapping in the mock API.
	// -----------------------------------------------------------------------

	Describe("ReadyToTrip production threshold = 5 (NewTunnelClient settings)", func() {
		var productionClient *TunnelClient

		BeforeEach(func() {
			// Create a client using the production NewTunnelClient, which
			// configures a circuit breaker with ConsecutiveFailures >= 5.
			// Then swap in the test mock and remove rate limiting.
			var err error
			productionClient, err = NewTunnelClient("test-token-threshold")
			Expect(err).NotTo(HaveOccurred())
			productionClient.api = mockAPI
			productionClient.limiter = rate.NewLimiter(rate.Inf, 0)
		})

		It("keeps the circuit CLOSED after 4 consecutive retryable failures", func() {
			retryableErr := &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, retryableErr
			}

			// 4 consecutive retryable failures — threshold not yet reached.
			for _, name := range []string{"t-fail-1", "t-fail-2", "t-fail-3", "t-fail-4"} {
				_, _, err := productionClient.CreateTunnel(ctx, "account-1", name)
				Expect(err).To(HaveOccurred())
			}

			// Switch mock to succeed. If circuit is CLOSED the call goes through.
			reachCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				reachCount++
				return cloudflare.Tunnel{ID: "ok"}, nil
			}

			_, _, err := productionClient.CreateTunnel(ctx, "account-1", "probe-after-4")
			Expect(err).NotTo(HaveOccurred(),
				"circuit must still be CLOSED after only 4 consecutive failures (threshold is 5)")
			Expect(reachCount).To(Equal(1), "mock must be reached — circuit is CLOSED")
		})

		It("opens the circuit after exactly 5 consecutive retryable failures", func() {
			retryableErr := &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, retryableErr
			}

			// 5 consecutive retryable failures — exactly at the threshold.
			for _, name := range []string{"t-fail-1", "t-fail-2", "t-fail-3", "t-fail-4", "t-fail-5"} {
				_, _, err := productionClient.CreateTunnel(ctx, "account-1", name)
				Expect(err).To(HaveOccurred())
			}

			// Circuit is now OPEN. The next call must not reach the mock.
			reachCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				reachCount++
				return cloudflare.Tunnel{}, nil
			}

			_, _, errOpen := productionClient.CreateTunnel(ctx, "account-1", "post-5-failures")
			Expect(errOpen).To(HaveOccurred(),
				"circuit must be OPEN after exactly 5 consecutive failures")
			Expect(reachCount).To(Equal(0),
				"mock must NOT be reached when circuit is open")
		})

		It("requires consecutive failures — a success resets the count", func() {
			retryableErr := &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			failCount := 0

			// Alternate fail / succeed: 4 failures, then 1 success, then 4 more
			// failures. Circuit should never open because the run of consecutive
			// failures never reaches 5.
			for call := 0; call < 9; call++ {
				if call == 4 {
					// Success resets the consecutive failure count.
					mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
						return cloudflare.Tunnel{ID: "reset"}, nil
					}
					_, _, err := productionClient.CreateTunnel(ctx, "account-1", "reset-call")
					Expect(err).NotTo(HaveOccurred())
				} else {
					mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
						failCount++
						return cloudflare.Tunnel{}, retryableErr
					}
					_, _, err := productionClient.CreateTunnel(ctx, "account-1", "fail-call")
					Expect(err).To(HaveOccurred())
				}
			}

			// After 4 + reset + 4 failures (8 failures total, max 4 consecutive),
			// the circuit must still be CLOSED.
			reachCount := 0
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				reachCount++
				return cloudflare.Tunnel{ID: "still-closed"}, nil
			}

			_, _, err := productionClient.CreateTunnel(ctx, "account-1", "final-probe")
			Expect(err).NotTo(HaveOccurred(),
				"circuit should be CLOSED — 4 consecutive failures then a reset never reaches threshold 5")
			Expect(reachCount).To(Equal(1))
		})
	})
})
