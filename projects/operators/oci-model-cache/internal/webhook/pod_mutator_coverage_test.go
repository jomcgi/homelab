package webhook

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	admissionv1 "k8s.io/api/admission/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/client/interceptor"
	"sigs.k8s.io/controller-runtime/pkg/webhook/admission"

	"github.com/jomcgi/homelab/bazel/tools/hf2oci/pkg/hf"
	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
	sm "github.com/jomcgi/homelab/projects/operators/oci-model-cache/internal/statemachine"
)

// podWithTwoHFVolumes builds a Pod with two hf.co image volumes pointing at
// different model repos.
func podWithTwoHFVolumes(repo1, repo2 string) *corev1.Pod {
	return &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "test-pod", Namespace: "default"},
		Spec: corev1.PodSpec{
			Containers: []corev1.Container{{Name: "main", Image: "busybox"}},
			Volumes: []corev1.Volume{
				{
					Name: "model-a",
					VolumeSource: corev1.VolumeSource{
						Image: &corev1.ImageVolumeSource{
							Reference: "hf.co/" + repo1,
						},
					},
				},
				{
					Name: "model-b",
					VolumeSource: corev1.VolumeSource{
						Image: &corev1.ImageVolumeSource{
							Reference: "hf.co/" + repo2,
						},
					},
				},
			},
		},
	}
}

// makeAdmissionRequestCoverage converts a Pod to an admission.Request.
// This mirrors makeAdmissionRequest from the base test file.
func makeAdmissionRequestCoverage(t *testing.T, pod *corev1.Pod) admission.Request {
	t.Helper()
	raw, err := json.Marshal(pod)
	require.NoError(t, err)
	return admission.Request{
		AdmissionRequest: admissionv1.AdmissionRequest{
			Object: runtime.RawExtension{Raw: raw},
		},
	}
}

// countPatchesWithPrefix returns the number of patch operations whose path
// starts with the given prefix.
func countPatchesWithPrefix(resp admission.Response, prefix string) int {
	count := 0
	for _, p := range resp.Patches {
		if len(p.Path) >= len(prefix) && p.Path[:len(prefix)] == prefix {
			count++
		}
	}
	return count
}

// --- Test 1: Handle multiple HF volumes ---

// TestHandle_TwoHFVolumes_BothRewritten verifies that a pod with two hf.co
// image volumes accumulates two waitingFor entries and adds a scheduling gate
// (because neither model is Ready). Both volume references must be rewritten.
func TestHandle_TwoHFVolumes_BothRewritten(t *testing.T) {
	s := newScheme()

	// Neither model has a ModelCache pre-created — both will be created as new.
	// Use a fake HF server that returns minimal model info.
	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Accept any model lookup and return minimal info.
		w.Header().Set("Content-Type", "application/json")
		// Extract the model path from the URL and return a minimal ModelInfo.
		json.NewEncoder(w).Encode(hf.ModelInfo{ID: "org/model"})
	}))
	defer hfSrv.Close()

	k8sClient := fake.NewClientBuilder().WithScheme(s).Build()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/test",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithTwoHFVolumes("Org/ModelA", "Org/ModelB")
	resp := mutator.Handle(context.Background(), makeAdmissionRequestCoverage(t, pod))

	require.True(t, resp.Allowed, "admission should be allowed")
	require.NotEmpty(t, resp.Patches, "two volumes should generate patches")

	// Both volumes should have their references rewritten.
	refPatchCount := countPatchesWithPrefix(resp, "/spec/volumes/")
	assert.GreaterOrEqual(t, refPatchCount, 2,
		"both hf.co volume references should be rewritten")

	// A scheduling gate should be added (neither model is Ready).
	assert.True(t, hasPatchPath(resp, "/spec/schedulingGates"),
		"a scheduling gate should be added when model is not Ready")

	// The annotation should be set (pointing to one of the two waiting-for names).
	assert.True(t, hasPatchPath(resp, "/metadata/annotations"),
		"waiting-for annotation should be patched")

	// Both ModelCache CRs should have been created.
	var mcList v1alpha1.ModelCacheList
	require.NoError(t, k8sClient.List(context.Background(), &mcList))
	assert.Equal(t, 2, len(mcList.Items),
		"one ModelCache CR per HF volume should be created")
}

