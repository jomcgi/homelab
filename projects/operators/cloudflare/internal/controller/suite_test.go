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

package controller

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/cloudflare/cloudflare-go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/envtest"
	logf "sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	gatewayv1 "sigs.k8s.io/gateway-api/apis/v1"

	tunnelsv1 "github.com/jomcgi/homelab/projects/operators/cloudflare/api/v1"
	cfclient "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/cloudflare"
	// +kubebuilder:scaffold:imports
)

// These tests use Ginkgo (BDD-style Go testing framework). Refer to
// http://onsi.github.io/ginkgo/ to learn more about Ginkgo.

var (
	ctx          context.Context
	cancel       context.CancelFunc
	testEnv      *envtest.Environment
	cfg          *rest.Config
	k8sClient    client.Client
	mockCFClient *MockTunnelClient
)

// MockTunnelClient is a mock implementation of the TunnelClientInterface for testing
type MockTunnelClient struct {
	// Tunnel management
	CreateTunnelFunc              func(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error)
	GetTunnelFunc                 func(ctx context.Context, accountID, tunnelID string) (*cloudflare.Tunnel, error)
	ListTunnelsFunc               func(ctx context.Context, accountID string) ([]cloudflare.Tunnel, error)
	DeleteTunnelFunc              func(ctx context.Context, accountID, tunnelID string) error
	UpdateTunnelConfigurationFunc func(ctx context.Context, accountID, tunnelID string, config cloudflare.TunnelConfiguration) error
	GetTunnelTokenFunc            func(ctx context.Context, accountID, tunnelID string) (string, error)

	// Published application routes
	CreatePublishedRouteFunc func(ctx context.Context, accountID, tunnelID string, route cfclient.RouteConfig) error
	DeletePublishedRouteFunc func(ctx context.Context, accountID, tunnelID, hostname string) error
	ListPublishedRoutesFunc  func(ctx context.Context, accountID, tunnelID string) ([]cfclient.RouteConfig, error)
	GetPublishedRouteFunc    func(ctx context.Context, accountID, tunnelID, hostname string) (*cfclient.RouteConfig, error)

	// DNS management
	CreateTunnelDNSRecordFunc func(ctx context.Context, hostname, tunnelID string) (*cfclient.DNSRecordConfig, error)
	DeleteDNSRecordFunc       func(ctx context.Context, zoneID, recordID string) error
	GetDNSRecordByNameFunc    func(ctx context.Context, hostname string) (*cfclient.DNSRecordConfig, error)
	ListTunnelDNSRecordsFunc  func(ctx context.Context, zoneID, tunnelID string) ([]cfclient.DNSRecordConfig, error)
	UpdateDNSRecordFunc       func(ctx context.Context, config cfclient.DNSRecordConfig) error

	// Zero Trust Access management
	CreateAccessApplicationFunc func(ctx context.Context, accountID string, config cfclient.AccessApplicationConfig) (*cfclient.AccessApplicationConfig, error)
	UpdateAccessApplicationFunc func(ctx context.Context, accountID string, config cfclient.AccessApplicationConfig) error
	DeleteAccessApplicationFunc func(ctx context.Context, accountID, applicationID string) error
	GetAccessApplicationFunc    func(ctx context.Context, accountID, applicationID string) (*cfclient.AccessApplicationConfig, error)
	CreateAccessPolicyFunc      func(ctx context.Context, accountID string, config cfclient.AccessPolicyConfig) (*cfclient.AccessPolicyConfig, error)
	DeleteAccessPolicyFunc      func(ctx context.Context, accountID, applicationID, policyID string) error
	ListAccessPoliciesFunc      func(ctx context.Context, accountID, applicationID string) ([]cfclient.AccessPolicyConfig, error)
}

// Verify that MockTunnelClient implements TunnelClientInterface
var _ cfclient.TunnelClientInterface = (*MockTunnelClient)(nil)

func (m *MockTunnelClient) CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error) {
	if m.CreateTunnelFunc != nil {
		return m.CreateTunnelFunc(ctx, accountID, name)
	}
	return &cloudflare.Tunnel{ID: "mock-tunnel-id", Name: name}, "mock-tunnel-secret", nil
}

func (m *MockTunnelClient) GetTunnel(ctx context.Context, accountID, tunnelID string) (*cloudflare.Tunnel, error) {
	if m.GetTunnelFunc != nil {
		return m.GetTunnelFunc(ctx, accountID, tunnelID)
	}
	return &cloudflare.Tunnel{ID: tunnelID, Name: "mock-tunnel"}, nil
}

