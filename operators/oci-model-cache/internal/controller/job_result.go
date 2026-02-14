package controller

import (
	"context"
	"encoding/json"
	"fmt"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// terminationResult is the JSON structure written by hf2oci as a termination message.
type terminationResult struct {
	Ref       string `json:"ref"`
	Digest    string `json:"digest"`
	Repo      string `json:"repo"`
	Revision  string `json:"revision"`
	Format    string `json:"format"`
	FileCount int    `json:"fileCount"`
	TotalSize int64  `json:"totalSize"`
}

// parseTerminationMessage reads the JSON termination message from a completed Job's pod.
// hf2oci writes its result to /dev/termination-log, which Kubernetes exposes on the
// pod's container status as state.terminated.message.
func parseTerminationMessage(ctx context.Context, c client.Client, job *batchv1.Job) (*ResolveResult, error) {
	// List pods belonging to this Job.
	var pods corev1.PodList
	if err := c.List(ctx, &pods,
		client.InNamespace(job.Namespace),
		client.MatchingLabels{"job-name": job.Name},
	); err != nil {
		return nil, fmt.Errorf("listing pods for job %s: %w", job.Name, err)
	}

	// Find a terminated container with a termination message.
	for i := range pods.Items {
		for _, cs := range pods.Items[i].Status.ContainerStatuses {
			if cs.State.Terminated != nil && cs.State.Terminated.Message != "" {
				return parseResultJSON(cs.State.Terminated.Message)
			}
		}
	}

	return nil, fmt.Errorf("no termination message found on job %s", job.Name)
}

func parseResultJSON(data string) (*ResolveResult, error) {
	var tr terminationResult
	if err := json.Unmarshal([]byte(data), &tr); err != nil {
		return nil, fmt.Errorf("parsing termination message: %w", err)
	}

	return &ResolveResult{
		Ref:       tr.Ref,
		Digest:    tr.Digest,
		Revision:  tr.Revision,
		Format:    tr.Format,
		FileCount: tr.FileCount,
		TotalSize: tr.TotalSize,
		Cached:    false,
	}, nil
}
