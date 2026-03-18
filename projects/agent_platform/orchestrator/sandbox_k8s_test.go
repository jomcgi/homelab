package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	dynamicfake "k8s.io/client-go/dynamic/fake"
	kubefake "k8s.io/client-go/kubernetes/fake"
)

func readyGoosePod(name, namespace string, phase corev1.PodPhase) *corev1.Pod {
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: namespace},
		Status:     corev1.PodStatus{Phase: phase},
	}
	if phase == corev1.PodRunning {
		pod.Status.ContainerStatuses = []corev1.ContainerStatus{
			{Name: "goose", Ready: true},
		}
	}
	return pod
}

func sandboxUnstructured(name, namespace, podName string) *unstructured.Unstructured {
	obj := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "agents.x-k8s.io/v1alpha1",
			"kind":       "Sandbox",
			"metadata": map[string]interface{}{
				"name":      name,
				"namespace": namespace,
			},
		},
	}
	if podName != "" {
		obj.SetAnnotations(map[string]string{
			"agents.x-k8s.io/pod-name": podName,
		})
	}
	return obj
}

// sandboxWithFQDN creates a Sandbox unstructured object with an optional
// pod-name annotation and an optional serviceFQDN in status.
func sandboxWithFQDN(name, namespace, podName, fqdn string) *unstructured.Unstructured {
	obj := sandboxUnstructured(name, namespace, podName)
	if fqdn != "" {
		obj.Object["status"] = map[string]interface{}{
			"serviceFQDN": fqdn,
		}
	}
	return obj
}

// sandboxClaimUnstructured creates a SandboxClaim with an optional sandbox
// name pre-populated in status.sandbox.Name.
func sandboxClaimUnstructured(name, namespace, sandboxName string) *unstructured.Unstructured {
	obj := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
			"kind":       "SandboxClaim",
			"metadata": map[string]interface{}{
				"name":      name,
				"namespace": namespace,
			},
		},
	}
	if sandboxName != "" {
		obj.Object["status"] = map[string]interface{}{
			"sandbox": map[string]interface{}{
				"Name": sandboxName,
			},
		}
	}
	return obj
}

// newDynClient creates a fake dynamic client pre-registered for both
// SandboxClaim and Sandbox GVRs so all CRD operations work without extra setup.
func newDynClient(objects ...runtime.Object) *dynamicfake.FakeDynamicClient {
	dynScheme := runtime.NewScheme()
	return dynamicfake.NewSimpleDynamicClientWithCustomListKinds(dynScheme,
		map[schema.GroupVersionResource]string{
			sandboxClaimGVR: "SandboxClaimList",
			sandboxGVR:      "SandboxList",
		},
		objects...,
	)
}

// mockRoundTripper intercepts HTTP requests and routes them through a handler
// without requiring a real network listener. Used to test methods that
// construct their own base URLs (PollRunnerStatus, CheckRunnerForClaim, etc.)
// where the URL cannot be overridden by a test server address.
type mockRoundTripper struct {
	handler http.HandlerFunc
}

func (m *mockRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	w := httptest.NewRecorder()
	m.handler(w, req)
	return w.Result(), nil
}

// ---- waitPodRunning tests ----------------------------------------------------

func TestWaitPodRunning_NotFoundThenRunning(t *testing.T) {
	ns := "test-ns"
	podName := "goose-pool-abc123"
	sandboxName := "orch-test-1"

	// Start with no pods — the pod will be added after a short delay.
	cs := kubefake.NewClientset()
	dynScheme := runtime.NewScheme()
	dynClient := dynamicfake.NewSimpleDynamicClientWithCustomListKinds(dynScheme,
		map[schema.GroupVersionResource]string{
			sandboxGVR: "SandboxList",
		},
		sandboxUnstructured(sandboxName, ns, podName),
	)

	s := &SandboxExecutor{
		clientset: cs,
		dynClient: dynClient,
		namespace: ns,
		logger:    slog.Default(),
	}

	// Add the pod after 100ms to simulate the controller provisioning it.
	go func() {
		time.Sleep(100 * time.Millisecond)
		cs.Tracker().Add(readyGoosePod(podName, ns, corev1.PodRunning))
	}()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	err := s.waitPodRunning(ctx, sandboxName, podName)
	if err != nil {
		t.Fatalf("expected waitPodRunning to succeed after pod appears, got: %v", err)
	}
}

