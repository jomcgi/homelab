package main

import (
	"strings"
)

// parseGooseResult extracts a structured result from the agent's raw output.
// It looks for the last ```goose-result fenced block and parses key: value
// header lines for type, url, and summary fields.
// Returns nil if no valid result block is found.
func parseGooseResult(raw string) *GooseResult {
	const startMarker = "```goose-result\n"
	const endMarker = "\n```"

	lastStart := strings.LastIndex(raw, startMarker)
	if lastStart == -1 {
		return nil
	}
	content := raw[lastStart+len(startMarker):]
	endIdx := strings.Index(content, endMarker)
	if endIdx == -1 {
		return nil
	}
	content = content[:endIdx]

	result := &GooseResult{}
	for _, line := range strings.Split(content, "\n") {
		key, val, ok := strings.Cut(line, ": ")
		if !ok {
			continue
		}
		switch strings.TrimSpace(key) {
		case "type":
			result.Type = strings.TrimSpace(val)
		case "url":
			result.URL = strings.TrimSpace(val)
		case "summary":
			result.Summary = strings.TrimSpace(val)
		case "reply":
			result.Reply = strings.TrimSpace(val)
		}
	}
	return result
}
