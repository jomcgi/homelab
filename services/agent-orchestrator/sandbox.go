package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
	executil "k8s.io/client-go/util/exec"
)

var sandboxClaimGVR = schema.GroupVersionResource{
	Group:    "extensions.agents.x-k8s.io",
	Version:  "v1alpha1",
	Resource: "sandboxclaims",
}

var sandboxGVR = schema.GroupVersionResource{
	Group:    "agents.x-k8s.io",
	Version:  "v1alpha1",
	Resource: "sandboxes",
}

// SandboxExecutor manages the lifecycle of sandbox pods for running agent tasks.
type SandboxExecutor struct {
	dynClient         dynamic.Interface
	clientset         kubernetes.Interface
	config            *rest.Config
	namespace         string
	template          string
	inactivityTimeout time.Duration
	logger            *slog.Logger
}

// ExecResult holds the outcome of a sandbox execution.
type ExecResult struct {
	ClaimName string
	ExitCode  int
	Output    string
}

// NewSandboxExecutor creates a SandboxExecutor from the given Kubernetes config.
func NewSandboxExecutor(config *rest.Config, namespace, template string, inactivityTimeout time.Duration, logger *slog.Logger) (*SandboxExecutor, error) {
	dynClient, err := dynamic.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("creating dynamic client: %w", err)
	}
	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("creating clientset: %w", err)
	}
	return &SandboxExecutor{
		dynClient:         dynClient,
		clientset:         clientset,
		config:            config,
		namespace:         namespace,
		template:          template,
		inactivityTimeout: inactivityTimeout,
		logger:            logger,
	}, nil
}

// Run creates a SandboxClaim, waits for the pod, refreshes the workspace,
// executes goose with the task, captures output, and cleans up.
// The cancelFn is checked before each phase to support cooperative cancellation.
func (s *SandboxExecutor) Run(ctx context.Context, claimName, task string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error) {
	s.logger.Info("creating sandbox claim", "claim", claimName, "namespace", s.namespace)

	if err := s.createClaim(ctx, claimName); err != nil {
		return nil, fmt.Errorf("creating claim: %w", err)
	}
	defer s.deleteClaim(claimName)

	if cancelFn() {
		return nil, fmt.Errorf("cancelled before pod allocation")
	}

	podName, err := s.waitForPod(ctx, claimName)
	if err != nil {
		return nil, fmt.Errorf("waiting for pod: %w", err)
	}
	s.logger.Info("sandbox pod allocated", "pod", podName)

	if cancelFn() {
		return nil, fmt.Errorf("cancelled before pod ready")
	}

	if err := s.waitPodRunning(ctx, podName); err != nil {
		return nil, fmt.Errorf("waiting for pod running: %w", err)
	}

	if cancelFn() {
		return nil, fmt.Errorf("cancelled before workspace refresh")
	}

	s.refreshWorkspace(ctx, podName)

	if cancelFn() {
		return nil, fmt.Errorf("cancelled before exec")
	}

	s.logger.Info("running goose task", "pod", podName)
	exitCode, err := s.execGoose(ctx, podName, task, outputBuf)
	if err != nil {
		return nil, fmt.Errorf("exec goose: %w", err)
	}

	s.logger.Info("goose completed", "pod", podName, "exitCode", exitCode)
	return &ExecResult{
		ClaimName: claimName,
		ExitCode:  exitCode,
		Output:    outputBuf.String(),
	}, nil
}

func (s *SandboxExecutor) createClaim(ctx context.Context, claimName string) error {
	claim := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
			"kind":       "SandboxClaim",
			"metadata": map[string]interface{}{
				"name":      claimName,
				"namespace": s.namespace,
			},
			"spec": map[string]interface{}{
				"sandboxTemplateRef": map[string]interface{}{
					"name": s.template,
				},
				"lifecycle": map[string]interface{}{
					"shutdownPolicy": "Delete",
				},
			},
		},
	}
	_, err := s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Create(ctx, claim, metav1.CreateOptions{})
	return err
}

func (s *SandboxExecutor) deleteClaim(claimName string) {
	s.logger.Info("cleaning up sandbox claim", "claim", claimName)
	err := s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Delete(
		context.Background(), claimName, metav1.DeleteOptions{})
	if err != nil {
		s.logger.Warn("failed to delete sandbox claim", "claim", claimName, "error", err)
	}
}

// waitForPod polls the SandboxClaim status until a sandbox name appears,
// then resolves the actual pod name via the Sandbox resource.
func (s *SandboxExecutor) waitForPod(ctx context.Context, claimName string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()

	for {
		claim, err := s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Get(ctx, claimName, metav1.GetOptions{})
		if err != nil {
			return "", err
		}

		status, ok := claim.Object["status"].(map[string]interface{})
		if ok {
			sandbox, _ := status["sandbox"].(map[string]interface{})
			if sandbox != nil {
				sandboxName, _ := sandbox["Name"].(string)
				if sandboxName != "" {
					return s.resolvePodName(ctx, sandboxName)
				}
			}
		}

		select {
		case <-ctx.Done():
			return "", fmt.Errorf("timed out waiting for sandbox allocation")
		case <-time.After(2 * time.Second):
		}
	}
}

