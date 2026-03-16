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
	"fmt"

	"github.com/cloudflare/cloudflare-go"
)

// mockCloudflareAPI is a test double for cloudflareAPI. Each method can be overridden
// via its corresponding Func field; unset fields return zero values.
type mockCloudflareAPI struct {
	// Zone
	zoneIDByNameFunc func(zoneName string) (string, error)

	// DNS
	createDNSRecordFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateDNSRecordParams) (cloudflare.DNSRecord, error)
	deleteDNSRecordFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, recordID string) error
	listDNSRecordsFunc  func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error)
	updateDNSRecordFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.UpdateDNSRecordParams) (cloudflare.DNSRecord, error)

	// Tunnels
	createTunnelFunc              func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error)
	getTunnelFunc                 func(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.Tunnel, error)
	listTunnelsFunc               func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelListParams) ([]cloudflare.Tunnel, *cloudflare.ResultInfo, error)
	deleteTunnelFunc              func(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) error
	getTunnelConfigurationFunc    func(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.TunnelConfigurationResult, error)
	updateTunnelConfigurationFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error)
	getTunnelTokenFunc            func(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (string, error)

	// Access Applications
	createAccessApplicationFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error)
	updateAccessApplicationFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error)
	deleteAccessApplicationFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, applicationID string) error
	getAccessApplicationFunc    func(ctx context.Context, rc *cloudflare.ResourceContainer, applicationID string) (cloudflare.AccessApplication, error)

	// Access Policies
	createAccessPolicyFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateAccessPolicyParams) (cloudflare.AccessPolicy, error)
	deleteAccessPolicyFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.DeleteAccessPolicyParams) error
	listAccessPoliciesFunc func(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListAccessPoliciesParams) ([]cloudflare.AccessPolicy, *cloudflare.ResultInfo, error)
}

// Compile-time assertion.
var _ cloudflareAPI = (*mockCloudflareAPI)(nil)

func (m *mockCloudflareAPI) ZoneIDByName(zoneName string) (string, error) {
	if m.zoneIDByNameFunc != nil {
		return m.zoneIDByNameFunc(zoneName)
	}
	return "", fmt.Errorf("ZoneIDByName not configured on mock")
}

func (m *mockCloudflareAPI) CreateDNSRecord(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateDNSRecordParams) (cloudflare.DNSRecord, error) {
	if m.createDNSRecordFunc != nil {
		return m.createDNSRecordFunc(ctx, rc, params)
	}
	return cloudflare.DNSRecord{}, nil
}

func (m *mockCloudflareAPI) DeleteDNSRecord(ctx context.Context, rc *cloudflare.ResourceContainer, recordID string) error {
	if m.deleteDNSRecordFunc != nil {
		return m.deleteDNSRecordFunc(ctx, rc, recordID)
	}
	return nil
}

func (m *mockCloudflareAPI) ListDNSRecords(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListDNSRecordsParams) ([]cloudflare.DNSRecord, *cloudflare.ResultInfo, error) {
	if m.listDNSRecordsFunc != nil {
		return m.listDNSRecordsFunc(ctx, rc, params)
	}
	return nil, &cloudflare.ResultInfo{}, nil
}

func (m *mockCloudflareAPI) UpdateDNSRecord(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.UpdateDNSRecordParams) (cloudflare.DNSRecord, error) {
	if m.updateDNSRecordFunc != nil {
		return m.updateDNSRecordFunc(ctx, rc, params)
	}
	return cloudflare.DNSRecord{}, nil
}

func (m *mockCloudflareAPI) CreateTunnel(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelCreateParams) (cloudflare.Tunnel, error) {
	if m.createTunnelFunc != nil {
		return m.createTunnelFunc(ctx, rc, params)
	}
	return cloudflare.Tunnel{}, nil
}

func (m *mockCloudflareAPI) GetTunnel(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.Tunnel, error) {
	if m.getTunnelFunc != nil {
		return m.getTunnelFunc(ctx, rc, tunnelID)
	}
	return cloudflare.Tunnel{}, nil
}

