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
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/cloudflare/cloudflare-go"
	"github.com/jomcgi/homelab/projects/operators/cloudflare/internal/telemetry"
	"github.com/sony/gobreaker"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
	"golang.org/x/time/rate"
)

// TunnelClientInterface defines the interface for tunnel operations
type TunnelClientInterface interface {
	// Tunnel management
	CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error)
	GetTunnel(ctx context.Context, accountID, tunnelID string) (*cloudflare.Tunnel, error)
	ListTunnels(ctx context.Context, accountID string) ([]cloudflare.Tunnel, error)
	DeleteTunnel(ctx context.Context, accountID, tunnelID string) error
	UpdateTunnelConfiguration(ctx context.Context, accountID, tunnelID string, config cloudflare.TunnelConfiguration) error
	GetTunnelToken(ctx context.Context, accountID, tunnelID string) (string, error)

	// Published application routes
	CreatePublishedRoute(ctx context.Context, accountID, tunnelID string, route RouteConfig) error
	DeletePublishedRoute(ctx context.Context, accountID, tunnelID, hostname string) error
	ListPublishedRoutes(ctx context.Context, accountID, tunnelID string) ([]RouteConfig, error)
	GetPublishedRoute(ctx context.Context, accountID, tunnelID, hostname string) (*RouteConfig, error)

	// DNS management
	CreateTunnelDNSRecord(ctx context.Context, hostname, tunnelID string) (*DNSRecordConfig, error)
	DeleteDNSRecord(ctx context.Context, zoneID, recordID string) error
	GetDNSRecordByName(ctx context.Context, hostname string) (*DNSRecordConfig, error)
	ListTunnelDNSRecords(ctx context.Context, zoneID, tunnelID string) ([]DNSRecordConfig, error)
	UpdateDNSRecord(ctx context.Context, config DNSRecordConfig) error

	// Zero Trust Access management
	CreateAccessApplication(ctx context.Context, accountID string, config AccessApplicationConfig) (*AccessApplicationConfig, error)
	UpdateAccessApplication(ctx context.Context, accountID string, config AccessApplicationConfig) error
	DeleteAccessApplication(ctx context.Context, accountID, applicationID string) error
	GetAccessApplication(ctx context.Context, accountID, applicationID string) (*AccessApplicationConfig, error)
	CreateAccessPolicy(ctx context.Context, accountID string, config AccessPolicyConfig) (*AccessPolicyConfig, error)
	DeleteAccessPolicy(ctx context.Context, accountID, applicationID, policyID string) error
	ListAccessPolicies(ctx context.Context, accountID, applicationID string) ([]AccessPolicyConfig, error)
}

// TunnelClient wraps the Cloudflare API with rate limiting, circuit breaker, and error handling
type TunnelClient struct {
	api            cloudflareAPI
	limiter        *rate.Limiter
	circuitBreaker *gobreaker.CircuitBreaker
	tracer         trace.Tracer
}

// NewTunnelClient creates a new rate-limited Cloudflare client with circuit breaker
func NewTunnelClient(apiToken string) (*TunnelClient, error) {
	api, err := cloudflare.NewWithAPIToken(apiToken)
	if err != nil {
		return nil, fmt.Errorf("failed to create cloudflare client: %w", err)
	}

	// Rate limiter: 3 requests per second with burst of 10
	// Cloudflare API limit: 1200 requests per 5 minutes (4 req/s average)
	// We use 3 req/s to stay safely under the limit with headroom for bursts
	limiter := rate.NewLimiter(rate.Limit(3), 10)

	// Circuit breaker: Open after 5 consecutive failures, half-open after 30s
	// This prevents cascading failures when Cloudflare API is degraded
	cbSettings := gobreaker.Settings{
		Name:        "cloudflare-api",
		MaxRequests: 3,                // Allow 3 requests in half-open state
		Interval:    time.Minute,      // Reset failure count every minute
		Timeout:     30 * time.Second, // Stay open for 30s before trying half-open
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			// Open circuit after 5 consecutive failures
			return counts.ConsecutiveFailures >= 5
		},
		OnStateChange: func(name string, from gobreaker.State, to gobreaker.State) {
			// Log state changes for observability
			fmt.Printf("Circuit breaker '%s' state changed from %s to %s\n", name, from, to)
		},
	}

	return &TunnelClient{
		api:            api,
		limiter:        limiter,
		circuitBreaker: gobreaker.NewCircuitBreaker(cbSettings),
		tracer:         telemetry.GetTracer("cloudflare-api-client"),
	}, nil
}

