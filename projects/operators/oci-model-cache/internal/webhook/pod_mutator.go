package webhook

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/webhook/admission"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/ociref"
	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
	"github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/controller"
	"github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/hfref"
	"github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/naming"
	sm "github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/statemachine"
)

// PodMutator handles mutating admission requests for Pods.
// It scans pod volumes for hf.co/ image volume references, creates
// ModelCache CRs if needed, and always rewrites the volume ref to a
// valid OCI reference. If the model is not yet Ready, a scheduling gate
// is added to block scheduling until the cache is populated.
type PodMutator struct {
	Client   client.Client
	Decoder  admission.Decoder
	Registry string // Default OCI registry
	HFClient *hf.Client
}

// Handle implements admission.Handler.
func (m *PodMutator) Handle(ctx context.Context, req admission.Request) admission.Response {
	log := logf.FromContext(ctx).WithName("pod-mutator")

	pod := &corev1.Pod{}
	if err := m.Decoder.Decode(req, pod); err != nil {
		return admission.Errored(http.StatusBadRequest, err)
	}

	mutated := false
	var waitingFor []string

	for i, vol := range pod.Spec.Volumes {
		if vol.Image == nil {
			continue
		}

		repo, file, ok := hfref.Parse(vol.Image.Reference)
		if !ok {
			continue
		}

		log.Info("Found hf.co volume", "volume", vol.Name, "repo", repo, "file", file)

		// Derive the ModelCache CR name
		mcName := naming.ModelCacheName(repo, file)

		// Look up or create the ModelCache CR
		mc, err := m.ensureModelCache(ctx, mcName, repo, file)
		if err != nil {
			log.Error(err, "Failed to ensure ModelCache", "name", mcName)
			// Don't block pod creation — just log the error
			continue
		}

		// Always rewrite the volume ref — pod spec is immutable after admission.
		if mc.Status.ResolvedRef != "" {
			// Use the ref already computed by the controller (any phase).
			log.Info("Rewriting volume from status", "volume", vol.Name, "ref", mc.Status.ResolvedRef)
			pod.Spec.Volumes[i].Image.Reference = mc.Status.ResolvedRef
		} else {
			// ModelCache is brand new (no resolvedRef yet) — compute via HF API.
			resolved := ociref.ResolveRef(ctx, m.HFClient, repo, m.Registry, file)
			log.Info("Rewriting volume via HF API", "volume", vol.Name, "ref", resolved)
			pod.Spec.Volumes[i].Image.Reference = resolved
		}
		mutated = true

		// Gate if model is not yet Ready.
		if mc.Status.Phase != sm.PhaseReady {
			log.Info("Model not ready, gating pod", "volume", vol.Name, "modelCache", mcName, "phase", mc.Status.Phase)
			waitingFor = append(waitingFor, mcName)
		}
	}

	if len(waitingFor) > 0 {
		// Add scheduling gate
		pod.Spec.SchedulingGates = append(pod.Spec.SchedulingGates, corev1.PodSchedulingGate{
			Name: controller.SchedulingGateName,
		})
		// Set annotation so the controller can find this pod
		if pod.Annotations == nil {
			pod.Annotations = make(map[string]string)
		}
		// Use the first waiting-for ModelCache (simplification: one gate covers all)
		pod.Annotations[controller.AnnotationWaitingFor] = waitingFor[0]
	}

	if !mutated {
		return admission.Allowed("no hf.co volumes found")
	}

	marshaledPod, err := json.Marshal(pod)
	if err != nil {
		return admission.Errored(http.StatusInternalServerError, err)
	}

	return admission.PatchResponseFromRaw(req.Object.Raw, marshaledPod)
}

// ensureModelCache looks up an existing ModelCache or creates a new one.
func (m *PodMutator) ensureModelCache(ctx context.Context, name, repo, file string) (*v1alpha1.ModelCache, error) {
	mc := &v1alpha1.ModelCache{}
	err := m.Client.Get(ctx, client.ObjectKey{Name: name}, mc)
	if err == nil {
		return mc, nil
	}
	if !errors.IsNotFound(err) {
		return nil, fmt.Errorf("looking up ModelCache %s: %w", name, err)
	}

	// Create a new ModelCache CR
	mc = &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{
			Name: name,
			Labels: map[string]string{
				"app.kubernetes.io/managed-by": "oci-model-cache-webhook",
			},
		},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     repo,
			Registry: m.Registry,
			File:     file,
		},
	}

	if err := m.Client.Create(ctx, mc); err != nil {
		if errors.IsAlreadyExists(err) {
			// Race condition — re-fetch
			return mc, m.Client.Get(ctx, client.ObjectKey{Name: name}, mc)
		}
		return nil, fmt.Errorf("creating ModelCache %s: %w", name, err)
	}

	return mc, nil
}
