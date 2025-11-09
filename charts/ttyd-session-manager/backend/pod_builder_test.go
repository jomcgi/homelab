package main

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
)

func TestBuildSessionPod_BasicStructure(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	pod := BuildSessionPod(config)

	// Verify basic metadata
	assert.Equal(t, "ttyd-session-test-123", pod.Name)
	assert.Equal(t, namespace, pod.Namespace)
	assert.Equal(t, "ttyd-session", pod.Labels["app"])
	assert.Equal(t, "test-123", pod.Labels["session-id"])
	assert.Equal(t, "Test Session", pod.Annotations["session-name"])
	assert.Equal(t, "session-test-123", pod.Annotations["git-branch"])
	assert.Equal(t, "main", pod.Annotations["image-tag"])
}

func TestBuildSessionPod_SecurityContext(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	pod := BuildSessionPod(config)

	// Pod-level security context
	require.NotNil(t, pod.Spec.SecurityContext)
	assert.True(t, *pod.Spec.SecurityContext.RunAsNonRoot, "Pod must run as non-root")
	assert.Equal(t, int64(1000), *pod.Spec.SecurityContext.RunAsUser)
	assert.Equal(t, int64(1000), *pod.Spec.SecurityContext.FSGroup)
}

func TestBuildEnvoyContainer_SecurityContext(t *testing.T) {
	container := buildEnvoyContainer()

	require.NotNil(t, container.SecurityContext)
	assert.True(t, *container.SecurityContext.ReadOnlyRootFilesystem, "Envoy root filesystem must be read-only")
	assert.False(t, *container.SecurityContext.AllowPrivilegeEscalation, "Envoy must not allow privilege escalation")
	assert.True(t, *container.SecurityContext.RunAsNonRoot, "Envoy must run as non-root")
	assert.Equal(t, int64(65534), *container.SecurityContext.RunAsUser, "Envoy should run as nobody user")
	assert.Contains(t, container.SecurityContext.Capabilities.Drop, corev1.Capability("ALL"), "Envoy must drop all capabilities")
}

func TestBuildEnvoyContainer_Resources(t *testing.T) {
	container := buildEnvoyContainer()

	// Verify resource requests
	assert.Equal(t, "50m", container.Resources.Requests.Cpu().String())
	assert.Equal(t, "64Mi", container.Resources.Requests.Memory().String())

	// Verify resource limits
	assert.Equal(t, "200m", container.Resources.Limits.Cpu().String())
	assert.Equal(t, "128Mi", container.Resources.Limits.Memory().String())
}

func TestBuildEnvoyContainer_Ports(t *testing.T) {
	container := buildEnvoyContainer()

	ports := make(map[string]int32)
	for _, p := range container.Ports {
		ports[p.Name] = p.ContainerPort
	}

	assert.Equal(t, int32(7681), ports["envoy-proxy"], "Envoy proxy port should be 7681")
	assert.Equal(t, int32(9901), ports["envoy-admin"], "Envoy admin port should be 9901")
}

func TestBuildTTYDContainer_SecurityContext(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	container := buildTTYDContainer(config)

	require.NotNil(t, container.SecurityContext)
	assert.False(t, *container.SecurityContext.AllowPrivilegeEscalation, "TTYD must not allow privilege escalation")
	assert.False(t, *container.SecurityContext.ReadOnlyRootFilesystem, "TTYD needs writable filesystem")
	assert.Contains(t, container.SecurityContext.Capabilities.Drop, corev1.Capability("ALL"), "TTYD must drop all capabilities")
}

func TestBuildTTYDContainer_Resources(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	container := buildTTYDContainer(config)

	// Verify resource requests
	assert.Equal(t, "100m", container.Resources.Requests.Cpu().String())
	assert.Equal(t, "256Mi", container.Resources.Requests.Memory().String())

	// Verify resource limits
	assert.Equal(t, "500m", container.Resources.Limits.Cpu().String())
	assert.Equal(t, "512Mi", container.Resources.Limits.Memory().String())
}

