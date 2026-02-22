# Grimoire RAG Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a RAG pipeline to Grimoire — sourcebook ingestion via NATS JetStream, vector search via Firestore, grounded answers via Gemini Flash — with a 3-service split (WS Gateway, API Service, Chunk Writer) and local PDF storage on SeaweedFS.

**Architecture:** The WS Gateway stays as a pure WebSocket relay (Redis pub/sub). A new API Service handles REST CRUD (migrated from Cloud Run) + RAG queries (Firestore vector search + Gemini Flash). A Chunk Writer consumes ingested chunks from NATS JetStream and upserts them to Firestore. A Python K8s Job handles PDF ingestion (pymupdf4llm → chunk → embed → NATS publish). GCS and Cloud Run are eliminated.

**Tech Stack:** Go 1.22+, Python 3.13, Firestore (vector search), Gemini API (text-embedding-005 + Flash), NATS JetStream, SeaweedFS (S3), Bazel (rules_go, aspect_rules_py), Helm, ArgoCD.

**Design doc:** `docs/plans/2026-02-21-grimoire-rag-design.md`

---

## Task 1: GCP Service Account + Firestore Vector Index

Manual infrastructure prerequisite. No code changes.

**Step 1: Create service account**

```bash
gcloud iam service-accounts create grimoire-gateway \
  --project=grimoire-prod \
  --display-name="Grimoire Gateway"
```

**Step 2: Grant roles**

```bash
gcloud projects add-iam-policy-binding grimoire-prod \
  --member="serviceAccount:grimoire-gateway@grimoire-prod.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding grimoire-prod \
  --member="serviceAccount:grimoire-gateway@grimoire-prod.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

**Step 3: Export JSON key and store in 1Password**

```bash
gcloud iam service-accounts keys create /tmp/grimoire-sa.json \
  --iam-account=grimoire-gateway@grimoire-prod.iam.gserviceaccount.com

# Store in 1Password: vault=k8s-homelab, item=grimoire, field=gcp_service_account
# Then delete the local copy
rm /tmp/grimoire-sa.json
```

**Step 4: Create Firestore vector index**

```bash
gcloud firestore indexes composite create \
  --project=grimoire-prod \
  --database=grimoire \
  --collection-group=sourcebook_chunks \
  --field-config=vector-config='{"dimension":"768","flat": {}}',field-path=embedding
```

Note: Vector index creation takes a few minutes. Verify with:
```bash
gcloud firestore indexes composite list --project=grimoire-prod --database=grimoire
```

---

## Task 2: Add Go Dependencies

Add `google/generative-ai-go` and `nats-io/nats.go` to the Go module so the API Service and Chunk Writer can use them.

**Files:**
- Modify: `go.mod`
- Modify: `go.sum` (auto-updated)
- Modify: `MODULE.bazel` (Gazelle updates `use_repo`)

**Step 1: Add dependencies to go.mod**

```bash
cd /tmp/claude-worktrees/grimoire-rag-design
go get github.com/google/generative-ai-go/genai@latest
go get google.golang.org/api/option@latest
go get github.com/nats-io/nats.go@latest
go mod tidy
```

**Step 2: Regenerate BUILD files**

```bash
bazelisk run gazelle
```

**Step 3: Verify build**

```bash
bazelisk build //services/grimoire/...
```

Expected: All existing targets still build.

**Step 4: Commit**

```bash
git add go.mod go.sum MODULE.bazel
git commit -m "deps(grimoire): add generative-ai-go and nats.go"
```

---

## Task 3: Add Python Dependencies

Add Python packages for the ingest pipeline.

**Files:**
- Modify: `requirements/all.txt`

**Step 1: Add dependencies**

Add these lines to `requirements/all.txt`:

```
pymupdf
pymupdf4llm
google-cloud-firestore
google-generativeai
nats-py
boto3
```

**Step 2: Update lock files**

```bash
format  # Runs all formatters including pip lock update
```

**Step 3: Verify**

```bash
bazelisk build @pip//pymupdf4llm
bazelisk build @pip//google_generativeai
bazelisk build @pip//nats_py
bazelisk build @pip//boto3
```

**Step 4: Commit**

```bash
git add requirements/
git commit -m "deps(grimoire): add Python deps for ingest pipeline"
```

---

## Task 4: Chunk Writer Service

A small Go service that subscribes to NATS JetStream (`grimoire.chunks.>`) and upserts chunks to Firestore. This is the simplest new service — no HTTP, no complex logic.

**Files:**
- Create: `services/grimoire/chunk-writer/main.go`
- Create: `services/grimoire/chunk-writer/BUILD`

**Step 1: Write the chunk writer**

Create `services/grimoire/chunk-writer/main.go`:

```go
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

// Chunk is the message format published by the ingest job.
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
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	projectID := requireEnv("GCP_PROJECT_ID")
	firestoreDB := requireEnv("FIRESTORE_DATABASE")
	natsURL := envOr("NATS_URL", "nats://nats.nats.svc.cluster.local:4222")

	// Connect to Firestore.
	fs, err := firestore.NewClientWithDatabase(ctx, projectID, firestoreDB)
	if err != nil {
		slog.Error("firestore connect failed", "error", err)
		os.Exit(1)
	}
	defer fs.Close()

	// Connect to NATS.
	nc, err := nats.Connect(natsURL)
	if err != nil {
		slog.Error("nats connect failed", "url", natsURL, "error", err)
		os.Exit(1)
	}
	defer nc.Close()

	js, err := jetstream.New(nc)
	if err != nil {
		slog.Error("jetstream init failed", "error", err)
		os.Exit(1)
	}

	// Ensure the stream exists (create if not).
	stream, err := js.CreateOrUpdateStream(ctx, jetstream.StreamConfig{
		Name:      "GRIMOIRE_CHUNKS",
		Subjects:  []string{"grimoire.chunks.>"},
		Retention: jetstream.LimitsPolicy,
		Storage:   jetstream.FileStorage,
		Replicas:  1,
	})
	if err != nil {
		slog.Error("stream create failed", "error", err)
		os.Exit(1)
	}
	slog.Info("stream ready", "name", stream.CachedInfo().Config.Name)

	// Create a durable consumer.
	cons, err := stream.CreateOrUpdateConsumer(ctx, jetstream.ConsumerConfig{
		Durable:       "chunk-writer",
		AckPolicy:     jetstream.AckExplicitPolicy,
		DeliverPolicy: jetstream.DeliverAllPolicy,
		AckWait:       30 * time.Second,
	})
	if err != nil {
		slog.Error("consumer create failed", "error", err)
		os.Exit(1)
	}

	slog.Info("chunk-writer consuming", "stream", "GRIMOIRE_CHUNKS")

	// Consume messages.
	iter, err := cons.Messages()
	if err != nil {
		slog.Error("consume failed", "error", err)
		os.Exit(1)
	}

	go func() {
		<-ctx.Done()
		iter.Stop()
	}()

	for {
		msg, err := iter.Next()
		if err != nil {
			// iter.Stop() was called — clean shutdown.
			slog.Info("consumer stopped")
			return
		}

		if err := processChunk(ctx, fs, msg); err != nil {
			slog.Error("process chunk failed", "error", err, "subject", msg.Subject())
			msg.Nak()
			continue
		}
		msg.Ack()
	}
}

