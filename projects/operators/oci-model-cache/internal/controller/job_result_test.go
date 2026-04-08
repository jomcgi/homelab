package controller

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

func TestParseTerminationMessage(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-test",
			Namespace: "default",
		},
	}

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-test-abc12",
			Namespace: "default",
			Labels:    map[string]string{"job-name": "mc-sync-test"},
		},
		Status: corev1.PodStatus{
			ContainerStatuses: []corev1.ContainerStatus{
				{
					Name: "hf2oci",
					State: corev1.ContainerState{
						Terminated: &corev1.ContainerStateTerminated{
							ExitCode: 0,
							Message:  `{"ref":"ghcr.io/test/model:v1","digest":"sha256:abc123","revision":"main","format":"safetensors","fileCount":3,"totalSize":1024}`,
						},
					},
				},
			},
		},
	}

	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()

	result, err := parseTerminationMessage(context.Background(), c, job)
	require.NoError(t, err)

	assert.Equal(t, "ghcr.io/test/model:v1", result.Ref)
	assert.Equal(t, "sha256:abc123", result.Digest)
	assert.Equal(t, "main", result.Revision)
	assert.Equal(t, "safetensors", result.Format)
	assert.Equal(t, 3, result.FileCount)
	assert.Equal(t, int64(1024), result.TotalSize)
}

func TestParseTerminationMessageNoPod(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-test",
			Namespace: "default",
		},
	}

	c := fake.NewClientBuilder().WithScheme(scheme).Build()

	_, err := parseTerminationMessage(context.Background(), c, job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "no termination message found")
}

func TestParseResultJSON(t *testing.T) {
	result, err := parseResultJSON(`{"ref":"ghcr.io/r/m:t","digest":"sha256:def","revision":"v2","format":"gguf","fileCount":1,"totalSize":500}`)
	require.NoError(t, err)
	assert.Equal(t, "ghcr.io/r/m:t", result.Ref)
	assert.Equal(t, "sha256:def", result.Digest)
	assert.Equal(t, "v2", result.Revision)
	assert.Equal(t, "gguf", result.Format)
	assert.Equal(t, 1, result.FileCount)
	assert.Equal(t, int64(500), result.TotalSize)
}

func TestParseResultJSONInvalid(t *testing.T) {
	_, err := parseResultJSON("not-json")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "parsing termination message")
}

// TestParseTerminationMessage_RunningPod verifies that when a pod's container
// is Running (not yet Terminated), parseTerminationMessage returns an error.
// This covers the inner loop body where cs.State.Terminated == nil, causing the
// function to fall through and return "no termination message found".
func TestParseTerminationMessage_RunningPod(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-running",
			Namespace: "default",
		},
	}

	// Pod exists with a Running container but no Terminated state.
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-running-abc12",
			Namespace: "default",
			Labels:    map[string]string{"job-name": "mc-sync-running"},
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

	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()

	_, err := parseTerminationMessage(context.Background(), c, job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "no termination message found")
}

// TestParseTerminationMessage_TerminatedEmptyMessage verifies that a container
// that has terminated but left an empty termination message is skipped, causing
// parseTerminationMessage to return "no termination message found".
// This covers the `cs.State.Terminated.Message != ""` guard in the inner loop.
func TestParseTerminationMessage_TerminatedEmptyMessage(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(scheme))

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-empty-msg",
			Namespace: "default",
		},
	}

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "mc-sync-empty-msg-abc12",
			Namespace: "default",
			Labels:    map[string]string{"job-name": "mc-sync-empty-msg"},
		},
		Status: corev1.PodStatus{
			ContainerStatuses: []corev1.ContainerStatus{
				{
					Name: "hf2oci",
					State: corev1.ContainerState{
						Terminated: &corev1.ContainerStateTerminated{
							ExitCode: 0,
							Message:  "", // empty — hf2oci did not write a result
						},
					},
				},
			},
		},
	}

	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(pod).Build()

	_, err := parseTerminationMessage(context.Background(), c, job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "no termination message found")
}

// TestParseResultJSON_CachedIsAlwaysFalse verifies that parseResultJSON always
// sets Cached=false regardless of any JSON content. The hf2oci termination
// message format does not include a "cached" field; cache hits are detected
// by the resolver before a job is created.
func TestParseResultJSON_CachedIsAlwaysFalse(t *testing.T) {
	result, err := parseResultJSON(`{"ref":"ghcr.io/r/m:t","digest":"sha256:abc","revision":"main","format":"safetensors","fileCount":5,"totalSize":1024}`)
	require.NoError(t, err)
	assert.False(t, result.Cached, "parseResultJSON should always produce Cached=false")
}