func TestWaitPodRunning_ReResolvePodName(t *testing.T) {
	ns := "test-ns"
	sandboxName := "orch-test-2"
	initialPodName := sandboxName // fallback: sandbox name used as pod name
	realPodName := "goose-pool-xyz789"

	// The real pod exists under a different name than the initial guess.
	cs := kubefake.NewClientset(readyGoosePod(realPodName, ns, corev1.PodRunning))

	// Sandbox already has the pod-name annotation — simulates the controller
	// having bound a pool pod. The initial pod name was the fallback (sandbox
	// name) because resolvePodName ran before the annotation was set. On
	// NotFound, waitPodRunning re-resolves and should pick up the real name.
	//
	// Use Tracker().Create() with an explicit GVR instead of passing objects
	// to the constructor — the constructor's Add() path uses
	// UnsafeGuessKindToResource which can mis-index unstructured CRDs.
	dynScheme := runtime.NewScheme()
	dynClient := dynamicfake.NewSimpleDynamicClientWithCustomListKinds(dynScheme,
		map[schema.GroupVersionResource]string{
			sandboxGVR: "SandboxList",
		},
	)
	if err := dynClient.Tracker().Create(sandboxGVR,
		sandboxUnstructured(sandboxName, ns, realPodName), ns); err != nil {
		t.Fatalf("setup: create sandbox in tracker: %v", err)
	}

	s := &SandboxExecutor{
		clientset: cs,
		dynClient: dynClient,
		namespace: ns,
		logger:    slog.Default(),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	err := s.waitPodRunning(ctx, sandboxName, initialPodName)
	if err != nil {
		t.Fatalf("expected waitPodRunning to re-resolve and succeed, got: %v", err)
	}
}

func TestWaitPodRunning_PodFailed(t *testing.T) {
	ns := "test-ns"
	podName := "goose-pool-fail"
	sandboxName := "orch-test-3"

	failedPod := readyGoosePod(podName, ns, corev1.PodFailed)
	failedPod.Status.Message = "OOMKilled"

	cs := kubefake.NewClientset(failedPod)
	dynScheme := runtime.NewScheme()
	dynClient := dynamicfake.NewSimpleDynamicClientWithCustomListKinds(dynScheme,
		map[schema.GroupVersionResource]string{
			sandboxGVR: "SandboxList",
		},
		sandboxUnstructured(sandboxName, ns, podName),
	)

	s := &SandboxExecutor{
		clientset: cs,
		dynClient: dynClient,
		namespace: ns,
		logger:    slog.Default(),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	err := s.waitPodRunning(ctx, sandboxName, podName)
	if err == nil {
		t.Fatal("expected error for failed pod, got nil")
	}
	if got := err.Error(); got != "pod failed: OOMKilled" {
		t.Errorf("error = %q, want %q", got, "pod failed: OOMKilled")
	}
}

func TestWaitPodRunning_ContextCancelled(t *testing.T) {
	ns := "test-ns"
	podName := "goose-pool-timeout"
	sandboxName := "orch-test-4"

	// Pod never appears — context cancels first.
	cs := kubefake.NewClientset()
	dynScheme := runtime.NewScheme()
	dynClient := dynamicfake.NewSimpleDynamicClientWithCustomListKinds(dynScheme,
		map[schema.GroupVersionResource]string{
			sandboxGVR: "SandboxList",
		},
		sandboxUnstructured(sandboxName, ns, ""),
	)

	s := &SandboxExecutor{
		clientset: cs,
		dynClient: dynClient,
		namespace: ns,
		logger:    slog.Default(),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	err := s.waitPodRunning(ctx, sandboxName, podName)
	if err == nil {
		t.Fatal("expected timeout error, got nil")
	}
}

// ---- createClaim tests -------------------------------------------------------

func TestCreateClaim_CreatesResource(t *testing.T) {
	ns := "test-ns"
	claimName := "test-claim-create"
	template := "default-sandbox"

	dynClient := newDynClient()
	s := &SandboxExecutor{
		dynClient: dynClient,
		namespace: ns,
		template:  template,
		logger:    slog.Default(),
	}

	ctx := context.Background()
	if err := s.createClaim(ctx, claimName); err != nil {
		t.Fatalf("createClaim: %v", err)
	}

	// Verify the resource was created.
	obj, err := dynClient.Resource(sandboxClaimGVR).Namespace(ns).Get(ctx, claimName, metav1.GetOptions{})
	if err != nil {
		t.Fatalf("get claim after create: %v", err)
	}
	if obj.GetName() != claimName {
		t.Errorf("name = %q, want %q", obj.GetName(), claimName)
	}

	// Verify spec.sandboxTemplateRef.name matches the executor's template.
	spec, _ := obj.Object["spec"].(map[string]interface{})
	templateRef, _ := spec["sandboxTemplateRef"].(map[string]interface{})
	if templateRef["name"] != template {
		t.Errorf("sandboxTemplateRef.name = %v, want %q", templateRef["name"], template)
	}

	// Verify lifecycle.shutdownPolicy is "Delete".
	lifecycle, _ := spec["lifecycle"].(map[string]interface{})
	if lifecycle["shutdownPolicy"] != "Delete" {
		t.Errorf("lifecycle.shutdownPolicy = %v, want Delete", lifecycle["shutdownPolicy"])
	}
}

func TestCreateClaim_SetsNamespace(t *testing.T) {
	ns := "goose-sandboxes"
	dynClient := newDynClient()
	s := &SandboxExecutor{
		dynClient: dynClient,
		namespace: ns,
		template:  "tmpl",
		logger:    slog.Default(),
	}

	ctx := context.Background()
	if err := s.createClaim(ctx, "ns-claim"); err != nil {
		t.Fatalf("createClaim: %v", err)
	}

	obj, err := dynClient.Resource(sandboxClaimGVR).Namespace(ns).Get(ctx, "ns-claim", metav1.GetOptions{})
	if err != nil {
		t.Fatalf("get claim: %v", err)
	}
	if obj.GetNamespace() != ns {
		t.Errorf("namespace = %q, want %q", obj.GetNamespace(), ns)
	}
}

// ---- deleteClaim tests -------------------------------------------------------

func TestDeleteClaim_RemovesResource(t *testing.T) {
	ns := "test-ns"
	claimName := "test-claim-delete"

	dynClient := newDynClient()
	s := &SandboxExecutor{
		dynClient: dynClient,
		namespace: ns,
		template:  "default-sandbox",
		logger:    slog.Default(),
	}

	ctx := context.Background()
	// Create the claim first.
	if err := s.createClaim(ctx, claimName); err != nil {
		t.Fatalf("createClaim: %v", err)
	}

	s.deleteClaim(claimName)

	// Verify the resource is gone.
	_, err := dynClient.Resource(sandboxClaimGVR).Namespace(ns).Get(ctx, claimName, metav1.GetOptions{})
	if err == nil {
		t.Fatal("expected error getting deleted claim, got nil")
	}
}

func TestDeleteClaim_NonExistentClaimIsHandledGracefully(t *testing.T) {
	ns := "test-ns"
	dynClient := newDynClient()
	s := &SandboxExecutor{
		dynClient: dynClient,
		namespace: ns,
		logger:    slog.Default(),
	}

	// Should not panic — deleteClaim only logs a warning on error.
	s.deleteClaim("nonexistent-claim")
}

// ---- waitForPodAndSandbox tests ----------------------------------------------

func TestWaitForPodAndSandbox_ImmediateResolution(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-immediate"
	sandboxName := "sandbox-immediate"
	podName := "pod-immediate"

	dynClient := newDynClient()
	if err := dynClient.Tracker().Create(sandboxClaimGVR, sandboxClaimUnstructured(claimName, ns, sandboxName), ns); err != nil {
		t.Fatalf("setup claim: %v", err)
	}
	if err := dynClient.Tracker().Create(sandboxGVR, sandboxUnstructured(sandboxName, ns, podName), ns); err != nil {
		t.Fatalf("setup sandbox: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	gotPod, gotSandbox, err := s.waitForPodAndSandbox(ctx, claimName)
	if err != nil {
		t.Fatalf("waitForPodAndSandbox: %v", err)
	}
	if gotPod != podName {
		t.Errorf("pod = %q, want %q", gotPod, podName)
	}
	if gotSandbox != sandboxName {
		t.Errorf("sandbox = %q, want %q", gotSandbox, sandboxName)
	}
}

func TestWaitForPodAndSandbox_SandboxNameAppearsAfterDelay(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-delayed"
	sandboxName := "sandbox-delayed"
	podName := "pod-delayed"

	dynClient := newDynClient()
	// Claim starts with no status — sandbox name will be set after a short delay.
	if err := dynClient.Tracker().Create(sandboxClaimGVR, sandboxClaimUnstructured(claimName, ns, ""), ns); err != nil {
		t.Fatalf("setup claim: %v", err)
	}
	if err := dynClient.Tracker().Create(sandboxGVR, sandboxUnstructured(sandboxName, ns, podName), ns); err != nil {
		t.Fatalf("setup sandbox: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	// Update the claim with sandbox name after 100ms to simulate the controller.
	go func() {
		time.Sleep(100 * time.Millisecond)
		updated := sandboxClaimUnstructured(claimName, ns, sandboxName)
		if err := dynClient.Tracker().Update(sandboxClaimGVR, updated, ns); err != nil {
			t.Errorf("goroutine: update claim: %v", err)
		}
	}()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	gotPod, gotSandbox, err := s.waitForPodAndSandbox(ctx, claimName)
	if err != nil {
		t.Fatalf("waitForPodAndSandbox: %v", err)
	}
	if gotPod != podName {
		t.Errorf("pod = %q, want %q", gotPod, podName)
	}
	if gotSandbox != sandboxName {
		t.Errorf("sandbox = %q, want %q", gotSandbox, sandboxName)
	}
}

func TestWaitForPodAndSandbox_Timeout(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-wait-timeout"

	dynClient := newDynClient()
	// Claim with no status — sandbox name never appears.
	if err := dynClient.Tracker().Create(sandboxClaimGVR, sandboxClaimUnstructured(claimName, ns, ""), ns); err != nil {
		t.Fatalf("setup claim: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	// Short outer timeout overrides the 2-minute internal timeout.
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()

	_, _, err := s.waitForPodAndSandbox(ctx, claimName)
	if err == nil {
		t.Fatal("expected timeout error, got nil")
	}
}

// ---- resolvePodName tests ----------------------------------------------------

func TestResolvePodName_WithAnnotation(t *testing.T) {
	ns := "test-ns"
	sandboxName := "sandbox-annotated"
	podName := "pool-pod-abc"

	dynClient := newDynClient()
	if err := dynClient.Tracker().Create(sandboxGVR, sandboxUnstructured(sandboxName, ns, podName), ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	got, err := s.resolvePodName(context.Background(), sandboxName)
	if err != nil {
		t.Fatalf("resolvePodName: %v", err)
	}
	if got != podName {
		t.Errorf("pod = %q, want %q", got, podName)
	}
}

func TestResolvePodName_WithoutAnnotation_FallsBackToSandboxName(t *testing.T) {
	ns := "test-ns"
	sandboxName := "sandbox-no-annotation"

	dynClient := newDynClient()
	// sandboxUnstructured with empty podName omits the annotation.
	if err := dynClient.Tracker().Create(sandboxGVR, sandboxUnstructured(sandboxName, ns, ""), ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	got, err := s.resolvePodName(context.Background(), sandboxName)
	if err != nil {
		t.Fatalf("resolvePodName: %v", err)
	}
	// Without the annotation the sandbox name is returned as the pod name.
	if got != sandboxName {
		t.Errorf("pod = %q, want sandbox name %q as fallback", got, sandboxName)
	}
}

func TestResolvePodName_SandboxNotFound(t *testing.T) {
	ns := "test-ns"
	dynClient := newDynClient()
	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, err := s.resolvePodName(context.Background(), "nonexistent-sandbox")
	if err == nil {
		t.Fatal("expected error for non-existent sandbox, got nil")
	}
}

// ---- resolveSandboxServiceFQDN tests ----------------------------------------

func TestResolveSandboxServiceFQDN_HappyPath(t *testing.T) {
	ns := "test-ns"
	sandboxName := "sandbox-with-fqdn"
	// nosemgrep: golang.no-hardcoded-k8s-service-url
	fqdn := "sandbox-abc.goose-sandboxes.svc.cluster.local"

	dynClient := newDynClient()
	if err := dynClient.Tracker().Create(sandboxGVR, sandboxWithFQDN(sandboxName, ns, "", fqdn), ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	got, err := s.resolveSandboxServiceFQDN(context.Background(), sandboxName)
	if err != nil {
		t.Fatalf("resolveSandboxServiceFQDN: %v", err)
	}
	if got != fqdn {
		t.Errorf("fqdn = %q, want %q", got, fqdn)
	}
}

func TestResolveSandboxServiceFQDN_NoStatus(t *testing.T) {
	ns := "test-ns"
	sandboxName := "sandbox-no-status"

	dynClient := newDynClient()
	// sandboxUnstructured does not set a status field.
	if err := dynClient.Tracker().Create(sandboxGVR, sandboxUnstructured(sandboxName, ns, ""), ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, err := s.resolveSandboxServiceFQDN(context.Background(), sandboxName)
	if err == nil {
		t.Fatal("expected error when sandbox has no status, got nil")
	}
}

func TestResolveSandboxServiceFQDN_EmptyFQDN(t *testing.T) {
	ns := "test-ns"
	sandboxName := "sandbox-empty-fqdn"

	dynClient := newDynClient()
	sandbox := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "agents.x-k8s.io/v1alpha1",
			"kind":       "Sandbox",
			"metadata":   map[string]interface{}{"name": sandboxName, "namespace": ns},
			"status":     map[string]interface{}{"serviceFQDN": ""},
		},
	}
	if err := dynClient.Tracker().Create(sandboxGVR, sandbox, ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, err := s.resolveSandboxServiceFQDN(context.Background(), sandboxName)
	if err == nil {
		t.Fatal("expected error when sandbox has empty serviceFQDN, got nil")
	}
}

func TestResolveSandboxServiceFQDN_SandboxNotFound(t *testing.T) {
	ns := "test-ns"
	dynClient := newDynClient()
	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, err := s.resolveSandboxServiceFQDN(context.Background(), "nonexistent-sandbox")
	if err == nil {
		t.Fatal("expected error for non-existent sandbox, got nil")
	}
}

// ---- pollUntilDone tests -----------------------------------------------------

// TestPollUntilDone_ContextCancelled verifies that a pre-cancelled context
// causes pollUntilDone to return immediately without waiting for the poll timer.
func TestPollUntilDone_ContextCancelled(t *testing.T) {
	s := newTestSandbox()

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel before entering the loop

	_, err := s.pollUntilDone(ctx, "http://localhost:9999", "claim-cancelled",
		func() bool { return false }, newSyncBuffer(0), nil)
	if err == nil {
		t.Fatal("expected error from cancelled context, got nil")
	}
}

// TestPollUntilDone_Done verifies that a "done" status from the runner produces
// an ExecResult with the correct fields.
// NOTE: pollUntilDone has a 5-second initial timer, so this test takes ~5s.
func TestPollUntilDone_Done(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/status":
			json.NewEncoder(w).Encode(map[string]any{
				"state":     "done",
				"exit_code": 0,
			})
		case "/output":
			w.Header().Set("X-Output-Offset", "11")
			w.WriteHeader(http.StatusOK)
			fmt.Fprint(w, "hello world")
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	s := newTestSandbox()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	result, err := s.pollUntilDone(ctx, srv.URL, "claim-done",
		func() bool { return false }, newSyncBuffer(0), nil)
	if err != nil {
		t.Fatalf("pollUntilDone: %v", err)
	}
	if result.ClaimName != "claim-done" {
		t.Errorf("ClaimName = %q, want claim-done", result.ClaimName)
	}
	if result.ExitCode != 0 {
		t.Errorf("ExitCode = %d, want 0", result.ExitCode)
	}
}

// TestPollUntilDone_Failed verifies that a "failed" status returns an ExecResult
// with the runner's non-zero exit code rather than a Go error.
// NOTE: pollUntilDone has a 5-second initial timer, so this test takes ~5s.
func TestPollUntilDone_Failed(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/status":
			json.NewEncoder(w).Encode(map[string]any{
				"state":     "failed",
				"exit_code": 1,
			})
		case "/output":
			w.Header().Set("X-Output-Offset", "0")
			w.WriteHeader(http.StatusOK)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	s := newTestSandbox()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	result, err := s.pollUntilDone(ctx, srv.URL, "claim-failed",
		func() bool { return false }, newSyncBuffer(0), nil)
	if err != nil {
		t.Fatalf("pollUntilDone: %v", err)
	}
	if result.ExitCode != 1 {
		t.Errorf("ExitCode = %d, want 1", result.ExitCode)
	}
}

// TestPollUntilDone_CancelFn verifies that returning true from cancelFn stops
// execution after the first poll tick with a "cancelled during execution" error.
// NOTE: pollUntilDone has a 5-second initial timer, so this test takes ~5s.
func TestPollUntilDone_CancelFn(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/status":
			json.NewEncoder(w).Encode(map[string]any{"state": "running"})
		case "/output":
			w.WriteHeader(http.StatusOK)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	s := newTestSandbox()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	_, err := s.pollUntilDone(ctx, srv.URL, "claim-cancel-fn",
		func() bool { return true }, newSyncBuffer(0), nil)
	if err == nil {
		t.Fatal("expected error from cancelFn, got nil")
	}
	const want = "cancelled during execution"
	if err.Error() != want {
		t.Errorf("error = %q, want %q", err.Error(), want)
	}
}

// ---- PollRunnerStatus tests --------------------------------------------------

func TestPollRunnerStatus_HappyPath(t *testing.T) {
	// nosemgrep: golang.no-hardcoded-k8s-service-url
	fqdn := "test-sandbox.ns.svc.cluster.local"

	var receivedURL string
	transport := &mockRoundTripper{
		handler: func(w http.ResponseWriter, r *http.Request) {
			receivedURL = r.URL.String()
			json.NewEncoder(w).Encode(map[string]any{
				"state":     "done",
				"exit_code": 0,
			})
		},
	}
	s := &SandboxExecutor{
		httpClient: &http.Client{Transport: transport},
		logger:     slog.Default(),
	}

	state, code, err := s.PollRunnerStatus(context.Background(), fqdn)
	if err != nil {
		t.Fatalf("PollRunnerStatus: %v", err)
	}
	if state != "done" {
		t.Errorf("state = %q, want done", state)
	}
	if code != 0 {
		t.Errorf("exitCode = %d, want 0", code)
	}
	// URL must be http://<fqdn>:8081/status — verifies the URL construction.
	wantURL := fmt.Sprintf("http://%s:8081/status", fqdn)
	if receivedURL != wantURL {
		t.Errorf("URL = %q, want %q", receivedURL, wantURL)
	}
}

func TestPollRunnerStatus_RunnerError(t *testing.T) {
	// nosemgrep: golang.no-hardcoded-k8s-service-url
	fqdn := "unreachable-sandbox.ns.svc.cluster.local"
	transport := &mockRoundTripper{
		handler: func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, "internal server error", http.StatusInternalServerError)
		},
	}
	s := &SandboxExecutor{
		httpClient: &http.Client{Transport: transport},
		logger:     slog.Default(),
	}

	_, _, err := s.PollRunnerStatus(context.Background(), fqdn)
	if err == nil {
		t.Fatal("expected error for 500 response, got nil")
	}
}

// ---- CheckRunnerForClaim tests -----------------------------------------------

func TestCheckRunnerForClaim_HappyPath(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-check-runner"
	sandboxName := "sandbox-check-runner"
	// nosemgrep: golang.no-hardcoded-k8s-service-url
	fqdn := "sandbox-check.ns.svc.cluster.local"

	dynClient := newDynClient()
	if err := dynClient.Tracker().Create(sandboxClaimGVR, sandboxClaimUnstructured(claimName, ns, sandboxName), ns); err != nil {
		t.Fatalf("setup claim: %v", err)
	}
	if err := dynClient.Tracker().Create(sandboxGVR, sandboxWithFQDN(sandboxName, ns, "", fqdn), ns); err != nil {
		t.Fatalf("setup sandbox: %v", err)
	}

	transport := &mockRoundTripper{
		handler: func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]any{"state": "running"})
		},
	}
	s := &SandboxExecutor{
		dynClient:  dynClient,
		namespace:  ns,
		httpClient: &http.Client{Transport: transport},
		logger:     slog.Default(),
	}

	state, _, err := s.CheckRunnerForClaim(context.Background(), claimName)
	if err != nil {
		t.Fatalf("CheckRunnerForClaim: %v", err)
	}
	if state != "running" {
		t.Errorf("state = %q, want running", state)
	}
}

func TestCheckRunnerForClaim_ClaimNotFound(t *testing.T) {
	ns := "test-ns"
	dynClient := newDynClient()
	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, _, err := s.CheckRunnerForClaim(context.Background(), "nonexistent-claim")
	if err == nil {
		t.Fatal("expected error for non-existent claim, got nil")
	}
}

func TestCheckRunnerForClaim_ClaimNoStatus(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-no-status"

	dynClient := newDynClient()
	// sandboxClaimUnstructured with empty sandboxName creates a claim with no status.
	if err := dynClient.Tracker().Create(sandboxClaimGVR, sandboxClaimUnstructured(claimName, ns, ""), ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, _, err := s.CheckRunnerForClaim(context.Background(), claimName)
	if err == nil {
		t.Fatal("expected error for claim with no status, got nil")
	}
}

func TestCheckRunnerForClaim_NoSandboxRef(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-no-sandbox-ref"

	dynClient := newDynClient()
	// Claim has a status map but no "sandbox" key.
	claim := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
			"kind":       "SandboxClaim",
			"metadata":   map[string]interface{}{"name": claimName, "namespace": ns},
			"status":     map[string]interface{}{},
		},
	}
	if err := dynClient.Tracker().Create(sandboxClaimGVR, claim, ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, _, err := s.CheckRunnerForClaim(context.Background(), claimName)
	if err == nil {
		t.Fatal("expected error for claim with no sandbox ref, got nil")
	}
}

func TestCheckRunnerForClaim_EmptySandboxName(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-empty-sandbox-name"

	dynClient := newDynClient()
	claim := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
			"kind":       "SandboxClaim",
			"metadata":   map[string]interface{}{"name": claimName, "namespace": ns},
			"status": map[string]interface{}{
				"sandbox": map[string]interface{}{"Name": ""},
			},
		},
	}
	if err := dynClient.Tracker().Create(sandboxClaimGVR, claim, ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, _, err := s.CheckRunnerForClaim(context.Background(), claimName)
	if err == nil {
		t.Fatal("expected error for empty sandbox name, got nil")
	}
}

// ---- FetchOutputForClaim tests -----------------------------------------------

func TestFetchOutputForClaim_HappyPath(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-fetch-output"
	sandboxName := "sandbox-fetch-output"
	// nosemgrep: golang.no-hardcoded-k8s-service-url
	fqdn := "sandbox-fetch.ns.svc.cluster.local"
	expectedOutput := "this is the task output"

	dynClient := newDynClient()
	if err := dynClient.Tracker().Create(sandboxClaimGVR, sandboxClaimUnstructured(claimName, ns, sandboxName), ns); err != nil {
		t.Fatalf("setup claim: %v", err)
	}
	if err := dynClient.Tracker().Create(sandboxGVR, sandboxWithFQDN(sandboxName, ns, "", fqdn), ns); err != nil {
		t.Fatalf("setup sandbox: %v", err)
	}

	transport := &mockRoundTripper{
		handler: func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/output" {
				http.NotFound(w, r)
				return
			}
			w.Header().Set("X-Output-Offset", fmt.Sprintf("%d", len(expectedOutput)))
			w.WriteHeader(http.StatusOK)
			fmt.Fprint(w, expectedOutput)
		},
	}
	s := &SandboxExecutor{
		dynClient:  dynClient,
		namespace:  ns,
		httpClient: &http.Client{Transport: transport},
		logger:     slog.Default(),
	}

	output, err := s.FetchOutputForClaim(context.Background(), claimName)
	if err != nil {
		t.Fatalf("FetchOutputForClaim: %v", err)
	}
	if output != expectedOutput {
		t.Errorf("output = %q, want %q", output, expectedOutput)
	}
}

func TestFetchOutputForClaim_ClaimNotFound(t *testing.T) {
	ns := "test-ns"
	dynClient := newDynClient()
	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, err := s.FetchOutputForClaim(context.Background(), "nonexistent-claim")
	if err == nil {
		t.Fatal("expected error for non-existent claim, got nil")
	}
}

func TestFetchOutputForClaim_ClaimNoStatus(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-fetch-no-status"

	dynClient := newDynClient()
	if err := dynClient.Tracker().Create(sandboxClaimGVR, sandboxClaimUnstructured(claimName, ns, ""), ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, err := s.FetchOutputForClaim(context.Background(), claimName)
	if err == nil {
		t.Fatal("expected error for claim with no status, got nil")
	}
}

func TestFetchOutputForClaim_NoSandboxRef(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-fetch-no-sandbox-ref"

	dynClient := newDynClient()
	claim := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
			"kind":       "SandboxClaim",
			"metadata":   map[string]interface{}{"name": claimName, "namespace": ns},
			"status":     map[string]interface{}{},
		},
	}
	if err := dynClient.Tracker().Create(sandboxClaimGVR, claim, ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, err := s.FetchOutputForClaim(context.Background(), claimName)
	if err == nil {
		t.Fatal("expected error for claim with no sandbox ref, got nil")
	}
}

func TestFetchOutputForClaim_EmptySandboxName(t *testing.T) {
	ns := "test-ns"
	claimName := "claim-fetch-empty-sandbox"

	dynClient := newDynClient()
	claim := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
			"kind":       "SandboxClaim",
			"metadata":   map[string]interface{}{"name": claimName, "namespace": ns},
			"status": map[string]interface{}{
				"sandbox": map[string]interface{}{"Name": ""},
			},
		},
	}
	if err := dynClient.Tracker().Create(sandboxClaimGVR, claim, ns); err != nil {
		t.Fatalf("setup: %v", err)
	}

	s := &SandboxExecutor{dynClient: dynClient, namespace: ns, logger: slog.Default()}

	_, err := s.FetchOutputForClaim(context.Background(), claimName)
	if err == nil {
		t.Fatal("expected error for empty sandbox name, got nil")
	}
}
