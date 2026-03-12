package main

import (
	"context"
	"encoding/json"
	"fmt"
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