func TestBuildTTYDContainer_ImageTag(t *testing.T) {
	tests := []struct {
		name     string
		imageTag string
		want     string
	}{
		{
			name:     "default image tag",
			imageTag: "main",
			want:     "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker:main",
		},
		{
			name:     "custom image tag",
			imageTag: "2025.01.08.12.34.56-abc1234",
			want:     "ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker:2025.01.08.12.34.56-abc1234",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			config := &PodConfig{
				SessionID:   "test-123",
				DisplayName: "Test Session",
				ImageTag:    tt.imageTag,
				GitBranch:   "session-test-123",
			}

			container := buildTTYDContainer(config)
			assert.Equal(t, tt.want, container.Image)
		})
	}
}

func TestBuildTTYDContainer_ReadinessProbe(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	container := buildTTYDContainer(config)

	require.NotNil(t, container.ReadinessProbe)
	require.NotNil(t, container.ReadinessProbe.Exec)
	assert.Equal(t, int32(2), container.ReadinessProbe.InitialDelaySeconds)
	assert.Equal(t, int32(2), container.ReadinessProbe.PeriodSeconds)
	assert.Equal(t, int32(30), container.ReadinessProbe.FailureThreshold, "Should wait up to 60 seconds (30 * 2s)")

	// Verify probe checks for git config
	cmd := container.ReadinessProbe.Exec.Command
	require.Len(t, cmd, 3)
	assert.Contains(t, cmd[2], "/workspace/session")
	assert.Contains(t, cmd[2], ".git/config")
}

func TestBuildTTYDContainer_PreStopHook(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	container := buildTTYDContainer(config)

	require.NotNil(t, container.Lifecycle)
	require.NotNil(t, container.Lifecycle.PreStop)
	require.NotNil(t, container.Lifecycle.PreStop.Exec)

	// Verify PreStop hook has git commit/push logic
	cmd := container.Lifecycle.PreStop.Exec.Command
	require.Len(t, cmd, 3)
	script := cmd[2]
	assert.Contains(t, script, "git add -A")
	assert.Contains(t, script, "git commit")
	assert.Contains(t, script, "git push")
}

func TestBuildSessionPod_Volumes(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	pod := BuildSessionPod(config)

	volumes := make(map[string]corev1.Volume)
	for _, v := range pod.Spec.Volumes {
		volumes[v.Name] = v
	}

	// Verify required volumes exist
	assert.Contains(t, volumes, "workspace", "Missing workspace volume")
	assert.Contains(t, volumes, "home", "Missing home volume")
	assert.Contains(t, volumes, "envoy-config", "Missing envoy-config volume")

	// Verify workspace and home are EmptyDir
	assert.NotNil(t, volumes["workspace"].EmptyDir)
	assert.NotNil(t, volumes["home"].EmptyDir)

	// Verify envoy-config is from ConfigMap
	assert.NotNil(t, volumes["envoy-config"].ConfigMap)
	assert.Equal(t, "ttyd-session-manager-envoy-session", volumes["envoy-config"].ConfigMap.Name)
}

func TestBuildSessionPod_RestartPolicy(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	pod := BuildSessionPod(config)

	assert.Equal(t, corev1.RestartPolicyNever, pod.Spec.RestartPolicy, "Sessions should never restart automatically")
}

func TestBuildSessionPod_ServiceAccount(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	pod := BuildSessionPod(config)

	assert.Equal(t, "ttyd-session-pods", pod.Spec.ServiceAccountName)
}

