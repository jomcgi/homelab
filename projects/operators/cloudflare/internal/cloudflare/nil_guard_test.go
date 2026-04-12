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

// Package cloudflare — nil-pointer guard tests.
//
// These tests document the behaviour of production code when the Cloudflare
// API returns structs whose pointer fields (Proxied, AutoRedirectToIdentity,
// EnableBindingCookie) are nil.  In the current implementation those fields
// are dereferenced unconditionally, which would cause a runtime panic if the
// API ever omits them.
//
// Each test is wrapped in a recover block (via Gomega's Panic matcher) so the
// test suite itself does not crash.  Fixing the underlying production-code
// panics is tracked separately; these tests exist to pin the current behaviour
// and make any future fix visible.
package cloudflare

import (
	"context"

	"github.com/cloudflare/cloudflare-go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"go.opentelemetry.io/otel"
	"golang.org/x/time/rate"
)

var _ = Describe("Nil-pointer guard — dns.go", func() {
	var (
		ctx     context.Context
		client  *TunnelClient
		mockAPI *mockCloudflareAPI
	)

	BeforeEach(func() {
		ctx = context.Background()
		mockAPI = &mockCloudflareAPI{}
		client = &TunnelClient{
			api:     mockAPI,
			limiter: rate.NewLimiter(rate.Inf, 0),
			tracer:  otel.GetTracerProvider().Tracer("test"),
		}
	})

	// -----------------------------------------------------------------
	// GetDNSRecordByName: dereferences record.Proxied unconditionally
	// -----------------------------------------------------------------

	Describe("GetDNSRecordByName with nil Proxied field", func() {
		It("panics when the API returns a DNSRecord with a nil Proxied pointer", func() {
			// The Cloudflare API may omit the Proxied field for certain record
			// types. Production code at dns.go currently dereferences the pointer
			// without a nil check, causing a panic.
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) {
				return "zone-123", nil
			}
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{
					{
						ID:      "record-nil-proxied",
						Name:    "app.example.com",
						Type:    "CNAME",
						Content: "tunnel-abc.cfargotunnel.com",
						Proxied: nil, // nil pointer — the current code will panic here
						TTL:     1,
					},
				}, &cloudflare.ResultInfo{}, nil
			}

			Expect(func() {
				_, _ = client.GetDNSRecordByName(ctx, "app.example.com")
			}).To(Panic(), "GetDNSRecordByName panics when record.Proxied is nil (known bug)")
		})
	})

	// -----------------------------------------------------------------
	// ListTunnelDNSRecords: same unconditional dereference
	// -----------------------------------------------------------------

	Describe("ListTunnelDNSRecords with nil Proxied field", func() {
		It("panics when a matched CNAME record has a nil Proxied pointer", func() {
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{
					{
						ID:      "record-nil-proxied",
						Name:    "app.example.com",
						Type:    "CNAME",
						Content: "tunnel-abc.cfargotunnel.com",
						Proxied: nil, // nil pointer — the current code will panic here
						TTL:     1,
					},
				}, &cloudflare.ResultInfo{}, nil
			}

			Expect(func() {
				_, _ = client.ListTunnelDNSRecords(ctx, "zone-123", "tunnel-abc")
			}).To(Panic(), "ListTunnelDNSRecords panics when record.Proxied is nil (known bug)")
		})
	})

	// -----------------------------------------------------------------
	// Positive: non-nil Proxied pointers work correctly
	// -----------------------------------------------------------------

	Describe("GetDNSRecordByName with non-nil Proxied = true", func() {
		It("does not panic and maps the value correctly", func() {
			proxied := true
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) { return "zone-123", nil }
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{
					{ID: "r1", Name: "app.example.com", Type: "CNAME", Content: "t.cfargotunnel.com", Proxied: &proxied, TTL: 1},
				}, &cloudflare.ResultInfo{}, nil
			}

			config, err := client.GetDNSRecordByName(ctx, "app.example.com")
			Expect(err).NotTo(HaveOccurred())
			Expect(config.Proxied).To(BeTrue())
		})
	})

	Describe("ListTunnelDNSRecords with non-nil Proxied = true", func() {
		It("does not panic and maps the value correctly", func() {
			proxied := true
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{
					{ID: "r1", Name: "app.example.com", Type: "CNAME", Content: "tunnel-abc.cfargotunnel.com", Proxied: &proxied, TTL: 1},
				}, &cloudflare.ResultInfo{}, nil
			}

			records, err := client.ListTunnelDNSRecords(ctx, "zone-123", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(records).To(HaveLen(1))
			Expect(records[0].Proxied).To(BeTrue())
		})
	})
})

