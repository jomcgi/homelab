package controller

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

// podScheme returns a runtime.Scheme with core/v1 registered.
func podScheme(t *testing.T) *runtime.Scheme {
	t.Helper()
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))
	return scheme
}

// makeGatedPod creates a Pod with the oci-model-cache scheduling gate and
// waiting-for annotation set to the given modelCacheName.
func makeGatedPod(name, namespace, modelCacheName string) *corev1.Pod {
	return &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
			Annotations: map[string]string{
				AnnotationWaitingFor: modelCacheName,
			},
		},
		Spec: corev1.PodSpec{
			SchedulingGates: []corev1.PodSchedulingGate{
				{Name: SchedulingGateName},
			},
			Containers: []corev1.Container{
				{Name: "app", Image: "nginx"},
			},
		},
	}
}

// TestUngateWaitingPods_HappyPath verifies that pods annotated for a given
// ModelCache are processed without error.
func TestUngateWaitingPods_HappyPath(t *testing.T) {
	pod := makeGatedPod("test-pod", "default", "my-model")

	scheme := podScheme(t)
	fakeClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(pod).
		Build()

	err := ungateWaitingPods(context.Background(), fakeClient, "my-model", "ghcr.io/jomcgi/models/llama:rev-main")
	require.NoError(t, err)
}

// TestUngateWaitingPods_SkipsPodForDifferentModel verifies that pods waiting
// for a different ModelCache are not patched.
func TestUngateWaitingPods_SkipsPodForDifferentModel(t *testing.T) {
	podForOtherModel := makeGatedPod("other-pod", "default", "other-model")

	scheme := podScheme(t)
	fakeClient := fake.NewClientBuilder().
		WithScheme(scheme).
		WithObjects(podForOtherModel).
		Build()

	// Ungate "my-model" — the pod is for "other-model", so it must be left alone.
	err := ungateWaitingPods(context.Background(), fakeClient, "my-model", "ghcr.io/jomcgi/models/llama:rev-main")
	require.NoError(t, err)

	// The pod's annotation should still be intact.
	var fetched corev1.Pod
	require.NoError(t, fakeClient.Get(context.Background(),
		types.NamespacedName{Namespace: "default", Name: "other-pod"}, &fetched))
	assert.Equal(t, "other-model", fetched.Annotations[AnnotationWaitingFor])
}

// TestUngateWaitingPods_NoPods verifies that ungating with an empty pod list
// returns nil without panicking.
func TestUngateWaitingPods_NoPods(t *testing.T) {
	scheme := podScheme(t)
	fakeClient := fake.NewClientBuilder().WithScheme(scheme).Build()

	err := ungateWaitingPods(context.Background(), fakeClient, "my-model", "ghcr.io/jomcgi/models/llama:rev-main")
	assert.NoError(t, err)
}

// TestUngateWaitingPods_MultiplePods verifies that multiple matching pods are
// all processed in a single call without error.
func TestUngateWaitingPods_MultiplePods(t *testing.T) {
	pods := []corev1.Pod{
		*makeGatedPod("pod-a", "default", "my-model"),
		*makeGatedPod("pod-b", "default", "my-model"),
		*makeGatedPod("pod-c", "default", "other-model"), // should not be patched
	}

	scheme := podScheme(t)
	builder := fake.NewClientBuilder().WithScheme(scheme)
	for i := range pods {
		builder = builder.WithObjects(&pods[i])
	}
	fakeClient := builder.Build()

	err := ungateWaitingPods(context.Background(), fakeClient, "my-model", "ghcr.io/jomcgi/models/llama:rev-main")
	require.NoError(t, err)
}

// TestBuildUngatePatch_RemovesGate verifies the patch removes exactly the
// oci-model-cache scheduling gate and leaves other gates intact.
func TestBuildUngatePatch_RemovesGate(t *testing.T) {
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test",
			Namespace: "default",
			Annotations: map[string]string{
				AnnotationWaitingFor: "my-model",
			},
		},
		Spec: corev1.PodSpec{
			SchedulingGates: []corev1.PodSchedulingGate{
				{Name: SchedulingGateName},
				{Name: "some-other-gate"},
			},
		},
	}

	raw, err := buildUngatePatch(pod, "ghcr.io/jomcgi/models/llama:rev-main")
	require.NoError(t, err)
	require.NotEmpty(t, raw)

	// Parse the patch and verify the gate list only contains the other gate.
	var patch struct {
		Metadata struct {
			Annotations map[string]*string `json:"annotations"`
		} `json:"metadata"`
		Spec struct {
			SchedulingGates []corev1.PodSchedulingGate `json:"schedulingGates"`
		} `json:"spec"`
	}
	require.NoError(t, json.Unmarshal(raw, &patch))

	assert.Len(t, patch.Spec.SchedulingGates, 1)
	assert.Equal(t, "some-other-gate", patch.Spec.SchedulingGates[0].Name)

	// The waiting-for annotation should be set to null (removal).
	val, ok := patch.Metadata.Annotations[AnnotationWaitingFor]
	assert.True(t, ok, "waiting-for annotation key must be present in patch")
	assert.Nil(t, val, "waiting-for annotation value must be null to remove it")

	// The resolved-ref annotation should be set to the provided value.
	resolvedVal, ok := patch.Metadata.Annotations["oci-model-cache.jomcgi.dev/resolved-ref"]
	assert.True(t, ok, "resolved-ref annotation must be present in patch")
	require.NotNil(t, resolvedVal)
	assert.Equal(t, "ghcr.io/jomcgi/models/llama:rev-main", *resolvedVal)
}

