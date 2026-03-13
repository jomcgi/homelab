package main

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/nats-io/nats.go"
)

// NotificationMessage represents a notification to be published via NATS.
type NotificationMessage struct {
	Title    string         `json:"title"`
	Body     string         `json:"body"`
	Severity string         `json:"severity"`
	Source   string         `json:"source"`
	Metadata map[string]any `json:"metadata,omitempty"`
}

// NotificationPublisher publishes notification messages to NATS subjects.
type NotificationPublisher struct {
	nc *nats.Conn
}

// NewNotificationPublisher creates a new NotificationPublisher with the given NATS connection.
func NewNotificationPublisher(nc *nats.Conn) *NotificationPublisher {
	return &NotificationPublisher{nc: nc}
}

// Notify publishes a notification message to the specified Discord channel via NATS.
func (p *NotificationPublisher) Notify(ctx context.Context, channel string, msg NotificationMessage) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("marshal notification: %w", err)
	}
	subject := fmt.Sprintf("notifications.discord.%s", channel)
	return p.nc.Publish(subject, data)
}
