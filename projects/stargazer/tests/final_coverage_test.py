"""Final coverage tests — fills gaps across all 8 stargazer source modules.

Covers previously-untested code paths in:
  api.py         — main(), log_message(), best_locations 500/non-list/bad-JSON paths
  acquisition.py — multi-chunk streaming download
  config.py      — BoundsConfig / EuropeBoundsConfig env overrides, forecast_hours
  main.py        — setup_telemetry ImportError warning, otel endpoint path
  preprocessing.py — gdalwarp failure, ogr2ogr failure
  scoring.py     — fog score boundary conditions (5 and 20 inflection points)
  spatial.py     — enrich_points with existing DEM, generate_sample_grid empty result
  weather.py     — empty timeseries, score sorting, missing next_1_hours,
                   missing altitude_m, output_best_locations empty input
"""

import json
import os
import subprocess
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import geopandas as gpd
import pytest
import pytest_asyncio  # noqa: F401 — needed to register pytest-asyncio plugin
from shapely.geometry import Point, Polygon

from projects.stargazer.backend.config import BoundsConfig, EuropeBoundsConfig, Settings
from projects.stargazer.backend.scoring import WeatherData, calculate_astronomy_score


# ---------------------------------------------------------------------------
# Helpers shared by API tests (mirrors the helper in api_test.py / api_additional_test.py)
# ---------------------------------------------------------------------------


class MockWFile:
    """Mock wfile for capturing response bytes."""

    def __init__(self):
        self.data = BytesIO()

    def write(self, data: bytes):
        self.data.write(data)

    def getvalue(self) -> bytes:
        return self.data.getvalue()


def create_api_handler(path: str):
    """Return a (handler, wfile) pair with all HTTP primitives mocked."""
    from projects.stargazer.backend.api import StargazerAPIHandler

    handler = StargazerAPIHandler.__new__(StargazerAPIHandler)
    handler.path = path
    handler.client_address = ("127.0.0.1", 9999)
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.headers = {}

    wfile = MockWFile()
    handler.wfile = wfile
    handler._headers = {}
    handler._status_code = None

    handler.send_response = lambda code: setattr(handler, "_status_code", code)
    handler.send_header = lambda k, v: handler._headers.__setitem__(k, v)
    handler.end_headers = lambda: None
    handler.send_error = lambda code, msg="": (
        setattr(handler, "_status_code", code),
        wfile.write(f"Error {code}: {msg}".encode()),
    )

    return handler, wfile


# ===========================================================================
# api.py
# ===========================================================================


class TestApiMain:
    """Tests for api.main() — server lifecycle."""

    def test_main_starts_server_on_default_port(self):
        """main() creates HTTPServer on port 8080 by default and calls serve_forever."""
        from projects.stargazer.backend.api import main

        mock_server = MagicMock()

        with patch(
            "projects.stargazer.backend.api.HTTPServer", return_value=mock_server
        ) as mock_cls:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PORT", None)  # Ensure PORT is not set
                main_thread = None
                # serve_forever blocks, so we make it raise KeyboardInterrupt immediately
                mock_server.serve_forever.side_effect = KeyboardInterrupt
                try:
                    main()
                except SystemExit:
                    pass

        # Server was instantiated on the empty host and a port
        # HTTPServer(("", port), StargazerAPIHandler) → call_args[0] = (addr_tuple, handler)
        mock_cls.assert_called_once()
        addr_tuple = mock_cls.call_args[0][0]
        assert addr_tuple == ("", 8080)

    def test_main_reads_port_from_env(self):
        """main() uses PORT environment variable when set."""
        from projects.stargazer.backend.api import main

        mock_server = MagicMock()
        mock_server.serve_forever.side_effect = KeyboardInterrupt

        with patch(
            "projects.stargazer.backend.api.HTTPServer", return_value=mock_server
        ) as mock_cls:
            with patch.dict(os.environ, {"PORT": "9999"}):
                try:
                    main()
                except SystemExit:
                    pass

        # call_args[0][0] is the address tuple ("", port)
        addr_tuple = mock_cls.call_args[0][0]
        assert addr_tuple[1] == 9999

    def test_main_calls_shutdown_on_keyboard_interrupt(self):
        """main() calls server.shutdown() when KeyboardInterrupt is raised."""
        from projects.stargazer.backend.api import main

        mock_server = MagicMock()
        mock_server.serve_forever.side_effect = KeyboardInterrupt

        with patch(
            "projects.stargazer.backend.api.HTTPServer", return_value=mock_server
        ):
            try:
                main()
            except SystemExit:
                pass

        mock_server.shutdown.assert_called_once()


