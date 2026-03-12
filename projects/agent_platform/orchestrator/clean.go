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

// cleanOutput strips ANSI escape codes, the Goose startup banner, and
// normalizes carriage returns so output renders cleanly in the UI.
func cleanOutput(raw string) string {
	s := ansiRE.ReplaceAllString(raw, "")

	// Normalize line endings: \r\n → \n, then lone \r → \n.
	s = strings.ReplaceAll(s, "\r\n", "\n")
	s = strings.ReplaceAll(s, "\r", "\n")

	// Strip Goose startup banner (ASCII art + "goose is ready").
	if idx := strings.Index(s, gooseBannerEnd); idx != -1 {
		after := idx + len(gooseBannerEnd)
		// Skip the trailing newline if present.
		if after < len(s) && s[after] == '\n' {
			after++
		}
		s = s[after:]
	}

	return strings.TrimLeft(s, "\n")
}