// resolvePodName gets the actual pod name from the Sandbox resource.
// When a pod is adopted from the warm pool, the pod name is stored in the
// agents.x-k8s.io/pod-name annotation.
func (s *SandboxExecutor) resolvePodName(ctx context.Context, sandboxName string) (string, error) {
	sandbox, err := s.dynClient.Resource(sandboxGVR).Namespace(s.namespace).Get(ctx, sandboxName, metav1.GetOptions{})
	if err != nil {
		return "", fmt.Errorf("getting Sandbox %s: %w", sandboxName, err)
	}

	annotations := sandbox.GetAnnotations()
	if podName, ok := annotations["agents.x-k8s.io/pod-name"]; ok && podName != "" {
		return podName, nil
	}

	return sandboxName, nil
}

func (s *SandboxExecutor) waitPodRunning(ctx context.Context, podName string) error {
	s.logger.Info("waiting for pod to be ready", "pod", podName)

	ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()

	for {
		pod, err := s.clientset.CoreV1().Pods(s.namespace).Get(ctx, podName, metav1.GetOptions{})
		if err != nil {
			return err
		}

		switch pod.Status.Phase {
		case corev1.PodRunning:
			for _, cs := range pod.Status.ContainerStatuses {
				if cs.Name == "goose" && cs.Ready {
					s.logger.Info("pod is ready", "pod", podName)
					return nil
				}
			}
		case corev1.PodFailed:
			return fmt.Errorf("pod failed: %s", pod.Status.Message)
		}

		select {
		case <-ctx.Done():
			return fmt.Errorf("timed out waiting for pod to be ready")
		case <-time.After(2 * time.Second):
		}
	}
}

// refreshWorkspace execs a git pull in the sandbox pod to get latest code.
// Errors are logged but not propagated since the workspace may already be current.
func (s *SandboxExecutor) refreshWorkspace(ctx context.Context, podName string) {
	req := s.clientset.CoreV1().RESTClient().Post().
		Resource("pods").
		Name(podName).
		Namespace(s.namespace).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Container: "goose",
			Command:   []string{"git", "-C", "/workspace/homelab", "pull", "--ff-only", "origin", "main"},
			Stdout:    true,
			Stderr:    true,
		}, scheme.ParameterCodec)

	exec, err := remotecommand.NewSPDYExecutor(s.config, "POST", req.URL())
	if err != nil {
		s.logger.Warn("failed to create workspace refresh executor", "error", err)
		return
	}

	if err := exec.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdout: io.Discard,
		Stderr: io.Discard,
	}); err != nil {
		s.logger.Warn("workspace refresh failed", "error", err)
	}
}

// logWriter adapts slog.Logger to an io.Writer, emitting each written chunk as a debug log.
type logWriter struct {
	logger *slog.Logger
}

func (w *logWriter) Write(p []byte) (int, error) {
	w.logger.Debug("sandbox output", "data", string(p))
	return len(p), nil
}

// execGoose runs goose inside the sandbox pod and captures stdout+stderr.
func (s *SandboxExecutor) execGoose(ctx context.Context, podName, task string, outputBuf *syncBuffer) (int, error) {
	req := s.clientset.CoreV1().RESTClient().Post().
		Resource("pods").
		Name(podName).
		Namespace(s.namespace).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Container: "goose",
			Command:   []string{"goose", "run", "--text", task},
			Stdout:    true,
			Stderr:    true,
		}, scheme.ParameterCodec)

	executor, err := remotecommand.NewSPDYExecutor(s.config, "POST", req.URL())
	if err != nil {
		return -1, fmt.Errorf("creating executor: %w", err)
	}

	execCtx, execCancel := context.WithCancel(ctx)
	defer execCancel()

	watchdog := newActivityWatchdog(s.inactivityTimeout, func() {
		s.logger.Warn("agent silent, killing execution", "threshold", s.inactivityTimeout, "pod", podName)
		execCancel()
	})
	defer watchdog.Stop()

	lw := &logWriter{logger: s.logger}
	w := io.MultiWriter(outputBuf, lw, watchdog)

	err = executor.StreamWithContext(execCtx, remotecommand.StreamOptions{
		Stdout: w,
		Stderr: w,
	})
	if err != nil {
		if exitErr, ok := err.(executil.ExitError); ok {
			return exitErr.ExitStatus(), nil
		}
		return -1, err
	}

	return 0, nil
}
