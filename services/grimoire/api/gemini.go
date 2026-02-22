package main

import (
	"context"
	"fmt"

	"github.com/google/generative-ai-go/genai"
	"golang.org/x/oauth2/google"
	"google.golang.org/api/option"
)

// GeminiClient wraps genai for embedding + generation.
type GeminiClient struct {
	client *genai.Client
}

// NewGeminiClient creates a new GeminiClient. If apiKey is empty, ADC is used;
// otherwise the API key authenticates requests.
func NewGeminiClient(ctx context.Context, apiKey string) (*GeminiClient, error) {
	var opts []option.ClientOption
	if apiKey != "" {
		opts = append(opts, option.WithAPIKey(apiKey))
	} else {
		ts, err := google.DefaultTokenSource(ctx, "https://www.googleapis.com/auth/generative-language")
		if err != nil {
			return nil, fmt.Errorf("default token source: %w", err)
		}
		opts = append(opts, option.WithTokenSource(ts))
	}

	client, err := genai.NewClient(ctx, opts...)
	if err != nil {
		return nil, fmt.Errorf("genai client: %w", err)
	}
	return &GeminiClient{client: client}, nil
}

// Embed returns a float32 embedding of text via text-embedding-005.
func (g *GeminiClient) Embed(ctx context.Context, text string) ([]float32, error) {
	em := g.client.EmbeddingModel("text-embedding-005")
	res, err := em.EmbedContent(ctx, genai.Text(text))
	if err != nil {
		return nil, fmt.Errorf("embed: %w", err)
	}
	if res.Embedding == nil {
		return nil, fmt.Errorf("embed: empty embedding")
	}
	return res.Embedding.Values, nil
}

// Generate returns a text response from gemini-2.0-flash.
func (g *GeminiClient) Generate(ctx context.Context, systemPrompt, userPrompt string) (string, error) {
	model := g.client.GenerativeModel("gemini-2.0-flash")
	model.SystemInstruction = genai.NewUserContent(genai.Text(systemPrompt))

	resp, err := model.GenerateContent(ctx, genai.Text(userPrompt))
	if err != nil {
		return "", fmt.Errorf("generate: %w", err)
	}
	if len(resp.Candidates) == 0 || resp.Candidates[0].Content == nil {
		return "", fmt.Errorf("generate: no candidates returned")
	}

	var result string
	for _, part := range resp.Candidates[0].Content.Parts {
		if t, ok := part.(genai.Text); ok {
			result += string(t)
		}
	}
	return result, nil
}

// Close closes the underlying genai client.
func (g *GeminiClient) Close() {
	g.client.Close()
}
