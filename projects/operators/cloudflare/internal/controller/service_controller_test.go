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
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/intstr"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("Service Controller", func() {
	Context("When reconciling a Service", func() {
		var (
			ctx                context.Context
			resourceName       string
			typeNamespacedName types.NamespacedName
		)

		BeforeEach(func() {
			ctx = context.Background()
			resourceName = fmt.Sprintf("test-svc-%d", time.Now().UnixNano())
			typeNamespacedName = types.NamespacedName{
				Name:      resourceName,
				Namespace: "default",
			}
		})

		AfterEach(func() {
			svc := &corev1.Service{}
			if err := k8sClient.Get(ctx, typeNamespacedName, svc); err == nil {
				_ = k8sClient.Delete(ctx, svc)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, typeNamespacedName, svc))
				}, time.Second*5).Should(BeTrue())
			}
		})

		newReconciler := func() *ServiceReconciler {
			return &ServiceReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
				tracer: telemetry.GetTracer("test-service"),
			}
		}

		createService := func(annotations map[string]string) *corev1.Service {
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{
					Name:        resourceName,
					Namespace:   "default",
					Annotations: annotations,
				},
				Spec: corev1.ServiceSpec{
					Selector: map[string]string{"app": resourceName},
					Ports: []corev1.ServicePort{
						{Name: "http", Port: 8080, TargetPort: intstr.FromInt(8080)},
					},
				},
			}
			Expect(k8sClient.Create(ctx, svc)).To(Succeed())
			return svc
		}

		It("should return nil when Service is not found", func() {
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{
				NamespacedName: types.NamespacedName{Name: "does-not-exist", Namespace: "default"},
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))
		})

		It("should skip reconciliation when cloudflare annotation is absent", func() {
			By("Creating a Service without cloudflare annotation")
			createService(nil)

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Verifying no Gateway was created")
			gwName := getDefaultGatewayName("default")
			gw := &gatewayv1.Gateway{}
			err = k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, gw)
			Expect(errors.IsNotFound(err)).To(BeTrue())
		})

		It("should skip reconciliation when hostname annotation is empty", func() {
			By("Creating a Service with empty hostname annotation")
			createService(map[string]string{
				AnnotationHostname: "",
			})

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())
		})

		It("should create Gateway and HTTPRoute when hostname annotation is set", func() {
			By("Creating a Service with cloudflare annotation")
			createService(map[string]string{
				AnnotationHostname:         "myapp.example.com",
				AnnotationZeroTrustEnabled: "false",
			})

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Verifying Gateway was created")
			gwName := getDefaultGatewayName("default")
			gw := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, gw)).To(Succeed())
			Expect(string(gw.Spec.GatewayClassName)).To(Equal("cloudflare"))
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			By("Verifying HTTPRoute was created")
			routeName := fmt.Sprintf("%s-route", resourceName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())
			Expect(string(route.Spec.Hostnames[0])).To(Equal("myapp.example.com"))
			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})

		It("should create AccessPolicy when zero-trust is enabled (default)", func() {
			By("Creating a Service with cloudflare annotation and zero-trust enabled (default)")
			createService(map[string]string{
				AnnotationHostname: "secure.example.com",
				// AnnotationZeroTrustEnabled intentionally omitted (defaults to true)
			})

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Verifying CloudflareAccessPolicy was created")
			policyName := fmt.Sprintf("%s-access", resourceName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())
			Expect(policy.Spec.Application.Name).To(ContainSubstring(resourceName))
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})

			By("Cleaning up Gateway and HTTPRoute")
			gwName := getDefaultGatewayName("default")
			gw := &gatewayv1.Gateway{}
			if err := k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, gw); err == nil {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			}
			routeName := fmt.Sprintf("%s-route", resourceName)
			route := &gatewayv1.HTTPRoute{}
			if err := k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route); err == nil {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			}
		})

		It("should not create AccessPolicy when zero-trust is disabled", func() {
			By("Creating a Service with zero-trust disabled")
			createService(map[string]string{
				AnnotationHostname:         "public.example.com",
				AnnotationZeroTrustEnabled: "false",
			})

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Verifying no CloudflareAccessPolicy was created")
			policyName := fmt.Sprintf("%s-access", resourceName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			err = k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)
			Expect(errors.IsNotFound(err)).To(BeTrue())

			DeferCleanup(func() {
				gwName := getDefaultGatewayName("default")
				gw := &gatewayv1.Gateway{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, gw); err == nil {
					gw.Finalizers = []string{}
					_ = k8sClient.Update(ctx, gw)
					_ = k8sClient.Delete(ctx, gw)
				}
				routeName := fmt.Sprintf("%s-route", resourceName)
				route := &gatewayv1.HTTPRoute{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route); err == nil {
					route.Finalizers = []string{}
					_ = k8sClient.Update(ctx, route)
					_ = k8sClient.Delete(ctx, route)
				}
			})
		})

		It("should create AccessPolicy with external policy reference", func() {
			By("Creating a Service with external policy annotation")
			createService(map[string]string{
				AnnotationHostname:        "protected.example.com",
				AnnotationZeroTrustPolicy: "external-policy-id",
			})

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Verifying CloudflareAccessPolicy uses external policy")
			policyName := fmt.Sprintf("%s-access", resourceName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())
			Expect(policy.Spec.Policies[0].ExternalPolicyID).To(Equal("external-policy-id"))
			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})

			DeferCleanup(func() {
				gwName := getDefaultGatewayName("default")
				gw := &gatewayv1.Gateway{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, gw); err == nil {
					gw.Finalizers = []string{}
					_ = k8sClient.Update(ctx, gw)
					_ = k8sClient.Delete(ctx, gw)
				}
				routeName := fmt.Sprintf("%s-route", resourceName)
				route := &gatewayv1.HTTPRoute{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route); err == nil {
					route.Finalizers = []string{}
					_ = k8sClient.Update(ctx, route)
					_ = k8sClient.Delete(ctx, route)
				}
			})
		})

		It("should clean up HTTPRoute and AccessPolicy when annotation is removed", func() {
			By("Creating Service resources manually to simulate pre-existing state")
			routeName := fmt.Sprintf("%s-route", resourceName)
			policyName := fmt.Sprintf("%s-access", resourceName)

			svc := createService(nil) // no annotation

			// Create an HTTPRoute as if the operator had previously made it
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
											Name: gatewayv1.ObjectName(resourceName),
											Port: func() *gatewayv1.PortNumber { p := gatewayv1.PortNumber(8080); return &p }(),
										},
									},
								},
							},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())

			// Create an AccessPolicy as if the operator had previously made it
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
					Policies: []tunnelsv1.AccessPolicy{
						{
							Decision: "allow",
							Rules: []tunnelsv1.AccessPolicyRule{
								{Everyone: true},
							},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, policy)).To(Succeed())

			By("Reconciling the unannotated Service — should clean up route and policy")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Verifying HTTPRoute was deleted")
			Eventually(func() bool {
				return errors.IsNotFound(
					k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route),
				)
			}, time.Second*5).Should(BeTrue())

			By("Verifying AccessPolicy was deleted")
			Eventually(func() bool {
				return errors.IsNotFound(
					k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy),
				)
			}, time.Second*5).Should(BeTrue())

			_ = svc
		})

		It("should use explicit port annotation when provided", func() {
			By("Parsing annotations with explicit port")
			r := newReconciler()
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{
					Annotations: map[string]string{
						AnnotationHostname:    "explicit-port.example.com",
						AnnotationServicePort: "9443",
					},
				},
				Spec: corev1.ServiceSpec{
					Ports: []corev1.ServicePort{
						{Port: 8080},
					},
				},
			}
			config := r.parseAnnotations(svc)
			Expect(config.Port).To(Equal(int32(9443)))
		})

		It("should fall back to first Service port when no port annotation", func() {
			r := newReconciler()
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{
					Namespace: "default",
					Annotations: map[string]string{
						AnnotationHostname: "fallback-port.example.com",
					},
				},
				Spec: corev1.ServiceSpec{
					Ports: []corev1.ServicePort{
						{Port: 3000},
					},
				},
			}
			config := r.parseAnnotations(svc)
			Expect(config.Port).To(Equal(int32(3000)))
		})

		It("should use namespace-scoped Gateway name", func() {
			r := newReconciler()
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{
					Namespace: "my-namespace",
					Annotations: map[string]string{
						AnnotationHostname: "scoped.example.com",
					},
				},
			}
			config := r.parseAnnotations(svc)
			Expect(config.GatewayName).To(Equal("namespace-my-namespace"))
			Expect(config.GatewayNamespace).To(Equal("my-namespace"))
		})

		It("should return error when ensureGateway finds a non-cloudflare Gateway", func() {
			By("Creating a Gateway with a different class")
			gwName := getDefaultGatewayName("default")
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "nginx",
					Listeners: []gatewayv1.Listener{
						{Name: "http", Protocol: gatewayv1.HTTPProtocolType, Port: 80},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			By("Creating a Service with cloudflare annotation")
			createService(map[string]string{
				AnnotationHostname: "conflict.example.com",
			})

			By("Reconciling — should fail because existing Gateway is not cloudflare class")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("not a Cloudflare Gateway"))
		})

		It("should update existing HTTPRoute on second reconcile", func() {
			By("Creating a Service with cloudflare annotation")
			createService(map[string]string{
				AnnotationHostname:         "update-test.example.com",
				AnnotationZeroTrustEnabled: "false",
			})

			r := newReconciler()

			By("First reconcile — creates Gateway and HTTPRoute")
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Second reconcile — updates existing HTTPRoute")
			_, err = r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("HTTPRoute still exists and is correct")
			routeName := fmt.Sprintf("%s-route", resourceName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())
			Expect(string(route.Spec.Hostnames[0])).To(Equal("update-test.example.com"))

			DeferCleanup(func() {
				gwName := getDefaultGatewayName("default")
				gw := &gatewayv1.Gateway{}
				if err := k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, gw); err == nil {
					gw.Finalizers = []string{}
					_ = k8sClient.Update(ctx, gw)
					_ = k8sClient.Delete(ctx, gw)
				}
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})
	})
})
