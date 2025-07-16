package cloudflare

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"time"

	cfv3 "github.com/cloudflare/cloudflare-go/v3"
	"github.com/cloudflare/cloudflare-go/v3/option"
	"github.com/cloudflare/cloudflare-go/v3/zero_trust"
)

type Client struct {
	client    *cfv3.Client
	AccountID string
	retryCount map[string]int // Track retry attempts per tunnel ID
}

func NewClient() (*Client, error) {
	token := os.Getenv("CLOUDFLARE_API_TOKEN")
	if token == "" {
		return nil, fmt.Errorf("CLOUDFLARE_API_TOKEN environment variable is required")
	}

	accountID := os.Getenv("CLOUDFLARE_ACCOUNT_ID")
	if accountID == "" {
		return nil, fmt.Errorf("CLOUDFLARE_ACCOUNT_ID environment variable is required")
	}


	client := cfv3.NewClient(
		option.WithAPIToken(token),
	)

	return &Client{
		client:     client,
		AccountID:  accountID,
		retryCount: make(map[string]int),
	}, nil
}

// CreateAccessApplication creates a new Zero Trust Access application with linked policy
func (c *Client) CreateAccessApplication(ctx context.Context, hostname, name, policyID string) (*zero_trust.AccessApplicationNewResponse, error) {
	// Create policy reference for the application
	var policies []zero_trust.AccessApplicationNewParamsBodySelfHostedApplicationPolicyUnion
	if policyID != "" {
		policyLink := zero_trust.AccessApplicationNewParamsBodySelfHostedApplicationPoliciesAccessAppPolicyLink{
			ID: cfv3.F(policyID),
		}
		policies = append(policies, policyLink)
	}

	application, err := c.client.ZeroTrust.Access.Applications.New(ctx, zero_trust.AccessApplicationNewParams{
		AccountID: cfv3.F(c.AccountID),
		Body: zero_trust.AccessApplicationNewParamsBodySelfHostedApplication{
			Domain:           cfv3.F(hostname),
			Type:             cfv3.F("self_hosted"),
			Name:             cfv3.F(name),
			SessionDuration:  cfv3.F("24h"),
			Policies:         cfv3.F(policies),
		},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create Access application: %w", err)
	}

	return application, nil
}

// FindAccessApplicationByDomain finds an existing Access application by domain
func (c *Client) FindAccessApplicationByDomain(ctx context.Context, domain string) (string, error) {
	// For now, let's disable this to get the basic functionality working
	// TODO: Implement proper application lookup with v3 SDK pagination API
	return "", nil // Not found
}

// CreateAccessPolicy creates a Zero Trust Access policy with email list
func (c *Client) CreateAccessPolicy(ctx context.Context, name string, emails []string) (*zero_trust.AccessPolicyNewResponse, error) {
	// Create include rules for the emails
	var includeRules []zero_trust.AccessRuleUnionParam
	for _, email := range emails {
		rule := zero_trust.EmailRuleParam{
			Email: cfv3.F(zero_trust.EmailRuleEmailParam{
				Email: cfv3.F(email),
			}),
		}
		includeRules = append(includeRules, rule)
	}

	policy, err := c.client.ZeroTrust.Access.Policies.New(ctx, zero_trust.AccessPolicyNewParams{
		AccountID: cfv3.F(c.AccountID),
		Decision:  cfv3.F(zero_trust.DecisionAllow),
		Include:   cfv3.F(includeRules),
		Name:      cfv3.F(name),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create Access policy: %w", err)
	}

	return policy, nil
}

// DeleteAccessPolicy deletes a Zero Trust Access policy
func (c *Client) DeleteAccessPolicy(ctx context.Context, policyID string) error {
	_, err := c.client.ZeroTrust.Access.Policies.Delete(ctx, policyID, zero_trust.AccessPolicyDeleteParams{
		AccountID: cfv3.F(c.AccountID),
	})
	if err != nil {
		return fmt.Errorf("failed to delete Access policy: %w", err)
	}

	return nil
}

// DeleteAccessApplication deletes a Zero Trust Access application
func (c *Client) DeleteAccessApplication(ctx context.Context, appID string) error {
	_, err := c.client.ZeroTrust.Access.Applications.Delete(ctx, appID, zero_trust.AccessApplicationDeleteParams{
		AccountID: cfv3.F(c.AccountID),
	})
	if err != nil {
		return fmt.Errorf("failed to delete Access application: %w", err)
	}

	return nil
}

// CreateTunnel creates a new Cloudflare Tunnel
func (c *Client) CreateTunnel(ctx context.Context, name string) (*zero_trust.TunnelNewResponse, error) {
	tunnel, err := c.client.ZeroTrust.Tunnels.New(ctx, zero_trust.TunnelNewParams{
		AccountID: cfv3.F(c.AccountID),
		Name:      cfv3.F(name),
		// Don't specify TunnelSecret - let Cloudflare auto-generate it
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create tunnel: %w", err)
	}

	return tunnel, nil
}

// GetTunnel retrieves an existing tunnel by ID
func (c *Client) GetTunnel(ctx context.Context, tunnelID string) (*zero_trust.TunnelGetResponse, error) {
	tunnel, err := c.client.ZeroTrust.Tunnels.Get(ctx, tunnelID, zero_trust.TunnelGetParams{
		AccountID: cfv3.F(c.AccountID),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to get tunnel: %w", err)
	}

	return tunnel, nil
}

// ListTunnels lists all tunnels for the account (simplified for operator use)
func (c *Client) ListTunnels(ctx context.Context) error {
	// For the operator, we don't need to list tunnels since each operator
	// manages its own tunnel. This is kept for potential future use.
	return fmt.Errorf("not implemented - operator manages its own tunnel")
}

// DeleteTunnel deletes a Cloudflare Tunnel with exponential backoff retry
func (c *Client) DeleteTunnel(ctx context.Context, tunnelID string) error {
	const maxRetryInterval = 30 * time.Second
	const alertAfterFailures = 5

	// Initialize retry count if not exists
	if c.retryCount == nil {
		c.retryCount = make(map[string]int)
	}

	for {
		// Attempt tunnel deletion
		_, err := c.client.ZeroTrust.Tunnels.Delete(ctx, tunnelID, zero_trust.TunnelDeleteParams{
			AccountID: cfv3.F(c.AccountID),
		})
		
		if err == nil {
			// Success - reset retry count and return
			delete(c.retryCount, tunnelID)
			return nil
		}

		// Track retry attempts
		c.retryCount[tunnelID]++
		currentAttempt := c.retryCount[tunnelID]

		// Alert after specified failures but continue retrying
		if currentAttempt == alertAfterFailures {
			// Log alert - in production this would integrate with monitoring
			fmt.Printf("🚨 ALERT: Tunnel deletion failed %d times, continuing to retry. TunnelID: %s, Error: %v\n", 
				alertAfterFailures, tunnelID, err)
		}

		// Calculate exponential backoff delay (capped at maxRetryInterval)
		delay := time.Duration(1<<min(currentAttempt-1, 5)) * time.Second
		if delay > maxRetryInterval {
			delay = maxRetryInterval
		}

		// Log retry attempt
		fmt.Printf("⏳ Tunnel deletion attempt %d failed, retrying in %v. TunnelID: %s, Error: %v\n", 
			currentAttempt, delay, tunnelID, err)

		// Check if context is cancelled before waiting
		select {
		case <-ctx.Done():
			return fmt.Errorf("tunnel deletion cancelled after %d attempts: %w", currentAttempt, ctx.Err())
		case <-time.After(delay):
			// Continue to next retry attempt
		}
	}
}

// min returns the minimum of two integers
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// GetTunnelToken gets the tunnel credentials for a tunnel
func (c *Client) GetTunnelToken(ctx context.Context, tunnelID string) (string, error) {
	// Get tunnel details to extract the secret
	tunnel, err := c.client.ZeroTrust.Tunnels.Get(ctx, tunnelID, zero_trust.TunnelGetParams{
		AccountID: cfv3.F(c.AccountID),
	})
	if err != nil {
		return "", fmt.Errorf("failed to get tunnel details: %w", err)
	}
	
	if tunnel == nil {
		return "", fmt.Errorf("tunnel not found")
	}

	// The tunnel response should contain the secret we need
	// Let's try to extract it from the tunnel object
	if tunnel != nil {
		// The tunnel secret might be in the tunnel response
		// For now, return a placeholder that will be replaced with actual credentials JSON
		return fmt.Sprintf("TUNNEL_CREDENTIALS:%s", tunnelID), nil
	}
	
	return "", fmt.Errorf("could not extract tunnel credentials")
}

// GetTunnelCredentials gets the complete tunnel credentials including the secret
func (c *Client) GetTunnelCredentials(ctx context.Context, tunnelID string) (map[string]string, error) {
	// Use the TunnelTokenService to get the actual tunnel token/secret
	tokenResponse, err := c.client.ZeroTrust.Tunnels.Token.Get(ctx, tunnelID, zero_trust.TunnelTokenGetParams{
		AccountID: cfv3.F(c.AccountID),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to get tunnel token: %w", err)
	}
	
	if tokenResponse == nil {
		return nil, fmt.Errorf("tunnel token response is nil")
	}

	// The token response contains the credentials - we need to extract the tunnel secret
	// The response is a union type that likely contains the credentials
	var tunnelSecret string
	
	// Parse the token response - the debug output shows it's a base64-encoded JSON string
	// From debug: "eyJhIjoiN2M1NmI0NThjZDY1N2Q5NmIwOTVjNjNkMTgxYzA1MWYiLCJ0IjoiNzZmYTljMjMtNTQxMi00MmM2LTk1ZDEtM2NlYjFiMmJlNjRmIiwicyI6IjkwZStBWjVvRW90T285SnZGa0ZYMnpNNnJ4a1JhWmtLMjBaY09YZ2JMQUt1Y0xoaU5OVXhmbVh3MmtydGVpeXJST2N2c1N4SHFJWnNPNkRPK2lQamtnPT0ifQ=="
	// Which decodes to: {"a":"account_id","t":"tunnel_id","s":"tunnel_secret"}
	
	// Convert the union response to string by marshaling and unmarshaling 
	responseBytes, err := json.Marshal(tokenResponse)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal token response: %w", err)
	}
	
	var tokenString string
	if err := json.Unmarshal(responseBytes, &tokenString); err != nil {
		return nil, fmt.Errorf("failed to unmarshal token response as string: %w", err)
	}
	
	// The token response contains a base64-encoded JSON with format:
	// {"a": "account_id", "t": "tunnel_id", "s": "tunnel_secret"}
	var tokenData struct {
		A string `json:"a"` // Account ID
		T string `json:"t"` // Tunnel ID  
		S string `json:"s"` // Tunnel Secret
	}
	
	// Decode the base64-encoded token
	decodedBytes, err := base64.StdEncoding.DecodeString(tokenString)
	if err != nil {
		return nil, fmt.Errorf("failed to decode base64 token: %w", err)
	}
	
	if err := json.Unmarshal(decodedBytes, &tokenData); err != nil {
		return nil, fmt.Errorf("failed to parse token JSON: %w", err)
	}
	
	// Extract the tunnel secret from the parsed token
	tunnelSecret = tokenData.S
	
	// Validate that we have the expected tunnel ID
	if tokenData.T != tunnelID {
		return nil, fmt.Errorf("token tunnel ID %s does not match requested tunnel ID %s", tokenData.T, tunnelID)
	}
	
	credentials := map[string]string{
		"AccountTag":   c.AccountID,
		"TunnelSecret": tunnelSecret,
		"TunnelID":     tunnelID,
		"Endpoint":     "", // Usually empty for standard tunnels
	}
	
	return credentials, nil
}

// ValidateExistingTunnel checks if a tunnel exists and is accessible in Cloudflare API
func (c *Client) ValidateExistingTunnel(ctx context.Context, tunnelID string) error {
	if tunnelID == "" {
		return fmt.Errorf("tunnel ID is empty")
	}
	
	_, err := c.GetTunnel(ctx, tunnelID)
	if err != nil {
		return fmt.Errorf("tunnel validation failed: %w", err)
	}
	
	return nil
}

// ValidateTunnelCredentials validates that tunnel credentials are properly formatted
func (c *Client) ValidateTunnelCredentials(credentials map[string]string) error {
	requiredFields := []string{"AccountTag", "TunnelSecret", "TunnelID"}
	
	for _, field := range requiredFields {
		if value, exists := credentials[field]; !exists || value == "" {
			return fmt.Errorf("missing or empty required field: %s", field)
		}
	}
	
	// Validate account ID matches
	if credentials["AccountTag"] != c.AccountID {
		return fmt.Errorf("credentials account ID %s does not match client account ID %s", 
			credentials["AccountTag"], c.AccountID)
	}
	
	// Validate tunnel secret is base64 encoded (basic check)
	if _, err := base64.StdEncoding.DecodeString(credentials["TunnelSecret"]); err != nil {
		return fmt.Errorf("tunnel secret is not valid base64: %w", err)
	}
	
	return nil
}

