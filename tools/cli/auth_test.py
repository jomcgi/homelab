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
