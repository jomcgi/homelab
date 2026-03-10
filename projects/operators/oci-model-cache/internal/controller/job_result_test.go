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
