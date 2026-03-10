"""Tests for rebuild command (recover NATS trip data from SeaweedFS images)."""

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main import (
    OpticsCache,
    OpticsData,
    UploadQueue,
    UploadStatus,
    _rebuild_batch,
    _run_rebuild,
    list_s3_keys,
)


# ---------------------------------------------------------------------------
# TestListS3Keys
# ---------------------------------------------------------------------------


class TestListS3Keys:
    def _make_s3(self, pages):
        """Build a mock S3 client that returns the given pages from list_objects_v2."""
        s3 = MagicMock()
        s3.list_objects_v2.side_effect = pages
        return s3

    def test_returns_image_keys_only(self):
        s3 = self._make_s3(
            [
                {
                    "Contents": [
                        {"Key": "img_aaa.jpg"},
                        {"Key": "img_bbb.jpeg"},
                        {"Key": "img_ccc.png"},
                        {"Key": "img_ddd.heic"},
                        {"Key": "img_eee.heif"},
                        {"Key": "notes.txt"},
                        {"Key": "video.mp4"},
                    ],
                    "IsTruncated": False,
                }
            ]
        )

        keys = list_s3_keys(s3, "trips")

        assert keys == [
            "img_aaa.jpg",
            "img_bbb.jpeg",
            "img_ccc.png",
            "img_ddd.heic",
            "img_eee.heif",
        ]

    def test_paginates_across_multiple_pages(self):
        s3 = self._make_s3(
            [
                {
                    "Contents": [{"Key": "img_a.jpg"}],
                    "IsTruncated": True,
                    "NextContinuationToken": "tok1",
                },
                {
                    "Contents": [{"Key": "img_b.jpg"}],
                    "IsTruncated": False,
                },
            ]
        )

        keys = list_s3_keys(s3, "trips")

        assert keys == ["img_a.jpg", "img_b.jpg"]
        # Second call should include ContinuationToken
        second_call_kwargs = s3.list_objects_v2.call_args_list[1][1]
        assert second_call_kwargs["ContinuationToken"] == "tok1"

    def test_empty_bucket_returns_empty_list(self):
        s3 = self._make_s3([{"IsTruncated": False}])

        keys = list_s3_keys(s3, "trips")

        assert keys == []

    def test_prefix_filtering(self):
        s3 = self._make_s3(
            [
                {
                    "Contents": [{"Key": "folder/img_a.jpg"}],
                    "IsTruncated": False,
                }
            ]
        )

        keys = list_s3_keys(s3, "trips", prefix="folder/")

        assert keys == ["folder/img_a.jpg"]
        call_kwargs = s3.list_objects_v2.call_args[1]
        assert call_kwargs["Prefix"] == "folder/"


# ---------------------------------------------------------------------------
# TestRebuildBatch
# ---------------------------------------------------------------------------


SAMPLE_OPTICS = OpticsData(
    light_value=8.6,
    iso=393,
    shutter_speed="1/240",
    aperture=2.5,
    focal_length_35mm=16,
)


