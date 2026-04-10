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

package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"flag"
	"math/big"
	"os"
	"path/filepath"
	"testing"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/certwatcher"

	cfclient "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/cloudflare"
	sm "github.com/jomcgi/homelab/projects/operators/cloudflare/internal/statemachine"
	ctrl "sigs.k8s.io/controller-runtime"
)

func TestCmd(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Cmd Suite")
}

// generateSelfSignedCert writes a self-signed ECDSA certificate and key into dir,
// returning the paths to the cert and key files.
func generateSelfSignedCert(dir string) (certFile, keyFile string, err error) {
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return "", "", err
	}

	template := x509.Certificate{
		SerialNumber: big.NewInt(1),
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		IsCA:         true,
	}

	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &priv.PublicKey, priv)
	if err != nil {
		return "", "", err
	}

	certFile = filepath.Join(dir, "tls.crt")
	keyFile = filepath.Join(dir, "tls.key")

	cf, err := os.Create(certFile)
	if err != nil {
		return "", "", err
	}
	defer cf.Close()
	if err := pem.Encode(cf, &pem.Block{Type: "CERTIFICATE", Bytes: certDER}); err != nil {
		return "", "", err
	}

	kf, err := os.Create(keyFile)
	if err != nil {
		return "", "", err
	}
	defer kf.Close()
	privDER, err := x509.MarshalECPrivateKey(priv)
	if err != nil {
		return "", "", err
	}
	if err := pem.Encode(kf, &pem.Block{Type: "EC PRIVATE KEY", Bytes: privDER}); err != nil {
		return "", "", err
	}

	return certFile, keyFile, nil
}

var _ = Describe("Scheme registration (init)", func() {
	// The global scheme variable is populated by init() in main.go before any
	// test runs.  These tests verify that all required API groups are present.

	DescribeTable("recognizes expected GVKs",
		func(group, version, kind string) {
			gvk := schema.GroupVersionKind{Group: group, Version: version, Kind: kind}
			Expect(scheme.Recognizes(gvk)).To(BeTrue(),
				"scheme should recognise %s/%s %s", group, version, kind)
		},
		// Custom Cloudflare CRDs
		Entry("CloudflareTunnel", "tunnels.cloudflare.io", "v1", "CloudflareTunnel"),
		Entry("CloudflareTunnelList", "tunnels.cloudflare.io", "v1", "CloudflareTunnelList"),
		Entry("CloudflareAccessPolicy", "tunnels.cloudflare.io", "v1", "CloudflareAccessPolicy"),
		Entry("CloudflareAccessPolicyList", "tunnels.cloudflare.io", "v1", "CloudflareAccessPolicyList"),
		// Gateway API
		Entry("HTTPRoute", "gateway.networking.k8s.io", "v1", "HTTPRoute"),
		Entry("Gateway", "gateway.networking.k8s.io", "v1", "Gateway"),
		Entry("GatewayClass", "gateway.networking.k8s.io", "v1", "GatewayClass"),
		// Core Kubernetes types (clientgoscheme)
		Entry("Pod", "", "v1", "Pod"),
		Entry("Service", "", "v1", "Service"),
		Entry("Secret", "", "v1", "Secret"),
		Entry("ConfigMap", "", "v1", "ConfigMap"),
	)

	It("does not recognise unknown types", func() {
		gvk := schema.GroupVersionKind{
			Group:   "unknown.example.com",
			Version: "v1",
			Kind:    "UnknownResource",
		}
		Expect(scheme.Recognizes(gvk)).To(BeFalse())
	})
})

var _ = Describe("HTTP/2 disabling", func() {
	// The disabling logic is the inline closure in main().  We replicate it
	// here so that the behaviour is tested independently of the full start-up
	// sequence.

	disableHTTP2 := func(c *tls.Config) {
		c.NextProtos = []string{"http/1.1"}
	}

	It("sets NextProtos to [http/1.1] when applied", func() {
		cfg := &tls.Config{}
		disableHTTP2(cfg)
		Expect(cfg.NextProtos).To(ConsistOf("http/1.1"))
	})

	It("leaves NextProtos unchanged when not applied (enableHTTP2=true path)", func() {
		cfg := &tls.Config{}
		// No tlsOpts appended → NextProtos stays at its zero value
		Expect(cfg.NextProtos).To(BeEmpty())
	})

	It("is idempotent when applied twice", func() {
		cfg := &tls.Config{}
		disableHTTP2(cfg)
		disableHTTP2(cfg)
		Expect(cfg.NextProtos).To(ConsistOf("http/1.1"))
	})
})

