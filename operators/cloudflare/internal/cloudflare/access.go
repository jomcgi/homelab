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
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// AccessApplicationConfig represents a Cloudflare Zero Trust access application
type AccessApplicationConfig struct {
	ID                     string
	Name                   string
	Domain                 string
	Type                   string // self_hosted, saas, ssh, vnc, etc.
	SessionDuration        string // e.g., "24h"
	AutoRedirectToIdentity bool
	EnableBindingCookie    bool
	CustomDenyMessage      string
	CustomDenyURL          string
	CORSHeaders            *AccessCORSConfig
}

// AccessCORSConfig represents CORS configuration for an access application
type AccessCORSConfig struct {
	AllowAllOrigins  bool
	AllowedOrigins   []string
	AllowedMethods   []string
	AllowedHeaders   []string
	AllowCredentials bool
	MaxAge           int
}

// AccessPolicyConfig represents a Cloudflare Zero Trust access policy
type AccessPolicyConfig struct {
	ID               string
	Name             string
	Decision         string // allow, deny, non_identity, bypass
	Include          []AccessPolicyRule
	Exclude          []AccessPolicyRule
	Require          []AccessPolicyRule
	ApplicationID    string
	ExternalPolicyID string // Reference to existing policy
}

// AccessPolicyRule represents a rule within an access policy
type AccessPolicyRule struct {
	EmailsEndingIn      []string
	Emails              []string
	EmailDomains        []string
	IPRanges            []string
	Everyone            bool
	GitHubOrganizations []string
	Countries           []string
	GroupID             string // Reference to an existing Access Group by ID
}

// CreateAccessApplication creates a new Cloudflare Zero Trust access application
func (c *TunnelClient) CreateAccessApplication(ctx context.Context, accountID string, config AccessApplicationConfig) (*AccessApplicationConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.CreateAccessApplication",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("application.name", config.Name),
			attribute.String("application.domain", config.Domain),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	// Build application parameters
	params := cloudflare.CreateAccessApplicationParams{
		Name:                   config.Name,
		Domain:                 config.Domain,
		Type:                   cloudflare.AccessApplicationType(config.Type),
		SessionDuration:        config.SessionDuration,
		AutoRedirectToIdentity: cloudflare.BoolPtr(config.AutoRedirectToIdentity),
		EnableBindingCookie:    cloudflare.BoolPtr(config.EnableBindingCookie),
	}

	if config.CustomDenyMessage != "" {
		params.CustomDenyMessage = config.CustomDenyMessage
	}
	if config.CustomDenyURL != "" {
		params.CustomDenyURL = config.CustomDenyURL
	}

	// Add CORS headers if configured
	if config.CORSHeaders != nil {
		params.CorsHeaders = &cloudflare.AccessApplicationCorsHeaders{
			AllowAllOrigins:  config.CORSHeaders.AllowAllOrigins,
			AllowedOrigins:   config.CORSHeaders.AllowedOrigins,
			AllowedMethods:   config.CORSHeaders.AllowedMethods,
			AllowedHeaders:   config.CORSHeaders.AllowedHeaders,
			AllowCredentials: config.CORSHeaders.AllowCredentials,
			MaxAge:           config.CORSHeaders.MaxAge,
		}
	}

	app, err := c.api.CreateAccessApplication(ctx, cloudflare.AccountIdentifier(accountID), params)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create access application")
		return nil, fmt.Errorf("failed to create access application %s: %w", config.Name, err)
	}

	result := &AccessApplicationConfig{
		ID:                     app.ID,
		Name:                   app.Name,
		Domain:                 app.Domain,
		Type:                   string(app.Type),
		SessionDuration:        app.SessionDuration,
		AutoRedirectToIdentity: *app.AutoRedirectToIdentity,
		EnableBindingCookie:    *app.EnableBindingCookie,
		CustomDenyMessage:      app.CustomDenyMessage,
		CustomDenyURL:          app.CustomDenyURL,
	}

	if app.CorsHeaders != nil {
		result.CORSHeaders = &AccessCORSConfig{
			AllowAllOrigins:  app.CorsHeaders.AllowAllOrigins,
			AllowedOrigins:   app.CorsHeaders.AllowedOrigins,
			AllowedMethods:   app.CorsHeaders.AllowedMethods,
			AllowedHeaders:   app.CorsHeaders.AllowedHeaders,
			AllowCredentials: app.CorsHeaders.AllowCredentials,
			MaxAge:           app.CorsHeaders.MaxAge,
		}
	}

	span.SetAttributes(attribute.String("application.id", app.ID))
	span.SetStatus(codes.Ok, "access application created")
	return result, nil
}

