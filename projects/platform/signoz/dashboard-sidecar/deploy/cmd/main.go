// Package main implements a GitOps sidecar for syncing SigNoz resources from ConfigMaps.
// It watches ConfigMaps with specific labels and syncs their JSON content to SigNoz:
//   - signoz.io/dashboard=true -> Dashboards (api/v1/dashboards)
//   - signoz.io/alert=true -> Alerts (api/v1/rules)
//   - signoz.io/channel=true -> Notification channels (api/v1/channels)
//
// Periodic reconciliation enforces desired state by always pushing ConfigMap content,
// ensuring manual changes in the SigNoz UI are reverted (drift correction).
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
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
)

const (
	dashboardLabel   = "signoz.io/dashboard"
	dashboardNameKey = "signoz.io/dashboard-name"
	dashboardTagsKey = "signoz.io/dashboard-tags"
	dashboardPath    = "api/v1/dashboards"

	// Alert constants
	alertLabel       = "signoz.io/alert"
	alertNameKey     = "signoz.io/alert-name"
	alertSeverityKey = "signoz.io/severity"
	alertChannelsKey = "signoz.io/notification-channels"
	alertPath        = "api/v1/rules"

	// Notification channel constants
	channelLabel   = "signoz.io/channel"
	channelNameKey = "signoz.io/channel-name"
	channelTypeKey = "signoz.io/channel-type"
	channelPath    = "api/v1/channels"
	secretRefKey   = "signoz.io/secret-ref" // Format: "namespace/secretName" or just "secretName" (same namespace)

	// Default tag applied to all sidecar-managed dashboards
	defaultManagedTag = "iac-managed"

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

	driftCorrections = promauto.NewCounter(prometheus.CounterOpts{
		Name: "signoz_dashboard_sidecar_drift_corrections_total",
		Help: "Total number of drift corrections (forced updates during reconciliation)",
	})

	// Alert metrics
	alertSyncTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "signoz_dashboard_sidecar_alert_sync_total",
		Help: "Total number of alert sync operations",
	}, []string{"operation", "status"})

	alertSyncDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "signoz_dashboard_sidecar_alert_sync_duration_seconds",
		Help:    "Duration of alert sync operations",
		Buckets: prometheus.DefBuckets,
	}, []string{"operation"})

	alertsManaged = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "signoz_dashboard_sidecar_alerts_managed",
		Help: "Current number of alerts managed by the sidecar",
	})

	alertConfigMapsWatched = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "signoz_dashboard_sidecar_alert_configmaps_watched",
		Help: "Current number of alert ConfigMaps being watched",
	})

	alertDriftCorrections = promauto.NewCounter(prometheus.CounterOpts{
		Name: "signoz_dashboard_sidecar_alert_drift_corrections_total",
		Help: "Total number of alert drift corrections (forced updates during reconciliation)",
	})

	// Channel metrics
	channelSyncTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "signoz_dashboard_sidecar_channel_sync_total",
		Help: "Total number of notification channel sync operations",
	}, []string{"operation", "status"})

	channelSyncDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "signoz_dashboard_sidecar_channel_sync_duration_seconds",
		Help:    "Duration of notification channel sync operations",
		Buckets: prometheus.DefBuckets,
	}, []string{"operation"})

	channelsManaged = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "signoz_dashboard_sidecar_channels_managed",
		Help: "Current number of notification channels managed by the sidecar",
	})

	channelConfigMapsWatched = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "signoz_dashboard_sidecar_channel_configmaps_watched",
		Help: "Current number of channel ConfigMaps being watched",
	})

	channelDriftCorrections = promauto.NewCounter(prometheus.CounterOpts{
		Name: "signoz_dashboard_sidecar_channel_drift_corrections_total",
		Help: "Total number of channel drift corrections (forced updates during reconciliation)",
	})
)

// Config holds the sidecar configuration.
type Config struct {
	SignozURL         string
	SignozAPIKey      string
	Namespace         string // empty = all namespaces
	StateNamespace    string // namespace for state ConfigMap
	ReconcileInterval time.Duration
	MetricsAddr       string
}

// DashboardState tracks a synced dashboard.
type DashboardState struct {
	UUID        string `json:"uuid"`
	ContentHash string `json:"contentHash"`
	Name        string `json:"name"`
	Namespace   string `json:"namespace"`
	SyncedAt    string `json:"syncedAt"`
}

// AlertState tracks a synced alert.
type AlertState struct {
	ID          string `json:"id"` // SigNoz returns "id" not "uuid" for alerts
	ContentHash string `json:"contentHash"`
	Name        string `json:"name"`
	Namespace   string `json:"namespace"`
	SyncedAt    string `json:"syncedAt"`
}

// StateStore maps ConfigMap UID -> DashboardState.
type StateStore map[string]DashboardState

// AlertStateStore maps ConfigMap UID -> AlertState.
type AlertStateStore map[string]AlertState

// ChannelState tracks a synced notification channel.
type ChannelState struct {
	ID          string `json:"id"`
	ContentHash string `json:"contentHash"`
	Name        string `json:"name"`
	Namespace   string `json:"namespace"`
	SyncedAt    string `json:"syncedAt"`
}

// ChannelStateStore maps ConfigMap UID -> ChannelState.
type ChannelStateStore map[string]ChannelState

