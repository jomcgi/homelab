package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

const (
	namespace = "ttyd-sessions"
)

type SessionManager struct {
	clientset *kubernetes.Clientset
}

type CreateSessionRequest struct {
	Name     string `json:"name" binding:"required"`
	ImageTag string `json:"image_tag,omitempty"` // Optional: defaults to "main"
}

type SessionResponse struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	PodName  string `json:"pod_name"`
	State    string `json:"state"`
	ImageTag string `json:"image_tag,omitempty"`
	Terminal string `json:"terminal_url,omitempty"`
}

func main() {
	// Create K8s client
	config, err := getKubeConfig()
	if err != nil {
		log.Fatalf("Failed to get kubeconfig: %v", err)
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		log.Fatalf("Failed to create K8s client: %v", err)
	}

	sm := &SessionManager{clientset: clientset}

	// Setup router
	r := gin.Default()

	// Enable CORS for local development
	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	})

	// API routes
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	r.POST("/api/sessions", sm.createSession)
	r.GET("/api/sessions", sm.listSessions)
	r.GET("/api/sessions/:id", sm.getSession)
	r.DELETE("/api/sessions/:id", sm.deleteSession)

	// Listen on 8081 internally, Envoy proxy listens on 8080 and forwards to us
	log.Println("Starting API server on :8081")
	if err := r.Run(":8081"); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}