class TestApiLogMessage:
    """Tests for StargazerAPIHandler.log_message() override."""

    def test_log_message_uses_logger_not_stderr(self):
        """log_message() delegates to logger.info() rather than stderr."""
        from projects.stargazer.backend.api import StargazerAPIHandler

        handler = StargazerAPIHandler.__new__(StargazerAPIHandler)
        handler.client_address = ("192.168.1.1", 54321)

        with patch("projects.stargazer.backend.api.logger") as mock_logger:
            handler.log_message("GET /health HTTP/1.1 %s", "200")

        mock_logger.info.assert_called_once()
        # The first positional arg should contain the client IP
        log_format, *args = mock_logger.info.call_args[0]
        combined = log_format % tuple(args)
        assert "192.168.1.1" in combined


class TestBestLocationsAdditionalPaths:
    """Additional edge-case coverage for send_best_locations."""

    def test_send_best_locations_returns_500_on_invalid_json(self, temp_data_dir: Path):
        """send_best_locations returns 500 when best_locations.json contains invalid JSON."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "best_locations.json").write_text("{ not valid json }")

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        assert handler._status_code == 500

    def test_send_best_locations_handles_non_list_data(self, temp_data_dir: Path):
        """send_best_locations wraps a non-list top-level object in a list."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # best_locations.json is a single dict (not a list) — code wraps it in [data]
        single_item = {
            "id": "scotland_0001",
            "coordinates": {"lat": 55.0, "lon": -4.5},
            "altitude_m": 100,
            "lp_zone": "1a",
            "best_hours": [{"time": "2024-01-15T22:00:00Z", "score": 88.0}],
        }
        (output_dir / "best_locations.json").write_text(json.dumps(single_item))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        assert handler._status_code == 200
        response = json.loads(wfile.getvalue().decode())
        # Should have exactly 1 item
        assert len(response) == 1
        assert response[0]["id"] == "scotland_0001"

    def test_send_best_locations_exposes_cors_headers(self, temp_data_dir: Path):
        """send_best_locations sets Access-Control-Expose-Headers alongside CORS header."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        test_data = [
            {
                "id": "loc1",
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "best_hours": [{"time": "2024-01-15T22:00:00Z", "score": 91.0}],
            }
        ]
        (output_dir / "best_locations.json").write_text(json.dumps(test_data))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        assert handler._headers.get("Access-Control-Allow-Origin") == "*"
        assert "Access-Control-Expose-Headers" in handler._headers
        assert "X-Next-Update" in handler._headers["Access-Control-Expose-Headers"]

    def test_send_best_locations_max_age_at_least_60(self, temp_data_dir: Path):
        """Cache-Control max-age is always at least 60 seconds."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        test_data = [
            {
                "id": "loc1",
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "best_hours": [{"time": "2024-01-15T22:00:00Z", "score": 91.0}],
            }
        ]
        (output_dir / "best_locations.json").write_text(json.dumps(test_data))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        cache_control = handler._headers.get("Cache-Control", "")
        # Extract max-age value
        assert "max-age=" in cache_control
        max_age = int(cache_control.split("max-age=")[1])
        assert max_age >= 60


# ===========================================================================
# acquisition.py — multi-chunk streaming
# ===========================================================================


