package main

import (
	"regexp"
	"strings"
)

// multiBlankRE matches runs of 3+ consecutive newlines (2+ blank lines).
var multiBlankRE = regexp.MustCompile(`\n{3,}`)

// ansiRE matches ANSI escape sequences (CSI codes like colors, cursor movement).
var ansiRE = regexp.MustCompile(`\x1b\[[0-9;]*[a-zA-Z]`)

// gooseBannerEnd is the marker that terminates the Goose startup banner.
// Everything up to and including this line is stripped.
const gooseBannerEnd = "goose is ready"

// isBannerLine returns true if the line is part of the Goose ASCII art banner.
func isBannerLine(line string) bool {
	trimmed := strings.TrimSpace(line)
	return strings.Contains(trimmed, "__( O)>") ||
		strings.Contains(trimmed, "\\___") ||
		strings.Contains(trimmed, "L L")
}

// cleanOutput strips ANSI escape codes, all Goose startup banners,
// goose-result fenced blocks, and normalizes carriage returns so output
// renders cleanly in the UI.
func cleanOutput(raw string) string {
	s := ansiRE.ReplaceAllString(raw, "")

	// Normalize line endings: \r\n → \n, then lone \r → \n.
	s = strings.ReplaceAll(s, "\r\n", "\n")
	s = strings.ReplaceAll(s, "\r", "\n")

	// Strip recipe loading preambles ("Loading recipe: ..." through next blank line).
	// These appear before each goose banner in pipeline jobs.
	const recipeMarker = "Loading recipe:"
	for {
		idx := strings.Index(s, recipeMarker)
		if idx == -1 {
			break
		}
		lineStart := strings.LastIndex(s[:idx], "\n")
		if lineStart == -1 {
			lineStart = 0
		} else {
			lineStart++
		}
		endIdx := strings.Index(s[idx:], "\n\n")
		if endIdx == -1 {
			s = s[:lineStart]
		} else {
			after := idx + endIdx + 2
			s = s[:lineStart] + s[after:]
		}
	}

	// Strip all Goose startup banners (ASCII art + "goose is ready").
	// Pipeline jobs spawn a new goose process per step, so there may be
	// multiple banners in the output.
	for {
		idx := strings.Index(s, gooseBannerEnd)
		if idx == -1 {
			break
		}

		// Find the end of the "goose is ready" marker.
		after := idx + len(gooseBannerEnd)
		if after < len(s) && s[after] == '\n' {
			after++
		}

		// Find the start of the line containing "goose is ready".
		lineStart := strings.LastIndex(s[:idx], "\n")
		if lineStart == -1 {
			lineStart = 0
		} else {
			lineStart++ // skip past the \n
		}

		// Walk backwards up to 3 lines looking for banner art lines.
		bannerStart := lineStart
		pos := bannerStart
		for i := 0; i < 3 && pos > 0; i++ {
			// pos points to the start of the current banner line.
			// Look at the line ending just before pos (s[pos-1] == '\n').
			prevEnd := pos - 1 // points to the \n before current line
			prevLineStart := strings.LastIndex(s[:prevEnd], "\n")
			if prevLineStart == -1 {
				prevLineStart = 0
			} else {
				prevLineStart++ // skip past the \n
			}
			prevLine := s[prevLineStart:prevEnd]
			if !isBannerLine(prevLine) {
				break
			}
			bannerStart = prevLineStart
			pos = prevLineStart
		}

		s = s[:bannerStart] + s[after:]
	}

	// Strip goose-result fenced blocks. These are already parsed and stored
	// in Attempt.Result, so they should not appear in the display output.
	const resultStart = "```goose-result\n"
	const resultEnd = "\n```"
	for {
		idx := strings.Index(s, resultStart)
		if idx == -1 {
			break
		}
		endContent := s[idx+len(resultStart):]
		endIdx := strings.Index(endContent, resultEnd)
		if endIdx == -1 {
			break
		}
		after := idx + len(resultStart) + endIdx + len(resultEnd)
		if after < len(s) && s[after] == '\n' {
			after++
		}
		s = s[:idx] + s[after:]
	}

	// Collapse runs of 3+ newlines (left behind after stripping banners/preambles)
	// down to a single blank line so the UI doesn't show large whitespace gaps.
	s = multiBlankRE.ReplaceAllString(s, "\n\n")

	s = strings.TrimLeft(s, "\n")
	s = strings.TrimRight(s, "\n")
	if s != "" {
		s += "\n"
	}
	return s
}