// TestHandle_TwoHFVolumes_BothReady_NoGate verifies that when both model caches
// are in Ready state, no scheduling gate is added.
func TestHandle_TwoHFVolumes_BothReady_NoGate(t *testing.T) {
	s := newScheme()

	mc1 := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "org-modela"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "Org/ModelA",
			Registry: "ghcr.io/test",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:       sm.PhaseReady,
			ResolvedRef: "ghcr.io/test/org/modela:rev-main",
		},
	}
	mc2 := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "org-modelb"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "Org/ModelB",
			Registry: "ghcr.io/test",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:       sm.PhaseReady,
			ResolvedRef: "ghcr.io/test/org/modelb:rev-main",
		},
	}

	k8sClient := fake.NewClientBuilder().
		WithScheme(s).
		WithStatusSubresource(&v1alpha1.ModelCache{}).
		WithObjects(mc1, mc2).
		Build()

	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("HF API should not be called when resolvedRef exists")
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   k8sClient,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/test",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithTwoHFVolumes("Org/ModelA", "Org/ModelB")
	resp := mutator.Handle(context.Background(), makeAdmissionRequestCoverage(t, pod))

	require.True(t, resp.Allowed)
	require.NotEmpty(t, resp.Patches)

	// Both volumes should be rewritten from status.
	ref0, found0 := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	assert.True(t, found0, "first volume should be rewritten")
	assert.Equal(t, "ghcr.io/test/org/modela:rev-main", ref0)

	ref1, found1 := findPatchStringValue(resp, "/spec/volumes/1/image/reference")
	assert.True(t, found1, "second volume should be rewritten")
	assert.Equal(t, "ghcr.io/test/org/modelb:rev-main", ref1)

	// No gate should be added when both are Ready.
	assert.False(t, hasPatchPath(resp, "/spec/schedulingGates"),
		"no scheduling gate should be added when all models are Ready")
}

// --- Test 2: ensureModelCache IsAlreadyExists race condition ---

// TestEnsureModelCache_AlreadyExists_ReFetchesExisting verifies that when creating
// a ModelCache races (Create returns AlreadyExists), ensureModelCache re-fetches
// the existing object and returns it. This means the pod volume is rewritten
// using the existing resolvedRef rather than an empty ref.
func TestEnsureModelCache_AlreadyExists_ReFetchesExisting(t *testing.T) {
	s := newScheme()

	// Pre-create a ModelCache with a resolvedRef already set.
	existingMC := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "org-racemodel"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "Org/RaceModel",
			Registry: "ghcr.io/test",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:       sm.PhaseSyncing,
			ResolvedRef: "ghcr.io/test/org/racemodel:rev-abc123",
		},
	}

	// Build a base fake client that already holds the pre-existing MC.
	fakeBase := fake.NewClientBuilder().
		WithScheme(s).
		WithStatusSubresource(&v1alpha1.ModelCache{}).
		WithObjects(existingMC).
		Build()

	// Intercept Get: first call returns NotFound so the webhook tries to Create;
	// subsequent calls return the real object (simulating the race window closing).
	getCalls := 0
	intercepted := fake.NewClientBuilder().
		WithScheme(s).
		WithStatusSubresource(&v1alpha1.ModelCache{}).
		WithObjects(existingMC).
		WithInterceptorFuncs(interceptor.Funcs{
			Create: func(ctx context.Context, c client.WithWatch, obj client.Object, opts ...client.CreateOption) error {
				if _, ok := obj.(*v1alpha1.ModelCache); ok {
					// Simulate the race: another controller already created it.
					return apierrors.NewAlreadyExists(
						schema.GroupResource{Group: "oci-model-cache.jomcgi.dev", Resource: "modelcaches"},
						obj.GetName(),
					)
				}
				return c.Create(ctx, obj, opts...)
			},
			Get: func(ctx context.Context, c client.WithWatch, key client.ObjectKey, obj client.Object, opts ...client.GetOption) error {
				if _, ok := obj.(*v1alpha1.ModelCache); ok {
					getCalls++
					if getCalls == 1 {
						// First Get: return NotFound so the webhook attempts Create.
						return apierrors.NewNotFound(
							schema.GroupResource{Group: "oci-model-cache.jomcgi.dev", Resource: "modelcaches"},
							key.Name,
						)
					}
					// Subsequent Gets: delegate to the real fake client (returns the object).
					return fakeBase.Get(ctx, key, obj, opts...)
				}
				return c.Get(ctx, key, obj, opts...)
			},
		}).
		Build()

	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("HF API should not be called when re-fetching existing ModelCache")
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   intercepted,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/test",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithHFVolume("Org/RaceModel")
	resp := mutator.Handle(context.Background(), makeAdmissionRequestCoverage(t, pod))

	require.True(t, resp.Allowed, "admission should be allowed")
	require.NotEmpty(t, resp.Patches)

	// The volume should be rewritten using the re-fetched resolvedRef.
	ref, found := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	assert.True(t, found, "volume reference should be rewritten")
	assert.Equal(t, "ghcr.io/test/org/racemodel:rev-abc123", ref,
		"rewrite should use the re-fetched resolvedRef from the existing ModelCache")

	// Get should have been called at least twice (initial NotFound + re-fetch).
	assert.GreaterOrEqual(t, getCalls, 2,
		"Get should be called at least twice: initial lookup + re-fetch after AlreadyExists")
}

