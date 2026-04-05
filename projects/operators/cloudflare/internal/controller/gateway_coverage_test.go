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
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	apimeta "k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("Gateway Controller Coverage", func() {
	var (
		ctx context.Context
	)

	BeforeEach(func() {
		ctx = context.Background()
	})

	newGatewayReconciler := func() *GatewayReconciler {
		return &GatewayReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-gw-coverage"),
		}
	}

	createTestGateway := func(name string) *gatewayv1.Gateway {
		gw := &gatewayv1.Gateway{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: "default",
			},
			Spec: gatewayv1.GatewaySpec{
				GatewayClassName: "cloudflare",
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

	Context("deleteCloudflaredDeployment", func() {
		It("should return nil when deployment does not exist (idempotent)", func() {
			gwName := fmt.Sprintf("gw-cov-%d", time.Now().UnixNano())
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
				},
			}
			r := newGatewayReconciler()
			err := r.deleteCloudflaredDeployment(ctx, gw)
			Expect(err).NotTo(HaveOccurred())
		})

		It("should delete an existing deployment", func() {
			gwName := fmt.Sprintf("gw-cov-%d", time.Now().UnixNano())
			gw := createTestGateway(gwName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			deploymentName := fmt.Sprintf("cloudflared-%s", gwName)
			replicas := int32(1)
			deployment := &appsv1.Deployment{
				ObjectMeta: metav1.ObjectMeta{
					Name:      deploymentName,
					Namespace: "default",
				},
				Spec: appsv1.DeploymentSpec{
					Replicas: &replicas,
					Selector: &metav1.LabelSelector{
						MatchLabels: map[string]string{"app": "cloudflared"},
					},
					Template: corev1.PodTemplateSpec{
						ObjectMeta: metav1.ObjectMeta{
							Labels: map[string]string{"app": "cloudflared"},
						},
						Spec: corev1.PodSpec{
							Containers: []corev1.Container{
								{Name: "cloudflared", Image: "cloudflare/cloudflared:latest"},
							},
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, deployment)).To(Succeed())

			By("Verifying deployment exists")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: deploymentName, Namespace: "default"}, &appsv1.Deployment{})).To(Succeed())

			By("Calling deleteCloudflaredDeployment")
			r := newGatewayReconciler()
			err := r.deleteCloudflaredDeployment(ctx, gw)
			Expect(err).NotTo(HaveOccurred())

			By("Verifying deployment was deleted")
			Eventually(func() bool {
				return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: deploymentName, Namespace: "default"}, &appsv1.Deployment{}))
			}, time.Second*5).Should(BeTrue())
		})
	})

	Context("deleteTunnelSecret", func() {
		It("should return nil when secret does not exist (idempotent)", func() {
			gwName := fmt.Sprintf("gw-cov-%d", time.Now().UnixNano())
			gw := &gatewayv1.Gateway{
				ObjectMeta: metav1.ObjectMeta{
					Name:      gwName,
					Namespace: "default",
				},
			}
			r := newGatewayReconciler()
			err := r.deleteTunnelSecret(ctx, gw)
			Expect(err).NotTo(HaveOccurred())
		})

		It("should delete an existing secret", func() {
			gwName := fmt.Sprintf("gw-cov-%d", time.Now().UnixNano())
			gw := createTestGateway(gwName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			secretName := fmt.Sprintf("cloudflare-tunnel-%s", gwName)
			secret := &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      secretName,
					Namespace: "default",
				},
				Type: corev1.SecretTypeOpaque,
				Data: map[string][]byte{
					"tunnel-token": []byte("test-token"),
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())

			By("Verifying secret exists")
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: secretName, Namespace: "default"}, &corev1.Secret{})).To(Succeed())

			By("Calling deleteTunnelSecret")
			r := newGatewayReconciler()
			err := r.deleteTunnelSecret(ctx, gw)
			Expect(err).NotTo(HaveOccurred())

			By("Verifying secret was deleted")
			Eventually(func() bool {
				return errors.IsNotFound(k8sClient.Get(ctx, types.NamespacedName{Name: secretName, Namespace: "default"}, &corev1.Secret{}))
			}, time.Second*5).Should(BeTrue())
		})
	})

	Context("handleAPIError", func() {
		It("should set GatewayConditionProgrammed=False with reason CloudflareAPIError", func() {
			gwName := fmt.Sprintf("gw-cov-%d", time.Now().UnixNano())
			gw := createTestGateway(gwName)
			DeferCleanup(func() {
				gw.Finalizers = []string{}
				_ = k8sClient.Update(ctx, gw)
				_ = k8sClient.Delete(ctx, gw)
			})

			testErr := fmt.Errorf("api call failed")
			r := newGatewayReconciler()
			result, err := r.handleAPIError(ctx, gw, testErr, "test message")

			By("Verifying the original error is returned")
			Expect(err).To(Equal(testErr))

			By("Verifying RequeueAfter is 30 seconds")
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			By("Verifying the condition was set on the gateway in k8s")
			updated := &gatewayv1.Gateway{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: gwName, Namespace: "default"}, updated)).To(Succeed())
			cond := apimeta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayConditionProgrammed))
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionFalse))
			Expect(cond.Reason).To(Equal("CloudflareAPIError"))
			Expect(cond.Message).To(Equal("test message: api call failed"))
		})

		It("should return error even when status update fails (nonexistent gateway)", func() {
			gwName := fmt.Sprintf("gw-cov-%d", time.Now().UnixNano())
			// Do not create this gateway in k8s — status update will fail
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

			testErr := fmt.Errorf("cloudflare api error")
			r := newGatewayReconciler()
			result, err := r.handleAPIError(ctx, gw, testErr, "operation failed")

			By("Verifying the original error is still returned despite status update failure")
			Expect(err).To(Equal(testErr))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})
	})
})
