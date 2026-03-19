package main

import (
	"regexp"
	"strings"
)

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

// cleanOutput strips ANSI escape codes, all Goose startup banners, and
// normalizes carriage returns so output renders cleanly in the UI.
func cleanOutput(raw string) string {
	s := ansiRE.ReplaceAllString(raw, "")

	// Normalize line endings: \r\n → \n, then lone \r → \n.
	s = strings.ReplaceAll(s, "\r\n", "\n")
	s = strings.ReplaceAll(s, "\r", "\n")

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

	return strings.TrimLeft(s, "\n")
}
