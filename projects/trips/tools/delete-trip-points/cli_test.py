"""CLI integration tests for delete-trip-points — Typer command flows.

Tests exercise by_date(), by_id(), and list_gaps() end-to-end using
typer.testing.CliRunner with mocked HTTP (httpx) and NATS.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_response(points: list[dict]) -> MagicMock:
    """Build a mock httpx response returning the given points list."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"points": points}
    return mock_resp


def _make_nats_mocks():
    """Return (mock_nc, mock_js) with nc.close() and js.publish() wired up."""
    mock_js = AsyncMock()
    mock_nc = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)
    return mock_nc, mock_js


_SAMPLE_POINTS = [
    {
        "id": "g1",
        "timestamp": "2025-06-15T08:00:00",
        "source": "gap",
        "lat": 60.0,
        "lng": -135.0,
    },
    {
        "id": "g2",
        "timestamp": "2025-06-15T09:00:00",
        "source": "gap",
        "lat": 60.1,
        "lng": -135.1,
    },
    {
        "id": "p1",
        "timestamp": "2025-06-15T08:30:00",
        "source": "gopro",
        "lat": 60.2,
        "lng": -135.2,
    },
    {
        "id": "g3",
        "timestamp": "2025-06-16T08:00:00",
        "source": "gap",
        "lat": 61.0,
        "lng": -136.0,
    },
]


# ---------------------------------------------------------------------------
# by_date — dry run (no NATS connection needed)
# ---------------------------------------------------------------------------


