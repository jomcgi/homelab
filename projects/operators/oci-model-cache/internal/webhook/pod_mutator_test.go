package webhook

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	admissionv1 "k8s.io/api/admission/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/webhook/admission"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
	sm "github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/statemachine"
)

func newScheme() *runtime.Scheme {
	s := runtime.NewScheme()
	_ = corev1.AddToScheme(s)
	_ = v1alpha1.AddToScheme(s)
	return s
}

func makeAdmissionRequest(t *testing.T, pod *corev1.Pod) admission.Request {
	t.Helper()
	raw, err := json.Marshal(pod)
	require.NoError(t, err)
	return admission.Request{
		AdmissionRequest: admissionv1.AdmissionRequest{
			Object: runtime.RawExtension{Raw: raw},
		},
	}
}

// findPatchStringValue finds the patch for a given path and returns its string value.
// PatchResponseFromRaw stores patches in resp.Patches (Go structs), not resp.Patch
// (raw bytes) — the latter is only populated after resp.Complete() is called by the
// webhook server. In unit tests we call Handle directly, so we use resp.Patches.
func findPatchStringValue(resp admission.Response, path string) (string, bool) {
	for _, p := range resp.Patches {
		if p.Path == path {
			if s, ok := p.Value.(string); ok {
				return s, true
			}
		}
	}
	return "", false
}

// hasPatchPath returns true if any patch operation targets the given path prefix.
func hasPatchPath(resp admission.Response, prefix string) bool {
	for _, p := range resp.Patches {
		if strings.HasPrefix(p.Path, prefix) {
			return true
		}
	}
	return false
}

func podWithHFVolume(repo string) *corev1.Pod {
	return &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "test-pod", Namespace: "default"},
		Spec: corev1.PodSpec{
			Containers: []corev1.Container{{Name: "main", Image: "busybox"}},
			Volumes: []corev1.Volume{{
				Name: "model",
				VolumeSource: corev1.VolumeSource{
					Image: &corev1.ImageVolumeSource{
						Reference: "hf.co/" + repo,
					},
				},
			}},
		},
	}
}

func podWithNoHFVolumes() *corev1.Pod {
	return &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "test-pod", Namespace: "default"},
		Spec: corev1.PodSpec{
			Containers: []corev1.Container{{Name: "main", Image: "busybox"}},
			Volumes: []corev1.Volume{{
				Name: "data",
				VolumeSource: corev1.VolumeSource{
					EmptyDir: &corev1.EmptyDirVolumeSource{},
				},
			}},
		},
	}
}

func TestHandle_ModelReady_RewritesFromStatus(t *testing.T) {
	s := newScheme()
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "nousresearch-hermes-3-8b"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "NousResearch/Hermes-3-8B",
			Registry: "ghcr.io/jomcgi/models",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:       sm.PhaseReady,
			ResolvedRef: "ghcr.io/jomcgi/models/nousresearch/hermes-3-8b:rev-main",
		},
	}

	k8sClient := fake.NewClientBuilder().WithScheme(s).WithStatusSubresource(&v1alpha1.ModelCache{}).WithObjects(mc).Build()
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("HF API should not be called when resolvedRef exists")
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/jomcgi/models",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithHFVolume("NousResearch/Hermes-3-8B")
	resp := mutator.Handle(context.Background(), makeAdmissionRequest(t, pod))
	require.True(t, resp.Allowed)
	require.NotEmpty(t, resp.Patches)

	ref, found := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	assert.True(t, found, "expected ref rewrite patch")
	assert.Equal(t, "ghcr.io/jomcgi/models/nousresearch/hermes-3-8b:rev-main", ref)

	// No scheduling gate should be added (model is Ready)
	assert.False(t, hasPatchPath(resp, "/spec/schedulingGates"), "should not gate when Ready")
}

func TestHandle_ModelNotReady_RewritesAndGates(t *testing.T) {
	s := newScheme()
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "nousresearch-hermes-3-8b"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "NousResearch/Hermes-3-8B",
			Registry: "ghcr.io/jomcgi/models",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase: sm.PhasePending,
		},
	}

	k8sClient := fake.NewClientBuilder().WithScheme(s).WithStatusSubresource(&v1alpha1.ModelCache{}).WithObjects(mc).Build()
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/models/NousResearch/Hermes-3-8B" {
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "NousResearch/Hermes-3-8B"})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/jomcgi/models",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithHFVolume("NousResearch/Hermes-3-8B")
	resp := mutator.Handle(context.Background(), makeAdmissionRequest(t, pod))
	require.True(t, resp.Allowed)
	require.NotEmpty(t, resp.Patches)

	ref, found := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	assert.True(t, found, "expected ref rewrite patch")
	assert.Equal(t, "ghcr.io/jomcgi/models/nousresearch/hermes-3-8b:rev-main", ref)
	assert.True(t, hasPatchPath(resp, "/spec/schedulingGates"), "should gate when Pending")
}