// Sidecar manages dashboard, alert, and channel synchronization.
type Sidecar struct {
	config     Config
	clientset  *kubernetes.Clientset
	httpClient *http.Client
	logger     *slog.Logger

	stateMu      sync.RWMutex
	state        StateStore
	alertState   AlertStateStore
	channelState ChannelStateStore
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

type alertResponse struct {
	Status string    `json:"status"`
	Data   alertData `json:"data"`
	Error  string    `json:"error,omitempty"`
}

type alertData struct {
	ID string `json:"id"`
}

// NewSidecar creates a new dashboard sidecar.
func NewSidecar(config Config, logger *slog.Logger) (*Sidecar, error) {
	k8sConfig, err := rest.InClusterConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to get in-cluster config: %w", err)
	}

	clientset, err := kubernetes.NewForConfig(k8sConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create clientset: %w", err)
	}

	return &Sidecar{
		config:       config,
		clientset:    clientset,
		httpClient:   &http.Client{Timeout: 30 * time.Second},
		logger:       logger,
		state:        make(StateStore),
		alertState:   make(AlertStateStore),
		channelState: make(ChannelStateStore),
	}, nil
}

// Run starts the sidecar main loop.
func (s *Sidecar) Run(ctx context.Context) error {
	// Start metrics server
	go s.serveMetrics()

	// Load persisted state
	if err := s.loadState(ctx); err != nil {
		s.logger.Warn("Failed to load state (starting fresh)", "error", err)
	}

	// Initial sync (with drift correction)
	if err := s.reconcileAll(ctx); err != nil {
		s.logger.Error("Initial reconciliation failed", "error", err)
	}

	// Start watching for changes
	go s.watchConfigMaps(ctx)
	go s.watchAlertConfigMaps(ctx)
	go s.watchChannelConfigMaps(ctx)

	// Periodic reconciliation with drift correction
	ticker := time.NewTicker(s.config.ReconcileInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			s.logger.Info("Shutting down...")
			return ctx.Err()
		case <-ticker.C:
			if err := s.reconcileAll(ctx); err != nil {
				s.logger.Error("Periodic reconciliation failed", "error", err)
			}
		}
	}
}

func (s *Sidecar) serveMetrics() {
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	s.logger.Info("Starting metrics server", "addr", s.config.MetricsAddr)
	if err := http.ListenAndServe(s.config.MetricsAddr, mux); err != nil {
		s.logger.Error("Metrics server failed", "error", err)
		os.Exit(1)
	}
}

// State persistence

func (s *Sidecar) loadState(ctx context.Context) error {
	cm, err := s.clientset.CoreV1().ConfigMaps(s.config.StateNamespace).Get(ctx, stateConfigMapName, metav1.GetOptions{})
	if err != nil {
		if errors.IsNotFound(err) {
			s.logger.Info("No existing state ConfigMap found, starting fresh")
			return nil
		}
		return fmt.Errorf("failed to get state ConfigMap: %w", err)
	}

	s.stateMu.Lock()
	defer s.stateMu.Unlock()

	// Load dashboard state
	if stateJSON, ok := cm.Data["state"]; ok {
		if err := json.Unmarshal([]byte(stateJSON), &s.state); err != nil {
			return fmt.Errorf("failed to unmarshal dashboard state: %w", err)
		}
	}

	// Load alert state
	if alertStateJSON, ok := cm.Data["alertState"]; ok {
		if err := json.Unmarshal([]byte(alertStateJSON), &s.alertState); err != nil {
			return fmt.Errorf("failed to unmarshal alert state: %w", err)
		}
	}

	// Load channel state
	if channelStateJSON, ok := cm.Data["channelState"]; ok {
		if err := json.Unmarshal([]byte(channelStateJSON), &s.channelState); err != nil {
			return fmt.Errorf("failed to unmarshal channel state: %w", err)
		}
	}

	dashboardsManaged.Set(float64(len(s.state)))
	alertsManaged.Set(float64(len(s.alertState)))
	channelsManaged.Set(float64(len(s.channelState)))
	s.logger.Info("Loaded state", "dashboards", len(s.state), "alerts", len(s.alertState), "channels", len(s.channelState))

	return nil
}

func (s *Sidecar) saveState(ctx context.Context) error {
	s.stateMu.RLock()
	stateJSON, err := json.Marshal(s.state)
	if err != nil {
		s.stateMu.RUnlock()
		return fmt.Errorf("failed to marshal dashboard state: %w", err)
	}
	alertStateJSON, err := json.Marshal(s.alertState)
	if err != nil {
		s.stateMu.RUnlock()
		return fmt.Errorf("failed to marshal alert state: %w", err)
	}
	channelStateJSON, err := json.Marshal(s.channelState)
	if err != nil {
		s.stateMu.RUnlock()
		return fmt.Errorf("failed to marshal channel state: %w", err)
	}
	s.stateMu.RUnlock()

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      stateConfigMapName,
			Namespace: s.config.StateNamespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":      "signoz-sidecar",
				"app.kubernetes.io/component": "state",
			},
		},
		Data: map[string]string{
			"state":        string(stateJSON),
			"alertState":   string(alertStateJSON),
			"channelState": string(channelStateJSON),
		},
	}

	existingCM, getErr := s.clientset.CoreV1().ConfigMaps(s.config.StateNamespace).Get(ctx, stateConfigMapName, metav1.GetOptions{})
	if errors.IsNotFound(getErr) {
		_, err = s.clientset.CoreV1().ConfigMaps(s.config.StateNamespace).Create(ctx, cm, metav1.CreateOptions{})
	} else if getErr == nil {
		// Preserve the current resourceVersion to satisfy Kubernetes optimistic concurrency
		cm.ResourceVersion = existingCM.ResourceVersion
		_, err = s.clientset.CoreV1().ConfigMaps(s.config.StateNamespace).Update(ctx, cm, metav1.UpdateOptions{})
	} else {
		err = getErr
	}

	if err != nil {
		return fmt.Errorf("failed to save state ConfigMap: %w", err)
	}

	s.stateMu.RLock()
	dashboardsManaged.Set(float64(len(s.state)))
	alertsManaged.Set(float64(len(s.alertState)))
	channelsManaged.Set(float64(len(s.channelState)))
	s.stateMu.RUnlock()

	return nil
}