func TestBuildSessionEnv_CoreVariables(t *testing.T) {
	config := &PodConfig{
		SessionID:           "test-123",
		DisplayName:         "Test Session",
		ImageTag:            "main",
		GitBranch:           "session-test-123",
		APIKeysSecretName:   "test-api-keys",
		AnthropicSecretKey:  "anthropic_key",
		GoogleSecretKey:     "google_key",
		BuildBuddySecretKey: "buildbuddy_key",
		OTelEnabled:         false,
	}

	env := buildSessionEnv(config)

	envMap := make(map[string]corev1.EnvVar)
	for _, e := range env {
		envMap[e.Name] = e
	}

	// Verify core environment variables
	assert.Equal(t, "/home/user", envMap["HOME"].Value)
	assert.Equal(t, "test-123", envMap["SESSION_ID"].Value)
	assert.Equal(t, "session-test-123", envMap["GIT_BRANCH"].Value)

	// Verify secret references
	assert.Equal(t, "ttyd-session-manager-github", envMap["GITHUB_TOKEN"].ValueFrom.SecretKeyRef.Name)
	assert.Equal(t, "test-api-keys", envMap["ANTHROPIC_API_KEY"].ValueFrom.SecretKeyRef.Name)
	assert.Equal(t, "test-api-keys", envMap["GOOGLE_API_KEY"].ValueFrom.SecretKeyRef.Name)
	assert.Equal(t, "test-api-keys", envMap["BUILDBUDDY_API_KEY"].ValueFrom.SecretKeyRef.Name)
}

func TestBuildSessionEnv_OTelEnabled(t *testing.T) {
	config := &PodConfig{
		SessionID:           "test-123",
		DisplayName:         "Test Session",
		ImageTag:            "main",
		GitBranch:           "session-test-123",
		APIKeysSecretName:   "test-api-keys",
		AnthropicSecretKey:  "anthropic_key",
		GoogleSecretKey:     "google_key",
		BuildBuddySecretKey: "buildbuddy_key",
		OTelEnabled:         true,
		OTelEndpoint:        "http://otel-collector:4317",
	}

	env := buildSessionEnv(config)

	envMap := make(map[string]corev1.EnvVar)
	for _, e := range env {
		envMap[e.Name] = e
	}

	// Verify OpenTelemetry variables are present
	assert.Equal(t, "http://otel-collector:4317", envMap["OTEL_EXPORTER_OTLP_ENDPOINT"].Value)
	assert.Equal(t, "opencode-session-test-123", envMap["OTEL_SERVICE_NAME"].Value)
	assert.Equal(t, "otlp", envMap["OTEL_TRACES_EXPORTER"].Value)
	assert.Equal(t, "otlp", envMap["OTEL_METRICS_EXPORTER"].Value)
	assert.Equal(t, "otlp", envMap["OTEL_LOGS_EXPORTER"].Value)
	assert.Contains(t, envMap["OTEL_RESOURCE_ATTRIBUTES"].Value, "session.id=test-123")
}

func TestBuildSessionEnv_OTelDisabled(t *testing.T) {
	config := &PodConfig{
		SessionID:           "test-123",
		DisplayName:         "Test Session",
		ImageTag:            "main",
		GitBranch:           "session-test-123",
		APIKeysSecretName:   "test-api-keys",
		AnthropicSecretKey:  "anthropic_key",
		GoogleSecretKey:     "google_key",
		BuildBuddySecretKey: "buildbuddy_key",
		OTelEnabled:         false,
	}

	env := buildSessionEnv(config)

	envMap := make(map[string]corev1.EnvVar)
	for _, e := range env {
		envMap[e.Name] = e
	}

	// Verify OpenTelemetry variables are NOT present
	_, hasOTel := envMap["OTEL_EXPORTER_OTLP_ENDPOINT"]
	assert.False(t, hasOTel, "OTEL variables should not be present when disabled")
}

func TestBuildSessionEnv_ProxyConfiguration(t *testing.T) {
	config := &PodConfig{
		SessionID:           "test-123",
		DisplayName:         "Test Session",
		ImageTag:            "main",
		GitBranch:           "session-test-123",
		APIKeysSecretName:   "test-api-keys",
		AnthropicSecretKey:  "anthropic_key",
		GoogleSecretKey:     "google_key",
		BuildBuddySecretKey: "buildbuddy_key",
		OTelEnabled:         false,
		HTTPProxy:           "http://proxy.example.com:8080",
		HTTPSProxy:          "https://proxy.example.com:8443",
		NoProxy:             "localhost,127.0.0.1",
	}

	env := buildSessionEnv(config)

	envMap := make(map[string]corev1.EnvVar)
	for _, e := range env {
		envMap[e.Name] = e
	}

	// Verify proxy configuration
	assert.Equal(t, "http://proxy.example.com:8080", envMap["HTTP_PROXY"].Value)
	assert.Equal(t, "https://proxy.example.com:8443", envMap["HTTPS_PROXY"].Value)
	assert.Equal(t, "localhost,127.0.0.1", envMap["NO_PROXY"].Value)
}

