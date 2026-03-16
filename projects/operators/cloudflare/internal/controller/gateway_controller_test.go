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
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("Gateway Controller", func() {
	Context("When reconciling a Gateway", func() {
		var (
			ctx                context.Context
			resourceName       string
			typeNamespacedName types.NamespacedName
		)

		BeforeEach(func() {
			ctx = context.Background()
			resourceName = fmt.Sprintf("test-gateway-%d", time.Now().UnixNano())
			typeNamespacedName = types.NamespacedName{
				Name:      resourceName,
				Namespace: "default",
			}
		})

		AfterEach(func() {
			gw := &gatewayv1.Gateway{}
			err := k8sClient.Get(ctx, typeNamespacedName, gw)
			if err == nil {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
				Eventually(func() bool {
					return errors.IsNotFound(k8sClient.Get(ctx, typeNamespacedName, gw))
				}, time.Second*5).Should(BeTrue())
			}
		})

		newReconciler := func() *GatewayReconciler {
			return &GatewayReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
				tracer: telemetry.GetTracer("test-gateway"),
			}
		}

		createGateway := func(gatewayClassName string) *gatewayv1.Gateway {
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: gatewayv1.ObjectName(gatewayClassName),
					Listeners: []gatewayv1.Listener{
						{
							Name:     "https",
							Protocol: gatewayv1.HTTPSProtocolType,
							Port:     443,
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())
			return gw
		}

		It("should return nil when Gateway is not found", func() {
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{
				NamespacedName: types.NamespacedName{Name: "does-not-exist", Namespace: "default"},
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))
		})

		It("should skip reconciliation for non-cloudflare GatewayClass", func() {
			By("Creating a Gateway with a different GatewayClass")
			createGateway("other-gateway-class")

			By("Reconciling")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))

			By("Verifying no finalizer was added")
			gw := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, gw)).To(Succeed())
			Expect(gw.Finalizers).NotTo(ContainElement(GatewayFinalizerName))
		})

		It("should add finalizer on first reconcile for cloudflare Gateway", func() {
			By("Creating a cloudflare Gateway")
			createGateway("cloudflare")

			By("First reconcile should add finalizer")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking that finalizer was added")
			gw := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, gw)).To(Succeed())
			Expect(gw.Finalizers).To(ContainElement(GatewayFinalizerName))
		})

		It("should attempt tunnel creation after finalizer and set status when GatewayClass missing", func() {
			By("Creating a cloudflare Gateway (no GatewayClass)")
			createGateway("cloudflare")

			r := newReconciler()

			By("First reconcile — adds finalizer")
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Second reconcile — tries to get account ID, fails because no GatewayClass")
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			// Error is propagated as it failed to get GatewayClass
			Expect(err).To(HaveOccurred())
			// Should requeue after backoff
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			By("Checking that Accepted=False condition is set")
			gw := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, gw)).To(Succeed())
			accepted := apimeta.FindStatusCondition(gw.Status.Conditions, string(gatewayv1.GatewayConditionAccepted))
			Expect(accepted).NotTo(BeNil())
			Expect(accepted.Status).To(Equal(metav1.ConditionFalse))
		})

		It("should handle deletion by removing finalizer", func() {
			By("Creating a cloudflare Gateway")
			gw := createGateway("cloudflare")

			r := newReconciler()

			By("First reconcile — adds finalizer")
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Deleting the Gateway")
			Expect(k8sClient.Delete(ctx, gw)).To(Succeed())

			By("Reconciling to handle deletion")
			_, err = r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking that the resource was deleted (finalizer removed)")
			Eventually(func() bool {
				return errors.IsNotFound(k8sClient.Get(ctx, typeNamespacedName, gw))
			}, time.Second*5).Should(BeTrue())
		})

		It("should update tunnel status when tunnelID annotation is present and tunnel CRD exists", func() {
			By("Creating a cloudflare Gateway with tunnel annotation")
			tunnelID := "test-tunnel-123"
			accountID := "test-account-456"
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
					Annotations: map[string]string{
						GatewayAnnotationTunnelID:  tunnelID,
						GatewayAnnotationAccountID: accountID,
					},
					Finalizers: []string{GatewayFinalizerName},
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())

			By("Creating a ready CloudflareTunnel CRD")
			tunnelCRDName := fmt.Sprintf("%s-gateway-tunnel", resourceName)
			tunnel := &tunnelsv1.CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      tunnelCRDName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareTunnelSpec{
					Name:      tunnelCRDName,
					AccountID: accountID,
				},
			}
			Expect(k8sClient.Create(ctx, tunnel)).To(Succeed())
			DeferCleanup(func() {
				tunnel.Finalizers = []string{}
				_ = k8sClient.Update(ctx, tunnel)
				_ = k8sClient.Delete(ctx, tunnel)
			})

			By("Setting tunnel status to active")
			tunnel.Status.TunnelID = tunnelID
			tunnel.Status.Ready = true
			tunnel.Status.Active = true
			Expect(k8sClient.Status().Update(ctx, tunnel)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Gateway Programmed condition reflects active tunnel")
			updated := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			programmed := apimeta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayConditionProgrammed))
			Expect(programmed).NotTo(BeNil())
			Expect(programmed.Status).To(Equal(metav1.ConditionTrue))
			Expect(programmed.Reason).To(Equal("Programmed"))
		})

		It("should set Programmed=True with ready-but-inactive tunnel", func() {
			By("Creating a cloudflare Gateway with tunnel annotation")
			tunnelID := "test-tunnel-ready-only"
			accountID := "test-account-789"
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
					Annotations: map[string]string{
						GatewayAnnotationTunnelID:  tunnelID,
						GatewayAnnotationAccountID: accountID,
					},
					Finalizers: []string{GatewayFinalizerName},
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())

			By("Creating a ready-but-not-active CloudflareTunnel CRD")
			tunnelCRDName := fmt.Sprintf("%s-gateway-tunnel", resourceName)
			tunnel := &tunnelsv1.CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      tunnelCRDName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareTunnelSpec{
					Name:      tunnelCRDName,
					AccountID: accountID,
				},
			}
			Expect(k8sClient.Create(ctx, tunnel)).To(Succeed())
			DeferCleanup(func() {
				tunnel.Finalizers = []string{}
				_ = k8sClient.Update(ctx, tunnel)
				_ = k8sClient.Delete(ctx, tunnel)
			})

			tunnel.Status.TunnelID = tunnelID
			tunnel.Status.Ready = true
			tunnel.Status.Active = false
			Expect(k8sClient.Status().Update(ctx, tunnel)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Gateway Programmed condition is True (ready but no connections)")
			updated := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			programmed := apimeta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayConditionProgrammed))
			Expect(programmed).NotTo(BeNil())
			Expect(programmed.Status).To(Equal(metav1.ConditionTrue))
		})

		It("should set Programmed=Unknown when tunnel CRD not ready", func() {
			By("Creating a cloudflare Gateway with tunnel annotation")
			tunnelID := "test-tunnel-not-ready"
			accountID := "test-account-notready"
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
					Annotations: map[string]string{
						GatewayAnnotationTunnelID:  tunnelID,
						GatewayAnnotationAccountID: accountID,
					},
					Finalizers: []string{GatewayFinalizerName},
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())

			By("Creating a not-ready CloudflareTunnel CRD")
			tunnelCRDName := fmt.Sprintf("%s-gateway-tunnel", resourceName)
			tunnel := &tunnelsv1.CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      tunnelCRDName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareTunnelSpec{
					Name:      tunnelCRDName,
					AccountID: accountID,
				},
			}
			Expect(k8sClient.Create(ctx, tunnel)).To(Succeed())
			DeferCleanup(func() {
				tunnel.Finalizers = []string{}
				_ = k8sClient.Update(ctx, tunnel)
				_ = k8sClient.Delete(ctx, tunnel)
			})
			// Leave status as zero value (not ready)

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Gateway Programmed condition is Unknown (pending)")
			updated := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			programmed := apimeta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayConditionProgrammed))
			Expect(programmed).NotTo(BeNil())
			Expect(programmed.Status).To(Equal(metav1.ConditionUnknown))
		})

		It("should trigger tunnel recreation when CRD is not found", func() {
			By("Creating a cloudflare Gateway with tunnelID annotation but no CRD")
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
					Annotations: map[string]string{
						GatewayAnnotationTunnelID:  "ghost-tunnel",
						GatewayAnnotationAccountID: "test-account",
					},
					Finalizers: []string{GatewayFinalizerName},
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())

			By("Reconciling — tunnel CRD not found, should clear annotation and requeue")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeTrue())

			By("Verifying the tunnelID annotation was cleared")
			updated := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			Expect(updated.Annotations[GatewayAnnotationTunnelID]).To(Equal(""))
		})

		It("should configure custom cloudflared image when set", func() {
			r := newReconciler()
			r.CloudflaredImage = "my-registry/cloudflared:custom"
			Expect(r.getCloudflaredImage()).To(Equal("my-registry/cloudflared:custom"))
		})

		It("should return default cloudflared image when not customised", func() {
			r := newReconciler()
			Expect(r.getCloudflaredImage()).To(Equal(DefaultCloudflaredImage))
		})

		It("should create a CloudflareTunnel CRD when GatewayClass 'cloudflare' and credentials exist", func() {
			// The Gateway controller only reconciles gateways whose GatewayClassName == "cloudflare"
			// (hardcoded check in the controller), so the GatewayClass resource must also be named "cloudflare".
			By("Creating a credentials Secret")
			secretName := fmt.Sprintf("gw-creds-%d", time.Now().UnixNano())
			secret := &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      secretName,
					Namespace: "default",
				},
				Data: map[string][]byte{
					"CLOUDFLARE_API_TOKEN":  []byte("test-token"),
					"CLOUDFLARE_ACCOUNT_ID": []byte("test-account-id"),
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			By("Creating (or adopting) a GatewayClass named 'cloudflare'")
			ns := gatewayv1.Namespace("default")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: "cloudflare"},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "v1",
						Kind:      "Secret",
						Name:      secretName,
						Namespace: &ns,
					},
				},
			}
			gcErr := k8sClient.Create(ctx, gc)
			if gcErr != nil && !errors.IsAlreadyExists(gcErr) {
				Fail(fmt.Sprintf("failed to create GatewayClass: %v", gcErr))
			}
			gcCreated := gcErr == nil
			DeferCleanup(func() {
				if gcCreated {
					_ = k8sClient.Delete(ctx, gc)
				}
			})

			By("Creating a Gateway with GatewayClassName 'cloudflare' and finalizer already set")
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:       resourceName,
					Namespace:  "default",
					Finalizers: []string{GatewayFinalizerName},
				},
				Spec: gatewayv1.GatewaySpec{
					GatewayClassName: "cloudflare",
					Listeners: []gatewayv1.Listener{
						{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
					},
				},
			}
			Expect(k8sClient.Create(ctx, gw)).To(Succeed())

			By("Reconciling — should create CloudflareTunnel CRD and wait for readiness")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())
			// Gateway waits for tunnel to become ready
			Expect(result.RequeueAfter).To(Equal(5 * time.Second))

			By("Verifying CloudflareTunnel CRD was created")
			tunnelName := fmt.Sprintf("%s-gateway-tunnel", resourceName)
			tunnel := &tunnelsv1.CloudflareTunnel{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: tunnelName, Namespace: "default"}, tunnel)).To(Succeed())
			Expect(tunnel.Spec.AccountID).To(Equal("test-account-id"))
			DeferCleanup(func() {
				tunnel.Finalizers = []string{}
				_ = k8sClient.Update(ctx, tunnel)
				_ = k8sClient.Delete(ctx, tunnel)
			})
		})
	})
})