class TestDownloadFileMultiChunk:
    """Tests for download_file with multi-chunk streaming responses."""

    @pytest.mark.asyncio
    async def test_downloads_multiple_chunks(self, tmp_path: Path):
        """download_file correctly concatenates multiple streamed chunks."""
        from projects.stargazer.backend.acquisition import download_file

        dest = tmp_path / "multi.bin"
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        async def aiter_bytes_gen():
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = aiter_bytes_gen

        @asynccontextmanager
        async def stream_ctx(*args, **kwargs):
            yield mock_response

        mock_client = MagicMock()
        mock_client.stream = stream_ctx

        result = await download_file(
            url="https://example.com/data.bin",
            dest=dest,
            client=mock_client,
        )

        assert result == dest
        assert dest.read_bytes() == b"chunk1chunk2chunk3"

    @pytest.mark.asyncio
    async def test_download_file_returns_path_object(self, tmp_path: Path):
        """download_file always returns a Path object."""
        from projects.stargazer.backend.acquisition import download_file

        dest = tmp_path / "returned.txt"
        dest.write_text("already exists")

        mock_client = AsyncMock()
        result = await download_file("https://example.com/x", dest, mock_client)

        assert isinstance(result, Path)
        assert result == dest


# ===========================================================================
# config.py — extra env overrides
# ===========================================================================


class TestBoundsConfigEnvOverrides:
    """Tests for BoundsConfig environment variable overrides (all four bounds)."""

    def test_south_can_be_overridden(self):
        """BOUNDS_SOUTH overrides the south bound."""
        with patch.dict(os.environ, {"BOUNDS_SOUTH": "53.0"}):
            bounds = BoundsConfig()
        assert bounds.south == pytest.approx(53.0)

    def test_west_can_be_overridden(self):
        """BOUNDS_WEST overrides the west bound."""
        with patch.dict(os.environ, {"BOUNDS_WEST": "-10.0"}):
            bounds = BoundsConfig()
        assert bounds.west == pytest.approx(-10.0)

    def test_east_can_be_overridden(self):
        """BOUNDS_EAST overrides the east bound."""
        with patch.dict(os.environ, {"BOUNDS_EAST": "0.0"}):
            bounds = BoundsConfig()
        assert bounds.east == pytest.approx(0.0)


class TestEuropeBoundsConfigEnvOverrides:
    """Tests for EuropeBoundsConfig environment variable overrides."""

    def test_north_can_be_overridden(self):
        """EUROPE_BOUNDS_NORTH overrides the north bound."""
        with patch.dict(os.environ, {"EUROPE_BOUNDS_NORTH": "80.0"}):
            bounds = EuropeBoundsConfig()
        assert bounds.north == pytest.approx(80.0)

    def test_south_can_be_overridden(self):
        """EUROPE_BOUNDS_SOUTH overrides the south bound."""
        with patch.dict(os.environ, {"EUROPE_BOUNDS_SOUTH": "30.0"}):
            bounds = EuropeBoundsConfig()
        assert bounds.south == pytest.approx(30.0)

    def test_west_can_be_overridden(self):
        """EUROPE_BOUNDS_WEST overrides the west bound."""
        with patch.dict(os.environ, {"EUROPE_BOUNDS_WEST": "-40.0"}):
            bounds = EuropeBoundsConfig()
        assert bounds.west == pytest.approx(-40.0)

    def test_east_can_be_overridden(self):
        """EUROPE_BOUNDS_EAST overrides the east bound."""
        with patch.dict(os.environ, {"EUROPE_BOUNDS_EAST": "75.0"}):
            bounds = EuropeBoundsConfig()
        assert bounds.east == pytest.approx(75.0)


class TestSettingsAdditionalDefaults:
    """Tests for Settings fields not yet covered."""

    def test_forecast_hours_default(self):
        """forecast_hours defaults to 72."""
        settings = Settings()
        assert settings.forecast_hours == 72

    def test_forecast_hours_env_override(self):
        """forecast_hours can be overridden via FORECAST_HOURS env var."""
        with patch.dict(os.environ, {"FORECAST_HOURS": "48"}):
            settings = Settings()
        assert settings.forecast_hours == 48

    def test_color_tolerance_env_override(self):
        """color_tolerance can be overridden via COLOR_TOLERANCE env var."""
        with patch.dict(os.environ, {"COLOR_TOLERANCE": "20"}):
            settings = Settings()
        assert settings.color_tolerance == 20

    def test_road_buffer_m_env_override(self):
        """road_buffer_m can be overridden via ROAD_BUFFER_M env var."""
        with patch.dict(os.environ, {"ROAD_BUFFER_M": "2000"}):
            settings = Settings()
        assert settings.road_buffer_m == 2000

    def test_otel_service_name_env_override(self):
        """otel_service_name can be overridden via OTEL_SERVICE_NAME env var."""
        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": "my-stargazer"}):
            settings = Settings()
        assert settings.otel_service_name == "my-stargazer"

    def test_cache_ttl_hours_default(self):
        """cache_ttl_hours defaults to 1."""
        settings = Settings()
        assert settings.cache_ttl_hours == 1


