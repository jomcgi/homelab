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

package monitor

import (
	"context"
	"fmt"
	"sync"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.uber.org/zap"

	"github.com/jomcgi/homelab/charts/obsidian-automation/monitor/internal/client"
	"github.com/jomcgi/homelab/charts/obsidian-automation/monitor/internal/telemetry"
)

// Monitor coordinates sync status monitoring and synthetic testing
type Monitor struct {
	config       Config
	client       *client.ObsidianClient
	logger       *zap.Logger
	telemetry    *telemetry.Telemetry

	mu           sync.RWMutex
	healthy      bool
	ready        bool
	lastCheck    time.Time
	failureCount int

	stopCh       chan struct{}
	wg           sync.WaitGroup
}

// Config holds configuration for the Monitor
type Config struct {
	ObsidianAPIURL    string
	APIKey            string
	CheckInterval     time.Duration
	SyntheticInterval time.Duration
	Logger            *zap.Logger
	Telemetry         *telemetry.Telemetry
}

// New creates a new Monitor instance
func New(config Config) *Monitor {
	return &Monitor{
		config:    config,
		client:    client.NewObsidianClient(config.ObsidianAPIURL, config.APIKey),
		logger:    config.Logger,
		telemetry: config.Telemetry,
		healthy:   false,
		ready:     false,
		stopCh:    make(chan struct{}),
	}
}

// Start begins monitoring sync status and running synthetic tests
func (m *Monitor) Start(ctx context.Context) error {
	m.logger.Info("Starting sync monitor",
		zap.String("obsidian_url", m.config.ObsidianAPIURL),
		zap.Duration("check_interval", m.config.CheckInterval),
		zap.Duration("synthetic_interval", m.config.SyntheticInterval),
	)

	// Initial health check
	if err := m.performHealthCheck(ctx); err != nil {
		m.logger.Error("Initial health check failed", zap.Error(err))
		return fmt.Errorf("initial health check failed: %w", err)
	}

	// Start monitoring goroutines
	m.wg.Add(3)
	go m.syncStatusLoop(ctx)
	go m.syntheticTestLoop(ctx)
	go m.healthCheckLoop(ctx)

	// Wait for context cancellation or stop signal
	select {
	case <-ctx.Done():
		m.logger.Info("Context cancelled, stopping monitor")
	case <-m.stopCh:
		m.logger.Info("Stop signal received")
	}

	// Stop all goroutines
	close(m.stopCh)
	m.wg.Wait()

	return nil
}

// Stop gracefully stops the monitor
func (m *Monitor) Stop() {
	select {
	case <-m.stopCh:
		// Already stopped
	default:
		close(m.stopCh)
	}
	m.wg.Wait()
}

// IsHealthy returns the current health status
func (m *Monitor) IsHealthy() bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.healthy
}

// IsReady returns the current readiness status
func (m *Monitor) IsReady() bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.ready
}

// syncStatusLoop periodically checks sync status
func (m *Monitor) syncStatusLoop(ctx context.Context) {
	defer m.wg.Done()

	ticker := time.NewTicker(m.config.CheckInterval)
	defer ticker.Stop()

	// Run immediately on start
	m.checkSyncStatus(ctx)

	for {
		select {
		case <-ctx.Done():
			return
		case <-m.stopCh:
			return
		case <-ticker.C:
			m.checkSyncStatus(ctx)
		}
	}
}

// syntheticTestLoop periodically runs synthetic tests
func (m *Monitor) syntheticTestLoop(ctx context.Context) {
	defer m.wg.Done()

	ticker := time.NewTicker(m.config.SyntheticInterval)
	defer ticker.Stop()

	// Run immediately after a short delay
	time.Sleep(30 * time.Second)
	m.runSyntheticTest(ctx)

	for {
		select {
		case <-ctx.Done():
			return
		case <-m.stopCh:
			return
		case <-ticker.C:
			m.runSyntheticTest(ctx)
		}
	}
}

// healthCheckLoop periodically performs health checks
func (m *Monitor) healthCheckLoop(ctx context.Context) {
	defer m.wg.Done()

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-m.stopCh:
			return
		case <-ticker.C:
			m.performHealthCheck(ctx)
		}
	}
}

