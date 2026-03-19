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

// TestNotify_NilMetadata verifies that a NotificationMessage with nil Metadata
// is serialised correctly. Because Metadata is tagged with omitempty, the JSON
// payload must NOT contain a "metadata" key when Metadata is nil, and the
// message must still be delivered to subscribers.
func TestNotify_NilMetadata(t *testing.T) {
	s := startTestNATSServer(t)
	defer s.Shutdown()

	nc, err := nats.Connect(s.ClientURL())
	if err != nil {
		t.Fatalf("failed to connect to test NATS server: %v", err)
	}
	defer nc.Close()

	const channel = "general"
	expectedSubject := "notifications.discord." + channel

	received := make(chan *nats.Msg, 1)
	sub, err := nc.Subscribe(expectedSubject, func(m *nats.Msg) {
		received <- m
	})
	if err != nil {
		t.Fatalf("failed to subscribe to %s: %v", expectedSubject, err)
	}
	defer sub.Unsubscribe() //nolint:errcheck

	if err := nc.Flush(); err != nil {
		t.Fatalf("nats flush: %v", err)
	}

	p := NewNotificationPublisher(nc)

	msg := NotificationMessage{
		Title:    "nil metadata test",
		Body:     "metadata field should be absent",
		Severity: "info",
		Source:   "patrol",
		Metadata: nil,
	}

	if err := p.Notify(context.Background(), channel, msg); err != nil {
		t.Fatalf("Notify returned unexpected error: %v", err)
	}

	select {
	case m := <-received:
		// Verify the "metadata" key is absent from the JSON payload (omitempty).
		var raw map[string]json.RawMessage
		if err := json.Unmarshal(m.Data, &raw); err != nil {
			t.Fatalf("payload is not valid JSON: %v", err)
		}
		if _, ok := raw["metadata"]; ok {
			t.Error("JSON payload contains \"metadata\" key; want it absent when Metadata is nil (omitempty)")
		}

		// Verify the remaining fields round-trip correctly.
		var got NotificationMessage
		if err := json.Unmarshal(m.Data, &got); err != nil {
			t.Fatalf("failed to unmarshal payload into NotificationMessage: %v", err)
		}
		if got.Title != msg.Title {
			t.Errorf("Title: got %q, want %q", got.Title, msg.Title)
		}

	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for NATS message")
	}
}

// TestNotify_ChannelUsedInSubject is a table-driven test that verifies the
// subject produced by Notify is always "notifications.discord.<channel>" for a
// range of channel values, including those containing dots and digits.
func TestNotify_ChannelUsedInSubject(t *testing.T) {
	cases := []struct {
		channel string
	}{
		{"general"},
		{"ops"},
		{"channel.with.dots"},
		{"123numeric"},
	}

	for _, tc := range cases {
		t.Run(tc.channel, func(t *testing.T) {
			s := startTestNATSServer(t)
			defer s.Shutdown()

			nc, err := nats.Connect(s.ClientURL())
			if err != nil {
				t.Fatalf("failed to connect to test NATS server: %v", err)
			}
			defer nc.Close()

			expectedSubject := "notifications.discord." + tc.channel

			received := make(chan *nats.Msg, 1)
			sub, err := nc.Subscribe(expectedSubject, func(m *nats.Msg) {
				received <- m
			})
			if err != nil {
				t.Fatalf("failed to subscribe to %s: %v", expectedSubject, err)
			}
			defer sub.Unsubscribe() //nolint:errcheck

			if err := nc.Flush(); err != nil {
				t.Fatalf("nats flush: %v", err)
			}

			p := NewNotificationPublisher(nc)

			msg := NotificationMessage{
				Title:    "channel routing test",
				Severity: "info",
				Source:   "patrol",
			}

			if err := p.Notify(context.Background(), tc.channel, msg); err != nil {
				t.Fatalf("Notify returned unexpected error: %v", err)
			}

			select {
			case m := <-received:
				if m.Subject != expectedSubject {
					t.Errorf("got subject %q, want %q", m.Subject, expectedSubject)
				}
			case <-time.After(3 * time.Second):
				t.Fatalf("timed out waiting for message on subject %q", expectedSubject)
			}
		})
	}
}

// TestNotify_DisconnectedConnection_ReturnsError verifies that Notify returns a
// non-nil error when the underlying NATS connection has been closed before the
// call. The embedded server is started and a connection is established, then
// the connection is explicitly closed so that the subsequent Publish call fails.
func TestNotify_DisconnectedConnection_ReturnsError(t *testing.T) {
	s := startTestNATSServer(t)
	defer s.Shutdown()

	nc, err := nats.Connect(s.ClientURL())
	if err != nil {
		t.Fatalf("failed to connect to test NATS server: %v", err)
	}

	// Close the connection before calling Notify so that Publish will fail.
	nc.Close()

	p := NewNotificationPublisher(nc)

	msg := NotificationMessage{
		Title:    "should fail",
		Severity: "info",
		Source:   "patrol",
	}

	err = p.Notify(context.Background(), "alerts", msg)
	if err == nil {
		t.Fatal("Notify returned nil; want an error when the NATS connection is closed")
	}
}

// TestNotify_MultipleMessages_DeliveredInOrder sends three distinct messages to
// the same channel and verifies that all three arrive at the subscriber in the
// same order they were published.
func TestNotify_MultipleMessages_DeliveredInOrder(t *testing.T) {
	s := startTestNATSServer(t)
	defer s.Shutdown()

	nc, err := nats.Connect(s.ClientURL())
	if err != nil {
		t.Fatalf("failed to connect to test NATS server: %v", err)
	}
	defer nc.Close()

	const channel = "ops"
	expectedSubject := "notifications.discord." + channel

	received := make(chan *nats.Msg, 10)
	sub, err := nc.Subscribe(expectedSubject, func(m *nats.Msg) {
		received <- m
	})
	if err != nil {
		t.Fatalf("failed to subscribe to %s: %v", expectedSubject, err)
	}
	defer sub.Unsubscribe() //nolint:errcheck

	if err := nc.Flush(); err != nil {
		t.Fatalf("nats flush: %v", err)
	}

	p := NewNotificationPublisher(nc)

	messages := []NotificationMessage{
		{Title: "first", Body: "message 1", Severity: "info", Source: "patrol"},
		{Title: "second", Body: "message 2", Severity: "warning", Source: "patrol"},
		{Title: "third", Body: "message 3", Severity: "critical", Source: "patrol"},
	}

	for i, msg := range messages {
		if err := p.Notify(context.Background(), channel, msg); err != nil {
			t.Fatalf("Notify[%d] returned unexpected error: %v", i, err)
		}
	}

	for i, want := range messages {
		select {
		case m := <-received:
			var got NotificationMessage
			if err := json.Unmarshal(m.Data, &got); err != nil {
				t.Fatalf("message[%d] payload is not valid JSON: %v", i, err)
			}
			if got.Title != want.Title {
				t.Errorf("message[%d] Title: got %q, want %q", i, got.Title, want.Title)
			}
			if got.Body != want.Body {
				t.Errorf("message[%d] Body: got %q, want %q", i, got.Body, want.Body)
			}
			if got.Severity != want.Severity {
				t.Errorf("message[%d] Severity: got %q, want %q", i, got.Severity, want.Severity)
			}
		case <-time.After(3 * time.Second):
			t.Fatalf("timed out waiting for message[%d]", i)
		}
	}
}