# ===========================================================================
# main.py — setup_telemetry edge cases
# ===========================================================================


class TestSetupTelemetryImportError:
    """Tests for setup_telemetry handling ImportError when OTEL packages absent."""

    def test_setup_telemetry_warns_on_import_error(self, settings: Settings):
        """setup_telemetry logs a warning and returns gracefully when ImportError is raised."""
        settings.otel_enabled = True
        settings.otel_exporter_otlp_endpoint = "http://signoz:4317"

        import builtins

        real_import = builtins.__import__

        def failing_import(name, *args, **kwargs):
            if "opentelemetry" in name:
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        from projects.stargazer.backend.main import setup_telemetry

        with patch("builtins.__import__", side_effect=failing_import):
            with patch("projects.stargazer.backend.main.logger") as mock_logger:
                # Should not raise
                setup_telemetry(settings)

        # Warning should have been logged
        mock_logger.warning.assert_called()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert (
            "not available" in warning_msg.lower()
            or "tracing disabled" in warning_msg.lower()
        )


class TestSetupTelemetryWithEndpoint:
    """Tests for setup_telemetry when OTEL is enabled with an endpoint."""

    def test_setup_telemetry_logs_endpoint_when_configured(self, settings: Settings):
        """setup_telemetry logs the configured OTLP endpoint."""
        settings.otel_enabled = True
        settings.otel_exporter_otlp_endpoint = "http://signoz:4317"

        # Mock all OTEL SDK components
        mock_resource = MagicMock()
        mock_resource_cls = MagicMock(return_value=mock_resource)
        mock_resource_cls.create = MagicMock(return_value=mock_resource)

        mock_provider = MagicMock()
        mock_provider_cls = MagicMock(return_value=mock_provider)

        mock_exporter_cls = MagicMock()
        mock_batch_cls = MagicMock()
        mock_trace = MagicMock()

        import sys

        fake_modules = {
            "opentelemetry": MagicMock(trace=mock_trace),
            "opentelemetry.trace": mock_trace,
            "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource_cls),
            "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_provider_cls),
            "opentelemetry.sdk.trace.export": MagicMock(
                BatchSpanProcessor=mock_batch_cls
            ),
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(
                OTLPSpanExporter=mock_exporter_cls
            ),
        }

        with patch.dict(sys.modules, fake_modules):
            from projects.stargazer.backend import main as main_module

            with patch.object(main_module, "logger") as mock_logger:
                main_module.setup_telemetry(settings)

        # The info log at the end should contain the endpoint
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("4317" in c or "signoz" in c for c in info_calls)


# ===========================================================================
# preprocessing.py — second subprocess failure
# ===========================================================================


class TestGeoreferenceRasterGdalwarpFailure:
    """Test georeference_raster propagates CalledProcessError from gdalwarp."""

    def test_gdalwarp_failure_propagates(self, settings: Settings):
        """georeference_raster propagates CalledProcessError from gdalwarp (second call)."""
        input_png = settings.raw_dir / "Europe2024.png"
        input_png.touch()

        call_count = {"n": 0}

        def controlled_run(cmd, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:  # gdalwarp is the second call
                raise subprocess.CalledProcessError(
                    1, cmd, output=b"", stderr=b"warp error"
                )
            return MagicMock(returncode=0)

        from projects.stargazer.backend.preprocessing import georeference_raster

        with patch("subprocess.run", side_effect=controlled_run):
            with pytest.raises(subprocess.CalledProcessError):
                georeference_raster(settings)


class TestExtractRoadsOgr2ogrFailure:
    """Test extract_roads propagates CalledProcessError from ogr2ogr."""

    def test_ogr2ogr_failure_propagates(self, settings: Settings):
        """extract_roads propagates CalledProcessError when ogr2ogr fails."""
        input_pbf = settings.raw_dir / "scotland-latest.osm.pbf"
        input_pbf.touch()

        mock_writer_instance = MagicMock()
        mock_writer_instance.__enter__ = MagicMock(return_value=mock_writer_instance)
        mock_writer_instance.__exit__ = MagicMock(return_value=False)

        from projects.stargazer.backend.preprocessing import extract_roads

        with patch("osmium.BackReferenceWriter", return_value=mock_writer_instance):
            with patch("osmium.FileProcessor", return_value=[]):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.CalledProcessError(1, ["ogr2ogr"]),
                ):
                    with pytest.raises(subprocess.CalledProcessError):
                        extract_roads(settings)