func processChunk(ctx context.Context, fs *firestore.Client, msg jetstream.Msg) error {
	var chunk Chunk
	if err := json.Unmarshal(msg.Data(), &chunk); err != nil {
		return fmt.Errorf("unmarshal chunk: %w", err)
	}

	// Deterministic doc ID for idempotent upserts.
	docID := chunkDocID(chunk.SourceBook, chunk.Page, chunk.Section, chunk.ContentType)

	// Convert embedding to Firestore vector.
	embedding := firestore.Vector(make([]float64, len(chunk.Embedding)))
	for i, v := range chunk.Embedding {
		embedding[i] = float64(v)
	}

	data := map[string]any{
		"text":         chunk.Text,
		"embedding":    embedding,
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

	_, err := fs.Collection("sourcebook_chunks").Doc(docID).Set(ctx, data)
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

// chunkDocID produces a deterministic document ID from chunk identity fields.
func chunkDocID(sourceBook string, page int, section, contentType string) string {
	h := sha256.Sum256([]byte(fmt.Sprintf("%s:%d:%s:%s", sourceBook, page, section, contentType)))
	return fmt.Sprintf("%x", h[:16]) // 32-char hex string
}

func requireEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		slog.Error("required env var not set", "key", key)
		os.Exit(1)
	}
	return v
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
```

**Step 2: Write the BUILD file**

Create `services/grimoire/chunk-writer/BUILD`:

```starlark
load("@rules_go//go:def.bzl", "go_binary", "go_library")
load("//tools/oci:go_image.bzl", "go_image")

go_library(
    name = "chunk-writer_lib",
    srcs = ["main.go"],
    importpath = "github.com/jomcgi/homelab/services/grimoire/chunk-writer",
    visibility = ["//visibility:private"],
    deps = [
        "@com_google_cloud_go_firestore//:firestore",
        "@com_github_nats_io_nats_go//:nats_go",
        "@com_github_nats_io_nats_go//jetstream",
    ],
)

go_binary(
    name = "chunk-writer",
    embed = [":chunk-writer_lib"],
    visibility = ["//visibility:public"],
)

go_image(
    name = "image",
    binary = ":chunk-writer",
    repository = "ghcr.io/jomcgi/homelab/services/grimoire-chunk-writer",
)
```

**Step 3: Run Gazelle to fix deps**

```bash
bazelisk run gazelle
```

Gazelle may adjust the `deps` list in the BUILD file — check the diff and accept its changes.

**Step 4: Build**

```bash
bazelisk build //services/grimoire/chunk-writer
```

Expected: BUILD SUCCESS

**Step 5: Commit**

```bash
git add services/grimoire/chunk-writer/
git commit -m "feat(grimoire): add chunk-writer NATS consumer service"
```

---

## Task 5: API Service — Add RAG Handler

The API Service already exists at `services/grimoire/api/`. It has CRUD handlers and connects to Firestore. We need to add the RAG query endpoint and switch from Cloud Run's default service account auth to ADC via `GOOGLE_APPLICATION_CREDENTIALS`.

**Files:**
- Create: `services/grimoire/api/rag.go`
- Create: `services/grimoire/api/gemini.go`
- Modify: `services/grimoire/api/main.go` (register RAG routes, init Gemini client)
- Modify: `services/grimoire/api/BUILD` (add genai dep)

**Step 1: Write the Gemini client wrapper**

Create `services/grimoire/api/gemini.go`:

```go
package main

import (
	"context"
	"fmt"

	"github.com/google/generative-ai-go/genai"
	"google.golang.org/api/option"
)

// GeminiClient wraps the generative AI client for embedding and generation.
type GeminiClient struct {
	client *genai.Client
}

// NewGeminiClient creates a Gemini client using Application Default Credentials.
// If apiKey is provided, it uses that instead (for backward compatibility).
func NewGeminiClient(ctx context.Context, apiKey string) (*GeminiClient, error) {
	var client *genai.Client
	var err error

	if apiKey != "" {
		client, err = genai.NewClient(ctx, option.WithAPIKey(apiKey))
	} else {
		// Uses GOOGLE_APPLICATION_CREDENTIALS (ADC).
		client, err = genai.NewClient(ctx)
	}
	if err != nil {
		return nil, fmt.Errorf("genai client: %w", err)
	}
	return &GeminiClient{client: client}, nil
}

// Embed generates a 768-dim embedding vector for the given text.
func (g *GeminiClient) Embed(ctx context.Context, text string) ([]float32, error) {
	em := g.client.EmbeddingModel("text-embedding-005")
	res, err := em.EmbedContent(ctx, genai.Text(text))
	if err != nil {
		return nil, fmt.Errorf("embed: %w", err)
	}
	return res.Embedding.Values, nil
}

// Generate sends a prompt to Gemini Flash and returns the text response.
func (g *GeminiClient) Generate(ctx context.Context, systemPrompt, userPrompt string) (string, error) {
	model := g.client.GenerativeModel("gemini-2.0-flash")
	model.SystemInstruction = genai.NewUserContent(genai.Text(systemPrompt))

	resp, err := model.GenerateContent(ctx, genai.Text(userPrompt))
	if err != nil {
		return "", fmt.Errorf("generate: %w", err)
	}
	if len(resp.Candidates) == 0 || len(resp.Candidates[0].Content.Parts) == 0 {
		return "", fmt.Errorf("empty response from Gemini")
	}

	text, ok := resp.Candidates[0].Content.Parts[0].(genai.Text)
	if !ok {
		return "", fmt.Errorf("unexpected response type from Gemini")
	}
	return string(text), nil
}

// Close releases the Gemini client resources.
func (g *GeminiClient) Close() {
	g.client.Close()
}
```

**Step 2: Write the RAG handler**

Create `services/grimoire/api/rag.go`:

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"

	"cloud.google.com/go/firestore"
)

const ragSystemPrompt = `You are a D&D 5e rules assistant. Answer the question using ONLY the provided context.

Rules:
- Cite source book and page for every claim: (PHB p.96), (MM p.23)
- If the context doesn't contain enough information, say so
- Be concise and precise — players want rulings, not essays
- If multiple sources conflict, note the discrepancy and cite both

Respond in JSON format:
{
  "answer": "Your answer text with inline citations",
  "citations": [{"source_book": "PHB", "page": 96, "section": "Sneak Attack", "relevance": 0.94}]
}`

// RAGRequest is the request body for POST /api/rag/query.
type RAGRequest struct {
	Query       string   `json:"query"`
	ContentType string   `json:"content_type,omitempty"`
	Books       []string `json:"books,omitempty"`
	Edition     string   `json:"edition,omitempty"`
	CampaignID  string   `json:"campaign_id,omitempty"`
}

// RAGResponse is the response from the RAG query endpoint.
type RAGResponse struct {
	Query           string            `json:"query"`
	Answer          string            `json:"answer"`
	Citations       []Citation        `json:"citations"`
	CampaignContext []CampaignContext `json:"campaign_context,omitempty"`
}

// Citation is a source reference from a retrieved chunk.
type Citation struct {
	SourceBook  string  `json:"source_book"`
	Page        int     `json:"page"`
	Section     string  `json:"section"`
	ContentType string  `json:"content_type"`
	Relevance   float64 `json:"relevance"`
	Text        string  `json:"text"`
}

// CampaignContext is a campaign entity matching the query.
type CampaignContext struct {
	Type    string `json:"type"`
	Name    string `json:"name"`
	Summary string `json:"summary"`
}

func registerRAGRoutes(mux *http.ServeMux, fs *firestore.Client, gemini *GeminiClient) {
	mux.HandleFunc("POST /api/rag/query", handleRAGQuery(fs, gemini))
}

func handleRAGQuery(fs *firestore.Client, gemini *GeminiClient) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req RAGRequest
		if err := readJSON(r, &req); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}
		if req.Query == "" {
			httpError(w, http.StatusBadRequest, "query is required")
			return
		}

		ctx := r.Context()
		email := userEmail(r)

		// 1. Embed the query.
		queryVector, err := gemini.Embed(ctx, req.Query)
		if err != nil {
			slog.Error("embed query failed", "error", err)
			internalError(w, err)
			return
		}

		// 2. Vector search on sourcebook_chunks.
		chunks, err := vectorSearch(ctx, fs, queryVector, req, email)
		if err != nil {
			slog.Error("vector search failed", "error", err)
			internalError(w, err)
			return
		}

		// 3. Campaign context (DM only).
		var campaignCtx []CampaignContext
		if req.CampaignID != "" {
			isDM, _ := isCampaignDM(ctx, fs, req.CampaignID, email)
			if isDM {
				campaignCtx, err = searchCampaignEntities(ctx, fs, req.CampaignID, req.Query)
				if err != nil {
					slog.Warn("campaign search failed", "error", err)
					// Non-fatal — continue without campaign context.
				}
			}
		}

		// 4. Assemble context and generate answer.
		answer, citations, err := generateAnswer(ctx, gemini, req.Query, chunks, campaignCtx)
		if err != nil {
			slog.Error("generate answer failed", "error", err)
			internalError(w, err)
			return
		}

		resp := RAGResponse{
			Query:           req.Query,
			Answer:          answer,
			Citations:       citations,
			CampaignContext: campaignCtx,
		}
		writeJSON(w, http.StatusOK, resp)
	}
}

// vectorSearch performs a Firestore FindNearest query on sourcebook_chunks.
func vectorSearch(ctx context.Context, fs *firestore.Client, queryVector []float32, req RAGRequest, email string) ([]map[string]any, error) {
	// Convert float32 to float64 for Firestore.
	vec := make([]float64, len(queryVector))
	for i, v := range queryVector {
		vec[i] = float64(v)
	}

	col := fs.Collection("sourcebook_chunks")

	query := col.FindNearest("embedding",
		firestore.Vector(vec),
		5,
		firestore.DistanceMeasureCosine,
		&firestore.FindNearestOptions{})

	iter := query.Documents(ctx)
	defer iter.Stop()

	var results []map[string]any
	for {
		doc, err := iter.Next()
		if err != nil {
			break
		}
		data := doc.Data()
		data["id"] = doc.Ref.ID

		// Filter by audience — never return dm_only to non-DM users.
		audience, _ := data["audience"].(string)
		if audience == "dm_only" || audience == "spoiler" {
			// Check if user is DM for campaign context queries.
			// For sourcebook-only queries without campaign_id, skip DM-only chunks.
			if req.CampaignID == "" {
				continue
			}
			isDM, _ := isCampaignDM(ctx, fs, req.CampaignID, email)
			if !isDM {
				continue
			}
		}

		// Apply optional filters.
		if req.ContentType != "" {
			ct, _ := data["content_type"].(string)
			if ct != req.ContentType {
				continue
			}
		}
		if len(req.Books) > 0 {
			sb, _ := data["source_book"].(string)
			found := false
			for _, b := range req.Books {
				if strings.EqualFold(sb, b) {
					found = true
					break
				}
			}
			if !found {
				continue
			}
		}
		if req.Edition != "" {
			ed, _ := data["edition"].(string)
			if ed != req.Edition && ed != "both" {
				continue
			}
		}

		// Remove embedding from results (large, not needed in response).
		delete(data, "embedding")
		results = append(results, data)
	}
	return results, nil
}

// isCampaignDM checks whether the email matches the campaign's dm_user_id.
func isCampaignDM(ctx context.Context, fs *firestore.Client, campaignID, email string) (bool, error) {
	doc, err := fs.Collection("campaigns").Doc(campaignID).Get(ctx)
	if err != nil {
		return false, err
	}
	dm, _ := doc.DataAt("dm_user_id")
	return dm == email, nil
}

// searchCampaignEntities does keyword search across NPCs, locations, and factions.
func searchCampaignEntities(ctx context.Context, fs *firestore.Client, campaignID, query string) ([]CampaignContext, error) {
	queryLower := strings.ToLower(query)
	var results []CampaignContext

	// Search NPCs.
	npcs := fs.Collection("campaigns").Doc(campaignID).Collection("npcs").Documents(ctx)
	for {
		doc, err := npcs.Next()
		if err != nil {
			break
		}
		name, _ := doc.DataAt("name")
		desc, _ := doc.DataAt("description")
		nameStr, _ := name.(string)
		descStr, _ := desc.(string)
		if strings.Contains(strings.ToLower(nameStr), queryLower) ||
			strings.Contains(strings.ToLower(descStr), queryLower) {
			results = append(results, CampaignContext{
				Type:    "npc",
				Name:    nameStr,
				Summary: descStr,
			})
		}
	}

	// Search locations.
	locs := fs.Collection("campaigns").Doc(campaignID).Collection("locations").Documents(ctx)
	for {
		doc, err := locs.Next()
		if err != nil {
			break
		}
		name, _ := doc.DataAt("name")
		desc, _ := doc.DataAt("description")
		nameStr, _ := name.(string)
		descStr, _ := desc.(string)
		if strings.Contains(strings.ToLower(nameStr), queryLower) ||
			strings.Contains(strings.ToLower(descStr), queryLower) {
			results = append(results, CampaignContext{
				Type:    "location",
				Name:    nameStr,
				Summary: descStr,
			})
		}
	}

	// Search factions.
	factions := fs.Collection("campaigns").Doc(campaignID).Collection("factions").Documents(ctx)
	for {
		doc, err := factions.Next()
		if err != nil {
			break
		}
		name, _ := doc.DataAt("name")
		desc, _ := doc.DataAt("description")
		nameStr, _ := name.(string)
		descStr, _ := desc.(string)
		if strings.Contains(strings.ToLower(nameStr), queryLower) ||
			strings.Contains(strings.ToLower(descStr), queryLower) {
			results = append(results, CampaignContext{
				Type:    "faction",
				Name:    nameStr,
				Summary: descStr,
			})
		}
	}

	return results, nil
}

// generateAnswer assembles context from chunks and campaign entities, then calls Gemini Flash.
func generateAnswer(ctx context.Context, gemini *GeminiClient, query string, chunks []map[string]any, campaign []CampaignContext) (string, []Citation, error) {
	if len(chunks) == 0 && len(campaign) == 0 {
		return "No relevant information found in the ingested sourcebooks.", nil, nil
	}

	// Build context string from chunks.
	var contextParts []string
	var citations []Citation

	for _, chunk := range chunks {
		text, _ := chunk["text"].(string)
		sourceBook, _ := chunk["source_book"].(string)
		page, _ := chunk["page"].(int64)
		section, _ := chunk["section"].(string)
		contentType, _ := chunk["content_type"].(string)

		contextParts = append(contextParts,
			fmt.Sprintf("[%s p.%d — %s]\n%s", sourceBook, page, section, text))

		citations = append(citations, Citation{
			SourceBook:  sourceBook,
			Page:        int(page),
			Section:     section,
			ContentType: contentType,
			Text:        truncate(text, 200),
		})
	}

	// Add campaign context if present.
	for _, c := range campaign {
		contextParts = append(contextParts,
			fmt.Sprintf("[Campaign — %s: %s]\n%s", c.Type, c.Name, c.Summary))
	}

	userPrompt := fmt.Sprintf("Context:\n%s\n\nQuestion: %s",
		strings.Join(contextParts, "\n\n---\n\n"), query)

	answer, err := gemini.Generate(ctx, ragSystemPrompt, userPrompt)
	if err != nil {
		return "", nil, err
	}

	// Try to parse structured response from Gemini.
	var structured struct {
		Answer    string     `json:"answer"`
		Citations []Citation `json:"citations"`
	}
	if json.Unmarshal([]byte(answer), &structured) == nil && structured.Answer != "" {
		// Merge Gemini's citation relevance scores with our citations.
		for i := range citations {
			for _, gc := range structured.Citations {
				if gc.SourceBook == citations[i].SourceBook && gc.Page == citations[i].Page {
					citations[i].Relevance = gc.Relevance
				}
			}
		}
		return structured.Answer, citations, nil
	}

	// Fallback: use raw text response.
	return answer, citations, nil
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
```

**Step 3: Update main.go to init Gemini and register RAG routes**

Modify `services/grimoire/api/main.go`:

Add Gemini client initialization after the Firestore client, and register RAG routes.

```go
// After fs initialization, add:
apiKey := os.Getenv("GOOGLE_API_KEY") // Empty string = use ADC
gemini, err := NewGeminiClient(ctx, apiKey)
if err != nil {
    log.Fatalf("gemini: %v", err)
}
defer gemini.Close()

// After existing route registrations, add:
registerRAGRoutes(api, fs, gemini)
```

**Step 4: Update BUILD file**

Add the new source files and genai dependency to `services/grimoire/api/BUILD`:

Add `"gemini.go"` and `"rag.go"` to the `srcs` list. Add these deps:
```starlark
"@com_github_google_generative_ai_go//genai",
"@org_golang_google_api//option",
```

**Step 5: Run Gazelle and build**

```bash
bazelisk run gazelle
bazelisk build //services/grimoire/api
```

Expected: BUILD SUCCESS

**Step 6: Commit**

```bash
git add services/grimoire/api/
git commit -m "feat(grimoire): add RAG query handler to API service

Embeds query via text-embedding-005, vector searches sourcebook_chunks
in Firestore, optionally includes campaign context for DM users, and
generates grounded answers via Gemini Flash with citations."
```

---

## Task 6: Ingest Job (Python)

Python K8s Job that reads PDFs from SeaweedFS, chunks them by content type, embeds via Gemini, and publishes to NATS JetStream.

**Files:**
- Create: `services/grimoire/ingest/__init__.py`
- Create: `services/grimoire/ingest/main.py`
- Create: `services/grimoire/ingest/chunker.py`
- Create: `services/grimoire/ingest/BUILD`

**Step 1: Write the chunker**

Create `services/grimoire/ingest/__init__.py` (empty file).

Create `services/grimoire/ingest/chunker.py`:

```python
"""Chunking strategies for D&D sourcebook content."""

import re


def chunk_by_content_type(pages, source_book, edition="2024", audience="player_safe"):
    """Split extracted pages into typed chunks with metadata.

    Args:
        pages: List of dicts from pymupdf4llm with 'text' and 'metadata' keys.
        source_book: Book identifier (e.g., "PHB", "MM").
        edition: "2014", "2024", or "both".
        audience: Default audience classification.

    Returns:
        List of chunk dicts ready for embedding and NATS publishing.
    """
    chunks = []

    for page in pages:
        text = page.get("text", "")
        page_num = page.get("metadata", {}).get("page", 0)

        if not text.strip():
            continue

        # Detect content type from text patterns.
        if _is_stat_block(text):
            chunks.append(_make_chunk(
                text=text,
                source_book=source_book,
                page=page_num,
                section=_extract_name(text),
                content_type="stat_block",
                audience=audience,
                edition=edition,
            ))
        elif _is_spell(text):
            chunks.append(_make_chunk(
                text=text,
                source_book=source_book,
                page=page_num,
                section=_extract_name(text),
                content_type="spell",
                audience=audience,
                edition=edition,
            ))
        else:
            # Default: rule chunks with overlapping windows.
            for chunk in _window_chunk(text, source_book, page_num, edition, audience):
                chunks.append(chunk)

    return chunks


def _make_chunk(text, source_book, page, section, content_type,
                audience, edition, section_path="", metadata=None):
    return {
        "text": text,
        "source_book": source_book,
        "page": page,
        "section": section,
        "section_path": section_path,
        "content_type": content_type,
        "audience": audience,
        "edition": edition,
        "metadata": metadata or {},
    }


def _window_chunk(text, source_book, page, edition, audience,
                  window_size=512, overlap=64):
    """Split text into overlapping windows for rule content."""
    words = text.split()
    chunks = []

    # Extract section header if present (first line that looks like a heading).
    lines = text.strip().split("\n")
    section = lines[0].strip("# ").strip() if lines else "Unknown"

    for i in range(0, len(words), window_size - overlap):
        window = " ".join(words[i:i + window_size])
        if len(window.strip()) < 20:
            continue
        chunks.append(_make_chunk(
            text=window,
            source_book=source_book,
            page=page,
            section=section,
            content_type="rule",
            audience=audience,
            edition=edition,
        ))

    return chunks if chunks else [_make_chunk(
        text=text,
        source_book=source_book,
        page=page,
        section=section,
        content_type="rule",
        audience=audience,
        edition=edition,
    )]


def _is_stat_block(text):
    """Detect monster stat blocks by characteristic patterns."""
    indicators = ["Armor Class", "Hit Points", "Challenge"]
    return sum(1 for i in indicators if i in text) >= 2


def _is_spell(text):
    """Detect spell descriptions by characteristic patterns."""
    indicators = ["Casting Time", "Range", "Components", "Duration"]
    return sum(1 for i in indicators if i in text) >= 3


def _extract_name(text):
    """Extract the entity name (first non-empty line)."""
    for line in text.strip().split("\n"):
        line = line.strip("# ").strip()
        if line:
            return line
    return "Unknown"
```

**Step 2: Write the main ingest script**

Create `services/grimoire/ingest/main.py`:

```python
"""Grimoire PDF ingest pipeline.

Reads a PDF from SeaweedFS (S3), chunks it, embeds via Gemini,
and publishes chunks to NATS JetStream.
"""

import json
import logging
import os
import sys
import tempfile
import time

import boto3
import google.generativeai as genai
import nats

from chunker import chunk_by_content_type

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Batch size for embedding requests (Gemini supports up to 100).
EMBED_BATCH_SIZE = 50


def main():
    pdf_path = os.environ.get("PDF_PATH", "")
    source_book = os.environ.get("SOURCE_BOOK", "")
    edition = os.environ.get("EDITION", "2024")
    audience = os.environ.get("AUDIENCE", "player_safe")
    nats_url = os.environ.get("NATS_URL", "nats://nats.nats.svc.cluster.local:4222")
    s3_endpoint = os.environ.get("SEAWEEDFS_ENDPOINT", "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333")

    if not pdf_path or not source_book:
        log.error("PDF_PATH and SOURCE_BOOK are required")
        sys.exit(1)

    log.info("Starting ingest: %s as %s", pdf_path, source_book)

    # 1. Download PDF from SeaweedFS.
    local_pdf = download_pdf(s3_endpoint, pdf_path)

    # 2. Extract text with pymupdf4llm.
    log.info("Extracting text from PDF...")
    import pymupdf4llm
    pages = pymupdf4llm.to_markdown(local_pdf, page_chunks=True)
    log.info("Extracted %d pages", len(pages))

    # 3. Chunk by content type.
    log.info("Chunking...")
    chunks = chunk_by_content_type(pages, source_book, edition, audience)
    log.info("Created %d chunks", len(chunks))

    # 4. Embed all chunks.
    log.info("Embedding %d chunks...", len(chunks))
    embed_chunks(chunks)
    log.info("Embedding complete")

    # 5. Publish to NATS.
    log.info("Publishing to NATS...")
    import asyncio
    asyncio.run(publish_to_nats(nats_url, source_book, chunks))
    log.info("Published %d chunks to NATS", len(chunks))

    # Cleanup.
    os.unlink(local_pdf)
    log.info("Ingest complete: %s (%d chunks)", source_book, len(chunks))


def download_pdf(s3_endpoint, pdf_path):
    """Download PDF from SeaweedFS S3 bucket."""
    # pdf_path format: s3://bucket-name/key
    parts = pdf_path.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""

    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id="unused",
        aws_secret_access_key="unused",
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    s3.download_file(bucket, key, tmp.name)
    log.info("Downloaded %s to %s", pdf_path, tmp.name)
    return tmp.name


def embed_chunks(chunks):
    """Embed all chunks using Gemini text-embedding-005."""
    model = "models/text-embedding-005"

    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i:i + EMBED_BATCH_SIZE]
        texts = [c["text"] for c in batch]

        result = genai.embed_content(
            model=model,
            content=texts,
            task_type="RETRIEVAL_DOCUMENT",
        )

        for j, embedding in enumerate(result["embedding"]):
            batch[j]["embedding"] = embedding

        log.info("Embedded batch %d-%d / %d",
                 i, min(i + EMBED_BATCH_SIZE, len(chunks)), len(chunks))

        # Rate limit: Gemini embedding has 1500 RPM limit on Tier 1.
        if i + EMBED_BATCH_SIZE < len(chunks):
            time.sleep(0.5)


async def publish_to_nats(nats_url, source_book, chunks):
    """Publish all chunks to NATS JetStream."""
    nc = await nats.connect(nats_url)
    js = nc.jetstream()

    # Ensure stream exists.
    try:
        await js.find_stream_name_by_subject(f"grimoire.chunks.{source_book}")
    except nats.js.errors.NotFoundError:
        await js.add_stream(
            name="GRIMOIRE_CHUNKS",
            subjects=["grimoire.chunks.>"],
            retention="limits",
            storage="file",
        )

    subject = f"grimoire.chunks.{source_book}"

    for i, chunk in enumerate(chunks):
        payload = json.dumps(chunk).encode()
        await js.publish(subject, payload)

        if (i + 1) % 100 == 0:
            log.info("Published %d / %d chunks", i + 1, len(chunks))

    await nc.close()


if __name__ == "__main__":
    main()
```

**Step 3: Write the BUILD file**

Create `services/grimoire/ingest/BUILD`:

```starlark
load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")
load("//tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "grimoire-ingest",
    srcs = [
        "__init__.py",
        "chunker.py",
    ],
    visibility = ["//:__subpackages__"],
)

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":grimoire-ingest",
        "@pip//boto3",
        "@pip//google_generativeai",
        "@pip//nats_py",
        "@pip//pymupdf",
        "@pip//pymupdf4llm",
    ],
)

py3_image(
    name = "image",
    binary = ":main",
    repository = "ghcr.io/jomcgi/homelab/services/grimoire-ingest",
)
```

**Step 4: Run Gazelle and build**

```bash
bazelisk run gazelle
bazelisk build //services/grimoire/ingest:main
```

Expected: BUILD SUCCESS

**Step 5: Commit**

```bash
git add services/grimoire/ingest/
git commit -m "feat(grimoire): add PDF ingest pipeline

Reads PDFs from SeaweedFS, chunks by content type (stat blocks, spells,
rules with overlapping windows), embeds via Gemini text-embedding-005,
and publishes to NATS JetStream for the chunk-writer to consume."
```

---

## Task 7: Simplify WS Gateway

Remove the `GOOGLE_API_KEY` env var from the WS Gateway. It's now a pure relay — no GCP dependencies.

**Files:**
- Modify: `charts/grimoire/templates/ws-gateway-deployment.yaml` (remove GOOGLE_API_KEY env var)
- Modify: `charts/grimoire/values.yaml` (document that wsGateway no longer needs GCP)

**Step 1: Remove GOOGLE_API_KEY from ws-gateway deployment template**

In `charts/grimoire/templates/ws-gateway-deployment.yaml`, remove the `GOOGLE_API_KEY` env block:

```yaml
# DELETE these lines:
            - name: GOOGLE_API_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.grimoireSecret.name }}
                  key: google_api_key
```

**Step 2: Verify Helm template renders**

```bash
helm template grimoire charts/grimoire/ -f overlays/dev/grimoire/values.yaml | grep -A5 "ws-gateway" | head -20
```

Verify no `GOOGLE_API_KEY` appears in the ws-gateway container spec.

**Step 3: Commit**

```bash
git add charts/grimoire/
git commit -m "refactor(grimoire): remove GOOGLE_API_KEY from ws-gateway

WS Gateway is now a pure WebSocket relay with no GCP dependencies.
Gemini and Firestore access moved to the API Service."
```

---

## Task 8: Helm Chart — New Deployments

Add Helm templates for the API Service, Chunk Writer, and Ingest Job.

**Files:**
- Create: `charts/grimoire/templates/api-deployment.yaml`
- Create: `charts/grimoire/templates/api-service.yaml`
- Create: `charts/grimoire/templates/chunk-writer-deployment.yaml`
- Create: `charts/grimoire/templates/ingest-job.yaml`
- Create: `charts/grimoire/templates/gcp-sa-secret.yaml`
- Modify: `charts/grimoire/values.yaml` (add api, chunkWriter, ingest sections)
- Modify: `charts/grimoire/templates/nginx-configmap.yaml` (proxy /api to API Service)
- Modify: `overlays/dev/grimoire/values.yaml` (add image overrides)

**Step 1: Add values.yaml entries**

Add to `charts/grimoire/values.yaml` after the existing `redis` section:

```yaml
# API Service — REST CRUD + RAG query handler
api:
  replicaCount: 1
  image:
    repository: ghcr.io/jomcgi/homelab/services/grimoire-api
    tag: main
    pullPolicy: Always
  service:
    type: ClusterIP
    port: 8080
  env:
    gcpProjectID: "grimoire-prod"
    firestoreDatabase: "grimoire"
    cfAccessTeam: ""
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 500m
      memory: 256Mi

# Chunk Writer — NATS consumer, upserts to Firestore
chunkWriter:
  replicaCount: 1
  image:
    repository: ghcr.io/jomcgi/homelab/services/grimoire-chunk-writer
    tag: main
    pullPolicy: Always
  env:
    natsURL: "nats://nats.nats.svc.cluster.local:4222"
    gcpProjectID: "grimoire-prod"
    firestoreDatabase: "grimoire"
  resources:
    requests:
      cpu: 50m
      memory: 64Mi
    limits:
      cpu: 200m
      memory: 128Mi

# Ingest Job — PDF processing, on-demand
ingest:
  image:
    repository: ghcr.io/jomcgi/homelab/services/grimoire-ingest
    tag: main
    pullPolicy: Always
  env:
    natsURL: "nats://nats.nats.svc.cluster.local:4222"
    seaweedfsEndpoint: "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333"
    gcpProjectID: "grimoire-prod"
    firestoreDatabase: "grimoire"
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: "2"
      memory: 1Gi

# GCP service account for Firestore + Gemini API access
gcpServiceAccount:
  enabled: true
  secretName: grimoire
  secretKey: gcp_service_account
  mountPath: /var/run/secrets/gcp/sa.json
```

**Step 2: Create GCP SA secret mount template**

Create `charts/grimoire/templates/gcp-sa-secret.yaml`:

This is handled by the existing `OnePasswordItem` in `externalsecret.yaml`. The SA key is stored as a field in the `grimoire` 1Password item. No new template needed — we just mount the existing secret in the new deployments.

**Step 3: Create API Service deployment**

Create `charts/grimoire/templates/api-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "grimoire.fullname" . }}-api
  labels:
    {{- include "grimoire.labels" . | nindent 4 }}
    app.kubernetes.io/component: api
spec:
  replicas: {{ .Values.api.replicaCount }}
  selector:
    matchLabels:
      {{- include "grimoire.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api
  template:
    metadata:
      labels:
        {{- include "grimoire.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: api
    spec:
      {{- if .Values.imagePullSecret.enabled }}
      imagePullSecrets:
        - name: ghcr-imagepull-secret
      {{- end }}
      serviceAccountName: {{ include "grimoire.serviceAccountName" . }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        runAsGroup: 65532
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          image: "{{ .Values.api.image.repository }}:{{ .Values.api.image.tag }}"
          imagePullPolicy: {{ .Values.api.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          env:
            - name: GCP_PROJECT_ID
              value: {{ .Values.api.env.gcpProjectID | quote }}
            - name: FIRESTORE_DATABASE
              value: {{ .Values.api.env.firestoreDatabase | quote }}
            - name: CF_ACCESS_TEAM
              value: {{ .Values.api.env.cfAccessTeam | quote }}
            {{- if .Values.gcpServiceAccount.enabled }}
            - name: GOOGLE_APPLICATION_CREDENTIALS
              value: {{ .Values.gcpServiceAccount.mountPath | quote }}
            {{- end }}
          {{- if .Values.gcpServiceAccount.enabled }}
          volumeMounts:
            - name: gcp-sa
              mountPath: {{ dir .Values.gcpServiceAccount.mountPath }}
              readOnly: true
          {{- end }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
            readOnlyRootFilesystem: true
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
          resources:
            {{- toYaml .Values.api.resources | nindent 12 }}
      {{- if .Values.gcpServiceAccount.enabled }}
      volumes:
        - name: gcp-sa
          secret:
            secretName: {{ .Values.gcpServiceAccount.secretName }}
            items:
              - key: {{ .Values.gcpServiceAccount.secretKey }}
                path: sa.json
      {{- end }}
```

**Step 4: Create API Service service**

Create `charts/grimoire/templates/api-service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "grimoire.fullname" . }}-api
  labels:
    {{- include "grimoire.labels" . | nindent 4 }}
    app.kubernetes.io/component: api
spec:
  type: {{ .Values.api.service.type }}
  ports:
    - port: {{ .Values.api.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "grimoire.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: api
```

**Step 5: Create Chunk Writer deployment**

Create `charts/grimoire/templates/chunk-writer-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "grimoire.fullname" . }}-chunk-writer
  labels:
    {{- include "grimoire.labels" . | nindent 4 }}
    app.kubernetes.io/component: chunk-writer
spec:
  replicas: {{ .Values.chunkWriter.replicaCount }}
  selector:
    matchLabels:
      {{- include "grimoire.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: chunk-writer
  template:
    metadata:
      annotations:
        config.linkerd.io/skip-outbound-ports: "4222"
      labels:
        {{- include "grimoire.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: chunk-writer
    spec:
      {{- if .Values.imagePullSecret.enabled }}
      imagePullSecrets:
        - name: ghcr-imagepull-secret
      {{- end }}
      serviceAccountName: {{ include "grimoire.serviceAccountName" . }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        runAsGroup: 65532
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: chunk-writer
          image: "{{ .Values.chunkWriter.image.repository }}:{{ .Values.chunkWriter.image.tag }}"
          imagePullPolicy: {{ .Values.chunkWriter.image.pullPolicy }}
          env:
            - name: NATS_URL
              value: {{ .Values.chunkWriter.env.natsURL | quote }}
            - name: GCP_PROJECT_ID
              value: {{ .Values.chunkWriter.env.gcpProjectID | quote }}
            - name: FIRESTORE_DATABASE
              value: {{ .Values.chunkWriter.env.firestoreDatabase | quote }}
            {{- if .Values.gcpServiceAccount.enabled }}
            - name: GOOGLE_APPLICATION_CREDENTIALS
              value: {{ .Values.gcpServiceAccount.mountPath | quote }}
            {{- end }}
          {{- if .Values.gcpServiceAccount.enabled }}
          volumeMounts:
            - name: gcp-sa
              mountPath: {{ dir .Values.gcpServiceAccount.mountPath }}
              readOnly: true
          {{- end }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
            readOnlyRootFilesystem: true
          resources:
            {{- toYaml .Values.chunkWriter.resources | nindent 12 }}
      {{- if .Values.gcpServiceAccount.enabled }}
      volumes:
        - name: gcp-sa
          secret:
            secretName: {{ .Values.gcpServiceAccount.secretName }}
            items:
              - key: {{ .Values.gcpServiceAccount.secretKey }}
                path: sa.json
      {{- end }}
```

**Step 6: Create Ingest Job template**

Create `charts/grimoire/templates/ingest-job.yaml`:

```yaml
{{- /*
Ingest Job template — not auto-deployed.
Create a job manually:
  kubectl create job grimoire-ingest-phb --from=job/grimoire-ingest \
    -- --env PDF_PATH=s3://grimoire-sourcebooks/phb.pdf \
       --env SOURCE_BOOK=PHB
*/ -}}
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "grimoire.fullname" . }}-ingest
  labels:
    {{- include "grimoire.labels" . | nindent 4 }}
    app.kubernetes.io/component: ingest
  annotations:
    argocd.argoproj.io/hook: Skip
spec:
  backoffLimit: 1
  template:
    metadata:
      annotations:
        config.linkerd.io/skip-outbound-ports: "4222,8333"
      labels:
        {{- include "grimoire.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: ingest
    spec:
      restartPolicy: Never
      {{- if .Values.imagePullSecret.enabled }}
      imagePullSecrets:
        - name: ghcr-imagepull-secret
      {{- end }}
      serviceAccountName: {{ include "grimoire.serviceAccountName" . }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        runAsGroup: 65532
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: ingest
          image: "{{ .Values.ingest.image.repository }}:{{ .Values.ingest.image.tag }}"
          imagePullPolicy: {{ .Values.ingest.image.pullPolicy }}
          env:
            - name: NATS_URL
              value: {{ .Values.ingest.env.natsURL | quote }}
            - name: SEAWEEDFS_ENDPOINT
              value: {{ .Values.ingest.env.seaweedfsEndpoint | quote }}
            - name: GCP_PROJECT_ID
              value: {{ .Values.ingest.env.gcpProjectID | quote }}
            - name: PDF_PATH
              value: ""
            - name: SOURCE_BOOK
              value: ""
            - name: EDITION
              value: "2024"
            - name: AUDIENCE
              value: "player_safe"
            {{- if .Values.gcpServiceAccount.enabled }}
            - name: GOOGLE_APPLICATION_CREDENTIALS
              value: {{ .Values.gcpServiceAccount.mountPath | quote }}
            {{- end }}
          {{- if .Values.gcpServiceAccount.enabled }}
          volumeMounts:
            - name: gcp-sa
              mountPath: {{ dir .Values.gcpServiceAccount.mountPath }}
              readOnly: true
          {{- end }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
          resources:
            {{- toYaml .Values.ingest.resources | nindent 12 }}
      {{- if .Values.gcpServiceAccount.enabled }}
      volumes:
        - name: gcp-sa
          secret:
            secretName: {{ .Values.gcpServiceAccount.secretName }}
            items:
              - key: {{ .Values.gcpServiceAccount.secretKey }}
                path: sa.json
      {{- end }}
```

**Step 7: Update Nginx configmap to proxy /api to API Service**

In `charts/grimoire/templates/nginx-configmap.yaml`, add an upstream and location block for the API Service. The existing config already has a `ws_gateway` upstream. Add:

```nginx
upstream api_service {
    server {{ include "grimoire.fullname" . }}-api:{{ .Values.api.service.port }};
}
```

And add a location block before the SPA fallback:

```nginx
location /api/ {
    proxy_pass http://api_service;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 30s;
}
```

**Step 8: Update overlays/dev/grimoire/values.yaml**

Add image overrides and the `cfAccessTeam` for the API service:

```yaml
# API Service
api:
  env:
    cfAccessTeam: jomcgi.cloudflareaccess.com
  image:
    repository: ghcr.io/jomcgi/homelab/services/grimoire-api
    tag: main
    pullPolicy: Always
```

Add Image Updater entries for the new services:

```yaml
  - alias: api
    imageName: ghcr.io/jomcgi/homelab/services/grimoire-api:main
    helm:
      name: api.image.repository
      tag: api.image.tag
  - alias: chunk-writer
    imageName: ghcr.io/jomcgi/homelab/services/grimoire-chunk-writer:main
    helm:
      name: chunkWriter.image.repository
      tag: chunkWriter.image.tag
```

**Step 9: Verify Helm template renders**

```bash
helm template grimoire charts/grimoire/ -f overlays/dev/grimoire/values.yaml
```

Check for:
- API deployment with GCP SA volume mount
- Chunk Writer deployment with NATS and GCP SA
- Ingest Job with `argocd.argoproj.io/hook: Skip`
- Nginx config with `/api/` proxy_pass
- No `GOOGLE_API_KEY` in ws-gateway

**Step 10: Commit**

```bash
git add charts/grimoire/ overlays/dev/grimoire/
git commit -m "feat(grimoire): add Helm templates for API, chunk-writer, and ingest

Adds three new workloads to the grimoire chart:
- API Service: REST CRUD + RAG query handler
- Chunk Writer: NATS consumer → Firestore upserts
- Ingest Job: PDF processing (skip hook, run manually)

Updates Nginx to proxy /api/ to the API Service.
Configures GCP service account mounting via 1Password."
```

---

## Task 9: Frontend — Wire Rule Lookup

The `DMPrep.tsx` already has a Rule Lookup search input. Wire it to the API Service's `POST /api/rag/query` endpoint and render results.

**Files:**
- Modify: `services/grimoire/frontend/src/routes/DMPrep.tsx`
- Modify: `services/grimoire/frontend/src/lib/api.ts` (already has `useRAGQuery` — just needs response type)
- Modify: `services/grimoire/frontend/src/types/index.ts` (add RAG types if needed)

**Step 1: Check existing types**

Read `services/grimoire/frontend/src/types/index.ts` (or wherever types are defined) to understand existing type patterns before adding RAG types.

**Step 2: Update useRAGQuery response type in api.ts**

The existing `useRAGQuery` in `api.ts` already calls `POST /api/rag/query`. Add the response type:

```typescript
export interface RAGResult {
  query: string;
  answer: string;
  citations: {
    source_book: string;
    page: number;
    section: string;
    content_type: string;
    relevance: number;
    text: string;
  }[];
  campaign_context?: {
    type: string;
    name: string;
    summary: string;
  }[];
}

export function useRAGQuery() {
  return useMutation({
    mutationFn: (params: {
      query: string;
      content_type?: string;
      books?: string[];
      edition?: string;
      campaign_id?: string;
    }) => postJSON<RAGResult>("/rag/query", params),
  });
}
```

**Step 3: Wire the search input in DMPrep.tsx**

In `DMPrep.tsx`, replace the static search input with a functional one that calls `useRAGQuery` and renders results below the input. Use `useState` for the query text, call the mutation on Enter/submit, and render the answer + citations.

Key UI elements to render:
- Answer text
- Citations as pills: `PHB p.96 — Sneak Attack`
- Loading state while waiting for Gemini
- Error state

**Step 4: Build frontend**

```bash
bazelisk build //services/grimoire/frontend:image
```

Expected: BUILD SUCCESS

**Step 5: Commit**

```bash
git add services/grimoire/frontend/
git commit -m "feat(grimoire): wire Rule Lookup to RAG query endpoint

DMPrep search bar now calls POST /api/rag/query and renders
grounded answers with source book + page citations."
```

---

## Task 10: End-to-End Verification

**Step 1: Build all images**

```bash
bazelisk build //services/grimoire/api:image
bazelisk build //services/grimoire/chunk-writer:image
bazelisk build //services/grimoire/ingest:image
bazelisk build //services/grimoire/ws-gateway:image
bazelisk build //services/grimoire/frontend:image
```

**Step 2: Verify Helm template renders cleanly**

```bash
helm template grimoire charts/grimoire/ -f overlays/dev/grimoire/values.yaml --debug 2>&1 | head -50
```

**Step 3: Push images and let ArgoCD sync**

```bash
bazelisk run //services/grimoire/api/image:push
bazelisk run //services/grimoire/chunk-writer/image:push
bazelisk run //services/grimoire/ws-gateway/image:push
bazelisk run //services/grimoire/frontend/image:push
```

**Step 4: Create SeaweedFS bucket and upload a test PDF**

```bash
# Port-forward SeaweedFS S3
kubectl port-forward svc/seaweedfs-s3 8333:8333 -n seaweedfs &

# Create bucket and upload
aws --endpoint-url http://localhost:8333 s3 mb s3://grimoire-sourcebooks
aws --endpoint-url http://localhost:8333 s3 cp ./test-sourcebook.pdf s3://grimoire-sourcebooks/
```

**Step 5: Run ingest job**

```bash
bazelisk run //services/grimoire/ingest:image.push

kubectl create job grimoire-ingest-test \
  --namespace=grimoire \
  --image=ghcr.io/jomcgi/homelab/services/grimoire-ingest:main \
  -- python main.py

# Override env vars for the job:
kubectl set env job/grimoire-ingest-test \
  PDF_PATH=s3://grimoire-sourcebooks/test-sourcebook.pdf \
  SOURCE_BOOK=TEST
```

Or apply a job manifest with the correct env vars directly.

**Step 6: Verify chunks in Firestore**

```bash
# Check Firestore via gcloud
gcloud firestore documents list \
  --project=grimoire-prod \
  --database=grimoire \
  --collection=sourcebook_chunks \
  --limit=5
```

**Step 7: Test RAG query**

```bash
# Port-forward the API service
kubectl port-forward svc/grimoire-api 8080:8080 -n grimoire &

curl -X POST http://localhost:8080/api/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test query"}'
```

**Step 8: Create PR**

```bash
git push -u origin docs/grimoire-rag-design
gh pr create --title "feat(grimoire): RAG pipeline with 3-service split" --body "$(cat <<'EOF'
## Summary
- Adds RAG pipeline: sourcebook ingestion → NATS JetStream → Firestore vector search → Gemini Flash grounded answers
- Splits grimoire into 3 services: WS Gateway (relay), API Service (CRUD + RAG), Chunk Writer (NATS consumer)
- Eliminates Cloud Run and GCS — all compute runs in-cluster, PDFs stored on SeaweedFS
- GCP reduced to Firestore (vector search) + Gemini API (embedding + Flash) only

## New services
- **API Service** (`services/grimoire/api/`): REST CRUD + RAG query handler
- **Chunk Writer** (`services/grimoire/chunk-writer/`): NATS → Firestore upserts
- **Ingest Job** (`services/grimoire/ingest/`): PDF → chunk → embed → NATS

## Design doc
`docs/plans/2026-02-21-grimoire-rag-design.md`

## Test plan
- [ ] All images build: `bazelisk build //services/grimoire/...`
- [ ] Helm template renders: `helm template grimoire charts/grimoire/ -f overlays/dev/grimoire/values.yaml`
- [ ] GCP service account created with Firestore + Gemini roles
- [ ] Firestore vector index created on `sourcebook_chunks.embedding`
- [ ] Ingest job processes a test PDF → chunks appear in Firestore
- [ ] RAG query returns grounded answer with citations
- [ ] Frontend Rule Lookup renders results
EOF
)"
```
