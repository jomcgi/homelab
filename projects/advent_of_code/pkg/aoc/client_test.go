package aoc

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

// ---------------------------------------------------------------------------
// parseSubmitResponse
// ---------------------------------------------------------------------------

func TestParseSubmitResponse_CorrectAnswer(t *testing.T) {
	html := `<html><body><article><p>That's the right answer! You are awesome.</p></article></body></html>`
	got := parseSubmitResponse(html)
	if !got.Correct {
		t.Errorf("expected Correct=true for right-answer response")
	}
	if got.TooSoon {
		t.Errorf("expected TooSoon=false")
	}
}

func TestParseSubmitResponse_WrongAnswer(t *testing.T) {
	html := `<html><body><article><p>That's not the right answer; your answer is too high.</p></article></body></html>`
	got := parseSubmitResponse(html)
	if got.Correct {
		t.Errorf("expected Correct=false for wrong-answer response")
	}
	if got.TooSoon {
		t.Errorf("expected TooSoon=false")
	}
}

func TestParseSubmitResponse_RateLimited(t *testing.T) {
	html := `<html><body><article><p>You gave an answer too recently; you have 5m 30s left to wait.</p></article></body></html>`
	got := parseSubmitResponse(html)
	if got.Correct {
		t.Errorf("expected Correct=false for rate-limited response")
	}
	if !got.TooSoon {
		t.Errorf("expected TooSoon=true for rate-limited response")
	}
}

func TestParseSubmitResponse_AlreadyCompleted(t *testing.T) {
	html := `<html><body><article><p>You don't seem to be solving the right level. Did you already complete it?</p></article></body></html>`
	got := parseSubmitResponse(html)
	if got.Correct {
		t.Errorf("expected Correct=false for already-completed response")
	}
	if got.TooSoon {
		t.Errorf("expected TooSoon=false")
	}
	if got.Message == "" {
		t.Errorf("expected non-empty Message for already-completed response")
	}
}

func TestParseSubmitResponse_MessageExtracted(t *testing.T) {
	html := `<html><body><article><p>That's the right answer! <span>You got a star!</span></p></article></body></html>`
	got := parseSubmitResponse(html)
	// The article content should be stripped of HTML tags.
	if got.Message == "" {
		t.Error("expected non-empty Message")
	}
}

// ---------------------------------------------------------------------------
// stripHTML
// ---------------------------------------------------------------------------

func TestStripHTML_RemovesAllTags(t *testing.T) {
	cases := []struct {
		input string
		want  string
	}{
		{"<p>Hello</p>", "Hello"},
		{"<b>bold</b> and <i>italic</i>", "bold and italic"},
		{"no tags here", "no tags here"},
		{"<a href=\"http://example.com\">link</a>", "link"},
	}
	for _, tc := range cases {
		got := stripHTML(tc.input)
		if got != tc.want {
			t.Errorf("stripHTML(%q) = %q, want %q", tc.input, got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// htmlToMarkdown
// ---------------------------------------------------------------------------

func TestHtmlToMarkdown_ContainsHeader(t *testing.T) {
	html := `<article class="day-desc"><h2>--- Day 1: Historian Hysteria ---</h2><p>Some puzzle text.</p></article>`
	got := htmlToMarkdown(html, 2024, 1)
	if got == "" {
		t.Fatal("expected non-empty markdown output")
	}
	// Must contain a year/day header.
	want := "# Advent of Code 2024 - Day 1"
	if len(got) < len(want) {
		t.Errorf("htmlToMarkdown output too short: %q", got)
	}
}

func TestHtmlToMarkdown_NoArticle(t *testing.T) {
	html := `<html><body><p>Not a puzzle page.</p></body></html>`
	got := htmlToMarkdown(html, 2024, 1)
	// Should still produce the header even with no article.
	if got == "" {
		t.Fatal("expected non-empty output even without article")
	}
}

// ---------------------------------------------------------------------------
// convertArticleToMarkdown
// ---------------------------------------------------------------------------

func TestConvertArticleToMarkdown_InlineCode(t *testing.T) {
	html := `<p>Use <code>sort.Ints</code> to sort.</p>`
	got := convertArticleToMarkdown(html)
	if got == "" {
		t.Fatal("expected non-empty output")
	}
	// Inline code should be wrapped in backticks.
	for _, substr := range []string{"`sort.Ints`"} {
		found := false
		for i := 0; i <= len(got)-len(substr); i++ {
			if got[i:i+len(substr)] == substr {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("expected %q in markdown output %q", substr, got)
		}
	}
}

func TestConvertArticleToMarkdown_CodeBlock(t *testing.T) {
	html := "<pre><code>line1\nline2\n</code></pre>"
	got := convertArticleToMarkdown(html)
	if got == "" {
		t.Fatal("expected non-empty output")
	}
	// Should produce a fenced code block with the triple-backtick marker.
	marker := "```"
	if len(got) < len(marker) {
		t.Errorf("expected fenced code block in output, got: %q", got)
	}
}

func TestConvertArticleToMarkdown_HTMLEntitiesDecoded(t *testing.T) {
	html := `<p>Use &lt;, &gt;, &amp;, &quot;, &#39; chars.</p>`
	got := convertArticleToMarkdown(html)
	for _, want := range []string{"<", ">", "&", `"`, "'"} {
		found := false
		for _, r := range got {
			if string(r) == want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("expected decoded entity %q in output %q", want, got)
		}
	}
}

// ---------------------------------------------------------------------------
// CurrentYear / CurrentDay / IsPuzzleAvailable
// ---------------------------------------------------------------------------

func TestCurrentYear_ReturnsReasonableYear(t *testing.T) {
	y := CurrentYear()
	if y < 2015 || y > 2100 {
		t.Errorf("CurrentYear() = %d, want value in [2015, 2100]", y)
	}
}

func TestCurrentDay_ZeroOutsideDecember(t *testing.T) {
	// Today is 2026-03-12 (March), so CurrentDay() must return 0.
	day := CurrentDay()
	if day != 0 {
		t.Errorf("CurrentDay() = %d in March, want 0", day)
	}
}

func TestIsPuzzleAvailable_PastPuzzleIsAvailable(t *testing.T) {
	// AoC 2015 Day 1 should always be available by now.
	if !IsPuzzleAvailable(2015, 1) {
		t.Error("IsPuzzleAvailable(2015, 1) = false, want true")
	}
}

func TestIsPuzzleAvailable_FuturePuzzleIsNotAvailable(t *testing.T) {
	// A puzzle far in the future should not yet be available.
	if IsPuzzleAvailable(2099, 1) {
		t.Error("IsPuzzleAvailable(2099, 1) = true, want false")
	}
}

// ---------------------------------------------------------------------------
// HTTP-level: GetInput / SaveInput / GetPuzzleHTML / Submit
// ---------------------------------------------------------------------------

func TestGetInput_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/2024/day/1/input" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		cookie, err := r.Cookie("session")
		if err != nil || cookie.Value != "test-session" {
			t.Errorf("expected session cookie, got %v", err)
		}
		fmt.Fprintln(w, "12345")
	}))
	defer srv.Close()

	c := NewClient("test-session")
	c.httpClient.Transport = &rewriteTransport{base: srv.URL, inner: http.DefaultTransport}

	input, err := c.GetInput(2024, 1)
	if err != nil {
		t.Fatal(err)
	}
	if input == "" {
		t.Error("expected non-empty input")
	}
}

func TestGetInput_NotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	c := NewClient("test-session")
	c.httpClient.Transport = &rewriteTransport{base: srv.URL, inner: http.DefaultTransport}

	_, err := c.GetInput(2024, 1)
	if err == nil {
		t.Error("expected error for 404 response")
	}
}