// TestEnsureModelCache_AlreadyExists_ModelNotReady_Gates verifies that after
// re-fetching an existing ModelCache that is not Ready, the pod is gated.
func TestEnsureModelCache_AlreadyExists_ModelNotReady_Gates(t *testing.T) {
	s := newScheme()

	// Existing MC is in Syncing phase with a resolvedRef.
	existingMC := &v1alpha1.ModelCache{
		ObjectMeta: metav1.ObjectMeta{Name: "org-syncingmodel"},
		Spec: v1alpha1.ModelCacheSpec{
			Repo:     "Org/SyncingModel",
			Registry: "ghcr.io/test",
		},
		Status: v1alpha1.ModelCacheStatus{
			Phase:       sm.PhaseSyncing,
			ResolvedRef: "ghcr.io/test/org/syncingmodel:rev-main",
		},
	}

	fakeBase := fake.NewClientBuilder().
		WithScheme(s).
		WithStatusSubresource(&v1alpha1.ModelCache{}).
		WithObjects(existingMC).
		Build()

	getCalls := 0
	intercepted := fake.NewClientBuilder().
		WithScheme(s).
		WithStatusSubresource(&v1alpha1.ModelCache{}).
		WithObjects(existingMC).
		WithInterceptorFuncs(interceptor.Funcs{
			Create: func(ctx context.Context, c client.WithWatch, obj client.Object, opts ...client.CreateOption) error {
				if _, ok := obj.(*v1alpha1.ModelCache); ok {
					return apierrors.NewAlreadyExists(
						schema.GroupResource{Group: "oci-model-cache.jomcgi.dev", Resource: "modelcaches"},
						obj.GetName(),
					)
				}
				return c.Create(ctx, obj, opts...)
			},
			Get: func(ctx context.Context, c client.WithWatch, key client.ObjectKey, obj client.Object, opts ...client.GetOption) error {
				if _, ok := obj.(*v1alpha1.ModelCache); ok {
					getCalls++
					if getCalls == 1 {
						return apierrors.NewNotFound(
							schema.GroupResource{Group: "oci-model-cache.jomcgi.dev", Resource: "modelcaches"},
							key.Name,
						)
					}
					return fakeBase.Get(ctx, key, obj, opts...)
				}
				return c.Get(ctx, key, obj, opts...)
			},
		}).
		Build()

	hfSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("HF API should not be called")
	}))
	defer hfSrv.Close()

	mutator := &PodMutator{
		Client:   intercepted,
		Decoder:  admission.NewDecoder(s),
		Registry: "ghcr.io/test",
		HFClient: hf.NewClient(hf.WithBaseURL(hfSrv.URL)),
	}

	pod := podWithHFVolume("Org/SyncingModel")
	resp := mutator.Handle(context.Background(), makeAdmissionRequestCoverage(t, pod))

	require.True(t, resp.Allowed)
	require.NotEmpty(t, resp.Patches)

	// Volume should be rewritten from the existing MC's resolvedRef.
	ref, found := findPatchStringValue(resp, "/spec/volumes/0/image/reference")
	assert.True(t, found, "volume should be rewritten from existing ModelCache")
	assert.Equal(t, "ghcr.io/test/org/syncingmodel:rev-main", ref)

	// Pod should be gated — model is Syncing, not Ready.
	assert.True(t, hasPatchPath(resp, "/spec/schedulingGates"),
		"pod should be gated when re-fetched model is not Ready")
}