// checkSyncStatus checks the current sync status and updates metrics
func (m *Monitor) checkSyncStatus(ctx context.Context) {
	tracer := otel.Tracer("sync-monitor")
	ctx, span := tracer.Start(ctx, "check_sync_status")
	defer span.End()

	startTime := time.Now()

	status, err := m.client.GetSyncStatus(ctx)
	duration := time.Since(startTime).Seconds()

	// Record API metrics
	endpoint := "sync_status"
	method := "GET"
	statusCode := "200"
	if err != nil {
		statusCode = "error"
		m.logger.Error("Failed to check sync status", zap.Error(err))
		span.RecordError(err)

		m.mu.Lock()
		m.failureCount++
		m.mu.Unlock()

		m.telemetry.IncSyncFailures("status_check", err.Error())
	} else {
		m.logger.Debug("Sync status checked successfully",
			zap.Bool("connected", status.Connected),
			zap.Int("pending_changes", status.PendingChanges),
			zap.Int("failed_files", len(status.FailedFiles)),
		)

		m.mu.Lock()
		m.failureCount = 0
		m.lastCheck = time.Now()
		m.mu.Unlock()

		// Update metrics
		m.telemetry.SetSyncConnected(status.Connected)
		m.telemetry.SetPendingChanges(float64(status.PendingChanges))

		if status.Connected {
			m.telemetry.SetSyncLastSuccessTime(float64(time.Now().Unix()))
		}

		span.SetAttributes(
			attribute.Bool("sync.connected", status.Connected),
			attribute.Int("sync.pending_changes", status.PendingChanges),
			attribute.Int("sync.failed_files_count", len(status.FailedFiles)),
		)
	}

	m.telemetry.ObserveAPIRequestDuration(endpoint, method, duration)
	m.telemetry.IncAPIRequestsTotal(endpoint, method, statusCode)
}

// runSyntheticTest performs end-to-end sync verification
func (m *Monitor) runSyntheticTest(ctx context.Context) {
	tracer := otel.Tracer("sync-monitor")
	ctx, span := tracer.Start(ctx, "synthetic_test")
	defer span.End()

	startTime := time.Now()
	testNote := &client.Note{
		Path:    fmt.Sprintf("_monitor_test_%d.md", time.Now().Unix()),
		Content: fmt.Sprintf("# Synthetic Test\n\nThis is a test note created at %s for sync verification.\n", time.Now().Format(time.RFC3339)),
		Tags:    []string{"monitor", "test"},
	}

	success := true

	defer func() {
		// Record test result
		m.telemetry.SetSyntheticTestSuccess(success)
		m.telemetry.SetLastSyntheticTestTime(float64(startTime.Unix()))

		if success {
			m.logger.Debug("Synthetic test passed")
		} else {
			m.logger.Warn("Synthetic test failed")
		}

		span.SetAttributes(attribute.Bool("test.success", success))
	}()

	// Step 1: Create test note
	if err := m.client.CreateNote(ctx, testNote); err != nil {
		m.logger.Error("Failed to create synthetic test note", zap.Error(err))
		success = false
		span.RecordError(err)
		return
	}

	// Step 2: Wait for sync to process
	time.Sleep(10 * time.Second)

	// Step 3: Verify sync status
	status, err := m.client.VerifySync(ctx)
	if err != nil {
		m.logger.Error("Failed to verify sync during synthetic test", zap.Error(err))
		success = false
		span.RecordError(err)
	} else if !status.Connected {
		m.logger.Error("Sync is not connected during synthetic test")
		success = false
	}

	// Step 4: Clean up test note (always attempt cleanup)
	cleanupCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := m.client.DeleteNote(cleanupCtx, testNote.Path); err != nil {
		m.logger.Warn("Failed to clean up synthetic test note",
			zap.String("path", testNote.Path),
			zap.Error(err),
		)
		// Don't mark test as failed for cleanup issues
	}
}

// performHealthCheck checks API health and updates readiness status
func (m *Monitor) performHealthCheck(ctx context.Context) error {
	healthy := m.client.IsHealthy(ctx)

	m.mu.Lock()
	m.healthy = healthy

	// Mark as ready if healthy and we haven't had too many recent failures
	m.ready = healthy && m.failureCount < 3

	// If we've been failing for too long, mark as unhealthy
	if !m.lastCheck.IsZero() && time.Since(m.lastCheck) > 15*time.Minute {
		m.healthy = false
		m.ready = false
	}
	m.mu.Unlock()

	if healthy {
		m.logger.Debug("Health check passed")
	} else {
		m.logger.Warn("Health check failed")
		return fmt.Errorf("health check failed")
	}

	return nil
}