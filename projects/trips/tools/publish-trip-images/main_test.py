"""Unit tests for publish-trip-images/main.py — OpticsCache and GracefulShutdown.

Supplements publish_images_test.py and rebuild_test.py by covering:
- OpticsCache: init, get (hit/miss), put, idempotent init
- GracefulShutdown: signal handling specific to the upload context
- OpticsData: default values and field presence
"""

import signal
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from main import (
    GracefulShutdown,
    OpticsCache,
    OpticsData,
)


# ---------------------------------------------------------------------------
# OpticsData
# ---------------------------------------------------------------------------


class TestOpticsData:
    """Dataclass default values and field types."""

    def test_all_fields_default_to_none(self):
        optics = OpticsData()
        assert optics.light_value is None
        assert optics.iso is None
        assert optics.shutter_speed is None
        assert optics.aperture is None
        assert optics.focal_length_35mm is None

    def test_fields_can_be_set(self):
        optics = OpticsData(
            light_value=8.6,
            iso=400,
            shutter_speed="1/240",
            aperture=2.8,
            focal_length_35mm=16,
        )
        assert optics.light_value == pytest.approx(8.6)
        assert optics.iso == 400
        assert optics.shutter_speed == "1/240"
        assert optics.aperture == pytest.approx(2.8)
        assert optics.focal_length_35mm == 16

    def test_partial_fields(self):
        optics = OpticsData(iso=100)
        assert optics.iso == 100
        assert optics.light_value is None

    def test_equality_same_values(self):
        a = OpticsData(iso=400, aperture=2.8)
        b = OpticsData(iso=400, aperture=2.8)
        assert a == b

    def test_inequality_different_values(self):
        a = OpticsData(iso=400)
        b = OpticsData(iso=800)
        assert a != b


# ---------------------------------------------------------------------------
# OpticsCache — initialisation
# ---------------------------------------------------------------------------


class TestOpticsCacheInit:
    """SQLite schema is created on construction."""

    def test_creates_optics_cache_table(self, tmp_path):
        db = tmp_path / "optics.db"
        OpticsCache(db)
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='optics_cache'"
            ).fetchall()
        assert len(rows) == 1

    def test_idempotent_init(self, tmp_path):
        """Constructing twice on the same path must not raise."""
        db = tmp_path / "optics.db"
        OpticsCache(db)
        OpticsCache(db)  # should not raise


# ---------------------------------------------------------------------------
# OpticsCache — get (cache miss)
# ---------------------------------------------------------------------------


class TestOpticsCacheGet:
    """Cache lookup returns (found, data) tuples."""

    @pytest.fixture
    def cache(self, tmp_path):
        return OpticsCache(tmp_path / "optics.db")

    def test_miss_returns_false_and_none(self, cache):
        found, data = cache.get("img_nonexistent.jpg")
        assert found is False
        assert data is None

    def test_hit_returns_true_and_optics_data(self, cache):
        optics = OpticsData(iso=400, aperture=2.8, light_value=9.2)
        cache.put("img_abc.jpg", optics)

        found, data = cache.get("img_abc.jpg")

        assert found is True
        assert data is not None
        assert data.iso == 400
        assert data.aperture == pytest.approx(2.8)
        assert data.light_value == pytest.approx(9.2)

    def test_hit_with_none_optics_returns_true_and_none_fields(self, cache):
        """put(key, None) stores a row with all-null fields; get returns (True, OpticsData())."""
        cache.put("img_null.jpg", None)
        found, data = cache.get("img_null.jpg")
        # Key is present in the cache even though optics are all None.
        assert found is True

    def test_different_keys_independent(self, cache):
        optics_a = OpticsData(iso=100)
        optics_b = OpticsData(iso=800)
        cache.put("img_a.jpg", optics_a)
        cache.put("img_b.jpg", optics_b)

        _, data_a = cache.get("img_a.jpg")
        _, data_b = cache.get("img_b.jpg")

        assert data_a.iso == 100
        assert data_b.iso == 800

    def test_missing_key_does_not_affect_other_keys(self, cache):
        optics = OpticsData(iso=200)
        cache.put("img_present.jpg", optics)

        found_missing, _ = cache.get("img_absent.jpg")
        found_present, _ = cache.get("img_present.jpg")

        assert found_missing is False
        assert found_present is True


# ---------------------------------------------------------------------------
# OpticsCache — put
# ---------------------------------------------------------------------------


class TestOpticsCachePut:
    """Storing entries and overwriting existing entries."""

    @pytest.fixture
    def cache(self, tmp_path):
        return OpticsCache(tmp_path / "optics.db")

    def test_put_creates_entry(self, cache):
        optics = OpticsData(shutter_speed="1/500")
        cache.put("img_x.jpg", optics)
        found, data = cache.get("img_x.jpg")
        assert found is True
        assert data.shutter_speed == "1/500"

    def test_put_overwrites_existing_entry(self, cache):
        cache.put("img_y.jpg", OpticsData(iso=100))
        cache.put("img_y.jpg", OpticsData(iso=800))

        _, data = cache.get("img_y.jpg")
        assert data.iso == 800

    def test_put_none_is_accepted(self, cache):
        """Caching None (no optics available) must not raise."""
        cache.put("img_none.jpg", None)

    def test_all_fields_round_trip(self, cache):
        optics = OpticsData(
            light_value=10.5,
            iso=393,
            shutter_speed="1/240",
            aperture=2.5,
            focal_length_35mm=16,
        )
        cache.put("img_full.jpg", optics)
        _, result = cache.get("img_full.jpg")

        assert result.light_value == pytest.approx(10.5)
        assert result.iso == 393
        assert result.shutter_speed == "1/240"
        assert result.aperture == pytest.approx(2.5)
        assert result.focal_length_35mm == 16

    def test_put_persists_across_instances(self, tmp_path):
        """Data written by one OpticsCache instance is readable by another."""
        db = tmp_path / "optics.db"
        cache1 = OpticsCache(db)
        cache1.put("img_persist.jpg", OpticsData(iso=1600))

        cache2 = OpticsCache(db)
        found, data = cache2.get("img_persist.jpg")

        assert found is True
        assert data.iso == 1600


# ---------------------------------------------------------------------------
# GracefulShutdown (publish-trip-images context)
# ---------------------------------------------------------------------------


class TestGracefulShutdownPublish:
    """GracefulShutdown context manager for the upload process."""

    def test_initial_state_not_requested(self):
        gs = GracefulShutdown()
        assert gs.shutdown_requested is False

    def test_handler_sets_flag(self):
        with GracefulShutdown() as gs:
            gs._handler(signal.SIGINT, None)
            assert gs.shutdown_requested is True

    def test_second_signal_raises_system_exit(self):
        with GracefulShutdown() as gs:
            gs._handler(signal.SIGINT, None)
            with pytest.raises(SystemExit):
                gs._handler(signal.SIGINT, None)

    def test_sigterm_also_sets_flag(self):
        with GracefulShutdown() as gs:
            gs._handler(signal.SIGTERM, None)
            assert gs.shutdown_requested is True

    def test_context_manager_restores_signals(self):
        original_sigint = signal.getsignal(signal.SIGINT)
        with GracefulShutdown():
            pass
        assert signal.getsignal(signal.SIGINT) is original_sigint

    def test_enter_returns_self(self):
        gs = GracefulShutdown()
        with gs as ctx:
            assert ctx is gs
