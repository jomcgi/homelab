package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/cloudflare/cloudflare-go/v3"
	"github.com/cloudflare/cloudflare-go/v3/option"
	"github.com/cloudflare/cloudflare-go/v3/zero_trust"
)

func main() {
	// Read credentials from JSON file
	data, err := os.ReadFile("/home/jomcgi/homelab/cloudflare-creds.json")
	if err != nil {
		log.Fatalf("Failed to read credentials file: %v", err)
	}

	var creds struct {
		Token     string `json:"token"`
		AccountID string `json:"account_id"`
	}

	if err := json.Unmarshal(data, &creds); err != nil {
		log.Fatalf("Failed to parse credentials: %v", err)
	}

	fmt.Println("🧪 Testing policy creation with email list...")

	client := cloudflare.NewClient(option.WithAPIToken(creds.Token))

	// Create email rules - trying individual EmailRuleParam for each email
	emails := []string{"joe.mcginley2@gmail.com", "joe@jomcgi.dev"}
	var includeRules []zero_trust.AccessRuleUnionParam
	
	for _, email := range emails {
		// Create individual email rule for each email address
		rule := zero_trust.EmailRuleParam{
			Email: cloudflare.F(zero_trust.EmailRuleEmailParam{
				Email: cloudflare.F(email),
			}),
		}
		includeRules = append(includeRules, rule)
	}

	policy, err := client.ZeroTrust.Access.Policies.New(context.TODO(), zero_trust.AccessPolicyNewParams{
		AccountID: cloudflare.F(creds.AccountID),
		Decision:  cloudflare.F(zero_trust.DecisionAllow),
		Include:   cloudflare.F(includeRules),
		Name:      cloudflare.F("test-email-policy"),
	})
	if err != nil {
		fmt.Printf("❌ Policy creation failed: %v\n", err)
		return
	}

	fmt.Printf("✅ Created policy: %s (ID: %s)\n", policy.Name, policy.ID)

	// Clean up - delete the test policy
	_, err = client.ZeroTrust.Access.Policies.Delete(context.TODO(), policy.ID, zero_trust.AccessPolicyDeleteParams{
		AccountID: cloudflare.F(creds.AccountID),
	})
	if err != nil {
		fmt.Printf("   Warning: Failed to delete test policy: %v\n", err)
	} else {
		fmt.Printf("   Cleaned up test policy\n")
	}
}