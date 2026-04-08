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

	"github.com/cloudflare/cloudflare-go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"github.com/sony/gobreaker"
	"go.opentelemetry.io/otel"
	"golang.org/x/time/rate"
)

var _ = Describe("Coverage gap tests", func() {
	var (
		ctx     context.Context
		client  *TunnelClient
		mockAPI *mockCloudflareAPI
	)

	BeforeEach(func() {
		ctx = context.Background()
		mockAPI = &mockCloudflareAPI{}
		client = &TunnelClient{
			api:            mockAPI,
			limiter:        rate.NewLimiter(rate.Inf, 0),
			circuitBreaker: gobreaker.NewCircuitBreaker(gobreaker.Settings{Name: "test"}),
			tracer:         otel.GetTracerProvider().Tracer("test"),
		}
	})

	// -----------------------------------------------------------------------
	// GetTunnel — does NOT wrap in circuit breaker, unlike CreateTunnel
	// -----------------------------------------------------------------------
	Describe("GetTunnel circuit-breaker independence", func() {
		It("succeeds even when the circuit breaker is in the open state", func() {
			// Trip the circuit breaker by opening it immediately.
			fastTrip := gobreaker.NewCircuitBreaker(gobreaker.Settings{
				Name: "fast-trip",
				ReadyToTrip: func(counts gobreaker.Counts) bool {
					return counts.ConsecutiveFailures >= 1
				},
			})
			// Force the breaker open via a synthetic failure.
			_, _ = fastTrip.Execute(func() (interface{}, error) {
				return nil, &cloudflare.Error{StatusCode: 503}
			})
			client.circuitBreaker = fastTrip

			// GetTunnel does not go through the circuit breaker,
			// so it should still succeed.
			mockAPI.getTunnelFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.Tunnel, error) {
				Expect(rc.Identifier).To(Equal("account-1"))
				Expect(tunnelID).To(Equal("tunnel-xyz"))
				return cloudflare.Tunnel{ID: tunnelID, Name: "my-tunnel"}, nil
			}

			tunnel, err := client.GetTunnel(ctx, "account-1", "tunnel-xyz")
			Expect(err).NotTo(HaveOccurred())
			Expect(tunnel.ID).To(Equal("tunnel-xyz"))
		})
	})

	// -----------------------------------------------------------------------
	// UpdateAccessApplication — additional param coverage
	// -----------------------------------------------------------------------
	Describe("UpdateAccessApplication additional params", func() {
		It("passes CORS headers to the API", func() {
			var gotParams cloudflare.UpdateAccessApplicationParams
			mockAPI.updateAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				gotParams = params
				return cloudflare.AccessApplication{}, nil
			}

			err := client.UpdateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				ID:   "app-id-999",
				Name: "My App",
				CORSHeaders: &AccessCORSConfig{
					AllowAllOrigins:  true,
					AllowedOrigins:   []string{"https://example.com"},
					AllowedMethods:   []string{"GET", "POST"},
					AllowedHeaders:   []string{"Content-Type"},
					AllowCredentials: true,
					MaxAge:           3600,
				},
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(gotParams.CorsHeaders).NotTo(BeNil())
			Expect(gotParams.CorsHeaders.AllowAllOrigins).To(BeTrue())
			Expect(gotParams.CorsHeaders.AllowedOrigins).To(ConsistOf("https://example.com"))
			Expect(gotParams.CorsHeaders.AllowedMethods).To(ConsistOf("GET", "POST"))
			Expect(gotParams.CorsHeaders.AllowedHeaders).To(ConsistOf("Content-Type"))
			Expect(gotParams.CorsHeaders.AllowCredentials).To(BeTrue())
			Expect(gotParams.CorsHeaders.MaxAge).To(Equal(3600))
		})

		It("passes CustomDenyMessage and CustomDenyURL to the API", func() {
			var gotParams cloudflare.UpdateAccessApplicationParams
			mockAPI.updateAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				gotParams = params
				return cloudflare.AccessApplication{}, nil
			}

			err := client.UpdateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				ID:                "app-id-999",
				CustomDenyMessage: "Access denied — contact your admin",
				CustomDenyURL:     "https://example.com/denied",
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(gotParams.CustomDenyMessage).To(Equal("Access denied — contact your admin"))
			Expect(gotParams.CustomDenyURL).To(Equal("https://example.com/denied"))
		})

		It("passes domain, type, session duration, auto-redirect, and binding cookie", func() {
			var gotParams cloudflare.UpdateAccessApplicationParams
			mockAPI.updateAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				gotParams = params
				return cloudflare.AccessApplication{}, nil
			}

			err := client.UpdateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				ID:                     "app-id-999",
				Name:                   "Updated App",
				Domain:                 "updated.example.com",
				Type:                   "self_hosted",
				SessionDuration:        "8h",
				AutoRedirectToIdentity: true,
				EnableBindingCookie:    true,
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(gotParams.Name).To(Equal("Updated App"))
			Expect(gotParams.Domain).To(Equal("updated.example.com"))
			Expect(string(gotParams.Type)).To(Equal("self_hosted"))
			Expect(gotParams.SessionDuration).To(Equal("8h"))
			Expect(gotParams.AutoRedirectToIdentity).NotTo(BeNil())
			Expect(*gotParams.AutoRedirectToIdentity).To(BeTrue())
			Expect(gotParams.EnableBindingCookie).NotTo(BeNil())
			Expect(*gotParams.EnableBindingCookie).To(BeTrue())
		})

		It("does not set CorsHeaders in params when config has no CORS", func() {
			var gotParams cloudflare.UpdateAccessApplicationParams
			mockAPI.updateAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				gotParams = params
				return cloudflare.AccessApplication{}, nil
			}

			err := client.UpdateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				ID:          "app-id-999",
				CORSHeaders: nil,
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(gotParams.CorsHeaders).To(BeNil())
		})
	})

	// -----------------------------------------------------------------------
	// GetAccessApplication — additional field coverage
	// -----------------------------------------------------------------------
	Describe("GetAccessApplication additional fields", func() {
		It("returns CORS headers when the application has them", func() {
			autoRedirect := false
			bindingCookie := false
			mockAPI.getAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id-999",
					Name:                   "My App",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
					CorsHeaders: &cloudflare.AccessApplicationCorsHeaders{
						AllowAllOrigins:  true,
						AllowedOrigins:   []string{"https://trusted.example.com"},
						AllowedMethods:   []string{"GET"},
						AllowCredentials: false,
						MaxAge:           7200,
					},
				}, nil
			}

			config, err := client.GetAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(config.CORSHeaders).NotTo(BeNil())
			Expect(config.CORSHeaders.AllowAllOrigins).To(BeTrue())
			Expect(config.CORSHeaders.AllowedOrigins).To(ConsistOf("https://trusted.example.com"))
			Expect(config.CORSHeaders.AllowedMethods).To(ConsistOf("GET"))
			Expect(config.CORSHeaders.AllowCredentials).To(BeFalse())
			Expect(config.CORSHeaders.MaxAge).To(Equal(7200))
		})

		It("returns nil CORSHeaders when the application has none", func() {
			autoRedirect := false
			bindingCookie := false
			mockAPI.getAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id-999",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
					CorsHeaders:            nil,
				}, nil
			}

			config, err := client.GetAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(config.CORSHeaders).To(BeNil())
		})

		It("returns CustomDenyMessage and CustomDenyURL", func() {
			autoRedirect := false
			bindingCookie := false
			mockAPI.getAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id-999",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
					CustomDenyMessage:      "You shall not pass",
					CustomDenyURL:          "https://example.com/nope",
				}, nil
			}

			config, err := client.GetAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(config.CustomDenyMessage).To(Equal("You shall not pass"))
			Expect(config.CustomDenyURL).To(Equal("https://example.com/nope"))
		})

		It("maps EnableBindingCookie from the application response", func() {
			autoRedirect := false
			bindingCookie := true // true this time
			mockAPI.getAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id-999",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
				}, nil
			}

			config, err := client.GetAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(config.EnableBindingCookie).To(BeTrue())
		})
	})

	// -----------------------------------------------------------------------
	// GetPublishedRoute — path field preservation
	// -----------------------------------------------------------------------
	Describe("GetPublishedRoute path preservation", func() {
		It("returns the route with its path", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "api.example.com", Service: "http://api:9090", Path: "/v1"},
							{Service: "http_status:404"},
						},
					},
				}, nil
			}

			route, err := client.GetPublishedRoute(ctx, "account-123", "tunnel-abc", "api.example.com")
			Expect(err).NotTo(HaveOccurred())
			Expect(route.Hostname).To(Equal("api.example.com"))
			Expect(route.Service).To(Equal("http://api:9090"))
			Expect(route.Path).To(Equal("/v1"))
		})
	})

	// -----------------------------------------------------------------------
	// DeletePublishedRoute — sole route deletion leaves only catch-all
	// -----------------------------------------------------------------------
	Describe("DeletePublishedRoute sole route", func() {
		It("leaves only the catch-all after the sole named route is deleted", func() {
			var capturedParams cloudflare.TunnelConfigurationParams
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "app.example.com", Service: "http://backend:8080"},
							{Service: "http_status:404"},
						},
					},
				}, nil
			}
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				capturedParams = params
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			err := client.DeletePublishedRoute(ctx, "account-123", "tunnel-abc", "app.example.com")
			Expect(err).NotTo(HaveOccurred())

			// Only the catch-all rule should remain.
			Expect(capturedParams.Config.Ingress).To(HaveLen(1))
			Expect(capturedParams.Config.Ingress[0].Hostname).To(BeEmpty())
			Expect(capturedParams.Config.Ingress[0].Service).To(Equal("http_status:404"))
		})
	})

	// -----------------------------------------------------------------------
	// GetDNSRecordByName — multiple records / Proxied field
	// -----------------------------------------------------------------------
	Describe("GetDNSRecordByName extra coverage", func() {
		It("returns the first record when multiple records match the hostname", func() {
			proxied := true
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) { return "zone-123", nil }
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{
					{ID: "record-1", Name: "app.example.com", Type: "CNAME", Content: "tunnel-a.cfargotunnel.com", Proxied: &proxied, TTL: 1},
					{ID: "record-2", Name: "app.example.com", Type: "CNAME", Content: "tunnel-b.cfargotunnel.com", Proxied: &proxied, TTL: 1},
				}, &cloudflare.ResultInfo{}, nil
			}

			config, err := client.GetDNSRecordByName(ctx, "app.example.com")
			Expect(err).NotTo(HaveOccurred())
			// Should return the first record only.
			Expect(config.RecordID).To(Equal("record-1"))
			Expect(config.Content).To(Equal("tunnel-a.cfargotunnel.com"))
		})

		It("maps Proxied=false from the DNS record response", func() {
			proxied := false
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) { return "zone-123", nil }
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{
					{ID: "record-1", Name: "app.example.com", Type: "CNAME", Content: "tunnel-abc.cfargotunnel.com", Proxied: &proxied, TTL: 300},
				}, &cloudflare.ResultInfo{}, nil
			}

			config, err := client.GetDNSRecordByName(ctx, "app.example.com")
			Expect(err).NotTo(HaveOccurred())
			Expect(config.Proxied).To(BeFalse())
			Expect(config.TTL).To(Equal(300))
		})
	})

	// -----------------------------------------------------------------------
	// UpdateDNSRecord — full parameter verification
	// -----------------------------------------------------------------------
	Describe("UpdateDNSRecord full params", func() {
		It("passes Type and TTL to the API", func() {
			var gotParams cloudflare.UpdateDNSRecordParams
			mockAPI.updateDNSRecordFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.UpdateDNSRecordParams) (cloudflare.DNSRecord, error) {
				gotParams = params
				return cloudflare.DNSRecord{}, nil
			}

			err := client.UpdateDNSRecord(ctx, DNSRecordConfig{
				ZoneID:   "zone-123",
				RecordID: "record-999",
				Name:     "app.example.com",
				Type:     "CNAME",
				Content:  "new-tunnel.cfargotunnel.com",
				Proxied:  true,
				TTL:      300,
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(gotParams.Type).To(Equal("CNAME"))
			Expect(gotParams.TTL).To(Equal(300))
			Expect(gotParams.Proxied).NotTo(BeNil())
			Expect(*gotParams.Proxied).To(BeTrue())
		})

		It("passes Proxied=false correctly via BoolPtr", func() {
			var gotParams cloudflare.UpdateDNSRecordParams
			mockAPI.updateDNSRecordFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.UpdateDNSRecordParams) (cloudflare.DNSRecord, error) {
				gotParams = params
				return cloudflare.DNSRecord{}, nil
			}

			err := client.UpdateDNSRecord(ctx, DNSRecordConfig{
				ZoneID:   "zone-123",
				RecordID: "record-999",
				Name:     "app.example.com",
				Type:     "CNAME",
				Content:  "tunnel.cfargotunnel.com",
				Proxied:  false,
				TTL:      1,
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(gotParams.Proxied).NotTo(BeNil())
			Expect(*gotParams.Proxied).To(BeFalse())
		})
	})

	// -----------------------------------------------------------------------
	// ListTunnelDNSRecords — Proxied field mapping
	// -----------------------------------------------------------------------
	Describe("ListTunnelDNSRecords proxied field", func() {
		It("maps Proxied=false from CNAME records pointing to the tunnel", func() {
			proxied := false
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{
					{
						ID:      "record-1",
						Name:    "app.example.com",
						Type:    "CNAME",
						Content: "tunnel-abc.cfargotunnel.com",
						Proxied: &proxied,
						TTL:     300,
					},
				}, &cloudflare.ResultInfo{}, nil
			}

			records, err := client.ListTunnelDNSRecords(ctx, "zone-123", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(records).To(HaveLen(1))
			Expect(records[0].Proxied).To(BeFalse())
			Expect(records[0].TTL).To(Equal(300))
		})

		It("maps ZoneID into each returned record", func() {
			proxied := true
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{
					{ID: "r1", Name: "a.example.com", Type: "CNAME", Content: "tunnel-abc.cfargotunnel.com", Proxied: &proxied, TTL: 1},
					{ID: "r2", Name: "b.example.com", Type: "CNAME", Content: "tunnel-abc.cfargotunnel.com", Proxied: &proxied, TTL: 1},
				}, &cloudflare.ResultInfo{}, nil
			}

			records, err := client.ListTunnelDNSRecords(ctx, "zone-999", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(records).To(HaveLen(2))
			for _, r := range records {
				Expect(r.ZoneID).To(Equal("zone-999"))
			}
		})
	})
})
