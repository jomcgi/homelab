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
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("HTTPRoute Controller", func() {
	Context("When reconciling an HTTPRoute", func() {
		var (
			ctx                context.Context
			resourceName       string
			typeNamespacedName types.NamespacedName
		)

		BeforeEach(func() {
			ctx = context.Background()
			resourceName = fmt.Sprintf("test-httproute-%d", time.Now().UnixNano())
			typeNamespacedName = types.NamespacedName{
				Name:      resourceName,
				Namespace: "default",
			}
		})

		AfterEach(func() {
			route := &gatewayv1.HTTPRoute{}
			err := k8sClient.Get(ctx, typeNamespacedName, route)
			if err == nil {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, typeNamespacedName, route))
				}, time.Second*5).Should(BeTrue())
			}
		})

		newReconciler := func() *HTTPRouteReconciler {
			return &HTTPRouteReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
				tracer: telemetry.GetTracer("test-httproute"),
			}
		}

		createHTTPRoute := func(parentGatewayName string) *gatewayv1.HTTPRoute {
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{
								Name:      gatewayv1.ObjectName(parentGatewayName),
								Namespace: ptr.To(gatewayv1.Namespace("default")),
							},
						},
					},
					Hostnames: []gatewayv1.Hostname{"test.example.com"},
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: "backend-svc",
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
			return route
		}

		It("should return nil when HTTPRoute is not found", func() {
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{
				NamespacedName: types.NamespacedName{Name: "does-not-exist", Namespace: "default"},
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))
		})

		It("should add finalizer on first reconcile", func() {
			By("Creating an HTTPRoute")
			createHTTPRoute("my-gateway")

			By("Reconciling — should add finalizer")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking the finalizer was added")
			route := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, route)).To(Succeed())
			Expect(route.Finalizers).To(ContainElement(HTTPRouteFinalizerName))
		})

		It("should handle deletion when no Cloudflare Gateway exists (skip cleanup, remove finalizer)", func() {
			By("Creating an HTTPRoute with finalizer")
			route := createHTTPRoute("nonexistent-gateway")

			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Deleting the HTTPRoute")
			Expect(k8sClient.Delete(ctx, route)).To(Succeed())

			By("Reconciling deletion — should remove finalizer even without Gateway")
			_, err = r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking resource is fully deleted")
			Eventually(func() bool {
				return errors.IsNotFound(k8sClient.Get(ctx, typeNamespacedName, route))
			}, time.Second*5).Should(BeTrue())
		})

		It("should return error and update status when no Cloudflare Gateway found in parentRefs", func() {
			By("Creating an HTTPRoute with finalizer already set")
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{HTTPRouteFinalizerName},
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{
								Name:      "nonexistent-gateway",
								Namespace: ptr.To(gatewayv1.Namespace("default")),
							},
						},
					},
					Hostnames: []gatewayv1.Hostname{"test.example.com"},
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: "backend-svc",
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

			By("Reconciling — handleCreateOrUpdate fails, no Cloudflare Gateway")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})

		It("should return error when Gateway exists but is not cloudflare class", func() {
			By("Creating a non-cloudflare Gateway")
			gwName := fmt.Sprintf("other-gw-%d", time.Now().UnixNano())
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "not-cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "http", Protocol: gatewayv1.HTTPProtocolType, Port: 80},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gw) })

			By("Creating HTTPRoute with finalizer pointing to the non-cloudflare Gateway")
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{HTTPRouteFinalizerName},
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{
								Name:      gatewayv1.ObjectName(gwName),
								Namespace: ptr.To(gatewayv1.Namespace("default")),
							},
						},
					},
					Hostnames: []gatewayv1.Hostname{"test.example.com"},
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: "backend-svc",
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

			By("Reconciling — no Cloudflare Gateway found")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})

		It("should return error when Gateway exists but missing tunnel metadata", func() {
			By("Creating a cloudflare Gateway without tunnel annotations")
			gwName := fmt.Sprintf("cf-gw-%d", time.Now().UnixNano())
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

			By("Creating HTTPRoute with finalizer pointing to the cloudflare Gateway")
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{HTTPRouteFinalizerName},
				},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{
								Name:      gatewayv1.ObjectName(gwName),
								Namespace: ptr.To(gatewayv1.Namespace("default")),
							},
						},
					},
					Hostnames: []gatewayv1.Hostname{"test.example.com"},
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: "backend-svc",
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

			By("Reconciling — Gateway exists but missing tunnel metadata")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).To(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})

		It("getBackendServiceURL should return error when HTTPRoute has no rules", func() {
			r := newReconciler()
			route := &gatewayv1.HTTPRoute{
				Spec: gatewayv1.HTTPRouteSpec{},
			}
			_, err := r.getBackendServiceURL(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("no rules"))
		})

		It("getBackendServiceURL should return error when rule has no backendRefs", func() {
			r := newReconciler()
			route := &gatewayv1.HTTPRoute{
				Spec: gatewayv1.HTTPRouteSpec{
					Rules: []gatewayv1.HTTPRouteRule{{}},
				},
			}
			_, err := r.getBackendServiceURL(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("no backendRefs"))
		})

		It("getBackendServiceURL should return error for unsupported backend kind", func() {
			r := newReconciler()
			kind := gatewayv1.Kind("CustomBackend")
			route := &gatewayv1.HTTPRoute{
				Spec: gatewayv1.HTTPRouteSpec{
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Kind: &kind,
											Name: "something",
										},
									},
								},
							},
						},
					},
				},
			}
			_, err := r.getBackendServiceURL(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("unsupported backendRef kind"))
		})

		It("getBackendServiceURL should construct correct URL for existing Service", func() {
			By("Creating a backend Service")
			svcName := fmt.Sprintf("backend-%d", time.Now().UnixNano())
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{
					Name:      svcName,
					Namespace: "default",
				},
				Spec: corev1.ServiceSpec{
					Ports: []corev1.ServicePort{
						{Port: 8080, TargetPort: intstr.FromInt(8080)},
					},
					Selector: map[string]string{"app": "test"},
				},
			}
			Expect(k8sClient.Create(ctx, svc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			r := newReconciler()
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{
					Namespace: "default",
				},
				Spec: gatewayv1.HTTPRouteSpec{
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: gatewayv1.ObjectName(svcName),
											Port: ptr.To(gatewayv1.PortNumber(9090)),
										},
									},
								},
							},
						},
					},
				},
			}
			url, err := r.getBackendServiceURL(ctx, route)
			Expect(err).NotTo(HaveOccurred())
			Expect(url).To(Equal(fmt.Sprintf("http://%s.default.svc:9090", svcName)))
		})
	})
})
