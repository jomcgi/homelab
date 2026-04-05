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

// Package controller — tests for HTTPRouteReconciler.getGatewayAndClient()
// and HTTPRouteReconciler.getBackendServiceURL() credential-resolution paths.
//
// Existing tests cover the following paths in httproute_controller_test.go:
//   - No parentRefs matching any Gateway
//   - Gateway exists but class is not "cloudflare"
//   - Gateway exists but missing tunnel annotations
//   - getBackendServiceURL: no rules, no backendRefs, unsupported kind, success
//
// This file adds direct unit-test coverage for the credential-resolution chain
// that was previously untested:
//   - GatewayClass not found
//   - GatewayClass has no parametersRef
//   - parametersRef.Kind is not "Secret"
//   - parametersRef.Namespace is nil
//   - Credentials Secret does not exist
//   - Credentials Secret is missing CLOUDFLARE_API_TOKEN key
//   - All credentials present → client returned with correct accountID / tunnelID
//
// Also adds additional getBackendServiceURL paths:
//   - Service has no ports and backendRef has no port → error
//   - Service has ports and backendRef has no port → uses first service port
package controller

import (
	"context"
	"fmt"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/utils/ptr"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("HTTPRouteReconciler.getGatewayAndClient credential resolution", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
	})

	newHTTPRouteR := func() *HTTPRouteReconciler {
		return &HTTPRouteReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-httproute-gw-client"),
		}
	}

	// -------------------------------------------------------------------------
	// Helpers
	// -------------------------------------------------------------------------

	// createCloudflareGateway creates a Gateway with the "cloudflare" class and
	// the provided tunnel/account annotations, returning the created resource.
	createCloudflareGateway := func(name, namespace, tunnelID, accountID string) *gatewayv1.Gateway {
		gw := &gatewayv1.Gateway{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: namespace,
				Annotations: map[string]string{
					GatewayAnnotationTunnelID:  tunnelID,
					GatewayAnnotationAccountID: accountID,
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
		return gw
	}

	// createHTTPRouteWithParent creates a minimal HTTPRoute that references the
	// given Gateway as its parent.
	createHTTPRouteWithParent := func(name, namespace, gatewayName, gatewayNamespace string) *gatewayv1.HTTPRoute {
		gwNS := gatewayv1.Namespace(gatewayNamespace)
		route := &gatewayv1.HTTPRoute{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: namespace,
			},
			Spec: gatewayv1.HTTPRouteSpec{
				CommonRouteSpec: gatewayv1.CommonRouteSpec{
					ParentRefs: []gatewayv1.ParentReference{
						{
							Name:      gatewayv1.ObjectName(gatewayName),
							Namespace: &gwNS,
						},
					},
				},
				Hostnames: []gatewayv1.Hostname{"test.example.com"},
			},
		}
		Expect(k8sClient.Create(ctx, route)).To(Succeed())
		DeferCleanup(func() {
			route.Finalizers = []string{}
			_ = k8sClient.Update(ctx, route)
			_ = k8sClient.Delete(ctx, route)
		})
		return route
	}

	// createGatewayClass creates a GatewayClass whose parametersRef points to the
	// given Secret.
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
		DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })
		return gc
	}

	// createCredentialsSecret creates an Opaque Secret with the given API token.
	createCredentialsSecret := func(name, namespace string, token []byte) *corev1.Secret {
		secret := &corev1.Secret{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: namespace},
			Type:       corev1.SecretTypeOpaque,
			Data:       map[string][]byte{"CLOUDFLARE_API_TOKEN": token},
		}
		Expect(k8sClient.Create(ctx, secret)).To(Succeed())
		DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })
		return secret
	}

	// unique returns a short unique suffix based on nanosecond timestamp.
	unique := func() string { return fmt.Sprintf("%d", time.Now().UnixNano()) }

	// -------------------------------------------------------------------------
	// Test cases
	// -------------------------------------------------------------------------

	Context("GatewayClass lookup failures", func() {
		It("returns error when GatewayClass does not exist", func() {
			id := unique()
			gw := createCloudflareGateway("gw-no-gc-"+id, "default", "tunnel-"+id, "account-"+id)
			// Use a gateway class name that was never created
			gw.Spec.GatewayClassName = gatewayv1.ObjectName("nonexistent-gc-" + id)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			route := createHTTPRouteWithParent("route-no-gc-"+id, "default", gw.Name, "default")
			r := newHTTPRouteR()
			_, _, _, _, err := r.getGatewayAndClient(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get GatewayClass"))
		})

		It("returns error when GatewayClass has no parametersRef", func() {
			id := unique()
			gcName := "gc-no-params-" + id
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					// ParametersRef intentionally nil
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gw := createCloudflareGateway("gw-no-params-"+id, "default", "tid-"+id, "aid-"+id)
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			route := createHTTPRouteWithParent("route-no-params-"+id, "default", gw.Name, "default")
			r := newHTTPRouteR()
			_, _, _, _, err := r.getGatewayAndClient(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("GatewayClass has no parametersRef"))
		})

		It("returns error when parametersRef.Kind is not 'Secret'", func() {
			id := unique()
			gcName := "gc-bad-kind-" + id
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

			gw := createCloudflareGateway("gw-bad-kind-"+id, "default", "tid-"+id, "aid-"+id)
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			route := createHTTPRouteWithParent("route-bad-kind-"+id, "default", gw.Name, "default")
			r := newHTTPRouteR()
			_, _, _, _, err := r.getGatewayAndClient(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("invalid parametersRef"))
		})

		It("returns error when parametersRef.Namespace is nil", func() {
			id := unique()
			gcName := "gc-nil-ns-" + id
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

			gw := createCloudflareGateway("gw-nil-ns-"+id, "default", "tid-"+id, "aid-"+id)
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			route := createHTTPRouteWithParent("route-nil-ns-"+id, "default", gw.Name, "default")
			r := newHTTPRouteR()
			_, _, _, _, err := r.getGatewayAndClient(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("invalid parametersRef"))
		})
	})

	Context("credentials Secret failures", func() {
		It("returns error when credentials Secret does not exist", func() {
			id := unique()
			gcName := "gc-missing-sec-" + id
			gc := createGatewayClass(gcName, "missing-secret-"+id, "default")
			_ = gc

			gw := createCloudflareGateway("gw-missing-sec-"+id, "default", "tid-"+id, "aid-"+id)
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			route := createHTTPRouteWithParent("route-missing-sec-"+id, "default", gw.Name, "default")
			r := newHTTPRouteR()
			_, _, _, _, err := r.getGatewayAndClient(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get credentials secret"))
		})

		It("returns error when Secret is missing CLOUDFLARE_API_TOKEN", func() {
			id := unique()
			secretName := "secret-no-token-" + id
			secret := &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{Name: secretName, Namespace: "default"},
				Type:       corev1.SecretTypeOpaque,
				Data: map[string][]byte{
					"OTHER_KEY": []byte("some-value"),
					// CLOUDFLARE_API_TOKEN deliberately missing
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			gcName := "gc-no-token-" + id
			gc := createGatewayClass(gcName, secretName, "default")
			_ = gc

			gw := createCloudflareGateway("gw-no-token-"+id, "default", "tid-"+id, "aid-"+id)
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			route := createHTTPRouteWithParent("route-no-token-"+id, "default", gw.Name, "default")
			r := newHTTPRouteR()
			_, _, _, _, err := r.getGatewayAndClient(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("credentials secret missing CLOUDFLARE_API_TOKEN"))
		})
	})

	Context("successful credential resolution", func() {
		It("returns the client, gateway, accountID, and tunnelID when all resources exist", func() {
			id := unique()
			secretName := "secret-valid-" + id
			secret := createCredentialsSecret(secretName, "default", []byte("fake-api-token"))
			_ = secret

			gcName := "gc-valid-" + id
			gc := createGatewayClass(gcName, secretName, "default")
			_ = gc

			tunnelID := "tunnel-id-" + id
			accountID := "account-id-" + id
			gw := createCloudflareGateway("gw-valid-"+id, "default", tunnelID, accountID)
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			route := createHTTPRouteWithParent("route-valid-"+id, "default", gw.Name, "default")
			r := newHTTPRouteR()
			retGateway, cfClient, retAccountID, retTunnelID, err := r.getGatewayAndClient(ctx, route)
			Expect(err).NotTo(HaveOccurred())
			Expect(cfClient).NotTo(BeNil())
			Expect(retGateway).NotTo(BeNil())
			Expect(retGateway.Name).To(Equal(gw.Name))
			Expect(retAccountID).To(Equal(accountID))
			Expect(retTunnelID).To(Equal(tunnelID))
		})

		It("uses the HTTPRoute's namespace when parentRef has no explicit namespace", func() {
			id := unique()
			secretName := "secret-ns-" + id
			secret := createCredentialsSecret(secretName, "default", []byte("fake-token"))
			_ = secret

			gcName := "gc-ns-" + id
			gc := createGatewayClass(gcName, secretName, "default")
			_ = gc

			gw := createCloudflareGateway("gw-ns-"+id, "default", "tid-ns-"+id, "aid-ns-"+id)
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			// Build route with no explicit namespace on the parentRef
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{Name: "route-ns-" + id, Namespace: "default"},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{Name: gatewayv1.ObjectName(gw.Name)}, // no Namespace field
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

			r := newHTTPRouteR()
			retGW, cfClient, _, _, err := r.getGatewayAndClient(ctx, route)
			Expect(err).NotTo(HaveOccurred())
			Expect(cfClient).NotTo(BeNil())
			Expect(retGW.Name).To(Equal(gw.Name))
		})

		It("skips non-Gateway parentRefs and finds the Cloudflare Gateway", func() {
			id := unique()
			secretName := "secret-skip-" + id
			secret := createCredentialsSecret(secretName, "default", []byte("fake-token"))
			_ = secret

			gcName := "gc-skip-" + id
			gc := createGatewayClass(gcName, secretName, "default")
			_ = gc

			gw := createCloudflareGateway("gw-skip-"+id, "default", "tid-skip-"+id, "aid-skip-"+id)
			gw.Spec.GatewayClassName = gatewayv1.ObjectName(gcName)
			Expect(k8sClient.Update(ctx, gw)).To(Succeed())

			gwNS := gatewayv1.Namespace("default")
			nonGWKind := gatewayv1.Kind("Service") // not a Gateway kind
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{Name: "route-skip-" + id, Namespace: "default"},
				Spec: gatewayv1.HTTPRouteSpec{
					CommonRouteSpec: gatewayv1.CommonRouteSpec{
						ParentRefs: []gatewayv1.ParentReference{
							{
								// This ref has Kind=Service — should be skipped
								Kind:      &nonGWKind,
								Name:      "some-service",
								Namespace: &gwNS,
							},
							{
								Name:      gatewayv1.ObjectName(gw.Name),
								Namespace: &gwNS,
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

			r := newHTTPRouteR()
			retGW, cfClient, _, _, err := r.getGatewayAndClient(ctx, route)
			Expect(err).NotTo(HaveOccurred())
			Expect(cfClient).NotTo(BeNil())
			Expect(retGW.Name).To(Equal(gw.Name))
		})
	})
})

var _ = Describe("HTTPRouteReconciler.getBackendServiceURL additional paths", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
	})

	newHTTPRouteR := func() *HTTPRouteReconciler {
		return &HTTPRouteReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-httproute-backend"),
		}
	}

	unique := func() string { return fmt.Sprintf("%d", time.Now().UnixNano()) }

	Context("port resolution", func() {
		It("returns error when Service has no ports and backendRef specifies no port", func() {
			id := unique()
			svcName := "svc-no-port-" + id
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{Name: svcName, Namespace: "default"},
				Spec: corev1.ServiceSpec{
					Ports:    []corev1.ServicePort{}, // no ports
					Selector: map[string]string{"app": svcName},
				},
			}
			Expect(k8sClient.Create(ctx, svc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{Name: "rt-no-port-" + id, Namespace: "default"},
				Spec: gatewayv1.HTTPRouteSpec{
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: gatewayv1.ObjectName(svcName),
											// Port intentionally nil
										},
									},
								},
							},
						},
					},
				},
			}
			r := newHTTPRouteR()
			_, err := r.getBackendServiceURL(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("no port specified"))
		})

		It("falls back to the first Service port when backendRef specifies no port", func() {
			id := unique()
			svcName := "svc-first-port-" + id
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{Name: svcName, Namespace: "default"},
				Spec: corev1.ServiceSpec{
					Ports: []corev1.ServicePort{
						{Name: "http", Port: 9090, TargetPort: intstr.FromInt(9090), Protocol: corev1.ProtocolTCP},
					},
					Selector: map[string]string{"app": svcName},
				},
			}
			Expect(k8sClient.Create(ctx, svc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{Name: "rt-first-port-" + id, Namespace: "default"},
				Spec: gatewayv1.HTTPRouteSpec{
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: gatewayv1.ObjectName(svcName),
											// Port intentionally nil — should fall back to svc port
										},
									},
								},
							},
						},
					},
				},
			}
			r := newHTTPRouteR()
			url, err := r.getBackendServiceURL(ctx, route)
			Expect(err).NotTo(HaveOccurred())
			Expect(url).To(Equal(fmt.Sprintf("http://%s.default.svc:9090", svcName)))
		})

		It("uses a cross-namespace backendRef when Namespace is explicit", func() {
			id := unique()
			svcName := "svc-cross-ns-" + id
			svc := &corev1.Service{
				ObjectMeta: metav1.ObjectMeta{Name: svcName, Namespace: "default"},
				Spec: corev1.ServiceSpec{
					Ports: []corev1.ServicePort{
						{Name: "http", Port: 8080, TargetPort: intstr.FromInt(8080), Protocol: corev1.ProtocolTCP},
					},
					Selector: map[string]string{"app": svcName},
				},
			}
			Expect(k8sClient.Create(ctx, svc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, svc) })

			backendNS := gatewayv1.Namespace("default")
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{Name: "rt-cross-ns-" + id, Namespace: "default"},
				Spec: gatewayv1.HTTPRouteSpec{
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name:      gatewayv1.ObjectName(svcName),
											Namespace: &backendNS,
											Port:      ptr.To(gatewayv1.PortNumber(8080)),
										},
									},
								},
							},
						},
					},
				},
			}
			r := newHTTPRouteR()
			url, err := r.getBackendServiceURL(ctx, route)
			Expect(err).NotTo(HaveOccurred())
			Expect(url).To(Equal(fmt.Sprintf("http://%s.default.svc:8080", svcName)))
		})

		It("returns error when backend Service does not exist", func() {
			id := unique()
			route := &gatewayv1.HTTPRoute{
				ObjectMeta: metav1.ObjectMeta{Name: "rt-no-svc-" + id, Namespace: "default"},
				Spec: gatewayv1.HTTPRouteSpec{
					Rules: []gatewayv1.HTTPRouteRule{
						{
							BackendRefs: []gatewayv1.HTTPBackendRef{
								{
									BackendRef: gatewayv1.BackendRef{
										BackendObjectReference: gatewayv1.BackendObjectReference{
											Name: gatewayv1.ObjectName("nonexistent-svc-" + id),
											Port: ptr.To(gatewayv1.PortNumber(8080)),
										},
									},
								},
							},
						},
					},
				},
			}
			r := newHTTPRouteR()
			_, err := r.getBackendServiceURL(ctx, route)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get backend Service"))
		})
	})
})