func (m *MockTunnelClient) ListTunnels(ctx context.Context, accountID string) ([]cloudflare.Tunnel, error) {
	if m.ListTunnelsFunc != nil {
		return m.ListTunnelsFunc(ctx, accountID)
	}
	return []cloudflare.Tunnel{{ID: "mock-tunnel-id", Name: "mock-tunnel"}}, nil
}

func (m *MockTunnelClient) DeleteTunnel(ctx context.Context, accountID, tunnelID string) error {
	if m.DeleteTunnelFunc != nil {
		return m.DeleteTunnelFunc(ctx, accountID, tunnelID)
	}
	return nil
}

func (m *MockTunnelClient) UpdateTunnelConfiguration(ctx context.Context, accountID, tunnelID string, config cloudflare.TunnelConfiguration) error {
	if m.UpdateTunnelConfigurationFunc != nil {
		return m.UpdateTunnelConfigurationFunc(ctx, accountID, tunnelID, config)
	}
	return nil
}

func (m *MockTunnelClient) GetTunnelToken(ctx context.Context, accountID, tunnelID string) (string, error) {
	if m.GetTunnelTokenFunc != nil {
		return m.GetTunnelTokenFunc(ctx, accountID, tunnelID)
	}
	return "mock-tunnel-token", nil
}

// Published application routes
func (m *MockTunnelClient) CreatePublishedRoute(ctx context.Context, accountID, tunnelID string, route cfclient.RouteConfig) error {
	if m.CreatePublishedRouteFunc != nil {
		return m.CreatePublishedRouteFunc(ctx, accountID, tunnelID, route)
	}
	return nil
}

func (m *MockTunnelClient) DeletePublishedRoute(ctx context.Context, accountID, tunnelID, hostname string) error {
	if m.DeletePublishedRouteFunc != nil {
		return m.DeletePublishedRouteFunc(ctx, accountID, tunnelID, hostname)
	}
	return nil
}

func (m *MockTunnelClient) ListPublishedRoutes(ctx context.Context, accountID, tunnelID string) ([]cfclient.RouteConfig, error) {
	if m.ListPublishedRoutesFunc != nil {
		return m.ListPublishedRoutesFunc(ctx, accountID, tunnelID)
	}
	return []cfclient.RouteConfig{}, nil
}

func (m *MockTunnelClient) GetPublishedRoute(ctx context.Context, accountID, tunnelID, hostname string) (*cfclient.RouteConfig, error) {
	if m.GetPublishedRouteFunc != nil {
		return m.GetPublishedRouteFunc(ctx, accountID, tunnelID, hostname)
	}
	return &cfclient.RouteConfig{}, nil
}

// DNS management
func (m *MockTunnelClient) CreateTunnelDNSRecord(ctx context.Context, hostname, tunnelID string) (*cfclient.DNSRecordConfig, error) {
	if m.CreateTunnelDNSRecordFunc != nil {
		return m.CreateTunnelDNSRecordFunc(ctx, hostname, tunnelID)
	}
	return &cfclient.DNSRecordConfig{}, nil
}

func (m *MockTunnelClient) DeleteDNSRecord(ctx context.Context, zoneID, recordID string) error {
	if m.DeleteDNSRecordFunc != nil {
		return m.DeleteDNSRecordFunc(ctx, zoneID, recordID)
	}
	return nil
}

func (m *MockTunnelClient) GetDNSRecordByName(ctx context.Context, hostname string) (*cfclient.DNSRecordConfig, error) {
	if m.GetDNSRecordByNameFunc != nil {
		return m.GetDNSRecordByNameFunc(ctx, hostname)
	}
	return &cfclient.DNSRecordConfig{}, nil
}

func (m *MockTunnelClient) ListTunnelDNSRecords(ctx context.Context, zoneID, tunnelID string) ([]cfclient.DNSRecordConfig, error) {
	if m.ListTunnelDNSRecordsFunc != nil {
		return m.ListTunnelDNSRecordsFunc(ctx, zoneID, tunnelID)
	}
	return []cfclient.DNSRecordConfig{}, nil
}

func (m *MockTunnelClient) UpdateDNSRecord(ctx context.Context, config cfclient.DNSRecordConfig) error {
	if m.UpdateDNSRecordFunc != nil {
		return m.UpdateDNSRecordFunc(ctx, config)
	}
	return nil
}

// Zero Trust Access management
func (m *MockTunnelClient) CreateAccessApplication(ctx context.Context, accountID string, config cfclient.AccessApplicationConfig) (*cfclient.AccessApplicationConfig, error) {
	if m.CreateAccessApplicationFunc != nil {
		return m.CreateAccessApplicationFunc(ctx, accountID, config)
	}
	return &cfclient.AccessApplicationConfig{ID: "mock-app-id"}, nil
}

