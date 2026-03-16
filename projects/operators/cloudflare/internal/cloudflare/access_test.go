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

var _ = Describe("Access operations", func() {
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

	Describe("convertAccessPolicyRules", func() {
		It("returns empty slice for empty input", func() {
			result := convertAccessPolicyRules([]AccessPolicyRule{})
			Expect(result).To(BeEmpty())
		})

		It("converts group rule", func() {
			rules := []AccessPolicyRule{
				{GroupID: "group-abc"},
			}
			result := convertAccessPolicyRules(rules)
			Expect(result).To(HaveLen(1))
			entry := result[0].(map[string]interface{})
			group := entry["group"].(map[string]interface{})
			Expect(group["id"]).To(Equal("group-abc"))
		})

		It("converts email rules into individual entries", func() {
			rules := []AccessPolicyRule{
				{Emails: []string{"a@example.com", "b@example.com"}},
			}
			result := convertAccessPolicyRules(rules)
			Expect(result).To(HaveLen(2))
			for _, r := range result {
				entry := r.(map[string]interface{})
				Expect(entry).To(HaveKey("email"))
			}
		})

		It("converts EmailsEndingIn rules", func() {
			rules := []AccessPolicyRule{
				{EmailsEndingIn: []string{"@example.com"}},
			}
			result := convertAccessPolicyRules(rules)
			Expect(result).To(HaveLen(1))
			entry := result[0].(map[string]interface{})
			domain := entry["email_domain"].(map[string]interface{})
			Expect(domain["domain"]).To(Equal("@example.com"))
		})

		It("converts EmailDomains rules", func() {
			rules := []AccessPolicyRule{
				{EmailDomains: []string{"example.com"}},
			}
			result := convertAccessPolicyRules(rules)
			Expect(result).To(HaveLen(1))
			entry := result[0].(map[string]interface{})
			domain := entry["email_domain"].(map[string]interface{})
			Expect(domain["domain"]).To(Equal("example.com"))
		})

		It("converts everyone rule", func() {
			rules := []AccessPolicyRule{
				{Everyone: true},
			}
			result := convertAccessPolicyRules(rules)
			Expect(result).To(HaveLen(1))
			entry := result[0].(map[string]interface{})
			Expect(entry).To(HaveKey("everyone"))
		})

		It("converts GitHub organization rules", func() {
			rules := []AccessPolicyRule{
				{GitHubOrganizations: []string{"my-org"}},
			}
			result := convertAccessPolicyRules(rules)
			Expect(result).To(HaveLen(1))
			entry := result[0].(map[string]interface{})
			ghOrg := entry["github-organization"].(map[string]interface{})
			Expect(ghOrg["name"]).To(Equal("my-org"))
		})

		It("converts IP range rules", func() {
			rules := []AccessPolicyRule{
				{IPRanges: []string{"10.0.0.0/8", "192.168.0.0/16"}},
			}
			result := convertAccessPolicyRules(rules)
			Expect(result).To(HaveLen(1))
			entry := result[0].(map[string]interface{})
			ip := entry["ip"].(map[string]interface{})
			Expect(ip["ip"]).To(ConsistOf("10.0.0.0/8", "192.168.0.0/16"))
		})

		It("converts country rules", func() {
			rules := []AccessPolicyRule{
				{Countries: []string{"US", "DE"}},
			}
			result := convertAccessPolicyRules(rules)
			Expect(result).To(HaveLen(1))
			entry := result[0].(map[string]interface{})
			geo := entry["geo"].(map[string]interface{})
			Expect(geo["country_code"]).To(ConsistOf("US", "DE"))
		})

		It("group rule takes precedence over other fields", func() {
			rules := []AccessPolicyRule{
				{
					GroupID: "group-abc",
					Emails:  []string{"user@example.com"},
				},
			}
			result := convertAccessPolicyRules(rules)
			// Only the group rule should be emitted — group takes priority and continues
			Expect(result).To(HaveLen(1))
			entry := result[0].(map[string]interface{})
			Expect(entry).To(HaveKey("group"))
		})
	})

	Describe("CreateAccessApplication", func() {
		It("creates an access application successfully", func() {
			autoRedirect := false
			bindingCookie := false
			mockAPI.createAccessApplicationFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(params.Name).To(Equal("My App"))
				Expect(params.Domain).To(Equal("app.example.com"))
				return cloudflare.AccessApplication{
					ID:                     "app-id-999",
					Name:                   params.Name,
					Domain:                 params.Domain,
					Type:                   cloudflare.SelfHosted,
					SessionDuration:        "24h",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
				}, nil
			}

			config, err := client.CreateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				Name:            "My App",
				Domain:          "app.example.com",
				Type:            "self_hosted",
				SessionDuration: "24h",
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(config).NotTo(BeNil())
			Expect(config.ID).To(Equal("app-id-999"))
			Expect(config.Name).To(Equal("My App"))
			Expect(config.Domain).To(Equal("app.example.com"))
		})

		It("includes CORS headers when provided", func() {
			autoRedirect := false
			bindingCookie := false
			mockAPI.createAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				Expect(params.CorsHeaders).NotTo(BeNil())
				Expect(params.CorsHeaders.AllowAllOrigins).To(BeTrue())
				return cloudflare.AccessApplication{
					ID:                     "app-id-999",
					Name:                   params.Name,
					Domain:                 params.Domain,
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
					CorsHeaders: &cloudflare.AccessApplicationCorsHeaders{
						AllowAllOrigins: true,
					},
				}, nil
			}

			config, err := client.CreateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				Name:   "My App",
				Domain: "app.example.com",
				CORSHeaders: &AccessCORSConfig{
					AllowAllOrigins: true,
				},
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(config.CORSHeaders).NotTo(BeNil())
			Expect(config.CORSHeaders.AllowAllOrigins).To(BeTrue())
		})

		It("includes CustomDenyMessage and CustomDenyURL when set", func() {
			autoRedirect := false
			bindingCookie := false
			mockAPI.createAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, params cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				Expect(params.CustomDenyMessage).To(Equal("Access denied"))
				Expect(params.CustomDenyURL).To(Equal("https://example.com/denied"))
				return cloudflare.AccessApplication{
					ID:                     "app-id-999",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
					CustomDenyMessage:      params.CustomDenyMessage,
					CustomDenyURL:          params.CustomDenyURL,
				}, nil
			}

			_, err := client.CreateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				Name:              "My App",
				CustomDenyMessage: "Access denied",
				CustomDenyURL:     "https://example.com/denied",
			})
			Expect(err).NotTo(HaveOccurred())
		})

		It("returns an error when the API call fails", func() {
			mockAPI.createAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{}, fmt.Errorf("API error")
			}

			_, err := client.CreateAccessApplication(ctx, "account-123", AccessApplicationConfig{Name: "My App"})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to create access application"))
		})
	})

	Describe("UpdateAccessApplication", func() {
		It("updates an access application successfully", func() {
			updateCalled := false
			mockAPI.updateAccessApplicationFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				updateCalled = true
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(params.ID).To(Equal("app-id-999"))
				return cloudflare.AccessApplication{}, nil
			}

			err := client.UpdateAccessApplication(ctx, "account-123", AccessApplicationConfig{
				ID:   "app-id-999",
				Name: "Updated App",
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(updateCalled).To(BeTrue())
		})

		It("returns an error when the API call fails", func() {
			mockAPI.updateAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{}, fmt.Errorf("API error")
			}

			err := client.UpdateAccessApplication(ctx, "account-123", AccessApplicationConfig{ID: "app-id-999"})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to update access application"))
		})
	})

	Describe("DeleteAccessApplication", func() {
		It("deletes an access application successfully", func() {
			deleteCalled := false
			mockAPI.deleteAccessApplicationFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, applicationID string) error {
				deleteCalled = true
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(applicationID).To(Equal("app-id-999"))
				return nil
			}

			err := client.DeleteAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(deleteCalled).To(BeTrue())
		})

		It("returns nil when the application is not found (idempotent)", func() {
			mockAPI.deleteAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) error {
				return &cloudflare.Error{StatusCode: http.StatusNotFound}
			}

			err := client.DeleteAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
		})

		It("returns an error on non-404 API failure", func() {
			mockAPI.deleteAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) error {
				return &cloudflare.Error{StatusCode: http.StatusInternalServerError}
			}

			err := client.DeleteAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to delete access application"))
		})
	})

	Describe("GetAccessApplication", func() {
		It("retrieves an access application by ID", func() {
			autoRedirect := true
			bindingCookie := false
			mockAPI.getAccessApplicationFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, applicationID string) (cloudflare.AccessApplication, error) {
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(applicationID).To(Equal("app-id-999"))
				return cloudflare.AccessApplication{
					ID:                     "app-id-999",
					Name:                   "My App",
					Domain:                 "app.example.com",
					Type:                   cloudflare.SelfHosted,
					SessionDuration:        "24h",
					AutoRedirectToIdentity: &autoRedirect,
					EnableBindingCookie:    &bindingCookie,
				}, nil
			}

			config, err := client.GetAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(config.ID).To(Equal("app-id-999"))
			Expect(config.Name).To(Equal("My App"))
			Expect(config.AutoRedirectToIdentity).To(BeTrue())
		})

		It("returns an error when the API call fails", func() {
			mockAPI.getAccessApplicationFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ string) (cloudflare.AccessApplication, error) {
				return cloudflare.AccessApplication{}, fmt.Errorf("API error")
			}

			_, err := client.GetAccessApplication(ctx, "account-123", "app-id-999")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get access application"))
		})
	})

	Describe("CreateAccessPolicy", func() {
		It("creates an access policy for an application", func() {
			mockAPI.createAccessPolicyFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateAccessPolicyParams) (cloudflare.AccessPolicy, error) {
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(params.ApplicationID).To(Equal("app-id-999"))
				Expect(params.Name).To(Equal("Allow admins"))
				Expect(params.Decision).To(Equal("allow"))
				return cloudflare.AccessPolicy{
					ID:       "policy-id-1",
					Name:     params.Name,
					Decision: "allow",
				}, nil
			}

			result, err := client.CreateAccessPolicy(ctx, "account-123", AccessPolicyConfig{
				ApplicationID: "app-id-999",
				Name:          "Allow admins",
				Decision:      "allow",
				Include: []AccessPolicyRule{
					{Everyone: true},
				},
			})

			Expect(err).NotTo(HaveOccurred())
			Expect(result.ID).To(Equal("policy-id-1"))
			Expect(result.Name).To(Equal("Allow admins"))
			Expect(result.ApplicationID).To(Equal("app-id-999"))
		})

		It("returns an error when the API call fails", func() {
			mockAPI.createAccessPolicyFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.CreateAccessPolicyParams) (cloudflare.AccessPolicy, error) {
				return cloudflare.AccessPolicy{}, fmt.Errorf("API error")
			}

			_, err := client.CreateAccessPolicy(ctx, "account-123", AccessPolicyConfig{
				ApplicationID: "app-id-999",
				Name:          "Allow admins",
			})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to create access policy"))
		})
	})

	Describe("DeleteAccessPolicy", func() {
		It("deletes an access policy successfully", func() {
			deleteCalled := false
			mockAPI.deleteAccessPolicyFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.DeleteAccessPolicyParams) error {
				deleteCalled = true
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(params.ApplicationID).To(Equal("app-id-999"))
				Expect(params.PolicyID).To(Equal("policy-id-1"))
				return nil
			}

			err := client.DeleteAccessPolicy(ctx, "account-123", "app-id-999", "policy-id-1")
			Expect(err).NotTo(HaveOccurred())
			Expect(deleteCalled).To(BeTrue())
		})

		It("returns nil when the policy is not found (idempotent)", func() {
			mockAPI.deleteAccessPolicyFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.DeleteAccessPolicyParams) error {
				return &cloudflare.Error{StatusCode: http.StatusNotFound}
			}

			err := client.DeleteAccessPolicy(ctx, "account-123", "app-id-999", "policy-id-1")
			Expect(err).NotTo(HaveOccurred())
		})

		It("returns an error on non-404 API failure", func() {
			mockAPI.deleteAccessPolicyFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.DeleteAccessPolicyParams) error {
				return &cloudflare.Error{StatusCode: http.StatusBadRequest}
			}

			err := client.DeleteAccessPolicy(ctx, "account-123", "app-id-999", "policy-id-1")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to delete access policy"))
		})
	})

	Describe("ListAccessPolicies", func() {
		It("lists all policies for an application", func() {
			mockAPI.listAccessPoliciesFunc = func(_ context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListAccessPoliciesParams) ([]cloudflare.AccessPolicy, *cloudflare.ResultInfo, error) {
				Expect(rc.Identifier).To(Equal("account-123"))
				Expect(params.ApplicationID).To(Equal("app-id-999"))
				return []cloudflare.AccessPolicy{
					{ID: "policy-1", Name: "Allow admins", Decision: "allow"},
					{ID: "policy-2", Name: "Deny all", Decision: "deny"},
				}, &cloudflare.ResultInfo{}, nil
			}

			policies, err := client.ListAccessPolicies(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(policies).To(HaveLen(2))
			Expect(policies[0].ID).To(Equal("policy-1"))
			Expect(policies[0].ApplicationID).To(Equal("app-id-999"))
			Expect(policies[1].ID).To(Equal("policy-2"))
		})

		It("returns empty slice when no policies exist", func() {
			mockAPI.listAccessPoliciesFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListAccessPoliciesParams) ([]cloudflare.AccessPolicy, *cloudflare.ResultInfo, error) {
				return []cloudflare.AccessPolicy{}, &cloudflare.ResultInfo{}, nil
			}

			policies, err := client.ListAccessPolicies(ctx, "account-123", "app-id-999")
			Expect(err).NotTo(HaveOccurred())
			Expect(policies).To(BeEmpty())
		})

		It("returns an error when the API call fails", func() {
			mockAPI.listAccessPoliciesFunc = func(_ context.Context, _ *cloudflare.ResourceContainer, _ cloudflare.ListAccessPoliciesParams) ([]cloudflare.AccessPolicy, *cloudflare.ResultInfo, error) {
				return nil, nil, fmt.Errorf("API error")
			}

			_, err := client.ListAccessPolicies(ctx, "account-123", "app-id-999")
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to list access policies"))
		})
	})
})
