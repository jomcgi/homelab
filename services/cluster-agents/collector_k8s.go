package main

import (
	"context"
	"fmt"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

const (
	restartThreshold = 3
	notReadyTimeout  = 5 * time.Minute
)

// K8sCollector gathers pod and node health findings from the Kubernetes API.
type K8sCollector struct {
	client kubernetes.Interface
}

func NewK8sCollector(client kubernetes.Interface) *K8sCollector {
	return &K8sCollector{client: client}
}

func (c *K8sCollector) Collect(ctx context.Context) ([]Finding, error) {
	var findings []Finding

	podFindings, err := c.collectPods(ctx)
	if err != nil {
		return nil, fmt.Errorf("collect pods: %w", err)
	}
	findings = append(findings, podFindings...)

	nodeFindings, err := c.collectNodes(ctx)
	if err != nil {
		return nil, fmt.Errorf("collect nodes: %w", err)
	}
	findings = append(findings, nodeFindings...)

	return findings, nil
}

func (c *K8sCollector) collectPods(ctx context.Context) ([]Finding, error) {
	pods, err := c.client.CoreV1().Pods("").List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, err
	}

	var findings []Finding
	now := time.Now()

	for _, pod := range pods.Items {
		for _, cs := range pod.Status.ContainerStatuses {
			if cs.State.Waiting != nil && cs.State.Waiting.Reason == "CrashLoopBackOff" {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:pod:%s/%s:CrashLoopBackOff", pod.Namespace, pod.Name),
					Source:      "k8s:pod",
					Severity:    SeverityCritical,
					Title:       "Container CrashLoopBackOff",
					Detail:      fmt.Sprintf("%s/%s container %s is crash-looping (restarts: %d)", pod.Namespace, pod.Name, cs.Name, cs.RestartCount),
					Data: map[string]any{
						"namespace":    pod.Namespace,
						"pod":          pod.Name,
						"container":    cs.Name,
						"restartCount": cs.RestartCount,
					},
					Timestamp: now,
				})
			} else if cs.RestartCount >= restartThreshold && !cs.Ready {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:pod:%s/%s:HighRestarts", pod.Namespace, pod.Name),
					Source:      "k8s:pod",
					Severity:    SeverityWarning,
					Title:       "Container restarting frequently",
					Detail:      fmt.Sprintf("%s/%s container %s has restarted %d times", pod.Namespace, pod.Name, cs.Name, cs.RestartCount),
					Data: map[string]any{
						"namespace":    pod.Namespace,
						"pod":          pod.Name,
						"container":    cs.Name,
						"restartCount": cs.RestartCount,
					},
					Timestamp: now,
				})
			}

			if cs.LastTerminationState.Terminated != nil && cs.LastTerminationState.Terminated.Reason == "OOMKilled" {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:pod:%s/%s:OOMKilled", pod.Namespace, pod.Name),
					Source:      "k8s:pod",
					Severity:    SeverityWarning,
					Title:       "Container OOMKilled",
					Detail:      fmt.Sprintf("%s/%s container %s was OOMKilled", pod.Namespace, pod.Name, cs.Name),
					Data: map[string]any{
						"namespace": pod.Namespace,
						"pod":       pod.Name,
						"container": cs.Name,
					},
					Timestamp: now,
				})
			}
		}

		for _, cond := range pod.Status.Conditions {
			if cond.Type == corev1.PodReady && cond.Status == corev1.ConditionFalse {
				if now.Sub(cond.LastTransitionTime.Time) > notReadyTimeout {
					findings = append(findings, Finding{
						Fingerprint: fmt.Sprintf("patrol:pod:%s/%s:NotReady", pod.Namespace, pod.Name),
						Source:      "k8s:pod",
						Severity:    SeverityWarning,
						Title:       "Pod not ready",
						Detail:      fmt.Sprintf("%s/%s has been not-ready for %s", pod.Namespace, pod.Name, now.Sub(cond.LastTransitionTime.Time).Round(time.Minute)),
						Data: map[string]any{
							"namespace": pod.Namespace,
							"pod":       pod.Name,
							"phase":     string(pod.Status.Phase),
						},
						Timestamp: now,
					})
				}
			}
		}
	}

	return findings, nil
}

func (c *K8sCollector) collectNodes(ctx context.Context) ([]Finding, error) {
	nodes, err := c.client.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, err
	}

	var findings []Finding
	now := time.Now()

	pressureConditions := map[corev1.NodeConditionType]bool{
		corev1.NodeMemoryPressure: true,
		corev1.NodeDiskPressure:   true,
		corev1.NodePIDPressure:    true,
	}

	for _, node := range nodes.Items {
		for _, cond := range node.Status.Conditions {
			if cond.Type == corev1.NodeReady && cond.Status != corev1.ConditionTrue {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:node:%s:NotReady", node.Name),
					Source:      "k8s:node",
					Severity:    SeverityCritical,
					Title:       "Node not ready",
					Detail:      fmt.Sprintf("Node %s is not ready: %s", node.Name, cond.Message),
					Data:        map[string]any{"node": node.Name, "reason": cond.Reason},
					Timestamp:   now,
				})
			}

			if pressureConditions[cond.Type] && cond.Status == corev1.ConditionTrue {
				findings = append(findings, Finding{
					Fingerprint: fmt.Sprintf("patrol:node:%s:%s", node.Name, cond.Type),
					Source:      "k8s:node",
					Severity:    SeverityWarning,
					Title:       fmt.Sprintf("Node %s", cond.Type),
					Detail:      fmt.Sprintf("Node %s has %s: %s", node.Name, cond.Type, cond.Message),
					Data:        map[string]any{"node": node.Name, "condition": string(cond.Type)},
					Timestamp:   now,
				})
			}
		}
	}

	return findings, nil
}
