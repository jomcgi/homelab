package main

import (
	"fmt"
	"os"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// PodConfig holds configuration for building session pods
type PodConfig struct {
	// Session metadata
	SessionID   string
	DisplayName string
	ImageTag    string
	GitBranch   string

	// Configuration from environment
	APIKeysSecretName   string
	AnthropicSecretKey  string
	GoogleSecretKey     string
	BuildBuddySecretKey string
	OTelEnabled         bool
	OTelEndpoint        string

	// Proxy configuration (optional)
	HTTPProxy  string
	HTTPSProxy string
	NoProxy    string
}

// NewPodConfig creates a PodConfig with defaults from environment
func NewPodConfig(sessionID, displayName, imageTag, gitBranch string) *PodConfig {
	if imageTag == "" {
		// Use default worker image tag from environment (set via Helm values)
		// This allows ArgoCD Image Updater to control the default image version
		imageTag = getEnvOrDefault("DEFAULT_WORKER_IMAGE_TAG", "main")
	}
	if gitBranch == "" {
		gitBranch = fmt.Sprintf("session-%s", sessionID)
	}

	return &PodConfig{
		SessionID:           sessionID,
		DisplayName:         displayName,
		ImageTag:            imageTag,
		GitBranch:           gitBranch,
		APIKeysSecretName:   getEnvOrDefault("API_KEYS_SECRET_NAME", "ttyd-session-manager-api-keys"),
		AnthropicSecretKey:  getEnvOrDefault("ANTHROPIC_SECRET_KEY", "anthropic_api_key"),
		GoogleSecretKey:     getEnvOrDefault("GOOGLE_SECRET_KEY", "google_api_key"),
		BuildBuddySecretKey: getEnvOrDefault("BUILDBUDDY_SECRET_KEY", "buildbuddy_api_key"),
		OTelEnabled:         getEnvOrDefault("OTEL_ENABLED", "true") == "true",
		OTelEndpoint:        getEnvOrDefault("OTEL_ENDPOINT", "http://signoz-otel-collector.signoz.svc.cluster.local:4317"),
		HTTPProxy:           os.Getenv("HTTP_PROXY"),
		HTTPSProxy:          os.Getenv("HTTPS_PROXY"),
		NoProxy:             os.Getenv("NO_PROXY"),
	}
}

// BuildSessionPod creates a Pod spec for a ttyd session
func BuildSessionPod(config *PodConfig) *corev1.Pod {
	podName := fmt.Sprintf("ttyd-session-%s", config.SessionID)
	gitRemoteURL := "https://github.com/jomcgi/homelab.git"

	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      podName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":        "ttyd-session",
				"session-id": config.SessionID,
			},
			Annotations: map[string]string{
				"session-name":   config.DisplayName,
				"git-branch":     config.GitBranch,
				"git-remote-url": gitRemoteURL,
				"image-tag":      config.ImageTag,
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
				buildGitCloneInitContainer(config),
			},
			Containers: []corev1.Container{
				buildEnvoyContainer(),
				buildTTYDContainer(config),
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

	return pod
}

func buildGitCloneInitContainer(config *PodConfig) corev1.Container {
	return corev1.Container{
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
				Value: config.GitBranch,
			},
			{
				Name:  "SESSION_ID",
				Value: config.SessionID,
			},
			{
				Name:  "SESSION_NAME",
				Value: config.DisplayName,
			},
		},
		VolumeMounts: []corev1.VolumeMount{
			{
				Name:      "workspace",
				MountPath: "/workspace",
			},
		},
	}
}

func buildEnvoyContainer() corev1.Container {
	return corev1.Container{
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
	}
}