var _ = Describe("Nil-pointer guard — access.go", func() {
	var (
		ctx     context.Context
		client  *TunnelClient
		mockAPI *mockCloudflareAPI
	)

	BeforeEach(func() {
		ctx = context.Background()
		mockAPI = &mockCloudflareAPI{}
		client = &TunnelClient{
			api:     mockAPI,
			limiter: rate.NewLimiter(rate.Inf, 0),
			tracer:  otel.GetTracerProvider().Tracer("test"),
		}
	})

	// -----------------------------------------------------------------
	// CreateAccessApplication: dereferences AutoRedirectToIdentity and
	// EnableBindingCookie from the returned AccessApplication
	// -----------------------------------------------------------------

	Describe("CreateAccessApplication with nil AutoRedirectToIdentity", func() {
		It("panics when the API returns AutoRedirectToIdentity = nil", func() {
			mockAPI.createAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id",
					Name:                   "My App",
					AutoRedirectToIdentity: nil, // nil — will panic on dereference
					EnableBindingCookie:    nil,
				}, nil
			}

			Expect(func() {
				_, _ = client.CreateAccessApplication(ctx, "account-123", AccessApplicationConfig{
					Name: "My App",
				})
			}).To(Panic(), "CreateAccessApplication panics when AutoRedirectToIdentity is nil (known bug)")
		})
	})

	Describe("CreateAccessApplication with nil EnableBindingCookie", func() {
		It("panics when the API returns EnableBindingCookie = nil (AutoRedirectToIdentity non-nil)", func() {
			autoRedirect := false
			mockAPI.createAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id",
					Name:                   "My App",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    nil, // nil — will panic on dereference
				}, nil
			}

			Expect(func() {
				_, _ = client.CreateAccessApplication(ctx, "account-123", AccessApplicationConfig{
					Name: "My App",
				})
			}).To(Panic(), "CreateAccessApplication panics when EnableBindingCookie is nil (known bug)")
		})
	})

	// -----------------------------------------------------------------
	// GetAccessApplication: same unconditional dereferences
	// -----------------------------------------------------------------

	Describe("GetAccessApplication with nil AutoRedirectToIdentity", func() {
		It("panics when the API returns AutoRedirectToIdentity = nil", func() {
			mockAPI.getAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id",
					AutoRedirectToIdentity: nil,
					EnableBindingCookie:    nil,
				}, nil
			}

			Expect(func() {
				_, _ = client.GetAccessApplication(ctx, "account-123", "app-id")
			}).To(Panic(), "GetAccessApplication panics when AutoRedirectToIdentity is nil (known bug)")
		})
	})

	Describe("GetAccessApplication with nil EnableBindingCookie", func() {
		It("panics when AutoRedirectToIdentity is non-nil but EnableBindingCookie is nil", func() {
			autoRedirect := true
			mockAPI.getAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    nil,
				}, nil
			}

			Expect(func() {
				_, _ = client.GetAccessApplication(ctx, "account-123", "app-id")
			}).To(Panic(), "GetAccessApplication panics when EnableBindingCookie is nil (known bug)")
		})
	})

	// -----------------------------------------------------------------
	// Positive: both fields non-nil — no panic
	// -----------------------------------------------------------------

	Describe("CreateAccessApplication with all required pointer fields set", func() {
		It("succeeds without panic when both pointer fields are non-nil", func() {
			autoRedirect := true
			bindingCookie := false
			mockAPI.createAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id",
					Name:                   "My App",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
				}, nil
			}

			config, err := client.CreateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				Name: "My App",
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(config.AutoRedirectToIdentity).To(BeTrue())
			Expect(config.EnableBindingCookie).To(BeFalse())
		})
	})

	Describe("GetAccessApplication with all required pointer fields set", func() {
		It("succeeds without panic when both pointer fields are non-nil", func() {
			autoRedirect := false
			bindingCookie := true
			mockAPI.getAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{
					ID:                     "app-id",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
				}, nil
			}

			config, err := client.GetAccessApplication(ctx, "account-123", "app-id")
			Expect(err).NotTo(HaveOccurred())
			Expect(config.AutoRedirectToIdentity).To(BeFalse())
			Expect(config.EnableBindingCookie).To(BeTrue())
		})
	})
})
