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
	"go.opentelemetry.io/otel"
	"golang.org/x/time/rate"
)

var _ = Describe("DNS operations", func() {
	var (
		ctx    context.Context
		client *TunnelClient
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

	Describe("extractZoneName", func() {
		DescribeTable("extracts zone name from hostname",
			func(hostname, expectedZone string, expectErr bool) {
				zone, err := extractZoneName(hostname)
				if expectErr {
					Expect(err).To(HaveOccurred())
				} else {
					Expect(err).NotTo(HaveOccurred())
					Expect(zone).To(Equal(expectedZone))
				}
			},
			Entry("subdomain hostname", "app.example.com", "example.com", false),
			Entry("nested subdomain", "deep.app.example.com", "example.com", false),
			Entry("bare apex domain", "example.com", "example.com", false),
			Entry("wildcard hostname", "*.example.com", "example.com", false),
			Entry("single label", "hostname", "", true),
			Entry("empty string", "", "", true),
		)
	})

	Describe("CreateTunnelDNSRecord", func() {
		It("creates a CNAME DNS record pointing to the tunnel", func() {
			mockAPI.zoneIDByNameFunc = func(zoneName string) (string, error) {
				Expect(zoneName).To(Equal("example.com"))
				return "zone-123", nil
			}
			mockAPI.createDNSRecordFunc = func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateDNSRecordParams) (cloudflare.DNSRecord, error) {
				Expect(rc.Identifier).To(Equal("zone-123"))
				Expect(params.Type).To(Equal("CNAME"))
				Expect(params.Name).To(Equal("app.example.com"))
				Expect(params.Content).To(Equal("tunnel-abc.cfargotunnel.com"))
				Expect(*params.Proxied).To(BeTrue())
				Expect(params.TTL).To(Equal(1))
				return cloudflare.DNSRecord{ID: "record-999"}, nil
			}

			config, err := client.CreateTunnelDNSRecord(ctx, "app.example.com", "tunnel-abc")

			Expect(err).NotTo(HaveOccurred())
			Expect(config).NotTo(BeNil())
			Expect(config.RecordID).To(Equal("record-999"))
			Expect(config.Name).To(Equal("app.example.com"))
			Expect(config.Type).To(Equal("CNAME"))
			Expect(config.Content).To(Equal("tunnel-abc.cfargotunnel.com"))
			Expect(config.Proxied).To(BeTrue())
			Expect(config.TTL).To(Equal(1))
			Expect(config.ZoneID).To(Equal("zone-123"))
		})

		It("returns an error when the hostname is invalid", func() {
			_, err := client.CreateTunnelDNSRecord(ctx, "noDots", "tunnel-abc")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to extract zone from hostname"))
		})

		It("returns an error when ZoneIDByName fails", func() {
			mockAPI.zoneIDByNameFunc = func(zoneName string) (string, error) {
				return "", fmt.Errorf("zone not found")
			}

			_, err := client.CreateTunnelDNSRecord(ctx, "app.example.com", "tunnel-abc")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get zone ID"))
		})

		It("returns an error when CreateDNSRecord fails", func() {
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) {
				return "zone-123", nil
			}
			mockAPI.createDNSRecordFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.CreateDNSRecordParams) (cloudflare.DNSRecord, error) {
				return cloudflare.DNSRecord{}, fmt.Errorf("API error")
			}

			_, err := client.CreateTunnelDNSRecord(ctx, "app.example.com", "tunnel-abc")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to create DNS record"))
		})
	})

	Describe("DeleteDNSRecord", func() {
		It("deletes the DNS record successfully", func() {
			deleteCalled := false
			mockAPI.deleteDNSRecordFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, recordID string) error {
				deleteCalled = true
				Expect(rc.Identifier).To(Equal("zone-123"))
				Expect(recordID).To(Equal("record-999"))
				return nil
			}

			err := client.DeleteDNSRecord(ctx, "zone-123", "record-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(deleteCalled).To(BeTrue())
		})

		It("returns nil when the record is not found (idempotent)", func() {
			mockAPI.deleteDNSRecordFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) error {
				return &cloudflare.Error{StatusCode: http.StatusNotFound}
			}

			err := client.DeleteDNSRecord(ctx, "zone-123", "record-999")
			Expect(err).NotTo(HaveOccurred())
		})

		It("returns an error on non-404 API failure", func() {
			mockAPI.deleteDNSRecordFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) error {
				return &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			}

			err := client.DeleteDNSRecord(ctx, "zone-123", "record-999")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to delete DNS record"))
		})
	})

	Describe("GetDNSRecordByName", func() {
		It("retrieves the DNS record by hostname", func() {
			proxied := true
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) {
				return "zone-123", nil
			}
			mockAPI.listDNSRecordsFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				Expect(rc.Identifier).To(Equal("zone-123"))
				Expect(params.Name).To(Equal("app.example.com"))
				return []cloudflare.DNSRecord{
					{
						ID:      "record-999",
						Name:    "app.example.com",
						Type:    "CNAME",
						Content: "tunnel-abc.cfargotunnel.com",
						Proxied: &proxied,
						TTL:     1,
					},
				}, &cloudflare.ResultInfo{}, nil
			}

			config, err := client.GetDNSRecordByName(ctx, "app.example.com")
			Expect(err).NotTo(HaveOccurred())
			Expect(config).NotTo(BeNil())
			Expect(config.RecordID).To(Equal("record-999"))
			Expect(config.Name).To(Equal("app.example.com"))
			Expect(config.Type).To(Equal("CNAME"))
			Expect(config.ZoneID).To(Equal("zone-123"))
		})

		It("returns an error when no DNS record is found", func() {
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) {
				return "zone-123", nil
			}
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{}, &cloudflare.ResultInfo{}, nil
			}

			_, err := client.GetDNSRecordByName(ctx, "app.example.com")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("DNS record not found for hostname"))
		})

		It("returns an error when ZoneIDByName fails", func() {
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) {
				return "", fmt.Errorf("zone lookup failed")
			}

			_, err := client.GetDNSRecordByName(ctx, "app.example.com")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get zone ID"))
		})

		It("returns an error when the hostname is invalid", func() {
			_, err := client.GetDNSRecordByName(ctx, "noDots")
			Expect(err).To(HaveOccurred())
		})

		It("returns an error when ListDNSRecords fails", func() {
			mockAPI.zoneIDByNameFunc = func(_ string) (string, error) {
				return "zone-123", nil
			}
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return nil, nil, fmt.Errorf("API error")
			}

			_, err := client.GetDNSRecordByName(ctx, "app.example.com")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to list DNS records"))
		})
	})

	Describe("ListTunnelDNSRecords", func() {
		It("lists DNS records pointing to the specified tunnel", func() {
			proxied := true
			mockAPI.listDNSRecordsFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				Expect(rc.Identifier).To(Equal("zone-123"))
				Expect(params.Type).To(Equal("CNAME"))
				return []cloudflare.DNSRecord{
					{
						ID:      "record-1",
						Name:    "app.example.com",
						Type:    "CNAME",
						Content: "tunnel-abc.cfargotunnel.com",
						Proxied: &proxied,
						TTL:     1,
					},
					{
						ID:      "record-2",
						Name:    "other.example.com",
						Type:    "CNAME",
						Content: "other-tunnel.cfargotunnel.com",
						Proxied: &proxied,
						TTL:     1,
					},
				}, &cloudflare.ResultInfo{}, nil
			}

			records, err := client.ListTunnelDNSRecords(ctx, "zone-123", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(records).To(HaveLen(1))
			Expect(records[0].RecordID).To(Equal("record-1"))
			Expect(records[0].Content).To(Equal("tunnel-abc.cfargotunnel.com"))
		})

		It("returns empty slice when no records match the tunnel", func() {
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return []cloudflare.DNSRecord{}, &cloudflare.ResultInfo{}, nil
			}

			records, err := client.ListTunnelDNSRecords(ctx, "zone-123", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(records).To(BeEmpty())
		})

		It("returns an error when ListDNSRecords fails", func() {
			mockAPI.listDNSRecordsFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
				return nil, nil, fmt.Errorf("API error")
			}

			_, err := client.ListTunnelDNSRecords(ctx, "zone-123", "tunnel-abc")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to list DNS records in zone"))
		})
	})

	Describe("UpdateDNSRecord", func() {
		It("updates an existing DNS record", func() {
			updateCalled := false
			mockAPI.updateDNSRecordFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.UpdateDNSRecordParams) (cloudflare.DNSRecord, error) {
				updateCalled = true
				Expect(rc.Identifier).To(Equal("zone-123"))
				Expect(params.ID).To(Equal("record-999"))
				Expect(params.Name).To(Equal("app.example.com"))
				Expect(params.Content).To(Equal("new-tunnel.cfargotunnel.com"))
				return cloudflare.DNSRecord{ID: "record-999"}, nil
			}

			err := client.UpdateDNSRecord(ctx, DNSRecordConfig{
				ZoneID:   "zone-123",
				RecordID: "record-999",
				Name:     "app.example.com",
				Type:     "CNAME",
				Content:  "new-tunnel.cfargotunnel.com",
				Proxied:  true,
				TTL:      1,
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(updateCalled).To(BeTrue())
		})

		It("returns an error when UpdateDNSRecord fails", func() {
			mockAPI.updateDNSRecordFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.UpdateDNSRecordParams) (cloudflare.DNSRecord, error) {
				return cloudflare.DNSRecord{}, fmt.Errorf("API error")
			}

			err := client.UpdateDNSRecord(ctx, DNSRecordConfig{
				ZoneID:   "zone-123",
				RecordID: "record-999",
				Name:     "app.example.com",
			})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to update DNS record"))
		})
	})
})
