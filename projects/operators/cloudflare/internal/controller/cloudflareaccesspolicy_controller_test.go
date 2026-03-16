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
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("CloudflareAccessPolicy Controller", func() {
	Context("When reconciling a CloudflareAccessPolicy", func() {
		var (
			ctx                context.Context
			resourceName       string
			typeNamespacedName types.NamespacedName
		)

		BeforeEach(func() {
			ctx = context.Background()
			resourceName = fmt.Sprintf("test-policy-%d", time.Now().UnixNano())
			typeNamespacedName = types.NamespacedName{
				Name:      resourceName,
				Namespace: "default",
			}
		})

		AfterEach(func() {
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			err := k8sClient.Get(ctx, typeNamespacedName, policy)
			if err == nil {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, typeNamespacedName, policy))
				}, time.Second*5).Should(BeTrue())
			}
		})

		newReconciler := func() *CloudflareAccessPolicyReconciler {
			return &CloudflareAccessPolicyReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
				tracer: telemetry.GetTracer("test-accesspolicy"),
			}
		}

		createAccessPolicy := func(targetKind, targetName string) *tunnelsv1.CloudflareAccessPolicy {
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
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
							Rules: []tunnelsv1.AccessPolicyRule{
								{Everyone: true},
							},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())
			return policy
		}

		It("should return nil when CloudflareAccessPolicy is not found", func() {
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{
				NamespacedName: types.NamespacedName{Name: "does-not-exist", Namespace: "default"},
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))
		})

		It("should add finalizer on first reconcile", func() {
			By("Creating a CloudflareAccessPolicy")
			createAccessPolicy("HTTPRoute", "my-route")

			By("Reconciling — should add finalizer")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking that finalizer was added")
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, policy)).To(Succeed())
			Expect(policy.Finalizers).To(ContainElement(AccessPolicyFinalizerName))
		})

		It("should handle deletion when no target exists (removes finalizer)", func() {
			By("Creating a CloudflareAccessPolicy with finalizer")
			policy := createAccessPolicy("HTTPRoute", "nonexistent-route")

			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Deleting the policy")
			Expect(k8sClient.Delete(ctx, policy)).To(Succeed())

			By("Reconciling deletion — should remove finalizer even without Gateway client")
			_, err = r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking resource is fully deleted")
			Eventually(func() bool {
				return errors.IsNotFound(k8sClient.Get(ctx, typeNamespacedName, policy))
			}, time.Second*5).Should(BeTrue())
		})

		It("should set ResolvedRefs=False when target HTTPRoute is not found", func() {
			By("Creating a CloudflareAccessPolicy with finalizer already set")
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  "nonexistent-httproute",
					},
					Application: tunnelsv1.ApplicationConfig{
						Name: "Test App",
					},
					Policies: []tunnelsv1.AccessPolicy{
						{
							Decision: "allow",
							Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			By("Checking ResolvedRefs condition is False")
			updated := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			resolvedRefs := meta.FindStatusCondition(updated.Status.Conditions, tunnelsv1.TypeResolvedRefs)
			Expect(resolvedRefs).NotTo(BeNil())
			Expect(resolvedRefs.Status).To(Equal(metav1.ConditionFalse))
			Expect(resolvedRefs.Reason).To(Equal(tunnelsv1.ReasonTargetNotFound))
		})

		It("should set Programmed=False when Cloudflare client cannot be obtained (no Gateway)", func() {
			By("Creating an HTTPRoute as target (but no parent Gateway)")
			routeName := fmt.Sprintf("test-route-%d", time.Now().UnixNano())
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      routeName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					Hostnames: []gatewayv1.Hostname{"test.example.com"},
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: "backend",
											Port: ptr.To(gatewayv1.PortNumber(8080)),
										},
									},
								},
							},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())
			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})

			By("Creating a CloudflareAccessPolicy targeting the HTTPRoute (with finalizer)")
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
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
						Name: "Test App",
					},
					Policies: []tunnelsv1.AccessPolicy{
						{
							Decision: "allow",
							Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())

			By("Reconciling — target resolves but no Cloudflare Gateway exists")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})

		It("should set Programmed=False when target Gateway exists but missing account ID", func() {
			By("Creating a cloudflare Gateway without account ID annotation")
			gwName := fmt.Sprintf("cf-gw-noacct-%d", time.Now().UnixNano())
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

			By("Creating a CloudflareAccessPolicy targeting the Gateway (with finalizer)")
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
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
						{
							Decision: "allow",
							Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())

			By("Reconciling — Gateway found but no account ID → Cloudflare client creation fails")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})

		It("should return error for unsupported targetRef kind during resolveTargetDomain", func() {
			By("Creating a CloudflareAccessPolicy with unsupported kind (with finalizer)")
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "GatewayClass",
						Name:  "some-class",
					},
					Application: tunnelsv1.ApplicationConfig{},
					Policies: []tunnelsv1.AccessPolicy{
						{
							Decision: "allow",
							Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())

			By("Reconciling — should fail with unsupported targetRef kind")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("unsupported targetRef kind"))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})

		It("should return error when HTTPRoute has no hostnames", func() {
			By("Creating an HTTPRoute without hostnames")
			routeName := fmt.Sprintf("no-hostname-route-%d", time.Now().UnixNano())
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      routeName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: "backend",
											Port: ptr.To(gatewayv1.PortNumber(8080)),
										},
									},
								},
							},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())
			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})

			By("Creating policy targeting the no-hostname route")
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "HTTPRoute",
						Name:  routeName,
					},
					Application: tunnelsv1.ApplicationConfig{},
					Policies: []tunnelsv1.AccessPolicy{
						{
							Decision: "allow",
							Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())

			By("Reconciling — should fail because HTTPRoute has no hostnames")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("no hostnames"))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})

		It("should return error when targeting a Gateway without explicit domain", func() {
			By("Creating a cloudflare Gateway")
			gwName := fmt.Sprintf("gw-nodomain-%d", time.Now().UnixNano())
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

			By("Creating a policy targeting the Gateway with no domain")
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{AccessPolicyFinalizerName},
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{
						Group: "gateway.networking.k8s.io",
						Kind:  "Gateway",
						Name:  gwName,
					},
					Application: tunnelsv1.ApplicationConfig{
						// Domain intentionally not set
					},
					Policies: []tunnelsv1.AccessPolicy{
						{
							Decision: "allow",
							Rules:    []tunnelsv1.AccessPolicyRule{{Everyone: true}},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())

			By("Reconciling — should fail because Gateway target requires explicit domain")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("explicit application.domain"))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})

		It("buildApplicationConfig should populate fields correctly", func() {
			r := newReconciler()
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test",
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					Application: tunnelsv1.ApplicationConfig{
						Name:                   "My App",
						Type:                   "self_hosted",
						SessionDuration:        "8h",
						AutoRedirectToIdentity: true,
						EnableBindingCookie:    true,
						CustomDenyMessage:      "Access Denied",
						CustomDenyURL:          "https://deny.example.com",
					},
					TargetRef: tunnelsv1.PolicyTargetReference{Kind: "HTTPRoute", Name: "test"},
					Policies:  []tunnelsv1.AccessPolicy{{Decision: "allow", Rules: []tunnelsv1.AccessPolicyRule{{Everyone: true}}}},
				},
			}

			config := r.buildApplicationConfig(policy, "myapp.example.com")
			Expect(config.Name).To(Equal("My App"))
			Expect(config.Domain).To(Equal("myapp.example.com"))
			Expect(config.Type).To(Equal("self_hosted"))
			Expect(config.SessionDuration).To(Equal("8h"))
			Expect(config.AutoRedirectToIdentity).To(BeTrue())
			Expect(config.EnableBindingCookie).To(BeTrue())
			Expect(config.CustomDenyMessage).To(Equal("Access Denied"))
			Expect(config.CustomDenyURL).To(Equal("https://deny.example.com"))
		})

		It("buildApplicationConfig should use defaults for missing fields", func() {
			r := newReconciler()
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "minimal",
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					Application: tunnelsv1.ApplicationConfig{},
					TargetRef:   tunnelsv1.PolicyTargetReference{Kind: "HTTPRoute", Name: "test"},
					Policies:    []tunnelsv1.AccessPolicy{{Decision: "allow", Rules: []tunnelsv1.AccessPolicyRule{{Everyone: true}}}},
				},
			}

			config := r.buildApplicationConfig(policy, "default.example.com")
			Expect(config.Name).To(ContainSubstring("access-default-minimal"))
			Expect(config.Type).To(Equal("self_hosted"))
			Expect(config.SessionDuration).To(Equal("24h"))
		})

		It("buildPolicyConfig should handle inline rules correctly", func() {
			r := newReconciler()
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{Kind: "HTTPRoute", Name: "test"},
					Policies:  []tunnelsv1.AccessPolicy{},
				},
			}

			p := tunnelsv1.AccessPolicy{
				Name:     "email-policy",
				Decision: "allow",
				Rules: []tunnelsv1.AccessPolicyRule{
					{Emails: []string{"user@example.com"}, EmailDomains: []string{"example.com"}},
				},
			}
			config := r.buildPolicyConfig(policy, p, 0)
			Expect(config.Name).To(Equal("email-policy"))
			Expect(config.Decision).To(Equal("allow"))
			Expect(config.Include).To(HaveLen(1))
			Expect(config.Include[0].Emails).To(ContainElement("user@example.com"))
			Expect(config.Include[0].EmailDomains).To(ContainElement("example.com"))
		})

		It("buildPolicyConfig should use external policy ID as a group reference", func() {
			r := newReconciler()
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{Kind: "HTTPRoute", Name: "test"},
					Policies:  []tunnelsv1.AccessPolicy{},
				},
			}

			p := tunnelsv1.AccessPolicy{
				Decision:         "allow",
				ExternalPolicyID: "ext-policy-123",
				Rules:            []tunnelsv1.AccessPolicyRule{{Everyone: true}},
			}
			config := r.buildPolicyConfig(policy, p, 0)
			Expect(config.Include).To(HaveLen(1))
			Expect(config.Include[0].GroupID).To(Equal("ext-policy-123"))
		})

		It("buildPolicyConfig should default missing name and decision", func() {
			r := newReconciler()
			policy := &tunnelsv1.CloudflareAccessPolicy{
				ObjectMeta: metav1.ObjectMeta{Name: "test", Namespace: "default"},
				Spec: tunnelsv1.CloudflareAccessPolicySpec{
					TargetRef: tunnelsv1.PolicyTargetReference{Kind: "HTTPRoute", Name: "test"},
					Policies:  []tunnelsv1.AccessPolicy{},
				},
			}

			p := tunnelsv1.AccessPolicy{
				Rules: []tunnelsv1.AccessPolicyRule{{Everyone: true}},
			}
			config := r.buildPolicyConfig(policy, p, 2)
			Expect(config.Name).To(Equal("policy-2"))
			Expect(config.Decision).To(Equal("allow"))
		})
	})
})
