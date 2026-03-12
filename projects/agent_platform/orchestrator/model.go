package main

import "time"

// JobStatus represents the current state of a job.
type JobStatus string

const (
	JobPending   JobStatus = "PENDING"
	JobRunning   JobStatus = "RUNNING"
	JobSucceeded JobStatus = "SUCCEEDED"
	JobFailed    JobStatus = "FAILED"
	JobCancelled JobStatus = "CANCELLED"
)

// ValidProfiles maps profile names to their recipe paths inside the container.
// An empty profile means default behavior (no recipe, all tools).
var ValidProfiles = map[string]string{
	"ci-debug": "/home/goose-agent/recipes/ci-debug.yaml",
	"code-fix": "/home/goose-agent/recipes/code-fix.yaml",
	"research": "/home/goose-agent/recipes/research.yaml",
	"bazel":    "/home/goose-agent/recipes/bazel.yaml",
}

// JobRecord is the primary data model persisted in the NATS KV store.
type JobRecord struct {
	ID         string    `json:"id"`
	Task       string    `json:"task"`
	Profile    string    `json:"profile,omitempty"`
	Status     JobStatus `json:"status"`
	CreatedAt  time.Time `json:"created_at"`
	UpdatedAt  time.Time `json:"updated_at"`
	MaxRetries int       `json:"max_retries"`
	Source     string    `json:"source"`
	Tags       []string  `json:"tags,omitempty"`

	// Reserved for webhook/DLQ integration.
	GithubIssue    int    `json:"github_issue,omitempty"`
	DebugMode      bool   `json:"debug_mode,omitempty"`
	FailureSummary string `json:"failure_summary,omitempty"`

	Attempts []Attempt `json:"attempts"`
}

// Attempt records a single execution attempt of a job.
type Attempt struct {
	Number           int          `json:"number"`
	SandboxClaimName string       `json:"sandbox_claim_name"`
	ExitCode         *int         `json:"exit_code,omitempty"`
	Output           string       `json:"output"`
	Truncated        bool         `json:"truncated,omitempty"`
	Result           *GooseResult `json:"result,omitempty"`
	StartedAt        time.Time    `json:"started_at"`
	FinishedAt       *time.Time   `json:"finished_at,omitempty"`
}

// GooseResult is a structured result parsed from the agent's output.
type GooseResult struct {
	Type    string `json:"type"`
	URL     string `json:"url"`
	Summary string `json:"summary"`
}

// SubmitRequest is the JSON body for POST /jobs.
type SubmitRequest struct {
	Task       string   `json:"task"`
	Profile    string   `json:"profile,omitempty"`
	MaxRetries *int     `json:"max_retries,omitempty"`
	Source     string   `json:"source,omitempty"`
	Tags       []string `json:"tags,omitempty"`
}

// SubmitResponse is returned after a job is created.
type SubmitResponse struct {
	ID        string    `json:"id"`
	Status    JobStatus `json:"status"`
	CreatedAt time.Time `json:"created_at"`
}

// ListResponse is returned by GET /jobs.
type ListResponse struct {
	Jobs  []JobRecord `json:"jobs"`
	Total int         `json:"total"`
}

// OutputResponse is returned by GET /jobs/{id}/output.
type OutputResponse struct {
	Attempt   int          `json:"attempt"`
	ExitCode  *int         `json:"exit_code,omitempty"`
	Output    string       `json:"output"`
	Truncated bool         `json:"truncated"`
	Result    *GooseResult `json:"result,omitempty"`
}
