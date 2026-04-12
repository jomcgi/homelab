// Tests for test-hardcoded-past-timestamp rule.
// This file is named *_test.go to match the path filter in the rule's paths.include section.
package example_test

import "time"

func ExampleHardcodedTimestamps() {
	// ruleid: test-hardcoded-past-timestamp
	ts := "2024-03-01T12:00:00Z"

	// ruleid: test-hardcoded-past-timestamp
	timestamp := "2025-01-15T09:30:00+00:00"

	// ruleid: test-hardcoded-past-timestamp
	createdAt := "2023-06-15"

	// ruleid: test-hardcoded-past-timestamp
	eventTime := "2024-12-31T23:59:59.999Z"

	// ruleid: test-hardcoded-past-timestamp
	var assignedTs string
	assignedTs = "2023-01-01T00:00:00Z"

	// ok: test-hardcoded-past-timestamp - dynamic timestamp, not a string literal
	nowDynamic := time.Now().UTC().Format(time.RFC3339)

	// ok: test-hardcoded-past-timestamp - not a date string
	name := "hello world"

	// ok: test-hardcoded-past-timestamp - not a date string
	status := "active"

	// ok: test-hardcoded-past-timestamp - not a date string (version number)
	version := "2024.1.0"

	_, _, _, _, _, _, _, _, _ = ts, timestamp, createdAt, eventTime, assignedTs, nowDynamic, name, status, version
}
