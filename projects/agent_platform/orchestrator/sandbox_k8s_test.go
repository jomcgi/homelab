package main

import (
	"context"
	"log/slog"
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

	// The real pod exists, but under a different name than the initial guess.
	cs := kubefake.NewClientset(readyGoosePod(realPodName, ns, corev1.PodRunning))

	// Sandbox starts without the pod-name annotation — simulate late binding.
	sandbox := sandboxUnstructured(sandboxName, ns, "")
	dynScheme := runtime.NewScheme()
	dynClient := dynamicfake.NewSimpleDynamicClientWithCustomListKinds(dynScheme,
		map[schema.GroupVersionResource]string{
			sandboxGVR: "SandboxList",
		},
		sandbox,
	)

	s := &SandboxExecutor{
		clientset: cs,
		dynClient: dynClient,
		namespace: ns,
		logger:    slog.Default(),
	}

	// After 100ms, update the sandbox annotation to point to the real pod.
	go func() {
		time.Sleep(100 * time.Millisecond)
		updated := sandboxUnstructured(sandboxName, ns, realPodName)
		dynClient.Resource(sandboxGVR).Namespace(ns).Update(
			context.Background(), updated, metav1.UpdateOptions{},
		)
	}()

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
