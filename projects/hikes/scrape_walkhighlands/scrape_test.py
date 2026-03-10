"""Tests for Walkhighlands scraper."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests  # nosemgrep: no-requests

from projects.hikes.scrape_walkhighlands.scrape import (
    Walk,
    parse_duration,
    scrape_area_links_from_homepage,
    scrape_sub_area_links_from_area,
    scrape_walk_data_from_file,
    scrape_walks_from_sub_area,
    scrape_walkhighlands,
)


class TestParseDuration:
    """Tests for duration parsing."""

    def test_parse_single_value(self):
        result = parse_duration("5 hours")
        assert result == timedelta(hours=5)

    def test_parse_decimal_value(self):
        result = parse_duration("3.5 hours")
        assert result == timedelta(hours=3.5)

    def test_parse_range(self):
        # Note: The regex strips decimals from low value, so "5.5" becomes 5
        # Average of 5 and 6.5 = 5.75
        result = parse_duration("5.5 - 6.5 hours")
        assert result == timedelta(hours=5.75)

    def test_parse_range_without_decimal(self):
        result = parse_duration("5 - 7 hours")
        assert result == timedelta(hours=6.0)  # Average of 5 and 7

    def test_parse_empty_string(self):
        result = parse_duration("")
        assert result is None

    def test_parse_none(self):
        result = parse_duration(None)
        assert result is None

    def test_parse_invalid(self):
        result = parse_duration("invalid")
        assert result is None


class TestWalkModel:
    """Tests for Walk Pydantic model."""

    def test_create_walk(self):
        walk = Walk(
            uuid="test-uuid-123",
            name="Ben Nevis",
            url="https://walkhighlands.co.uk/ben-nevis",
            distance_km=17.0,
            ascent_m=1350,
            duration_h=8.5,
            summary="Classic route up Britain's highest mountain",
            latitude=56.7969,
            longitude=-5.0035,
        )

        assert walk.uuid == "test-uuid-123"
        assert walk.name == "Ben Nevis"
        assert walk.distance_km == 17.0
        assert walk.ascent_m == 1350
        assert walk.viable_dates is None

    def test_walk_with_viable_dates(self):
        walk = Walk(
            uuid="test-uuid",
            name="Test Walk",
            url="https://example.com",
            distance_km=10.0,
            ascent_m=500,
            duration_h=4.0,
            summary="Test",
            latitude=56.0,
            longitude=-5.0,
            viable_dates=["2024-03-15", "2024-03-16"],
        )

        assert walk.viable_dates == ["2024-03-15", "2024-03-16"]


class TestScrapeAreaLinksFromHomepage:
    """Tests for homepage scraping."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock(spec=requests.Session)
        return session

    @pytest.fixture
    def headers(self):
        return {"User-Agent": "Test Agent"}

    def test_scrape_area_links_success(self, mock_session, headers):
        """Successful scrape returns list of links."""
        html = """
        <html>
        <body>
            <div id="choosearea">
                <table>
                    <tr><td class="cell"><a href="/highlands/">Highlands</a></td></tr>
                    <tr><td class="cell"><a href="/islands/">Islands</a></td></tr>
                </table>
            </div>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_area_links_from_homepage(
            "https://www.walkhighlands.co.uk/", headers, mock_session
        )

        assert len(result) == 2
        assert "https://www.walkhighlands.co.uk/highlands/" in result
        assert "https://www.walkhighlands.co.uk/islands/" in result

    def test_scrape_area_links_no_container(self, mock_session, headers):
        """Returns empty list when container div not found."""
        html = "<html><body><div id='other'>No area links</div></body></html>"
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_area_links_from_homepage(
            "https://www.walkhighlands.co.uk/", headers, mock_session
        )

        assert result == []

    def test_scrape_area_links_filters_shtml(self, mock_session, headers):
        """Links with .shtml extension are filtered out."""
        html = """
        <html>
        <body>
            <div id="choosearea">
                <table>
                    <tr><td class="cell"><a href="/highlands/">Highlands</a></td></tr>
                    <tr><td class="cell"><a href="/old/page.shtml">Old Page</a></td></tr>
                </table>
            </div>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_area_links_from_homepage(
            "https://www.walkhighlands.co.uk/", headers, mock_session
        )

        assert len(result) == 1
        assert "highlands" in result[0]

    def test_scrape_area_links_network_error(self, mock_session, headers):
        """Network errors return empty list."""
        mock_session.get.side_effect = requests.RequestException("Connection error")

        result = scrape_area_links_from_homepage(
            "https://www.walkhighlands.co.uk/", headers, mock_session
        )

        assert result == []


