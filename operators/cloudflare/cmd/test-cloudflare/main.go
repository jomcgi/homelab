package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/cloudflare/cloudflare-go/v3"
)

func main() {
	// Read credentials from JSON file
	credsFile := os.Getenv("CF_CREDS_FILE")
	if credsFile == "" {
		credsFile = "/home/jomcgi/homelab/cloudflare-creds.json"
	}

	data, err := os.ReadFile(credsFile)
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

	// Create Cloudflare client
	api, err := cloudflare.NewWithAPIToken(creds.Token)
	if err != nil {
		log.Fatalf("Failed to create Cloudflare client: %v", err)
	}

	ctx := context.Background()

	fmt.Println("🧪 Testing Cloudflare API connectivity...")

	// Test 1: List zones
	fmt.Println("\n1. Testing zone listing...")
	zones, err := api.ListZones(ctx)
	if err != nil {
		log.Fatalf("Failed to list zones: %v", err)
	}
	fmt.Printf("✅ Found %d zones\n", len(zones))
	for _, zone := range zones {
		fmt.Printf("   - %s (%s)\n", zone.Name, zone.ID)
	}

	if len(zones) == 0 {
		log.Fatal("No zones found - need at least one zone for testing")
	}

	// Test 2: Try account-scoped Access Application
	fmt.Printf("\n2. Testing Access Application creation (account-scoped)...\n")
	err = testAccessApplicationAccount(ctx, api, creds.AccountID)
	if err != nil {
		fmt.Printf("❌ Account-scoped failed: %v\n", err)
	} else {
		fmt.Println("✅ Account-scoped Access Application worked!")
	}

	// Test 3: Try zone-scoped Access Application  
	fmt.Printf("\n3. Testing Access Application creation (zone-scoped)...\n")
	err = testAccessApplicationZone(ctx, api, zones[0].ID)
	if err != nil {
		fmt.Printf("❌ Zone-scoped failed: %v\n", err)
	} else {
		fmt.Println("✅ Zone-scoped Access Application worked!")
	}

	// Test 4: Try listing existing Access applications
	fmt.Printf("\n4. Testing Access Application listing...\n")
	err = testListAccessApplications(ctx, api, creds.AccountID, zones[0].ID)
	if err != nil {
		fmt.Printf("❌ Access Application listing failed: %v\n", err)
	} else {
		fmt.Println("✅ Access Application listing worked!")
	}

	// Test 5: Try tunnel creation
	fmt.Printf("\n5. Testing tunnel creation...\n")
	err = testTunnelCreation(ctx, api, creds.AccountID)
	if err != nil {
		fmt.Printf("❌ Tunnel creation failed: %v\n", err)
	} else {
		fmt.Println("✅ Tunnel creation worked!")
	}
}

func testAccessApplicationAccount(ctx context.Context, api *cloudflare.API, accountID string) error {
	fmt.Printf("   Trying: POST /accounts/%s/access/apps\n", accountID)
	
	rc := &cloudflare.ResourceContainer{
		Identifier: accountID,
		Type:       cloudflare.AccountType,
	}

	params := cloudflare.CreateAccessApplicationParams{
		Name:                   "test-k8s-app-account",
		Domain:                 "test-account.jomcgi.dev",
		Type:                   "self_hosted",
		SessionDuration:        "24h",
		AutoRedirectToIdentity: cloudflare.BoolPtr(true),
		AllowedIdps:            []string{},
	}

	app, err := api.CreateAccessApplication(ctx, rc, params)
	if err != nil {
		return err
	}

	fmt.Printf("   Created Access Application: %s (ID: %s)\n", app.Name, app.ID)
	
	// Clean up - delete the test application
	err = api.DeleteAccessApplication(ctx, rc, app.ID)
	if err != nil {
		fmt.Printf("   Warning: Failed to delete test application: %v\n", err)
	} else {
		fmt.Printf("   Cleaned up test application\n")
	}

	return nil
}

func testAccessApplicationZone(ctx context.Context, api *cloudflare.API, zoneID string) error {
	fmt.Printf("   Trying: POST /zones/%s/access/apps\n", zoneID)
	
	rc := &cloudflare.ResourceContainer{
		Identifier: zoneID,
		Type:       cloudflare.ZoneType,
	}

	params := cloudflare.CreateAccessApplicationParams{
		Name:                   "test-k8s-app-zone",
		Domain:                 "test-zone.jomcgi.dev",
		Type:                   "self_hosted",
		SessionDuration:        "24h",
		AutoRedirectToIdentity: cloudflare.BoolPtr(true),
		AllowedIdps:            []string{},
	}

	app, err := api.CreateAccessApplication(ctx, rc, params)
	if err != nil {
		return err
	}

	fmt.Printf("   Created Access Application: %s (ID: %s)\n", app.Name, app.ID)
	
	// Clean up - delete the test application
	err = api.DeleteAccessApplication(ctx, rc, app.ID)
	if err != nil {
		fmt.Printf("   Warning: Failed to delete test application: %v\n", err)
	} else {
		fmt.Printf("   Cleaned up test application\n")
	}

	return nil
}

func testTunnelCreation(ctx context.Context, api *cloudflare.API, accountID string) error {
	rc := &cloudflare.ResourceContainer{
		Identifier: accountID,
		Type:       cloudflare.AccountType,
	}

	params := cloudflare.TunnelCreateParams{
		Name:      "test-k8s-tunnel",
		Secret:    "dGVzdC1zZWNyZXQtZm9yLWs4cy10dW5uZWw=", // base64 encoded secret
		ConfigSrc: "cloudflare",
	}

	tunnel, err := api.CreateTunnel(ctx, rc, params)
	if err != nil {
		return err
	}

	fmt.Printf("   Created tunnel: %s (ID: %s)\n", tunnel.Name, tunnel.ID)
	
	// Clean up - delete the test tunnel
	err = api.DeleteTunnel(ctx, rc, tunnel.ID)
	if err != nil {
		fmt.Printf("   Warning: Failed to delete test tunnel: %v\n", err)
	} else {
		fmt.Printf("   Cleaned up test tunnel\n")
	}

	return nil
}