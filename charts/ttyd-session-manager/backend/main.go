package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/go-containerregistry/pkg/crane"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	metricsv "k8s.io/metrics/pkg/client/clientset/versioned"
)

const (
	namespace = "ttyd-sessions"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true // Allow all origins for development
	},
	Subprotocols:    []string{"tty"}, // ttyd requires the "tty" subprotocol
	ReadBufferSize:  32 * 1024,       // 32KB read buffer for better throughput
	WriteBufferSize: 32 * 1024,       // 32KB write buffer for better throughput
}

type SessionManager struct {
	clientset     *kubernetes.Clientset
	metricsClient *metricsv.Clientset
}

type CreateSessionRequest struct {
	DisplayName string `json:"display_name" binding:"required"` // User-friendly session name
	GitBranch   string `json:"git_branch,omitempty"`            // Optional: defaults to "session-{id}"
	ImageTag    string `json:"image_tag,omitempty"`             // Optional: defaults to "main"
}

type SessionResponse struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	PodName     string `json:"pod_name"`
	State       string `json:"state"`
	Ready       bool   `json:"ready"`                       // Pod is ready for connections
	ImageTag    string `json:"image_tag,omitempty"`
	Branch      string `json:"branch,omitempty"`
	CreatedAt   string `json:"created_at,omitempty"`
	LastActive  string `json:"last_active,omitempty"`
	AgeDays     int    `json:"age_days,omitempty"`
	MemoryUsage string `json:"memory_usage,omitempty"`
	CPUUsage    string `json:"cpu_usage,omitempty"`
	TerminalURL string `json:"terminal_url,omitempty"`
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

	// Create metrics client
	metricsClient, err := metricsv.NewForConfig(config)
	if err != nil {
		log.Printf("Warning: Failed to create metrics client: %v (metrics will be unavailable)", err)
	}

	sm := &SessionManager{
		clientset:     clientset,
		metricsClient: metricsClient,
	}

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
	r.GET("/api/sessions/:id/terminal", sm.terminalWebSocket)
	r.DELETE("/api/sessions/:id", sm.deleteSession)

	// Web interface routes - proxy to ttyd on session pod
	r.GET("/sessions/:id", sm.sessionWebInterface)
	r.GET("/sessions/:id/*path", sm.sessionWebInterface)

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

	// Generate session ID
	sessionID := uuid.New().String()[:8]

	// Use the requested image tag (empty string will use DEFAULT_WORKER_IMAGE_TAG from env)
	// The default tag is managed by ArgoCD Image Updater via Helm values
	imageTag := req.ImageTag

	// Build pod config and create pod spec
	config := NewPodConfig(sessionID, req.DisplayName, imageTag, req.GitBranch)
	pod := BuildSessionPod(config)

	// Create Service first for DNS resolution (required for direct nginx routing)
	service := BuildSessionService(sessionID)
	_, err := sm.clientset.CoreV1().Services(namespace).Create(
		context.Background(),
		service,
		metav1.CreateOptions{},
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to create service: %v", err)})
		return
	}

	// Create Pod
	createdPod, err := sm.clientset.CoreV1().Pods(namespace).Create(
		context.Background(),
		pod,
		metav1.CreateOptions{},
	)
	if err != nil {
		// Clean up the service if pod creation fails
		sm.clientset.CoreV1().Services(namespace).Delete(
			context.Background(),
			service.Name,
			metav1.DeleteOptions{},
		)
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to create pod: %v", err)})
		return
	}

	c.JSON(http.StatusCreated, SessionResponse{
		ID:       sessionID,
		Name:     req.DisplayName,
		PodName:  createdPod.Name,
		State:    "creating",
		Ready:    false,
		ImageTag: config.ImageTag,
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

		// Check if pod is ready (all readiness probes passed)
		ready := false
		for _, condition := range pod.Status.Conditions {
			if condition.Type == corev1.PodReady && condition.Status == corev1.ConditionTrue {
				ready = true
				break
			}
		}

		imageTag := pod.Annotations["image-tag"]
		if imageTag == "" {
			imageTag = "main" // Default for older sessions without this annotation
		}

		sessionName := pod.Annotations["session-name"]
		if sessionName == "" {
			sessionName = pod.Name // Fallback for older sessions without this annotation
		}

		gitBranch := pod.Annotations["git-branch"]

		// Get creation and last active times
		createdAt := pod.CreationTimestamp.Time.Format(time.RFC3339)
		lastActive := createdAt // Default to creation time
		if pod.Status.StartTime != nil {
			lastActive = pod.Status.StartTime.Time.Format(time.RFC3339)
		}

		// Calculate age in days
		ageDays := calculateAgeDays(pod.CreationTimestamp.Time)

		// Get metrics
		cpuUsage, memoryUsage := sm.getPodMetrics(pod.Name)

		// Build terminal URL
		terminalURL := fmt.Sprintf("/api/sessions/%s/terminal", sessionID)

		sessions = append(sessions, SessionResponse{
			ID:          sessionID,
			Name:        sessionName,
			PodName:     pod.Name,
			State:       state,
			Ready:       ready,
			ImageTag:    imageTag,
			Branch:      gitBranch,
			CreatedAt:   createdAt,
			LastActive:  lastActive,
			AgeDays:     ageDays,
			CPUUsage:    cpuUsage,
			MemoryUsage: memoryUsage,
			TerminalURL: terminalURL,
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

	// Check if pod is ready (all readiness probes passed)
	ready := false
	for _, condition := range pod.Status.Conditions {
		if condition.Type == corev1.PodReady && condition.Status == corev1.ConditionTrue {
			ready = true
			break
		}
	}

	imageTag := pod.Annotations["image-tag"]
	if imageTag == "" {
		imageTag = "main" // Default for older sessions without this annotation
	}

	sessionName := pod.Annotations["session-name"]
	if sessionName == "" {
		sessionName = pod.Name // Fallback for older sessions without this annotation
	}

	gitBranch := pod.Annotations["git-branch"]

	// Get creation and last active times
	createdAt := pod.CreationTimestamp.Time.Format(time.RFC3339)
	lastActive := createdAt // Default to creation time
	if pod.Status.StartTime != nil {
		lastActive = pod.Status.StartTime.Time.Format(time.RFC3339)
	}

	// Calculate age in days
	ageDays := calculateAgeDays(pod.CreationTimestamp.Time)

	// Get metrics
	cpuUsage, memoryUsage := sm.getPodMetrics(pod.Name)

	// Build terminal URL
	terminalURL := fmt.Sprintf("/api/sessions/%s/terminal", sessionID)

	c.JSON(http.StatusOK, SessionResponse{
		ID:          sessionID,
		Name:        sessionName,
		PodName:     pod.Name,
		State:       state,
		Ready:       ready,
		ImageTag:    imageTag,
		Branch:      gitBranch,
		CreatedAt:   createdAt,
		LastActive:  lastActive,
		AgeDays:     ageDays,
		CPUUsage:    cpuUsage,
		MemoryUsage: memoryUsage,
		TerminalURL: terminalURL,
	})
}

func (sm *SessionManager) deleteSession(c *gin.Context) {
	sessionID := c.Param("id")
	podName := fmt.Sprintf("ttyd-session-%s", sessionID)
	serviceName := fmt.Sprintf("ttyd-session-%s", sessionID)

	// Delete Pod
	err := sm.clientset.CoreV1().Pods(namespace).Delete(
		context.Background(),
		podName,
		metav1.DeleteOptions{},
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to delete pod: %v", err)})
		return
	}

	// Delete Service (best effort - don't fail if it doesn't exist)
	sm.clientset.CoreV1().Services(namespace).Delete(
		context.Background(),
		serviceName,
		metav1.DeleteOptions{},
	)

	c.JSON(http.StatusOK, gin.H{"message": "Session deleted"})
}

func (sm *SessionManager) terminalWebSocket(c *gin.Context) {
	sessionID := c.Param("id")
	podName := fmt.Sprintf("ttyd-session-%s", sessionID)

	// Verify pod exists
	pod, err := sm.clientset.CoreV1().Pods(namespace).Get(
		context.Background(),
		podName,
		metav1.GetOptions{},
	)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	// Check if pod is running and ready
	if pod.Status.Phase != corev1.PodRunning {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Session is not running"})
		return
	}

	// Check if pod is ready (all readiness probes passed)
	podReady := false
	for _, condition := range pod.Status.Conditions {
		if condition.Type == corev1.PodReady && condition.Status == corev1.ConditionTrue {
			podReady = true
			break
		}
	}
	if !podReady {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Session is starting, please wait..."})
		return
	}

	// Upgrade HTTP connection to WebSocket
	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("Failed to upgrade WebSocket: %v", err)
		return
	}
	defer conn.Close()

	// For MVP: Connect directly to pod IP and port
	// The pod has an envoy sidecar listening on port 7681
	podIP := pod.Status.PodIP
	if podIP == "" {
		conn.WriteMessage(websocket.TextMessage, []byte("Error: Pod IP not available"))
		return
	}

	// Connect to the ttyd service via envoy proxy (port 7681)
	ttydURL := fmt.Sprintf("ws://%s:7681/ws", podIP)

	// Create WebSocket connection to ttyd with "tty" subprotocol and larger buffers
	headers := make(http.Header)
	headers.Set("Sec-WebSocket-Protocol", "tty")
	dialer := websocket.Dialer{
		ReadBufferSize:  32 * 1024, // 32KB read buffer
		WriteBufferSize: 32 * 1024, // 32KB write buffer
	}
	ttydConn, _, err := dialer.Dial(ttydURL, headers)
	if err != nil {
		errMsg := fmt.Sprintf("Error connecting to terminal: %v", err)
		conn.WriteMessage(websocket.TextMessage, []byte(errMsg))
		log.Printf("Failed to connect to ttyd at %s: %v", ttydURL, err)
		return
	}
	defer ttydConn.Close()

	// Bidirectional proxy between client and ttyd
	// No write deadlines for lower latency (removes syscall overhead on every message)
	errChan := make(chan error, 2)

	// Client → ttyd
	go func() {
		for {
			messageType, message, err := conn.ReadMessage()
			if err != nil {
				errChan <- fmt.Errorf("client read error: %w", err)
				return
			}
			if err := ttydConn.WriteMessage(messageType, message); err != nil {
				errChan <- fmt.Errorf("ttyd write error: %w", err)
				return
			}
		}
	}()

	// ttyd → Client (typically much more data, so optimize for throughput)
	go func() {
		for {
			messageType, message, err := ttydConn.ReadMessage()
			if err != nil {
				errChan <- fmt.Errorf("ttyd read error: %w", err)
				return
			}
			if err := conn.WriteMessage(messageType, message); err != nil {
				errChan <- fmt.Errorf("client write error: %w", err)
				return
			}
		}
	}()

	// Wait for error from either goroutine
	err = <-errChan
	log.Printf("WebSocket proxy terminated: %v", err)
}

// sessionWebInterface proxies HTTP requests to the ttyd web interface on the session pod
func (sm *SessionManager) sessionWebInterface(c *gin.Context) {
	sessionID := c.Param("id")
	podName := fmt.Sprintf("ttyd-session-%s", sessionID)

	// Verify pod exists and is running
	pod, err := sm.clientset.CoreV1().Pods(namespace).Get(
		context.Background(),
		podName,
		metav1.GetOptions{},
	)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	if pod.Status.Phase != corev1.PodRunning {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Session is not running"})
		return
	}

	// Check if pod is ready (all readiness probes passed)
	podReady := false
	for _, condition := range pod.Status.Conditions {
		if condition.Type == corev1.PodReady && condition.Status == corev1.ConditionTrue {
			podReady = true
			break
		}
	}
	if !podReady {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Session is starting, please wait..."})
		return
	}

	podIP := pod.Status.PodIP
	if podIP == "" {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Pod IP not available"})
		return
	}

	// Check if this is a WebSocket upgrade request
	if c.Request.Header.Get("Upgrade") == "websocket" {
		// Handle WebSocket connection
		sm.proxyWebSocket(c, podIP)
		return
	}

	// Create reverse proxy to ttyd on the pod (port 7681 - envoy sidecar)
	targetURL, err := url.Parse(fmt.Sprintf("http://%s:7681", podIP))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to parse target URL"})
		return
	}

	// Create a reverse proxy
	proxy := httputil.NewSingleHostReverseProxy(targetURL)

	// Modify the request path to remove the /sessions/:id prefix
	pathParam := c.Param("path")
	c.Request.URL.Path = pathParam
	if pathParam == "" {
		c.Request.URL.Path = "/"
	}

	// Serve the proxied request
	proxy.ServeHTTP(c.Writer, c.Request)
}

// proxyWebSocket handles WebSocket connections to the ttyd pod
func (sm *SessionManager) proxyWebSocket(c *gin.Context, podIP string) {
	// Upgrade HTTP connection to WebSocket
	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("Failed to upgrade WebSocket: %v", err)
		return
	}
	defer conn.Close()

	// Connect to the ttyd WebSocket endpoint (via envoy proxy on port 7681)
	// The client is connecting to /sessions/:id/ws, which maps to /ws on ttyd
	ttydURL := fmt.Sprintf("ws://%s:7681/ws", podIP)

	// Create WebSocket connection to ttyd with "tty" subprotocol
	headers := make(http.Header)
	headers.Set("Sec-WebSocket-Protocol", "tty")
	ttydConn, _, err := websocket.DefaultDialer.Dial(ttydURL, headers)
	if err != nil {
		errMsg := fmt.Sprintf("Error connecting to terminal: %v", err)
		conn.WriteMessage(websocket.TextMessage, []byte(errMsg))
		log.Printf("Failed to connect to ttyd at %s: %v", ttydURL, err)
		return
	}
	defer ttydConn.Close()

	// Bidirectional proxy between client and ttyd
	// No write deadlines for lower latency (removes syscall overhead on every message)
	errChan := make(chan error, 2)

	// Client → ttyd
	go func() {
		for {
			messageType, message, err := conn.ReadMessage()
			if err != nil {
				errChan <- fmt.Errorf("client read error: %w", err)
				return
			}
			if err := ttydConn.WriteMessage(messageType, message); err != nil {
				errChan <- fmt.Errorf("ttyd write error: %w", err)
				return
			}
		}
	}()

	// ttyd → Client (typically much more data, so optimize for throughput)
	go func() {
		for {
			messageType, message, err := ttydConn.ReadMessage()
			if err != nil {
				errChan <- fmt.Errorf("ttyd read error: %w", err)
				return
			}
			if err := conn.WriteMessage(messageType, message); err != nil {
				errChan <- fmt.Errorf("client write error: %w", err)
				return
			}
		}
	}()

	// Wait for error from either goroutine
	err = <-errChan
	log.Printf("WebSocket proxy terminated: %v", err)
}

