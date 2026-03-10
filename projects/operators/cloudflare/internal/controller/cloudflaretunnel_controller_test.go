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

	"github.com/cloudflare/cloudflare-go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
)

var _ = Describe("CloudflareTunnel Controller", func() {
	Context("When reconciling a resource", func() {
		var (
			resourceName       = "test-tunnel"
			accountID          = "test-account-id"
			ctx                = context.Background()
			typeNamespacedName types.NamespacedName
		)

		BeforeEach(func() {
			// Reset mock client state
			mockCFClient.CreateTunnelFunc = nil
			mockCFClient.GetTunnelFunc = nil
			mockCFClient.DeleteTunnelFunc = nil
			mockCFClient.UpdateTunnelConfigurationFunc = nil

			// Use unique resource name for each test to avoid conflicts
			resourceName = fmt.Sprintf("test-tunnel-%d", time.Now().UnixNano())
			typeNamespacedName = types.NamespacedName{
				Name:      resourceName,
				Namespace: "default",
			}
		})

		AfterEach(func() {
			// Clean up any remaining resources
			resource := &tunnelsv1.CloudflareTunnel{}
			err := k8sClient.Get(ctx, typeNamespacedName, resource)
			if err == nil {
				By("Cleaning up the CloudflareTunnel resource")

				// Remove finalizers to allow deletion
				resource.Finalizers = []string{}
				Expect(k8sClient.Update(ctx, resource)).To(Succeed())

				// Delete the resource
				Expect(k8sClient.Delete(ctx, resource)).To(Succeed())

				// Wait for resource to be deleted
				Eventually(func() bool {
					err := k8sClient.Get(ctx, typeNamespacedName, resource)
					return errors.IsNotFound(err)
				}, time.Second*5).Should(BeTrue())
			}
		})

		createTestResource := func() *tunnelsv1.CloudflareTunnel {
			resource := &tunnelsv1.CloudflareTunnel{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
				},
				Spec: tunnelsv1.CloudflareTunnelSpec{
					Name:      resourceName,
					AccountID: accountID,
					Ingress: []tunnelsv1.TunnelIngress{
						{
							Hostname: "test.example.com",
							Service:  "http://backend:8080",
						},
					},
				},
			}
			Expect(k8sClient.Create(ctx, resource)).To(Succeed())
			return resource
		}

		It("should successfully reconcile the resource", func() {
			resource := createTestResource()

			controllerReconciler := &CloudflareTunnelReconciler{
				Client:   k8sClient,
				Scheme:   k8sClient.Scheme(),
				CFClient: mockCFClient,
			}

			By("First reconciliation should add finalizer")
			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("Checking if the finalizer was added")
			err = k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())
			Expect(resource.Finalizers).To(ContainElement(FinalizerName))
		})

		It("should update status when tunnel is created successfully", func() {
			resource := createTestResource()

			By("Setting up mock tunnel creation")
			mockCFClient.CreateTunnelFunc = func(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error) {
				return &cloudflare.Tunnel{
					ID:   "test-tunnel-id",
					Name: name,
				}, "test-tunnel-id", nil
			}

			controllerReconciler := &CloudflareTunnelReconciler{
				Client:   k8sClient,
				Scheme:   k8sClient.Scheme(),
				CFClient: mockCFClient,
			}

			By("First reconcile to add finalizer")
			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("Second reconcile to create tunnel")
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("Checking if tunnel ID was set in status")
			err = k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())
			Expect(resource.Status.TunnelID).To(Equal("test-tunnel-id"))
			Expect(resource.Status.Ready).To(BeTrue())

			By("Checking if Ready condition was set")
			readyCondition := meta.FindStatusCondition(resource.Status.Conditions, tunnelsv1.TypeReady)
			Expect(readyCondition).NotTo(BeNil())
			Expect(readyCondition.Status).To(Equal(metav1.ConditionTrue))
		})

		It("should handle tunnel creation errors", func() {
			resource := createTestResource()

			By("Setting up mock tunnel creation error")
			mockCFClient.CreateTunnelFunc = func(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error) {
				return nil, "", &cloudflare.Error{
					StatusCode:    400,
					ErrorMessages: []string{"Invalid request"},
				}
			}

			controllerReconciler := &CloudflareTunnelReconciler{
				Client:   k8sClient,
				Scheme:   k8sClient.Scheme(),
				CFClient: mockCFClient,
			}

			By("First reconcile to add finalizer")
			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("Second reconcile should handle creation error")
			result, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(result.RequeueAfter).To(Equal(time.Duration(0)))

			By("Checking if Degraded condition was set")
			err = k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())
			degradedCondition := meta.FindStatusCondition(resource.Status.Conditions, tunnelsv1.TypeDegraded)
			Expect(degradedCondition).NotTo(BeNil())
			Expect(degradedCondition.Status).To(Equal(metav1.ConditionTrue))
			Expect(degradedCondition.Reason).To(Equal(tunnelsv1.ReasonAPIError))
		})

		It("should handle tunnel status updates", func() {
			resource := createTestResource()

			By("Adding finalizer first")
			controllerReconciler := &CloudflareTunnelReconciler{
				Client:   k8sClient,
				Scheme:   k8sClient.Scheme(),
				CFClient: mockCFClient,
			}

			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("Setting up tunnel with existing ID")
			err = k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())
			resource.Status.TunnelID = "existing-tunnel-id"
			err = k8sClient.Status().Update(ctx, resource)
			Expect(err).NotTo(HaveOccurred())

			By("Setting up mock tunnel status retrieval")
			mockCFClient.GetTunnelFunc = func(ctx context.Context, accountID, tunnelID string) (*cloudflare.Tunnel, error) {
				return &cloudflare.Tunnel{
					ID:   tunnelID,
					Name: "test-tunnel",
					Connections: []cloudflare.TunnelConnection{
						{ID: "conn-1"},
						{ID: "conn-2"},
					},
				}, nil
			}

			By("Reconciling to update tunnel status")
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("Checking if Active status was updated")
			err = k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())
			Expect(resource.Status.Active).To(BeTrue())

			By("Checking if Active condition was set")
			activeCondition := meta.FindStatusCondition(resource.Status.Conditions, tunnelsv1.TypeActive)
			Expect(activeCondition).NotTo(BeNil())
			Expect(activeCondition.Status).To(Equal(metav1.ConditionTrue))
			Expect(activeCondition.Reason).To(Equal(tunnelsv1.ReasonTunnelConnected))
		})

		It("should handle tunnel deletion", func() {
			resource := createTestResource()

			controllerReconciler := &CloudflareTunnelReconciler{
				Client:   k8sClient,
				Scheme:   k8sClient.Scheme(),
				CFClient: mockCFClient,
			}

			By("Adding finalizer first")
			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("Setting up tunnel with existing ID")
			err = k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())
			resource.Status.TunnelID = "existing-tunnel-id"
			err = k8sClient.Status().Update(ctx, resource)
			Expect(err).NotTo(HaveOccurred())

			By("Setting up mock tunnel deletion")
			deleteCalled := false
			mockCFClient.DeleteTunnelFunc = func(ctx context.Context, accountID, tunnelID string) error {
				deleteCalled = true
				Expect(accountID).To(Equal(accountID))
				Expect(tunnelID).To(Equal("existing-tunnel-id"))
				return nil
			}

			By("Deleting the resource")
			err = k8sClient.Delete(ctx, resource)
			Expect(err).NotTo(HaveOccurred())

			By("Reconciling to handle deletion")
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())
			Expect(deleteCalled).To(BeTrue())

			By("Checking if resource was deleted")
			err = k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(errors.IsNotFound(err)).To(BeTrue())
		})
	})
})
