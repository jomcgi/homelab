package controller

import (
	"fmt"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"

	v1alpha1 "github.com/jomcgi/homelab/operators/oci-model-cache/api/v1alpha1"
	"github.com/jomcgi/homelab/operators/oci-model-cache/internal/config"
)

// buildCopyJob creates a Kubernetes Job that runs hf2oci to copy a HuggingFace
// model to the OCI registry. The Job writes its result as a JSON termination
// message so the controller can parse it.
func buildCopyJob(mc *v1alpha1.ModelCache, cfg config.Config) *batchv1.Job {
	jobName := fmt.Sprintf("mc-sync-%s", mc.Name)
	if len(jobName) > 63 {
		jobName = jobName[:63]
	}

	args := []string{
		"copy",
		mc.Spec.Repo,
		"--registry", mc.Spec.Registry,
		"--revision", revision(mc),
		"-o", "json",
		"-O", "/dev/termination-log",
	}
	if mc.Spec.Tag != "" {
		args = append(args, "--tag", mc.Spec.Tag)
	}
	if mc.Spec.ModelDir != "" {
		args = append(args, "--model-dir", mc.Spec.ModelDir)
	}

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      jobName,
			Namespace: cfg.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":                "oci-model-cache",
				"app.kubernetes.io/component":           "sync",
				"app.kubernetes.io/managed-by":          "oci-model-cache-operator",
				"oci-model-cache.jomcgi.dev/modelcache": mc.Name,
			},
		},
		Spec: batchv1.JobSpec{
			// Don't retry — the controller manages retry logic
			BackoffLimit: ptr.To(int32(0)),
			// Clean up completed Jobs after 5 minutes
			TTLSecondsAfterFinished: ptr.To(int32(300)),
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					RestartPolicy: corev1.RestartPolicyNever,
					Containers: []corev1.Container{
						{
							Name:  "hf2oci",
							Image: cfg.CopyImage,
							Args:  args,
							SecurityContext: &corev1.SecurityContext{
								RunAsNonRoot:             ptr.To(true),
								AllowPrivilegeEscalation: ptr.To(false),
								Capabilities: &corev1.Capabilities{
									Drop: []corev1.Capability{"ALL"},
								},
								SeccompProfile: &corev1.SeccompProfile{
									Type: corev1.SeccompProfileTypeRuntimeDefault,
								},
							},
							TerminationMessagePolicy: corev1.TerminationMessageFallbackToLogsOnError,
						},
					},
				},
			},
		},
	}

	if cfg.SyncServiceAccount != "" {
		job.Spec.Template.Spec.ServiceAccountName = cfg.SyncServiceAccount
	}

	if cfg.HFTokenSecret != "" {
		job.Spec.Template.Spec.Containers[0].Env = append(
			job.Spec.Template.Spec.Containers[0].Env,
			corev1.EnvVar{
				Name: "HF_TOKEN",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: cfg.HFTokenSecret},
						Key:                  cfg.HFTokenSecretKey,
					},
				},
			},
		)
	}

	return job
}

func revision(mc *v1alpha1.ModelCache) string {
	if mc.Spec.Revision != "" {
		return mc.Spec.Revision
	}
	return "main"
}

// isJobComplete returns true if the Job has completed successfully.
func isJobComplete(job *batchv1.Job) bool {
	for _, c := range job.Status.Conditions {
		if c.Type == batchv1.JobComplete && c.Status == corev1.ConditionTrue {
			return true
		}
	}
	return false
}

// isJobFailed returns true if the Job has failed.
func isJobFailed(job *batchv1.Job) bool {
	for _, c := range job.Status.Conditions {
		if c.Type == batchv1.JobFailed && c.Status == corev1.ConditionTrue {
			return true
		}
	}
	return false
}

// jobFailureReason extracts the failure reason from a Job.
func jobFailureReason(job *batchv1.Job) string {
	for _, c := range job.Status.Conditions {
		if c.Type == batchv1.JobFailed && c.Status == corev1.ConditionTrue {
			return c.Message
		}
	}
	return "unknown failure"
}
