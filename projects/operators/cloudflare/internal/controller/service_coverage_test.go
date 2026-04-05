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
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("Service Controller Coverage", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
	})

	newServiceReconciler := func() *ServiceReconciler {
		return &ServiceReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-svc-coverage"),
		}
	}

	createTestService := func(name string, annotations map[string]string, ports []corev1.ServicePort) *corev1.Service {
		svc := &corev1.Service{
			ObjectMeta: metav1.ObjectMeta{
				Name:        name,
				Namespace:   "default",
				Annotations: annotations,
			},
			Spec: corev1.ServiceSpec{
				Ports:    ports,
				Selector: map[string]string{"app": name},
			},
		}
		Expect(k8sClient.Create(ctx, svc)).To(Succeed())
		return svc
	}

	Context("getDefaultGatewayName", func() {
		It("should return namespace-prefixed gateway name", func() {
			Expect(getDefaultGatewayName("default")).To(Equal("namespace-default"))
			Expect(getDefaultGatewayName("production")).To(Equal("namespace-production"))
			Expect(getDefaultGatewayName("my-ns")).To(Equal("namespace-my-ns"))
		})
	})

	Context("parseAnnotations", func() {
		It("should default ZeroTrustEnabled to true when annotation is absent", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, map[string]string{
				AnnotationHostname: "app.example.com",
			}, []corev1.ServicePort{
				{Port: 8080, TargetPort: intstr.FromInt(8080), Protocol: corev1.ProtocolTCP},
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newServiceReconciler()
			config := r.parseAnnotations(svc)

			Expect(config.Hostname).To(Equal("app.example.com"))
			Expect(config.ZeroTrustEnabled).To(BeTrue())
			Expect(config.Port).To(Equal(int32(8080)))
			Expect(config.GatewayName).To(Equal("namespace-default"))
			Expect(config.GatewayNamespace).To(Equal("default"))
		})

		It("should set ZeroTrustEnabled=false when annotation is 'false'", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, map[string]string{
				AnnotationHostname:         "app.example.com",
				AnnotationZeroTrustEnabled: "false",
			}, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newServiceReconciler()
			config := r.parseAnnotations(svc)

			Expect(config.ZeroTrustEnabled).To(BeFalse())
		})

		It("should set ZeroTrustEnabled=true when annotation is 'true'", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, map[string]string{
				AnnotationHostname:         "app.example.com",
				AnnotationZeroTrustEnabled: "true",
			}, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newServiceReconciler()
			config := r.parseAnnotations(svc)

			Expect(config.ZeroTrustEnabled).To(BeTrue())
		})

		It("should parse port from annotation", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, map[string]string{
				AnnotationHostname:    "app.example.com",
				AnnotationServicePort: "9090",
			}, []corev1.ServicePort{
				{Port: 8080, TargetPort: intstr.FromInt(8080), Protocol: corev1.ProtocolTCP},
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newServiceReconciler()
			config := r.parseAnnotations(svc)

			By("Port annotation takes priority over spec ports")
			Expect(config.Port).To(Equal(int32(9090)))
		})

		It("should fall back to first service port when port annotation is absent", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, map[string]string{
				AnnotationHostname: "app.example.com",
			}, []corev1.ServicePort{
				{Port: 3000, TargetPort: intstr.FromInt(3000), Protocol: corev1.ProtocolTCP},
				{Port: 3001, TargetPort: intstr.FromInt(3001), Protocol: corev1.ProtocolTCP},
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newServiceReconciler()
			config := r.parseAnnotations(svc)

			Expect(config.Port).To(Equal(int32(3000)))
		})

		It("should leave Port as 0 when annotation is invalid and no service ports exist", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, map[string]string{
				AnnotationHostname:    "app.example.com",
				AnnotationServicePort: "not-a-number",
			}, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newServiceReconciler()
			config := r.parseAnnotations(svc)

			Expect(config.Port).To(Equal(int32(0)))
		})

		It("should parse ZeroTrustPolicy annotation", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, map[string]string{
				AnnotationHostname:        "app.example.com",
				AnnotationZeroTrustPolicy: "my-external-policy",
			}, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newServiceReconciler()
			config := r.parseAnnotations(svc)

			Expect(config.ZeroTrustPolicy).To(Equal("my-external-policy"))
		})
	})

	Context("cleanupResources", func() {
		It("should return nil when neither HTTPRoute nor AccessPolicy exists (idempotent)", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, nil, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newServiceReconciler()
			result, err := r.cleanupResources(ctx, svc)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeFalse())
		})

		It("should delete existing HTTPRoute when annotation is removed", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, nil, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			routeName := fmt.Sprintf("%s-route", svcName)
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
				},
			}
			Expect(k8sClient.Create(ctx, route)).To(Succeed())

			By("Verifying the route exists")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, &gatewayv1.HTTPRoute{})).To(Succeed())

			By("Calling cleanupResources")
			r := newServiceReconciler()
			result, err := r.cleanupResources(ctx, svc)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeFalse())

			By("Verifying the route was deleted")
			Eventually(func() bool {
				return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, &gatewayv1.HTTPRoute{}))
			}, time.Second*5).Should(BeTrue())
		})

		It("should delete existing AccessPolicy when annotation is removed", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, nil, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			policyName := fmt.Sprintf("%s-access", svcName)
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

			By("Verifying the access policy exists")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, &tunnelsv1.CloudflareAccessPolicy{})).To(Succeed())

			By("Calling cleanupResources")
			r := newServiceReconciler()
			result, err := r.cleanupResources(ctx, svc)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeFalse())

			By("Verifying the access policy was deleted")
			Eventually(func() bool {
				return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, &tunnelsv1.CloudflareAccessPolicy{}))
			}, time.Second*5).Should(BeTrue())
		})
	})

	Context("deleteAccessPolicy", func() {
		It("should return nil when AccessPolicy does not exist (idempotent)", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{
					Name:      svcName,
					Namespace: "default",
				},
			}

			r := newServiceReconciler()
			err := r.deleteAccessPolicy(ctx, svc)
			Expect(err).NotTo(HaveOccurred())
		})

		It("should delete an existing AccessPolicy", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, nil, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			policyName := fmt.Sprintf("%s-access", svcName)
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

			By("Verifying the policy exists")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, &tunnelsv1.CloudflareAccessPolicy{})).To(Succeed())

			By("Calling deleteAccessPolicy")
			r := newServiceReconciler()
			err := r.deleteAccessPolicy(ctx, svc)
			Expect(err).NotTo(HaveOccurred())

			By("Verifying the policy was deleted")
			Eventually(func() bool {
				return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, &tunnelsv1.CloudflareAccessPolicy{}))
			}, time.Second*5).Should(BeTrue())
		})
	})

	Context("ensureGateway", func() {
		It("should return error when existing Gateway is not a Cloudflare Gateway", func() {
			svcName := fmt.Sprintf("svc-cov-%d", time.Now().UnixNano())
			svc := createTestService(svcName, map[string]string{
				AnnotationHostname: "app.example.com",
			}, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			gwName := getDefaultGatewayName("default")
			// Create a gateway with a different (non-cloudflare) class
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
			// Only create if it doesn't already exist
			existing := &gatewayv1.Gateway{}
			err := k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, existing)
			if errors.IsNotFound(err) {
				Expect(k8sClient.Create(ctx, gw)).To(Succeed())
				DeferCleanup(func() {
					gw.Finalizers = []string{}
					_ = k8sClient.Update(ctx, gw)
					_ = k8sClient.Delete(ctx, gw)
				})
			} else {
				// If it already exists with cloudflare class, skip this test
				if existing.Spec.GatewayClassName == "cloudflare" {
					Skip("namespace-default gateway already exists with cloudflare class")
				}
			}

			r := newServiceReconciler()
			config := r.parseAnnotations(svc)
			// Override to use a gateway name we control
			config.GatewayName = gwName
			config.GatewayNamespace = "default"

			_, err = r.ensureGateway(ctx, svc, config)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("not a Cloudflare Gateway"))
		})
	})
})