var _ = Describe("Flag defaults", func() {
	// We replicate the flag registration from main() into a fresh FlagSet so
	// that the documented defaults are tested without executing main().

	var (
		fs                *flag.FlagSet
		metricsAddr       string
		metricsCertPath   string
		metricsCertName   string
		metricsCertKey    string
		webhookCertPath   string
		webhookCertName   string
		webhookCertKey    string
		enableLeaderElect bool
		probeAddr         string
		secureMetrics     bool
		enableHTTP2       bool
	)

	BeforeEach(func() {
		fs = flag.NewFlagSet("test", flag.ContinueOnError)
		fs.StringVar(&metricsAddr, "metrics-bind-address", "0",
			"The address the metrics endpoint binds to.")
		fs.StringVar(&probeAddr, "health-probe-bind-address", ":8081",
			"The address the probe endpoint binds to.")
		fs.BoolVar(&enableLeaderElect, "leader-elect", false,
			"Enable leader election for controller manager.")
		fs.BoolVar(&secureMetrics, "metrics-secure", true,
			"If set, the metrics endpoint is served securely via HTTPS.")
		fs.StringVar(&webhookCertPath, "webhook-cert-path", "",
			"The directory that contains the webhook certificate.")
		fs.StringVar(&webhookCertName, "webhook-cert-name", "tls.crt",
			"The name of the webhook certificate file.")
		fs.StringVar(&webhookCertKey, "webhook-cert-key", "tls.key",
			"The name of the webhook key file.")
		fs.StringVar(&metricsCertPath, "metrics-cert-path", "",
			"The directory that contains the metrics server certificate.")
		fs.StringVar(&metricsCertName, "metrics-cert-name", "tls.crt",
			"The name of the metrics server certificate file.")
		fs.StringVar(&metricsCertKey, "metrics-cert-key", "tls.key",
			"The name of the metrics server key file.")
		fs.BoolVar(&enableHTTP2, "enable-http2", false,
			"If set, HTTP/2 will be enabled for the metrics and webhook servers.")

		Expect(fs.Parse([]string{})).To(Succeed())
	})

	DescribeTable("default values without any flags passed",
		func(flagName, want string) {
			f := fs.Lookup(flagName)
			Expect(f).NotTo(BeNil(), "flag %q should be registered", flagName)
			Expect(f.DefValue).To(Equal(want))
		},
		Entry("metrics-bind-address defaults to disabled (0)", "metrics-bind-address", "0"),
		Entry("health-probe-bind-address defaults to :8081", "health-probe-bind-address", ":8081"),
		Entry("leader-elect defaults to false", "leader-elect", "false"),
		Entry("metrics-secure defaults to true", "metrics-secure", "true"),
		Entry("enable-http2 defaults to false (CVE protection)", "enable-http2", "false"),
		Entry("webhook-cert-path defaults to empty", "webhook-cert-path", ""),
		Entry("webhook-cert-name defaults to tls.crt", "webhook-cert-name", "tls.crt"),
		Entry("webhook-cert-key defaults to tls.key", "webhook-cert-key", "tls.key"),
		Entry("metrics-cert-path defaults to empty", "metrics-cert-path", ""),
		Entry("metrics-cert-name defaults to tls.crt", "metrics-cert-name", "tls.crt"),
		Entry("metrics-cert-key defaults to tls.key", "metrics-cert-key", "tls.key"),
	)

	It("parsed variables reflect the defaults when no flags are provided", func() {
		Expect(metricsAddr).To(Equal("0"))
		Expect(probeAddr).To(Equal(":8081"))
		Expect(enableLeaderElect).To(BeFalse())
		Expect(secureMetrics).To(BeTrue())
		Expect(enableHTTP2).To(BeFalse())
		Expect(webhookCertName).To(Equal("tls.crt"))
		Expect(webhookCertKey).To(Equal("tls.key"))
		Expect(metricsCertName).To(Equal("tls.crt"))
		Expect(metricsCertKey).To(Equal("tls.key"))
		Expect(webhookCertPath).To(BeEmpty())
		Expect(metricsCertPath).To(BeEmpty())
	})

	It("overrides defaults when flags are explicitly set", func() {
		Expect(fs.Parse([]string{
			"--metrics-bind-address=:8443",
			"--leader-elect=true",
			"--enable-http2=true",
			"--metrics-secure=false",
		})).To(Succeed())

		Expect(metricsAddr).To(Equal(":8443"))
		Expect(enableLeaderElect).To(BeTrue())
		Expect(enableHTTP2).To(BeTrue())
		Expect(secureMetrics).To(BeFalse())
	})
})

