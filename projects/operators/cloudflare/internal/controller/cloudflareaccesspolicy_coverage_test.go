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

package controller

import (
	"context"
	"fmt"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	apimeta "k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("CloudflareAccessPolicy Controller Coverage", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
	})

	newAccessPolicyReconciler := func() *CloudflareAccessPolicyReconciler {
		return &CloudflareAccessPolicyReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-accesspolicy-coverage"),
		}
	}

	createTestAccessPolicy := func(name string, targetKind, targetName string) *tunnelsv1.CloudflareAccessPolicy {
		policy := &tunnelsv1.CloudflareAccessPolicy{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: "default",
			},
			Spec: tunnelsv1.CloudflareAccessPolicySpec{
				TargetRef: tunnelsv1.PolicyTargetReference{
					Group: "gateway.networking.k8s.io",
					Kind:  targetKind,
					Name:  targetName,
				},
				Application: tunnelsv1.ApplicationConfig{
					Name:            "Test App",
					SessionDuration: "24h",
					Type:            "self_hosted",
				},
				Policies: []tunnelsv1.AccessPolicy{
					{
						Name:     "allow-all",
						Decision: "allow",
						Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
					},
				},
			},
		}
		Expect(k8sClient.Create(ctx, policy)).To(Succeed())
		return policy
	}

	Context("handleError", func() {
		It("should set TypeResolvedRefs=False with TargetNotFound when message is 'Failed to resolve target'", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := createTestAccessPolicy(policyName, "HTTPRoute", "test-route")
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			testErr := fmt.Errorf("httproute not found")
			r := newAccessPolicyReconciler()
			result, err := r.handleError(ctx, policy, testErr, "Failed to resolve target")

			By("Verifying the original error is returned")
			Expect(err).To(Equal(testErr))

			By("Verifying RequeueAfter is 30 seconds")
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			By("Verifying TypeResolvedRefs=False with TargetNotFound reason")
			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			cond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeResolvedRefs)
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionFalse))
			Expect(cond.Reason).To(Equal(tunnelsv1.ReasonTargetNotFound))
			Expect(cond.Message).To(ContainSubstring("Failed to resolve target"))
		})

		It("should set TypeProgrammed=False with CloudflareError for 'Failed to get Cloudflare client'", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := createTestAccessPolicy(policyName, "HTTPRoute", "test-route")
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			testErr := fmt.Errorf("no credentials")
			r := newAccessPolicyReconciler()
			result, err := r.handleError(ctx, policy, testErr, "Failed to get Cloudflare client")

			Expect(err).To(Equal(testErr))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			cond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeProgrammed)
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionFalse))
			Expect(cond.Reason).To(Equal(tunnelsv1.ReasonCloudflareError))
		})

		It("should set TypeProgrammed=False with CloudflareError for 'Failed to create access application'", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := createTestAccessPolicy(policyName, "HTTPRoute", "test-route")
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			testErr := fmt.Errorf("cloudflare API error")
			r := newAccessPolicyReconciler()
			result, err := r.handleError(ctx, policy, testErr, "Failed to create access application")

			Expect(err).To(Equal(testErr))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			cond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeProgrammed)
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionFalse))
			Expect(cond.Reason).To(Equal(tunnelsv1.ReasonCloudflareError))
		})

		It("should set TypeProgrammed=False with CloudflareError for 'Failed to create access policy'", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := createTestAccessPolicy(policyName, "HTTPRoute", "test-route")
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			testErr := fmt.Errorf("policy creation failed")
			r := newAccessPolicyReconciler()
			result, err := r.handleError(ctx, policy, testErr, "Failed to create access policy")

			Expect(err).To(Equal(testErr))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			cond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeProgrammed)
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionFalse))
			Expect(cond.Reason).To(Equal(tunnelsv1.ReasonCloudflareError))
		})

		It("should set TypeAccepted=False with Invalid for unrecognised messages", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := createTestAccessPolicy(policyName, "HTTPRoute", "test-route")
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			testErr := fmt.Errorf("some unexpected error")
			r := newAccessPolicyReconciler()
			result, err := r.handleError(ctx, policy, testErr, "Some unexpected failure")

			Expect(err).To(Equal(testErr))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			cond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeAccepted)
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionFalse))
			Expect(cond.Reason).To(Equal(tunnelsv1.ReasonInvalid))
		})

		It("should return error even when status update fails (nonexistent policy)", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			// Do not create this policy in k8s — status update will fail
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      policyName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  "test-route",
					},
					Application: tunnelsv1.ApplicationConfig{
						Name: "Test App",
					},
				},
			}

			testErr := fmt.Errorf("original error")
			r := newAccessPolicyReconciler()
			result, err := r.handleError(ctx, policy, testErr, "Failed to resolve target")

			By("Verifying the original error is still returned despite status update failure")
			Expect(err).To(Equal(testErr))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})
	})

	Context("buildApplicationConfig", func() {
		r := &CloudflareAccessPolicyReconciler{}

		It("should use defaults when Name, Type, and SessionDuration are empty", func() {
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "my-policy",
					Namespace: "my-ns",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					Application: tunnelsv1.ApplicationConfig{
						// Name, Type, SessionDuration all empty
					},
				},
			}

			config := r.buildApplicationConfig(policy, "example.com")

			Expect(config.Name).To(Equal("access-my-ns-my-policy"))
			Expect(config.Type).To(Equal("self_hosted"))
			Expect(config.SessionDuration).To(Equal("24h"))
			Expect(config.Domain).To(Equal("example.com"))
		})

		It("should use provided values when all fields are set", func() {
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "my-policy",
					Namespace: "my-ns",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					Application: tunnelsv1.ApplicationConfig{
						Name:                   "My Custom App",
						Type:                   "saas",
						SessionDuration:        "8h",
						AutoRedirectToIdentity: true,
						EnableBindingCookie:    true,
						CustomDenyMessage:      "Access denied",
						CustomDenyURL:          "https://example.com/denied",
					},
				},
			}

			config := r.buildApplicationConfig(policy, "app.example.com")

			Expect(config.Name).To(Equal("My Custom App"))
			Expect(config.Type).To(Equal("saas"))
			Expect(config.SessionDuration).To(Equal("8h"))
			Expect(config.AutoRedirectToIdentity).To(BeTrue())
			Expect(config.EnableBindingCookie).To(BeTrue())
			Expect(config.CustomDenyMessage).To(Equal("Access denied"))
			Expect(config.CustomDenyURL).To(Equal("https://example.com/denied"))
		})

		It("should include CORS headers when CORSHeaders is set", func() {
			maxAge := 3600
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "my-policy",
					Namespace: "my-ns",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					Application: tunnelsv1.ApplicationConfig{
						Name: "Test App",
						CORSHeaders: &tunnelsv1.CORSHeaders{
							AllowAllOrigins:  true,
							AllowedOrigins:   []string{"https://example.com"},
							AllowedMethods:   []string{"GET", "POST"},
							AllowedHeaders:   []string{"Content-Type"},
							AllowCredentials: true,
							MaxAge:           &maxAge,
						},
					},
				},
			}

			config := r.buildApplicationConfig(policy, "app.example.com")

			Expect(config.CORSHeaders).NotTo(BeNil())
			Expect(config.CORSHeaders.AllowAllOrigins).To(BeTrue())
			Expect(config.CORSHeaders.AllowedOrigins).To(ContainElement("https://example.com"))
			Expect(config.CORSHeaders.AllowedMethods).To(ContainElements("GET", "POST"))
			Expect(config.CORSHeaders.AllowCredentials).To(BeTrue())
			Expect(config.CORSHeaders.MaxAge).To(Equal(3600))
		})

		It("should not include CORSHeaders when CORSHeaders is nil", func() {
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "my-policy",
					Namespace: "my-ns",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					Application: tunnelsv1.ApplicationConfig{
						Name:        "Test App",
						CORSHeaders: nil,
					},
				},
			}

			config := r.buildApplicationConfig(policy, "app.example.com")

			Expect(config.CORSHeaders).To(BeNil())
		})
	})

	Context("buildPolicyConfig", func() {
		r := &CloudflareAccessPolicyReconciler{}
		policy := &tunnelsv1.CloudflareAccessPolicy{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "my-policy",
				Namespace: "my-ns",
			},
		}

		It("should use default name 'policy-N' when Name is empty", func() {
			p := tunnelsv1.AccessPolicy{
				Name:     "",
				Decision: "allow",
				Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
			}

			config := r.buildPolicyConfig(policy, p, 2)

			Expect(config.Name).To(Equal("policy-2"))
		})

		It("should use default decision 'allow' when Decision is empty", func() {
			p := tunnelsv1.AccessPolicy{
				Name:     "my-rule",
				Decision: "",
				Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
			}

			config := r.buildPolicyConfig(policy, p, 0)

			Expect(config.Decision).To(Equal("allow"))
		})

		It("should use ExternalPolicyID as a group rule when set", func() {
			p := tunnelsv1.AccessPolicy{
				Name:             "external-ref",
				Decision:         "allow",
				ExternalPolicyID: "ext-policy-abc123",
				Rules:            []tunnelsv1.AccessPolicyRule{{Everyone: true}},
			}

			config := r.buildPolicyConfig(policy, p, 0)

			Expect(config.Include).To(HaveLen(1))
			Expect(config.Include[0].GroupID).To(Equal("ext-policy-abc123"))
		})

		It("should convert inline rules to Include rules when ExternalPolicyID is empty", func() {
			p := tunnelsv1.AccessPolicy{
				Name:     "inline-rule",
				Decision: "allow",
				Rules: []tunnelsv1.AccessPolicyRule{
					{
						Everyone:     false,
						Emails:       []string{"user@example.com"},
						EmailDomains: []string{"example.com"},
						IPRanges:     []string{"10.0.0.0/8"},
					},
				},
			}

			config := r.buildPolicyConfig(policy, p, 0)

			Expect(config.Include).To(HaveLen(1))
			Expect(config.Include[0].Emails).To(ContainElement("user@example.com"))
			Expect(config.Include[0].EmailDomains).To(ContainElement("example.com"))
			Expect(config.Include[0].IPRanges).To(ContainElement("10.0.0.0/8"))
			Expect(config.Include[0].GroupID).To(BeEmpty())
		})

		It("should preserve Name and Decision from policy spec", func() {
			p := tunnelsv1.AccessPolicy{
				Name:     "custom-name",
				Decision: "deny",
				Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
			}

			config := r.buildPolicyConfig(policy, p, 0)

			Expect(config.Name).To(Equal("custom-name"))
			Expect(config.Decision).To(Equal("deny"))
		})
	})

	Context("resolveTargetDomain", func() {
		It("should return error for unsupported targetRef kind", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      policyName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "UnsupportedKind",
						Name:  "test",
					},
					Application: tunnelsv1.ApplicationConfig{Name: "Test"},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			r := newAccessPolicyReconciler()
			_, err := r.resolveTargetDomain(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("unsupported targetRef kind"))
		})

		It("should return error when HTTPRoute has no hostnames", func() {
			routeName := fmt.Sprintf("ap-cov-route-%d", time.Now().UnixNano())
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      routeName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{Name: "test-gateway"},
						},
					},
					// No hostnames set
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, route)
			})

			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      policyName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  routeName,
					},
					Application: tunnelsv1.ApplicationConfig{Name: "Test"},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			r := newAccessPolicyReconciler()
			_, err := r.resolveTargetDomain(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("HTTPRoute has no hostnames"))
		})

		It("should return error for Gateway target without explicit application.domain", func() {
			gwName := fmt.Sprintf("ap-cov-gw-%d", time.Now().UnixNano())
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      policyName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "Gateway",
						Name:  gwName,
					},
					Application: tunnelsv1.ApplicationConfig{
						Name:   "Test App",
						Domain: "", // No domain set
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			r := newAccessPolicyReconciler()
			_, err := r.resolveTargetDomain(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("Gateway target requires explicit application.domain"))
		})

		It("should use application.domain when Gateway target has it set", func() {
			gwName := fmt.Sprintf("ap-cov-gw-%d", time.Now().UnixNano())
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      policyName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "Gateway",
						Name:  gwName,
					},
					Application: tunnelsv1.ApplicationConfig{
						Name:   "Test App",
						Domain: "my-app.example.com",
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			r := newAccessPolicyReconciler()
			domain, err := r.resolveTargetDomain(ctx, policy)
			Expect(err).NotTo(HaveOccurred())
			Expect(domain).To(Equal("my-app.example.com"))
		})

		It("should use cross-namespace targetRef when Namespace is set", func() {
			routeName := fmt.Sprintf("ap-cov-route-%d", time.Now().UnixNano())
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      routeName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{{Name: "test-gw"}},
					},
					Hostnames: []gatewayv1.Hostname{"cross-ns.example.com"},
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, route) })

			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			ns := gatewayv1.Namespace("default")
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      policyName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group:     "gateway.networking.k8s.io",
						Kind:      "HTTPRoute",
						Name:      routeName,
						Namespace: &ns,
					},
					Application: tunnelsv1.ApplicationConfig{Name: "Test"},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy))
				}, time.Second*5).Should(BeTrue())
			})

			r := newAccessPolicyReconciler()
			domain, err := r.resolveTargetDomain(ctx, policy)
			Expect(err).NotTo(HaveOccurred())
			Expect(domain).To(Equal("cross-ns.example.com"))
		})
	})

	Context("resolveTargetGateway", func() {
		It("should return error for unsupported targetRef kind", func() {
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test",
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Kind: "ServiceMesh",
						Name: "test",
					},
				},
			}

			r := newAccessPolicyReconciler()
			_, err := r.resolveTargetGateway(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("unsupported targetRef kind"))
		})

		It("should return error when Gateway does not exist", func() {
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test",
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Kind: "Gateway",
						Name: fmt.Sprintf("nonexistent-gw-%d", time.Now().UnixNano()),
					},
				},
			}

			r := newAccessPolicyReconciler()
			_, err := r.resolveTargetGateway(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get Gateway"))
		})

		It("should return existing Gateway when found", func() {
			gwName := fmt.Sprintf("ap-cov-gw-%d", time.Now().UnixNano())
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test",
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Kind: "Gateway",
						Name: gwName,
					},
				},
			}

			r := newAccessPolicyReconciler()
			result, err := r.resolveTargetGateway(ctx, policy)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Name).To(Equal(gwName))
		})

		It("should return error when HTTPRoute has no Cloudflare parent Gateway", func() {
			routeName := fmt.Sprintf("ap-cov-route-%d", time.Now().UnixNano())
			// Create HTTPRoute with a parent that is not a cloudflare gateway
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      routeName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{Name: "nonexistent-gateway"},
						},
					},
					Hostnames: []gatewayv1.Hostname{"test.example.com"},
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, route) })

			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test",
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Kind: "HTTPRoute",
						Name: routeName,
					},
				},
			}

			r := newAccessPolicyReconciler()
			_, err := r.resolveTargetGateway(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("no Cloudflare Gateway found for HTTPRoute"))
		})

		It("should find Cloudflare Gateway via HTTPRoute parent reference", func() {
			gwName := fmt.Sprintf("ap-cov-gw-%d", time.Now().UnixNano())
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			routeName := fmt.Sprintf("ap-cov-route-%d", time.Now().UnixNano())
			ns := gatewayv1.Namespace("default")
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      routeName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{
								Name:      gatewayv1.ObjectName(gwName),
								Namespace: &ns,
							},
						},
					},
					Hostnames: []gatewayv1.Hostname{"test.example.com"},
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, route) })

			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test",
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Kind: "HTTPRoute",
						Name: routeName,
					},
				},
			}

			r := newAccessPolicyReconciler()
			result, err := r.resolveTargetGateway(ctx, policy)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Name).To(Equal(gwName))
		})
	})

	Context("handleDeletion", func() {
		It("should return immediately when finalizer is not present", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      policyName,
					Namespace: "default",
					// No finalizer
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Kind: "HTTPRoute",
						Name: "test",
					},
					Application: tunnelsv1.ApplicationConfig{Name: "Test"},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, policy)
			})

			r := newAccessPolicyReconciler()
			result, err := r.handleDeletion(ctx, policy)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeFalse())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))
		})

		It("should remove finalizer and skip Cloudflare cleanup when getCloudflareClient fails", func() {
			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       policyName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  fmt.Sprintf("nonexistent-route-%d", time.Now().UnixNano()),
					},
					Application: tunnelsv1.ApplicationConfig{Name: "Test App"},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				cleanup := &tunnelsv1.CloudflareAccessPolicy{}
				err := k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, cleanup)
				if err == nil {
					cleanup.Finalizers = []string{}
					_ = k8sClient.Update(ctx, cleanup)
					_ = k8sClient.Delete(ctx, cleanup)
				}
			})

			By("Verifying the finalizer is present")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())
			Expect(policy.Finalizers).To(ContainElement(AccessPolicyFinalizerName))

			By("Calling handleDeletion - getCloudflareClient will fail because route doesn't exist")
			r := newAccessPolicyReconciler()
			result, err := r.handleDeletion(ctx, policy)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeFalse())

			By("Verifying the finalizer was removed despite Cloudflare client failure")
			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())
			Expect(updated.Finalizers).NotTo(ContainElement(AccessPolicyFinalizerName))
		})

		It("should requeue when DeleteAccessApplication fails", func() {
			// Set up a Gateway with account ID annotation
			gwName := fmt.Sprintf("ap-cov-gw-%d", time.Now().UnixNano())
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
					Annotations: map[string]string{
						GatewayAnnotationAccountID: "test-account-id",
					},
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			// Create a GatewayClass with a valid parametersRef
			secretName := fmt.Sprintf("ap-cov-secret-%d", time.Now().UnixNano())
			secret := &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      secretName,
					Namespace: "default",
				},
				Type: corev1.SecretTypeOpaque,
				Data: map[string][]byte{
					"CLOUDFLARE_API_TOKEN":  []byte("fake-token"),
					"CLOUDFLARE_ACCOUNT_ID": []byte("test-account-id"),
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			gcName := fmt.Sprintf("ap-cov-gc-%d", time.Now().UnixNano())
			gcNs := gatewayv1.Namespace("default")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "core",
						Kind:      "Secret",
						Name:      secretName,
						Namespace: &gcNs,
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			// Update the gateway to use the GatewayClass we just created
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, gw)).To(Succeed())
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			// Create HTTPRoute pointing to the gateway
			routeName := fmt.Sprintf("ap-cov-route-%d", time.Now().UnixNano())
			routeNs := gatewayv1.Namespace("default")
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      routeName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{
								Name:      gatewayv1.ObjectName(gwName),
								Namespace: &routeNs,
							},
						},
					},
					Hostnames: []gatewayv1.Hostname{"test.example.com"},
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, route) })

			policyName := fmt.Sprintf("ap-cov-%d", time.Now().UnixNano())
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       policyName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  routeName,
					},
					Application: tunnelsv1.ApplicationConfig{Name: "Test App"},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				cleanup := &tunnelsv1.CloudflareAccessPolicy{}
				err := k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, cleanup)
				if err == nil {
					cleanup.Finalizers = []string{}
					_ = k8sClient.Update(ctx, cleanup)
					_ = k8sClient.Delete(ctx, cleanup)
				}
			})

			// Set application ID in status so deletion path is reached
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())
			policy.Status.ApplicationID = "app-to-delete"
			Expect(k8sClient.Status().Update(ctx, policy)).To(Succeed())

			By("Reloading policy after status update")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			By("Calling handleDeletion - note: this will attempt a real CF API call with a fake token and fail, which we treat as the error path being covered")
			// The getCloudflareClient will succeed (credentials exist) but DeleteAccessApplication
			// will fail because the token is fake. This exercises the error branch in handleDeletion
			// where DeleteAccessApplication fails and the controller schedules a retry.
			r := newAccessPolicyReconciler()
			result, _ := r.handleDeletion(ctx, policy)
			// The controller returns RequeueAfter(30s) when DeleteAccessApplication fails.
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})
	})

	// -----------------------------------------------------------------------
	// getCloudflareClient credential resolution
	// -----------------------------------------------------------------------
	Context("getCloudflareClient", func() {
		// Helper to build a policy targeting a Gateway by name
		makeGatewayTargetPolicy := func(policyName, gwName string) *tunnelsv1.CloudflareAccessPolicy {
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      policyName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "Gateway",
						Name:  gwName,
					},
					Application: tunnelsv1.ApplicationConfig{
						Name:   "Test App",
						Domain: "test.example.com",
					},
					Policies: []tunnelsv1.AccessPolicy{
						{Decision: "allow", Rules: []tunnelsv1.AccessPolicyRule{{Everyone: true}}},
					},
				},
			}
			return policy
		}

		createGatewayWithAccountID := func(name, namespace, gatewayClassName string) *gatewayv1.Gateway {
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      name,
					Namespace: namespace,
					Annotations: map[string]string{
						GatewayAnnotationAccountID: "test-account-id",
					},
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: gatewayv1.ObjectName(gatewayClassName),
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			return gw
		}

		createGatewayClass := func(name, secretName, secretNamespace string) *gatewayv1.GatewayClass {
			gcNs := gatewayv1.Namespace(secretNamespace)
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: name},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "core",
						Kind:      "Secret",
						Name:      secretName,
						Namespace: &gcNs,
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			return gc
		}

		createCredentialsSecret := func(name, namespace string, token []byte) *corev1.Secret {
			secret := &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      name,
					Namespace: namespace,
				},
				Type: corev1.SecretTypeOpaque,
				Data: map[string][]byte{
					"CLOUDFLARE_API_TOKEN": token,
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())
			return secret
		}

		It("should return error when GatewayClass does not exist", func() {
			gwName := fmt.Sprintf("gw-no-class-%d", time.Now().UnixNano())
			gcName := fmt.Sprintf("nonexistent-gc-%d", time.Now().UnixNano())
			gw := createGatewayWithAccountID(gwName, "default", gcName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cred-%d", time.Now().UnixNano())
			policy := makeGatewayTargetPolicy(policyName, gwName)

			r := newAccessPolicyReconciler()
			_, _, err := r.getCloudflareClient(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get GatewayClass"))
		})

		It("should return error when GatewayClass has no parametersRef", func() {
			gcName := fmt.Sprintf("gc-no-params-%d", time.Now().UnixNano())
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					// ParametersRef intentionally nil
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gwName := fmt.Sprintf("gw-no-params-%d", time.Now().UnixNano())
			gw := createGatewayWithAccountID(gwName, "default", gcName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cred-%d", time.Now().UnixNano())
			policy := makeGatewayTargetPolicy(policyName, gwName)

			r := newAccessPolicyReconciler()
			_, _, err := r.getCloudflareClient(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("GatewayClass has no parametersRef"))
		})

		It("should return error when parametersRef.Kind is not 'Secret'", func() {
			gcName := fmt.Sprintf("gc-bad-kind-%d", time.Now().UnixNano())
			gcNs := gatewayv1.Namespace("default")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "core",
						Kind:      "ConfigMap", // wrong kind
						Name:      "some-config",
						Namespace: &gcNs,
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gwName := fmt.Sprintf("gw-bad-kind-%d", time.Now().UnixNano())
			gw := createGatewayWithAccountID(gwName, "default", gcName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cred-%d", time.Now().UnixNano())
			policy := makeGatewayTargetPolicy(policyName, gwName)

			r := newAccessPolicyReconciler()
			_, _, err := r.getCloudflareClient(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("invalid parametersRef"))
		})

		It("should return error when parametersRef.Namespace is nil", func() {
			gcName := fmt.Sprintf("gc-no-ns-%d", time.Now().UnixNano())
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "core",
						Kind:      "Secret",
						Name:      "my-secret",
						Namespace: nil, // nil namespace
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gwName := fmt.Sprintf("gw-no-ns-%d", time.Now().UnixNano())
			gw := createGatewayWithAccountID(gwName, "default", gcName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cred-%d", time.Now().UnixNano())
			policy := makeGatewayTargetPolicy(policyName, gwName)

			r := newAccessPolicyReconciler()
			_, _, err := r.getCloudflareClient(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("invalid parametersRef"))
		})

		It("should return error when credentials Secret does not exist", func() {
			gcName := fmt.Sprintf("gc-no-secret-%d", time.Now().UnixNano())
			gc := createGatewayClass(gcName, fmt.Sprintf("missing-secret-%d", time.Now().UnixNano()), "default")
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gwName := fmt.Sprintf("gw-no-secret-%d", time.Now().UnixNano())
			gw := createGatewayWithAccountID(gwName, "default", gcName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cred-%d", time.Now().UnixNano())
			policy := makeGatewayTargetPolicy(policyName, gwName)

			r := newAccessPolicyReconciler()
			_, _, err := r.getCloudflareClient(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get credentials secret"))
		})

		It("should return error when Secret is missing CLOUDFLARE_API_TOKEN key", func() {
			secretName := fmt.Sprintf("secret-no-token-%d", time.Now().UnixNano())
			secret := &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      secretName,
					Namespace: "default",
				},
				Type: corev1.SecretTypeOpaque,
				Data: map[string][]byte{
					"OTHER_KEY": []byte("some-value"),
					// CLOUDFLARE_API_TOKEN deliberately missing
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			gcName := fmt.Sprintf("gc-no-token-%d", time.Now().UnixNano())
			gc := createGatewayClass(gcName, secretName, "default")
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gwName := fmt.Sprintf("gw-no-token-%d", time.Now().UnixNano())
			gw := createGatewayWithAccountID(gwName, "default", gcName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cred-%d", time.Now().UnixNano())
			policy := makeGatewayTargetPolicy(policyName, gwName)

			r := newAccessPolicyReconciler()
			_, _, err := r.getCloudflareClient(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("credentials secret missing CLOUDFLARE_API_TOKEN"))
		})

		It("should return a client and the account ID when all credentials are valid", func() {
			secretName := fmt.Sprintf("secret-valid-%d", time.Now().UnixNano())
			secret := createCredentialsSecret(secretName, "default", []byte("fake-api-token"))
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			gcName := fmt.Sprintf("gc-valid-%d", time.Now().UnixNano())
			gc := createGatewayClass(gcName, secretName, "default")
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gwName := fmt.Sprintf("gw-valid-%d", time.Now().UnixNano())
			gw := createGatewayWithAccountID(gwName, "default", gcName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			policyName := fmt.Sprintf("ap-cred-%d", time.Now().UnixNano())
			policy := makeGatewayTargetPolicy(policyName, gwName)

			r := newAccessPolicyReconciler()
			cfClient, accountID, err := r.getCloudflareClient(ctx, policy)
			Expect(err).NotTo(HaveOccurred())
			Expect(cfClient).NotTo(BeNil())
			Expect(accountID).To(Equal("test-account-id"))
		})
	})

	// -----------------------------------------------------------------------
	// handleCreateOrUpdate — condition-setting flow
	// -----------------------------------------------------------------------
	Context("handleCreateOrUpdate conditions", func() {
		// Helper to build the full infrastructure needed for handleCreateOrUpdate
		// to reach the Cloudflare API call phase (which will fail with a fake token)
		buildFullInfra := func(policyName string) (
			gw *gatewayv1.Gateway,
			gc *gatewayv1.GatewayClass,
			secret *corev1.Secret,
			route *gatewayv1.HTTPRoute,
			policy *tunnelsv1.CloudflareAccessPolicy,
		) {
			suffix := fmt.Sprintf("%d", time.Now().UnixNano())

			secretName := fmt.Sprintf("secret-full-%s", suffix)
			secret = &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      secretName,
					Namespace: "default",
				},
				Type: corev1.SecretTypeOpaque,
				Data: map[string][]byte{
					"CLOUDFLARE_API_TOKEN": []byte("fake-api-token-for-testing"),
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())

			gcName := fmt.Sprintf("gc-full-%s", suffix)
			gcNs := gatewayv1.Namespace("default")
			gc = &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "core",
						Kind:      "Secret",
						Name:      secretName,
						Namespace: &gcNs,
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			gwName := fmt.Sprintf("gw-full-%s", suffix)
			gw = &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
					Annotations: map[string]string{
						GatewayAnnotationAccountID: "test-account-id",
					},
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: gatewayv1.ObjectName(gcName),
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())

			routeName := fmt.Sprintf("route-full-%s", suffix)
			routeNs := gatewayv1.Namespace("default")
			route = &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      routeName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{
								Name:      gatewayv1.ObjectName(gwName),
								Namespace: &routeNs,
							},
						},
					},
					Hostnames: []gatewayv1.Hostname{"app.example.com"},
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())

			policy = &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       policyName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  routeName,
					},
					Application: tunnelsv1.ApplicationConfig{
						Name:            "Test App",
						SessionDuration: "24h",
						Type:            "self_hosted",
					},
					Policies: []tunnelsv1.AccessPolicy{
						{
							Name:     "allow-all",
							Decision: "allow",
							Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())

			return gw, gc, secret, route, policy
		}

		It("should set TypeAccepted=True immediately even when CF API call fails", func() {
			policyName := fmt.Sprintf("ap-flow-%d", time.Now().UnixNano())
			gw, gc, secret, route, policy := buildFullInfra(policyName)
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, secret)
				_ = k8sClient.Delete(ctx, gc)
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
				_ = k8sClient.Delete(ctx, route)
				cleanup := &tunnelsv1.CloudflareAccessPolicy{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, cleanup); err == nil {
					cleanup.Finalizers = []string{}
					_ = k8sClient.Update(ctx, cleanup)
					_ = k8sClient.Delete(ctx, cleanup)
				}
			})

			r := newAccessPolicyReconciler()
			// handleCreateOrUpdate will fail at the CF API call (fake token), but
			// TypeAccepted should still be set to True (it's set before the API call)
			_, _ = r.handleCreateOrUpdate(ctx, policy)

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			acceptedCond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeAccepted)
			Expect(acceptedCond).NotTo(BeNil())
			Expect(acceptedCond.Status).To(Equal(metav1.ConditionTrue))
			Expect(acceptedCond.Reason).To(Equal(tunnelsv1.ReasonAccepted))
		})

		It("should set TypeResolvedRefs=True when target domain resolves (before CF API call)", func() {
			policyName := fmt.Sprintf("ap-flow-%d", time.Now().UnixNano())
			gw, gc, secret, route, policy := buildFullInfra(policyName)
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, secret)
				_ = k8sClient.Delete(ctx, gc)
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
				_ = k8sClient.Delete(ctx, route)
				cleanup := &tunnelsv1.CloudflareAccessPolicy{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, cleanup); err == nil {
					cleanup.Finalizers = []string{}
					_ = k8sClient.Update(ctx, cleanup)
					_ = k8sClient.Delete(ctx, cleanup)
				}
			})

			r := newAccessPolicyReconciler()
			// Even though CF API will fail, ResolvedRefs should be set when domain is found
			_, _ = r.handleCreateOrUpdate(ctx, policy)

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			resolvedCond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeResolvedRefs)
			Expect(resolvedCond).NotTo(BeNil())
			Expect(resolvedCond.Status).To(Equal(metav1.ConditionTrue))
			Expect(resolvedCond.Reason).To(Equal(tunnelsv1.ReasonAccepted))
			Expect(resolvedCond.Message).To(ContainSubstring("app.example.com"))
		})

		It("should set TypeProgrammed=False with CloudflareError when CreateAccessApplication fails", func() {
			policyName := fmt.Sprintf("ap-flow-%d", time.Now().UnixNano())
			gw, gc, secret, route, policy := buildFullInfra(policyName)
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, secret)
				_ = k8sClient.Delete(ctx, gc)
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
				_ = k8sClient.Delete(ctx, route)
				cleanup := &tunnelsv1.CloudflareAccessPolicy{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, cleanup); err == nil {
					cleanup.Finalizers = []string{}
					_ = k8sClient.Update(ctx, cleanup)
					_ = k8sClient.Delete(ctx, cleanup)
				}
			})

			r := newAccessPolicyReconciler()
			// ApplicationID is empty in status → takes the create-application path
			// The fake token causes the CF API call to fail
			result, err := r.handleCreateOrUpdate(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			programmedCond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeProgrammed)
			Expect(programmedCond).NotTo(BeNil())
			Expect(programmedCond.Status).To(Equal(metav1.ConditionFalse))
			Expect(programmedCond.Reason).To(Equal(tunnelsv1.ReasonCloudflareError))
		})

		It("should take update-application path when ApplicationID is pre-set in status", func() {
			policyName := fmt.Sprintf("ap-flow-%d", time.Now().UnixNano())
			gw, gc, secret, route, policy := buildFullInfra(policyName)
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, secret)
				_ = k8sClient.Delete(ctx, gc)
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
				_ = k8sClient.Delete(ctx, route)
				cleanup := &tunnelsv1.CloudflareAccessPolicy{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, cleanup); err == nil {
					cleanup.Finalizers = []string{}
					_ = k8sClient.Update(ctx, cleanup)
					_ = k8sClient.Delete(ctx, cleanup)
				}
			})

			By("Pre-setting ApplicationID in status to trigger update path")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())
			policy.Status.ApplicationID = "existing-app-id-12345"
			Expect(k8sClient.Status().Update(ctx, policy)).To(Succeed())

			By("Reloading policy after status update")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			r := newAccessPolicyReconciler()
			// ApplicationID is non-empty → takes UpdateAccessApplication path (fails with fake token)
			result, err := r.handleCreateOrUpdate(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			programmedCond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeProgrammed)
			Expect(programmedCond).NotTo(BeNil())
			Expect(programmedCond.Status).To(Equal(metav1.ConditionFalse))
			Expect(programmedCond.Reason).To(Equal(tunnelsv1.ReasonCloudflareError))
			Expect(programmedCond.Message).To(ContainSubstring("Failed to update access application"))
		})

		It("should set TypeResolvedRefs=False when target HTTPRoute does not exist", func() {
			policyName := fmt.Sprintf("ap-flow-%d", time.Now().UnixNano())
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       policyName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  fmt.Sprintf("nonexistent-route-%d", time.Now().UnixNano()),
					},
					Application: tunnelsv1.ApplicationConfig{
						Name: "Test App",
					},
					Policies: []tunnelsv1.AccessPolicy{
						{Decision: "allow", Rules: []tunnelsv1.AccessPolicyRule{{Everyone: true}}},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			DeferCleanup(func() {
				cleanup := &tunnelsv1.CloudflareAccessPolicy{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, cleanup); err == nil {
					cleanup.Finalizers = []string{}
					_ = k8sClient.Update(ctx, cleanup)
					_ = k8sClient.Delete(ctx, cleanup)
				}
			})

			r := newAccessPolicyReconciler()
			result, err := r.handleCreateOrUpdate(ctx, policy)
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updated)).To(Succeed())

			By("TypeAccepted should be True — it is set before domain resolution attempt")
			acceptedCond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeAccepted)
			Expect(acceptedCond).NotTo(BeNil())
			Expect(acceptedCond.Status).To(Equal(metav1.ConditionTrue))

			By("TypeResolvedRefs should be False — domain resolution failed")
			resolvedCond := apimeta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeResolvedRefs)
			Expect(resolvedCond).NotTo(BeNil())
			Expect(resolvedCond.Status).To(Equal(metav1.ConditionFalse))
			Expect(resolvedCond.Reason).To(Equal(tunnelsv1.ReasonTargetNotFound))
		})
	})
})