// TestBuildUngatePatch_PodWithNoGates verifies the patch can be built for a pod
// that has no scheduling gates at all.
func TestBuildUngatePatch_PodWithNoGates(t *testing.T) {
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "no-gates-pod",
			Namespace: "default",
			Annotations: map[string]string{
				AnnotationWaitingFor: "my-model",
			},
		},
		Spec: corev1.PodSpec{},
	}

	raw, err := buildUngatePatch(pod, "ghcr.io/jomcgi/models/llama:rev-main")
	require.NoError(t, err)
	require.NotEmpty(t, raw)

	var patch struct {
		Spec struct {
			SchedulingGates []corev1.PodSchedulingGate `json:"schedulingGates"`
		} `json:"spec"`
	}
	require.NoError(t, json.Unmarshal(raw, &patch))
	assert.Empty(t, patch.Spec.SchedulingGates)
}

// TestBuildUngatePatch_OnlyOurGateRemoved verifies that if the pod only has the
// oci-model-cache gate, the resulting gates list does not contain it.
func TestBuildUngatePatch_OnlyOurGateRemoved(t *testing.T) {
	pod := makeGatedPod("solo-gate", "default", "my-model")

	raw, err := buildUngatePatch(pod, "ghcr.io/jomcgi/models/llama:rev-main")
	require.NoError(t, err)
	require.NotEmpty(t, raw)

	var patch struct {
		Spec struct {
			SchedulingGates []corev1.PodSchedulingGate `json:"schedulingGates"`
		} `json:"spec"`
	}
	require.NoError(t, json.Unmarshal(raw, &patch))
	for _, g := range patch.Spec.SchedulingGates {
		assert.NotEqual(t, SchedulingGateName, g.Name)
	}
}

// TestBuildUngatePatch_TableDriven covers multiple scheduling gate configurations.
func TestBuildUngatePatch_TableDriven(t *testing.T) {
	resolvedRef := "ghcr.io/jomcgi/models/llama:rev-main"

	tests := []struct {
		name          string
		inputGates    []corev1.PodSchedulingGate
		wantGateCount int
		wantGateNames []string
	}{
		{
			name:          "only our gate",
			inputGates:    []corev1.PodSchedulingGate{{Name: SchedulingGateName}},
			wantGateCount: 0,
		},
		{
			name: "our gate plus others",
			inputGates: []corev1.PodSchedulingGate{
				{Name: SchedulingGateName},
				{Name: "gate-a"},
				{Name: "gate-b"},
			},
			wantGateCount: 2,
			wantGateNames: []string{"gate-a", "gate-b"},
		},
		{
			name:          "no gates at all",
			inputGates:    nil,
			wantGateCount: 0,
		},
		{
			name: "other gates only (not ours)",
			inputGates: []corev1.PodSchedulingGate{
				{Name: "gate-x"},
			},
			wantGateCount: 1,
			wantGateNames: []string{"gate-x"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			pod := &corev1.Pod{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "pod",
					Namespace: "default",
					Annotations: map[string]string{
						AnnotationWaitingFor: "my-model",
					},
				},
				Spec: corev1.PodSpec{SchedulingGates: tt.inputGates},
			}

			raw, err := buildUngatePatch(pod, resolvedRef)
			require.NoError(t, err)

			var patch struct {
				Spec struct {
					SchedulingGates []corev1.PodSchedulingGate `json:"schedulingGates"`
				} `json:"spec"`
			}
			require.NoError(t, json.Unmarshal(raw, &patch))

			assert.Len(t, patch.Spec.SchedulingGates, tt.wantGateCount)
			for _, wantName := range tt.wantGateNames {
				found := false
				for _, g := range patch.Spec.SchedulingGates {
					if g.Name == wantName {
						found = true
						break
					}
				}
				assert.True(t, found, "expected gate %q to remain in patch", wantName)
			}
		})
	}
}