// Content hashing

func hashContent(content []byte) string {
	hash := sha256.Sum256(content)
	return hex.EncodeToString(hash[:])
}

// computeConfigHash computes a hash that includes both the dashboard JSON content
// and the relevant annotations (title, tags). This ensures that annotation-only
// changes are detected and trigger immediate sync on watch events.
func computeConfigHash(jsonContent []byte, annotations map[string]string) string {
	h := sha256.New()
	h.Write(jsonContent)
	// Include relevant annotations in deterministic order
	h.Write([]byte(annotations[dashboardNameKey]))
	h.Write([]byte(annotations[dashboardTagsKey]))
	return hex.EncodeToString(h.Sum(nil))
}

// mergeTags combines existing dashboard tags with default and annotation-provided tags.
// It ensures no duplicates and always includes the defaultManagedTag.
func mergeTags(existingTags []interface{}, annotationTags string) []string {
	tagSet := make(map[string]bool)
	result := []string{}

	// Add existing tags from dashboard JSON
	for _, t := range existingTags {
		if tag, ok := t.(string); ok && tag != "" {
			if !tagSet[tag] {
				tagSet[tag] = true
				result = append(result, tag)
			}
		}
	}

	// Add default managed tag
	if !tagSet[defaultManagedTag] {
		tagSet[defaultManagedTag] = true
		result = append(result, defaultManagedTag)
	}

	// Add tags from annotation (comma-separated)
	if annotationTags != "" {
		for _, tag := range strings.Split(annotationTags, ",") {
			tag = strings.TrimSpace(tag)
			if tag != "" && !tagSet[tag] {
				tagSet[tag] = true
				result = append(result, tag)
			}
		}
	}

	return result
}

// Watch and reconcile

func (s *Sidecar) watchConfigMaps(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		listOpts := metav1.ListOptions{
			LabelSelector: fmt.Sprintf("%s=true", dashboardLabel),
		}

		var watcher watch.Interface
		var err error

		if s.config.Namespace == "" {
			watcher, err = s.clientset.CoreV1().ConfigMaps("").Watch(ctx, listOpts)
		} else {
			watcher, err = s.clientset.CoreV1().ConfigMaps(s.config.Namespace).Watch(ctx, listOpts)
		}

		if err != nil {
			s.logger.Error("Failed to start watch", "error", err)
			time.Sleep(5 * time.Second)
			continue
		}

		s.handleWatchEvents(ctx, watcher)
		watcher.Stop()
	}
}

func (s *Sidecar) handleWatchEvents(ctx context.Context, watcher watch.Interface) {
	for {
		select {
		case <-ctx.Done():
			return
		case event, ok := <-watcher.ResultChan():
			if !ok {
				s.logger.Info("Watch channel closed, restarting...")
				return
			}

			cm, ok := event.Object.(*corev1.ConfigMap)
			if !ok {
				continue
			}

			switch event.Type {
			case watch.Added, watch.Modified:
				// For watch events, use hash check to avoid unnecessary updates
				if err := s.syncDashboard(ctx, cm, false); err != nil {
					s.logger.Error("Failed to sync dashboard", "namespace", cm.Namespace, "name", cm.Name, "error", err)
				}
			case watch.Deleted:
				if err := s.deleteDashboard(ctx, cm); err != nil {
					s.logger.Error("Failed to delete dashboard", "namespace", cm.Namespace, "name", cm.Name, "error", err)
				}
			}
		}
	}
}

func (s *Sidecar) reconcileAll(ctx context.Context) error {
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
	s.logger.Info("Reconciling dashboard ConfigMaps (with drift correction)", "count", len(configMaps.Items))

	// Track which ConfigMap UIDs we've seen
	seenUIDs := make(map[string]bool)

	for i := range configMaps.Items {
		cm := &configMaps.Items[i]
		seenUIDs[string(cm.UID)] = true

		// During reconciliation, force update to correct any drift
		if err := s.syncDashboard(ctx, cm, true); err != nil {
			s.logger.Error("Failed to sync", "namespace", cm.Namespace, "name", cm.Name, "error", err)
		}
	}

	// Clean up orphaned dashboards (ConfigMap was deleted while sidecar was down)
	// First, collect orphaned entries under lock to keep the critical section small.
	type orphanedDashboard struct {
		uid       string
		uuid      string
		namespace string
		name      string
	}

	var orphaned []orphanedDashboard

	s.stateMu.Lock()
	for uid, state := range s.state {
		if !seenUIDs[uid] {
			orphaned = append(orphaned, orphanedDashboard{
				uid:       uid,
				uuid:      state.UUID,
				namespace: state.Namespace,
				name:      state.Name,
			})
		}
	}
	s.stateMu.Unlock()

	// Perform external deletions without holding the state mutex.
	for _, od := range orphaned {
		s.logger.Info("Cleaning up orphaned dashboard",
			"uuid", od.uuid, "namespace", od.namespace, "name", od.name)

		if err := s.deleteDashboardByUUID(ctx, od.uuid); err != nil {
			s.logger.Error("Failed to delete orphaned dashboard", "uuid", od.uuid, "error", err)
			continue
		}

		// On successful deletion, remove from state with a short lock.
		s.stateMu.Lock()
		delete(s.state, od.uid)
		s.stateMu.Unlock()
	}

	// Reconcile alerts
	if err := s.reconcileAlerts(ctx); err != nil {
		s.logger.Error("Alert reconciliation failed", "error", err)
	}

	// Reconcile channels
	if err := s.reconcileChannels(ctx); err != nil {
		s.logger.Error("Channel reconciliation failed", "error", err)
	}

	if err := s.saveState(ctx); err != nil {
		s.logger.Error("Failed to save state after reconciliation", "error", err)
	}

	lastReconcileTime.SetToCurrentTime()
	syncTotal.WithLabelValues("reconcile_all", "success").Inc()

	return nil
}

