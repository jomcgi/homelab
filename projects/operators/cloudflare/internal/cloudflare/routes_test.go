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

	"github.com/cloudflare/cloudflare-go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"go.opentelemetry.io/otel"
	"golang.org/x/time/rate"
)

var _ = Describe("Routes operations", func() {
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

	Describe("CreatePublishedRoute", func() {
		It("creates a route in an empty tunnel configuration", func() {
			var capturedParams cloudflare.TunnelConfigurationParams

			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.TunnelConfigurationResult, error) {
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(tunnelID).To(Equal("tunnel-abc"))
				return cloudflare.TunnelConfigurationResult{}, nil
			}
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				Expect(rc.Identifier).To(Equal("account-123"))
				capturedParams = params
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			err := client.CreatePublishedRoute(ctx, "account-123", "tunnel-abc", RouteConfig{
				Hostname: "app.example.com",
				Service:  "http://backend:8080",
			})

			Expect(err).NotTo(HaveOccurred())
			// Should have the new route + catch-all
			Expect(capturedParams.Config.Ingress).To(HaveLen(2))
			Expect(capturedParams.Config.Ingress[0].Hostname).To(Equal("app.example.com"))
			Expect(capturedParams.Config.Ingress[0].Service).To(Equal("http://backend:8080"))
			// Last rule is catch-all
			Expect(capturedParams.Config.Ingress[1].Hostname).To(BeEmpty())
			Expect(capturedParams.Config.Ingress[1].Service).To(Equal("http_status:404"))
		})

		It("preserves existing routes and adds the new one", func() {
			var capturedParams cloudflare.TunnelConfigurationParams

			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "existing.example.com", Service: "http://existing:8080"},
							{Service: "http_status:404"}, // catch-all
						},
					},
				}, nil
			}
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				capturedParams = params
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			err := client.CreatePublishedRoute(ctx, "account-123", "tunnel-abc", RouteConfig{
				Hostname: "new.example.com",
				Service:  "http://new:9090",
			})

			Expect(err).NotTo(HaveOccurred())
			// existing + new + catch-all = 3
			Expect(capturedParams.Config.Ingress).To(HaveLen(3))
			hostnames := make([]string, 0, 3)
			for _, r := range capturedParams.Config.Ingress {
				hostnames = append(hostnames, r.Hostname)
			}
			Expect(hostnames).To(ContainElements("existing.example.com", "new.example.com", ""))
		})

		It("replaces an existing route with a different service", func() {
			var capturedParams cloudflare.TunnelConfigurationParams

			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "app.example.com", Service: "http://old:8080"},
							{Service: "http_status:404"},
						},
					},
				}, nil
			}
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				capturedParams = params
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			err := client.CreatePublishedRoute(ctx, "account-123", "tunnel-abc", RouteConfig{
				Hostname: "app.example.com",
				Service:  "http://new:9090",
			})

			Expect(err).NotTo(HaveOccurred())
			// Only new route + catch-all (old route replaced)
			Expect(capturedParams.Config.Ingress).To(HaveLen(2))
			Expect(capturedParams.Config.Ingress[0].Service).To(Equal("http://new:9090"))
		})

		It("returns nil without calling update when route already exists with same config", func() {
			updateCalled := false
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
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				updateCalled = true
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			err := client.CreatePublishedRoute(ctx, "account-123", "tunnel-abc", RouteConfig{
				Hostname: "app.example.com",
				Service:  "http://backend:8080",
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(updateCalled).To(BeFalse())
		})

		It("creates a route with a path", func() {
			var capturedParams cloudflare.TunnelConfigurationParams

			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, nil
			}
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				capturedParams = params
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			err := client.CreatePublishedRoute(ctx, "account-123", "tunnel-abc", RouteConfig{
				Hostname: "app.example.com",
				Service:  "http://backend:8080",
				Path:     "/api",
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(capturedParams.Config.Ingress[0].Path).To(Equal("/api"))
		})

		It("returns an error when GetTunnelConfiguration fails with non-404 error", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, fmt.Errorf("unexpected API error")
			}

			err := client.CreatePublishedRoute(ctx, "account-123", "tunnel-abc", RouteConfig{
				Hostname: "app.example.com",
				Service:  "http://backend:8080",
			})

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get current tunnel configuration"))
		})

		It("returns an error when UpdateTunnelConfiguration fails", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, nil
			}
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, fmt.Errorf("API error")
			}

			err := client.CreatePublishedRoute(ctx, "account-123", "tunnel-abc", RouteConfig{
				Hostname: "app.example.com",
				Service:  "http://backend:8080",
			})

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to create published route"))
		})

		It("sorts ingress rules by hostname alphabetically", func() {
			var capturedParams cloudflare.TunnelConfigurationParams

			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "zzz.example.com", Service: "http://zzz:8080"},
							{Service: "http_status:404"},
						},
					},
				}, nil
			}
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				capturedParams = params
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			err := client.CreatePublishedRoute(ctx, "account-123", "tunnel-abc", RouteConfig{
				Hostname: "aaa.example.com",
				Service:  "http://aaa:8080",
			})

			Expect(err).NotTo(HaveOccurred())
			// aaa should come before zzz
			Expect(capturedParams.Config.Ingress[0].Hostname).To(Equal("aaa.example.com"))
			Expect(capturedParams.Config.Ingress[1].Hostname).To(Equal("zzz.example.com"))
		})
	})

	Describe("DeletePublishedRoute", func() {
		It("deletes an existing route", func() {
			var capturedParams cloudflare.TunnelConfigurationParams

			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "app.example.com", Service: "http://backend:8080"},
							{Hostname: "other.example.com", Service: "http://other:9090"},
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
			// remaining route + catch-all
			Expect(capturedParams.Config.Ingress).To(HaveLen(2))
			Expect(capturedParams.Config.Ingress[0].Hostname).To(Equal("other.example.com"))
			Expect(capturedParams.Config.Ingress[1].Hostname).To(BeEmpty()) // catch-all
		})

		It("returns nil when the route does not exist (idempotent)", func() {
			updateCalled := false
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "other.example.com", Service: "http://other:9090"},
							{Service: "http_status:404"},
						},
					},
				}, nil
			}
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				updateCalled = true
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			err := client.DeletePublishedRoute(ctx, "account-123", "tunnel-abc", "notexist.example.com")

			Expect(err).NotTo(HaveOccurred())
			Expect(updateCalled).To(BeFalse())
		})

		It("returns an error when GetTunnelConfiguration fails", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, fmt.Errorf("API error")
			}

			err := client.DeletePublishedRoute(ctx, "account-123", "tunnel-abc", "app.example.com")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get tunnel configuration"))
		})

		It("returns an error when UpdateTunnelConfiguration fails", func() {
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
			mockAPI.updateTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, fmt.Errorf("API error")
			}

			err := client.DeletePublishedRoute(ctx, "account-123", "tunnel-abc", "app.example.com")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to delete published route"))
		})
	})

	Describe("ListPublishedRoutes", func() {
		It("returns all routes excluding catch-all", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.TunnelConfigurationResult, error) {
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(tunnelID).To(Equal("tunnel-abc"))
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "app.example.com", Service: "http://backend:8080"},
							{Hostname: "api.example.com", Service: "http://api:9090", Path: "/v1"},
							{Service: "http_status:404"},
						},
					},
				}, nil
			}

			routes, err := client.ListPublishedRoutes(ctx, "account-123", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(routes).To(HaveLen(2))
			Expect(routes[0].Hostname).To(Equal("app.example.com"))
			Expect(routes[0].Service).To(Equal("http://backend:8080"))
			Expect(routes[1].Hostname).To(Equal("api.example.com"))
			Expect(routes[1].Path).To(Equal("/v1"))
		})

		It("returns empty slice when there are no routes (only catch-all)", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Service: "http_status:404"},
						},
					},
				}, nil
			}

			routes, err := client.ListPublishedRoutes(ctx, "account-123", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(routes).To(BeEmpty())
		})

		It("returns empty slice when configuration has no ingress rules", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, nil
			}

			routes, err := client.ListPublishedRoutes(ctx, "account-123", "tunnel-abc")
			Expect(err).NotTo(HaveOccurred())
			Expect(routes).To(BeEmpty())
		})

		It("returns an error when GetTunnelConfiguration fails", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, fmt.Errorf("API error")
			}

			_, err := client.ListPublishedRoutes(ctx, "account-123", "tunnel-abc")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to list published routes"))
		})
	})

	Describe("GetPublishedRoute", func() {
		It("retrieves a route by hostname", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "app.example.com", Service: "http://backend:8080"},
							{Hostname: "api.example.com", Service: "http://api:9090"},
							{Service: "http_status:404"},
						},
					},
				}, nil
			}

			route, err := client.GetPublishedRoute(ctx, "account-123", "tunnel-abc", "app.example.com")
			Expect(err).NotTo(HaveOccurred())
			Expect(route).NotTo(BeNil())
			Expect(route.Hostname).To(Equal("app.example.com"))
			Expect(route.Service).To(Equal("http://backend:8080"))
		})

		It("returns an error when the route does not exist", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{
					Config: cloudflare.TunnelConfiguration{
						Ingress: []cloudflare.UnvalidatedIngressRule{
							{Hostname: "other.example.com", Service: "http://other:8080"},
							{Service: "http_status:404"},
						},
					},
				}, nil
			}

			_, err := client.GetPublishedRoute(ctx, "account-123", "tunnel-abc", "notexist.example.com")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("route not found for hostname"))
		})

		It("returns an error when ListPublishedRoutes fails", func() {
			mockAPI.getTunnelConfigurationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.TunnelConfigurationResult, error) {
				return cloudflare.TunnelConfigurationResult{}, fmt.Errorf("API error")
			}

			_, err := client.GetPublishedRoute(ctx, "account-123", "tunnel-abc", "app.example.com")
			Expect(err).To(HaveOccurred())
		})
	})
})
