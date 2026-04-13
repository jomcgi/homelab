# Tests for no-generic-test-filename rule.
# This fixture simulates a vague-named test file (e.g. coverage_test.py).
# In production the rule only fires on files matching the paths.include patterns;
# paths.include is not applied in semgrep --test mode, so content anchors
# (def test_ / func Test) drive the annotations here.

# ruleid: no-generic-test-filename
def test_coverage():
    assert True


# ruleid: no-generic-test-filename
def test_identified_gaps():
    pass


# ok: no-generic-test-filename — helper, not a test function
def setup_fixtures():
    return {}


# ok: no-generic-test-filename — not a test function definition
class SomeHelper:
    pass
