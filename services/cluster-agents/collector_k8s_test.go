package main

import (
	"context"
	"testing"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestK8sCollector_FindsCrashLooping(t *testing.T) {
	client := fake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "bad-pod", Namespace: "default"},
		Status: corev1.PodStatus{
			Phase: corev1.PodRunning,
			ContainerStatuses: []corev1.ContainerStatus{{
				Name:         "app",
				RestartCount: 10,
				Ready:        false,
				State: corev1.ContainerState{
					Waiting: &corev1.ContainerStateWaiting{
						Reason: "CrashLoopBackOff",
					},
				},
			}},
		},
	})

	collector := NewK8sCollector(client)
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	found := false
	for _, f := range findings {
		if f.Source == "k8s:pod" && f.Title == "Container CrashLoopBackOff" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected CrashLoopBackOff finding, got %d findings: %+v", len(findings), findings)
	}
}

func TestK8sCollector_FindsNotReady(t *testing.T) {
	notReadyTime := metav1.NewTime(time.Now().Add(-10 * time.Minute))
	client := fake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "slow-pod", Namespace: "default"},
		Status: corev1.PodStatus{
			Phase: corev1.PodPending,
			Conditions: []corev1.PodCondition{{
				Type:               corev1.PodReady,
				Status:             corev1.ConditionFalse,
				LastTransitionTime: notReadyTime,
			}},
		},
	})

	collector := NewK8sCollector(client)
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}

	found := false
	for _, f := range findings {
		if f.Source == "k8s:pod" && f.Title == "Pod not ready" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected not-ready finding, got %d findings: %+v", len(findings), findings)
	}
}

func TestK8sCollector_HealthyPodsNoFindings(t *testing.T) {
	client := fake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "good-pod", Namespace: "default"},
		Status: corev1.PodStatus{
			Phase: corev1.PodRunning,
			ContainerStatuses: []corev1.ContainerStatus{{
				Name:         "app",
				RestartCount: 0,
				Ready:        true,
				State: corev1.ContainerState{
					Running: &corev1.ContainerStateRunning{},
				},
			}},
		},
	})

	collector := NewK8sCollector(client)
	findings, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 0 {
		t.Errorf("expected no findings for healthy pod, got %d: %+v", len(findings), findings)
	}
}
