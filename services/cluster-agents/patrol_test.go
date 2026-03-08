package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPatrolAgent_AnalyzesFindings(t *testing.T) {
	llmServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := ChatCompletionResponse{
			Choices: []Choice{{
				Message: Message{
					Content: `[{"action_type":"orchestrator_job","finding_fingerprint":"patrol:pod:default/bad:CrashLoopBackOff","severity":"critical"}]`,
				},
			}},
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer llmServer.Close()

	findings := []Finding{{
		Fingerprint: "patrol:pod:default/bad:CrashLoopBackOff",
		Source:      "k8s:pod",
		Severity:    SeverityCritical,
		Title:       "Container CrashLoopBackOff",
		Detail:      "default/bad container app is crash-looping",
	}}

	llm := NewLLMClient(llmServer.URL, "test-model")
	patrol := &PatrolAgent{
		llm:      llm,
		interval: 5 * time.Minute,
	}

	actions, err := patrol.Analyze(context.Background(), findings)
	if err != nil {
		t.Fatal(err)
	}

	if len(actions) == 0 {
		t.Fatal("expected at least one action")
	}
	if actions[0].Type != ActionOrchestratorJob {
		t.Errorf("expected orchestrator_job action, got %s", actions[0].Type)
	}
}
