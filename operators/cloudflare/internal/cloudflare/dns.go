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
	"strings"

	"github.com/cloudflare/cloudflare-go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// DNSRecordConfig represents a DNS record configuration for tunnel routing
type DNSRecordConfig struct {
	Name     string // Hostname (e.g., "app.example.com")
	Type     string // Record type (typically "CNAME")
	Content  string // Target (e.g., "{TUNNEL_ID}.cfargotunnel.com")
	Proxied  bool   // Cloudflare proxy status
	TTL      int    // Time to live (1 = automatic)
	ZoneID   string // Zone ID (required for DNS operations)
	RecordID string // Record ID (for updates/deletes)
}

// CreateTunnelDNSRecord creates a CNAME DNS record pointing to a Cloudflare tunnel
// This automatically determines the zone ID from the hostname
func (c *TunnelClient) CreateTunnelDNSRecord(ctx context.Context, hostname, tunnelID string) (*DNSRecordConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.CreateTunnelDNSRecord",
		trace.WithAttributes(
			attribute.String("dns.hostname", hostname),
			attribute.String("tunnel.id", tunnelID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	// Extract zone name from hostname (e.g., "app.example.com" -> "example.com")
	zoneName, err := extractZoneName(hostname)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "invalid hostname format")
		return nil, fmt.Errorf("failed to extract zone from hostname %s: %w", hostname, err)
	}

	// Get zone ID
	zoneID, err := c.api.ZoneIDByName(zoneName)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get zone ID")
		return nil, fmt.Errorf("failed to get zone ID for %s: %w", zoneName, err)
	}

	span.SetAttributes(
		attribute.String("dns.zone.name", zoneName),
		attribute.String("dns.zone.id", zoneID),
	)

	// Create CNAME record pointing to tunnel
	tunnelTarget := fmt.Sprintf("%s.cfargotunnel.com", tunnelID)
	record := cloudflare.CreateDNSRecordParams{
		Type:    "CNAME",
		Name:    hostname,
		Content: tunnelTarget,
		Proxied: cloudflare.BoolPtr(true), // Enable Cloudflare proxy
		TTL:     1,                        // Automatic TTL
	}

	result, err := c.api.CreateDNSRecord(ctx, cloudflare.ZoneIdentifier(zoneID), record)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to create DNS record")
		return nil, fmt.Errorf("failed to create DNS record for %s: %w", hostname, err)
	}

	config := &DNSRecordConfig{
		Name:     hostname,
		Type:     "CNAME",
		Content:  tunnelTarget,
		Proxied:  true,
		TTL:      1,
		ZoneID:   zoneID,
		RecordID: result.ID,
	}

	span.SetAttributes(attribute.String("dns.record.id", result.ID))
	span.SetStatus(codes.Ok, "DNS record created")
	return config, nil
}

// DeleteDNSRecord deletes a DNS record by ID
func (c *TunnelClient) DeleteDNSRecord(ctx context.Context, zoneID, recordID string) error {
	ctx, span := c.tracer.Start(ctx, "cloudflare.DeleteDNSRecord",
		trace.WithAttributes(
			attribute.String("dns.zone.id", zoneID),
			attribute.String("dns.record.id", recordID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return err
	}

	err := c.api.DeleteDNSRecord(ctx, cloudflare.ZoneIdentifier(zoneID), recordID)
	if err != nil {
		// If record not found, consider it already deleted (idempotent)
		if IsNotFoundError(err) {
			span.SetStatus(codes.Ok, "record not found (already deleted)")
			return nil
		}
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to delete DNS record")
		return fmt.Errorf("failed to delete DNS record %s: %w", recordID, err)
	}

	span.SetStatus(codes.Ok, "DNS record deleted")
	return nil
}

// GetDNSRecordByName retrieves a DNS record by hostname
func (c *TunnelClient) GetDNSRecordByName(ctx context.Context, hostname string) (*DNSRecordConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.GetDNSRecordByName",
		trace.WithAttributes(
			attribute.String("dns.hostname", hostname),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	// Extract zone name from hostname
	zoneName, err := extractZoneName(hostname)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "invalid hostname format")
		return nil, fmt.Errorf("failed to extract zone from hostname %s: %w", hostname, err)
	}

	// Get zone ID
	zoneID, err := c.api.ZoneIDByName(zoneName)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to get zone ID")
		return nil, fmt.Errorf("failed to get zone ID for %s: %w", zoneName, err)
	}

	span.SetAttributes(
		attribute.String("dns.zone.name", zoneName),
		attribute.String("dns.zone.id", zoneID),
	)

	// List DNS records filtered by name
	records, _, err := c.api.ListDNSRecords(ctx, cloudflare.ZoneIdentifier(zoneID), cloudflare.ListDNSRecordsParams{
		Name: hostname,
	})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to list DNS records")
		return nil, fmt.Errorf("failed to list DNS records for %s: %w", hostname, err)
	}

	if len(records) == 0 {
		err := fmt.Errorf("DNS record not found for hostname: %s", hostname)
		span.SetStatus(codes.Error, "record not found")
		return nil, err
	}

	// Return the first matching record (should be unique by name)
	record := records[0]
	config := &DNSRecordConfig{
		Name:     record.Name,
		Type:     record.Type,
		Content:  record.Content,
		Proxied:  *record.Proxied,
		TTL:      record.TTL,
		ZoneID:   zoneID,
		RecordID: record.ID,
	}

	span.SetAttributes(
		attribute.String("dns.record.id", record.ID),
		attribute.String("dns.record.type", record.Type),
	)
	span.SetStatus(codes.Ok, "DNS record found")
	return config, nil
}

