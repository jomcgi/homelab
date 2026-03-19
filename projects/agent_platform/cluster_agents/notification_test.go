package main

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	natsserver "github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
)

// startTestNATSServer starts an embedded NATS server on a random port and
// returns it. The caller must call s.Shutdown() when done.
func startTestNATSServer(t *testing.T) *natsserver.Server {
	t.Helper()
	opts := &natsserver.Options{
		Host:   "127.0.0.1",
		Port:   -1, // random port
		NoLog:  true,
		NoSigs: true,
	}
	s, err := natsserver.NewServer(opts)
	if err != nil {
		t.Fatalf("failed to create NATS server: %v", err)
	}
	go s.Start()
	if !s.ReadyForConnections(5 * time.Second) {
		t.Fatal("NATS server did not become ready within 5s")
	}
	return s
}

// TestNewNotificationPublisher_ReturnsNonNil verifies that NewNotificationPublisher
// always returns a non-nil publisher, even when given a nil connection. The
// constructor itself performs no validation — callers are responsible for
// providing a live *nats.Conn before calling Notify.
func TestNewNotificationPublisher_ReturnsNonNil(t *testing.T) {
	p := NewNotificationPublisher(nil)
	if p == nil {
		t.Fatal("NewNotificationPublisher returned nil; want non-nil *NotificationPublisher")
	}
}

// TestNotify_PublishesToCorrectSubject verifies that Notify marshals the
// NotificationMessage to JSON and publishes it to the subject
// "notifications.discord.<channel>". An embedded NATS server and a subscriber
// on that subject are used to capture the message without any external
// infrastructure.
func TestNotify_PublishesToCorrectSubject(t *testing.T) {
	s := startTestNATSServer(t)
	defer s.Shutdown()

	nc, err := nats.Connect(s.ClientURL())
	if err != nil {
		t.Fatalf("failed to connect to test NATS server: %v", err)
	}
	defer nc.Close()

	const channel = "alerts"
	expectedSubject := "notifications.discord." + channel

	received := make(chan *nats.Msg, 1)
	sub, err := nc.Subscribe(expectedSubject, func(m *nats.Msg) {
		received <- m
	})
	if err != nil {
		t.Fatalf("failed to subscribe to %s: %v", expectedSubject, err)
	}
	defer sub.Unsubscribe() //nolint:errcheck

	// Flush the subscription to ensure the server has registered it before
	// we publish.
	if err := nc.Flush(); err != nil {
		t.Fatalf("nats flush: %v", err)
	}

	p := NewNotificationPublisher(nc)

	msg := NotificationMessage{
		Title:    "Disk usage critical",
		Body:     "Node /dev/sda1 is 95% full",
		Severity: "critical",
		Source:   "patrol",
		Metadata: map[string]any{
			"node": "worker-1",
		},
	}

	if err := p.Notify(context.Background(), channel, msg); err != nil {
		t.Fatalf("Notify returned unexpected error: %v", err)
	}

	select {
	case m := <-received:
		// Verify the message was published to the correct subject.
		if m.Subject != expectedSubject {
			t.Errorf("got subject %q, want %q", m.Subject, expectedSubject)
		}

		// Verify the payload is valid JSON that round-trips back to the original
		// NotificationMessage.
		var got NotificationMessage
		if err := json.Unmarshal(m.Data, &got); err != nil {
			t.Fatalf("message payload is not valid JSON: %v", err)
		}
		if got.Title != msg.Title {
			t.Errorf("Title: got %q, want %q", got.Title, msg.Title)
		}
		if got.Severity != msg.Severity {
			t.Errorf("Severity: got %q, want %q", got.Severity, msg.Severity)
		}
		if got.Source != msg.Source {
			t.Errorf("Source: got %q, want %q", got.Source, msg.Source)
		}
		if got.Body != msg.Body {
			t.Errorf("Body: got %q, want %q", got.Body, msg.Body)
		}

	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for NATS message; Notify may not have published")
	}
}

// TestNotify_MarshalFailureReturnsError verifies that when json.Marshal fails
// (e.g. when Metadata contains a non-serialisable value such as a channel),
// Notify returns a wrapped error and never attempts to call Publish. Because
// the error is returned before the *nats.Conn is touched, a nil connection is
// sufficient for this test.
func TestNotify_MarshalFailureReturnsError(t *testing.T) {
	// A nil *nats.Conn is safe here: the code returns before calling Publish.
	p := NewNotificationPublisher(nil)

	msg := NotificationMessage{
		Title:    "test",
		Severity: "info",
		Source:   "patrol",
		Metadata: map[string]any{
			// Channels cannot be marshalled to JSON; this forces json.Marshal to
			// return an error.
			"ch": make(chan int),
		},
	}

	err := p.Notify(context.Background(), "alerts", msg)
	if err == nil {
		t.Fatal("Notify returned nil; want an error when marshalling an unmarshalable value")
	}
}
