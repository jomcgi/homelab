// Package aoc provides a client for interacting with adventofcode.com
package aoc

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const (
	BaseURL   = "https://adventofcode.com"
	UserAgent = "github.com/jomcgi/homelab/projects/advent_of_code by jomcgi"
)

// Client handles interactions with adventofcode.com
type Client struct {
	httpClient *http.Client
	session    string
}

// SubmitResult represents the result of submitting an answer
type SubmitResult struct {
	Correct  bool
	Message  string
	TooSoon  bool   // Rate limited
	WaitTime string // How long to wait if rate limited
}

// NewClient creates a new AOC client with the given session cookie
func NewClient(session string) *Client {
	return &Client{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		session: session,
	}
}

// GetInput downloads the puzzle input for the specified year and day
func (c *Client) GetInput(year, day int) (string, error) {
	url := fmt.Sprintf("%s/%d/day/%d/input", BaseURL, year, day)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return "", err
	}

	req.Header.Set("User-Agent", UserAgent)
	req.AddCookie(&http.Cookie{
		Name:  "session",
		Value: c.session,
	})

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusBadRequest {
		return "", fmt.Errorf("puzzle not yet available (year=%d, day=%d)", year, day)
	}
	if resp.StatusCode == http.StatusNotFound {
		return "", fmt.Errorf("puzzle not found (year=%d, day=%d)", year, day)
	}
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	return string(body), nil
}

// SaveInput downloads and saves the puzzle input to the specified path
func (c *Client) SaveInput(year, day int, path string) error {
	input, err := c.GetInput(year, day)
	if err != nil {
		return err
	}

	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}

	return os.WriteFile(path, []byte(input), 0o644)
}

// GetPuzzleHTML downloads the puzzle description HTML for the specified year and day
func (c *Client) GetPuzzleHTML(year, day int) (string, error) {
	url := fmt.Sprintf("%s/%d/day/%d", BaseURL, year, day)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return "", err
	}

	req.Header.Set("User-Agent", UserAgent)
	req.AddCookie(&http.Cookie{
		Name:  "session",
		Value: c.session,
	})

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	return string(body), nil
}

// GetPuzzleMarkdown downloads the puzzle and converts it to markdown
func (c *Client) GetPuzzleMarkdown(year, day int) (string, error) {
	html, err := c.GetPuzzleHTML(year, day)
	if err != nil {
		return "", err
	}

	return htmlToMarkdown(html, year, day), nil
}

// Submit submits an answer for the specified year, day, and part
func (c *Client) Submit(year, day, part int, answer string) (*SubmitResult, error) {
	submitURL := fmt.Sprintf("%s/%d/day/%d/answer", BaseURL, year, day)

	form := url.Values{}
	form.Set("level", fmt.Sprintf("%d", part))
	form.Set("answer", answer)

	req, err := http.NewRequest("POST", submitURL, strings.NewReader(form.Encode()))
	if err != nil {
		return nil, err
	}

	req.Header.Set("User-Agent", UserAgent)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.AddCookie(&http.Cookie{
		Name:  "session",
		Value: c.session,
	})

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	return parseSubmitResponse(string(body)), nil
}

// parseSubmitResponse parses the HTML response from submitting an answer
func parseSubmitResponse(html string) *SubmitResult {
	result := &SubmitResult{}

	// Extract the main article content
	articleRe := regexp.MustCompile(`(?s)<article><p>(.*?)</p></article>`)
	match := articleRe.FindStringSubmatch(html)
	if len(match) > 1 {
		result.Message = stripHTML(match[1])
	}

	lower := strings.ToLower(html)

	// Check for correct answer
	if strings.Contains(lower, "that's the right answer") {
		result.Correct = true
		return result
	}

	// Check for wrong answer
	if strings.Contains(lower, "that's not the right answer") {
		result.Correct = false
		return result
	}

	// Check for rate limiting
	if strings.Contains(lower, "you gave an answer too recently") {
		result.TooSoon = true
		// Try to extract wait time
		waitRe := regexp.MustCompile(`(?i)you have (\d+[smh]|\d+m \d+s) left to wait`)
		if waitMatch := waitRe.FindStringSubmatch(html); len(waitMatch) > 1 {
			result.WaitTime = waitMatch[1]
		}
		return result
	}

	// Check if already completed
	if strings.Contains(lower, "you don't seem to be solving the right level") {
		result.Message = "Already completed or wrong level"
		return result
	}

	return result
}

