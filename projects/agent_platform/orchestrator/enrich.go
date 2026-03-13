package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

// enrichment holds LLM-generated metadata for a pipeline step.
type enrichment struct {
	Title   string `json:"title"`
	Summary string `json:"summary"`
}

// enrichResult holds per-step enrichments plus a pipeline-level summary.
type enrichResult struct {
	Steps           []enrichment `json:"steps"`
	PipelineSummary string       `json:"pipeline_summary"`
}

// enrichPipeline calls the inference endpoint to generate titles, summaries,
// and an overall pipeline summary. Returns zero value on empty URL (graceful degradation).
func enrichPipeline(ctx context.Context, logger *slog.Logger, inferenceURL string, steps []PipelineStep) (enrichResult, error) {
	if inferenceURL == "" || len(steps) == 0 {
		return enrichResult{}, nil
	}

	var sb strings.Builder
	for i, s := range steps {
		fmt.Fprintf(&sb, "Step %d: agent=%s, task=%s\n", i+1, s.Agent, s.Task)
	}

	prompt := fmt.Sprintf(`Generate a short title (max 6 words) and summary (max 2 sentences) for each pipeline step, plus a brief overall pipeline summary (max 10 words).

Steps:
%s
Return JSON: {"steps": [{"title": "...", "summary": "..."}], "pipeline_summary": "..."} with one entry per step. Only JSON, no other text.`, sb.String())

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
		return enrichResult{}, fmt.Errorf("creating enrichment request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		logger.Warn("pipeline enrichment: inference request failed", "error", err)
		return enrichResult{}, nil // Graceful degradation — don't block pipeline creation.
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		logger.Warn("pipeline enrichment: inference returned non-200", "status", resp.StatusCode)
		return enrichResult{}, nil
	}

	var llmResp struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&llmResp); err != nil {
		logger.Warn("pipeline enrichment: failed to decode inference response", "error", err)
		return enrichResult{}, nil
	}

	if len(llmResp.Choices) == 0 {
		logger.Warn("pipeline enrichment: inference returned no choices")
		return enrichResult{}, nil
	}

	content := strings.TrimSpace(llmResp.Choices[0].Message.Content)
	content = strings.TrimPrefix(content, "```json")
	content = strings.TrimSuffix(content, "```")
	content = strings.TrimSpace(content)

	// Try new format first: {"steps": [...], "pipeline_summary": "..."}
	var result enrichResult
	if err := json.Unmarshal([]byte(content), &result); err == nil && len(result.Steps) > 0 {
		return result, nil
	}

	// Fall back to old format: [{"title": "...", "summary": "..."}]
	var stepEnrichments []enrichment
	if err := json.Unmarshal([]byte(content), &stepEnrichments); err != nil {
		logger.Warn("pipeline enrichment: failed to parse LLM content as JSON", "content", content)
		return enrichResult{}, nil
	}

	logger.Warn("pipeline enrichment: LLM used old format, pipeline_summary will be empty")
	return enrichResult{Steps: stepEnrichments}, nil
}
