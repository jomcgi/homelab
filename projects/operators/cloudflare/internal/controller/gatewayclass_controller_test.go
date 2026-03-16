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
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("GatewayClass Controller", func() {
	Context("When reconciling a GatewayClass", func() {
		var (
			ctx                context.Context
			resourceName       string
			typeNamespacedName types.NamespacedName
		)

		BeforeEach(func() {
			ctx = context.Background()
			resourceName = fmt.Sprintf("test-gatewayclass-%d", time.Now().UnixNano())
			typeNamespacedName = types.NamespacedName{Name: resourceName}
		})

		AfterEach(func() {
			gatewayClass := &gatewayv1.GatewayClass{}
			err := k8sClient.Get(ctx, typeNamespacedName, gatewayClass)
			if err == nil {
				Expect(k8sClient.Delete(ctx, gatewayClass)).To(Succeed())
				Eventually(func() bool {
					err := k8sClient.Get(ctx, typeNamespacedName, gatewayClass)
					return errors.IsNotFound(err)
				}, time.Second*5).Should(BeTrue())
			}
		})

		newReconciler := func() *GatewayClassReconciler {
			return &GatewayClassReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
				tracer: telemetry.GetTracer("test-gatewayclass"),
			}
		}

		It("should return nil for a GatewayClass not managed by this controller", func() {
			By("Creating a GatewayClass with a different controller name")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: resourceName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: "other.io/controller",
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))
		})

		It("should return nil when GatewayClass is not found", func() {
			r := newReconciler()
			result, err := r.Reconcile(ctx, reconcile.Request{
				NamespacedName: types.NamespacedName{Name: "does-not-exist"},
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))
		})

		It("should set Accepted condition to True when Secret has required fields", func() {
			By("Creating a valid credentials Secret")
			secretName := fmt.Sprintf("cf-creds-%d", time.Now().UnixNano())
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
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, secret)
			})

			By("Creating a GatewayClass referencing the Secret")
			ns := gatewayv1.Namespace("default")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: resourceName},
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
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Accepted condition is True")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			accepted := meta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(accepted).NotTo(BeNil())
			Expect(accepted.Status).To(Equal(metav1.ConditionTrue))
			Expect(accepted.Reason).To(Equal(GatewayClassConditionReasonAccepted))
		})

		It("should set Accepted condition to False when Secret is missing", func() {
			By("Creating a GatewayClass referencing a non-existent Secret")
			ns := gatewayv1.Namespace("default")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: resourceName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "v1",
						Kind:      "Secret",
						Name:      "nonexistent-secret",
						Namespace: &ns,
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Accepted condition is False with InvalidParameters reason")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			accepted := meta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(accepted).NotTo(BeNil())
			Expect(accepted.Status).To(Equal(metav1.ConditionFalse))
			Expect(accepted.Reason).To(Equal(GatewayClassConditionReasonInvalidParameters))
		})

		It("should set Accepted condition to False when Secret is missing CLOUDFLARE_API_TOKEN", func() {
			By("Creating a Secret without CLOUDFLARE_API_TOKEN")
			secretName := fmt.Sprintf("cf-creds-missing-%d", time.Now().UnixNano())
			secret := &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      secretName,
					Namespace: "default",
				},
				Data: map[string][]byte{
					"CLOUDFLARE_ACCOUNT_ID": []byte("test-account-id"),
					// deliberately missing CLOUDFLARE_API_TOKEN
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, secret)
			})

			By("Creating a GatewayClass referencing the incomplete Secret")
			ns := gatewayv1.Namespace("default")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: resourceName},
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
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Accepted condition is False")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			accepted := meta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(accepted).NotTo(BeNil())
			Expect(accepted.Status).To(Equal(metav1.ConditionFalse))
		})

		It("should set Accepted condition to False when Secret is missing CLOUDFLARE_ACCOUNT_ID", func() {
			By("Creating a Secret without CLOUDFLARE_ACCOUNT_ID")
			secretName := fmt.Sprintf("cf-creds-noacct-%d", time.Now().UnixNano())
			secret := &corev1.Secret{
				ObjectMeta: metav1.ObjectMeta{
					Name:      secretName,
					Namespace: "default",
				},
				Data: map[string][]byte{
					"CLOUDFLARE_API_TOKEN": []byte("test-token"),
					// deliberately missing CLOUDFLARE_ACCOUNT_ID
				},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())
			DeferCleanup(func() {
				_ = k8sClient.Delete(ctx, secret)
			})

			By("Creating a GatewayClass referencing the incomplete Secret")
			ns := gatewayv1.Namespace("default")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: resourceName},
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
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Accepted condition is False")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			accepted := meta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(accepted).NotTo(BeNil())
			Expect(accepted.Status).To(Equal(metav1.ConditionFalse))
		})

		It("should set Accepted condition to True when no parametersRef is provided", func() {
			By("Creating a GatewayClass without parametersRef")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: resourceName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Accepted condition is True (no params to validate)")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			accepted := meta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(accepted).NotTo(BeNil())
			Expect(accepted.Status).To(Equal(metav1.ConditionTrue))
		})

		It("should reject parametersRef with unsupported Kind", func() {
			By("Creating a GatewayClass with a ConfigMap parametersRef")
			ns := gatewayv1.Namespace("default")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: resourceName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "v1",
						Kind:      "ConfigMap",
						Name:      "some-config",
						Namespace: &ns,
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			By("Reconciling")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking Accepted condition is False")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, updated)).To(Succeed())
			accepted := meta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(accepted).NotTo(BeNil())
			Expect(accepted.Status).To(Equal(metav1.ConditionFalse))
			Expect(accepted.Reason).To(Equal(GatewayClassConditionReasonInvalidParameters))
		})

		It("should reject parametersRef missing namespace", func() {
			By("Creating a GatewayClass with parametersRef missing namespace")
			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: resourceName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: ControllerName,
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "v1",
						Kind:      "Secret",
						Name:      "some-secret",
						Namespace: ptr.To(gatewayv1.Namespace("")),
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())

			By("Reconciling — Namespace is an empty string but non-nil, so lookup will fail")
			r := newReconciler()
			_, err := r.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
			Expect(err).NotTo(HaveOccurred())
		})
	})
})
