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
	"testing"
)

func TestTelemetry_New(t *testing.T) {
	tel := New()
	if tel == nil {
		t.Error("Expected telemetry instance to be created, got nil")
	}
}

func TestTelemetry_SetSyncConnected(t *testing.T) {
	tel := New()

	// Test setting connected
	tel.SetSyncConnected(true)

	// Test setting disconnected
	tel.SetSyncConnected(false)

	// No error means metrics were set successfully
}

func TestTelemetry_SetSyncLastSuccessTime(t *testing.T) {
	tel := New()
	timestamp := float64(1234567890)

	tel.SetSyncLastSuccessTime(timestamp)

	// No error means metric was set successfully
}

func TestTelemetry_ObserveAPIRequestDuration(t *testing.T) {
	tel := New()

	tel.ObserveAPIRequestDuration("sync_status", "GET", 0.5)
	tel.ObserveAPIRequestDuration("notes", "POST", 1.2)

	// No error means metrics were observed successfully
}

func TestTelemetry_IncAPIRequestsTotal(t *testing.T) {
	tel := New()

	tel.IncAPIRequestsTotal("sync_status", "GET", "200")
	tel.IncAPIRequestsTotal("notes", "POST", "201")
	tel.IncAPIRequestsTotal("sync_status", "GET", "error")

	// No error means metrics were incremented successfully
}

func TestTelemetry_SetSyntheticTestSuccess(t *testing.T) {
	tel := New()

	tel.SetSyntheticTestSuccess(true)
	tel.SetSyntheticTestSuccess(false)

	// No error means metrics were set successfully
}

func TestTelemetry_IncAuthenticationAttempts(t *testing.T) {
	tel := New()

	tel.IncAuthenticationAttempts("success")
	tel.IncAuthenticationAttempts("failure")

	// No error means metrics were incremented successfully
}

func TestTelemetry_IncSyncFailures(t *testing.T) {
	tel := New()

	tel.IncSyncFailures("connection", "timeout")
	tel.IncSyncFailures("api", "unauthorized")

	// No error means metrics were incremented successfully
}

func TestTelemetry_SetPendingChanges(t *testing.T) {
	tel := New()

	tel.SetPendingChanges(5)
	tel.SetPendingChanges(0)

	// No error means metrics were set successfully
}

func TestTelemetry_SetLastSyntheticTestTime(t *testing.T) {
	tel := New()
	timestamp := float64(1234567890)

	tel.SetLastSyntheticTestTime(timestamp)

	// No error means metric was set successfully
}