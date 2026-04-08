package controller

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/client/interceptor"
)

// TestParseTerminationMessage_ListError verifies that when the client.List call
// fails, parseTerminationMessage wraps and returns the error.
// This covers the error branch at: return nil, fmt.Errorf("listing pods for job %s: %w", job.Name, err)
func TestParseTerminationMessage_ListError(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-test",
			Namespace: "default",
		},
	}

	listErr := errors.New("etcd: connection refused")

	c := fake.NewClientBuilder().
		WithScheme(scheme).
		WithInterceptorFuncs(interceptor.Funcs{
			List: func(ctx context.Context, cl client.WithWatch, list client.ObjectList, opts ...client.ListOption) error {
				return listErr
			},
		}).
		Build()

	_, err := parseTerminationMessage(context.Background(), c, job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "listing pods for job mc-sync-test")
	assert.ErrorIs(t, err, listErr)
}

// TestParseTerminationMessage_MultiplePods verifies that parseTerminationMessage
// iterates over multiple pods and picks up the termination message from the
// second pod when the first has no terminated container.
// This exercises the outer for-loop continuing past the first pod.
func TestParseTerminationMessage_MultiplePods(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-multi",
			Namespace: "default",
		},
	}

	// First pod: running — no termination message.
	pod1 := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-multi-aaa11",
			Namespace: "default",
			Labels:    map[string]string{"job-name": "mc-sync-multi"},
		},
		Status: corev1.PodStatus{
			ContainerStatuses: []corev1.ContainerStatus{
				{
					Name: "hf2oci",
					State: corev1.ContainerState{
						Running: &corev1.ContainerStateRunning{},
					},
				},
			},
		},
	}

	// Second pod: terminated with a valid message.
	pod2 := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-multi-bbb22",
			Namespace: "default",
			Labels:    map[string]string{"job-name": "mc-sync-multi"},
		},
		Status: corev1.PodStatus{
			ContainerStatuses: []corev1.ContainerStatus{
				{
					Name: "hf2oci",
					State: corev1.ContainerState{
						Terminated: &corev1.ContainerStateTerminated{
							ExitCode: 0,
							Message:  `{"ref":"ghcr.io/test/model:v2","digest":"sha256:def456","revision":"v2","format":"gguf","fileCount":2,"totalSize":2048}`,
						},
					},
				},
			},
		},
	}

	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod1, pod2).Build()

	result, err := parseTerminationMessage(context.Background(), c, job)
	require.NoError(t, err)
	assert.Equal(t, "ghcr.io/test/model:v2", result.Ref)
	assert.Equal(t, "sha256:def456", result.Digest)
	assert.Equal(t, "v2", result.Revision)
	assert.Equal(t, "gguf", result.Format)
	assert.Equal(t, 2, result.FileCount)
	assert.Equal(t, int64(2048), result.TotalSize)
	assert.False(t, result.Cached)
}

// TestParseTerminationMessage_MultipleContainers verifies that parseTerminationMessage
// iterates container statuses within a single pod and picks up the termination
// message from the second container when the first has no terminated state.
// This exercises the inner for-loop continuing past the first container status.
func TestParseTerminationMessage_MultipleContainers(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-multicontainer",
			Namespace: "default",
		},
	}

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-multicontainer-abc12",
			Namespace: "default",
			Labels:    map[string]string{"job-name": "mc-sync-multicontainer"},
		},
		Status: corev1.PodStatus{
			ContainerStatuses: []corev1.ContainerStatus{
				{
					// First container: init-style container still running — no termination.
					Name: "init-container",
					State: corev1.ContainerState{
						Running: &corev1.ContainerStateRunning{},
					},
				},
				{
					// Second container: hf2oci — terminated with a valid result.
					Name: "hf2oci",
					State: corev1.ContainerState{
						Terminated: &corev1.ContainerStateTerminated{
							ExitCode: 0,
							Message:  `{"ref":"ghcr.io/test/model:v3","digest":"sha256:ghi789","revision":"v3","format":"safetensors","fileCount":5,"totalSize":4096}`,
						},
					},
				},
			},
		},
	}

	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()

	result, err := parseTerminationMessage(context.Background(), c, job)
	require.NoError(t, err)
	assert.Equal(t, "ghcr.io/test/model:v3", result.Ref)
	assert.Equal(t, "sha256:ghi789", result.Digest)
	assert.Equal(t, "v3", result.Revision)
	assert.Equal(t, "safetensors", result.Format)
	assert.Equal(t, 5, result.FileCount)
	assert.Equal(t, int64(4096), result.TotalSize)
}

// TestParseTerminationMessage_InvalidJSON verifies that when the pod's termination
// message contains invalid JSON, parseTerminationMessage propagates the parse error
// returned by parseResultJSON.
// This covers the parseResultJSON error path when invoked from the wrapper.
func TestParseTerminationMessage_InvalidJSON(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-badjson",
			Namespace: "default",
		},
	}

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-badjson-abc12",
			Namespace: "default",
			Labels:    map[string]string{"job-name": "mc-sync-badjson"},
		},
		Status: corev1.PodStatus{
			ContainerStatuses: []corev1.ContainerStatus{
				{
					Name: "hf2oci",
					State: corev1.ContainerState{
						Terminated: &corev1.ContainerStateTerminated{
							ExitCode: 0,
							Message:  "this-is-not-json",
						},
					},
				},
			},
		},
	}

	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()

	_, err := parseTerminationMessage(context.Background(), c, job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "parsing termination message")
}