// CreateTunnel creates a new tunnel in Cloudflare and returns both the tunnel and its secret
func (c *TunnelClient) CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.CreateTunnel",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("tunnel.name", name),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, "", err
	}

	// Generate a random tunnel secret (32 bytes, base64 encoded)
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to generate secret")
		return nil, "", fmt.Errorf("failed to generate tunnel secret: %w", err)
	}
	tunnelSecret := base64.StdEncoding.EncodeToString(secret)

	// Wrap API call with circuit breaker
	result, err := c.circuitBreaker.Execute(func() (interface{}, error) {
		tunnel, err := c.api.CreateTunnel(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelCreateParams{
			Name:   name,
			Secret: tunnelSecret,
		})
		if err != nil {
			// Only trip circuit on retryable errors (5xx, 429)
			// Non-retryable errors (4xx) return error but don't affect circuit state
			if !IsRetryableError(err) {
				// Return success to circuit breaker (don't count as failure)
				// but pass error through result
				return nil, err
			}
			return nil, err
		}
		return &tunnel, nil
	})
	if err != nil {
		span.RecordError(err)
		if err == gobreaker.ErrOpenState {
			span.SetStatus(codes.Error, "circuit breaker open")
		} else {
			span.SetStatus(codes.Error, "cloudflare API call failed")
		}
		return nil, "", fmt.Errorf("failed to create tunnel %s: %w", name, err)
	}

	tunnel := result.(*cloudflare.Tunnel)
	span.SetAttributes(attribute.String("tunnel.id", tunnel.ID))
	span.SetStatus(codes.Ok, "tunnel created")
	return tunnel, tunnelSecret, nil
}

// GetTunnel retrieves tunnel information from Cloudflare
func (c *TunnelClient) GetTunnel(ctx context.Context, accountID, tunnelID string) (*cloudflare.Tunnel, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.GetTunnel",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("tunnel.id", tunnelID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	tunnel, err := c.api.GetTunnel(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "cloudflare API call failed")
		return nil, fmt.Errorf("failed to get tunnel %s: %w", tunnelID, err)
	}

	span.SetStatus(codes.Ok, "tunnel retrieved")
	return &tunnel, nil
}

// ListTunnels lists all tunnels for an account
func (c *TunnelClient) ListTunnels(ctx context.Context, accountID string) ([]cloudflare.Tunnel, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.ListTunnels",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	tunnels, _, err := c.api.ListTunnels(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelListParams{})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "cloudflare API call failed")
		return nil, fmt.Errorf("failed to list tunnels: %w", err)
	}

	span.SetAttributes(attribute.Int("tunnel.count", len(tunnels)))
	span.SetStatus(codes.Ok, "tunnels listed")
	return tunnels, nil
}

// DeleteTunnel deletes a tunnel from Cloudflare
func (c *TunnelClient) DeleteTunnel(ctx context.Context, accountID, tunnelID string) error {
	ctx, span := c.tracer.Start(ctx, "cloudflare.DeleteTunnel",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("tunnel.id", tunnelID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return err
	}

	err := c.api.DeleteTunnel(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "cloudflare API call failed")
		return fmt.Errorf("failed to delete tunnel %s: %w", tunnelID, err)
	}

	span.SetStatus(codes.Ok, "tunnel deleted")
	return nil
}

// UpdateTunnelConfiguration updates tunnel ingress rules
func (c *TunnelClient) UpdateTunnelConfiguration(ctx context.Context, accountID, tunnelID string, config cloudflare.TunnelConfiguration) error {
	if err := c.limiter.Wait(ctx); err != nil {
		return err
	}

	_, err := c.api.UpdateTunnelConfiguration(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelConfigurationParams{
		TunnelID: tunnelID,
		Config:   config,
	})
	if err != nil {
		return fmt.Errorf("failed to update tunnel configuration for %s: %w", tunnelID, err)
	}

	return nil
}

// GetTunnelToken retrieves the tunnel token for daemon configuration
func (c *TunnelClient) GetTunnelToken(ctx context.Context, accountID, tunnelID string) (string, error) {
	if err := c.limiter.Wait(ctx); err != nil {
		return "", err
	}

	token, err := c.api.GetTunnelToken(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
	if err != nil {
		return "", fmt.Errorf("failed to get tunnel token for %s: %w", tunnelID, err)
	}

	return token, nil
}

// IsRetryableError determines if an error should trigger a retry
func IsRetryableError(err error) bool {
	if err == nil {
		return false
	}

	var cfErr *cloudflare.Error
	if errors.As(err, &cfErr) {
		switch cfErr.StatusCode {
		case http.StatusTooManyRequests, http.StatusInternalServerError, http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
			return true
		}
	}

	return false
}

// IsNotFoundError checks if the error is a "not found" error
func IsNotFoundError(err error) bool {
	if err == nil {
		return false
	}

	var cfErr *cloudflare.Error
	if errors.As(err, &cfErr) {
		return cfErr.StatusCode == http.StatusNotFound
	}

	return false
}