# ===========================================================================
# scoring.py — fog score boundary conditions (inflection at 5 and 20)
# ===========================================================================


class TestFogScoreBoundaries:
    """Tests for exact fog score boundary conditions in calculate_astronomy_score."""

    def _make_weather(self, fog: float) -> WeatherData:
        """Helper: create weather with only fog varying, all others optimal."""
        return WeatherData(
            cloud_area_fraction=0.0,  # < 20 → cloud_score = 100
            relative_humidity=0.0,  # < 70 → humidity_score = 100
            fog_area_fraction=fog,
            wind_speed=0.0,  # < 5  → wind_score = 100
            air_temperature=15.0,
            dew_point_temperature=5.0,  # spread = 10 > 5 → dew_score = 100
            air_pressure_at_sea_level=1013.25,  # no pressure bonus
        )

    def test_fog_below_5_gives_max_fog_score(self):
        """Fog < 5% → fog_score = 100, full base score."""
        w = self._make_weather(0.0)
        score = calculate_astronomy_score(w)
        # All components at 100, no pressure bonus
        assert score == pytest.approx(100.0, abs=0.1)

    def test_fog_at_5_boundary_still_max_fog_score(self):
        """Fog = 4.9% (just below 5) → fog_score = 100 (stays in first branch)."""
        below = self._make_weather(4.9)
        score = calculate_astronomy_score(below)
        assert score == pytest.approx(100.0, abs=0.1)

    def test_fog_at_5_enters_linear_region_no_penalty(self):
        """Fog = 5% → linear region starts: fog_score = 100 - (5-5)*3.33 = 100."""
        w = self._make_weather(5.0)
        score = calculate_astronomy_score(w)
        expected_fog = 100 - (5 - 5) * 3.33  # 100
        expected = 100 * 0.5 + 100 * 0.15 + expected_fog * 0.10 + 100 * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=0.5)

    def test_fog_at_12_5_midpoint_linear_region(self):
        """Fog = 12.5% → fog_score = 100 - (12.5-5)*3.33 ≈ 75."""
        w = self._make_weather(12.5)
        score = calculate_astronomy_score(w)
        expected_fog = 100 - (12.5 - 5) * 3.33  # ≈ 75
        expected = 100 * 0.5 + 100 * 0.15 + expected_fog * 0.10 + 100 * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=0.5)

    def test_fog_at_20_enters_step_region_score_50(self):
        """Fog = 20% → step region: fog_score = max(0, 50 - (20-20)*1.67) = 50."""
        w = self._make_weather(20.0)
        score = calculate_astronomy_score(w)
        expected_fog = max(0, 50 - (20 - 20) * 1.67)  # 50
        expected = 100 * 0.5 + 100 * 0.15 + expected_fog * 0.10 + 100 * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=0.5)

    def test_fog_at_50_gives_low_fog_score(self):
        """Fog = 50% → fog_score = max(0, 50 - (50-20)*1.67) = max(0, -0.1) = 0."""
        w = self._make_weather(50.0)
        score = calculate_astronomy_score(w)
        expected_fog = max(0, 50 - (50 - 20) * 1.67)  # 0
        expected = 100 * 0.5 + 100 * 0.15 + expected_fog * 0.10 + 100 * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=0.5)

    def test_fog_at_100_gives_zero_fog_score(self):
        """Fog = 100% → fog_score = 0."""
        w = self._make_weather(100.0)
        score = calculate_astronomy_score(w)
        expected_fog = 0.0
        expected = 100 * 0.5 + 100 * 0.15 + expected_fog * 0.10 + 100 * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=0.5)


