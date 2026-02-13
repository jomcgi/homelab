package controller

import (
	"encoding/json"
	"fmt"

	batchv1 "k8s.io/api/batch/v1"
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
// hf2oci writes its result to the container's termination message when --termination-message is set.
func parseTerminationMessage(job *batchv1.Job) (*ResolveResult, error) {
	// The termination message is in the Job status's pod template status,
	// but we need to check the pods. For simplicity, we look at the Job's
	// completionTime and the first container's termination state.
	// In practice, the controller should read the pod's termination message.

	// Check if the job has the message annotation (set by the Job controller)
	// For now, fall back to using Job annotations if the pod isn't directly accessible.

	// Try to get termination message from job annotations (workaround)
	if msg, ok := job.Annotations["oci-model-cache.jomcgi.dev/result"]; ok {
		return parseResultJSON(msg)
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
