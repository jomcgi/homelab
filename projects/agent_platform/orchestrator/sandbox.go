package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
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
	httpClient        *http.Client
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
		httpClient:        &http.Client{Timeout: 30 * time.Second},
	}, nil
}

// Run creates a SandboxClaim, waits for the pod, dispatches the task via HTTP,
// and polls for completion. The cancelFn is checked before each phase to
// support cooperative cancellation.
func (s *SandboxExecutor) Run(ctx context.Context, claimName, task, profile string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error) {
	s.logger.Info("creating sandbox claim", "claim", claimName, "namespace", s.namespace)
	if err := s.createClaim(ctx, claimName); err != nil {
		return nil, fmt.Errorf("creating claim: %w", err)
	}
	defer s.deleteClaim(claimName)

	if cancelFn() {
		return nil, fmt.Errorf("cancelled before pod allocation")
	}

	podName, sandboxName, err := s.waitForPodAndSandbox(ctx, claimName)
	if err != nil {
		return nil, fmt.Errorf("waiting for pod: %w", err)
	}
	s.logger.Info("sandbox pod allocated", "pod", podName, "sandbox", sandboxName)

	if cancelFn() {
		return nil, fmt.Errorf("cancelled before pod ready")
	}

	if err := s.waitPodRunning(ctx, podName); err != nil {
		return nil, fmt.Errorf("waiting for pod running: %w", err)
	}

	if cancelFn() {
		return nil, fmt.Errorf("cancelled before dispatch")
	}

	fqdn, err := s.resolveSandboxServiceFQDN(ctx, sandboxName)
	if err != nil {
		return nil, fmt.Errorf("resolving service FQDN: %w", err)
	}
	baseURL := fmt.Sprintf("http://%s:8081", fqdn)
	s.logger.Info("resolved runner URL", "url", baseURL)

	if err := s.dispatchTask(ctx, baseURL, task, profile); err != nil {
		return nil, fmt.Errorf("dispatching task: %w", err)
	}

	return s.pollUntilDone(ctx, baseURL, claimName, cancelFn, outputBuf)
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
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	err := s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Delete(
		ctx, claimName, metav1.DeleteOptions{})
	if err != nil {
		s.logger.Warn("failed to delete sandbox claim", "claim", claimName, "error", err)
	}
}

