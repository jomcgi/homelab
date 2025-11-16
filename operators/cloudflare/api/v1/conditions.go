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

package v1

// Condition types for CloudflareTunnel status
const (
	// TypeReady indicates that the tunnel is ready for use
	TypeReady = "Ready"
	// TypeProgressing indicates that the tunnel is being created or updated
	TypeProgressing = "Progressing"
	// TypeDegraded indicates that the tunnel has issues
	TypeDegraded = "Degraded"
	// TypeActive indicates that the tunnel is live in Cloudflare
	TypeActive = "Active"
	// TypeInactive indicates that the tunnel exists but is not connected
	TypeInactive = "Inactive"
)

// Common condition reasons
const (
	// ReasonCreating indicates the tunnel is being created
	ReasonCreating = "Creating"
	// ReasonUpdating indicates the tunnel is being updated
	ReasonUpdating = "Updating"
	// ReasonDeleting indicates the tunnel is being deleted
	ReasonDeleting = "Deleting"
	// ReasonTunnelConnected indicates the tunnel has active connections
	ReasonTunnelConnected = "TunnelConnected"
	// ReasonTunnelDisconnected indicates the tunnel has no connections
	ReasonTunnelDisconnected = "TunnelDisconnected"
	// ReasonAPIError indicates an error with the Cloudflare API
	ReasonAPIError = "APIError"
	// ReasonInvalidSpec indicates the tunnel spec is invalid
	ReasonInvalidSpec = "InvalidSpec"
	// ReasonTargetNotFound indicates the policy target resource was not found
	ReasonTargetNotFound = "TargetNotFound"
	// ReasonTargetInvalid indicates the policy target is invalid
	ReasonTargetInvalid = "TargetInvalid"
	// ReasonPolicyApplied indicates the access policy was successfully applied
	ReasonPolicyApplied = "PolicyApplied"
	// ReasonPolicyFailed indicates the access policy application failed
	ReasonPolicyFailed = "PolicyFailed"
)