func (sm *SessionManager) createSession(c *gin.Context) {
	var req CreateSessionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Default to "main" tag if not specified
	imageTag := req.ImageTag
	if imageTag == "" {
		imageTag = "main"
	}

	// Generate session ID
	sessionID := uuid.New().String()[:8]
	podName := fmt.Sprintf("ttyd-session-%s", sessionID)
	gitBranch := fmt.Sprintf("session-%s", sessionID)

	// Git remote URL (using homelab repo)
	gitRemoteURL := "https://github.com/jomcgi/homelab.git"

	// Read configuration from environment
	apiKeysSecretName := getEnvOrDefault("API_KEYS_SECRET_NAME", "ttyd-session-manager-api-keys")
	anthropicSecretKey := getEnvOrDefault("ANTHROPIC_SECRET_KEY", "anthropic_api_key")
	googleSecretKey := getEnvOrDefault("GOOGLE_SECRET_KEY", "google_api_key")
	buildbuddySecretKey := getEnvOrDefault("BUILDBUDDY_SECRET_KEY", "buildbuddy_api_key")
	otelEnabled := getEnvOrDefault("OTEL_ENABLED", "true") == "true"
	otelEndpoint := getEnvOrDefault("OTEL_ENDPOINT", "http://signoz-otel-collector.signoz.svc.cluster.local:4317")

	// Create pod with Git integration
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      podName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":        "ttyd-session",
				"session-id": sessionID,
			},
			Annotations: map[string]string{
				"session-name":   req.Name,
				"git-branch":     gitBranch,
				"git-remote-url": gitRemoteURL,
				"image-tag":      imageTag,
			},
		},
		Spec: corev1.PodSpec{
			ServiceAccountName: "ttyd-session-pods",
			ImagePullSecrets: []corev1.LocalObjectReference{
				{
					Name: "ttyd-session-manager-github-dockerconfig",
				},
			},
			SecurityContext: &corev1.PodSecurityContext{
				RunAsNonRoot: boolPtr(true),
				RunAsUser:    int64Ptr(1000),
				FSGroup:      int64Ptr(1000),
			},
			InitContainers: []corev1.Container{
				{
					Name:    "git-clone",
					Image:   "alpine/git:latest",
					Command: []string{"sh", "-c"},
					Args: []string{`
set -e
cd /workspace

# Build authenticated Git URL
GIT_REPO_WITH_AUTH="https://jomcgi:${GITHUB_TOKEN}@github.com/jomcgi/homelab.git"

# Clone the repo (shallow clone for speed)
git clone --depth 1 $GIT_REPO_WITH_AUTH session

cd session

# Configure git
git config user.name "TTYD Session Manager"
git config user.email "sessions@jomcgi.dev"

# Create and checkout new branch
git checkout -b ${GIT_BRANCH}

# Create session directory structure
mkdir -p .session .claude/artifacts work

# Create session metadata
cat > .session/metadata.json <<EOF
{
  "session_id": "${SESSION_ID}",
  "name": "${SESSION_NAME}",
  "git_branch": "${GIT_BRANCH}",
  "created_at": "$(date -Iseconds)"
}
EOF

# Create Claude context file
cat > .claude/context.json <<EOF
{
  "messages": [],
  "artifacts": []
}
EOF

# Create .gitignore
cat > .gitignore <<EOF
# Ignore temp files
*.tmp
.bash_history
EOF

# Initial commit
git add .
git commit -m "Initialize session: ${SESSION_NAME}"

# Push to remote
git push -u origin ${GIT_BRANCH}

echo "Session initialized and pushed to branch: ${GIT_BRANCH}"
`},
					WorkingDir: "/workspace",
					Env: []corev1.EnvVar{
						{
							Name: "GITHUB_TOKEN",
							ValueFrom: &corev1.EnvVarSource{
								SecretKeyRef: &corev1.SecretKeySelector{
									LocalObjectReference: corev1.LocalObjectReference{
										Name: "ttyd-session-manager-github",
									},
									Key: "github_token",
								},
							},
						},
						{
							Name:  "GIT_BRANCH",
							Value: gitBranch,
						},
						{
							Name:  "SESSION_ID",
							Value: sessionID,
						},
						{
							Name:  "SESSION_NAME",
							Value: req.Name,
						},
					},
					VolumeMounts: []corev1.VolumeMount{
						{
							Name:      "workspace",
							MountPath: "/workspace",
						},
					},
				},
			},
			Containers: []corev1.Container{
				// Envoy sidecar for distributed tracing
				{
					Name:  "envoy",
					Image: "envoyproxy/envoy:v1.31-latest",
					Args: []string{
						"-c",
						"/etc/envoy/envoy.yaml",
					},
					Ports: []corev1.ContainerPort{
						{
							Name:          "envoy-proxy",
							ContainerPort: 7681,
						},
						{
							Name:          "envoy-admin",
							ContainerPort: 9901,
						},
					},
					VolumeMounts: []corev1.VolumeMount{
						{
							Name:      "envoy-config",
							MountPath: "/etc/envoy",
							ReadOnly:  true,
						},
					},
					Resources: corev1.ResourceRequirements{
						Requests: corev1.ResourceList{
							corev1.ResourceCPU:    mustParseQuantity("50m"),
							corev1.ResourceMemory: mustParseQuantity("64Mi"),
						},
						Limits: corev1.ResourceList{
							corev1.ResourceCPU:    mustParseQuantity("200m"),
							corev1.ResourceMemory: mustParseQuantity("128Mi"),
						},
					},
					SecurityContext: &corev1.SecurityContext{
						ReadOnlyRootFilesystem:   boolPtr(true),
						AllowPrivilegeEscalation: boolPtr(false),
						RunAsNonRoot:             boolPtr(true),
						RunAsUser:                int64Ptr(65534),
						Capabilities: &corev1.Capabilities{
							Drop: []corev1.Capability{"ALL"},
						},
					},
				},
				{
					Name:  "ttyd",
					Image: fmt.Sprintf("ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker:%s", imageTag),
					Command: []string{
						"ttyd",
						"-p", "7682", // Envoy proxies 7681->7682
						"-W",
						"--writable",
						"-o", "disableLeaveAlert=true", // Disable leave page alert
						"-o", "rendererType=dom", // Use DOM renderer (may help with mouse events)
						"opencode",
					},
					WorkingDir: "/workspace/session",
					Env:        buildSessionEnv(sessionID, gitBranch, apiKeysSecretName, anthropicSecretKey, googleSecretKey, buildbuddySecretKey, otelEnabled, otelEndpoint),
					Ports: []corev1.ContainerPort{
						{
							Name:          "http",
							ContainerPort: 7682,
						},
					},
					VolumeMounts: []corev1.VolumeMount{
						{
							Name:      "workspace",
							MountPath: "/workspace",
						},
						{
							Name:      "home",
							MountPath: "/home/user",
						},
					},
					Resources: corev1.ResourceRequirements{
						Requests: corev1.ResourceList{
							corev1.ResourceCPU:    mustParseQuantity("100m"),
							corev1.ResourceMemory: mustParseQuantity("256Mi"),
						},
						Limits: corev1.ResourceList{
							corev1.ResourceCPU:    mustParseQuantity("500m"),
							corev1.ResourceMemory: mustParseQuantity("512Mi"),
						},
					},
					SecurityContext: &corev1.SecurityContext{
						AllowPrivilegeEscalation: boolPtr(false),
						ReadOnlyRootFilesystem:   boolPtr(false),
						Capabilities: &corev1.Capabilities{
							Drop: []corev1.Capability{"ALL"},
						},
					},
					Lifecycle: &corev1.Lifecycle{
						PreStop: &corev1.LifecycleHandler{
							Exec: &corev1.ExecAction{
								Command: []string{"sh", "-c", `
cd /workspace/session

# Add authenticated remote if not already set
git remote set-url origin https://jomcgi:${GITHUB_TOKEN}@github.com/jomcgi/homelab.git

# Commit changes
git add -A
git commit -m "Auto-commit on session suspend/delete at $(date -Iseconds)" || true

# Push to remote
git push origin ${GIT_BRANCH} || echo "Push failed, but continuing"

echo "Session state saved to Git"
`},
							},
						},
					},
				},
			},
			Volumes: []corev1.Volume{
				{
					Name: "workspace",
					VolumeSource: corev1.VolumeSource{
						EmptyDir: &corev1.EmptyDirVolumeSource{},
					},
				},
				{
					Name: "home",
					VolumeSource: corev1.VolumeSource{
						EmptyDir: &corev1.EmptyDirVolumeSource{},
					},
				},
				{
					Name: "envoy-config",
					VolumeSource: corev1.VolumeSource{
						ConfigMap: &corev1.ConfigMapVolumeSource{
							LocalObjectReference: corev1.LocalObjectReference{
								Name: "ttyd-session-manager-envoy-session",
							},
							Items: []corev1.KeyToPath{
								{
									Key:  "envoy.yaml",
									Path: "envoy.yaml",
								},
							},
						},
					},
				},
			},
			RestartPolicy: corev1.RestartPolicyNever,
		},
	}

	createdPod, err := sm.clientset.CoreV1().Pods(namespace).Create(
		context.Background(),
		pod,
		metav1.CreateOptions{},
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to create pod: %v", err)})
		return
	}

	c.JSON(http.StatusCreated, SessionResponse{
		ID:       sessionID,
		Name:     req.Name,
		PodName:  createdPod.Name,
		State:    "creating",
		ImageTag: imageTag,
	})
}

