# Tests for test-hardcoded-past-timestamp rule.
# This file is named test_hardcoded_past_timestamp.py to match the test_*.py
# path filter in the rule's paths.include section.
from datetime import datetime, timezone


# ruleid: test-hardcoded-past-timestamp
now = "2024-03-01T12:00:00Z"

# ruleid: test-hardcoded-past-timestamp
timestamp = "2025-01-15T09:30:00+00:00"

# ruleid: test-hardcoded-past-timestamp
created_at = "2023-06-15"

# ruleid: test-hardcoded-past-timestamp
event_time = "2024-12-31T23:59:59.999Z"

# ok: test-hardcoded-past-timestamp - dynamic timestamp, not a string literal
now_dynamic = datetime.now(timezone.utc)

# ok: test-hardcoded-past-timestamp - not a date string
name = "hello world"

# ok: test-hardcoded-past-timestamp - not a date string
status = "active"

# ok: test-hardcoded-past-timestamp - not a date string
version = "2024.1.0"

# ok: test-hardcoded-past-timestamp - isoformat call, not a literal
ts = datetime.now(timezone.utc).isoformat()