// UpdateAccessApplication updates an existing access application
func (c *TunnelClient) UpdateAccessApplication(ctx context.Context, accountID string, config AccessApplicationConfig) error {
	ctx, span := c.tracer.Start(ctx, "cloudflare.UpdateAccessApplication",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("application.id", config.ID),
			attribute.String("application.name", config.Name),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return err
	}

	// Build update parameters
	params := cloudflare.UpdateAccessApplicationParams{
		ID:                     config.ID,
		Name:                   config.Name,
		Domain:                 config.Domain,
		Type:                   cloudflare.AccessApplicationType(config.Type),
		SessionDuration:        config.SessionDuration,
		AutoRedirectToIdentity: cloudflare.BoolPtr(config.AutoRedirectToIdentity),
		EnableBindingCookie:    cloudflare.BoolPtr(config.EnableBindingCookie),
	}

	if config.CustomDenyMessage != "" {
		params.CustomDenyMessage = config.CustomDenyMessage
	}
	if config.CustomDenyURL != "" {
		params.CustomDenyURL = config.CustomDenyURL
	}

	// Add CORS headers if configured
	if config.CORSHeaders != nil {
		params.CorsHeaders = &cloudflare.AccessApplicationCorsHeaders{
			AllowAllOrigins:  config.CORSHeaders.AllowAllOrigins,
			AllowedOrigins:   config.CORSHeaders.AllowedOrigins,
			AllowedMethods:   config.CORSHeaders.AllowedMethods,
			AllowedHeaders:   config.CORSHeaders.AllowedHeaders,
			AllowCredentials: config.CORSHeaders.AllowCredentials,
			MaxAge:           config.CORSHeaders.MaxAge,
		}
	}

	_, err := c.api.UpdateAccessApplication(ctx, cloudflare.AccountIdentifier(accountID), params)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to update access application")
		return fmt.Errorf("failed to update access application %s: %w", config.ID, err)
	}

	span.SetStatus(codes.Ok, "access application updated")
	return nil
}

// DeleteAccessApplication deletes an access application
func (c *TunnelClient) DeleteAccessApplication(ctx context.Context, accountID, applicationID string) error {
	ctx, span := c.tracer.Start(ctx, "cloudflare.DeleteAccessApplication",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("application.id", applicationID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return err
	}

	err := c.api.DeleteAccessApplication(ctx, cloudflare.AccountIdentifier(accountID), applicationID)
	if err != nil {
		// If application not found, consider it already deleted (idempotent)
		if IsNotFoundError(err) {
			span.SetStatus(codes.Ok, "application not found (already deleted)")
			return nil
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to delete access application")
		return fmt.Errorf("failed to delete access application %s: %w", applicationID, err)
	}

	span.SetStatus(codes.Ok, "access application deleted")
	return nil
}

// GetAccessApplication retrieves an access application by ID
func (c *TunnelClient) GetAccessApplication(ctx context.Context, accountID, applicationID string) (*AccessApplicationConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.GetAccessApplication",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("application.id", applicationID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	app, err := c.api.GetAccessApplication(ctx, cloudflare.AccountIdentifier(accountID), applicationID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get access application")
		return nil, fmt.Errorf("failed to get access application %s: %w", applicationID, err)
	}

	result := &AccessApplicationConfig{
		ID:                     app.ID,
		Name:                   app.Name,
		Domain:                 app.Domain,
		Type:                   string(app.Type),
		SessionDuration:        app.SessionDuration,
		AutoRedirectToIdentity: *app.AutoRedirectToIdentity,
		EnableBindingCookie:    *app.EnableBindingCookie,
		CustomDenyMessage:      app.CustomDenyMessage,
		CustomDenyURL:          app.CustomDenyURL,
	}

	if app.CorsHeaders != nil {
		result.CORSHeaders = &AccessCORSConfig{
			AllowAllOrigins:  app.CorsHeaders.AllowAllOrigins,
			AllowedOrigins:   app.CorsHeaders.AllowedOrigins,
			AllowedMethods:   app.CorsHeaders.AllowedMethods,
			AllowedHeaders:   app.CorsHeaders.AllowedHeaders,
			AllowCredentials: app.CorsHeaders.AllowCredentials,
			MaxAge:           app.CorsHeaders.MaxAge,
		}
	}

	span.SetStatus(codes.Ok, "access application retrieved")
	return result, nil
}