// Helper functions for metrics and metadata
func (sm *SessionManager) getPodMetrics(podName string) (cpuUsage, memoryUsage string) {
	if sm.metricsClient == nil {
		return "N/A", "N/A"
	}

	metrics, err := sm.metricsClient.MetricsV1beta1().PodMetricses(namespace).Get(
		context.Background(),
		podName,
		metav1.GetOptions{},
	)
	if err != nil {
		// Metrics not available (pod might be too new or metrics-server issue)
		return "N/A", "N/A"
	}

	var totalCPU, totalMemory int64
	for _, container := range metrics.Containers {
		totalCPU += container.Usage.Cpu().MilliValue()
		totalMemory += container.Usage.Memory().Value()
	}

	// Format CPU as millicores (e.g., "150m")
	cpuUsage = fmt.Sprintf("%dm", totalCPU)

	// Format memory as Mi (e.g., "256Mi")
	memoryMi := totalMemory / (1024 * 1024)
	memoryUsage = fmt.Sprintf("%dMi", memoryMi)

	return cpuUsage, memoryUsage
}

func calculateAgeDays(createdAt time.Time) int {
	return int(time.Since(createdAt).Hours() / 24)
}

// Helper functions
func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
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

// isMutableTag checks if a tag is mutable (like "main", branch names) vs immutable (version tags)
// Version tags match the pattern: YYYY.MM.DD.HH.MM.SS-hash
func isMutableTag(tag string) bool {
	if tag == "" || tag == "main" || tag == "latest" {
		return true
	}
	// Check if it matches our version tag pattern
	versionPattern := regexp.MustCompile(`^\d{4}\.\d{2}\.\d{2}\.\d{2}\.\d{2}\.\d{2}-[a-f0-9]+$`)
	return !versionPattern.MatchString(tag)
}

