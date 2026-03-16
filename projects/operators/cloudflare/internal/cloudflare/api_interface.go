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

package cloudflare

import (
	"context"

	"github.com/cloudflare/cloudflare-go"
)

// cloudflareAPI defines the subset of cloudflare.API methods used by TunnelClient.
// This interface enables dependency injection and unit testing without hitting the
// real Cloudflare API.
type cloudflareAPI interface {
	// Zone
	ZoneIDByName(zoneName string) (string, error)

	// DNS
	CreateDNSRecord(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateDNSRecordParams) (cloudflare.DNSRecord, error)
	DeleteDNSRecord(ctx context.Context, rc *cloudflare.ResourceContainer, recordID string) error
	ListDNSRecords(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error)
	UpdateDNSRecord(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.UpdateDNSRecordParams) (cloudflare.DNSRecord, error)

	// Tunnels
	CreateTunnel(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error)
	GetTunnel(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.Tunnel, error)
	ListTunnels(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelListParams) ([]cloudflare.Tunnel, *cloudflare.ResultInfo, error)
	DeleteTunnel(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) error
	GetTunnelConfiguration(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.TunnelConfigurationResult, error)
	UpdateTunnelConfiguration(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error)
	GetTunnelToken(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (string, error)

	// Access Applications
	CreateAccessApplication(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error)
	UpdateAccessApplication(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error)
	DeleteAccessApplication(ctx context.Context, rc *cloudflare.ResourceContainer, applicationID string) error
	GetAccessApplication(ctx context.Context, rc *cloudflare.ResourceContainer, applicationID string) (cloudflare.AccessApplication, error)

	// Access Policies
	CreateAccessPolicy(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateAccessPolicyParams) (cloudflare.AccessPolicy, error)
	DeleteAccessPolicy(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.DeleteAccessPolicyParams) error
	ListAccessPolicies(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListAccessPoliciesParams) ([]cloudflare.AccessPolicy, *cloudflare.ResultInfo, error)
}

// Ensure *cloudflare.API satisfies cloudflareAPI.
var _ cloudflareAPI = (*cloudflare.API)(nil)
