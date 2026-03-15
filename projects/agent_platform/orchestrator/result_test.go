package main

import "testing"

func TestParseGooseResult_Valid(t *testing.T) {
	raw := "lots of goose output here\n```goose-result\ntype: pr\nurl: https://github.com/jomcgi/homelab/pull/42\nsummary: Fixed healthcheck port in values.yaml. CI passes.\n```\n"

	r := parseGooseResult(raw)
	if r == nil {
		t.Fatal("expected non-nil result")
	}
	if r.Type != "pr" {
		t.Errorf("type = %q, want %q", r.Type, "pr")
	}
	if r.URL != "https://github.com/jomcgi/homelab/pull/42" {
		t.Errorf("url = %q, want PR URL", r.URL)
	}
	if r.Summary != "Fixed healthcheck port in values.yaml. CI passes." {
		t.Errorf("summary = %q", r.Summary)
	}
}

func TestParseGooseResult_NoBlock(t *testing.T) {
	r := parseGooseResult("just some regular output with no result block")
	if r != nil {
		t.Errorf("expected nil, got %+v", r)
	}
}

func TestParseGooseResult_Empty(t *testing.T) {
	r := parseGooseResult("")
	if r != nil {
		t.Errorf("expected nil for empty input, got %+v", r)
	}
}

func TestParseGooseResult_UsesLastBlock(t *testing.T) {
	raw := "```goose-result\ntype: issue\nurl: https://old\nsummary: old\n```\nmore output\n```goose-result\ntype: pr\nurl: https://new\nsummary: new\n```\n"

	r := parseGooseResult(raw)
	if r == nil {
		t.Fatal("expected non-nil result")
	}
	if r.Type != "pr" {
		t.Errorf("should use last block: type = %q, want %q", r.Type, "pr")
	}
	if r.URL != "https://new" {
		t.Errorf("should use last block: url = %q", r.URL)
	}
}

func TestParseGooseResult_MalformedNoClose(t *testing.T) {
	raw := "```goose-result\ntype: pr\nurl: https://example.com\nsummary: no closing fence"

	r := parseGooseResult(raw)
	if r != nil {
		t.Errorf("expected nil for unclosed block, got %+v", r)
	}
}

func TestParseGooseResult_PartialFields(t *testing.T) {
	raw := "```goose-result\ntype: gist\nsummary: Research findings on logging.\n```\n"

	r := parseGooseResult(raw)
	if r == nil {
		t.Fatal("expected non-nil result")
	}
	if r.Type != "gist" {
		t.Errorf("type = %q, want %q", r.Type, "gist")
	}
	if r.URL != "" {
		t.Errorf("url should be empty, got %q", r.URL)
	}
	if r.Summary != "Research findings on logging." {
		t.Errorf("summary = %q", r.Summary)
	}
}

func TestParseGooseResult_GistType(t *testing.T) {
	raw := "investigation complete\n```goose-result\ntype: gist\nurl: https://gist.github.com/jomcgi/abc123\nsummary: Investigated SigNoz trace sampling. Current rate is 10%, recommend increasing to 25%.\n```\n"

	r := parseGooseResult(raw)
	if r == nil {
		t.Fatal("expected non-nil result")
	}
	if r.Type != "gist" {
		t.Errorf("type = %q, want %q", r.Type, "gist")
	}
}

func TestParseGooseResult_IssueType(t *testing.T) {
	raw := "found a problem\n```goose-result\ntype: issue\nurl: https://github.com/jomcgi/homelab/issues/99\nsummary: Discovered stale CronJob in monitoring namespace. Created issue to track cleanup.\n```\n"

	r := parseGooseResult(raw)
	if r == nil {
		t.Fatal("expected non-nil result")
	}
	if r.Type != "issue" {
		t.Errorf("type = %q, want %q", r.Type, "issue")
	}
}
