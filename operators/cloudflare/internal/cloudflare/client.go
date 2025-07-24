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

	"github.com/cloudflare/cloudflare-go"
	"golang.org/x/time/rate"
)

// TunnelClientInterface defines the interface for tunnel operations
type TunnelClientInterface interface {
	CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error)
	GetTunnel(ctx context.Context, accountID, tunnelID string) (*cloudflare.Tunnel, error)
	DeleteTunnel(ctx context.Context, accountID, tunnelID string) error
	UpdateTunnelConfiguration(ctx context.Context, accountID, tunnelID string, config cloudflare.TunnelConfiguration) error
	GetTunnelToken(ctx context.Context, accountID, tunnelID string) (string, error)
}

// TunnelClient wraps the Cloudflare API with rate limiting and error handling
type TunnelClient struct {
	api     *cloudflare.API
	limiter *rate.Limiter
}

// NewTunnelClient creates a new rate-limited Cloudflare client
func NewTunnelClient(apiToken string) (*TunnelClient, error) {
	api, err := cloudflare.NewWithAPIToken(apiToken)
	if err != nil {
		return nil, fmt.Errorf("failed to create cloudflare client: %w", err)
	}

	// Rate limiter: 10 requests per second with burst of 20
	limiter := rate.NewLimiter(rate.Limit(10), 20)

	return &TunnelClient{
		api:     api,
		limiter: limiter,
	}, nil
}

// CreateTunnel creates a new tunnel in Cloudflare and returns both the tunnel and its secret
func (c *TunnelClient) CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error) {
	if err := c.limiter.Wait(ctx); err != nil {
		return nil, "", err
	}

	// Generate a random tunnel secret (32 bytes, base64 encoded)
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		return nil, "", fmt.Errorf("failed to generate tunnel secret: %w", err)
	}
	tunnelSecret := base64.StdEncoding.EncodeToString(secret)

	tunnel, err := c.api.CreateTunnel(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelCreateParams{
		Name:   name,
		Secret: tunnelSecret,
	})
	if err != nil {
		return nil, "", fmt.Errorf("failed to create tunnel %s: %w", name, err)
	}

	return &tunnel, tunnelSecret, nil
}

// GetTunnel retrieves tunnel information from Cloudflare
func (c *TunnelClient) GetTunnel(ctx context.Context, accountID, tunnelID string) (*cloudflare.Tunnel, error) {
	if err := c.limiter.Wait(ctx); err != nil {
		return nil, err
	}

	tunnel, err := c.api.GetTunnel(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
	if err != nil {
		return nil, fmt.Errorf("failed to get tunnel %s: %w", tunnelID, err)
	}

	return &tunnel, nil
}

// DeleteTunnel deletes a tunnel from Cloudflare
func (c *TunnelClient) DeleteTunnel(ctx context.Context, accountID, tunnelID string) error {
	if err := c.limiter.Wait(ctx); err != nil {
		return err
	}

	err := c.api.DeleteTunnel(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
	if err != nil {
		return fmt.Errorf("failed to delete tunnel %s: %w", tunnelID, err)
	}

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
