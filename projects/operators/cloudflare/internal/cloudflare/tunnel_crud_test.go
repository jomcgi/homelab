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
	"fmt"
	"net/http"

	"github.com/cloudflare/cloudflare-go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"github.com/sony/gobreaker"
	"go.opentelemetry.io/otel"
	"golang.org/x/time/rate"
)

// newTestTunnelClient returns a TunnelClient backed by a mock API,
// with an unlimited rate limiter and a default circuit breaker.
func newTestTunnelClient(mock *mockCloudflareAPI) *TunnelClient {
	return &TunnelClient{
		api:            mock,
		limiter:        rate.NewLimiter(rate.Inf, 0),
		circuitBreaker: gobreaker.NewCircuitBreaker(gobreaker.Settings{Name: "test"}),
		tracer:         otel.GetTracerProvider().Tracer("test"),
	}
}

var _ = Describe("TunnelClient tunnel CRUD", func() {
	var (
		ctx     context.Context
		tc      *TunnelClient
		mockAPI *mockCloudflareAPI
	)

	BeforeEach(func() {
		ctx = context.Background()
		mockAPI = &mockCloudflareAPI{}
		tc = newTestTunnelClient(mockAPI)
	})

	Describe("CreateTunnel", func() {
		It("returns the created tunnel and a non-empty secret on success", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				Expect(params.Name).To(Equal("my-tunnel"))
				Expect(params.Secret).NotTo(BeEmpty())
				return cloudflare.Tunnel{ID: "tunnel-abc", Name: params.Name}, nil
			}

			tunnel, secret, err := tc.CreateTunnel(ctx, "account-1", "my-tunnel")
			Expect(err).NotTo(HaveOccurred())
			Expect(tunnel).NotTo(BeNil())
			Expect(tunnel.ID).To(Equal("tunnel-abc"))
			Expect(tunnel.Name).To(Equal("my-tunnel"))
			Expect(secret).NotTo(BeEmpty())
		})

		It("generates a unique secret on each call", func() {
			var receivedSecrets []string
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				receivedSecrets = append(receivedSecrets, params.Secret)
				return cloudflare.Tunnel{ID: "t-" + params.Name}, nil
			}

			_, secret1, err := tc.CreateTunnel(ctx, "account-1", "tunnel-1")
			Expect(err).NotTo(HaveOccurred())
			_, secret2, err := tc.CreateTunnel(ctx, "account-1", "tunnel-2")
			Expect(err).NotTo(HaveOccurred())
			Expect(secret1).NotTo(Equal(secret2), "each call should generate a unique random secret")
		})

		It("returns an error wrapping the tunnel name on API failure", func() {
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			}

			_, _, err := tc.CreateTunnel(ctx, "account-1", "my-tunnel")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("my-tunnel"))
		})

		It("returns a circuit-breaker error after the breaker opens", func() {
			// Use a breaker that opens on the very first failure.
			tc.circuitBreaker = gobreaker.NewCircuitBreaker(gobreaker.Settings{
				Name: "fast-trip",
				ReadyToTrip: func(counts gobreaker.Counts) bool {
					return counts.ConsecutiveFailures >= 1
				},
			})

			retryableErr := &cloudflare.Error{StatusCode: http.StatusServiceUnavailable}
			mockAPI.createTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, retryableErr
			}

			// First call — fails, trips the breaker.
			_, _, err := tc.CreateTunnel(ctx, "account-1", "tunnel-1")
			Expect(err).To(HaveOccurred())

			// Second call — breaker should now be open.
			_, _, err = tc.CreateTunnel(ctx, "account-1", "tunnel-2")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnel-2"))
		})
	})

	Describe("GetTunnel", func() {
		It("returns tunnel information on success", func() {
			mockAPI.getTunnelFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.Tunnel, error) {
				Expect(tunnelID).To(Equal("tunnel-abc"))
				Expect(rc.Identifier).To(Equal("account-1"))
				return cloudflare.Tunnel{ID: tunnelID, Name: "my-tunnel"}, nil
			}

			tunnel, err := tc.GetTunnel(ctx, "account-1", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(tunnel).NotTo(BeNil())
			Expect(tunnel.ID).To(Equal("tunnel-abc"))
			Expect(tunnel.Name).To(Equal("my-tunnel"))
		})

		It("wraps API error with the tunnel ID", func() {
			mockAPI.getTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.Tunnel, error) {
				return cloudflare.Tunnel{}, &cloudflare.Error{StatusCode: http.StatusNotFound}
			}

			_, err := tc.GetTunnel(ctx, "account-1", "tunnel-abc")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnel-abc"))
		})
	})

	Describe("ListTunnels", func() {
		It("returns all tunnels on success", func() {
			mockAPI.listTunnelsFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, _ cloudflare.TunnelListParams) ([]cloudflare.Tunnel, *cloudflare.ResultInfo, error) {
				Expect(rc.Identifier).To(Equal("account-1"))
				return []cloudflare.Tunnel{
					{ID: "t1", Name: "tunnel-1"},
					{ID: "t2", Name: "tunnel-2"},
				}, &cloudflare.ResultInfo{}, nil
			}

			tunnels, err := tc.ListTunnels(ctx, "account-1")
			Expect(err).NotTo(HaveOccurred())
			Expect(tunnels).To(HaveLen(2))
			Expect(tunnels[0].ID).To(Equal("t1"))
			Expect(tunnels[1].ID).To(Equal("t2"))
		})

		It("returns an empty slice when no tunnels exist", func() {
			mockAPI.listTunnelsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelListParams) ([]cloudflare.Tunnel, *cloudflare.ResultInfo, error) {
				return []cloudflare.Tunnel{}, &cloudflare.ResultInfo{}, nil
			}

			tunnels, err := tc.ListTunnels(ctx, "account-1")
			Expect(err).NotTo(HaveOccurred())
			Expect(tunnels).To(BeEmpty())
		})

		It("wraps API error with a descriptive message", func() {
			mockAPI.listTunnelsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelListParams) ([]cloudflare.Tunnel, *cloudflare.ResultInfo, error) {
				return nil, nil, &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			}

			_, err := tc.ListTunnels(ctx, "account-1")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to list tunnels"))
		})
	})

	Describe("DeleteTunnel", func() {
		It("deletes the tunnel successfully", func() {
			deleted := false
			mockAPI.deleteTunnelFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, tunnelID string) error {
				Expect(tunnelID).To(Equal("tunnel-abc"))
				Expect(rc.Identifier).To(Equal("account-1"))
				deleted = true
				return nil
			}

			err := tc.DeleteTunnel(ctx, "account-1", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(deleted).To(BeTrue())
		})

		It("wraps API error with the tunnel ID", func() {
			mockAPI.deleteTunnelFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) error {
				return &cloudflare.Error{StatusCode: http.StatusNotFound}
			}

			err := tc.DeleteTunnel(ctx, "account-1", "tunnel-abc")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnel-abc"))
		})
	})

	Describe("UpdateTunnelConfiguration", func() {
		It("passes the correct tunnel ID and configuration to the API", func() {
			var gotParams cloudflare.TunnelConfigurationParams
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				gotParams = params
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			cfg := cloudflare.TunnelConfiguration{
				Ingress: []cloudflare.UnvalidatedIngressRule{
					{Hostname: "app.example.com", Service: "http://localhost:8080"},
				},
			}

			err := tc.UpdateTunnelConfiguration(ctx, "account-1", "tunnel-abc", cfg)
			Expect(err).NotTo(HaveOccurred())
			Expect(gotParams.TunnelID).To(Equal("tunnel-abc"))
			Expect(gotParams.Config.Ingress).To(HaveLen(1))
			Expect(gotParams.Config.Ingress[0].Hostname).To(Equal("app.example.com"))
		})

		It("wraps API error with the tunnel ID", func() {
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, fmt.Errorf("upstream error")
			}

			err := tc.UpdateTunnelConfiguration(ctx, "account-1", "tunnel-abc", cloudflare.TunnelConfiguration{})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnel-abc"))
		})
	})

	Describe("GetTunnelToken", func() {
		It("returns the tunnel token on success", func() {
			mockAPI.getTunnelTokenFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (string, error) {
				Expect(tunnelID).To(Equal("tunnel-abc"))
				Expect(rc.Identifier).To(Equal("account-1"))
				return "eyJhbGci-secret-token", nil
			}

			token, err := tc.GetTunnelToken(ctx, "account-1", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(token).To(Equal("eyJhbGci-secret-token"))
		})

		It("wraps API error with the tunnel ID", func() {
			mockAPI.getTunnelTokenFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (string, error) {
				return "", &cloudflare.Error{StatusCode: http.StatusUnauthorized}
			}

			_, err := tc.GetTunnelToken(ctx, "account-1", "tunnel-abc")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("tunnel-abc"))
		})
	})
})