func buildTTYDContainer(config *PodConfig) corev1.Container {
	imageRepo := getEnvOrDefault("DEFAULT_WORKER_IMAGE_REPOSITORY", "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker")
	return corev1.Container{
		Name:  "ttyd",
		Image: fmt.Sprintf("%s:%s", imageRepo, config.ImageTag),
		Command: []string{
			"/bin/sh", "-c",
			// Create tmux session with fish shell that runs opencode, then falls back to fish on exit
			"tmux -f /dev/null -L opencode new-session -d -s opencode -c /workspace/session " +
				"\"fish -c 'opencode; exec fish'\" || true && " +
				"exec ttyd -p 7682 --writable --max-clients 5 " +
				"tmux -L opencode attach -t opencode",
		},
		WorkingDir: "/workspace/session",
		Env:        buildSessionEnv(config),
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
		ReadinessProbe: &corev1.Probe{
			ProbeHandler: corev1.ProbeHandler{
				Exec: &corev1.ExecAction{
					Command: []string{
						"/bin/sh", "-c",
						"test -d /workspace/session && test -f /workspace/session/.git/config",
					},
				},
			},
			InitialDelaySeconds: 2,
			PeriodSeconds:       2,
			TimeoutSeconds:      1,
			FailureThreshold:    30, // 60 seconds total (30 * 2s)
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
	}
}

func buildSessionEnv(config *PodConfig) []corev1.EnvVar {
	env := []corev1.EnvVar{
		// Core session configuration
		{
			Name:  "HOME",
			Value: "/home/user",
		},
		{
			Name:  "SESSION_ID",
			Value: config.SessionID,
		},
		{
			Name:  "GIT_BRANCH",
			Value: config.GitBranch,
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
						Name: config.APIKeysSecretName,
					},
					Key: config.AnthropicSecretKey,
				},
			},
		},
		// Google API authentication (for AI services)
		{
			Name: "GOOGLE_API_KEY",
			ValueFrom: &corev1.EnvVarSource{
				SecretKeyRef: &corev1.SecretKeySelector{
					LocalObjectReference: corev1.LocalObjectReference{
						Name: config.APIKeysSecretName,
					},
					Key: config.GoogleSecretKey,
				},
			},
		},
		// BuildBuddy API key for remote cache/build execution
		{
			Name: "BUILDBUDDY_API_KEY",
			ValueFrom: &corev1.EnvVarSource{
				SecretKeyRef: &corev1.SecretKeySelector{
					LocalObjectReference: corev1.LocalObjectReference{
						Name: config.APIKeysSecretName,
					},
					Key: config.BuildBuddySecretKey,
				},
			},
		},
	}

	// Add OpenTelemetry configuration if enabled
	if config.OTelEnabled {
		otelEnv := []corev1.EnvVar{
			{
				Name:  "OTEL_EXPORTER_OTLP_ENDPOINT",
				Value: config.OTelEndpoint,
			},
			{
				Name:  "OTEL_SERVICE_NAME",
				Value: fmt.Sprintf("opencode-session-%s", config.SessionID),
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
				Value: fmt.Sprintf("deployment.environment=homelab,service.namespace=ttyd-sessions,session.id=%s", config.SessionID),
			},
		}
		env = append(env, otelEnv...)
	}

	// Add proxy configuration if set
	if config.HTTPProxy != "" {
		env = append(env, corev1.EnvVar{
			Name:  "HTTP_PROXY",
			Value: config.HTTPProxy,
		})
	}
	if config.HTTPSProxy != "" {
		env = append(env, corev1.EnvVar{
			Name:  "HTTPS_PROXY",
			Value: config.HTTPSProxy,
		})
	}
	if config.NoProxy != "" {
		env = append(env, corev1.EnvVar{
			Name:  "NO_PROXY",
			Value: config.NoProxy,
		})
	}

	return env
}

func mustParseQuantity(s string) resource.Quantity {
	q, err := resource.ParseQuantity(s)
	if err != nil {
		panic(err)
	}
	return q
}

// BuildSessionService creates a Kubernetes Service for direct access to a session pod
// This enables low-latency WebSocket connections by bypassing the backend API proxy
func BuildSessionService(sessionID string) *corev1.Service {
	serviceName := fmt.Sprintf("ttyd-session-%s", sessionID)

	return &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      serviceName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":        "ttyd-session",
				"session-id": sessionID,
			},
		},
		Spec: corev1.ServiceSpec{
			Type: corev1.ServiceTypeClusterIP,
			Selector: map[string]string{
				"app":        "ttyd-session",
				"session-id": sessionID,
			},
			Ports: []corev1.ServicePort{
				{
					Name:     "envoy-proxy",
					Port:     7681,
					Protocol: corev1.ProtocolTCP,
				},
			},
		},
	}
}
