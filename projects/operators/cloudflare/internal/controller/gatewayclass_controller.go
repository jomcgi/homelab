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

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	// ControllerName is the controller name used in GatewayClass spec.controllerName
	ControllerName = "github.com/jomcgi/homelab/projects/operators/cloudflare"

	// GatewayClassConditionReasonAccepted indicates the GatewayClass is accepted
	GatewayClassConditionReasonAccepted = "Accepted"

	// GatewayClassConditionReasonInvalidParameters indicates invalid parameters
	GatewayClassConditionReasonInvalidParameters = "InvalidParameters"

	// GatewayClassConditionReasonUnsupportedVersion indicates unsupported version
	GatewayClassConditionReasonUnsupportedVersion = "UnsupportedVersion"
)

// GatewayClassReconciler reconciles a GatewayClass object
type GatewayClassReconciler struct {
	client.Client
	Scheme *runtime.Scheme
	tracer trace.Tracer
}

// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gatewayclasses,verbs=get;list;watch
// +kubebuilder:rbac:groups=gateway.networking.k8s.io,resources=gatewayclasses/status,verbs=get;update;patch
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch

// Reconcile is part of the main kubernetes reconciliation loop
func (r *GatewayClassReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	// Start span for reconciliation
	ctx, span := r.tracer.Start(ctx, "GatewayClass.Reconcile",
		trace.WithAttributes(
			attribute.String("k8s.resource.name", req.Name),
		),
	)
	defer span.End()

	log := log.FromContext(ctx)

	// Fetch the GatewayClass instance
	var gatewayClass gatewayv1.GatewayClass
	if err := r.Get(ctx, req.NamespacedName, &gatewayClass); err != nil {
		if errors.IsNotFound(err) {
			log.V(1).Info("GatewayClass resource not found, ignoring since object must be deleted")
			span.SetStatus(codes.Ok, "resource not found")
			return ctrl.Result{}, nil
		}
		log.Error(err, "failed to get GatewayClass")
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get resource")
		return ctrl.Result{}, err
	}

	// Only reconcile GatewayClasses managed by this controller
	if gatewayClass.Spec.ControllerName != ControllerName {
		log.V(1).Info("GatewayClass not managed by this controller",
			"controllerName", gatewayClass.Spec.ControllerName,
			"expectedControllerName", ControllerName,
		)
		span.SetStatus(codes.Ok, "not managed by this controller")
		return ctrl.Result{}, nil
	}

	span.SetAttributes(
		attribute.String("gatewayclass.name", gatewayClass.Name),
		attribute.String("gatewayclass.controller", string(gatewayClass.Spec.ControllerName)),
	)

	// Validate GatewayClass parameters
	result, err := r.validateGatewayClass(ctx, &gatewayClass)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "validation failed")
		return result, err
	}

	span.SetStatus(codes.Ok, "reconciliation successful")
	return ctrl.Result{}, nil
}

// validateGatewayClass validates the GatewayClass and updates status conditions
func (r *GatewayClassReconciler) validateGatewayClass(ctx context.Context, gatewayClass *gatewayv1.GatewayClass) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Validate parametersRef if provided
	if gatewayClass.Spec.ParametersRef != nil {
		if err := r.validateParametersRef(ctx, gatewayClass.Spec.ParametersRef); err != nil {
			log.Error(err, "invalid parametersRef")

			// Set Accepted condition to False
			meta.SetStatusCondition(&gatewayClass.Status.Conditions, metav1.Condition{
				Type:               string(gatewayv1.GatewayClassConditionStatusAccepted),
				Status:             metav1.ConditionFalse,
				Reason:             GatewayClassConditionReasonInvalidParameters,
				Message:            fmt.Sprintf("Invalid parametersRef: %v", err),
				ObservedGeneration: gatewayClass.Generation,
			})

			if err := r.Status().Update(ctx, gatewayClass); err != nil {
				log.Error(err, "failed to update GatewayClass status")
				return ctrl.Result{}, err
			}

			// Don't requeue - wait for parameters to be fixed
			return ctrl.Result{}, nil
		}
	}

	// GatewayClass is valid - set Accepted condition to True
	log.Info("GatewayClass accepted", "name", gatewayClass.Name)

	meta.SetStatusCondition(&gatewayClass.Status.Conditions, metav1.Condition{
		Type:               string(gatewayv1.GatewayClassConditionStatusAccepted),
		Status:             metav1.ConditionTrue,
		Reason:             GatewayClassConditionReasonAccepted,
		Message:            "GatewayClass accepted by controller",
		ObservedGeneration: gatewayClass.Generation,
	})

	// SupportedFeatures is experimental in Gateway API v1.2.1
	// TODO: Re-enable when feature constants are stable
	// See: https://gateway-api.sigs.k8s.io/reference/spec/#gateway.networking.k8s.io/v1.SupportedFeature

	if err := r.Status().Update(ctx, gatewayClass); err != nil {
		log.Error(err, "failed to update GatewayClass status")
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

// validateParametersRef validates that the referenced parameters exist and are valid
func (r *GatewayClassReconciler) validateParametersRef(ctx context.Context, ref *gatewayv1.ParametersReference) error {
	log := log.FromContext(ctx)

	// Currently, we only support Secret references for Cloudflare credentials
	// The secret should contain CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID
	if ref.Group != "" && ref.Group != "core" && ref.Group != "v1" {
		return fmt.Errorf("unsupported parametersRef group: %s (expected core or v1 for Secret)", ref.Group)
	}

	if ref.Kind != "Secret" {
		return fmt.Errorf("unsupported parametersRef kind: %s (expected Secret)", ref.Kind)
	}

	// Validate namespace
	namespace := ref.Namespace
	if namespace == nil {
		return fmt.Errorf("parametersRef namespace is required")
	}

	// Get the referenced Secret
	var secret corev1.Secret
	if err := r.Get(ctx, types.NamespacedName{
		Name:      ref.Name,
		Namespace: string(*namespace),
	}, &secret); err != nil {
		if errors.IsNotFound(err) {
			return fmt.Errorf("parametersRef secret not found: %s/%s", *namespace, ref.Name)
		}
		return fmt.Errorf("failed to get parametersRef secret: %w", err)
	}

	// Validate that the secret contains required fields
	if _, ok := secret.Data["CLOUDFLARE_API_TOKEN"]; !ok {
		return fmt.Errorf("secret %s/%s missing required field: CLOUDFLARE_API_TOKEN", *namespace, ref.Name)
	}

	if _, ok := secret.Data["CLOUDFLARE_ACCOUNT_ID"]; !ok {
		return fmt.Errorf("secret %s/%s missing required field: CLOUDFLARE_ACCOUNT_ID", *namespace, ref.Name)
	}

	log.V(1).Info("parametersRef secret validated successfully",
		"secret", fmt.Sprintf("%s/%s", *namespace, ref.Name),
	)

	return nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *GatewayClassReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Initialize tracer
	r.tracer = telemetry.GetTracer("gatewayclass-controller")

	return ctrl.NewControllerManagedBy(mgr).
		For(&gatewayv1.GatewayClass{}).
		Named("gatewayclass").
		Complete(r)
}
