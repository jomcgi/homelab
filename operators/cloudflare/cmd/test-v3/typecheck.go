package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"encoding/json"
	"github.com/cloudflare/cloudflare-go/v3"
	"github.com/cloudflare/cloudflare-go/v3/option"
	"github.com/cloudflare/cloudflare-go/v3/zero_trust"
)

func main() {
	data, err := os.ReadFile("/home/jomcgi/homelab/cloudflare-creds.json")
	if err != nil {
		log.Fatal(err)
	}
	var creds struct {
		Token     string `json:"token"`
		AccountID string `json:"account_id"`
	}
	json.Unmarshal(data, &creds)
	
	client := cloudflare.NewClient(option.WithAPIToken(creds.Token))
	
	// Check the real type
	app, err := client.ZeroTrust.Access.Applications.New(context.TODO(), zero_trust.AccessApplicationNewParams{
		AccountID: cloudflare.F(creds.AccountID),
		Body: zero_trust.AccessApplicationNewParamsBodySelfHostedApplication{
			Domain: cloudflare.F("test.example.com"),
			Type:   cloudflare.F("self_hosted"),
			Name:   cloudflare.F("test"),
			SessionDuration: cloudflare.F("24h"),
		},
	})
	if err != nil {
		log.Printf("Error (expected): %v", err)
	}
	fmt.Printf("Type: %T\n", app)
}
