package controller

import (
	"context"
	"encoding/json"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
)

const (
	// AnnotationWaitingFor is the annotation set on pods waiting for a ModelCache to be ready.
	AnnotationWaitingFor = "oci-model-cache.jomcgi.dev/waiting-for"

	// SchedulingGateName is the scheduling gate added to pods while waiting for model cache.
	SchedulingGateName = "oci-model-cache.jomcgi.dev/gated"
)

// ungateWaitingPods finds pods annotated as waiting for the given ModelCache
// and removes their scheduling gate + rewrites their volume sources.
func ungateWaitingPods(ctx context.Context, c client.Client, mcName, resolvedRef string) error {
	log := logf.FromContext(ctx)

	// List all pods with the waiting annotation
	var pods corev1.PodList
	if err := c.List(ctx, &pods, client.MatchingFields{
		"metadata.annotations." + AnnotationWaitingFor: mcName,
	}); err != nil {
		// Field selector may not be indexed — fall back to listing all pods and filtering
		if err := c.List(ctx, &pods); err != nil {
			return fmt.Errorf("listing pods: %w", err)
		}
	}

	ungated := 0
	for i := range pods.Items {
		pod := &pods.Items[i]
		if pod.Annotations[AnnotationWaitingFor] != mcName {
			continue
		}

		// Build a JSON merge patch to:
		// 1. Remove the scheduling gate
		// 2. Remove the waiting-for annotation
		patch, err := buildUngatePatch(pod, resolvedRef)
		if err != nil {
			log.Error(err, "Failed to build ungate patch", "pod", pod.Name, "namespace", pod.Namespace)
			continue
		}

		if err := c.Patch(ctx, pod, client.RawPatch(client.MergeFrom(pod).Type(), patch)); err != nil {
			log.Error(err, "Failed to ungate pod", "pod", pod.Name, "namespace", pod.Namespace)
			continue
		}

		log.Info("Ungated pod", "pod", pod.Name, "namespace", pod.Namespace)
		ungated++
	}

	if ungated > 0 {
		log.Info("Ungated waiting pods", "count", ungated, "modelCache", mcName)
	}

	return nil
}

// buildUngatePatch creates a JSON merge patch that removes the scheduling gate
// and updates the waiting-for annotation.
func buildUngatePatch(pod *corev1.Pod, resolvedRef string) ([]byte, error) {
	// Remove the scheduling gate
	var gates []corev1.PodSchedulingGate
	for _, g := range pod.Spec.SchedulingGates {
		if g.Name != SchedulingGateName {
			gates = append(gates, g)
		}
	}

	// Build the patch
	type patchSpec struct {
		SchedulingGates []corev1.PodSchedulingGate `json:"schedulingGates"`
	}
	type patchMeta struct {
		Annotations map[string]*string `json:"annotations"`
	}
	type patchBody struct {
		Metadata patchMeta `json:"metadata"`
		Spec     patchSpec `json:"spec"`
	}

	p := patchBody{
		Metadata: patchMeta{
			Annotations: map[string]*string{
				AnnotationWaitingFor:                      nil, // remove
				"oci-model-cache.jomcgi.dev/resolved-ref": &resolvedRef,
			},
		},
		Spec: patchSpec{
			SchedulingGates: gates,
		},
	}

	return json.Marshal(p)
}