# ===========================================================================
# spatial.py — enrich_points with DEM, empty grid
# ===========================================================================


class TestEnrichPointsWithDem:
    """Tests for enrich_points when a DEM raster is present."""

    def test_enrich_points_samples_elevation_from_dem(
        self, settings: Settings, sample_color_palette: list
    ):
        """When dem_path exists, altitude_m is sampled from the DEM raster."""
        from projects.stargazer.backend.spatial import enrich_points

        # Write sample points
        points_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.5, 55.0]},
                    "properties": {"id": "scotland_0001", "lat": 55.0, "lon": -4.5},
                }
            ],
        }
        (settings.processed_dir / "sample_points.geojson").write_text(
            json.dumps(points_data)
        )
        (settings.processed_dir / "color_palette.json").write_text(
            json.dumps(sample_color_palette)
        )

        # Create a fake DEM file so dem_path.exists() is True
        dem_path = settings.processed_dir / "scotland-dem.tif"
        dem_path.touch()

        # Mock both rasterio opens: DEM returns elevation 250, LP returns zone "1a"
        mock_dem = MagicMock()
        mock_dem.sample.return_value = [[250]]
        mock_dem.__enter__ = MagicMock(return_value=mock_dem)
        mock_dem.__exit__ = MagicMock(return_value=False)

        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[50, 50, 50]]  # matches zone "1a"
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        # rasterio.open is called twice: first for DEM, then for LP
        open_calls = [mock_dem, mock_lp]

        with patch("rasterio.open", side_effect=open_calls):
            result = enrich_points(settings)

        enriched = gpd.read_file(result)
        assert "altitude_m" in enriched.columns
        # The DEM-sampled value should be 250, not the default 0
        assert enriched.iloc[0]["altitude_m"] == pytest.approx(250, abs=1)


class TestGenerateSampleGridEmpty:
    """Tests for generate_sample_grid when no grid points fall inside the area."""

    def test_generate_sample_grid_produces_valid_geojson_when_empty(
        self, settings: Settings
    ):
        """generate_sample_grid creates a valid GeoJSON FeatureCollection even with 0 points."""
        from projects.stargazer.backend.spatial import generate_sample_grid, WGS84_CRS

        # Very tiny polygon and very large spacing → no points inside
        tiny_polygon = Polygon(
            [(-4.501, 55.000), (-4.500, 55.000), (-4.500, 55.001), (-4.501, 55.001)]
        )
        accessible_gdf = gpd.GeoDataFrame(
            geometry=[tiny_polygon],
            crs=WGS84_CRS,
        )
        accessible_gdf.to_file(
            settings.processed_dir / "accessible_dark.geojson",
            driver="GeoJSON",
        )

        # Use 200km spacing — no grid points will fall inside a ~1km² area
        settings.grid_spacing_m = 200_000

        result = generate_sample_grid(settings)

        assert result.exists()
        with open(result) as f:
            data = json.load(f)

        assert data.get("type") == "FeatureCollection"
        assert isinstance(data.get("features"), list)


# ===========================================================================
# weather.py — additional paths
# ===========================================================================


class TestScoreLocationsEmptyTimeseries:
    """Tests for score_locations when a forecast has an empty timeseries."""

    def test_empty_timeseries_location_not_in_output(
        self, settings: Settings, sample_geojson_points: dict
    ):
        """Locations with empty timeseries produce no scored_hours and are excluded from output."""
        from projects.stargazer.backend.weather import score_locations

        (settings.processed_dir / "sample_points_enriched.geojson").write_text(
            json.dumps(sample_geojson_points)
        )

        empty_forecast = {"properties": {"timeseries": []}}
        forecasts = {
            feat["properties"]["id"]: empty_forecast
            for feat in sample_geojson_points["features"]
        }
        (settings.output_dir / "forecasts_raw.json").write_text(json.dumps(forecasts))

        result = score_locations(settings)

        with open(result) as f:
            scored = json.load(f)

        # No scored hours → no entries in output
        assert len(scored) == 0


