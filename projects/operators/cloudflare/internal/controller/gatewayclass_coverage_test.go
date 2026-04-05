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
	apimeta "k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("GatewayClass Controller Coverage", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
	})

	newGatewayClassReconciler := func() *GatewayClassReconciler {
		return &GatewayClassReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-gwclass-coverage"),
		}
	}

	createTestGatewayClass := func(name string, paramsRef *gatewayv1.ParametersReference) *gatewayv1.GatewayClass {
		gc := &gatewayv1.GatewayClass{
			ObjectMeta: metav1.ObjectMeta{
				Name: name,
			},
			Spec: gatewayv1.GatewayClassSpec{
				ControllerName: ControllerName,
				ParametersRef:  paramsRef,
			},
		}
		Expect(k8sClient.Create(ctx, gc)).To(Succeed())
		return gc
	}

	createCredentialsSecret := func(name, namespace string, data map[string][]byte) *corev1.Secret {
		secret := &corev1.Secret{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: namespace,
			},
			Type: corev1.SecretTypeOpaque,
			Data: data,
		}
		Expect(k8sClient.Create(ctx, secret)).To(Succeed())
		return secret
	}

	Context("validateParametersRef", func() {
		It("should return error when group is unsupported", func() {
			ns := gatewayv1.Namespace("default")
			ref := &gatewayv1.ParametersReference{
				Group:     "apps",
				Kind:      "Secret",
				Name:      "my-secret",
				Namespace: &ns,
			}

			r := newGatewayClassReconciler()
			err := r.validateParametersRef(ctx, ref)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("unsupported parametersRef group"))
		})

		It("should return error when kind is not Secret", func() {
			ns := gatewayv1.Namespace("default")
			ref := &gatewayv1.ParametersReference{
				Group:     "core",
				Kind:      "ConfigMap",
				Name:      "my-config",
				Namespace: &ns,
			}

			r := newGatewayClassReconciler()
			err := r.validateParametersRef(ctx, ref)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("unsupported parametersRef kind"))
			Expect(err.Error()).To(ContainSubstring("expected Secret"))
		})

		It("should return error when namespace is nil", func() {
			ref := &gatewayv1.ParametersReference{
				Group:     "core",
				Kind:      "Secret",
				Name:      "my-secret",
				Namespace: nil,
			}

			r := newGatewayClassReconciler()
			err := r.validateParametersRef(ctx, ref)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("namespace is required"))
		})

		It("should return error when referenced Secret does not exist", func() {
			ns := gatewayv1.Namespace("default")
			ref := &gatewayv1.ParametersReference{
				Group:     "core",
				Kind:      "Secret",
				Name:      fmt.Sprintf("nonexistent-secret-%d", time.Now().UnixNano()),
				Namespace: &ns,
			}

			r := newGatewayClassReconciler()
			err := r.validateParametersRef(ctx, ref)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("parametersRef secret not found"))
		})

		It("should return error when Secret is missing CLOUDFLARE_API_TOKEN", func() {
			secretName := fmt.Sprintf("gwclass-cov-secret-%d", time.Now().UnixNano())
			secret := createCredentialsSecret(secretName, "default", map[string][]byte{
				"CLOUDFLARE_ACCOUNT_ID": []byte("test-account"),
				// CLOUDFLARE_API_TOKEN intentionally missing
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			ns := gatewayv1.Namespace("default")
			ref := &gatewayv1.ParametersReference{
				Group:     "core",
				Kind:      "Secret",
				Name:      secretName,
				Namespace: &ns,
			}

			r := newGatewayClassReconciler()
			err := r.validateParametersRef(ctx, ref)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("missing required field: CLOUDFLARE_API_TOKEN"))
		})

		It("should return error when Secret is missing CLOUDFLARE_ACCOUNT_ID", func() {
			secretName := fmt.Sprintf("gwclass-cov-secret-%d", time.Now().UnixNano())
			secret := createCredentialsSecret(secretName, "default", map[string][]byte{
				"CLOUDFLARE_API_TOKEN": []byte("test-token"),
				// CLOUDFLARE_ACCOUNT_ID intentionally missing
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			ns := gatewayv1.Namespace("default")
			ref := &gatewayv1.ParametersReference{
				Group:     "core",
				Kind:      "Secret",
				Name:      secretName,
				Namespace: &ns,
			}

			r := newGatewayClassReconciler()
			err := r.validateParametersRef(ctx, ref)
			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("missing required field: CLOUDFLARE_ACCOUNT_ID"))
		})

		It("should succeed when Secret has all required fields", func() {
			secretName := fmt.Sprintf("gwclass-cov-secret-%d", time.Now().UnixNano())
			secret := createCredentialsSecret(secretName, "default", map[string][]byte{
				"CLOUDFLARE_API_TOKEN":  []byte("test-token"),
				"CLOUDFLARE_ACCOUNT_ID": []byte("test-account"),
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			ns := gatewayv1.Namespace("default")
			ref := &gatewayv1.ParametersReference{
				Group:     "core",
				Kind:      "Secret",
				Name:      secretName,
				Namespace: &ns,
			}

			r := newGatewayClassReconciler()
			err := r.validateParametersRef(ctx, ref)
			Expect(err).NotTo(HaveOccurred())
		})

		It("should accept empty group (defaults to core)", func() {
			secretName := fmt.Sprintf("gwclass-cov-secret-%d", time.Now().UnixNano())
			secret := createCredentialsSecret(secretName, "default", map[string][]byte{
				"CLOUDFLARE_API_TOKEN":  []byte("test-token"),
				"CLOUDFLARE_ACCOUNT_ID": []byte("test-account"),
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			ns := gatewayv1.Namespace("default")
			ref := &gatewayv1.ParametersReference{
				Group:     "", // empty group is accepted
				Kind:      "Secret",
				Name:      secretName,
				Namespace: &ns,
			}

			r := newGatewayClassReconciler()
			err := r.validateParametersRef(ctx, ref)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Context("validateGatewayClass", func() {
		It("should set Accepted=True when no parametersRef is configured", func() {
			gcName := fmt.Sprintf("gwclass-cov-%d", time.Now().UnixNano())
			gc := createTestGatewayClass(gcName, nil)
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			r := newGatewayClassReconciler()
			result, err := r.validateGatewayClass(ctx, gc)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeFalse())

			By("Verifying Accepted condition is True")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: gcName}, updated)).To(Succeed())

			cond := apimeta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionTrue))
			Expect(cond.Reason).To(Equal(GatewayClassConditionReasonAccepted))
			Expect(cond.Message).To(Equal("GatewayClass accepted by controller"))
		})

		It("should set Accepted=False with InvalidParameters when parametersRef is invalid", func() {
			gcName := fmt.Sprintf("gwclass-cov-%d", time.Now().UnixNano())
			ns := gatewayv1.Namespace("default")
			gc := createTestGatewayClass(gcName, &gatewayv1.ParametersReference{
				Group:     "core",
				Kind:      "Secret",
				Name:      fmt.Sprintf("nonexistent-%d", time.Now().UnixNano()),
				Namespace: &ns,
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			r := newGatewayClassReconciler()
			result, err := r.validateGatewayClass(ctx, gc)

			By("Verifying no error is returned (just condition set)")
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeFalse())

			By("Verifying Accepted=False with InvalidParameters reason")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: gcName}, updated)).To(Succeed())

			cond := apimeta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionFalse))
			Expect(cond.Reason).To(Equal(GatewayClassConditionReasonInvalidParameters))
			Expect(cond.Message).To(ContainSubstring("Invalid parametersRef"))
		})

		It("should set Accepted=True when parametersRef points to a valid Secret", func() {
			secretName := fmt.Sprintf("gwclass-cov-secret-%d", time.Now().UnixNano())
			secret := createCredentialsSecret(secretName, "default", map[string][]byte{
				"CLOUDFLARE_API_TOKEN":  []byte("test-token"),
				"CLOUDFLARE_ACCOUNT_ID": []byte("test-account"),
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })

			gcName := fmt.Sprintf("gwclass-cov-%d", time.Now().UnixNano())
			ns := gatewayv1.Namespace("default")
			gc := createTestGatewayClass(gcName, &gatewayv1.ParametersReference{
				Group:     "core",
				Kind:      "Secret",
				Name:      secretName,
				Namespace: &ns,
			})
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			r := newGatewayClassReconciler()
			result, err := r.validateGatewayClass(ctx, gc)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Requeue).To(BeFalse())

			By("Verifying Accepted=True")
			updated := &gatewayv1.GatewayClass{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: gcName}, updated)).To(Succeed())

			cond := apimeta.FindStatusCondition(updated.Status.Conditions, string(gatewayv1.GatewayClassConditionStatusAccepted))
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionTrue))
			Expect(cond.Reason).To(Equal(GatewayClassConditionReasonAccepted))
		})
	})
})