func (sm *SessionManager) listSessions(c *gin.Context) {
	pods, err := sm.clientset.CoreV1().Pods(namespace).List(
		context.Background(),
		metav1.ListOptions{
			LabelSelector: "app=ttyd-session",
		},
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to list pods: %v", err)})
		return
	}

	sessions := make([]SessionResponse, 0, len(pods.Items))
	for _, pod := range pods.Items {
		sessionID := pod.Labels["session-id"]
		state := "unknown"
		switch pod.Status.Phase {
		case corev1.PodPending:
			state = "pending"
		case corev1.PodRunning:
			state = "active"
		case corev1.PodSucceeded, corev1.PodFailed:
			state = "terminated"
		}

		imageTag := pod.Annotations["image-tag"]
		if imageTag == "" {
			imageTag = "main" // Default for older sessions without this annotation
		}

		sessions = append(sessions, SessionResponse{
			ID:       sessionID,
			Name:     pod.Name,
			PodName:  pod.Name,
			State:    state,
			ImageTag: imageTag,
		})
	}

	c.JSON(http.StatusOK, sessions)
}

func (sm *SessionManager) getSession(c *gin.Context) {
	sessionID := c.Param("id")
	podName := fmt.Sprintf("ttyd-session-%s", sessionID)

	pod, err := sm.clientset.CoreV1().Pods(namespace).Get(
		context.Background(),
		podName,
		metav1.GetOptions{},
	)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	state := "unknown"
	switch pod.Status.Phase {
	case corev1.PodPending:
		state = "pending"
	case corev1.PodRunning:
		state = "active"
	case corev1.PodSucceeded, corev1.PodFailed:
		state = "terminated"
	}

	imageTag := pod.Annotations["image-tag"]
	if imageTag == "" {
		imageTag = "main" // Default for older sessions without this annotation
	}

	c.JSON(http.StatusOK, SessionResponse{
		ID:       sessionID,
		Name:     pod.Name,
		PodName:  pod.Name,
		State:    state,
		ImageTag: imageTag,
	})
}

func (sm *SessionManager) deleteSession(c *gin.Context) {
	sessionID := c.Param("id")
	podName := fmt.Sprintf("ttyd-session-%s", sessionID)

	err := sm.clientset.CoreV1().Pods(namespace).Delete(
		context.Background(),
		podName,
		metav1.DeleteOptions{},
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to delete pod: %v", err)})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Session deleted"})
}

