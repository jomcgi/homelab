/*
Copyright 2025.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package telemetry

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Telemetry holds all metric collectors for the sync monitor
type Telemetry struct {
	syncConnected           prometheus.Gauge
	syncLastSuccessTime     prometheus.Gauge
	apiRequestDuration      prometheus.HistogramVec
	apiRequestsTotal        prometheus.CounterVec
	syntheticTestSuccess    prometheus.Gauge
	authenticationAttempts  prometheus.CounterVec
	syncFailuresTotal       prometheus.CounterVec
	pendingChanges          prometheus.Gauge
	lastSyntheticTestTime   prometheus.Gauge
}

// New creates a new Telemetry instance with initialized metrics
func New() *Telemetry {
	return &Telemetry{
		syncConnected: promauto.NewGauge(prometheus.GaugeOpts{
			Name: "obsidian_sync_connected",
			Help: "1 if Obsidian Sync is connected, 0 if disconnected",
		}),
		syncLastSuccessTime: promauto.NewGauge(prometheus.GaugeOpts{
			Name: "obsidian_sync_last_success_timestamp",
			Help: "Unix timestamp of the last successful sync operation",
		}),
		apiRequestDuration: *promauto.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "obsidian_api_request_duration_seconds",
			Help:    "Duration of Obsidian API requests in seconds",
			Buckets: prometheus.DefBuckets,
		}, []string{"endpoint", "method"}),
		apiRequestsTotal: *promauto.NewCounterVec(prometheus.CounterOpts{
			Name: "obsidian_api_requests_total",
			Help: "Total number of Obsidian API requests by endpoint and status",
		}, []string{"endpoint", "method", "status"}),
		syntheticTestSuccess: promauto.NewGauge(prometheus.GaugeOpts{
			Name: "obsidian_synthetic_test_success",
			Help: "1 if the last synthetic test passed, 0 if it failed",
		}),
		authenticationAttempts: *promauto.NewCounterVec(prometheus.CounterOpts{
			Name: "obsidian_authentication_attempts_total",
			Help: "Total number of authentication attempts by result",
		}, []string{"result"}),
		syncFailuresTotal: *promauto.NewCounterVec(prometheus.CounterOpts{
			Name: "obsidian_sync_failures_total",
			Help: "Total number of sync failures by type",
		}, []string{"type", "reason"}),
		pendingChanges: promauto.NewGauge(prometheus.GaugeOpts{
			Name: "obsidian_pending_changes",
			Help: "Number of pending changes waiting to be synced",
		}),
		lastSyntheticTestTime: promauto.NewGauge(prometheus.GaugeOpts{
			Name: "obsidian_last_synthetic_test_timestamp",
			Help: "Unix timestamp of the last synthetic test execution",
		}),
	}
}

// SetSyncConnected updates the sync connection status metric
func (t *Telemetry) SetSyncConnected(connected bool) {
	if connected {
		t.syncConnected.Set(1)
	} else {
		t.syncConnected.Set(0)
	}
}

// SetSyncLastSuccessTime updates the last successful sync timestamp
func (t *Telemetry) SetSyncLastSuccessTime(timestamp float64) {
	t.syncLastSuccessTime.Set(timestamp)
}

// ObserveAPIRequestDuration records the duration of an API request
func (t *Telemetry) ObserveAPIRequestDuration(endpoint, method string, duration float64) {
	t.apiRequestDuration.WithLabelValues(endpoint, method).Observe(duration)
}

// IncAPIRequestsTotal increments the API requests counter
func (t *Telemetry) IncAPIRequestsTotal(endpoint, method, status string) {
	t.apiRequestsTotal.WithLabelValues(endpoint, method, status).Inc()
}

// SetSyntheticTestSuccess updates the synthetic test success metric
func (t *Telemetry) SetSyntheticTestSuccess(success bool) {
	if success {
		t.syntheticTestSuccess.Set(1)
	} else {
		t.syntheticTestSuccess.Set(0)
	}
}

// IncAuthenticationAttempts increments the authentication attempts counter
func (t *Telemetry) IncAuthenticationAttempts(result string) {
	t.authenticationAttempts.WithLabelValues(result).Inc()
}

// IncSyncFailures increments the sync failures counter
func (t *Telemetry) IncSyncFailures(failureType, reason string) {
	t.syncFailuresTotal.WithLabelValues(failureType, reason).Inc()
}

// SetPendingChanges updates the pending changes metric
func (t *Telemetry) SetPendingChanges(count float64) {
	t.pendingChanges.Set(count)
}

// SetLastSyntheticTestTime updates the last synthetic test timestamp
func (t *Telemetry) SetLastSyntheticTestTime(timestamp float64) {
	t.lastSyntheticTestTime.Set(timestamp)
}