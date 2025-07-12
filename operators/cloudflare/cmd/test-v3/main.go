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

	fmt.Println("🧪 Testing Cloudflare API v3 SDK...")

	client := cloudflare.NewClient(
		option.WithAPIToken(creds.Token),
	)

	fmt.Println("\n1. Testing Access Application creation with v3 SDK...")
	
	application, err := client.ZeroTrust.Access.Applications.New(context.TODO(), zero_trust.AccessApplicationNewParams{
		AccountID: cloudflare.F(creds.AccountID),
		Body: zero_trust.AccessApplicationNewParamsBodySelfHostedApplication{
			Domain: cloudflare.F("test-v3.jomcgi.dev"),
			Type:   cloudflare.F("self_hosted"),
			Name:   cloudflare.F("test-k8s-app-v3"),
			SessionDuration: cloudflare.F("24h"),
		},
	})
	if err != nil {
		fmt.Printf("❌ v3 SDK failed: %v\n", err)
		return
	}

	fmt.Printf("✅ v3 SDK worked! Created: %s (ID: %s)\n", application.Name, application.ID)

	// Clean up - delete the test application
	_, err = client.ZeroTrust.Access.Applications.Delete(context.TODO(), application.ID, zero_trust.AccessApplicationDeleteParams{
		AccountID: cloudflare.F(creds.AccountID),
	})
	if err != nil {
		fmt.Printf("   Warning: Failed to delete test application: %v\n", err)
	} else {
		fmt.Printf("   Cleaned up test application\n")
	}
}