package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type ghPullRequest struct {
	Number   int        `json:"number"`
	State    string     `json:"state"`
	MergedAt *time.Time `json:"merged_at,omitempty"`
}

type GitHubPRChecker struct {
	baseURL string
	token   string
	repo    string
	client  *http.Client
}

func NewGitHubPRChecker(baseURL, token, repo string) *GitHubPRChecker {
	return &GitHubPRChecker{
		baseURL: baseURL,
		token:   token,
		repo:    repo,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (g *GitHubPRChecker) HasOpenPR(ctx context.Context, ruleID string) (bool, error) {
	prs, err := g.listPRs(ctx, "open", fmt.Sprintf("alert:%s", ruleID))
	if err != nil {
		return false, err
	}
	return len(prs) > 0, nil
}

func (g *GitHubPRChecker) HasRecentlyMergedPR(ctx context.Context, ruleID string, window time.Duration) (bool, error) {
	prs, err := g.listPRs(ctx, "closed", fmt.Sprintf("alert:%s", ruleID))
	if err != nil {
		return false, err
	}

	cutoff := time.Now().Add(-window)
	for _, pr := range prs {
		if pr.MergedAt != nil && pr.MergedAt.After(cutoff) {
			return true, nil
		}
	}
	return false, nil
}

func (g *GitHubPRChecker) listPRs(ctx context.Context, state, label string) ([]ghPullRequest, error) {
	url := fmt.Sprintf("%s/repos/%s/pulls?state=%s&labels=%s&per_page=5", g.baseURL, g.repo, state, label)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	if g.token != "" {
		req.Header.Set("Authorization", "Bearer "+g.token)
	}
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("github list PRs: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("github returned %d", resp.StatusCode)
	}

	var prs []ghPullRequest
	if err := json.NewDecoder(resp.Body).Decode(&prs); err != nil {
		return nil, fmt.Errorf("decode github response: %w", err)
	}
	return prs, nil
}