// syncDashboard syncs a ConfigMap to SigNoz.
// If forceUpdate is true, it always PUTs to SigNoz (drift correction).
// If forceUpdate is false, it only updates if the ConfigMap content has changed.
func (s *Sidecar) syncDashboard(ctx context.Context, cm *corev1.ConfigMap, forceUpdate bool) error {
	timer := prometheus.NewTimer(syncDuration.WithLabelValues("sync"))
	defer timer.ObserveDuration()

	// Extract dashboard JSON
	dashboardJSON, err := s.extractDashboardJSON(cm)
	if err != nil {
		syncTotal.WithLabelValues("sync", "invalid_config").Inc()
		return err
	}

	// Hash includes both JSON content and relevant annotations (title, tags)
	// so annotation-only changes are detected and trigger immediate sync
	contentHash := computeConfigHash(dashboardJSON, cm.Annotations)
	uid := string(cm.UID)

	// Check if content has changed (only skip if not forcing update)
	s.stateMu.RLock()
	existing, exists := s.state[uid]
	s.stateMu.RUnlock()

	if !forceUpdate && exists && existing.ContentHash == contentHash {
		s.logger.Debug("Dashboard unchanged, skipping", "namespace", cm.Namespace, "name", cm.Name, "hash", contentHash[:12])
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

	// Merge tags: existing + "iac-managed" + annotation-provided tags
	var existingTags []interface{}
	if tags, ok := dashboard["tags"].([]interface{}); ok {
		existingTags = tags
	}
	annotationTags := cm.Annotations[dashboardTagsKey]
	dashboard["tags"] = mergeTags(existingTags, annotationTags)

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

		if forceUpdate && existing.ContentHash == contentHash {
			driftCorrections.Inc()
			s.logger.Debug("Drift correction: re-applied dashboard", "uuid", existing.UUID, "namespace", cm.Namespace, "name", cm.Name)
			syncTotal.WithLabelValues("sync", "drift_corrected").Inc()
		} else {
			syncTotal.WithLabelValues("sync", "updated").Inc()
			s.logger.Info("Updated dashboard", "uuid", existing.UUID, "namespace", cm.Namespace, "name", cm.Name)
		}
	} else {
		// Create new dashboard
		dashboardUUID, err := s.createDashboard(ctx, dashboard)
		if err != nil {
			syncTotal.WithLabelValues("sync", "create_error").Inc()
			return err
		}

		s.stateMu.Lock()
		s.state[uid] = DashboardState{
			UUID:        dashboardUUID,
			ContentHash: contentHash,
			Name:        cm.Name,
			Namespace:   cm.Namespace,
			SyncedAt:    time.Now().UTC().Format(time.RFC3339),
		}
		s.stateMu.Unlock()

		syncTotal.WithLabelValues("sync", "created").Inc()
		s.logger.Info("Created dashboard", "uuid", dashboardUUID, "namespace", cm.Namespace, "name", cm.Name)
	}

	if err := s.saveState(ctx); err != nil {
		s.logger.Error("Failed to save state", "error", err)
	}

	return nil
}

func (s *Sidecar) extractDashboardJSON(cm *corev1.ConfigMap) ([]byte, error) {
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

func (s *Sidecar) deleteDashboard(ctx context.Context, cm *corev1.ConfigMap) error {
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
		s.logger.Error("Failed to save state after deletion", "error", err)
	}

	syncTotal.WithLabelValues("delete", "success").Inc()
	s.logger.Info("Deleted dashboard", "uuid", state.UUID, "namespace", cm.Namespace, "name", cm.Name)

	return nil
}

// SigNoz API calls

