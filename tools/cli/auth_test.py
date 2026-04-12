"""Tests for Cloudflare Access token management."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.cli.auth import get_cf_token


class TestGetCfToken:
    def test_returns_token_from_existing_file(self, tmp_path):
        token_file = tmp_path / "private.jomcgi.dev-token"
        token_file.write_text("my-cf-token")
        with patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path):
            assert get_cf_token() == "my-cf-token"

    def test_raises_when_no_token_and_cloudflared_missing(self, tmp_path):
        with (
            patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path),
            patch("tools.cli.auth.shutil.which", return_value=None),
        ):
            with pytest.raises(SystemExit):
                get_cf_token()

    def test_runs_cloudflared_login_when_no_token(self, tmp_path):
        token_file = tmp_path / "private.jomcgi.dev-token"
        call_count = 0

        def fake_login(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            token_file.write_text("fresh-token")

        with (
            patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path),
            patch(
                "tools.cli.auth.shutil.which", return_value="/usr/local/bin/cloudflared"
            ),
            patch("tools.cli.auth.subprocess.run", side_effect=fake_login),
        ):
            result = get_cf_token()
            assert result == "fresh-token"
            assert call_count == 1

    def test_custom_hostname_reads_matching_token(self, tmp_path):
        """Custom hostname resolves the file containing that hostname in its name."""
        token_file = tmp_path / "custom.example.com-token"
        token_file.write_text("custom-host-token")
        with patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path):
            result = get_cf_token("custom.example.com")
        assert result == "custom-host-token"

    def test_custom_hostname_does_not_match_default_token(self, tmp_path):
        """A token file for the default hostname is not returned for a different hostname."""
        # Only the default hostname token exists.
        default_token = tmp_path / "private.jomcgi.dev-token"
        default_token.write_text("default-token")
        with (
            patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path),
            patch("tools.cli.auth.shutil.which", return_value=None),
        ):
            # No matching file for "other.example.com" → triggers SystemExit (no cloudflared).
            with pytest.raises(SystemExit):
                get_cf_token("other.example.com")

    def test_strips_leading_and_trailing_whitespace_from_token(self, tmp_path):
        """Token files with surrounding whitespace are stripped before returning."""
        token_file = tmp_path / "private.jomcgi.dev-token"
        token_file.write_text("  \n  actual-token  \n  ")
        with patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path):
            result = get_cf_token()
        assert result == "actual-token"

    def test_strips_newline_only_whitespace(self, tmp_path):
        """Token files ending with a trailing newline (common in editors) are stripped."""
        token_file = tmp_path / "private.jomcgi.dev-token"
        token_file.write_text("newline-token\n")
        with patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path):
            result = get_cf_token()
        assert result == "newline-token"

    def test_permission_error_reading_token_file_propagates(self, tmp_path):
        """PermissionError when reading the token file propagates to the caller."""
        token_file = tmp_path / "private.jomcgi.dev-token"
        token_file.write_text("secret")

        def mock_read_text(self, *args, **kwargs):
            raise PermissionError("Permission denied: token file")

        with (
            patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path),
            patch.object(Path, "read_text", mock_read_text),
        ):
            with pytest.raises(PermissionError):
                get_cf_token()

    def test_most_recent_token_file_wins(self, tmp_path):
        """When multiple token files match, the most recently modified one is used."""
        import time

        old_file = tmp_path / "private.jomcgi.dev-old"
        old_file.write_text("old-token")
        time.sleep(0.01)  # ensure mtime difference
        new_file = tmp_path / "private.jomcgi.dev-new"
        new_file.write_text("new-token")

        with patch("tools.cli.auth.CF_TOKEN_DIR", tmp_path):
            result = get_cf_token()
        assert result == "new-token"
