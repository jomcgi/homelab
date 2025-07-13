package cloudflare

import (
	"context"
	"fmt"
	"os"

	cfv3 "github.com/cloudflare/cloudflare-go/v3"
	"github.com/cloudflare/cloudflare-go/v3/option"
	"github.com/cloudflare/cloudflare-go/v3/zero_trust"
)

type Client struct {
	client    *cfv3.Client
	AccountID string
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
		client:    client,
		AccountID: accountID,
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