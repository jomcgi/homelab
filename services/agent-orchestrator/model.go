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

// JobRecord is the primary data model persisted in the NATS KV store.
type JobRecord struct {
	ID         string    `json:"id"`
	Task       string    `json:"task"`
	Status     JobStatus `json:"status"`
	CreatedAt  time.Time `json:"created_at"`
	UpdatedAt  time.Time `json:"updated_at"`
	MaxRetries int       `json:"max_retries"`
	Source     string    `json:"source"`

	// Reserved for webhook/DLQ integration.
	GithubIssue    int    `json:"github_issue,omitempty"`
	DebugMode      bool   `json:"debug_mode,omitempty"`
	FailureSummary string `json:"failure_summary,omitempty"`

	Attempts []Attempt `json:"attempts"`
}

// Attempt records a single execution attempt of a job.
type Attempt struct {
	Number           int        `json:"number"`
	SandboxClaimName string     `json:"sandbox_claim_name"`
	ExitCode         *int       `json:"exit_code,omitempty"`
	Output           string     `json:"output"`
	StartedAt        time.Time  `json:"started_at"`
	FinishedAt       *time.Time `json:"finished_at,omitempty"`
}

// SubmitRequest is the JSON body for POST /api/v1/jobs.
type SubmitRequest struct {
	Task       string `json:"task"`
	MaxRetries *int   `json:"max_retries,omitempty"`
	Source     string `json:"source,omitempty"`
}

// SubmitResponse is returned after a job is created.
type SubmitResponse struct {
	ID        string    `json:"id"`
	Status    JobStatus `json:"status"`
	CreatedAt time.Time `json:"created_at"`
}

// ListResponse is returned by GET /api/v1/jobs.
type ListResponse struct {
	Jobs  []JobRecord `json:"jobs"`
	Total int         `json:"total"`
}

// OutputResponse is returned by GET /api/v1/jobs/{id}/output.
type OutputResponse struct {
	Attempt   int    `json:"attempt"`
	ExitCode  *int   `json:"exit_code,omitempty"`
	Output    string `json:"output"`
	Truncated bool   `json:"truncated"`
}
