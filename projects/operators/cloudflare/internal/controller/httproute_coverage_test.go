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
	apimeta "k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
)

var _ = Describe("HTTPRoute Controller Coverage", func() {
	var ctx context.Context

	BeforeEach(func() {
		ctx = context.Background()
	})

	newHTTPRouteReconciler := func() *HTTPRouteReconciler {
		return &HTTPRouteReconciler{
			Client: k8sClient,
			Scheme: k8sClient.Scheme(),
			tracer: telemetry.GetTracer("test-httproute-coverage"),
		}
	}

	createTestHTTPRoute := func(name string) *gatewayv1.HTTPRoute {
		route := &gatewayv1.HTTPRoute{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
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
		return route
	}

	Context("handleError", func() {
		It("should set RouteConditionAccepted=False with reason GatewayNotFound and return the original error", func() {
			routeName := fmt.Sprintf("gw-cov-%d", time.Now().UnixNano())
			route := createTestHTTPRoute(routeName)
			DeferCleanup(func() {
				route.Finalizers = []string{}
				_ = k8sClient.Update(ctx, route)
				_ = k8sClient.Delete(ctx, route)
			})

			testErr := fmt.Errorf("gateway lookup failed")
			r := newHTTPRouteReconciler()
			result, err := r.handleError(ctx, route, testErr, "Failed to get Gateway")

			By("Verifying the original error is returned")
			Expect(err).To(Equal(testErr))

			By("Verifying RequeueAfter is 30 seconds")
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))

			By("Verifying the status was updated in k8s")
			updated := &gatewayv1.HTTPRoute{}
			Expect(k8sClient.Get(ctx, types.NamespacedName{Name: routeName, Namespace: "default"}, updated)).To(Succeed())

			By("Verifying there is a parent status entry")
			Expect(updated.Status.RouteStatus.Parents).To(HaveLen(1))

			By("Verifying the ControllerName is set")
			Expect(string(updated.Status.RouteStatus.Parents[0].ControllerName)).To(Equal(string(ControllerName)))

			By("Verifying RouteConditionAccepted=False with GatewayNotFound reason")
			cond := apimeta.FindStatusCondition(
				updated.Status.RouteStatus.Parents[0].Conditions,
				string(gatewayv1.RouteConditionAccepted),
			)
			Expect(cond).NotTo(BeNil())
			Expect(cond.Status).To(Equal(metav1.ConditionFalse))
			Expect(cond.Reason).To(Equal("GatewayNotFound"))
			Expect(cond.Message).To(Equal("Failed to get Gateway: gateway lookup failed"))
		})

		It("should return error even when status update fails (nonexistent route)", func() {
			routeName := fmt.Sprintf("gw-cov-%d", time.Now().UnixNano())
			// Do not create this route in k8s — status update will fail
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

			testErr := fmt.Errorf("route error")
			r := newHTTPRouteReconciler()
			result, err := r.handleError(ctx, route, testErr, "operation failed")

			By("Verifying the original error is still returned despite status update failure")
			Expect(err).To(Equal(testErr))
			Expect(result.RequeueAfter).To(Equal(30 * time.Second))
		})
	})
})