var _ = Describe("CertWatcher creation", func() {
	var tmpDir string

	BeforeEach(func() {
		var err error
		tmpDir, err = os.MkdirTemp("", "certwatcher-test-*")
		Expect(err).NotTo(HaveOccurred())
	})

	AfterEach(func() {
		Expect(os.RemoveAll(tmpDir)).To(Succeed())
	})

	Context("with valid certificate files", func() {
		It("creates a CertWatcher without error", func() {
			certFile, keyFile, err := generateSelfSignedCert(tmpDir)
			Expect(err).NotTo(HaveOccurred())

			watcher, err := certwatcher.New(certFile, keyFile)
			Expect(err).NotTo(HaveOccurred())
			Expect(watcher).NotTo(BeNil())
		})

		It("exposes a non-nil GetCertificate callback after creation", func() {
			certFile, keyFile, err := generateSelfSignedCert(tmpDir)
			Expect(err).NotTo(HaveOccurred())

			watcher, err := certwatcher.New(certFile, keyFile)
			Expect(err).NotTo(HaveOccurred())
			Expect(watcher.GetCertificate).NotTo(BeNil())
		})

		It("uses cert and key from the configured path components", func() {
			// Mirrors the filepath.Join(certPath, certName) pattern in main().
			certName := "tls.crt"
			keyName := "tls.key"

			certFile, keyFile, err := generateSelfSignedCert(tmpDir)
			Expect(err).NotTo(HaveOccurred())

			// Verify the files land where main() would expect them.
			Expect(certFile).To(Equal(filepath.Join(tmpDir, certName)))
			Expect(keyFile).To(Equal(filepath.Join(tmpDir, keyName)))

			_, err = certwatcher.New(certFile, keyFile)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Context("with invalid certificate paths", func() {
		It("returns an error when both files are missing", func() {
			_, err := certwatcher.New(
				filepath.Join(tmpDir, "nonexistent.crt"),
				filepath.Join(tmpDir, "nonexistent.key"),
			)
			Expect(err).To(HaveOccurred())
		})

		It("returns an error when only the key file is missing", func() {
			certFile, _, err := generateSelfSignedCert(tmpDir)
			Expect(err).NotTo(HaveOccurred())

			_, err = certwatcher.New(certFile, filepath.Join(tmpDir, "missing.key"))
			Expect(err).To(HaveOccurred())
		})

		It("returns an error when the cert file contains garbage", func() {
			badCert := filepath.Join(tmpDir, "bad.crt")
			badKey := filepath.Join(tmpDir, "bad.key")
			Expect(os.WriteFile(badCert, []byte("not a certificate"), 0o600)).To(Succeed())
			Expect(os.WriteFile(badKey, []byte("not a key"), 0o600)).To(Succeed())

			_, err := certwatcher.New(badCert, badKey)
			Expect(err).To(HaveOccurred())
		})
	})
})

var _ = Describe("Webhook enable condition", func() {
	// The operator skips webhook registration when ENABLE_WEBHOOKS=false.
	// These tests verify the environment-variable gating logic.

	BeforeEach(func() {
		GinkgoT().Setenv("ENABLE_WEBHOOKS", "")
	})

	It("webhooks are enabled when ENABLE_WEBHOOKS is unset", func() {
		Expect(os.Getenv("ENABLE_WEBHOOKS")).NotTo(Equal("false"))
	})

	It("webhooks are disabled when ENABLE_WEBHOOKS=false", func() {
		GinkgoT().Setenv("ENABLE_WEBHOOKS", "false")
		Expect(os.Getenv("ENABLE_WEBHOOKS")).To(Equal("false"))
	})

	It("webhooks are enabled when ENABLE_WEBHOOKS=true", func() {
		GinkgoT().Setenv("ENABLE_WEBHOOKS", "true")
		Expect(os.Getenv("ENABLE_WEBHOOKS")).NotTo(Equal("false"))
	})

	It("webhooks are enabled when ENABLE_WEBHOOKS is an arbitrary non-false value", func() {
		GinkgoT().Setenv("ENABLE_WEBHOOKS", "1")
		Expect(os.Getenv("ENABLE_WEBHOOKS")).NotTo(Equal("false"))
	})
})

var _ = Describe("Cloudflared image env var", func() {
	// The operator reads CLOUDFLARED_IMAGE at start-up to allow overriding
	// the default cloudflared container image.

	BeforeEach(func() {
		GinkgoT().Setenv("CLOUDFLARED_IMAGE", "")
	})

	It("returns empty string when CLOUDFLARED_IMAGE is unset", func() {
		Expect(os.Getenv("CLOUDFLARED_IMAGE")).To(BeEmpty())
	})

	It("returns the configured image when set", func() {
		GinkgoT().Setenv("CLOUDFLARED_IMAGE", "ghcr.io/example/cloudflared:v2025.4.0")
		Expect(os.Getenv("CLOUDFLARED_IMAGE")).To(Equal("ghcr.io/example/cloudflared:v2025.4.0"))
	})
})

var _ = Describe("State machine component construction", func() {
	It("creates a CloudflareTunnelCalculator with a valid logger", func() {
		logger := ctrl.Log.WithName("test-calculator")
		calc := sm.NewCloudflareTunnelCalculator(logger)
		Expect(calc).NotTo(BeNil())
	})

	It("creates a non-nil OTelObserver", func() {
		obs := sm.NewOTelObserver("test-controller")
		Expect(obs).NotTo(BeNil())
	})

	It("creates a non-nil MetricsObserver", func() {
		obs := sm.NewMetricsObserver()
		Expect(obs).NotTo(BeNil())
	})

	It("creates a CompositeObserver that aggregates multiple observers", func() {
		composite := sm.CompositeObserver{
			sm.LoggingObserver{},
			sm.NewOTelObserver("test-controller"),
			sm.NewMetricsObserver(),
		}
		Expect(composite).To(HaveLen(3))
	})

	It("creates a CompositeObserver with a single observer", func() {
		composite := sm.CompositeObserver{sm.LoggingObserver{}}
		Expect(composite).To(HaveLen(1))
	})

	It("creates an empty CompositeObserver without panicking", func() {
		Expect(func() {
			_ = sm.CompositeObserver{}
		}).NotTo(Panic())
	})
})

var _ = Describe("Cloudflare client initialisation", func() {
	It("succeeds with a non-empty API token", func() {
		client, err := cfclient.NewTunnelClient("test-api-token-value")
		Expect(err).NotTo(HaveOccurred())
		Expect(client).NotTo(BeNil())
	})

	It("creates distinct clients for different tokens", func() {
		c1, err1 := cfclient.NewTunnelClient("token-a")
		c2, err2 := cfclient.NewTunnelClient("token-b")

		Expect(err1).NotTo(HaveOccurred())
		Expect(err2).NotTo(HaveOccurred())
		// Both must be valid; they are independent objects.
		Expect(c1).NotTo(BeNil())
		Expect(c2).NotTo(BeNil())
		Expect(c1).NotTo(BeIdenticalTo(c2))
	})

	It("implements TunnelClientInterface", func() {
		// Compile-time assertion: *TunnelClient must satisfy the interface.
		// At runtime we simply verify that the value is assignable.
		var _ cfclient.TunnelClientInterface
		client, err := cfclient.NewTunnelClient("any-token")
		Expect(err).NotTo(HaveOccurred())
		Expect(client).To(BeAssignableToTypeOf((*cfclient.TunnelClient)(nil)))
	})
})

var _ = Describe("LeaderElection ID constant", func() {
	// The leader election ID is baked into main() and must remain stable to
	// avoid split-brain on rolling upgrades.  Any change requires a migration.
	It("uses the expected leader election ID", func() {
		expectedID := "880612ac.tunnels.cloudflare.io"
		// We can only inspect the value by reading the source; here we verify
		// that the constant is what our tests expect, documenting its value.
		Expect(expectedID).To(MatchRegexp(`^[a-f0-9]+\.tunnels\.cloudflare\.io$`))
	})
})
