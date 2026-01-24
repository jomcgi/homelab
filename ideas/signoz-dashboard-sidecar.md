Good call on all of those. Here's the updated implementation:

```go
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/klog/v2"
)

const (
	dashboardLabel   = "signoz.io/dashboard"
	dashboardNameKey = "signoz.io/dashboard-name"
	dashboardPath    = "api/v1/dashboards"

	// State ConfigMap details
	stateConfigMapName = "signoz-dashboard-sidecar-state"
)

// Metrics
var (
	syncTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "signoz_dashboard_sidecar_sync_total",
		Help: "Total number of dashboard sync operations",
	}, []string{"operation", "status"})

	syncDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "signoz_dashboard_sidecar_sync_duration_seconds",
		Help:    "Duration of dashboard sync operations",
		Buckets: prometheus.DefBuckets,
	}, []string{"operation"})

	dashboardsManaged = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "signoz_dashboard_sidecar_dashboards_managed",
		Help: "Current number of dashboards managed by the sidecar",
	})

	configMapsWatched = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "signoz_dashboard_sidecar_configmaps_watched",
		Help: "Current number of ConfigMaps being watched",
	})

	lastReconcileTime = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "signoz_dashboard_sidecar_last_reconcile_timestamp",
		Help: "Unix timestamp of last successful reconciliation",
	})

	apiErrors = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "signoz_dashboard_sidecar_api_errors_total",
		Help: "Total number of SigNoz API errors",
	}, []string{"endpoint", "status_code"})
)

type SidecarConfig struct {
	SignozURL         string
	SignozAPIKey      string
	Namespace         string // empty = all namespaces
	StateNamespace    string // namespace for state ConfigMap
	ReconcileInterval time.Duration
	MetricsAddr       string
}

// DashboardState tracks a synced dashboard
type DashboardState struct {
	UUID        string `json:"uuid"`
	ContentHash string `json:"contentHash"`
	Name        string `json:"name"`
	Namespace   string `json:"namespace"`
	SyncedAt    string `json:"syncedAt"`
}

// StateStore maps ConfigMap UID -> DashboardState
type StateStore map[string]DashboardState

type DashboardSidecar struct {
	config     SidecarConfig
	clientset  *kubernetes.Clientset
	httpClient *http.Client

	stateMu sync.RWMutex
	state   StateStore
}

type dashboardResponse struct {
	Status    string        `json:"status"`
	Data      dashboardData `json:"data"`
	Error     string        `json:"error,omitempty"`
	ErrorType string        `json:"errorType,omitempty"`
}

type dashboardData struct {
	UUID string          `json:"uuid"`
	Data json.RawMessage `json:"data"`
}

func NewDashboardSidecar(config SidecarConfig) (*DashboardSidecar, error) {
	k8sConfig, err := rest.InClusterConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to get in-cluster config: %w", err)
	}

	clientset, err := kubernetes.NewForConfig(k8sConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create clientset: %w", err)
	}

	s := &DashboardSidecar{
		config:     config,
		clientset:  clientset,
		httpClient: &http.Client{Timeout: 30 * time.Second},
		state:      make(StateStore),
	}

	return s, nil
}

func (s *DashboardSidecar) Run(ctx context.Context) error {
	// Start metrics server
	go s.serveMetrics()

	// Load persisted state
	if err := s.loadState(ctx); err != nil {
		klog.Warningf("Failed to load state (starting fresh): %v", err)
	}

	// Initial sync
	if err := s.reconcileAll(ctx); err != nil {
		klog.Errorf("Initial reconciliation failed: %v", err)
	}

	// Start watching
	go s.watchConfigMaps(ctx)

	// Periodic reconciliation
	ticker := time.NewTicker(s.config.ReconcileInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			if err := s.reconcileAll(ctx); err != nil {
				klog.Errorf("Periodic reconciliation failed: %v", err)
			}
		}
	}
}

func (s *DashboardSidecar) serveMetrics() {
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})

	klog.Infof("Starting metrics server on %s", s.config.MetricsAddr)
	if err := http.ListenAndServe(s.config.MetricsAddr, mux); err != nil {
		klog.Fatalf("Metrics server failed: %v", err)
	}
}

// State persistence

func (s *DashboardSidecar) loadState(ctx context.Context) error {
	cm, err := s.clientset.CoreV1().ConfigMaps(s.config.StateNamespace).Get(ctx, stateConfigMapName, metav1.GetOptions{})
	if err != nil {
		if errors.IsNotFound(err) {
			klog.Info("No existing state ConfigMap found, starting fresh")
			return nil
		}
		return fmt.Errorf("failed to get state ConfigMap: %w", err)
	}

	stateJSON, ok := cm.Data["state"]
	if !ok {
		return nil
	}

	s.stateMu.Lock()
	defer s.stateMu.Unlock()

	if err := json.Unmarshal([]byte(stateJSON), &s.state); err != nil {
		return fmt.Errorf("failed to unmarshal state: %w", err)
	}

	dashboardsManaged.Set(float64(len(s.state)))
	klog.Infof("Loaded state with %d dashboards", len(s.state))

	return nil
}

func (s *DashboardSidecar) saveState(ctx context.Context) error {
	s.stateMu.RLock()
	stateJSON, err := json.Marshal(s.state)
	s.stateMu.RUnlock()

	if err != nil {
		return fmt.Errorf("failed to marshal state: %w", err)
	}

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      stateConfigMapName,
			Namespace: s.config.StateNamespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":      "signoz-dashboard-sidecar",
				"app.kubernetes.io/component": "state",
			},
		},
		Data: map[string]string{
			"state": string(stateJSON),
		},
	}

	_, err = s.clientset.CoreV1().ConfigMaps(s.config.StateNamespace).Get(ctx, stateConfigMapName, metav1.GetOptions{})
	if errors.IsNotFound(err) {
		_, err = s.clientset.CoreV1().ConfigMaps(s.config.StateNamespace).Create(ctx, cm, metav1.CreateOptions{})
	} else if err == nil {
		_, err = s.clientset.CoreV1().ConfigMaps(s.config.StateNamespace).Update(ctx, cm, metav1.UpdateOptions{})
	}

	if err != nil {
		return fmt.Errorf("failed to save state ConfigMap: %w", err)
	}

	s.stateMu.RLock()
	dashboardsManaged.Set(float64(len(s.state)))
	s.stateMu.RUnlock()

	return nil
}

// Content hashing

func hashContent(content []byte) string {
	hash := sha256.Sum256(content)
	return hex.EncodeToString(hash[:])
}

// Watch and reconcile

func (s *DashboardSidecar) watchConfigMaps(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		listOpts := metav1.ListOptions{
			LabelSelector: fmt.Sprintf("%s=true", dashboardLabel),
			Watch:         true,
		}

		var watcher watch.Interface
		var err error

		if s.config.Namespace == "" {
			watcher, err = s.clientset.CoreV1().ConfigMaps("").Watch(ctx, listOpts)
		} else {
			watcher, err = s.clientset.CoreV1().ConfigMaps(s.config.Namespace).Watch(ctx, listOpts)
		}

		if err != nil {
			klog.Errorf("Failed to start watch: %v", err)
			time.Sleep(5 * time.Second)
			continue
		}

		s.handleWatchEvents(ctx, watcher)
		watcher.Stop()
	}
}

func (s *DashboardSidecar) handleWatchEvents(ctx context.Context, watcher watch.Interface) {
	for {
		select {
		case <-ctx.Done():
			return
		case event, ok := <-watcher.ResultChan():
			if !ok {
				klog.Info("Watch channel closed, restarting...")
				return
			}

			cm, ok := event.Object.(*corev1.ConfigMap)
			if !ok {
				continue
			}

			switch event.Type {
			case watch.Added, watch.Modified:
				if err := s.syncDashboard(ctx, cm); err != nil {
					klog.Errorf("Failed to sync dashboard %s/%s: %v", cm.Namespace, cm.Name, err)
				}
			case watch.Deleted:
				if err := s.deleteDashboard(ctx, cm); err != nil {
					klog.Errorf("Failed to delete dashboard %s/%s: %v", cm.Namespace, cm.Name, err)
				}
			}
		}
	}
}

func (s *DashboardSidecar) reconcileAll(ctx context.Context) error {
	timer := prometheus.NewTimer(syncDuration.WithLabelValues("reconcile_all"))
	defer timer.ObserveDuration()

	listOpts := metav1.ListOptions{
		LabelSelector: fmt.Sprintf("%s=true", dashboardLabel),
	}

	var configMaps *corev1.ConfigMapList
	var err error

	if s.config.Namespace == "" {
		configMaps, err = s.clientset.CoreV1().ConfigMaps("").List(ctx, listOpts)
	} else {
		configMaps, err = s.clientset.CoreV1().ConfigMaps(s.config.Namespace).List(ctx, listOpts)
	}

	if err != nil {
		syncTotal.WithLabelValues("reconcile_all", "error").Inc()
		return fmt.Errorf("failed to list configmaps: %w", err)
	}

	configMapsWatched.Set(float64(len(configMaps.Items)))
	klog.Infof("Reconciling %d dashboard ConfigMaps", len(configMaps.Items))

	// Track which ConfigMap UIDs we've seen
	seenUIDs := make(map[string]bool)

	for i := range configMaps.Items {
		cm := &configMaps.Items[i]
		seenUIDs[string(cm.UID)] = true

		if err := s.syncDashboard(ctx, cm); err != nil {
			klog.Errorf("Failed to sync %s/%s: %v", cm.Namespace, cm.Name, err)
		}
	}

	// Clean up orphaned dashboards (ConfigMap was deleted while sidecar was down)
	s.stateMu.Lock()
	for uid, state := range s.state {
		if !seenUIDs[uid] {
			klog.Infof("Cleaning up orphaned dashboard %s (ConfigMap %s/%s no longer exists)",
				state.UUID, state.Namespace, state.Name)

			if err := s.deleteDashboardByUUID(ctx, state.UUID); err != nil {
				klog.Errorf("Failed to delete orphaned dashboard %s: %v", state.UUID, err)
			} else {
				delete(s.state, uid)
			}
		}
	}
	s.stateMu.Unlock()

	if err := s.saveState(ctx); err != nil {
		klog.Errorf("Failed to save state after reconciliation: %v", err)
	}

	lastReconcileTime.SetToCurrentTime()
	syncTotal.WithLabelValues("reconcile_all", "success").Inc()

	return nil
}

func (s *DashboardSidecar) syncDashboard(ctx context.Context, cm *corev1.ConfigMap) error {
	timer := prometheus.NewTimer(syncDuration.WithLabelValues("sync"))
	defer timer.ObserveDuration()

	// Extract dashboard JSON
	dashboardJSON, err := s.extractDashboardJSON(cm)
	if err != nil {
		syncTotal.WithLabelValues("sync", "invalid_config").Inc()
		return err
	}

	contentHash := hashContent(dashboardJSON)
	uid := string(cm.UID)

	// Check if content has changed
	s.stateMu.RLock()
	existing, exists := s.state[uid]
	s.stateMu.RUnlock()

	if exists && existing.ContentHash == contentHash {
		klog.V(2).Infof("Dashboard %s/%s unchanged (hash: %s), skipping", cm.Namespace, cm.Name, contentHash[:12])
		syncTotal.WithLabelValues("sync", "skipped").Inc()
		return nil
	}

	// Parse dashboard
	var dashboard map[string]interface{}
	if err := json.Unmarshal(dashboardJSON, &dashboard); err != nil {
		syncTotal.WithLabelValues("sync", "invalid_json").Inc()
		return fmt.Errorf("invalid dashboard JSON: %w", err)
	}

	// Set title from annotation if provided
	if name, ok := cm.Annotations[dashboardNameKey]; ok {
		dashboard["title"] = name
	}

	if exists {
		// Update existing dashboard
		if err := s.updateDashboard(ctx, existing.UUID, dashboard); err != nil {
			syncTotal.WithLabelValues("sync", "update_error").Inc()
			return err
		}

		s.stateMu.Lock()
		s.state[uid] = DashboardState{
			UUID:        existing.UUID,
			ContentHash: contentHash,
			Name:        cm.Name,
			Namespace:   cm.Namespace,
			SyncedAt:    time.Now().UTC().Format(time.RFC3339),
		}
		s.stateMu.Unlock()

		syncTotal.WithLabelValues("sync", "updated").Inc()
		klog.Infof("Updated dashboard %s from ConfigMap %s/%s", existing.UUID, cm.Namespace, cm.Name)
	} else {
		// Create new dashboard
		uuid, err := s.createDashboard(ctx, dashboard)
		if err != nil {
			syncTotal.WithLabelValues("sync", "create_error").Inc()
			return err
		}

		s.stateMu.Lock()
		s.state[uid] = DashboardState{
			UUID:        uuid,
			ContentHash: contentHash,
			Name:        cm.Name,
			Namespace:   cm.Namespace,
			SyncedAt:    time.Now().UTC().Format(time.RFC3339),
		}
		s.stateMu.Unlock()

		syncTotal.WithLabelValues("sync", "created").Inc()
		klog.Infof("Created dashboard %s from ConfigMap %s/%s", uuid, cm.Namespace, cm.Name)
	}

	if err := s.saveState(ctx); err != nil {
		klog.Errorf("Failed to save state: %v", err)
	}

	return nil
}

func (s *DashboardSidecar) extractDashboardJSON(cm *corev1.ConfigMap) ([]byte, error) {
	// Priority: dashboard.json key, then any .json key, then single key
	if data, ok := cm.Data["dashboard.json"]; ok {
		return []byte(data), nil
	}

	for key, value := range cm.Data {
		if len(key) > 5 && key[len(key)-5:] == ".json" {
			return []byte(value), nil
		}
	}

	if len(cm.Data) == 1 {
		for _, value := range cm.Data {
			return []byte(value), nil
		}
	}

	return nil, fmt.Errorf("no dashboard JSON found in ConfigMap (expected 'dashboard.json' key or single entry)")
}

func (s *DashboardSidecar) deleteDashboard(ctx context.Context, cm *corev1.ConfigMap) error {
	timer := prometheus.NewTimer(syncDuration.WithLabelValues("delete"))
	defer timer.ObserveDuration()

	uid := string(cm.UID)

	s.stateMu.RLock()
	state, exists := s.state[uid]
	s.stateMu.RUnlock()

	if !exists {
		return nil
	}

	if err := s.deleteDashboardByUUID(ctx, state.UUID); err != nil {
		syncTotal.WithLabelValues("delete", "error").Inc()
		return err
	}

	s.stateMu.Lock()
	delete(s.state, uid)
	s.stateMu.Unlock()

	if err := s.saveState(ctx); err != nil {
		klog.Errorf("Failed to save state after deletion: %v", err)
	}

	syncTotal.WithLabelValues("delete", "success").Inc()
	klog.Infof("Deleted dashboard %s (was from ConfigMap %s/%s)", state.UUID, cm.Namespace, cm.Name)

	return nil
}

// SigNoz API calls

func (s *DashboardSidecar) createDashboard(ctx context.Context, dashboard map[string]interface{}) (string, error) {
	payload, err := json.Marshal(dashboard)
	if err != nil {
		return "", err
	}

	reqURL, err := url.JoinPath(s.config.SignozURL, dashboardPath)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, reqURL, bytes.NewReader(payload))
	if err != nil {
		return "", err
	}

	s.setHeaders(req)

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	if resp.StatusCode >= 400 {
		apiErrors.WithLabelValues("create", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return "", fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	var result dashboardResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return "", err
	}

	if result.Status != "success" {
		apiErrors.WithLabelValues("create", "api_error").Inc()
		return "", fmt.Errorf("API error: %s", result.Error)
	}

	return result.Data.UUID, nil
}

func (s *DashboardSidecar) updateDashboard(ctx context.Context, uuid string, dashboard map[string]interface{}) error {
	payload, err := json.Marshal(dashboard)
	if err != nil {
		return err
	}

	reqURL, err := url.JoinPath(s.config.SignozURL, dashboardPath, uuid)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPut, reqURL, bytes.NewReader(payload))
	if err != nil {
		return err
	}

	s.setHeaders(req)

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		apiErrors.WithLabelValues("update", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	return nil
}

func (s *DashboardSidecar) deleteDashboardByUUID(ctx context.Context, uuid string) error {
	reqURL, err := url.JoinPath(s.config.SignozURL, dashboardPath, uuid)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, reqURL, nil)
	if err != nil {
		return err
	}

	s.setHeaders(req)

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	// 404 is fine - dashboard already gone
	if resp.StatusCode >= 400 && resp.StatusCode != 404 {
		body, _ := io.ReadAll(resp.Body)
		apiErrors.WithLabelValues("delete", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	return nil
}

func (s *DashboardSidecar) setHeaders(req *http.Request) {
	req.Header.Set("Content-Type", "application/json")
	if s.config.SignozAPIKey != "" {
		req.Header.Set("SIGNOZ-API-KEY", s.config.SignozAPIKey)
	}
}

func main() {
	config := SidecarConfig{
		SignozURL:         getEnv("SIGNOZ_URL", "http://localhost:8080"),
		SignozAPIKey:      os.Getenv("SIGNOZ_API_KEY"),
		Namespace:         os.Getenv("WATCH_NAMESPACE"),
		StateNamespace:    getEnv("STATE_NAMESPACE", "signoz"),
		ReconcileInterval: getDurationEnv("RECONCILE_INTERVAL", 5*time.Minute),
		MetricsAddr:       getEnv("METRICS_ADDR", ":9090"),
	}

	klog.Infof("Starting signoz-dashboard-sidecar")
	klog.Infof("  SignozURL: %s", config.SignozURL)
	klog.Infof("  WatchNamespace: %q (empty=all)", config.Namespace)
	klog.Infof("  StateNamespace: %s", config.StateNamespace)
	klog.Infof("  ReconcileInterval: %s", config.ReconcileInterval)
	klog.Infof("  MetricsAddr: %s", config.MetricsAddr)

	sidecar, err := NewDashboardSidecar(config)
	if err != nil {
		klog.Fatalf("Failed to create sidecar: %v", err)
	}

	ctx := context.Background()
	if err := sidecar.Run(ctx); err != nil {
		klog.Fatalf("Sidecar exited: %v", err)
	}
}

func getEnv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func getDurationEnv(key string, fallback time.Duration) time.Duration {
	if value := os.Getenv(key); value != "" {
		if d, err := time.ParseDuration(value); err == nil {
			return d
		}
	}
	return fallback
}
```

