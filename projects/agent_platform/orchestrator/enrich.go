package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// enrichment holds LLM-generated metadata for a pipeline step.
type enrichment struct {
	Title   string `json:"title"`
	Summary string `json:"summary"`
}

// enrichPipeline calls the inference endpoint to generate titles and summaries
// for each pipeline step. Returns nil on empty URL (graceful degradation).
func enrichPipeline(ctx context.Context, inferenceURL string, steps []PipelineStep) ([]enrichment, error) {
	if inferenceURL == "" || len(steps) == 0 {
		return nil, nil
	}

	var sb strings.Builder
	for i, s := range steps {
		fmt.Fprintf(&sb, "Step %d: agent=%s, task=%s\n", i+1, s.Agent, s.Task)
	}

	prompt := fmt.Sprintf(`Generate a short title (max 6 words) and summary (max 2 sentences) for each pipeline step.

Steps:
%s
Return a JSON array: [{"title": "...", "summary": "..."}] with one entry per step. Only JSON, no other text.`, sb.String())

	body, _ := json.Marshal(map[string]any{
		"model": "qwen3.5-35b-a3b",
		"messages": []map[string]string{
			{"role": "user", "content": prompt},
		},
		"temperature": 0.3,
		"max_tokens":  500,
	})

	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, inferenceURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("creating enrichment request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, nil // Graceful degradation — don't block pipeline creation.
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, nil
	}

	var llmResp struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&llmResp); err != nil {
		return nil, nil
	}

	if len(llmResp.Choices) == 0 {
		return nil, nil
	}

	content := strings.TrimSpace(llmResp.Choices[0].Message.Content)
	content = strings.TrimPrefix(content, "```json")
	content = strings.TrimSuffix(content, "```")
	content = strings.TrimSpace(content)

	var enrichments []enrichment
	if err := json.Unmarshal([]byte(content), &enrichments); err != nil {
		return nil, nil
	}

	return enrichments, nil
}