// htmlToMarkdown converts AOC puzzle HTML to markdown
func htmlToMarkdown(html string, year, day int) string {
	var sb strings.Builder

	// Header
	sb.WriteString(fmt.Sprintf("# Advent of Code %d - Day %d\n\n", year, day))
	sb.WriteString(fmt.Sprintf("[View on adventofcode.com](https://adventofcode.com/%d/day/%d)\n\n", year, day))

	// Extract article content (puzzle description)
	articleRe := regexp.MustCompile(`(?s)<article class="day-desc">(.*?)</article>`)
	articles := articleRe.FindAllStringSubmatch(html, -1)

	for i, match := range articles {
		if len(match) > 1 {
			if i == 0 {
				sb.WriteString("## Part One\n\n")
			} else {
				sb.WriteString("\n---\n\n## Part Two\n\n")
			}
			sb.WriteString(convertArticleToMarkdown(match[1]))
			sb.WriteString("\n")
		}
	}

	return sb.String()
}

// convertArticleToMarkdown converts an article's HTML content to markdown
func convertArticleToMarkdown(html string) string {
	s := html

	// Remove the h2 title (we add our own)
	s = regexp.MustCompile(`(?s)<h2>.*?</h2>`).ReplaceAllString(s, "")

	// Convert code blocks
	s = regexp.MustCompile(`<pre><code>([\s\S]*?)</code></pre>`).ReplaceAllString(s, "```\n$1```\n")

	// Convert inline code
	s = regexp.MustCompile(`<code><em>(.*?)</em></code>`).ReplaceAllString(s, "**`$1`**")
	s = regexp.MustCompile(`<code>(.*?)</code>`).ReplaceAllString(s, "`$1`")

	// Convert emphasis
	s = regexp.MustCompile(`<em class="star">([^<]*)</em>`).ReplaceAllString(s, "⭐$1")
	s = regexp.MustCompile(`<em>(.*?)</em>`).ReplaceAllString(s, "**$1**")

	// Convert links
	s = regexp.MustCompile(`<a href="([^"]*)"[^>]*>(.*?)</a>`).ReplaceAllString(s, "[$2]($1)")

	// Convert lists
	s = regexp.MustCompile(`<ul>([\s\S]*?)</ul>`).ReplaceAllStringFunc(s, func(match string) string {
		inner := regexp.MustCompile(`<li>([\s\S]*?)</li>`).ReplaceAllString(match, "- $1\n")
		inner = strings.ReplaceAll(inner, "<ul>", "")
		inner = strings.ReplaceAll(inner, "</ul>", "")
		return inner
	})

	// Convert paragraphs
	s = regexp.MustCompile(`<p>([\s\S]*?)</p>`).ReplaceAllString(s, "$1\n\n")

	// Clean up remaining HTML tags
	s = stripHTML(s)

	// Clean up whitespace
	s = regexp.MustCompile(`\n{3,}`).ReplaceAllString(s, "\n\n")
	s = strings.TrimSpace(s)

	// Decode HTML entities
	s = strings.ReplaceAll(s, "&lt;", "<")
	s = strings.ReplaceAll(s, "&gt;", ">")
	s = strings.ReplaceAll(s, "&amp;", "&")
	s = strings.ReplaceAll(s, "&quot;", "\"")
	s = strings.ReplaceAll(s, "&#39;", "'")

	return s
}

// stripHTML removes all HTML tags from a string
func stripHTML(s string) string {
	return regexp.MustCompile(`<[^>]*>`).ReplaceAllString(s, "")
}

// CurrentYear returns the current AOC year (December uses current year, otherwise previous)
func CurrentYear() int {
	now := time.Now()
	if now.Month() == time.December {
		return now.Year()
	}
	return now.Year() - 1
}

// CurrentDay returns today's day number if we're in December 1-25, otherwise 0
func CurrentDay() int {
	now := time.Now()
	if now.Month() == time.December && now.Day() <= 25 {
		return now.Day()
	}
	return 0
}

// IsPuzzleAvailable checks if a puzzle is available yet
func IsPuzzleAvailable(year, day int) bool {
	// AOC puzzles unlock at midnight EST (UTC-5).
	// Use FixedZone instead of LoadLocation to avoid depending on tzdata,
	// which is unavailable in some sandbox environments (e.g. Bazel RBE).
	est := time.FixedZone("EST", -5*60*60)
	unlockTime := time.Date(year, time.December, day, 0, 0, 0, 0, est)
	return time.Now().After(unlockTime)
}