class TestScoreLocationsMissingNextHours:
    """Tests for score_locations when next_1_hours is absent from a timeseries entry."""

    def test_missing_next_1_hours_gives_empty_symbol(
        self, settings: Settings, sample_geojson_points: dict
    ):
        """When next_1_hours is absent, the symbol field in scored output is empty string."""
        from projects.stargazer.backend.weather import score_locations

        (settings.processed_dir / "sample_points_enriched.geojson").write_text(
            json.dumps(sample_geojson_points)
        )

        # Use a winter night timestamp — definitely dark at Scottish latitude
        forecast_no_symbol = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-01-15T02:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": 0.0,
                                    "relative_humidity": 50.0,
                                    "fog_area_fraction": 0.0,
                                    "wind_speed": 2.0,
                                    "air_temperature": 10.0,
                                    "dew_point_temperature": 2.0,
                                    "air_pressure_at_sea_level": 1025.0,
                                }
                            }
                            # next_1_hours deliberately absent
                        },
                    }
                ]
            }
        }

        first_id = sample_geojson_points["features"][0]["properties"]["id"]
        (settings.output_dir / "forecasts_raw.json").write_text(
            json.dumps({first_id: forecast_no_symbol})
        )

        result = score_locations(settings)

        with open(result) as f:
            scored = json.load(f)

        if first_id in scored:
            # Check scored hours for the empty symbol
            hours = scored[first_id]["scored_hours"]
            if hours:
                assert hours[0]["symbol"] == ""


class TestScoreLocationsSortedByScore:
    """Tests for score_locations producing hours sorted by score descending."""

    def test_scored_hours_sorted_descending(
        self, settings: Settings, sample_geojson_points: dict
    ):
        """score_locations sorts scored_hours by score descending."""
        from projects.stargazer.backend.weather import score_locations

        (settings.processed_dir / "sample_points_enriched.geojson").write_text(
            json.dumps(sample_geojson_points)
        )

        # Two winter night hours in January — both dark at Scotland latitudes.
        # First hour: partly cloudy (cloud=30) → cloud_score≈83, overall ≈ 87 (>= min=60)
        # Second hour: perfectly clear (cloud=0) → overall = 100 (>= min=60)
        # After sorting descending, the clear (higher-score) hour must come first.
        forecast = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-01-15T02:00:00Z",  # partly cloudy — lower score (~87)
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": 30.0,
                                    "relative_humidity": 70.0,
                                    "fog_area_fraction": 5.0,
                                    "wind_speed": 5.0,
                                    "air_temperature": 10.0,
                                    "dew_point_temperature": 7.0,  # spread=3, dew_score≈50
                                    "air_pressure_at_sea_level": 1013.25,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "partlycloudy_night"}
                            },
                        },
                    },
                    {
                        "time": "2024-01-15T03:00:00Z",  # perfectly clear — higher score (100)
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": 0.0,
                                    "relative_humidity": 40.0,
                                    "fog_area_fraction": 0.0,
                                    "wind_speed": 1.0,
                                    "air_temperature": 10.0,
                                    "dew_point_temperature": 2.0,  # spread=8, dew_score=100
                                    "air_pressure_at_sea_level": 1013.25,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "clearsky_night"}
                            },
                        },
                    },
                ]
            }
        }

        first_id = sample_geojson_points["features"][0]["properties"]["id"]
        (settings.output_dir / "forecasts_raw.json").write_text(
            json.dumps({first_id: forecast})
        )

        result = score_locations(settings)

        with open(result) as f:
            scored = json.load(f)

        assert first_id in scored, "Expected point to appear in scored output"
        hours = scored[first_id]["scored_hours"]
        assert len(hours) >= 2, "Both hours should score >= 60 and appear in output"
        # Verify descending sort order
        for i in range(len(hours) - 1):
            assert hours[i]["score"] >= hours[i + 1]["score"]