// waitForPodAndSandbox polls the SandboxClaim status until a sandbox name appears,
// then resolves the actual pod name via the Sandbox resource.
func (s *SandboxExecutor) waitForPodAndSandbox(ctx context.Context, claimName string) (podName, sandboxName string, err error) {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()
	for {
		claim, err := s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Get(ctx, claimName, metav1.GetOptions{})
		if err != nil {
			return "", "", err
		}
		status, ok := claim.Object["status"].(map[string]interface{})
		if ok {
			sandbox, _ := status["sandbox"].(map[string]interface{})
			if sandbox != nil {
				name, _ := sandbox["Name"].(string)
				if name != "" {
					pod, err := s.resolvePodName(ctx, name)
					if err != nil {
						return "", "", err
					}
					return pod, name, nil
				}
			}
		}
		select {
		case <-ctx.Done():
			return "", "", fmt.Errorf("timed out waiting for sandbox allocation")
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

// resolveSandboxServiceFQDN gets the stable Service FQDN from the Sandbox resource.
// The Sandbox controller creates a headless Service per sandbox that survives
// pod restarts, providing a stable DNS name for HTTP communication.
func (s *SandboxExecutor) resolveSandboxServiceFQDN(ctx context.Context, sandboxName string) (string, error) {
	sandbox, err := s.dynClient.Resource(sandboxGVR).Namespace(s.namespace).Get(ctx, sandboxName, metav1.GetOptions{})
	if err != nil {
		return "", fmt.Errorf("getting Sandbox %s: %w", sandboxName, err)
	}

	status, ok := sandbox.Object["status"].(map[string]interface{})
	if !ok {
		return "", fmt.Errorf("sandbox %s has no status", sandboxName)
	}

	fqdn, ok := status["serviceFQDN"].(string)
	if !ok || fqdn == "" {
		return "", fmt.Errorf("sandbox %s has no serviceFQDN in status", sandboxName)
	}

	return fqdn, nil
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

func (s *SandboxExecutor) dispatchTask(ctx context.Context, baseURL, task, profile string) error {
	payload := struct {
		Task              string `json:"task"`
		Profile           string `json:"profile,omitempty"`
		InactivityTimeout int    `json:"inactivity_timeout,omitempty"`
	}{
		Task:              task,
		Profile:           profile,
		InactivityTimeout: int(s.inactivityTimeout.Seconds()),
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshaling request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, "POST", baseURL+"/run", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("POST /run: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("POST /run returned %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

func (s *SandboxExecutor) pollUntilDone(ctx context.Context, baseURL, claimName string, cancelFn func() bool, outputBuf *syncBuffer) (*ExecResult, error) {
	offset := 0
	// Short initial wait, then poll every 30 seconds.
	timer := time.NewTimer(5 * time.Second)
	defer timer.Stop()
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-timer.C:
		case <-ticker.C:
		}
		if cancelFn() {
			return nil, fmt.Errorf("cancelled during execution")
		}
		// Poll output
		newOffset, err := s.pollOutput(ctx, baseURL, offset, outputBuf)
		if err != nil {
			s.logger.Warn("poll output error", "error", err)
		} else {
			offset = newOffset
		}
		// Check status
		state, exitCode, err := s.pollStatus(ctx, baseURL)
		if err != nil {
			s.logger.Warn("poll status error", "error", err)
			continue
		}
		if state == "done" || state == "failed" {
			// Final output drain
			if o, err := s.pollOutput(ctx, baseURL, offset, outputBuf); err == nil {
				offset = o
			}
			return &ExecResult{
				ClaimName: claimName,
				ExitCode:  exitCode,
				Output:    outputBuf.String(),
			}, nil
		}
	}
}

func (s *SandboxExecutor) pollOutput(ctx context.Context, baseURL string, offset int, outputBuf *syncBuffer) (int, error) {
	url := fmt.Sprintf("%s/output?offset=%d", baseURL, offset)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return offset, err
	}
	resp, err := s.httpClient.Do(req)
	if err != nil {
		return offset, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return offset, err
	}
	if resp.StatusCode != http.StatusOK {
		return offset, fmt.Errorf("GET /output returned %d: %s", resp.StatusCode, string(body))
	}
	if len(body) > 0 {
		outputBuf.Write(body)
	}
	newOffset := offset
	if hdr := resp.Header.Get("X-Output-Offset"); hdr != "" {
		if v, err := strconv.Atoi(hdr); err == nil {
			newOffset = v
		}
	}
	return newOffset, nil
}

// pollStatus checks the runner's current state. Used by both the Run loop
// and reconciliation (via PollRunnerStatus).
func (s *SandboxExecutor) pollStatus(ctx context.Context, baseURL string) (state string, exitCode int, err error) {
	req, err := http.NewRequestWithContext(ctx, "GET", baseURL+"/status", nil)
	if err != nil {
		return "", -1, err
	}
	resp, err := s.httpClient.Do(req)
	if err != nil {
		return "", -1, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", -1, fmt.Errorf("GET /status returned %d: %s", resp.StatusCode, string(body))
	}
	var status struct {
		State    string `json:"state"`
		ExitCode *int   `json:"exit_code"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&status); err != nil {
		return "", -1, err
	}
	exitCode = -1
	if status.ExitCode != nil {
		exitCode = *status.ExitCode
	}
	return status.State, exitCode, nil
}

// PollRunnerStatus checks a runner's HTTP status at the given service FQDN.
// Used by reconciliation to determine if a running job's goose is still alive.
func (s *SandboxExecutor) PollRunnerStatus(ctx context.Context, serviceFQDN string) (state string, exitCode int, err error) {
	baseURL := fmt.Sprintf("http://%s:8081", serviceFQDN)
	return s.pollStatus(ctx, baseURL)
}

// CheckRunnerForClaim resolves the runner status for a sandbox claim by walking
// the chain: claim → sandbox name → service FQDN → HTTP status check.
// Returns a RunnerStatusFunc-compatible signature.
func (s *SandboxExecutor) CheckRunnerForClaim(ctx context.Context, claimName string) (state string, exitCode int, err error) {
	// Get the sandbox name from the claim's status.
	claim, err := s.dynClient.Resource(sandboxClaimGVR).Namespace(s.namespace).Get(ctx, claimName, metav1.GetOptions{})
	if err != nil {
		return "", -1, fmt.Errorf("getting claim %s: %w", claimName, err)
	}
	status, ok := claim.Object["status"].(map[string]interface{})
	if !ok {
		return "", -1, fmt.Errorf("claim %s has no status", claimName)
	}
	sandboxMap, _ := status["sandbox"].(map[string]interface{})
	if sandboxMap == nil {
		return "", -1, fmt.Errorf("claim %s has no sandbox ref", claimName)
	}
	sandboxName, _ := sandboxMap["Name"].(string)
	if sandboxName == "" {
		return "", -1, fmt.Errorf("claim %s has empty sandbox name", claimName)
	}

	// Get the service FQDN from the sandbox.
	fqdn, err := s.resolveSandboxServiceFQDN(ctx, sandboxName)
	if err != nil {
		return "", -1, fmt.Errorf("resolving FQDN for sandbox %s: %w", sandboxName, err)
	}

	return s.PollRunnerStatus(ctx, fqdn)
}