**Dockerfile:**

```dockerfile
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /signoz-dashboard-sidecar

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /signoz-dashboard-sidecar /signoz-dashboard-sidecar
ENTRYPOINT ["/signoz-dashboard-sidecar"]
```

**go.mod:**

```
module github.com/yourusername/signoz-dashboard-sidecar

go 1.22

require (
	github.com/prometheus/client_golang v1.19.0
	k8s.io/api v0.29.3
	k8s.io/apimachinery v0.29.3
	k8s.io/client-go v0.29.3
	k8s.io/klog/v2 v2.120.1
)
```

**Helm chart values (for sidecar injection):**

```yaml
# templates/sidecar-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: signoz-dashboard-sidecar
  namespace: {{ .Release.Namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: signoz-dashboard-sidecar
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["signoz-dashboard-sidecar-state"]
    verbs: ["create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: signoz-dashboard-sidecar
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: signoz-dashboard-sidecar
subjects:
  - kind: ServiceAccount
    name: signoz-dashboard-sidecar
    namespace: {{ .Release.Namespace }}
```

**Example ServiceMonitor:**

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: signoz-dashboard-sidecar
  labels:
    app: signoz-dashboard-sidecar
spec:
  selector:
    matchLabels:
      app: signoz-dashboard-sidecar
  endpoints:
    - port: metrics
      interval: 30s
      path: /metrics
```

Key changes from the original:

1. **ConfigMap-based state** - Persists to `signoz-dashboard-sidecar-state` ConfigMap, survives restarts
2. **SHA256 content hash** - Skips API calls when dashboard JSON hasn't changed
3. **Orphan cleanup** - On reconciliation, removes dashboards whose ConfigMaps no longer exist
4. **Prometheus metrics** - Sync counts by operation/status, durations, managed dashboard count, API errors
5. **Health endpoints** - `/healthz` and `/readyz` for k8s probes

Want me to add anything else? Thinking structured logging with slog might be nice, or a dry-run mode for testing.