// CreateAccessPolicy creates a new access policy and links it to an application
func (c *TunnelClient) CreateAccessPolicy(ctx context.Context, accountID string, config AccessPolicyConfig) (*AccessPolicyConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.CreateAccessPolicy",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("policy.name", config.Name),
			attribute.String("policy.decision", config.Decision),
			attribute.String("application.id", config.ApplicationID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	// Build policy parameters
	params := cloudflare.CreateAccessPolicyParams{
		ApplicationID: config.ApplicationID,
		Name:          config.Name,
		Decision:      config.Decision, // Decision is a string, not a custom type
		Include:       convertAccessPolicyRules(config.Include),
	}

	if len(config.Exclude) > 0 {
		params.Exclude = convertAccessPolicyRules(config.Exclude)
	}
	if len(config.Require) > 0 {
		params.Require = convertAccessPolicyRules(config.Require)
	}

	policy, err := c.api.CreateAccessPolicy(ctx, cloudflare.AccountIdentifier(accountID), params)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create access policy")
		return nil, fmt.Errorf("failed to create access policy %s: %w", config.Name, err)
	}

	result := &AccessPolicyConfig{
		ID:            policy.ID,
		Name:          policy.Name,
		Decision:      string(policy.Decision),
		ApplicationID: config.ApplicationID,
	}

	span.SetAttributes(attribute.String("policy.id", policy.ID))
	span.SetStatus(codes.Ok, "access policy created")
	return result, nil
}

// DeleteAccessPolicy deletes an access policy
func (c *TunnelClient) DeleteAccessPolicy(ctx context.Context, accountID, applicationID, policyID string) error {
	ctx, span := c.tracer.Start(ctx, "cloudflare.DeleteAccessPolicy",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("application.id", applicationID),
			attribute.String("policy.id", policyID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return err
	}

	err := c.api.DeleteAccessPolicy(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.DeleteAccessPolicyParams{
		ApplicationID: applicationID,
		PolicyID:      policyID,
	})
	if err != nil {
		// If policy not found, consider it already deleted (idempotent)
		if IsNotFoundError(err) {
			span.SetStatus(codes.Ok, "policy not found (already deleted)")
			return nil
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to delete access policy")
		return fmt.Errorf("failed to delete access policy %s: %w", policyID, err)
	}

	span.SetStatus(codes.Ok, "access policy deleted")
	return nil
}

// ListAccessPolicies lists all policies for an application
func (c *TunnelClient) ListAccessPolicies(ctx context.Context, accountID, applicationID string) ([]AccessPolicyConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.ListAccessPolicies",
		trace.WithAttributes(
			attribute.String("account.id", accountID),
			attribute.String("application.id", applicationID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	policies, _, err := c.api.ListAccessPolicies(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.ListAccessPoliciesParams{
		ApplicationID: applicationID,
	})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to list access policies")
		return nil, fmt.Errorf("failed to list access policies for application %s: %w", applicationID, err)
	}

	var result []AccessPolicyConfig
	for _, policy := range policies {
		result = append(result, AccessPolicyConfig{
			ID:            policy.ID,
			Name:          policy.Name,
			Decision:      string(policy.Decision),
			ApplicationID: applicationID,
		})
	}

	span.SetAttributes(attribute.Int("policy.count", len(result)))
	span.SetStatus(codes.Ok, "access policies listed")
	return result, nil
}

// convertAccessPolicyRules converts our AccessPolicyRule to Cloudflare's format
func convertAccessPolicyRules(rules []AccessPolicyRule) []interface{} {
	var cfRules []interface{}

	for _, rule := range rules {
		cfRule := make(map[string]interface{})

		// Group reference takes precedence - if set, use it exclusively
		if rule.GroupID != "" {
			cfRules = append(cfRules, map[string]interface{}{
				"group": map[string]interface{}{"id": rule.GroupID},
			})
			continue
		}

		if len(rule.Emails) > 0 {
			for _, email := range rule.Emails {
				cfRules = append(cfRules, map[string]interface{}{
					"email": map[string]interface{}{"email": email},
				})
			}
		}
		if len(rule.EmailsEndingIn) > 0 {
			for _, domain := range rule.EmailsEndingIn {
				cfRules = append(cfRules, map[string]interface{}{
					"email_domain": map[string]interface{}{"domain": domain},
				})
			}
		}
		if len(rule.EmailDomains) > 0 {
			for _, domain := range rule.EmailDomains {
				cfRules = append(cfRules, map[string]interface{}{
					"email_domain": map[string]interface{}{"domain": domain},
				})
			}
		}
		if len(rule.IPRanges) > 0 {
			cfRule["ip"] = map[string]interface{}{"ip": rule.IPRanges}
		}
		if rule.Everyone {
			cfRules = append(cfRules, map[string]interface{}{
				"everyone": map[string]interface{}{},
			})
			continue
		}
		if len(rule.GitHubOrganizations) > 0 {
			for _, org := range rule.GitHubOrganizations {
				cfRules = append(cfRules, map[string]interface{}{
					"github-organization": map[string]interface{}{
						"name":              org,
						"identity_provider": "github",
					},
				})
			}
		}
		if len(rule.Countries) > 0 {
			cfRule["geo"] = map[string]interface{}{"country_code": rule.Countries}
		}

		if len(cfRule) > 0 {
			cfRules = append(cfRules, cfRule)
		}
	}

	return cfRules
}