// Helper functions
func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func buildSessionEnv(sessionID, gitBranch, apiKeysSecretName, anthropicSecretKey, googleSecretKey, buildbuddySecretKey string, otelEnabled bool, otelEndpoint string) []corev1.EnvVar {
	env := []corev1.EnvVar{
		// Core session configuration
		{
			Name:  "HOME",
			Value: "/home/user",
		},
		{
			Name:  "SESSION_ID",
			Value: sessionID,
		},
		{
			Name:  "GIT_BRANCH",
			Value: gitBranch,
		},
		// GitHub token for git operations
		{
			Name: "GITHUB_TOKEN",
			ValueFrom: &corev1.EnvVarSource{
				SecretKeyRef: &corev1.SecretKeySelector{
					LocalObjectReference: corev1.LocalObjectReference{
						Name: "ttyd-session-manager-github",
					},
					Key: "github_token",
				},
			},
		},
		// Anthropic API authentication (for opencode-ai)
		{
			Name: "ANTHROPIC_API_KEY",
			ValueFrom: &corev1.EnvVarSource{
				SecretKeyRef: &corev1.SecretKeySelector{
					LocalObjectReference: corev1.LocalObjectReference{
						Name: apiKeysSecretName,
					},
					Key: anthropicSecretKey,
				},
			},
		},
		// Google API authentication (for AI services)
		{
			Name: "GOOGLE_API_KEY",
			ValueFrom: &corev1.EnvVarSource{
				SecretKeyRef: &corev1.SecretKeySelector{
					LocalObjectReference: corev1.LocalObjectReference{
						Name: apiKeysSecretName,
					},
					Key: googleSecretKey,
				},
			},
		},
		// BuildBuddy API key for remote cache/build execution
		{
			Name: "BUILDBUDDY_API_KEY",
			ValueFrom: &corev1.EnvVarSource{
				SecretKeyRef: &corev1.SecretKeySelector{
					LocalObjectReference: corev1.LocalObjectReference{
						Name: apiKeysSecretName,
					},
					Key: buildbuddySecretKey,
				},
			},
		},
	}

	// Add OpenTelemetry configuration if enabled
	if otelEnabled {
		otelEnv := []corev1.EnvVar{
			{
				Name:  "OTEL_EXPORTER_OTLP_ENDPOINT",
				Value: otelEndpoint,
			},
			{
				Name:  "OTEL_SERVICE_NAME",
				Value: fmt.Sprintf("opencode-session-%s", sessionID),
			},
			{
				Name:  "OTEL_TRACES_EXPORTER",
				Value: "otlp",
			},
			{
				Name:  "OTEL_METRICS_EXPORTER",
				Value: "otlp",
			},
			{
				Name:  "OTEL_LOGS_EXPORTER",
				Value: "otlp",
			},
			{
				Name:  "OTEL_RESOURCE_ATTRIBUTES",
				Value: fmt.Sprintf("deployment.environment=homelab,service.namespace=ttyd-sessions,session.id=%s", sessionID),
			},
		}
		env = append(env, otelEnv...)
	}

	// Add proxy configuration if set
	if httpProxy := os.Getenv("HTTP_PROXY"); httpProxy != "" {
		env = append(env, corev1.EnvVar{
			Name:  "HTTP_PROXY",
			Value: httpProxy,
		})
	}
	if httpsProxy := os.Getenv("HTTPS_PROXY"); httpsProxy != "" {
		env = append(env, corev1.EnvVar{
			Name:  "HTTPS_PROXY",
			Value: httpsProxy,
		})
	}
	if noProxy := os.Getenv("NO_PROXY"); noProxy != "" {
		env = append(env, corev1.EnvVar{
			Name:  "NO_PROXY",
			Value: noProxy,
		})
	}

	return env
}

func getKubeConfig() (*rest.Config, error) {
	// Try in-cluster config first
	config, err := rest.InClusterConfig()
	if err == nil {
		return config, nil
	}

	// Fall back to kubeconfig
	kubeconfig := filepath.Join(os.Getenv("HOME"), ".kube", "config")
	if env := os.Getenv("KUBECONFIG"); env != "" {
		kubeconfig = env
	}

	return clientcmd.BuildConfigFromFlags("", kubeconfig)
}

func boolPtr(b bool) *bool {
	return &b
}

func int64Ptr(i int64) *int64 {
	return &i
}

func mustParseQuantity(s string) resource.Quantity {
	q, err := resource.ParseQuantity(s)
	if err != nil {
		panic(err)
	}
	return q
}