// resolveImageTag resolves a mutable tag (like "main") to an immutable version tag
// by finding all tags with the same digest and picking the version tag
func resolveImageTag(repository string, tag string) (string, error) {
	if tag == "" {
		tag = "main"
	}

	imageRef := fmt.Sprintf("%s:%s", repository, tag)

	// Get the digest of the mutable tag
	digest, err := crane.Digest(imageRef)
	if err != nil {
		return "", fmt.Errorf("failed to get digest for %s: %w", imageRef, err)
	}

	// List all tags in the repository
	tags, err := crane.ListTags(repository)
	if err != nil {
		return "", fmt.Errorf("failed to list tags for %s: %w", repository, err)
	}

	// Version tag pattern: YYYY.MM.DD.HH.MM.SS-hash
	versionPattern := regexp.MustCompile(`^\d{4}\.\d{2}\.\d{2}\.\d{2}\.\d{2}\.\d{2}-[a-f0-9]+$`)

	// Find all version tags with the same digest
	var versionTags []string
	for _, t := range tags {
		if !versionPattern.MatchString(t) {
			continue
		}

		tagRef := fmt.Sprintf("%s:%s", repository, t)
		tagDigest, err := crane.Digest(tagRef)
		if err != nil {
			log.Printf("Warning: Failed to get digest for %s: %v", tagRef, err)
			continue
		}

		if tagDigest == digest {
			versionTags = append(versionTags, t)
		}
	}

	if len(versionTags) == 0 {
		return "", fmt.Errorf("no version tags found with digest %s", digest)
	}

	// Return the latest version tag (they're sorted lexicographically by timestamp)
	latestTag := versionTags[len(versionTags)-1]
	return latestTag, nil
}
