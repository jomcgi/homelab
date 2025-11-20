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
	"sort"

	"github.com/cloudflare/cloudflare-go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// RouteConfig represents a published application route configuration
type RouteConfig struct {
	Hostname string
	Service  string
	Path     string // Optional path-based routing
}

// CreatePublishedRoute creates a published application route by updating tunnel configuration
// This automatically publishes the application via the tunnel for the specified hostname
func (c *TunnelClient) CreatePublishedRoute(ctx context.Context, accountID, tunnelID string, route RouteConfig) error {
	ctx, span := c.tracer.Start(ctx, "cloudflare.CreatePublishedRoute",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("tunnel.id", tunnelID),
			attribute.String("route.hostname", route.Hostname),
			attribute.String("route.service", route.Service),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return err
	}

	// Get current configuration to preserve existing routes
	currentConfig, err := c.api.GetTunnelConfiguration(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
	if err != nil && !IsNotFoundError(err) {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get current tunnel configuration")
		return fmt.Errorf("failed to get current tunnel configuration for %s: %w", tunnelID, err)
	}

	// Build ingress rules - preserve existing routes and add new one
	var ingressRules []cloudflare.UnvalidatedIngressRule
	var existingRoute *cloudflare.UnvalidatedIngressRule

	// Copy existing rules (if any), excluding catch-all
	if currentConfig.Config.Ingress != nil {
		for _, rule := range currentConfig.Config.Ingress {
			// Skip catch-all rule (service without hostname) - we'll re-add it at the end
			if rule.Hostname == "" {
				continue
			}
			// Skip if this hostname already exists (we're updating it)
			if rule.Hostname == route.Hostname {
				existingRoute = &rule
				continue
			}
			ingressRules = append(ingressRules, rule)
		}
	}

	// If route already exists with same service, no update needed
	if existingRoute != nil && existingRoute.Service == route.Service && existingRoute.Path == route.Path {
		span.SetStatus(codes.Ok, "route already exists with same configuration")
		return nil
	}

	// Add the new route
	newRule := cloudflare.UnvalidatedIngressRule{
		Hostname: route.Hostname,
		Service:  route.Service,
	}
	if route.Path != "" {
		newRule.Path = route.Path
	}
	ingressRules = append(ingressRules, newRule)

	// Sort ingress rules by hostname for consistent ordering
	sort.Slice(ingressRules, func(i, j int) bool {
		return ingressRules[i].Hostname < ingressRules[j].Hostname
	})

	// Add catch-all rule (required by Cloudflare)
	ingressRules = append(ingressRules, cloudflare.UnvalidatedIngressRule{
		Service: "http_status:404",
	})

	// Update tunnel configuration
	config := cloudflare.TunnelConfiguration{
		Ingress: ingressRules,
	}

	_, err = c.api.UpdateTunnelConfiguration(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelConfigurationParams{
		TunnelID: tunnelID,
		Config:   config,
	})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to update tunnel configuration")
		return fmt.Errorf("failed to create published route for %s: %w", route.Hostname, err)
	}

	span.SetAttributes(attribute.Int("ingress.rule.count", len(ingressRules)))
	span.SetStatus(codes.Ok, "published route created")
	return nil
}

// DeletePublishedRoute removes a published application route from tunnel configuration
func (c *TunnelClient) DeletePublishedRoute(ctx context.Context, accountID, tunnelID, hostname string) error {
	ctx, span := c.tracer.Start(ctx, "cloudflare.DeletePublishedRoute",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("tunnel.id", tunnelID),
			attribute.String("route.hostname", hostname),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return err
	}

	// Get current configuration
	currentConfig, err := c.api.GetTunnelConfiguration(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get current tunnel configuration")
		return fmt.Errorf("failed to get tunnel configuration for %s: %w", tunnelID, err)
	}

	// Build new ingress rules excluding the deleted hostname
	var ingressRules []cloudflare.UnvalidatedIngressRule
	found := false

	if currentConfig.Config.Ingress != nil {
		for _, rule := range currentConfig.Config.Ingress {
			// Skip catch-all rule (we'll re-add it)
			if rule.Hostname == "" {
				continue
			}
			// Skip the hostname we're deleting
			if rule.Hostname == hostname {
				found = true
				continue
			}
			ingressRules = append(ingressRules, rule)
		}
	}

	if !found {
		span.SetStatus(codes.Ok, "route not found (already deleted)")
		return nil
	}

	// Sort ingress rules by hostname for consistent ordering
	sort.Slice(ingressRules, func(i, j int) bool {
		return ingressRules[i].Hostname < ingressRules[j].Hostname
	})

	// Add catch-all rule (required by Cloudflare)
	ingressRules = append(ingressRules, cloudflare.UnvalidatedIngressRule{
		Service: "http_status:404",
	})

	// Update tunnel configuration
	config := cloudflare.TunnelConfiguration{
		Ingress: ingressRules,
	}

	_, err = c.api.UpdateTunnelConfiguration(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelConfigurationParams{
		TunnelID: tunnelID,
		Config:   config,
	})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to update tunnel configuration")
		return fmt.Errorf("failed to delete published route for %s: %w", hostname, err)
	}

	span.SetAttributes(attribute.Int("ingress.rule.count", len(ingressRules)))
	span.SetStatus(codes.Ok, "published route deleted")
	return nil
}

// ListPublishedRoutes retrieves all published application routes from tunnel configuration
func (c *TunnelClient) ListPublishedRoutes(ctx context.Context, accountID, tunnelID string) ([]RouteConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.ListPublishedRoutes",
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

	// Get current tunnel configuration
	config, err := c.api.GetTunnelConfiguration(ctx, cloudflare.AccountIdentifier(accountID), tunnelID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get tunnel configuration")
		return nil, fmt.Errorf("failed to list published routes for tunnel %s: %w", tunnelID, err)
	}

	// Convert ingress rules to RouteConfig (excluding catch-all)
	var routes []RouteConfig
	if config.Config.Ingress != nil {
		for _, rule := range config.Config.Ingress {
			// Skip catch-all rule (service without hostname)
			if rule.Hostname == "" {
				continue
			}
			routes = append(routes, RouteConfig{
				Hostname: rule.Hostname,
				Service:  rule.Service,
				Path:     rule.Path,
			})
		}
	}

	span.SetAttributes(attribute.Int("route.count", len(routes)))
	span.SetStatus(codes.Ok, "published routes listed")
	return routes, nil
}

// GetPublishedRoute retrieves a specific published route by hostname
func (c *TunnelClient) GetPublishedRoute(ctx context.Context, accountID, tunnelID, hostname string) (*RouteConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.GetPublishedRoute",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("tunnel.id", tunnelID),
			attribute.String("route.hostname", hostname),
		),
	)
	defer span.End()

	routes, err := c.ListPublishedRoutes(ctx, accountID, tunnelID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to list routes")
		return nil, err
	}

	for _, route := range routes {
		if route.Hostname == hostname {
			span.SetStatus(codes.Ok, "route found")
			return &route, nil
		}
	}

	err = fmt.Errorf("route not found for hostname: %s", hostname)
	span.SetStatus(codes.Error, "route not found")
	return nil, err
}