class TestRebuildBatch:
    @pytest.fixture
    def queue(self, tmp_path):
        return UploadQueue(tmp_path / "queue.db")

    @pytest.fixture
    def optics_cache(self, tmp_path):
        return OpticsCache(tmp_path / "optics.db")

    @patch("main.extract_exif")
    def test_extracts_exif_and_returns_points(
        self, mock_exif, queue, optics_cache, tmp_path
    ):
        mock_exif.return_value = (
            49.2827,
            -123.1207,
            "2025-07-01T12:00:00",
            SAMPLE_OPTICS,
        )

        s3 = MagicMock()
        s3.download_file.return_value = None

        points = _rebuild_batch(
            s3_client=s3,
            bucket="trips",
            keys=["img_abc.jpg"],
            queue=queue,
            optics_cache=optics_cache,
            tmp_dir=tmp_path / "dl",
            concurrency=1,
        )

        assert len(points) == 1
        assert points[0]["lat"] == 49.2827
        assert points[0]["lng"] == -123.1207
        assert points[0]["timestamp"] == "2025-07-01T12:00:00"
        assert points[0]["optics"] == SAMPLE_OPTICS

    @patch("main.extract_exif")
    def test_skips_images_without_gps(self, mock_exif, queue, optics_cache, tmp_path):
        mock_exif.return_value = (None, None, "2025-07-01T12:00:00", None)
        s3 = MagicMock()
        s3.download_file.return_value = None

        points = _rebuild_batch(
            s3_client=s3,
            bucket="trips",
            keys=["img_nogps.jpg"],
            queue=queue,
            optics_cache=optics_cache,
            tmp_dir=tmp_path / "dl",
            concurrency=1,
        )

        assert points == []

    @patch("main.extract_exif")
    def test_populates_queue_db(self, mock_exif, queue, optics_cache, tmp_path):
        mock_exif.return_value = (49.0, -123.0, "2025-07-01T12:00:00", None)
        s3 = MagicMock()
        s3.download_file.return_value = None

        _rebuild_batch(
            s3_client=s3,
            bucket="trips",
            keys=["img_abc.jpg"],
            queue=queue,
            optics_cache=optics_cache,
            tmp_dir=tmp_path / "dl",
            concurrency=1,
        )

        completed = queue.get_completed()
        assert len(completed) == 1
        assert completed[0].dest_key == "img_abc.jpg"
        assert completed[0].status == UploadStatus.COMPLETED

    @patch("main.extract_exif")
    def test_uses_optics_cache(self, mock_exif, queue, optics_cache, tmp_path):
        # Pre-populate cache
        optics_cache.put("img_cached.jpg", SAMPLE_OPTICS)

        mock_exif.return_value = (49.0, -123.0, "2025-07-01T12:00:00", None)
        s3 = MagicMock()
        s3.download_file.return_value = None

        points = _rebuild_batch(
            s3_client=s3,
            bucket="trips",
            keys=["img_cached.jpg"],
            queue=queue,
            optics_cache=optics_cache,
            tmp_dir=tmp_path / "dl",
            concurrency=1,
        )

        assert len(points) == 1
        # Should use cached optics rather than extract_exif's None
        assert points[0]["optics"] == SAMPLE_OPTICS

    @patch("main.extract_exif")
    def test_handles_download_failure(self, mock_exif, queue, optics_cache, tmp_path):
        s3 = MagicMock()
        s3.download_file.side_effect = Exception("network error")

        points = _rebuild_batch(
            s3_client=s3,
            bucket="trips",
            keys=["img_fail.jpg"],
            queue=queue,
            optics_cache=optics_cache,
            tmp_dir=tmp_path / "dl",
            concurrency=1,
        )

        # Should not crash, just skip
        assert points == []

    @patch("main.extract_exif")
    def test_cleans_up_temp_dir(self, mock_exif, queue, optics_cache, tmp_path):
        mock_exif.return_value = (49.0, -123.0, "2025-07-01T12:00:00", None)
        s3 = MagicMock()
        s3.download_file.return_value = None

        dl_dir = tmp_path / "dl"
        dl_dir.mkdir()
        # Create a dummy file to verify cleanup
        (dl_dir / "leftover.txt").write_text("old")

        _rebuild_batch(
            s3_client=s3,
            bucket="trips",
            keys=["img_abc.jpg"],
            queue=queue,
            optics_cache=optics_cache,
            tmp_dir=dl_dir,
            concurrency=1,
        )

        # tmp_dir should exist but leftover should be gone (dir was rm'd and recreated)
        assert dl_dir.exists()
        assert not (dl_dir / "leftover.txt").exists()

    @patch("main.extract_exif")
    def test_creates_parent_dirs_for_nested_keys(
        self, mock_exif, queue, optics_cache, tmp_path
    ):
        mock_exif.return_value = (49.0, -123.0, "2025-07-01T12:00:00", None)
        s3 = MagicMock()
        s3.download_file.return_value = None

        points = _rebuild_batch(
            s3_client=s3,
            bucket="trips",
            keys=["folder/subfolder/img_nested.jpg"],
            queue=queue,
            optics_cache=optics_cache,
            tmp_dir=tmp_path / "dl",
            concurrency=1,
        )

        assert len(points) == 1
        assert points[0]["key"] == "folder/subfolder/img_nested.jpg"


