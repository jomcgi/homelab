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
	"testing"
	"time"

	"go.uber.org/zap"

	"github.com/jomcgi/homelab/charts/obsidian-automation/monitor/internal/telemetry"
)

func TestMonitor_New(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tel := telemetry.New()

	config := Config{
		ObsidianAPIURL:    "http://localhost:27124",
		APIKey:            "test-key",
		CheckInterval:     5 * time.Minute,
		SyntheticInterval: 5 * time.Minute,
		Logger:            logger,
		Telemetry:         tel,
	}

	monitor := New(config)

	if monitor == nil {
		t.Error("Expected monitor to be created, got nil")
	}

	if monitor.config.ObsidianAPIURL != config.ObsidianAPIURL {
		t.Errorf("Expected ObsidianAPIURL %s, got %s", config.ObsidianAPIURL, monitor.config.ObsidianAPIURL)
	}

	if monitor.IsHealthy() {
		t.Error("Expected monitor to start as unhealthy")
	}

	if monitor.IsReady() {
		t.Error("Expected monitor to start as not ready")
	}
}

func TestMonitor_HealthStatus(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tel := telemetry.New()

	config := Config{
		ObsidianAPIURL:    "http://localhost:27124",
		APIKey:            "test-key",
		CheckInterval:     5 * time.Minute,
		SyntheticInterval: 5 * time.Minute,
		Logger:            logger,
		Telemetry:         tel,
	}

	monitor := New(config)

	// Initially unhealthy
	if monitor.IsHealthy() {
		t.Error("Expected monitor to start as unhealthy")
	}

	// Test setting health status
	monitor.mu.Lock()
	monitor.healthy = true
	monitor.ready = true
	monitor.mu.Unlock()

	if !monitor.IsHealthy() {
		t.Error("Expected monitor to be healthy after setting status")
	}

	if !monitor.IsReady() {
		t.Error("Expected monitor to be ready after setting status")
	}
}

func TestMonitor_StopWithoutStart(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	tel := telemetry.New()

	config := Config{
		ObsidianAPIURL:    "http://localhost:27124",
		APIKey:            "test-key",
		CheckInterval:     5 * time.Minute,
		SyntheticInterval: 5 * time.Minute,
		Logger:            logger,
		Telemetry:         tel,
	}

	monitor := New(config)

	// Should be able to stop without starting
	monitor.Stop()
}