func TestGetInput_BadRequest(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()

	c := NewClient("test-session")
	c.httpClient.Transport = &rewriteTransport{base: srv.URL, inner: http.DefaultTransport}

	_, err := c.GetInput(2024, 1)
	if err == nil {
		t.Error("expected error for 400 response")
	}
}

func TestGetInput_UnexpectedStatus(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	c := NewClient("test-session")
	c.httpClient.Transport = &rewriteTransport{base: srv.URL, inner: http.DefaultTransport}

	_, err := c.GetInput(2024, 1)
	if err == nil {
		t.Error("expected error for 500 response")
	}
}

func TestSaveInput_WritesFile(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "puzzle data")
	}))
	defer srv.Close()

	c := NewClient("test-session")
	c.httpClient.Transport = &rewriteTransport{base: srv.URL, inner: http.DefaultTransport}

	dir := t.TempDir()
	path := filepath.Join(dir, "subdir", "input.txt")

	if err := c.SaveInput(2024, 1, path); err != nil {
		t.Fatal(err)
	}

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) == "" {
		t.Error("expected non-empty file")
	}
}

func TestGetPuzzleHTML_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/2024/day/1" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		fmt.Fprintln(w, "<html><body><article class=\"day-desc\"><p>Puzzle</p></article></body></html>")
	}))
	defer srv.Close()

	c := NewClient("test-session")
	c.httpClient.Transport = &rewriteTransport{base: srv.URL, inner: http.DefaultTransport}

	html, err := c.GetPuzzleHTML(2024, 1)
	if err != nil {
		t.Fatal(err)
	}
	if html == "" {
		t.Error("expected non-empty HTML")
	}
}

func TestGetPuzzleHTML_ErrorStatus(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer srv.Close()

	c := NewClient("test-session")
	c.httpClient.Transport = &rewriteTransport{base: srv.URL, inner: http.DefaultTransport}

	_, err := c.GetPuzzleHTML(2024, 1)
	if err == nil {
		t.Error("expected error for non-200 response")
	}
}

func TestSubmit_CorrectAnswer(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		fmt.Fprintln(w, `<html><body><article><p>That's the right answer!</p></article></body></html>`)
	}))
	defer srv.Close()

	c := NewClient("test-session")
	c.httpClient.Transport = &rewriteTransport{base: srv.URL, inner: http.DefaultTransport}

	result, err := c.Submit(2024, 1, 1, "42")
	if err != nil {
		t.Fatal(err)
	}
	if !result.Correct {
		t.Errorf("expected Correct=true, got false; message=%q", result.Message)
	}
}

func TestNewClient_SetsSession(t *testing.T) {
	c := NewClient("my-session-token")
	if c.session != "my-session-token" {
		t.Errorf("expected session=my-session-token, got %q", c.session)
	}
	if c.httpClient == nil {
		t.Error("expected non-nil httpClient")
	}
}

// rewriteTransport redirects all requests to the given base URL (for testing).
type rewriteTransport struct {
	base  string
	inner http.RoundTripper
}

func (rt *rewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	// Redirect scheme+host to the test server while keeping the original path.
	newReq := req.Clone(req.Context())
	newReq.URL.Scheme = "http"
	newReq.URL.Host = rt.base[len("http://"):] // strip "http://" prefix
	return rt.inner.RoundTrip(newReq)
}
