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

// cancelledCtx returns a context that is already cancelled so that the rate
// limiter's Wait call returns an error immediately.
func cancelledCtx() context.Context {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	return ctx
}

var _ = Describe("Rate-limiter error paths (cancelled context)", func() {
	var (
		mockAPI *mockCloudflareAPI
		tc      *TunnelClient
	)

	BeforeEach(func() {
		mockAPI = &mockCloudflareAPI{}
		tc = &TunnelClient{
			api:            mockAPI,
			limiter:        rate.NewLimiter(rate.Inf, 0),
			circuitBreaker: gobreaker.NewCircuitBreaker(gobreaker.Settings{Name: "test"}),
			tracer:         otel.GetTracerProvider().Tracer("test"),
		}
	})

	// ── client.go methods ───────────────────────────────────────────────────

	Describe("CreateTunnel", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, _, err := tc.CreateTunnel(cancelledCtx(), "account-1", "my-tunnel")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("GetTunnel", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.GetTunnel(cancelledCtx(), "account-1", "tunnel-abc")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("ListTunnels", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.ListTunnels(cancelledCtx(), "account-1")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("DeleteTunnel", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.DeleteTunnel(cancelledCtx(), "account-1", "tunnel-abc")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("UpdateTunnelConfiguration", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.UpdateTunnelConfiguration(cancelledCtx(), "account-1", "tunnel-abc", cloudflare.TunnelConfiguration{})
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("GetTunnelToken", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.GetTunnelToken(cancelledCtx(), "account-1", "tunnel-abc")
			Expect(err).To(HaveOccurred())
		})
	})

	// ── dns.go methods ───────────────────────────────────────────────────────

	Describe("CreateTunnelDNSRecord", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.CreateTunnelDNSRecord(cancelledCtx(), "app.example.com", "tunnel-abc")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("DeleteDNSRecord", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.DeleteDNSRecord(cancelledCtx(), "zone-123", "record-999")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("GetDNSRecordByName", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.GetDNSRecordByName(cancelledCtx(), "app.example.com")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("ListTunnelDNSRecords", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.ListTunnelDNSRecords(cancelledCtx(), "zone-123", "tunnel-abc")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("UpdateDNSRecord", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.UpdateDNSRecord(cancelledCtx(), DNSRecordConfig{ZoneID: "zone-123", RecordID: "record-999"})
			Expect(err).To(HaveOccurred())
		})
	})

	// ── routes.go methods ────────────────────────────────────────────────────

	Describe("CreatePublishedRoute", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.CreatePublishedRoute(cancelledCtx(), "account-1", "tunnel-abc", RouteConfig{
				Hostname: "app.example.com",
				Service:  "http://backend:8080",
			})
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("DeletePublishedRoute", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.DeletePublishedRoute(cancelledCtx(), "account-1", "tunnel-abc", "app.example.com")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("ListPublishedRoutes", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.ListPublishedRoutes(cancelledCtx(), "account-1", "tunnel-abc")
			Expect(err).To(HaveOccurred())
		})
	})

	// GetPublishedRoute delegates to ListPublishedRoutes; the limiter error
	// propagates through that call.
	Describe("GetPublishedRoute", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.GetPublishedRoute(cancelledCtx(), "account-1", "tunnel-abc", "app.example.com")
			Expect(err).To(HaveOccurred())
		})
	})

	// ── access.go methods ────────────────────────────────────────────────────

	Describe("CreateAccessApplication", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.CreateAccessApplication(cancelledCtx(), "account-1", AccessApplicationConfig{Name: "App"})
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("UpdateAccessApplication", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.UpdateAccessApplication(cancelledCtx(), "account-1", AccessApplicationConfig{ID: "app-1"})
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("DeleteAccessApplication", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.DeleteAccessApplication(cancelledCtx(), "account-1", "app-1")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("GetAccessApplication", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.GetAccessApplication(cancelledCtx(), "account-1", "app-1")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("CreateAccessPolicy", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.CreateAccessPolicy(cancelledCtx(), "account-1", AccessPolicyConfig{
				ApplicationID: "app-1",
				Name:          "Policy",
				Decision:      "allow",
			})
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("DeleteAccessPolicy", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			err := tc.DeleteAccessPolicy(cancelledCtx(), "account-1", "app-1", "policy-1")
			Expect(err).To(HaveOccurred())
		})
	})

	Describe("ListAccessPolicies", func() {
		It("returns an error when the context is cancelled before the rate limiter", func() {
			_, err := tc.ListAccessPolicies(cancelledCtx(), "account-1", "app-1")
			Expect(err).To(HaveOccurred())
		})
	})
})

var _ = Describe("CreateAccessPolicy Exclude/Require rule branches", func() {
	var (
		ctx     context.Context
		mockAPI *mockCloudflareAPI
		tc      *TunnelClient
	)

	BeforeEach(func() {
		ctx = context.Background()
		mockAPI = &mockCloudflareAPI{}
		tc = &TunnelClient{
			api:     mockAPI,
			limiter: rate.NewLimiter(rate.Inf, 0),
			tracer:  otel.GetTracerProvider().Tracer("test"),
		}
	})

	It("passes non-empty Exclude rules to the API", func() {
		var capturedParams cloudflare.CreateAccessPolicyParams
		mockAPI.createAccessPolicyFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.CreateAccessPolicyParams) (cloudflare.AccessPolicy, error) {
			capturedParams = params
			return cloudflare.AccessPolicy{ID: "pol-1", Name: params.Name, Decision: "allow"}, nil
		}

		_, err := tc.CreateAccessPolicy(ctx, "account-1", AccessPolicyConfig{
			ApplicationID: "app-1",
			Name:          "Policy with exclusions",
			Decision:      "allow",
			Include: []AccessPolicyRule{
				{Everyone: true},
			},
			Exclude: []AccessPolicyRule{
				{Emails: []string{"blocked@example.com"}},
			},
		})
		Expect(err).NotTo(HaveOccurred())
		Expect(capturedParams.Exclude).NotTo(BeEmpty())
	})

	It("passes non-empty Require rules to the API", func() {
		var capturedParams cloudflare.CreateAccessPolicyParams
		mockAPI.createAccessPolicyFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.CreateAccessPolicyParams) (cloudflare.AccessPolicy, error) {
			capturedParams = params
			return cloudflare.AccessPolicy{ID: "pol-2", Name: params.Name, Decision: "allow"}, nil
		}

		_, err := tc.CreateAccessPolicy(ctx, "account-1", AccessPolicyConfig{
			ApplicationID: "app-1",
			Name:          "Policy with requirements",
			Decision:      "allow",
			Include: []AccessPolicyRule{
				{Everyone: true},
			},
			Require: []AccessPolicyRule{
				{Countries: []string{"US"}},
			},
		})
		Expect(err).NotTo(HaveOccurred())
		Expect(capturedParams.Require).NotTo(BeEmpty())
	})

	It("leaves Exclude and Require nil when the slices are empty", func() {
		var capturedParams cloudflare.CreateAccessPolicyParams
		mockAPI.createAccessPolicyFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.CreateAccessPolicyParams) (cloudflare.AccessPolicy, error) {
			capturedParams = params
			return cloudflare.AccessPolicy{ID: "pol-3", Name: params.Name, Decision: "allow"}, nil
		}

		_, err := tc.CreateAccessPolicy(ctx, "account-1", AccessPolicyConfig{
			ApplicationID: "app-1",
			Name:          "Policy without extras",
			Decision:      "allow",
			Include: []AccessPolicyRule{
				{Everyone: true},
			},
		})
		Expect(err).NotTo(HaveOccurred())
		Expect(capturedParams.Exclude).To(BeNil())
		Expect(capturedParams.Require).To(BeNil())
	})
})