class TestByDateDryRun:
    """by_date --dry-run shows what would be deleted without publishing."""

    def _run(self, extra_args=None):
        args = ["by-date", "2025-06-15", "--dry-run"]
        if extra_args:
            args += extra_args

        mock_resp = _make_api_response(_SAMPLE_POINTS)

        async def _fake_get(*args, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = _fake_get

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            return runner.invoke(app, args)

    def test_exit_code_zero(self):
        result = self._run()
        assert result.exit_code == 0, result.output

    def test_shows_dry_run_banner(self):
        result = self._run()
        assert "[DRY RUN]" in result.output

    def test_shows_point_count(self):
        result = self._run()
        # Two gap points on 2025-06-15
        assert "2 gap points" in result.output

    def test_no_nats_connection_in_dry_run(self):
        """NATS must not be contacted when --dry-run is active."""
        mock_resp = _make_api_response(_SAMPLE_POINTS)

        async def _fake_get(*args, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = _fake_get

        with (
            patch("main.httpx.AsyncClient", return_value=mock_client),
            patch("main.nats.connect") as mock_connect,
        ):
            result = runner.invoke(app, ["by-date", "2025-06-15", "--dry-run"])

        assert result.exit_code == 0
        mock_connect.assert_not_called()

    def test_no_points_for_date_exits_cleanly(self):
        mock_resp = _make_api_response(_SAMPLE_POINTS)

        async def _fake_get(*args, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = _fake_get

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = runner.invoke(app, ["by-date", "2099-01-01", "--dry-run"])

        assert result.exit_code == 0
        assert "No gap points" in result.output

    def test_custom_source_filter(self):
        mock_resp = _make_api_response(_SAMPLE_POINTS)

        async def _fake_get(*args, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = _fake_get

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            # Filter by 'gopro' source — only p1 matches 2025-06-15/gopro
            result = runner.invoke(
                app,
                ["by-date", "2025-06-15", "--source", "gopro", "--dry-run"],
            )

        assert result.exit_code == 0
        assert "1 gopro points" in result.output


# ---------------------------------------------------------------------------
# by_date — full run (with NATS, --yes to skip confirmation)
# ---------------------------------------------------------------------------


class TestByDateFullRun:
    """by_date without --dry-run publishes tombstones to NATS."""

    def _run_with_mocks(self, date: str, points: list[dict], extra_args=None):
        mock_resp = _make_api_response(points)

        async def _fake_get(*args, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = _fake_get

        mock_nc, mock_js = _make_nats_mocks()

        args = ["by-date", date, "--yes"]
        if extra_args:
            args += extra_args

        with (
            patch("main.httpx.AsyncClient", return_value=mock_client),
            patch("main.nats.connect", return_value=mock_nc),
        ):
            result = runner.invoke(app, args)

        return result, mock_js

    def test_exit_code_zero_with_matching_points(self):
        result, _ = self._run_with_mocks("2025-06-15", _SAMPLE_POINTS)
        assert result.exit_code == 0, result.output

    def test_publishes_tombstone_for_each_matching_point(self):
        result, mock_js = self._run_with_mocks("2025-06-15", _SAMPLE_POINTS)
        # Two gap points on 2025-06-15
        assert mock_js.publish.call_count == 2

    def test_tombstones_have_correct_ids(self):
        result, mock_js = self._run_with_mocks("2025-06-15", _SAMPLE_POINTS)
        published_ids = {
            json.loads(call[0][1].decode())["id"]
            for call in mock_js.publish.call_args_list
        }
        assert published_ids == {"g1", "g2"}

    def test_tombstones_published_to_trips_delete_subject(self):
        result, mock_js = self._run_with_mocks("2025-06-15", _SAMPLE_POINTS)
        for call in mock_js.publish.call_args_list:
            assert call[0][0] == "trips.delete"

    def test_all_tombstones_have_deleted_true(self):
        result, mock_js = self._run_with_mocks("2025-06-15", _SAMPLE_POINTS)
        for call in mock_js.publish.call_args_list:
            payload = json.loads(call[0][1].decode())
            assert payload["deleted"] is True

    def test_shows_deleted_count_in_output(self):
        result, _ = self._run_with_mocks("2025-06-15", _SAMPLE_POINTS)
        assert "Deleted 2 points" in result.output

    def test_nats_connection_closed_after_publish(self):
        result, mock_js = self._run_with_mocks("2025-06-15", _SAMPLE_POINTS)
        # mock_nc is the connection object; find it via the patch
        assert result.exit_code == 0  # nc.close() is awaited in finally block

    def test_no_publish_when_no_matching_points(self):
        result, mock_js = self._run_with_mocks("2099-01-01", _SAMPLE_POINTS)
        assert result.exit_code == 0
        mock_js.publish.assert_not_called()


# ---------------------------------------------------------------------------
# by_id — dry run
# ---------------------------------------------------------------------------


class TestByIdDryRunCli:
    """by_id --dry-run prints IDs without connecting to NATS."""

    def _run(self, ids: list[str], dry_run: bool = True):
        args = ["by-id"] + ids
        if dry_run:
            args.append("--dry-run")
        return runner.invoke(app, args)

    def test_exit_code_zero(self):
        result = self._run(["id1", "id2", "id3"])
        assert result.exit_code == 0, result.output

    def test_shows_would_delete_messages(self):
        result = self._run(["id1", "id2"])
        assert "Would delete" in result.output
        assert "id1" in result.output
        assert "id2" in result.output

    def test_dry_run_banner_present(self):
        result = self._run(["id1"])
        assert "[DRY RUN]" in result.output

    def test_no_nats_connection_in_dry_run(self):
        with patch("main.nats.connect") as mock_connect:
            result = self._run(["id1", "id2"])
        assert result.exit_code == 0
        mock_connect.assert_not_called()

    def test_single_id_dry_run(self):
        result = self._run(["only-id"])
        assert "only-id" in result.output
        assert "[DRY RUN]" in result.output


# ---------------------------------------------------------------------------
# by_id — full run (publishes to NATS)
# ---------------------------------------------------------------------------


class TestByIdFullRunCli:
    """by_id without --dry-run publishes tombstones for each provided ID."""

    def _run_with_mocks(self, ids: list[str]):
        mock_nc, mock_js = _make_nats_mocks()
        with patch("main.nats.connect", return_value=mock_nc):
            result = runner.invoke(app, ["by-id"] + ids)
        return result, mock_js

    def test_exit_code_zero(self):
        result, _ = self._run_with_mocks(["id1", "id2"])
        assert result.exit_code == 0, result.output

    def test_publishes_one_tombstone_per_id(self):
        _, mock_js = self._run_with_mocks(["id1", "id2", "id3"])
        assert mock_js.publish.call_count == 3

    def test_tombstones_have_correct_ids(self):
        ids = ["alpha", "beta", "gamma"]
        _, mock_js = self._run_with_mocks(ids)
        published = [
            json.loads(c[0][1].decode())["id"] for c in mock_js.publish.call_args_list
        ]
        assert published == ids

    def test_all_tombstones_have_deleted_true(self):
        _, mock_js = self._run_with_mocks(["x", "y"])
        for call in mock_js.publish.call_args_list:
            assert json.loads(call[0][1].decode())["deleted"] is True

    def test_output_shows_deleted_count(self):
        result, _ = self._run_with_mocks(["id1", "id2"])
        assert "Deleted 2 points" in result.output

    def test_single_id_publishes_once(self):
        _, mock_js = self._run_with_mocks(["sole-id"])
        mock_js.publish.assert_called_once()

    def test_tombstones_on_trips_delete_subject(self):
        _, mock_js = self._run_with_mocks(["id1"])
        assert mock_js.publish.call_args[0][0] == "trips.delete"


# ---------------------------------------------------------------------------
# list_gaps — no date filter
# ---------------------------------------------------------------------------


class TestListGapsCli:
    """list_gaps fetches all points and shows gap points grouped by date."""

    def _run(self, points: list[dict], args=None):
        mock_resp = _make_api_response(points)

        async def _fake_get(*_, **__):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = _fake_get

        invoke_args = ["list-gaps"]
        if args:
            invoke_args += args

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            return runner.invoke(app, invoke_args)

    def test_exit_code_zero(self):
        result = self._run(_SAMPLE_POINTS)
        assert result.exit_code == 0, result.output

    def test_shows_total_gap_count(self):
        result = self._run(_SAMPLE_POINTS)
        # Three gap points total in _SAMPLE_POINTS
        assert "3 gap points" in result.output

    def test_shows_both_dates(self):
        result = self._run(_SAMPLE_POINTS)
        assert "2025-06-15" in result.output
        assert "2025-06-16" in result.output

    def test_no_gap_points_message(self):
        non_gap = [
            {
                "id": "p1",
                "timestamp": "2025-06-15T08:00:00",
                "source": "gopro",
                "lat": 60.0,
                "lng": -135.0,
            }
        ]
        result = self._run(non_gap)
        assert result.exit_code == 0
        assert "No gap points found" in result.output

    def test_date_filter_narrows_results(self):
        result = self._run(_SAMPLE_POINTS, args=["2025-06-15"])
        # Only the two gap points on 2025-06-15 should appear
        assert "2 gap points" in result.output
        assert "2025-06-16" not in result.output

    def test_date_filter_no_match(self):
        result = self._run(_SAMPLE_POINTS, args=["2099-01-01"])
        assert result.exit_code == 0
        assert "No gap points found" in result.output

    def test_empty_response_exits_cleanly(self):
        result = self._run([])
        assert result.exit_code == 0
        assert "No gap points found" in result.output

    def test_sample_id_shown_in_output(self):
        """list_gaps prints a sample ID for the first point in each date group."""
        result = self._run(_SAMPLE_POINTS, args=["2025-06-15"])
        # g1 is the first gap point on 2025-06-15
        assert "g1" in result.output