// ListTunnelDNSRecords lists all DNS records pointing to a specific tunnel
func (c *TunnelClient) ListTunnelDNSRecords(ctx context.Context, zoneID, tunnelID string) ([]DNSRecordConfig, error) {
	ctx, span := c.tracer.Start(ctx, "cloudflare.ListTunnelDNSRecords",
		trace.WithAttributes(
			attribute.String("dns.zone.id", zoneID),
			attribute.String("tunnel.id", tunnelID),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return nil, err
	}

	// List all CNAME records in the zone
	records, _, err := c.api.ListDNSRecords(ctx, cloudflare.ZoneIdentifier(zoneID), cloudflare.ListDNSRecordsParams{
		Type: "CNAME",
	})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to list DNS records")
		return nil, fmt.Errorf("failed to list DNS records in zone %s: %w", zoneID, err)
	}

	// Filter records pointing to this tunnel
	tunnelTarget := fmt.Sprintf("%s.cfargotunnel.com", tunnelID)
	var tunnelRecords []DNSRecordConfig

	for _, record := range records {
		if record.Content == tunnelTarget {
			tunnelRecords = append(tunnelRecords, DNSRecordConfig{
				Name:     record.Name,
				Type:     record.Type,
				Content:  record.Content,
				Proxied:  *record.Proxied,
				TTL:      record.TTL,
				ZoneID:   zoneID,
				RecordID: record.ID,
			})
		}
	}

	span.SetAttributes(attribute.Int("dns.record.count", len(tunnelRecords)))
	span.SetStatus(codes.Ok, "DNS records listed")
	return tunnelRecords, nil
}

// UpdateDNSRecord updates an existing DNS record (e.g., to point to a different tunnel)
func (c *TunnelClient) UpdateDNSRecord(ctx context.Context, config DNSRecordConfig) error {
	ctx, span := c.tracer.Start(ctx, "cloudflare.UpdateDNSRecord",
		trace.WithAttributes(
			attribute.String("dns.zone.id", config.ZoneID),
			attribute.String("dns.record.id", config.RecordID),
			attribute.String("dns.hostname", config.Name),
		),
	)
	defer span.End()

	if err := c.limiter.Wait(ctx); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "rate limiter wait failed")
		return err
	}

	params := cloudflare.UpdateDNSRecordParams{
		ID:      config.RecordID,
		Type:    config.Type,
		Name:    config.Name,
		Content: config.Content,
		Proxied: cloudflare.BoolPtr(config.Proxied),
		TTL:     config.TTL,
	}

	_, err := c.api.UpdateDNSRecord(ctx, cloudflare.ZoneIdentifier(config.ZoneID), params)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "failed to update DNS record")
		return fmt.Errorf("failed to update DNS record %s: %w", config.RecordID, err)
	}

	span.SetStatus(codes.Ok, "DNS record updated")
	return nil
}

// extractZoneName extracts the zone name from a hostname
// e.g., "app.example.com" -> "example.com"
//
//	"*.example.com" -> "example.com"
//
// This uses a simple heuristic: take the last two parts of the hostname
func extractZoneName(hostname string) (string, error) {
	// Remove wildcard prefix if present
	hostname = strings.TrimPrefix(hostname, "*.")

	parts := strings.Split(hostname, ".")
	if len(parts) < 2 {
		return "", fmt.Errorf("invalid hostname format: %s", hostname)
	}

	// Take last two parts (domain.tld)
	// This works for most cases but may fail for multi-level TLDs (e.g., .co.uk)
	// For production, consider using a proper public suffix list
	zoneName := strings.Join(parts[len(parts)-2:], ".")
	return zoneName, nil
}