func (m *mockCloudflareAPI) ListTunnels(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelListParams) ([]cloudflare.Tunnel, *cloudflare.ResultInfo, error) {
	if m.listTunnelsFunc != nil {
		return m.listTunnelsFunc(ctx, rc, params)
	}
	return nil, &cloudflare.ResultInfo{}, nil
}

func (m *mockCloudflareAPI) DeleteTunnel(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) error {
	if m.deleteTunnelFunc != nil {
		return m.deleteTunnelFunc(ctx, rc, tunnelID)
	}
	return nil
}

func (m *mockCloudflareAPI) GetTunnelConfiguration(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (cloudflare.TunnelConfigurationResult, error) {
	if m.getTunnelConfigurationFunc != nil {
		return m.getTunnelConfigurationFunc(ctx, rc, tunnelID)
	}
	return cloudflare.TunnelConfigurationResult{}, nil
}

func (m *mockCloudflareAPI) UpdateTunnelConfiguration(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.TunnelConfigurationParams) (cloudflare.TunnelConfigurationResult, error) {
	if m.updateTunnelConfigurationFunc != nil {
		return m.updateTunnelConfigurationFunc(ctx, rc, params)
	}
	return cloudflare.TunnelConfigurationResult{}, nil
}

func (m *mockCloudflareAPI) GetTunnelToken(ctx context.Context, rc *cloudflare.ResourceContainer, tunnelID string) (string, error) {
	if m.getTunnelTokenFunc != nil {
		return m.getTunnelTokenFunc(ctx, rc, tunnelID)
	}
	return "", nil
}

func (m *mockCloudflareAPI) CreateAccessApplication(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateAccessApplicationParams) (cloudflare.AccessApplication, error) {
	if m.createAccessApplicationFunc != nil {
		return m.createAccessApplicationFunc(ctx, rc, params)
	}
	return cloudflare.AccessApplication{}, nil
}

func (m *mockCloudflareAPI) UpdateAccessApplication(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.UpdateAccessApplicationParams) (cloudflare.AccessApplication, error) {
	if m.updateAccessApplicationFunc != nil {
		return m.updateAccessApplicationFunc(ctx, rc, params)
	}
	return cloudflare.AccessApplication{}, nil
}

func (m *mockCloudflareAPI) DeleteAccessApplication(ctx context.Context, rc *cloudflare.ResourceContainer, applicationID string) error {
	if m.deleteAccessApplicationFunc != nil {
		return m.deleteAccessApplicationFunc(ctx, rc, applicationID)
	}
	return nil
}

func (m *mockCloudflareAPI) GetAccessApplication(ctx context.Context, rc *cloudflare.ResourceContainer, applicationID string) (cloudflare.AccessApplication, error) {
	if m.getAccessApplicationFunc != nil {
		return m.getAccessApplicationFunc(ctx, rc, applicationID)
	}
	return cloudflare.AccessApplication{}, nil
}

func (m *mockCloudflareAPI) CreateAccessPolicy(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.CreateAccessPolicyParams) (cloudflare.AccessPolicy, error) {
	if m.createAccessPolicyFunc != nil {
		return m.createAccessPolicyFunc(ctx, rc, params)
	}
	return cloudflare.AccessPolicy{}, nil
}

func (m *mockCloudflareAPI) DeleteAccessPolicy(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.DeleteAccessPolicyParams) error {
	if m.deleteAccessPolicyFunc != nil {
		return m.deleteAccessPolicyFunc(ctx, rc, params)
	}
	return nil
}

func (m *mockCloudflareAPI) ListAccessPolicies(ctx context.Context, rc *cloudflare.ResourceContainer, params cloudflare.ListAccessPoliciesParams) ([]cloudflare.AccessPolicy, *cloudflare.ResultInfo, error) {
	if m.listAccessPoliciesFunc != nil {
		return m.listAccessPoliciesFunc(ctx, rc, params)
	}
	return nil, &cloudflare.ResultInfo{}, nil
}
