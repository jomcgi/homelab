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
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/intstr"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("Service Controller — ensureHTTPRoute and ensureAccessPolicy", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
	})

	newEnsureReconciler := func() *ServiceReconciler {
		return &ServiceReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-ensure-coverage"),
		}
	}

	// createEnsureTestService creates a Service in the API server and registers DeferCleanup.
	createEnsureTestService := func(name string, annotations map[string]string, ports []corev1.ServicePort) *corev1.Service {
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
		DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })
		return svc
	}

	defaultPorts := func() []corev1.ServicePort {
		return []corev1.ServicePort{
			{Name: "http", Port: 8080, TargetPort: intstr.FromInt(8080), Protocol: corev1.ProtocolTCP},
		}
	}

	// -----------------------------------------------------------------------
	// ensureHTTPRoute
	// -----------------------------------------------------------------------
	Context("ensureHTTPRoute", func() {
		It("should create HTTPRoute with correct name when it does not exist", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "httproute-create.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			err := r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)
			Expect(err).NotTo(HaveOccurred())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())

			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})

		It("should set hostname on the created HTTPRoute from config", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "my-app.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)).To(Succeed())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())
			Expect(string(route.Spec.Hostnames[0])).To(Equal("my-app.example.com"))

			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})

		It("should set the ParentRef to the gateway name and namespace", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "parent-ref.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)
			gwName := config.GatewayName

			Expect(r.ensureHTTPRoute(ctx, svc, config, gwName)).To(Succeed())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())

			Expect(route.Spec.ParentRefs).To(HaveLen(1))
			Expect(string(route.Spec.ParentRefs[0].Name)).To(Equal(gwName))
			Expect(string(*route.Spec.ParentRefs[0].Namespace)).To(Equal("default"))

			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})

		It("should set the BackendRef to the service name and port", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "backend-ref.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)).To(Succeed())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())

			Expect(route.Spec.Rules).To(HaveLen(1))
			backendRefs := route.Spec.Rules[0].BackendRefs
			Expect(backendRefs).To(HaveLen(1))
			Expect(string(backendRefs[0].Name)).To(Equal(svcName))
			Expect(int32(*backendRefs[0].Port)).To(Equal(int32(8080)))

			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})

		It("should set an owner reference pointing to the Service", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "owner-ref.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)).To(Succeed())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())

			Expect(route.OwnerReferences).NotTo(BeEmpty())
			ownerRef := route.OwnerReferences[0]
			Expect(ownerRef.Name).To(Equal(svcName))
			Expect(ownerRef.Kind).To(Equal("Service"))
			Expect(*ownerRef.Controller).To(BeTrue())

			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})

		It("should apply the expected labels to the created HTTPRoute", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "labels.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)).To(Succeed())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())

			Expect(route.Labels).To(HaveKeyWithValue("app.kubernetes.io/name", "cloudflare-httproute"))
			Expect(route.Labels).To(HaveKeyWithValue("app.kubernetes.io/managed-by", "cloudflare-operator"))
			Expect(route.Labels).To(HaveKeyWithValue("cloudflare.io/service", svcName))

			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})

		It("should update hostname when HTTPRoute already exists", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "original.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()

			By("First call — creates the HTTPRoute")
			config := r.parseAnnotations(svc)
			Expect(r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)).To(Succeed())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())
			Expect(string(route.Spec.Hostnames[0])).To(Equal("original.example.com"))

			By("Updating the Service annotation to a new hostname")
			svc.Annotations[AnnotationHostname] = "updated.example.com"
			updatedConfig := r.parseAnnotations(svc)

			By("Second call — updates the existing HTTPRoute")
			Expect(r.ensureHTTPRoute(ctx, svc, updatedConfig, updatedConfig.GatewayName)).To(Succeed())

			updatedRoute := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, updatedRoute)).To(Succeed())
			Expect(string(updatedRoute.Spec.Hostnames[0])).To(Equal("updated.example.com"))

			DeferCleanup(func() {
				updatedRoute.Finalizers = []string{}
				_ = k8sClient.Update(ctx, updatedRoute)
				_ = k8sClient.Delete(ctx, updatedRoute)
			})
		})

		It("should be idempotent — calling twice does not return an error", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "idempotent.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)).To(Succeed())
			Expect(r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)).To(Succeed())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())

			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})

		It("should use explicit port annotation in BackendRef when provided", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname:    "explicit-port.example.com",
				AnnotationServicePort: "9443",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)
			Expect(config.Port).To(Equal(int32(9443)))

			Expect(r.ensureHTTPRoute(ctx, svc, config, config.GatewayName)).To(Succeed())

			routeName := fmt.Sprintf("%s-route", svcName)
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, route)).To(Succeed())
			Expect(int32(*route.Spec.Rules[0].BackendRefs[0].Port)).To(Equal(int32(9443)))

			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})
		})
	})

	// -----------------------------------------------------------------------
	// ensureAccessPolicy
	// -----------------------------------------------------------------------
	Context("ensureAccessPolicy", func() {
		It("should create CloudflareAccessPolicy with correct name when it does not exist", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "access-create.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})
		})

		It("should set TargetRef to the corresponding HTTPRoute", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "target-ref.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			expectedRouteName := fmt.Sprintf("%s-route", svcName)
			Expect(policy.Spec.TargetRef.Kind).To(Equal("HTTPRoute"))
			Expect(policy.Spec.TargetRef.Group).To(Equal("gateway.networking.k8s.io"))
			Expect(policy.Spec.TargetRef.Name).To(Equal(expectedRouteName))

			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})
		})

		It("should set ApplicationConfig name, session duration, and type", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "app-config.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			Expect(policy.Spec.Application.Name).To(ContainSubstring(svcName))
			Expect(policy.Spec.Application.Name).To(ContainSubstring("default"))
			Expect(policy.Spec.Application.SessionDuration).To(Equal("24h"))
			Expect(policy.Spec.Application.Type).To(Equal("self_hosted"))

			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})
		})

		It("should create a default-allow policy when no ZeroTrustPolicy annotation is set", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "default-policy.example.com",
				// AnnotationZeroTrustPolicy intentionally absent
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)
			Expect(config.ZeroTrustPolicy).To(BeEmpty())

			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			Expect(policy.Spec.Policies).To(HaveLen(1))
			Expect(policy.Spec.Policies[0].Name).To(Equal("default-allow"))
			Expect(policy.Spec.Policies[0].Decision).To(Equal("allow"))
			Expect(policy.Spec.Policies[0].Rules).To(HaveLen(1))
			Expect(policy.Spec.Policies[0].Rules[0].Everyone).To(BeTrue())
			Expect(policy.Spec.Policies[0].ExternalPolicyID).To(BeEmpty())

			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})
		})

		It("should create an external policy reference when ZeroTrustPolicy annotation is set", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname:        "external-policy.example.com",
				AnnotationZeroTrustPolicy: "cf-policy-abc123",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)
			Expect(config.ZeroTrustPolicy).To(Equal("cf-policy-abc123"))

			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			Expect(policy.Spec.Policies).To(HaveLen(1))
			Expect(policy.Spec.Policies[0].Name).To(Equal("cf-policy-abc123"))
			Expect(policy.Spec.Policies[0].ExternalPolicyID).To(Equal("cf-policy-abc123"))
			Expect(policy.Spec.Policies[0].Decision).To(Equal("allow"))

			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})
		})

		It("should set an owner reference pointing to the Service", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "owner-ref-policy.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			Expect(policy.OwnerReferences).NotTo(BeEmpty())
			ownerRef := policy.OwnerReferences[0]
			Expect(ownerRef.Name).To(Equal(svcName))
			Expect(ownerRef.Kind).To(Equal("Service"))
			Expect(*ownerRef.Controller).To(BeTrue())

			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})
		})

		It("should apply the expected labels to the created AccessPolicy", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "policy-labels.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			Expect(policy.Labels).To(HaveKeyWithValue("app.kubernetes.io/name", "cloudflare-access-policy"))
			Expect(policy.Labels).To(HaveKeyWithValue("app.kubernetes.io/managed-by", "cloudflare-operator"))
			Expect(policy.Labels).To(HaveKeyWithValue("cloudflare.io/service", svcName))

			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})
		})

		It("should update AccessPolicy when annotation changes from default to external policy", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "update-policy.example.com",
				// no ZeroTrustPolicy — default-allow
			}, defaultPorts())

			r := newEnsureReconciler()

			By("First call — creates default-allow policy")
			config := r.parseAnnotations(svc)
			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())
			Expect(policy.Spec.Policies[0].Name).To(Equal("default-allow"))

			By("Updating the annotation to reference an external policy")
			svc.Annotations[AnnotationZeroTrustPolicy] = "new-external-id"
			updatedConfig := r.parseAnnotations(svc)

			By("Second call — updates to external policy reference")
			Expect(r.ensureAccessPolicy(ctx, svc, updatedConfig)).To(Succeed())

			updatedPolicy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, updatedPolicy)).To(Succeed())
			Expect(updatedPolicy.Spec.Policies[0].Name).To(Equal("new-external-id"))
			Expect(updatedPolicy.Spec.Policies[0].ExternalPolicyID).To(Equal("new-external-id"))

			DeferCleanup(func() {
				updatedPolicy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, updatedPolicy)
				_ = k8sClient.Delete(ctx, updatedPolicy)
			})
		})

		It("should be idempotent — calling twice does not return an error", func() {
			svcName := fmt.Sprintf("svc-ensure-%d", time.Now().UnixNano())
			svc := createEnsureTestService(svcName, map[string]string{
				AnnotationHostname: "idempotent-policy.example.com",
			}, defaultPorts())

			r := newEnsureReconciler()
			config := r.parseAnnotations(svc)

			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())
			Expect(r.ensureAccessPolicy(ctx, svc, config)).To(Succeed())

			policyName := fmt.Sprintf("%s-access", svcName)
			policy := &tunnelsv1.CloudflareAccessPolicy{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: policyName, Namespace: "default"}, policy)).To(Succeed())

			DeferCleanup(func() {
				policy.Finalizers = []string{}
				_ = k8sClient.Update(ctx, policy)
				_ = k8sClient.Delete(ctx, policy)
			})
		})
	})
})
