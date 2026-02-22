package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"cloud.google.com/go/firestore"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// Chunk represents a sourcebook text chunk with its embedding vector.
type Chunk struct {
	Text        string         `json:"text"`
	Embedding   []float32      `json:"embedding"`
	SourceBook  string         `json:"source_book"`
	Page        int            `json:"page"`
	Section     string         `json:"section"`
	SectionPath string         `json:"section_path"`
	ContentType string         `json:"content_type"`
	Audience    string         `json:"audience"`
	Edition     string         `json:"edition"`
	Metadata    map[string]any `json:"metadata"`
}

func main() {
	// Structured logging.
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))

	// Graceful shutdown context.
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Configuration from environment.
	projectID := os.Getenv("GCP_PROJECT_ID")
	if projectID == "" {
		slog.Error("GCP_PROJECT_ID is required")
		os.Exit(1)
	}

	database := os.Getenv("FIRESTORE_DATABASE")
	if database == "" {
		slog.Error("FIRESTORE_DATABASE is required")
		os.Exit(1)
	}

	natsURL := envOr("NATS_URL", "nats://nats.nats.svc.cluster.local:4222")

	// Connect to Firestore.
	fs, err := firestore.NewClientWithDatabase(ctx, projectID, database)
	if err != nil {
		slog.Error("failed to connect to Firestore", "project", projectID, "database", database, "error", err)
		os.Exit(1)
	}
	defer fs.Close()
	slog.Info("connected to Firestore", "project", projectID, "database", database)

	// Connect to NATS.
	nc, err := nats.Connect(natsURL)
	if err != nil {
		slog.Error("failed to connect to NATS", "url", natsURL, "error", err)
		os.Exit(1)
	}
	defer nc.Close()
	slog.Info("connected to NATS", "url", natsURL)

	// Create JetStream context.
	js, err := jetstream.New(nc)
	if err != nil {
		slog.Error("failed to create JetStream context", "error", err)
		os.Exit(1)
	}

	// Create or update the stream.
	_, err = js.CreateOrUpdateStream(ctx, jetstream.StreamConfig{
		Name:      "GRIMOIRE_CHUNKS",
		Subjects:  []string{"grimoire.chunks.>"},
		Retention: jetstream.LimitsPolicy,
		Storage:   jetstream.FileStorage,
		Replicas:  1,
	})
	if err != nil {
		slog.Error("failed to create/update stream", "error", err)
		os.Exit(1)
	}
	slog.Info("stream ready", "name", "GRIMOIRE_CHUNKS")

	// Create durable consumer.
	cons, err := js.CreateOrUpdateConsumer(ctx, "GRIMOIRE_CHUNKS", jetstream.ConsumerConfig{
		Durable:       "chunk-writer",
		AckPolicy:     jetstream.AckExplicitPolicy,
		DeliverPolicy: jetstream.DeliverAllPolicy,
		AckWait:       30 * time.Second,
	})
	if err != nil {
		slog.Error("failed to create/update consumer", "error", err)
		os.Exit(1)
	}
	slog.Info("consumer ready", "name", "chunk-writer")

	// Consume messages until context is cancelled.
	iter, err := cons.Messages()
	if err != nil {
		slog.Error("failed to start message iterator", "error", err)
		os.Exit(1)
	}

	slog.Info("chunk-writer started, waiting for messages")

	// Stop the iterator when the context is cancelled.
	go func() {
		<-ctx.Done()
		iter.Stop()
	}()

	for {
		msg, err := iter.Next()
		if err != nil {
			// Iterator stopped (context cancelled or drain).
			slog.Info("message iterator stopped", "error", err)
			break
		}

		if err := processMessage(ctx, fs, msg); err != nil {
			slog.Error("failed to process message", "subject", msg.Subject(), "error", err)
			if nakErr := msg.Nak(); nakErr != nil {
				slog.Error("failed to nak message", "error", nakErr)
			}
			continue
		}

		if err := msg.Ack(); err != nil {
			slog.Error("failed to ack message", "error", err)
		}
	}

	slog.Info("shutting down")
}

// processMessage deserializes a chunk message and upserts it to Firestore.
func processMessage(ctx context.Context, fs *firestore.Client, msg jetstream.Msg) error {
	var chunk Chunk
	if err := json.Unmarshal(msg.Data(), &chunk); err != nil {
		return fmt.Errorf("unmarshal chunk: %w", err)
	}

	// Compute deterministic document ID.
	docID := chunkDocID(chunk.SourceBook, chunk.Page, chunk.Section, chunk.ContentType)

	// Build the document data.
	doc := map[string]any{
		"text":         chunk.Text,
		"embedding":    firestore.Vector32(chunk.Embedding),
		"source_book":  chunk.SourceBook,
		"page":         chunk.Page,
		"section":      chunk.Section,
		"section_path": chunk.SectionPath,
		"content_type": chunk.ContentType,
		"audience":     chunk.Audience,
		"edition":      chunk.Edition,
		"metadata":     chunk.Metadata,
		"updated_at":   time.Now().UTC(),
	}

	// Upsert (Set) to the sourcebook_chunks collection.
	_, err := fs.Collection("sourcebook_chunks").Doc(docID).Set(ctx, doc)
	if err != nil {
		return fmt.Errorf("firestore set: %w", err)
	}

	slog.Info("upserted chunk",
		"doc_id", docID,
		"source_book", chunk.SourceBook,
		"page", chunk.Page,
		"section", chunk.Section,
	)
	return nil
}

// chunkDocID computes a deterministic document ID from the chunk's identity fields.
// The ID is the first 32 hex characters of the SHA-256 hash of "source_book:page:section:content_type".
func chunkDocID(sourceBook string, page int, section, contentType string) string {
	key := fmt.Sprintf("%s:%d:%s:%s", sourceBook, page, section, contentType)
	h := sha256.Sum256([]byte(key))
	return fmt.Sprintf("%x", h[:16]) // 16 bytes = 32 hex chars
}

// envOr returns the value of the named environment variable, or the fallback.
func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