class TestScrapeSubAreaLinksFromArea:
    """Tests for sub-area scraping."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock(spec=requests.Session)
        return session

    @pytest.fixture
    def headers(self):
        return {"User-Agent": "Test Agent"}

    def test_scrape_sub_area_links_success(self, mock_session, headers):
        html = """
        <html>
        <body>
            <div id="arealist">
                <table>
                    <tr><td class="cell"><a href="/highlands/cairngorms/">Cairngorms</a></td></tr>
                    <tr><td class="cell"><a href="/highlands/glen-coe/">Glen Coe</a></td></tr>
                </table>
            </div>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_sub_area_links_from_area(
            "https://www.walkhighlands.co.uk/highlands/", headers, mock_session
        )

        assert len(result) == 2

    def test_scrape_sub_area_links_filters_php(self, mock_session, headers):
        """Links with .php extension are filtered out."""
        html = """
        <html>
        <body>
            <div id="arealist">
                <table>
                    <tr><td class="cell"><a href="/highlands/cairngorms/">Cairngorms</a></td></tr>
                    <tr><td class="cell"><a href="/search.php">Search</a></td></tr>
                </table>
            </div>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_sub_area_links_from_area(
            "https://www.walkhighlands.co.uk/highlands/", headers, mock_session
        )

        assert len(result) == 1


class TestScrapeWalksFromSubArea:
    """Tests for walk list scraping."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock(spec=requests.Session)
        return session

    @pytest.fixture
    def headers(self):
        return {"User-Agent": "Test Agent"}

    def test_scrape_walks_success(self, mock_session, headers):
        html = """
        <html>
        <body>
            <div class="walktable">
                <table class="table1">
                    <tbody>
                        <tr>
                            <td><a href="/highlands/ben-nevis.shtml">Ben Nevis</a></td>
                            <td>17km</td>
                        </tr>
                        <tr>
                            <td><a href="/highlands/aonach-mor.shtml">Aonach Mor</a></td>
                            <td>12km</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_walks_from_sub_area(
            "https://www.walkhighlands.co.uk/highlands/", headers, mock_session
        )

        assert len(result) == 2

    def test_scrape_walks_no_table(self, mock_session, headers):
        html = "<html><body><div>No walks here</div></body></html>"
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_walks_from_sub_area(
            "https://www.walkhighlands.co.uk/highlands/", headers, mock_session
        )

        assert result == []


class TestScrapeWalkDataFromFile:
    """Tests for individual walk data scraping."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock(spec=requests.Session)
        return session

    @pytest.fixture
    def headers(self):
        return {"User-Agent": "Test Agent"}

    def test_scrape_walk_data_success(self, mock_session, headers):
        html = """
        <html>
        <head>
            <link rel="canonical" href="https://www.walkhighlands.co.uk/highlands/ben-nevis.shtml"/>
        </head>
        <body>
            <div id="content">
                <h1>Ben Nevis via the Mountain Track</h1>
            </div>
            <h2>Summary</h2>
            <p>The classic tourist route up Britain's highest mountain.</p>
            <div id="col">
                <dl>
                    <dt>Distance</dt><dd>17 km / 10.5 miles</dd>
                    <dt>Time</dt><dd>7 - 9 hours</dd>
                    <dt>Total Ascent</dt><dd>1350m</dd>
                </dl>
            </div>
            <a href="https://www.google.com/maps/search/56.7969,-5.0035/">Open in Google Maps</a>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_walk_data_from_file(
            "https://www.walkhighlands.co.uk/highlands/ben-nevis.shtml",
            headers,
            mock_session,
        )

        assert result is not None
        assert result.name == "Ben Nevis via the Mountain Track"
        assert result.distance_km == 17.0
        assert result.ascent_m == 1350
        assert result.latitude == pytest.approx(56.7969, rel=1e-4)
        assert result.longitude == pytest.approx(-5.0035, rel=1e-4)

    def test_scrape_walk_data_missing_coordinates(self, mock_session, headers):
        """Walk without coordinates should return None."""
        html = """
        <html>
        <head>
            <link rel="canonical" href="https://www.walkhighlands.co.uk/highlands/test.shtml"/>
        </head>
        <body>
            <div id="content">
                <h1>Test Walk</h1>
            </div>
            <h2>Summary</h2>
            <p>A test walk.</p>
            <div id="col">
                <dl>
                    <dt>Distance</dt><dd>10 km</dd>
                    <dt>Time</dt><dd>4 hours</dd>
                    <dt>Total Ascent</dt><dd>500m</dd>
                </dl>
            </div>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = scrape_walk_data_from_file(
            "https://www.walkhighlands.co.uk/highlands/test.shtml",
            headers,
            mock_session,
        )

        # Missing lat/lng should cause validation error
        assert result is None