func (m *MockTunnelClient) UpdateAccessApplication(ctx context.Context, accountID string, config cfclient.AccessApplicationConfig) error {
	if m.UpdateAccessApplicationFunc != nil {
		return m.UpdateAccessApplicationFunc(ctx, accountID, config)
	}
	return nil
}

func (m *MockTunnelClient) DeleteAccessApplication(ctx context.Context, accountID, applicationID string) error {
	if m.DeleteAccessApplicationFunc != nil {
		return m.DeleteAccessApplicationFunc(ctx, accountID, applicationID)
	}
	return nil
}

func (m *MockTunnelClient) GetAccessApplication(ctx context.Context, accountID, applicationID string) (*cfclient.AccessApplicationConfig, error) {
	if m.GetAccessApplicationFunc != nil {
		return m.GetAccessApplicationFunc(ctx, accountID, applicationID)
	}
	return &cfclient.AccessApplicationConfig{ID: applicationID}, nil
}

func (m *MockTunnelClient) CreateAccessPolicy(ctx context.Context, accountID string, config cfclient.AccessPolicyConfig) (*cfclient.AccessPolicyConfig, error) {
	if m.CreateAccessPolicyFunc != nil {
		return m.CreateAccessPolicyFunc(ctx, accountID, config)
	}
	return &cfclient.AccessPolicyConfig{ID: "mock-policy-id"}, nil
}

func (m *MockTunnelClient) DeleteAccessPolicy(ctx context.Context, accountID, applicationID, policyID string) error {
	if m.DeleteAccessPolicyFunc != nil {
		return m.DeleteAccessPolicyFunc(ctx, accountID, applicationID, policyID)
	}
	return nil
}

func (m *MockTunnelClient) ListAccessPolicies(ctx context.Context, accountID, applicationID string) ([]cfclient.AccessPolicyConfig, error) {
	if m.ListAccessPoliciesFunc != nil {
		return m.ListAccessPoliciesFunc(ctx, accountID, applicationID)
	}
	return []cfclient.AccessPolicyConfig{}, nil
}

func TestControllers(t *testing.T) {
	RegisterFailHandler(Fail)

	RunSpecs(t, "Controller Suite")
}

var _ = BeforeSuite(func() {
	logf.SetLogger(zap.New(zap.WriteTo(GinkgoWriter), zap.UseDevMode(true)))

	ctx, cancel = context.WithCancel(context.TODO())

	// Initialize mock client
	mockCFClient = &MockTunnelClient{}

	var err error
	err = tunnelsv1.AddToScheme(scheme.Scheme)
	Expect(err).NotTo(HaveOccurred())

	err = gatewayv1.Install(scheme.Scheme)
	Expect(err).NotTo(HaveOccurred())

	// +kubebuilder:scaffold:scheme

	By("bootstrapping test environment")
	testEnv = &envtest.Environment{
		CRDDirectoryPaths:     []string{filepath.Join("..", "..", "config", "crd", "bases")},
		ErrorIfCRDPathMissing: true,
	}

	// Retrieve the first found binary directory to allow running tests from IDEs
	if getFirstFoundEnvTestBinaryDir() != "" {
		testEnv.BinaryAssetsDirectory = getFirstFoundEnvTestBinaryDir()
	}

	// cfg is defined in this file globally.
	cfg, err = testEnv.Start()
	Expect(err).NotTo(HaveOccurred())
	Expect(cfg).NotTo(BeNil())

	k8sClient, err = client.New(cfg, client.Options{Scheme: scheme.Scheme})
	Expect(err).NotTo(HaveOccurred())
	Expect(k8sClient).NotTo(BeNil())
})

var _ = AfterSuite(func() {
	By("tearing down the test environment")
	cancel()
	err := testEnv.Stop()
	Expect(err).NotTo(HaveOccurred())
})

// getFirstFoundEnvTestBinaryDir locates the first binary in the specified path.
// ENVTEST-based tests depend on specific binaries, usually located in paths set by
// controller-runtime. When running tests directly (e.g., via an IDE) without using
// Makefile targets, the 'BinaryAssetsDirectory' must be explicitly configured.
//
// This function streamlines the process by finding the required binaries, similar to
// setting the 'KUBEBUILDER_ASSETS' environment variable. To ensure the binaries are
// properly set up, run 'make setup-envtest' beforehand.
func getFirstFoundEnvTestBinaryDir() string {
	basePath := filepath.Join("..", "..", "bin", "k8s")
	entries, err := os.ReadDir(basePath)
	if err != nil {
		logf.Log.Error(err, "Failed to read directory", "path", basePath)
		return ""
	}
	for _, entry := range entries {
		if entry.IsDir() {
			return filepath.Join(basePath, entry.Name())
		}
	}
	return ""
}