func (s *Sidecar) createDashboard(ctx context.Context, dashboard map[string]interface{}) (string, error) {
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

func (s *Sidecar) updateDashboard(ctx context.Context, uuid string, dashboard map[string]interface{}) error {
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

func (s *Sidecar) deleteDashboardByUUID(ctx context.Context, uuid string) error {
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

func (s *Sidecar) setHeaders(req *http.Request) {
	req.Header.Set("Content-Type", "application/json")
	if s.config.SignozAPIKey != "" {
		req.Header.Set("SIGNOZ-API-KEY", s.config.SignozAPIKey)
	}
}

// ============================================================================
// Alert sync methods
// ============================================================================

func (s *Sidecar) watchAlertConfigMaps(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		listOpts := metav1.ListOptions{
			LabelSelector: fmt.Sprintf("%s=true", alertLabel),
		}

		var watcher watch.Interface
		var err error

		if s.config.Namespace == "" {
			watcher, err = s.clientset.CoreV1().ConfigMaps("").Watch(ctx, listOpts)
		} else {
			watcher, err = s.clientset.CoreV1().ConfigMaps(s.config.Namespace).Watch(ctx, listOpts)
		}

		if err != nil {
			s.logger.Error("Failed to start alert watch", "error", err)
			time.Sleep(5 * time.Second)
			continue
		}

		s.handleAlertWatchEvents(ctx, watcher)
		watcher.Stop()
	}
}

func (s *Sidecar) handleAlertWatchEvents(ctx context.Context, watcher watch.Interface) {
	for {
		select {
		case <-ctx.Done():
			return
		case event, ok := <-watcher.ResultChan():
			if !ok {
				s.logger.Info("Alert watch channel closed, restarting...")
				return
			}

			cm, ok := event.Object.(*corev1.ConfigMap)
			if !ok {
				continue
			}

			switch event.Type {
			case watch.Added, watch.Modified:
				if err := s.syncAlert(ctx, cm, false); err != nil {
					s.logger.Error("Failed to sync alert", "namespace", cm.Namespace, "name", cm.Name, "error", err)
				}
			case watch.Deleted:
				if err := s.deleteAlert(ctx, cm); err != nil {
					s.logger.Error("Failed to delete alert", "namespace", cm.Namespace, "name", cm.Name, "error", err)
				}
			}
		}
	}
}

func (s *Sidecar) reconcileAlerts(ctx context.Context) error {
	timer := prometheus.NewTimer(alertSyncDuration.WithLabelValues("reconcile_all"))
	defer timer.ObserveDuration()

	listOpts := metav1.ListOptions{
		LabelSelector: fmt.Sprintf("%s=true", alertLabel),
	}

	var configMaps *corev1.ConfigMapList
	var err error

	if s.config.Namespace == "" {
		configMaps, err = s.clientset.CoreV1().ConfigMaps("").List(ctx, listOpts)
	} else {
		configMaps, err = s.clientset.CoreV1().ConfigMaps(s.config.Namespace).List(ctx, listOpts)
	}

	if err != nil {
		alertSyncTotal.WithLabelValues("reconcile_all", "error").Inc()
		return fmt.Errorf("failed to list alert configmaps: %w", err)
	}

	alertConfigMapsWatched.Set(float64(len(configMaps.Items)))
	s.logger.Info("Reconciling alert ConfigMaps", "count", len(configMaps.Items))

	seenUIDs := make(map[string]bool)

	for i := range configMaps.Items {
		cm := &configMaps.Items[i]
		seenUIDs[string(cm.UID)] = true

		if err := s.syncAlert(ctx, cm, true); err != nil {
			s.logger.Error("Failed to sync alert", "namespace", cm.Namespace, "name", cm.Name, "error", err)
		}
	}

	// Clean up orphaned alerts
	var orphaned []struct {
		uid, id, namespace, name string
	}

	s.stateMu.Lock()
	for uid, state := range s.alertState {
		if !seenUIDs[uid] {
			orphaned = append(orphaned, struct{ uid, id, namespace, name string }{uid, state.ID, state.Namespace, state.Name})
		}
	}
	s.stateMu.Unlock()

	for _, od := range orphaned {
		s.logger.Info("Cleaning up orphaned alert", "id", od.id, "namespace", od.namespace, "name", od.name)
		if err := s.deleteAlertByID(ctx, od.id); err != nil {
			s.logger.Error("Failed to delete orphaned alert", "id", od.id, "error", err)
			continue
		}
		s.stateMu.Lock()
		delete(s.alertState, od.uid)
		s.stateMu.Unlock()
	}

	alertSyncTotal.WithLabelValues("reconcile_all", "success").Inc()
	return nil
}

func (s *Sidecar) syncAlert(ctx context.Context, cm *corev1.ConfigMap, forceUpdate bool) error {
	timer := prometheus.NewTimer(alertSyncDuration.WithLabelValues("sync"))
	defer timer.ObserveDuration()

	alertJSON, err := s.extractAlertJSON(cm)
	if err != nil {
		alertSyncTotal.WithLabelValues("sync", "invalid_config").Inc()
		return err
	}

	contentHash := hashContent(alertJSON)
	uid := string(cm.UID)

	s.stateMu.RLock()
	existing, exists := s.alertState[uid]
	s.stateMu.RUnlock()

	if !forceUpdate && exists && existing.ContentHash == contentHash {
		s.logger.Debug("Alert unchanged, skipping", "namespace", cm.Namespace, "name", cm.Name)
		alertSyncTotal.WithLabelValues("sync", "skipped").Inc()
		return nil
	}

	var alert map[string]interface{}
	if err := json.Unmarshal(alertJSON, &alert); err != nil {
		alertSyncTotal.WithLabelValues("sync", "invalid_json").Inc()
		return fmt.Errorf("invalid alert JSON: %w", err)
	}

	// Override from annotations if provided
	if name, ok := cm.Annotations[alertNameKey]; ok {
		alert["alert"] = name
	}
	if severity, ok := cm.Annotations[alertSeverityKey]; ok {
		alert["severity"] = severity
	}
	if channels, ok := cm.Annotations[alertChannelsKey]; ok {
		channelList := strings.Split(channels, ",")
		for i := range channelList {
			channelList[i] = strings.TrimSpace(channelList[i])
		}
		alert["preferredChannels"] = channelList
	}

	if exists {
		if err := s.updateAlert(ctx, existing.ID, alert); err != nil {
			// If rule was deleted from SigNoz (e.g. after fresh install),
			// clear stale state and fall through to create below.
			if strings.Contains(err.Error(), "status 404") {
				s.logger.Info("Alert not found in SigNoz, recreating",
					"id", existing.ID, "namespace", cm.Namespace, "name", cm.Name)
				exists = false
			} else {
				alertSyncTotal.WithLabelValues("sync", "update_error").Inc()
				return err
			}
		}
	}

	if exists {
		s.stateMu.Lock()
		s.alertState[uid] = AlertState{
			ID:          existing.ID,
			ContentHash: contentHash,
			Name:        cm.Name,
			Namespace:   cm.Namespace,
			SyncedAt:    time.Now().UTC().Format(time.RFC3339),
		}
		s.stateMu.Unlock()

		if forceUpdate && existing.ContentHash == contentHash {
			alertDriftCorrections.Inc()
			alertSyncTotal.WithLabelValues("sync", "drift_corrected").Inc()
		} else {
			alertSyncTotal.WithLabelValues("sync", "updated").Inc()
			s.logger.Info("Updated alert", "id", existing.ID, "namespace", cm.Namespace, "name", cm.Name)
		}
	} else {
		alertID, err := s.createAlert(ctx, alert)
		if err != nil {
			alertSyncTotal.WithLabelValues("sync", "create_error").Inc()
			return err
		}

		s.stateMu.Lock()
		s.alertState[uid] = AlertState{
			ID:          alertID,
			ContentHash: contentHash,
			Name:        cm.Name,
			Namespace:   cm.Namespace,
			SyncedAt:    time.Now().UTC().Format(time.RFC3339),
		}
		s.stateMu.Unlock()

		alertSyncTotal.WithLabelValues("sync", "created").Inc()
		s.logger.Info("Created alert", "id", alertID, "namespace", cm.Namespace, "name", cm.Name)
	}

	return nil
}

func (s *Sidecar) extractAlertJSON(cm *corev1.ConfigMap) ([]byte, error) {
	if data, ok := cm.Data["alert.json"]; ok {
		return []byte(data), nil
	}
	for key, value := range cm.Data {
		if strings.HasSuffix(key, ".json") {
			return []byte(value), nil
		}
	}
	if len(cm.Data) == 1 {
		for _, value := range cm.Data {
			return []byte(value), nil
		}
	}
	return nil, fmt.Errorf("no alert JSON found in ConfigMap (expected 'alert.json' key)")
}

func (s *Sidecar) deleteAlert(ctx context.Context, cm *corev1.ConfigMap) error {
	timer := prometheus.NewTimer(alertSyncDuration.WithLabelValues("delete"))
	defer timer.ObserveDuration()

	uid := string(cm.UID)

	s.stateMu.RLock()
	state, exists := s.alertState[uid]
	s.stateMu.RUnlock()

	if !exists {
		return nil
	}

	if err := s.deleteAlertByID(ctx, state.ID); err != nil {
		alertSyncTotal.WithLabelValues("delete", "error").Inc()
		return err
	}

	s.stateMu.Lock()
	delete(s.alertState, uid)
	s.stateMu.Unlock()

	alertSyncTotal.WithLabelValues("delete", "success").Inc()
	s.logger.Info("Deleted alert", "id", state.ID, "namespace", cm.Namespace, "name", cm.Name)

	return nil
}

// Alert API calls

func (s *Sidecar) createAlert(ctx context.Context, alert map[string]interface{}) (string, error) {
	payload, err := json.Marshal(alert)
	if err != nil {
		return "", err
	}

	reqURL, err := url.JoinPath(s.config.SignozURL, alertPath)
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
		apiErrors.WithLabelValues("alert_create", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return "", fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	var result alertResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return "", err
	}

	if result.Status != "success" {
		apiErrors.WithLabelValues("alert_create", "api_error").Inc()
		return "", fmt.Errorf("API error: %s", result.Error)
	}

	return result.Data.ID, nil
}

func (s *Sidecar) updateAlert(ctx context.Context, id string, alert map[string]interface{}) error {
	payload, err := json.Marshal(alert)
	if err != nil {
		return err
	}

	reqURL, err := url.JoinPath(s.config.SignozURL, alertPath, id)
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
		apiErrors.WithLabelValues("alert_update", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	return nil
}

func (s *Sidecar) deleteAlertByID(ctx context.Context, id string) error {
	reqURL, err := url.JoinPath(s.config.SignozURL, alertPath, id)
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

	if resp.StatusCode >= 400 && resp.StatusCode != 404 {
		body, _ := io.ReadAll(resp.Body)
		apiErrors.WithLabelValues("alert_delete", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ============================================================================
// Channel sync methods
// ============================================================================

type channelResponse struct {
	Status string      `json:"status"`
	Data   channelData `json:"data"`
	Error  string      `json:"error,omitempty"`
}

type channelData struct {
	ID string `json:"id"`
}

func (s *Sidecar) watchChannelConfigMaps(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		listOpts := metav1.ListOptions{
			LabelSelector: fmt.Sprintf("%s=true", channelLabel),
		}

		var watcher watch.Interface
		var err error

		if s.config.Namespace == "" {
			watcher, err = s.clientset.CoreV1().ConfigMaps("").Watch(ctx, listOpts)
		} else {
			watcher, err = s.clientset.CoreV1().ConfigMaps(s.config.Namespace).Watch(ctx, listOpts)
		}

		if err != nil {
			s.logger.Error("Failed to start channel watch", "error", err)
			time.Sleep(5 * time.Second)
			continue
		}

		s.handleChannelWatchEvents(ctx, watcher)
		watcher.Stop()
	}
}

func (s *Sidecar) handleChannelWatchEvents(ctx context.Context, watcher watch.Interface) {
	for {
		select {
		case <-ctx.Done():
			return
		case event, ok := <-watcher.ResultChan():
			if !ok {
				s.logger.Info("Channel watch channel closed, restarting...")
				return
			}

			cm, ok := event.Object.(*corev1.ConfigMap)
			if !ok {
				continue
			}

			switch event.Type {
			case watch.Added, watch.Modified:
				if err := s.syncChannel(ctx, cm, false); err != nil {
					s.logger.Error("Failed to sync channel", "namespace", cm.Namespace, "name", cm.Name, "error", err)
				}
			case watch.Deleted:
				if err := s.deleteChannel(ctx, cm); err != nil {
					s.logger.Error("Failed to delete channel", "namespace", cm.Namespace, "name", cm.Name, "error", err)
				}
			}
		}
	}
}

func (s *Sidecar) reconcileChannels(ctx context.Context) error {
	timer := prometheus.NewTimer(channelSyncDuration.WithLabelValues("reconcile_all"))
	defer timer.ObserveDuration()

	listOpts := metav1.ListOptions{
		LabelSelector: fmt.Sprintf("%s=true", channelLabel),
	}

	var configMaps *corev1.ConfigMapList
	var err error

	if s.config.Namespace == "" {
		configMaps, err = s.clientset.CoreV1().ConfigMaps("").List(ctx, listOpts)
	} else {
		configMaps, err = s.clientset.CoreV1().ConfigMaps(s.config.Namespace).List(ctx, listOpts)
	}

	if err != nil {
		channelSyncTotal.WithLabelValues("reconcile_all", "error").Inc()
		return fmt.Errorf("failed to list channel configmaps: %w", err)
	}

	channelConfigMapsWatched.Set(float64(len(configMaps.Items)))
	s.logger.Info("Reconciling channel ConfigMaps", "count", len(configMaps.Items))

	seenUIDs := make(map[string]bool)

	for i := range configMaps.Items {
		cm := &configMaps.Items[i]
		seenUIDs[string(cm.UID)] = true

		if err := s.syncChannel(ctx, cm, true); err != nil {
			s.logger.Error("Failed to sync channel", "namespace", cm.Namespace, "name", cm.Name, "error", err)
		}
	}

	// Clean up orphaned channels
	var orphaned []struct {
		uid, id, namespace, name string
	}

	s.stateMu.Lock()
	for uid, state := range s.channelState {
		if !seenUIDs[uid] {
			orphaned = append(orphaned, struct{ uid, id, namespace, name string }{uid, state.ID, state.Namespace, state.Name})
		}
	}
	s.stateMu.Unlock()

	for _, od := range orphaned {
		s.logger.Info("Cleaning up orphaned channel", "id", od.id, "namespace", od.namespace, "name", od.name)
		if err := s.deleteChannelByID(ctx, od.id); err != nil {
			s.logger.Error("Failed to delete orphaned channel", "id", od.id, "error", err)
			continue
		}
		s.stateMu.Lock()
		delete(s.channelState, od.uid)
		s.stateMu.Unlock()
	}

	channelSyncTotal.WithLabelValues("reconcile_all", "success").Inc()
	return nil
}

func (s *Sidecar) syncChannel(ctx context.Context, cm *corev1.ConfigMap, forceUpdate bool) error {
	timer := prometheus.NewTimer(channelSyncDuration.WithLabelValues("sync"))
	defer timer.ObserveDuration()

	channelJSON, err := s.extractChannelJSON(cm)
	if err != nil {
		channelSyncTotal.WithLabelValues("sync", "invalid_config").Inc()
		return err
	}

	// Substitute secret values if secretRef annotation is present
	if secretRef, ok := cm.Annotations[secretRefKey]; ok {
		channelJSON, err = s.substituteSecrets(ctx, channelJSON, secretRef, cm.Namespace)
		if err != nil {
			channelSyncTotal.WithLabelValues("sync", "secret_error").Inc()
			return fmt.Errorf("failed to substitute secrets: %w", err)
		}
	}

	contentHash := hashContent(channelJSON)
	uid := string(cm.UID)

	s.stateMu.RLock()
	existing, exists := s.channelState[uid]
	s.stateMu.RUnlock()

	if !forceUpdate && exists && existing.ContentHash == contentHash {
		s.logger.Debug("Channel unchanged, skipping", "namespace", cm.Namespace, "name", cm.Name)
		channelSyncTotal.WithLabelValues("sync", "skipped").Inc()
		return nil
	}

	var channel map[string]interface{}
	if err := json.Unmarshal(channelJSON, &channel); err != nil {
		channelSyncTotal.WithLabelValues("sync", "invalid_json").Inc()
		return fmt.Errorf("invalid channel JSON: %w", err)
	}

	// Override name from annotation if provided
	if name, ok := cm.Annotations[channelNameKey]; ok {
		channel["name"] = name
	}

	if exists {
		if err := s.updateChannel(ctx, existing.ID, channel); err != nil {
			channelSyncTotal.WithLabelValues("sync", "update_error").Inc()
			return err
		}

		s.stateMu.Lock()
		s.channelState[uid] = ChannelState{
			ID:          existing.ID,
			ContentHash: contentHash,
			Name:        cm.Name,
			Namespace:   cm.Namespace,
			SyncedAt:    time.Now().UTC().Format(time.RFC3339),
		}
		s.stateMu.Unlock()

		if forceUpdate && existing.ContentHash == contentHash {
			channelDriftCorrections.Inc()
			channelSyncTotal.WithLabelValues("sync", "drift_corrected").Inc()
		} else {
			channelSyncTotal.WithLabelValues("sync", "updated").Inc()
			s.logger.Info("Updated channel", "id", existing.ID, "namespace", cm.Namespace, "name", cm.Name)
		}
	} else {
		channelID, err := s.createChannel(ctx, channel)
		if err != nil {
			channelSyncTotal.WithLabelValues("sync", "create_error").Inc()
			return err
		}

		s.stateMu.Lock()
		s.channelState[uid] = ChannelState{
			ID:          channelID,
			ContentHash: contentHash,
			Name:        cm.Name,
			Namespace:   cm.Namespace,
			SyncedAt:    time.Now().UTC().Format(time.RFC3339),
		}
		s.stateMu.Unlock()

		channelSyncTotal.WithLabelValues("sync", "created").Inc()
		s.logger.Info("Created channel", "id", channelID, "namespace", cm.Namespace, "name", cm.Name)
	}

	return nil
}

func (s *Sidecar) extractChannelJSON(cm *corev1.ConfigMap) ([]byte, error) {
	if data, ok := cm.Data["channel.json"]; ok {
		return []byte(data), nil
	}
	for key, value := range cm.Data {
		if strings.HasSuffix(key, ".json") {
			return []byte(value), nil
		}
	}
	if len(cm.Data) == 1 {
		for _, value := range cm.Data {
			return []byte(value), nil
		}
	}
	return nil, fmt.Errorf("no channel JSON found in ConfigMap (expected 'channel.json' key)")
}

func (s *Sidecar) deleteChannel(ctx context.Context, cm *corev1.ConfigMap) error {
	timer := prometheus.NewTimer(channelSyncDuration.WithLabelValues("delete"))
	defer timer.ObserveDuration()

	uid := string(cm.UID)

	s.stateMu.RLock()
	state, exists := s.channelState[uid]
	s.stateMu.RUnlock()

	if !exists {
		return nil
	}

	if err := s.deleteChannelByID(ctx, state.ID); err != nil {
		channelSyncTotal.WithLabelValues("delete", "error").Inc()
		return err
	}

	s.stateMu.Lock()
	delete(s.channelState, uid)
	s.stateMu.Unlock()

	channelSyncTotal.WithLabelValues("delete", "success").Inc()
	s.logger.Info("Deleted channel", "id", state.ID, "namespace", cm.Namespace, "name", cm.Name)

	return nil
}

// Channel API calls

func (s *Sidecar) createChannel(ctx context.Context, channel map[string]interface{}) (string, error) {
	payload, err := json.Marshal(channel)
	if err != nil {
		return "", err
	}

	reqURL, err := url.JoinPath(s.config.SignozURL, channelPath)
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
		apiErrors.WithLabelValues("channel_create", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return "", fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	var result channelResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return "", err
	}

	if result.Status != "success" {
		apiErrors.WithLabelValues("channel_create", "api_error").Inc()
		return "", fmt.Errorf("API error: %s", result.Error)
	}

	return result.Data.ID, nil
}

func (s *Sidecar) updateChannel(ctx context.Context, id string, channel map[string]interface{}) error {
	payload, err := json.Marshal(channel)
	if err != nil {
		return err
	}

	reqURL, err := url.JoinPath(s.config.SignozURL, channelPath, id)
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
		apiErrors.WithLabelValues("channel_update", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	return nil
}

func (s *Sidecar) deleteChannelByID(ctx context.Context, id string) error {
	reqURL, err := url.JoinPath(s.config.SignozURL, channelPath, id)
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

	if resp.StatusCode >= 400 && resp.StatusCode != 404 {
		body, _ := io.ReadAll(resp.Body)
		apiErrors.WithLabelValues("channel_delete", fmt.Sprintf("%d", resp.StatusCode)).Inc()
		return fmt.Errorf("API error (status %d): %s", resp.StatusCode, string(body))
	}

	return nil
}

// ============================================================================
// Helper functions
// ============================================================================

// substituteSecrets reads a Kubernetes secret and replaces ${KEY} placeholders in the JSON.
// secretRef format: "secretName" (same namespace as ConfigMap) or "namespace/secretName"
func (s *Sidecar) substituteSecrets(ctx context.Context, jsonData []byte, secretRef, defaultNamespace string) ([]byte, error) {
	// Parse secretRef
	namespace := defaultNamespace
	secretName := secretRef
	if parts := strings.SplitN(secretRef, "/", 2); len(parts) == 2 {
		namespace = parts[0]
		secretName = parts[1]
	}

	// Fetch the secret
	secret, err := s.clientset.CoreV1().Secrets(namespace).Get(ctx, secretName, metav1.GetOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to get secret %s/%s: %w", namespace, secretName, err)
	}

	// Replace ${KEY} patterns with secret values
	result := string(jsonData)
	for key, value := range secret.Data {
		placeholder := fmt.Sprintf("${%s}", key)
		result = strings.ReplaceAll(result, placeholder, string(value))
	}

	s.logger.Debug("Substituted secrets", "secret", secretRef, "keys", len(secret.Data))
	return []byte(result), nil
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

func main() {
	// Setup structured logging
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))

	config := Config{
		SignozURL:         getEnv("SIGNOZ_URL", "http://signoz-query-service:8080"),
		SignozAPIKey:      os.Getenv("SIGNOZ_API_KEY"),
		Namespace:         os.Getenv("WATCH_NAMESPACE"),
		StateNamespace:    getEnv("STATE_NAMESPACE", "signoz"),
		ReconcileInterval: getDurationEnv("RECONCILE_INTERVAL", 5*time.Minute),
		MetricsAddr:       getEnv("METRICS_ADDR", ":9090"),
	}

	logger.Info("Starting signoz-dashboard-sidecar",
		"signoz_url", config.SignozURL,
		"watch_namespace", config.Namespace,
		"state_namespace", config.StateNamespace,
		"reconcile_interval", config.ReconcileInterval,
		"metrics_addr", config.MetricsAddr,
	)

	sidecar, err := NewSidecar(config, logger)
	if err != nil {
		logger.Error("Failed to create sidecar", "error", err)
		os.Exit(1)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	if err := sidecar.Run(ctx); err != nil && err != context.Canceled {
		logger.Error("Sidecar exited", "error", err)
		os.Exit(1)
	}
}