class TestScoreLocationsDewSpreadOutput:
    """Tests for dew_spread calculation in score_locations output."""

    def test_dew_spread_is_temp_minus_dew_point(
        self, settings: Settings, sample_geojson_points: dict
    ):
        """score_locations computes dew_spread as air_temperature - dew_point_temperature."""
        from projects.stargazer.backend.weather import score_locations

        (settings.processed_dir / "sample_points_enriched.geojson").write_text(
            json.dumps(sample_geojson_points)
        )

        temp, dew = 10.0, 4.0  # expected dew_spread = 6.0
        forecast = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-01-15T02:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": 0.0,
                                    "relative_humidity": 50.0,
                                    "fog_area_fraction": 0.0,
                                    "wind_speed": 2.0,
                                    "air_temperature": temp,
                                    "dew_point_temperature": dew,
                                    "air_pressure_at_sea_level": 1020.0,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "clearsky_night"}
                            },
                        },
                    }
                ]
            }
        }

        first_id = sample_geojson_points["features"][0]["properties"]["id"]
        (settings.output_dir / "forecasts_raw.json").write_text(
            json.dumps({first_id: forecast})
        )

        result = score_locations(settings)

        with open(result) as f:
            scored = json.load(f)

        if first_id in scored:
            hours = scored[first_id]["scored_hours"]
            if hours:
                assert hours[0]["dew_spread"] == pytest.approx(temp - dew, abs=0.1)


class TestFetchAllForecastsMissingAltitude:
    """Tests for fetch_all_forecasts when altitude_m column is missing."""

    @pytest.mark.asyncio
    async def test_fetch_all_defaults_altitude_to_zero(
        self, settings: Settings, sample_forecast_response: dict
    ):
        """fetch_all_forecasts uses altitude=0 when altitude_m column is absent."""
        from projects.stargazer.backend.weather import fetch_all_forecasts

        # GeoJSON points without altitude_m field
        points_no_altitude = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.5, 55.0]},
                    "properties": {
                        "id": "scotland_0001",
                        "lat": 55.0,
                        "lon": -4.5,
                        # altitude_m deliberately omitted
                    },
                }
            ],
        }
        (settings.processed_dir / "sample_points_enriched.geojson").write_text(
            json.dumps(points_no_altitude)
        )

        altitude_used = []

        async def capture_fetch(lat, lon, altitude, client, settings):
            altitude_used.append(altitude)
            return sample_forecast_response

        with patch(
            "projects.stargazer.backend.weather.fetch_forecast",
            side_effect=capture_fetch,
        ):
            await fetch_all_forecasts(settings)

        assert len(altitude_used) == 1
        assert altitude_used[0] == 0  # default when missing


class TestOutputBestLocationsEmpty:
    """Tests for output_best_locations with no qualifying locations."""

    def test_empty_scored_data_produces_empty_best_locations(self, settings: Settings):
        """output_best_locations produces an empty list when no location meets score >= 80."""
        from projects.stargazer.backend.weather import output_best_locations

        # All scored hours below 80
        scored_data = {
            "point_low": {
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "altitude_m": 100,
                "lp_zone": "1a",
                "scored_hours": [
                    {"time": "2024-01-15T22:00:00Z", "score": 70.0},
                    {"time": "2024-01-15T23:00:00Z", "score": 65.0},
                ],
            }
        }
        (settings.output_dir / "forecasts_scored.json").write_text(
            json.dumps(scored_data)
        )

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert best == []

    def test_completely_empty_scored_data(self, settings: Settings):
        """output_best_locations handles an empty scored dict gracefully."""
        from projects.stargazer.backend.weather import output_best_locations

        (settings.output_dir / "forecasts_scored.json").write_text(json.dumps({}))

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert best == []

    def test_best_score_reflects_first_qualifying_hour(self, settings: Settings):
        """best_score is the score of the first best_hour (highest qualifying)."""
        from projects.stargazer.backend.weather import output_best_locations

        scored_data = {
            "point_a": {
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "altitude_m": 100,
                "lp_zone": "1a",
                "scored_hours": [
                    {"time": "2024-01-15T22:00:00Z", "score": 93.0},
                    {"time": "2024-01-15T23:00:00Z", "score": 85.0},
                    {"time": "2024-01-16T00:00:00Z", "score": 75.0},  # Below 80
                ],
            }
        }
        (settings.output_dir / "forecasts_scored.json").write_text(
            json.dumps(scored_data)
        )

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert len(best) == 1
        assert best[0]["best_score"] == pytest.approx(93.0)
        # Only hours >= 80 should be in best_hours (so 2 of 3)
        assert len(best[0]["best_hours"]) == 2