func TestHandle_ModelNotReady_HasResolvedRef(t *testing.T) {
	s := newScheme()
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "nousresearch-hermes-3-8b"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "NousResearch/Hermes-3-8B",
			Registry: "ghcr.io/jomcgi/models",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:       "Syncing",
			ResolvedRef: "ghcr.io/jomcgi/models/nousresearch/hermes-3-8b:rev-main",
		},
	}

	k8sClient := fake.NewClientBuilder().WithScheme(s).WithStatusSubresource(&v1alpha1.ModelCache{}).WithObjects(mc).Build()
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("HF API should not be called when resolvedRef exists")
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/jomcgi/models",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithHFVolume("NousResearch/Hermes-3-8B")
	resp := mutator.Handle(context.Background(), makeAdmissionRequest(t, pod))
	require.True(t, resp.Allowed)

	ref, found := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	assert.True(t, found, "expected ref rewrite from status")
	assert.Equal(t, "ghcr.io/jomcgi/models/nousresearch/hermes-3-8b:rev-main", ref)
	assert.True(t, hasPatchPath(resp, "/spec/schedulingGates"), "should gate — model is Syncing, not Ready")
}

func TestHandle_DerivativeModel_SmartNaming(t *testing.T) {
	s := newScheme()
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "emilio407-nllb-200-distilled-1.3b-4bit"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "Emilio407/nllb-200-distilled-1.3B-4bit",
			Registry: "ghcr.io/jomcgi/models",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase: sm.PhasePending,
		},
	}

	k8sClient := fake.NewClientBuilder().WithScheme(s).WithStatusSubresource(&v1alpha1.ModelCache{}).WithObjects(mc).Build()
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/models/Emilio407/nllb-200-distilled-1.3B-4bit" {
			json.NewEncoder(w).Encode(hf.ModelInfo{
				ID: "Emilio407/nllb-200-distilled-1.3B-4bit",
				BaseModels: &hf.BaseModels{
					Relation: "quantized",
					Models:   []hf.BaseModel{{ID: "facebook/nllb-200-distilled-1.3B"}},
				},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/jomcgi/models",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithHFVolume("Emilio407/nllb-200-distilled-1.3B-4bit")
	resp := mutator.Handle(context.Background(), makeAdmissionRequest(t, pod))
	require.True(t, resp.Allowed)
	require.NotEmpty(t, resp.Patches)

	ref, found := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	require.True(t, found, "expected ref rewrite patch")
	assert.Equal(t, "ghcr.io/jomcgi/models/facebook/nllb-200-distilled-1.3b:emilio407-nllb-200-distilled-1.3b-4bit", ref)
}

func TestHandle_HFUnavailable_FallbackNaming(t *testing.T) {
	s := newScheme()
	mc := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "org-model"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "Org/Model",
			Registry: "ghcr.io/test",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase: sm.PhasePending,
		},
	}

	k8sClient := fake.NewClientBuilder().WithScheme(s).WithStatusSubresource(&v1alpha1.ModelCache{}).WithObjects(mc).Build()
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/test",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithHFVolume("Org/Model")
	resp := mutator.Handle(context.Background(), makeAdmissionRequest(t, pod))
	require.True(t, resp.Allowed)
	require.NotEmpty(t, resp.Patches)

	ref, found := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	require.True(t, found, "expected ref rewrite patch")
	assert.Equal(t, "ghcr.io/test/org/model:rev-main", ref)
}

func TestHandle_NoHFVolumes(t *testing.T) {
	s := newScheme()
	k8sClient := fake.NewClientBuilder().WithScheme(s).Build()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/test",
		HFClient: hf.NewClient(),
	}

	pod := podWithNoHFVolumes()
	resp := mutator.Handle(context.Background(), makeAdmissionRequest(t, pod))

	require.True(t, resp.Allowed)
	assert.Empty(t, resp.Patches, "no patches expected for non-HF volumes")
	assert.Contains(t, resp.Result.Message, "no hf.co volumes")
}

func TestHandle_NewModelCache_CreatedAndGated(t *testing.T) {
	s := newScheme()
	k8sClient := fake.NewClientBuilder().WithScheme(s).Build()

	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/models/Org/NewModel" {
			json.NewEncoder(w).Encode(hf.ModelInfo{ID: "Org/NewModel"})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/test",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithHFVolume("Org/NewModel")
	resp := mutator.Handle(context.Background(), makeAdmissionRequest(t, pod))
	require.True(t, resp.Allowed)
	require.NotEmpty(t, resp.Patches)

	ref, found := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	assert.True(t, found, "expected ref rewrite")
	assert.Equal(t, "ghcr.io/test/org/newmodel:rev-main", ref)
	assert.True(t, hasPatchPath(resp, "/spec/schedulingGates"), "should gate — newly created MC not Ready")

	// Verify the ModelCache CR was created
	mc := &v1alpha1.ModelCache{}
	err := k8sClient.Get(context.Background(), client.ObjectKey{Name: "org-newmodel"}, mc)
	require.NoError(t, err, "ModelCache CR should have been created")
	assert.Equal(t, "Org/NewModel", mc.Spec.Repo)
	assert.Equal(t, "ghcr.io/test", mc.Spec.Registry)
}
