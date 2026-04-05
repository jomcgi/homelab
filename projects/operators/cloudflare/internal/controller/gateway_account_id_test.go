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

// Package controller — getAccountID coverage gaps.
//
// The getAccountID helper reads the CLOUDFLARE_ACCOUNT_ID key from the Secret
// referenced by the GatewayClass parametersRef.  Before the fix, an empty byte
// slice (key present, value "") was accepted and the empty string was forwarded
// silently to Cloudflare, causing silent API failures.
//
// Tests in this file cover:
//  1. Happy path — non-empty account ID is returned unchanged.
//  2. Key absent — error "missing CLOUDFLARE_ACCOUNT_ID".
//  3. Key present but empty — error "CLOUDFLARE_ACCOUNT_ID is empty" (the bug fix).
//  4. GatewayClass not found — error propagated.
//  5. No parametersRef — error "GatewayClass has no parametersRef".
//  6. Secret not found — error propagated.
package controller

import (
	"context"
	"fmt"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/types"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"
	"k8s.io/utils/ptr"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("GatewayReconciler.getAccountID", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
	})

	newReconciler := func() *GatewayReconciler {
		return &GatewayReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-get-account-id"),
		}
	}

	// createGatewayClassWithSecret creates a GatewayClass whose parametersRef
	// points to the named secret in the "default" namespace.
	createGatewayClassWithSecret := func(gcName, secretName string) *gatewayv1.GatewayClass {
		ns := gatewayv1.Namespace("default")
		gc := &gatewayv1.GatewayClass{
			ObjectMeta: metav1.ObjectMeta{
				Name: gcName,
			},
			Spec: gatewayv1.GatewayClassSpec{
				ControllerName: "cloudflare.io/gateway-controller",
				ParametersRef: &gatewayv1.ParametersReference{
					Group:     "v1",
					Kind:      "Secret",
					Name:      secretName,
					Namespace: &ns,
				},
			},
		}
		Expect(k8sClient.Create(ctx, gc)).To(Succeed())
		DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })
		return gc
	}

	// createSecret creates a Secret in the "default" namespace with the given data.
	createSecret := func(name string, data map[string][]byte) *corev1.Secret {
		secret := &corev1.Secret{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: "default",
			},
			Type: corev1.SecretTypeOpaque,
			Data: data,
		}
		Expect(k8sClient.Create(ctx, secret)).To(Succeed())
		DeferCleanup(func() { _ = k8sClient.Delete(ctx, secret) })
		return secret
	}

	// makeGateway returns a Gateway pointing to the given GatewayClass (not created in k8s).
	makeGateway := func(gwName, gcName string) *gatewayv1.Gateway {
		return &gatewayv1.Gateway{
			ObjectMeta: metav1.ObjectMeta{
				Name:      gwName,
				Namespace: "default",
			},
			Spec: gatewayv1.GatewaySpec{
				GatewayClassName: gatewayv1.ObjectName(gcName),
				Listeners: []gatewayv1.Listener{
					{Name: "https", Protocol: gatewayv1.HTTPSProtocolType, Port: 443},
				},
			},
		}
	}

	Context("happy path", func() {
		It("returns the account ID when the key is present and non-empty", func() {
			suffix := fmt.Sprintf("%d", time.Now().UnixNano())
			secretName := "cf-creds-" + suffix
			gcName := "cloudflare-gc-" + suffix

			createSecret(secretName, map[string][]byte{
				"CLOUDFLARE_ACCOUNT_ID": []byte("acct-123"),
				"CLOUDFLARE_API_TOKEN":  []byte("tok-abc"),
			})
			createGatewayClassWithSecret(gcName, secretName)

			gw := makeGateway("gw-"+suffix, gcName)
			r := newReconciler()
			accountID, err := r.getAccountID(ctx, gw)

			Expect(err).NotTo(HaveOccurred())
			Expect(accountID).To(Equal("acct-123"))
		})
	})

	Context("error paths", func() {
		It("returns an error when CLOUDFLARE_ACCOUNT_ID key is absent from the secret", func() {
			suffix := fmt.Sprintf("%d", time.Now().UnixNano())
			secretName := "cf-creds-nokey-" + suffix
			gcName := "cloudflare-gc-nokey-" + suffix

			createSecret(secretName, map[string][]byte{
				"CLOUDFLARE_API_TOKEN": []byte("tok-abc"),
				// CLOUDFLARE_ACCOUNT_ID intentionally absent
			})
			createGatewayClassWithSecret(gcName, secretName)

			gw := makeGateway("gw-nokey-"+suffix, gcName)
			r := newReconciler()
			_, err := r.getAccountID(ctx, gw)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("missing CLOUDFLARE_ACCOUNT_ID"))
		})

		It("returns an error when CLOUDFLARE_ACCOUNT_ID is present but empty (bug fix)", func() {
			// Regression test: before the fix, an empty value was silently accepted
			// and forwarded to Cloudflare, causing silent API failures downstream.
			suffix := fmt.Sprintf("%d", time.Now().UnixNano())
			secretName := "cf-creds-empty-" + suffix
			gcName := "cloudflare-gc-empty-" + suffix

			createSecret(secretName, map[string][]byte{
				"CLOUDFLARE_ACCOUNT_ID": []byte(""), // empty — must be rejected
				"CLOUDFLARE_API_TOKEN":  []byte("tok-abc"),
			})
			createGatewayClassWithSecret(gcName, secretName)

			gw := makeGateway("gw-empty-"+suffix, gcName)
			r := newReconciler()
			_, err := r.getAccountID(ctx, gw)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("CLOUDFLARE_ACCOUNT_ID is empty"))
		})

		It("returns an error when the GatewayClass does not exist", func() {
			gw := makeGateway("gw-nogc", "nonexistent-gc")
			r := newReconciler()
			_, err := r.getAccountID(ctx, gw)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get GatewayClass"))
		})

		It("returns an error when the GatewayClass has no parametersRef", func() {
			suffix := fmt.Sprintf("%d", time.Now().UnixNano())
			gcName := "cloudflare-gc-noparams-" + suffix

			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: "cloudflare.io/gateway-controller",
					// ParametersRef intentionally absent
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gw := makeGateway("gw-noparams-"+suffix, gcName)
			r := newReconciler()
			_, err := r.getAccountID(ctx, gw)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("GatewayClass has no parametersRef"))
		})

		It("returns an error when the referenced Secret does not exist", func() {
			suffix := fmt.Sprintf("%d", time.Now().UnixNano())
			gcName := "cloudflare-gc-nosecret-" + suffix

			createGatewayClassWithSecret(gcName, "nonexistent-secret-"+suffix)

			gw := makeGateway("gw-nosecret-"+suffix, gcName)
			r := newReconciler()
			_, err := r.getAccountID(ctx, gw)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("failed to get credentials secret"))
		})

		It("returns an error when parametersRef namespace is nil", func() {
			suffix := fmt.Sprintf("%d", time.Now().UnixNano())
			gcName := "cloudflare-gc-nons-" + suffix

			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: "cloudflare.io/gateway-controller",
					ParametersRef: &gatewayv1.ParametersReference{
						Group:     "v1",
						Kind:      "Secret",
						Name:      "some-secret",
						Namespace: nil, // nil namespace
					},
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			DeferCleanup(func() { _ = k8sClient.Delete(ctx, gc) })

			gw := makeGateway("gw-nons-"+suffix, gcName)
			r := newReconciler()
			_, err := r.getAccountID(ctx, gw)

			Expect(err).To(HaveOccurred())
			Expect(err.Error()).To(ContainSubstring("parametersRef namespace is required"))
		})
	})

	// Ensure the cleanup works — just a sanity check on test isolation.
	Context("test isolation", func() {
		It("creates and cleans up resources without leaving orphans", func() {
			suffix := fmt.Sprintf("%d", time.Now().UnixNano())
			gcName := "cloudflare-gc-isolation-" + suffix

			gc := &gatewayv1.GatewayClass{
				ObjectMeta: metav1.ObjectMeta{Name: gcName},
				Spec: gatewayv1.GatewayClassSpec{
					ControllerName: "cloudflare.io/gateway-controller",
				},
			}
			Expect(k8sClient.Create(ctx, gc)).To(Succeed())
			_ = k8sClient.Delete(ctx, gc)

			Eventually(func() bool {
				return errors.IsNotFound(
					k8sClient.Get(ctx, types.NamespacedName{Name: gcName}, &gatewayv1.GatewayClass{}),
				)
			}, 5*time.Second).Should(BeTrue())
		})
	})

	// Ensure getCloudflaredImage returns the custom image when set.
	Context("getCloudflaredImage", func() {
		It("returns the configured custom image", func() {
			r := newReconciler()
			r.CloudflaredImage = "custom/cloudflared:v1.0.0"
			Expect(r.getCloudflaredImage()).To(Equal("custom/cloudflared:v1.0.0"))
		})

		It("returns the default image when no custom image is configured", func() {
			r := newReconciler()
			r.CloudflaredImage = ""
			Expect(r.getCloudflaredImage()).To(Equal(DefaultCloudflaredImage))
		})
	})

	// Verify the ptr import is used correctly.
	_ = ptr.To(true)
})
