package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
)

type GitActivityGate struct {
	github       *GitHubClient
	orchestrator *OrchestratorClient
	botAuthors   []string
	branch       string
}

func NewGitActivityGate(github *GitHubClient, orchestrator *OrchestratorClient, botAuthors []string, branch string) *GitActivityGate {
	return &GitActivityGate{
		github:       github,
		orchestrator: orchestrator,
		botAuthors:   botAuthors,
		branch:       branch,
	}
}

// Check determines whether there are new non-bot commits on the branch since
// the last orchestrator job with the given tag. It returns the commit range,
// whether there is new activity, and any error.
func (g *GitActivityGate) Check(ctx context.Context, tag string) (commitRange string, hasActivity bool, err error) {
	latest, err := g.github.LatestNonBotCommit(ctx, g.branch, g.botAuthors)
	if err != nil {
		return "", false, fmt.Errorf("fetching latest commit: %w", err)
	}
	if latest == nil {
		return "", false, nil
	}

	lastSHA, err := g.lastProcessedCommit(ctx, tag)
	if err != nil {
		return "", false, fmt.Errorf("fetching last processed commit: %w", err)
	}

	if lastSHA == latest.SHA {
		return "", false, nil
	}

	if lastSHA == "" {
		return latest.SHA, true, nil
	}

	return fmt.Sprintf("%s..%s", lastSHA, latest.SHA), true, nil
}

// lastProcessedCommit queries the orchestrator for the last SUCCEEDED job with
// the given tag and returns its commit SHA. Returns empty string if no jobs exist.
func (g *GitActivityGate) lastProcessedCommit(ctx context.Context, tag string) (string, error) {
	u := fmt.Sprintf("%s/jobs?status=%s&tags=%s&limit=1",
		g.orchestrator.baseURL,
		url.QueryEscape("SUCCEEDED"),
		url.QueryEscape(tag),
	)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return "", err
	}

	resp, err := g.orchestrator.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("orchestrator list jobs: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("orchestrator returned %d", resp.StatusCode)
	}

	var result orchestratorListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("decode orchestrator response: %w", err)
	}

	if result.Total == 0 {
		return "", nil
	}

	return result.Jobs[0].ID, nil
}
