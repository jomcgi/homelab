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

// Summarizer calls an OpenAI-compatible LLM to generate short titles and
// summaries for agent tasks and plans.
type Summarizer struct {
	inferenceURL string
	model        string
	logger       *slog.Logger
}

// NewSummarizer creates a Summarizer that calls the given inference endpoint.
func NewSummarizer(inferenceURL, model string, logger *slog.Logger) *Summarizer {
	return &Summarizer{inferenceURL: inferenceURL, model: model, logger: logger}
}

// SummarizeTask generates a short title from raw task text.
// Returns zero values without error if the receiver is nil or inferenceURL is empty.
func (s *Summarizer) SummarizeTask(ctx context.Context, task string) (string, error) {
	if s == nil || s.inferenceURL == "" {
		return "", nil
	}
	systemPrompt := "You generate short titles for agent tasks. Respond with JSON containing \"title\" (max 10 words, no quotes around it)."
	userPrompt := "Task: " + task
	result, err := s.callLLM(ctx, systemPrompt, userPrompt, []string{"title"})
	if err != nil {
		return "", err
	}
	return result["title"], nil
}

// SummarizePlan generates a title and summary from the task and its plan steps.
// Returns zero values without error if the receiver is nil or inferenceURL is empty.
func (s *Summarizer) SummarizePlan(ctx context.Context, task string, plan []PlanStep) (string, string, error) {
	if s == nil || s.inferenceURL == "" {
		return "", "", nil
	}
	var sb strings.Builder
	sb.WriteString("Job task: ")
	sb.WriteString(task)
	sb.WriteString("\n\nPlan steps:\n")
	for i, step := range plan {
		fmt.Fprintf(&sb, "%d. [%s] %s (agent: %s)\n", i+1, step.Status, step.Description, step.Agent)
	}
	systemPrompt := "You summarize agent job plans. Respond with JSON containing \"title\" (short, max 10 words) and \"summary\" (1-2 sentences)."
	result, err := s.callLLM(ctx, systemPrompt, sb.String(), []string{"title", "summary"})
	if err != nil {
		return "", "", err
	}
	return result["title"], result["summary"], nil
}

// callLLM sends a chat completion request to the OpenAI-compatible endpoint
// and parses the JSON response into a map of the requested fields.
func (s *Summarizer) callLLM(ctx context.Context, systemPrompt, userPrompt string, fields []string) (map[string]string, error) {
	properties := make(map[string]any, len(fields))
	for _, f := range fields {
		properties[f] = map[string]string{"type": "string"}
	}
	reqBody := map[string]any{
		"model": s.model,
		"messages": []map[string]string{
			{"role": "system", "content": systemPrompt},
			{"role": "user", "content": userPrompt},
		},
		"temperature": 0.3,
		"max_tokens":  256,
		"response_format": map[string]any{
			"type": "json_schema",
			"json_schema": map[string]any{
				"name":   "summary_response",
				"strict": true,
				"schema": map[string]any{
					"type":                 "object",
					"properties":           properties,
					"required":             fields,
					"additionalProperties": false,
				},
			},
		},
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	callCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(callCtx, http.MethodPost, s.inferenceURL+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("inference request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("inference returned %d", resp.StatusCode)
	}

	var chatResp struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&chatResp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	if len(chatResp.Choices) == 0 {
		return nil, fmt.Errorf("no choices in response")
	}

	var result map[string]string
	if err := json.Unmarshal([]byte(chatResp.Choices[0].Message.Content), &result); err != nil {
		s.logger.Error("failed to parse summary JSON", "content", chatResp.Choices[0].Message.Content, "error", err)
		return nil, fmt.Errorf("parse summary JSON: %w", err)
	}
	return result, nil
}
