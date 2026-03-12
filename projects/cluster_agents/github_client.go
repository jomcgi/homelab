package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"time"
)

type ghAuthor struct {
	Name string    `json:"name"`
	Date time.Time `json:"date"`
}

type ghCommitDetail struct {
	Author  ghAuthor `json:"author"`
	Message string   `json:"message"`
}

type ghCommit struct {
	SHA    string         `json:"sha"`
	Commit ghCommitDetail `json:"commit"`
}

type ghHead struct {
	Ref string `json:"ref"`
	SHA string `json:"sha"`
}

type ghPullRequest struct {
	Number    int       `json:"number"`
	Head      ghHead    `json:"head"`
	PushedAt  time.Time `json:"pushed_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type ghCheckSuite struct {
	Conclusion string `json:"conclusion"`
}

type ghCheckSuitesResponse struct {
	CheckSuites []ghCheckSuite `json:"check_suites"`
}

type GitHubClient struct {
	baseURL string
	token   string
	repo    string
	client  *http.Client
}

func NewGitHubClient(baseURL, token, repo string) *GitHubClient {
	return &GitHubClient{
		baseURL: baseURL,
		token:   token,
		repo:    repo,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (g *GitHubClient) LatestNonBotCommit(ctx context.Context, branch string, botAuthors []string) (*ghCommit, error) {
	url := fmt.Sprintf("%s/repos/%s/commits?sha=%s&per_page=20", g.baseURL, g.repo, branch)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("creating request: %w", err)
	}

	req.Header.Set("Accept", "application/vnd.github+json")
	if g.token != "" {
		req.Header.Set("Authorization", "Bearer "+g.token)
	}

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetching commits: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GitHub API returned status %d", resp.StatusCode)
	}

	var commits []ghCommit
	if err := json.NewDecoder(resp.Body).Decode(&commits); err != nil {
		return nil, fmt.Errorf("decoding commits: %w", err)
	}

	for i := range commits {
		if !slices.Contains(botAuthors, commits[i].Commit.Author.Name) {
			return &commits[i], nil
		}
	}

	return nil, nil
}

func (g *GitHubClient) hasFailingChecks(ctx context.Context, sha string) (bool, error) {
	url := fmt.Sprintf("%s/repos/%s/commits/%s/check-suites", g.baseURL, g.repo, sha)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, fmt.Errorf("creating request: %w", err)
	}

	req.Header.Set("Accept", "application/vnd.github+json")
	if g.token != "" {
		req.Header.Set("Authorization", "Bearer "+g.token)
	}

	resp, err := g.client.Do(req)
	if err != nil {
		return false, fmt.Errorf("fetching check suites: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("GitHub API returned status %d", resp.StatusCode)
	}

	var result ghCheckSuitesResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false, fmt.Errorf("decoding check suites: %w", err)
	}

	for _, cs := range result.CheckSuites {
		if cs.Conclusion == "failure" {
			return true, nil
		}
	}

	return false, nil
}

func (g *GitHubClient) OpenPRsWithFailingChecks(ctx context.Context, staleThreshold time.Duration) ([]ghPullRequest, error) {
	url := fmt.Sprintf("%s/repos/%s/pulls?state=open&per_page=30", g.baseURL, g.repo)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("creating request: %w", err)
	}

	req.Header.Set("Accept", "application/vnd.github+json")
	if g.token != "" {
		req.Header.Set("Authorization", "Bearer "+g.token)
	}

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetching pull requests: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GitHub API returned status %d", resp.StatusCode)
	}

	var prs []ghPullRequest
	if err := json.NewDecoder(resp.Body).Decode(&prs); err != nil {
		return nil, fmt.Errorf("decoding pull requests: %w", err)
	}

	cutoff := time.Now().Add(-staleThreshold)
	var failing []ghPullRequest

	for _, pr := range prs {
		if pr.PushedAt.After(cutoff) {
			continue
		}

		hasFailing, err := g.hasFailingChecks(ctx, pr.Head.SHA)
		if err != nil {
			slog.Warn("failed to fetch check suites for PR, skipping",
				"pr", pr.Number,
				"sha", pr.Head.SHA,
				"error", err,
			)
			continue
		}

		if hasFailing {
			failing = append(failing, pr)
		}
	}

	return failing, nil
}