# ---------------------------------------------------------------------------
# TestRunRebuild
# ---------------------------------------------------------------------------


class TestRunRebuild:
    @pytest.fixture
    def db_path(self, tmp_path):
        return tmp_path / "rebuild_queue.db"

    def _mock_nats(self):
        """Build mock NATS connection + JetStream."""
        nc = AsyncMock()
        js = AsyncMock()

        # stream_info returns a mock with config.max_age
        stream_info = MagicMock()
        stream_info.config.max_age = 2592000  # 30 days in seconds
        js.stream_info.return_value = stream_info

        return nc, js

    def _mock_elevation_client(self):
        """Build mock ElevationClient async context manager."""
        from projects.trips.tools.elevation.client import ElevationResult

        elev_client = AsyncMock()
        elev_client.__aenter__ = AsyncMock(return_value=elev_client)
        elev_client.__aexit__ = AsyncMock(return_value=False)

        def make_results(coords, **kwargs):
            cb = kwargs.get("progress_callback")
            results = [
                ElevationResult(lat=lat, lng=lng, elevation=100.0)
                for lat, lng in coords
            ]
            if cb:
                cb(len(results), len(results))
            return results

        elev_client.get_elevations.side_effect = make_results
        return elev_client

    @patch("main.ElevationClient")
    @patch("main.list_s3_keys")
    @patch("main.get_jetstream")
    @patch("main.get_s3_client")
    @patch("main.extract_exif")
    @pytest.mark.asyncio
    async def test_dry_run_does_not_publish(
        self,
        mock_exif,
        mock_s3_client,
        mock_jetstream,
        mock_list_keys,
        mock_elev_cls,
        db_path,
    ):
        nc, js = self._mock_nats()
        mock_jetstream.return_value = (nc, js)
        mock_s3_client.return_value = MagicMock()
        mock_list_keys.return_value = ["img_abc.jpg"]
        mock_exif.return_value = (49.0, -123.0, "2025-07-01T12:00:00", SAMPLE_OPTICS)

        elev_client = self._mock_elevation_client()
        mock_elev_cls.return_value = elev_client

        await _run_rebuild(
            bucket="trips",
            batch_size=100,
            concurrency=1,
            dry_run=True,
            source="gopro",
            db_path=db_path,
            fix_retention=False,
        )

        js.publish.assert_not_called()

    @patch("main.ElevationClient")
    @patch("main.list_s3_keys")
    @patch("main.get_jetstream")
    @patch("main.get_s3_client")
    @patch("main.extract_exif")
    @pytest.mark.asyncio
    async def test_fixes_stream_retention(
        self,
        mock_exif,
        mock_s3_client,
        mock_jetstream,
        mock_list_keys,
        mock_elev_cls,
        db_path,
    ):
        nc, js = self._mock_nats()
        mock_jetstream.return_value = (nc, js)
        mock_s3_client.return_value = MagicMock()
        mock_list_keys.return_value = ["img_abc.jpg"]
        mock_exif.return_value = (49.0, -123.0, "2025-07-01T12:00:00", None)

        elev_client = self._mock_elevation_client()
        mock_elev_cls.return_value = elev_client

        await _run_rebuild(
            bucket="trips",
            batch_size=100,
            concurrency=1,
            dry_run=False,
            source="gopro",
            db_path=db_path,
            fix_retention=True,
        )

        js.update_stream.assert_called_once()
        updated_config = js.update_stream.call_args[0][0]
        assert updated_config.max_age == 0

    @patch("main.ElevationClient")
    @patch("main.list_s3_keys")
    @patch("main.get_jetstream")
    @patch("main.get_s3_client")
    @patch("main.extract_exif")
    @pytest.mark.asyncio
    async def test_skips_retention_fix_when_disabled(
        self,
        mock_exif,
        mock_s3_client,
        mock_jetstream,
        mock_list_keys,
        mock_elev_cls,
        db_path,
    ):
        nc, js = self._mock_nats()
        mock_jetstream.return_value = (nc, js)
        mock_s3_client.return_value = MagicMock()
        mock_list_keys.return_value = ["img_abc.jpg"]
        mock_exif.return_value = (49.0, -123.0, "2025-07-01T12:00:00", None)

        elev_client = self._mock_elevation_client()
        mock_elev_cls.return_value = elev_client

        await _run_rebuild(
            bucket="trips",
            batch_size=100,
            concurrency=1,
            dry_run=False,
            source="gopro",
            db_path=db_path,
            fix_retention=False,
        )

        js.update_stream.assert_not_called()

    @patch("main.ElevationClient")
    @patch("main.list_s3_keys")
    @patch("main.get_jetstream")
    @patch("main.get_s3_client")
    @patch("main.extract_exif")
    @pytest.mark.asyncio
    async def test_publishes_correct_nats_message(
        self,
        mock_exif,
        mock_s3_client,
        mock_jetstream,
        mock_list_keys,
        mock_elev_cls,
        db_path,
    ):
        nc, js = self._mock_nats()
        mock_jetstream.return_value = (nc, js)
        mock_s3_client.return_value = MagicMock()
        mock_list_keys.return_value = ["img_aabbccddeeff.jpg"]
        mock_exif.return_value = (
            49.28270,
            -123.12070,
            "2025-07-01T12:00:00",
            SAMPLE_OPTICS,
        )

        elev_client = self._mock_elevation_client()
        mock_elev_cls.return_value = elev_client

        await _run_rebuild(
            bucket="trips",
            batch_size=100,
            concurrency=1,
            dry_run=False,
            source="gopro",
            db_path=db_path,
            fix_retention=False,
        )

        js.publish.assert_called_once()
        subject, payload = js.publish.call_args[0]
        assert subject == "trips.point"

        msg = json.loads(payload.decode())

        # Verify all 13 fields from the design spec
        assert msg["id"] == "aabbccddeeff"  # hex from key
        assert msg["lat"] == 49.2827
        assert msg["lng"] == -123.1207
        assert msg["timestamp"] == "2025-07-01T12:00:00"
        assert msg["image"] == "img_aabbccddeeff.jpg"
        assert msg["source"] == "gopro"
        assert msg["tags"] == []
        assert msg["elevation"] == 100.0
        assert msg["light_value"] == 8.6
        assert msg["iso"] == 393
        assert msg["shutter_speed"] == "1/240"
        assert msg["aperture"] == 2.5
        assert msg["focal_length_35mm"] == 16

    @patch("main.list_s3_keys")
    @patch("main.get_jetstream")
    @patch("main.get_s3_client")
    @pytest.mark.asyncio
    async def test_handles_empty_bucket(
        self, mock_s3_client, mock_jetstream, mock_list_keys, db_path
    ):
        nc, js = self._mock_nats()
        mock_jetstream.return_value = (nc, js)
        mock_s3_client.return_value = MagicMock()
        mock_list_keys.return_value = []

        await _run_rebuild(
            bucket="trips",
            batch_size=100,
            concurrency=1,
            dry_run=False,
            source="gopro",
            db_path=db_path,
            fix_retention=False,
        )

        js.publish.assert_not_called()
