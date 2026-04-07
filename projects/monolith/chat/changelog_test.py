"""Tests for the hourly changelog notifier module."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from chat.changelog import (
    _auth_headers,
    _build_embed,
    _filter_changelog_commits,
    _summarize_with_gemma,
    run_changelog_iteration,
)


def _make_commit(message: str, author: str = "Alice") -> dict:
    """Helper to build a minimal GitHub commit dict."""
    return {
        "commit": {
            "message": message,
            "author": {"name": author},
        }
    }


# ---------------------------------------------------------------------------
# _filter_changelog_commits
# ---------------------------------------------------------------------------


class TestFilterChangelogCommits:
    def test_empty_list_returns_empty(self):
        """Empty input returns empty list."""
        assert _filter_changelog_commits([]) == []

    def test_feat_commit_passes(self):
        """feat: commits are included."""
        commits = [_make_commit("feat: add dark mode")]
        assert len(_filter_changelog_commits(commits)) == 1

    def test_fix_commit_excluded(self):
        """fix: commits are excluded (feat-only filter)."""
        commits = [_make_commit("fix: correct typo in footer")]
        assert _filter_changelog_commits(commits) == []

    def test_chore_commit_excluded(self):
        """chore: commits are not included."""
        commits = [_make_commit("chore: update dependencies")]
        assert _filter_changelog_commits(commits) == []

    def test_docs_commit_excluded(self):
        """docs: commits are not included."""
        commits = [_make_commit("docs: improve README")]
        assert _filter_changelog_commits(commits) == []

    def test_refactor_commit_excluded(self):
        """refactor: commits are not included."""
        commits = [_make_commit("refactor: extract helper function")]
        assert _filter_changelog_commits(commits) == []

    def test_ci_commit_excluded(self):
        """ci: commits are not included."""
        commits = [_make_commit("ci: add lint step")]
        assert _filter_changelog_commits(commits) == []

    def test_feat_with_scope_passes(self):
        """feat(auth): scoped feature commits are included."""
        commits = [_make_commit("feat(auth): add OAuth2 support")]
        assert len(_filter_changelog_commits(commits)) == 1

    def test_feat_breaking_change_passes(self):
        """feat!: breaking change feature commits are included."""
        commits = [_make_commit("feat!: redesign auth token format")]
        assert len(_filter_changelog_commits(commits)) == 1

    def test_feat_scope_breaking_change_passes(self):
        """feat(auth)!: scoped breaking change is included."""
        commits = [_make_commit("feat(auth)!: drop legacy token support")]
        assert len(_filter_changelog_commits(commits)) == 1

    def test_multiline_commit_uses_first_line_only(self):
        """Only the subject line (before first newline) is matched."""
        commits = [_make_commit("feat: add feature\n\nLong description here.")]
        assert len(_filter_changelog_commits(commits)) == 1

    def test_multiline_commit_fix_excluded(self):
        """fix: with body is still excluded even when body mentions feat."""
        commits = [_make_commit("fix: patch crash\n\nfeat: unrelated note")]
        assert _filter_changelog_commits(commits) == []

    def test_mixed_commits_returns_only_feat(self):
        """Only feat commits are returned from a mixed list."""
        commits = [
            _make_commit("feat: new dashboard"),
            _make_commit("fix: remove null pointer"),
            _make_commit("chore: bump versions"),
            _make_commit("feat(ui): dark mode toggle"),
        ]
        result = _filter_changelog_commits(commits)
        assert len(result) == 2
        assert result[0]["commit"]["message"] == "feat: new dashboard"
        assert result[1]["commit"]["message"] == "feat(ui): dark mode toggle"

    def test_partial_word_feat_excluded(self):
        """A commit message starting with 'feature:' (not 'feat:') is excluded."""
        commits = [_make_commit("feature: add something")]
        assert _filter_changelog_commits(commits) == []

    def test_feat_without_colon_excluded(self):
        """'feat add something' (no colon) is excluded."""
        commits = [_make_commit("feat add something")]
        assert _filter_changelog_commits(commits) == []


# ---------------------------------------------------------------------------
# _build_embed
# ---------------------------------------------------------------------------


class TestBuildEmbed:
    def test_embed_title(self):
        """Embed title is 'Homelab Changelog'."""
        embed = _build_embed("Some summary", commit_count=3)
        assert embed.title == "Homelab Changelog"

    def test_embed_color(self):
        """Embed color is 0x2ECC71 (green)."""
        embed = _build_embed("Some summary", commit_count=3)
        assert embed.colour.value == 0x2ECC71

    def test_embed_description_matches_summary(self):
        """Embed description equals the provided summary string."""
        summary = "Added dark mode and fixed login bug."
        embed = _build_embed(summary, commit_count=2)
        assert embed.description == summary

    def test_embed_footer_singular(self):
        """Footer text shows commit count."""
        embed = _build_embed("x", commit_count=1)
        assert embed.footer.text == "1 commit(s)"

    def test_embed_footer_plural(self):
        """Footer text with multiple commits."""
        embed = _build_embed("x", commit_count=5)
        assert embed.footer.text == "5 commit(s)"

    def test_embed_has_timestamp(self):
        """Embed has a timestamp set."""
        embed = _build_embed("x", commit_count=1)
        assert embed.timestamp is not None

    def test_embed_returns_discord_embed(self):
        """Return type is discord.Embed."""
        embed = _build_embed("x", commit_count=1)
        assert isinstance(embed, discord.Embed)


# ---------------------------------------------------------------------------
# _auth_headers
# ---------------------------------------------------------------------------


class TestAuthHeaders:
    def test_returns_authorization_header(self):
        """Returned dict contains Authorization header with token prefix."""
        headers = _auth_headers("ghp_abc123")
        assert headers["Authorization"] == "token ghp_abc123"

    def test_merges_github_accept_header(self):
        """Returned dict also contains the GitHub Accept header."""
        headers = _auth_headers("tok")
        assert headers["Accept"] == "application/vnd.github+json"

    def test_returns_dict(self):
        """Return value is a plain dict."""
        assert isinstance(_auth_headers("x"), dict)

    def test_does_not_mutate_global_headers(self):
        """Calling _auth_headers does not modify _GITHUB_HEADERS in place."""
        from chat.changelog import _GITHUB_HEADERS

        original_keys = set(_GITHUB_HEADERS.keys())
        _auth_headers("secret")
        assert set(_GITHUB_HEADERS.keys()) == original_keys
        assert "Authorization" not in _GITHUB_HEADERS


# ---------------------------------------------------------------------------
# _summarize_with_gemma
# ---------------------------------------------------------------------------


class TestSummarizeWithGemma:
    @pytest.mark.asyncio
    async def test_prompt_includes_commit_messages(self):
        """The prompt forwarded to llm_call contains commit message text."""
        commits = [_make_commit("feat: add search", "Bob")]
        mock_llm = AsyncMock(return_value="Added search functionality.")

        await _summarize_with_gemma(commits, mock_llm)

        call_args = mock_llm.call_args[0][0]
        assert "feat: add search" in call_args

    @pytest.mark.asyncio
    async def test_prompt_includes_author_names(self):
        """The prompt forwarded to llm_call includes the commit author names."""
        commits = [_make_commit("feat: add feature", "Charlie")]
        mock_llm = AsyncMock(return_value="Added a feature.")

        await _summarize_with_gemma(commits, mock_llm)

        call_args = mock_llm.call_args[0][0]
        assert "Charlie" in call_args

    @pytest.mark.asyncio
    async def test_returns_llm_output(self):
        """Return value is exactly what the llm_call callable returns."""
        commits = [_make_commit("feat: dark mode")]
        expected = "Users can now toggle dark mode."
        mock_llm = AsyncMock(return_value=expected)

        result = await _summarize_with_gemma(commits, mock_llm)

        assert result == expected

    @pytest.mark.asyncio
    async def test_llm_called_once(self):
        """llm_call is invoked exactly once per summarize call."""
        commits = [_make_commit("feat: a"), _make_commit("feat: b")]
        mock_llm = AsyncMock(return_value="summary")

        await _summarize_with_gemma(commits, mock_llm)

        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_commits_all_appear_in_prompt(self):
        """All commit messages appear in the prompt when multiple commits are given."""
        commits = [
            _make_commit("feat: feature A", "Alice"),
            _make_commit("feat: feature B", "Bob"),
        ]
        mock_llm = AsyncMock(return_value="Two features added.")

        await _summarize_with_gemma(commits, mock_llm)

        call_args = mock_llm.call_args[0][0]
        assert "feat: feature A" in call_args
        assert "feat: feature B" in call_args
        assert "Alice" in call_args
        assert "Bob" in call_args


# ---------------------------------------------------------------------------
# run_changelog_iteration
# ---------------------------------------------------------------------------


class TestRunChangelogIteration:
    @pytest.mark.asyncio
    async def test_missing_all_env_vars_returns_early(self):
        """When all env vars are absent the function exits without error."""
        bot = MagicMock(spec=discord.Client)
        mock_llm = AsyncMock()

        with patch.dict("os.environ", {}, clear=True):
            # Remove relevant keys if present
            import os

            for key in (
                "CHANGELOG_CHANNEL_ID",
                "GITHUB_TOKEN",
                "CHANGELOG_GITHUB_REPO",
            ):
                os.environ.pop(key, None)

            await run_changelog_iteration(bot, mock_llm)

        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_single_env_var_returns_early(self):
        """Missing just one env var causes early return (AND logic)."""
        bot = MagicMock(spec=discord.Client)
        mock_llm = AsyncMock()

        env = {
            "CHANGELOG_CHANNEL_ID": "123456",
            "GITHUB_TOKEN": "ghp_xxx",
            # CHANGELOG_GITHUB_REPO intentionally omitted
        }
        with patch.dict("os.environ", env, clear=True):
            await run_changelog_iteration(bot, mock_llm)

        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_commits_returns_early(self):
        """When GitHub returns no commits, no Discord message is sent."""
        bot = MagicMock(spec=discord.Client)
        mock_llm = AsyncMock()

        env = {
            "CHANGELOG_CHANNEL_ID": "111",
            "GITHUB_TOKEN": "ghp_tok",
            "CHANGELOG_GITHUB_REPO": "owner/repo",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", env):
            with patch("chat.changelog.httpx.AsyncClient", return_value=mock_client):
                await run_changelog_iteration(bot, mock_llm)

        mock_llm.assert_not_called()
        bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_matching_commits_returns_early(self):
        """When commits exist but none are feat, no Discord message is sent."""
        bot = MagicMock(spec=discord.Client)
        mock_llm = AsyncMock()

        env = {
            "CHANGELOG_CHANNEL_ID": "111",
            "GITHUB_TOKEN": "ghp_tok",
            "CHANGELOG_GITHUB_REPO": "owner/repo",
        }

        commits = [
            _make_commit("fix: patch null pointer"),
            _make_commit("chore: update deps"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = commits
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", env):
            with patch("chat.changelog.httpx.AsyncClient", return_value=mock_client):
                await run_changelog_iteration(bot, mock_llm)

        mock_llm.assert_not_called()
        bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_post_sends_embed(self):
        """With valid env vars and feat commits, an embed is posted to Discord."""
        mock_channel = AsyncMock()
        bot = MagicMock(spec=discord.Client)
        bot.get_channel.return_value = mock_channel

        mock_llm = AsyncMock(return_value="Added a great new feature.")

        env = {
            "CHANGELOG_CHANNEL_ID": "999",
            "GITHUB_TOKEN": "ghp_tok",
            "CHANGELOG_GITHUB_REPO": "owner/repo",
        }

        commits = [_make_commit("feat: amazing new feature", "Alice")]
        mock_response = MagicMock()
        mock_response.json.return_value = commits
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", env):
            with patch("chat.changelog.httpx.AsyncClient", return_value=mock_client):
                await run_changelog_iteration(bot, mock_llm)

        bot.get_channel.assert_called_once_with(999)
        mock_channel.send.assert_called_once()
        send_kwargs = mock_channel.send.call_args[1]
        assert "embed" in send_kwargs
        assert isinstance(send_kwargs["embed"], discord.Embed)

    @pytest.mark.asyncio
    async def test_channel_not_found_does_not_raise(self):
        """When bot.get_channel returns None, no error is raised."""
        bot = MagicMock(spec=discord.Client)
        bot.get_channel.return_value = None

        mock_llm = AsyncMock(return_value="Summary text.")

        env = {
            "CHANGELOG_CHANNEL_ID": "888",
            "GITHUB_TOKEN": "ghp_tok",
            "CHANGELOG_GITHUB_REPO": "owner/repo",
        }

        commits = [_make_commit("feat: something cool", "Dave")]
        mock_response = MagicMock()
        mock_response.json.return_value = commits
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", env):
            with patch("chat.changelog.httpx.AsyncClient", return_value=mock_client):
                await run_changelog_iteration(bot, mock_llm)

        # Should log a warning but not crash
        bot.get_channel.assert_called_once_with(888)