func TestNewPodConfig_Defaults(t *testing.T) {
	// Temporarily unset environment variables for clean test
	originalAPIKeys := getEnvOrDefault("API_KEYS_SECRET_NAME", "")
	defer func() {
		if originalAPIKeys != "" {
			t.Setenv("API_KEYS_SECRET_NAME", originalAPIKeys)
		}
	}()

	config := NewPodConfig("test-123", "Test Session", "", "")

	// Verify defaults
	assert.Equal(t, "test-123", config.SessionID)
	assert.Equal(t, "Test Session", config.DisplayName)
	assert.Equal(t, "main", config.ImageTag, "Should default to 'main' image tag")
	assert.Equal(t, "session-test-123", config.GitBranch, "Should default to session-{id}")
	assert.Equal(t, "ttyd-session-manager-api-keys", config.APIKeysSecretName)
	assert.Equal(t, "anthropic_api_key", config.AnthropicSecretKey)
	assert.Equal(t, "google_api_key", config.GoogleSecretKey)
	assert.Equal(t, "buildbuddy_api_key", config.BuildBuddySecretKey)
	assert.True(t, config.OTelEnabled, "OTel should be enabled by default")
	assert.Equal(t, "http://signoz-otel-collector.signoz.svc.cluster.local:4317", config.OTelEndpoint)
}

func TestNewPodConfig_CustomValues(t *testing.T) {
	config := NewPodConfig("test-456", "Custom Session", "v1.2.3", "custom-branch")

	// Verify custom values are used
	assert.Equal(t, "test-456", config.SessionID)
	assert.Equal(t, "Custom Session", config.DisplayName)
	assert.Equal(t, "v1.2.3", config.ImageTag)
	assert.Equal(t, "custom-branch", config.GitBranch)
}

func TestBuildGitCloneInitContainer_EnvironmentVariables(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	container := buildGitCloneInitContainer(config)

	envMap := make(map[string]corev1.EnvVar)
	for _, e := range container.Env {
		envMap[e.Name] = e
	}

	// Verify environment variables
	assert.Equal(t, "session-test-123", envMap["GIT_BRANCH"].Value)
	assert.Equal(t, "test-123", envMap["SESSION_ID"].Value)
	assert.Equal(t, "Test Session", envMap["SESSION_NAME"].Value)
	assert.Equal(t, "ttyd-session-manager-github", envMap["GITHUB_TOKEN"].ValueFrom.SecretKeyRef.Name)
	assert.Equal(t, "github_token", envMap["GITHUB_TOKEN"].ValueFrom.SecretKeyRef.Key)
}

func TestBuildGitCloneInitContainer_Script(t *testing.T) {
	config := &PodConfig{
		SessionID:   "test-123",
		DisplayName: "Test Session",
		ImageTag:    "main",
		GitBranch:   "session-test-123",
	}

	container := buildGitCloneInitContainer(config)

	require.Len(t, container.Args, 1)
	script := container.Args[0]

	// Verify key operations in script
	assert.Contains(t, script, "git clone")
	assert.Contains(t, script, "git checkout -b ${GIT_BRANCH}")
	assert.Contains(t, script, "git config user.name")
	assert.Contains(t, script, "git commit")
	assert.Contains(t, script, "git push -u origin ${GIT_BRANCH}")
	assert.Contains(t, script, ".session/metadata.json")
	assert.Contains(t, script, ".claude/context.json")
}
