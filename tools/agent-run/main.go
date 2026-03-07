// Package main provides the agent-run CLI for triggering Goose agent tasks
// by creating SandboxClaim resources and streaming pod logs.
package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"

	"github.com/spf13/cobra"
)

const (
	namespace    = "goose-sandboxes"
	warmPoolName = "goose-pool"
)

var sandboxClaimGVR = schema.GroupVersionResource{
	Group:    "extensions.agents.x-k8s.io",
	Version:  "v1alpha1",
	Resource: "sandboxclaims",
}

var sandboxGVR = schema.GroupVersionResource{
	Group:    "extensions.agents.x-k8s.io",
	Version:  "v1alpha1",
	Resource: "sandboxes",
}

var issueFlag int

var rootCmd = &cobra.Command{
	Use:   "agent-run [task description]",
	Short: "Trigger a Goose agent task in a sandbox pod",
	Long: `agent-run creates a SandboxClaim referencing the goose-pool WarmPool,
injects the task as the AGENT_TASK environment variable, watches the
Sandbox until the pod reaches Running, streams pod logs until Goose
exits, and reports the exit code.`,
	Args:         cobra.MinimumNArgs(0),
	SilenceUsage: true,
	RunE:         run,
}

func init() {
	rootCmd.Flags().IntVar(&issueFlag, "issue", 0, "GitHub issue number to use as task description")
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	task, err := resolveTask(args)
	if err != nil {
		return err
	}

	config, err := clientcmd.NewNonInteractiveDeferredLoadingClientConfig(
		clientcmd.NewDefaultClientConfigLoadingRules(), nil).ClientConfig()
	if err != nil {
		return fmt.Errorf("loading kubeconfig: %w", err)
	}

	dynClient, err := dynamic.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("creating dynamic client: %w", err)
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return fmt.Errorf("creating clientset: %w", err)
	}

	claimName := fmt.Sprintf("agent-run-%d", time.Now().Unix())
	fmt.Printf("Creating SandboxClaim %s/%s\n", namespace, claimName)

	claim := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
			"kind":       "SandboxClaim",
			"metadata": map[string]interface{}{
				"name":      claimName,
				"namespace": namespace,
			},
			"spec": map[string]interface{}{
				"warmPoolRef": map[string]interface{}{
					"name": warmPoolName,
				},
				"envOverrides": []interface{}{
					map[string]interface{}{
						"name":  "AGENT_TASK",
						"value": task,
					},
				},
			},
		},
	}

	created, err := dynClient.Resource(sandboxClaimGVR).Namespace(namespace).Create(ctx, claim, metav1.CreateOptions{})
	if err != nil {
		return fmt.Errorf("creating SandboxClaim: %w", err)
	}
	fmt.Printf("SandboxClaim created: %s\n", created.GetName())

	// Clean up claim on exit.
	defer func() {
		fmt.Printf("\nCleaning up SandboxClaim %s\n", claimName)
		_ = dynClient.Resource(sandboxClaimGVR).Namespace(namespace).Delete(
			context.Background(), claimName, metav1.DeleteOptions{})
	}()

	// Wait for associated Sandbox to be created and get pod name.
	podName, err := waitForPod(ctx, dynClient, claimName)
	if err != nil {
		return fmt.Errorf("waiting for pod: %w", err)
	}
	fmt.Printf("Sandbox pod: %s\n", podName)

	// Wait for pod to be running.
	if err := waitPodRunning(ctx, clientset, podName); err != nil {
		return fmt.Errorf("waiting for pod running: %w", err)
	}

	// Stream logs until completion.
	exitCode, err := streamLogs(ctx, clientset, podName)
	if err != nil {
		return fmt.Errorf("streaming logs: %w", err)
	}

	fmt.Printf("\nGoose exited with code %d\n", exitCode)
	if exitCode != 0 {
		return fmt.Errorf("agent exited with non-zero code: %d", exitCode)
	}
	return nil
}

func resolveTask(args []string) (string, error) {
	if issueFlag > 0 {
		return fmt.Sprintf("Fix GitHub issue #%d in the homelab repo. Read the issue first with gh, then implement the fix and create a PR.", issueFlag), nil
	}
	if len(args) == 0 {
		return "", fmt.Errorf("provide a task description or --issue flag")
	}
	return strings.Join(args, " "), nil
}

// waitForPod watches SandboxClaims until one is bound and returns the pod name.
func waitForPod(ctx context.Context, client dynamic.Interface, claimName string) (string, error) {
	timeout := 2 * time.Minute
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	for {
		claim, err := client.Resource(sandboxClaimGVR).Namespace(namespace).Get(ctx, claimName, metav1.GetOptions{})
		if err != nil {
			return "", err
		}

		status, ok := claim.Object["status"].(map[string]interface{})
		if ok {
			sandboxName, _ := status["sandboxName"].(string)
			if sandboxName != "" {
				// Get the sandbox to find the pod name.
				sandbox, err := client.Resource(sandboxGVR).Namespace(namespace).Get(ctx, sandboxName, metav1.GetOptions{})
				if err != nil {
					return "", fmt.Errorf("getting sandbox %s: %w", sandboxName, err)
				}
				sStatus, _ := sandbox.Object["status"].(map[string]interface{})
				if sStatus != nil {
					podName, _ := sStatus["podName"].(string)
					if podName != "" {
						return podName, nil
					}
				}
				// Pod name not yet set, use sandbox name as pod name (common pattern).
				return sandboxName, nil
			}
		}

		select {
		case <-ctx.Done():
			return "", fmt.Errorf("timed out waiting for sandbox allocation")
		case <-time.After(2 * time.Second):
		}
	}
}

func waitPodRunning(ctx context.Context, clientset kubernetes.Interface, podName string) error {
	w, err := clientset.CoreV1().Pods(namespace).Watch(ctx, metav1.ListOptions{
		FieldSelector: "metadata.name=" + podName,
	})
	if err != nil {
		return err
	}
	defer w.Stop()

	fmt.Printf("Waiting for pod %s to be running...\n", podName)
	for event := range w.ResultChan() {
		if event.Type == watch.Error {
			return fmt.Errorf("watch error")
		}
		pod, ok := event.Object.(*corev1.Pod)
		if !ok {
			continue
		}
		switch pod.Status.Phase {
		case corev1.PodRunning:
			fmt.Println("Pod is running")
			return nil
		case corev1.PodSucceeded:
			fmt.Println("Pod completed")
			return nil
		case corev1.PodFailed:
			return fmt.Errorf("pod failed: %s", pod.Status.Message)
		}
	}
	return fmt.Errorf("watch closed")
}

func streamLogs(ctx context.Context, clientset kubernetes.Interface, podName string) (int, error) {
	req := clientset.CoreV1().Pods(namespace).GetLogs(podName, &corev1.PodLogOptions{
		Container: "goose",
		Follow:    true,
	})

	stream, err := req.Stream(ctx)
	if err != nil {
		return -1, fmt.Errorf("opening log stream: %w", err)
	}
	defer stream.Close()

	scanner := bufio.NewScanner(stream)
	for scanner.Scan() {
		fmt.Println(scanner.Text())
	}

	// Check final pod status for exit code.
	pod, err := clientset.CoreV1().Pods(namespace).Get(context.Background(), podName, metav1.GetOptions{})
	if err != nil {
		return -1, fmt.Errorf("getting final pod status: %w", err)
	}

	for _, cs := range pod.Status.ContainerStatuses {
		if cs.Name == "goose" && cs.State.Terminated != nil {
			return int(cs.State.Terminated.ExitCode), nil
		}
	}

	return 0, nil
}