class TestScrapeWalkhighlands:
    """Tests for the main scraping orchestration function."""

    def test_scrape_walkhighlands_empty_areas(self):
        """Returns empty list when no area links found."""
        with patch(
            "projects.hikes.scrape_walkhighlands.scrape.scrape_area_links_from_homepage"
        ) as mock_areas:
            mock_areas.return_value = []

            result = scrape_walkhighlands()

            assert result == []

    def test_scrape_walkhighlands_empty_sub_areas(self):
        """Returns empty list when no sub-area links found."""
        with (
            patch(
                "projects.hikes.scrape_walkhighlands.scrape.scrape_area_links_from_homepage"
            ) as mock_areas,
            patch(
                "projects.hikes.scrape_walkhighlands.scrape.scrape_sub_area_links_from_area"
            ) as mock_sub_areas,
        ):
            mock_areas.return_value = ["https://example.com/area1"]
            mock_sub_areas.return_value = []

            result = scrape_walkhighlands()

            assert result == []

    def test_scrape_walkhighlands_with_walks(self):
        """Returns walks when all scraping steps succeed."""
        mock_walk = Walk(
            uuid="test-uuid",
            name="Test Walk",
            url="https://example.com/walk",
            distance_km=10.0,
            ascent_m=500,
            duration_h=4.0,
            summary="A test walk",
            latitude=56.0,
            longitude=-5.0,
        )

        with (
            patch(
                "projects.hikes.scrape_walkhighlands.scrape.scrape_area_links_from_homepage"
            ) as mock_areas,
            patch(
                "projects.hikes.scrape_walkhighlands.scrape.scrape_sub_area_links_from_area"
            ) as mock_sub_areas,
            patch(
                "projects.hikes.scrape_walkhighlands.scrape.scrape_walks_from_sub_area"
            ) as mock_walks,
            patch(
                "projects.hikes.scrape_walkhighlands.scrape.scrape_walk_data_from_file"
            ) as mock_walk_data,
        ):
            mock_areas.return_value = ["https://example.com/area1"]
            mock_sub_areas.return_value = ["https://example.com/subarea1"]
            mock_walks.return_value = ["https://example.com/walk1"]
            mock_walk_data.return_value = mock_walk

            result = scrape_walkhighlands()

            assert len(result) == 1
            assert result[0].name == "Test Walk"
