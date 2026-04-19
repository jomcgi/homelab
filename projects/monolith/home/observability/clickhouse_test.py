import pytest
import httpx

from home.observability.clickhouse import ClickHouseClient


@pytest.fixture
def mock_ch_response():
    """Standard ClickHouse FORMAT JSON response."""
    return {
        "meta": [{"name": "value", "type": "Float64"}],
        "data": [{"value": 99.9712}],
        "rows": 1,
    }


@pytest.fixture
def mock_ch_multi_row():
    return {
        "meta": [
            {"name": "bucket", "type": "UInt64"},
            {"name": "value", "type": "Float64"},
        ],
        "data": [
            {"bucket": 1, "value": 100.0},
            {"bucket": 2, "value": 99.5},
            {"bucket": 3, "value": 100.0},
        ],
        "rows": 3,
    }


class TestClickHouseClient:
    @pytest.mark.asyncio
    async def test_query_scalar_returns_first_row_value(self, mock_ch_response):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_ch_response)
        )
        client = ClickHouseClient(base_url="http://fake:8123", transport=transport)
        result = await client.query_scalar("SELECT 1 AS value")
        assert result == 99.9712

    @pytest.mark.asyncio
    async def test_query_scalar_returns_none_on_empty(self):
        empty = {"meta": [], "data": [], "rows": 0}
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json=empty))
        client = ClickHouseClient(base_url="http://fake:8123", transport=transport)
        result = await client.query_scalar("SELECT 1 AS value WHERE 0")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_rows_returns_all_rows(self, mock_ch_multi_row):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_ch_multi_row)
        )
        client = ClickHouseClient(base_url="http://fake:8123", transport=transport)
        rows = await client.query_rows("SELECT bucket, value FROM ...")
        assert len(rows) == 3
        assert rows[0]["bucket"] == 1
        assert rows[1]["value"] == 99.5

    @pytest.mark.asyncio
    async def test_query_appends_format_json(self):
        seen_body = None

        def handler(req):
            nonlocal seen_body
            seen_body = req.content.decode()
            return httpx.Response(200, json={"meta": [], "data": [], "rows": 0})

        transport = httpx.MockTransport(handler)
        client = ClickHouseClient(base_url="http://fake:8123", transport=transport)
        await client.query_scalar("SELECT 1 AS value")
        assert seen_body.rstrip().endswith("FORMAT JSON")

    @pytest.mark.asyncio
    async def test_query_raises_on_http_error(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, text="DB error")
        )
        client = ClickHouseClient(base_url="http://fake:8123", transport=transport)
        with pytest.raises(httpx.HTTPStatusError):
            await client.query_scalar("BAD QUERY")
