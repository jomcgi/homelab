# Tests for httpx-client-no-timeout rule.
import httpx


async def bad_client_no_timeout():
    # ruleid: httpx-client-no-timeout
    async with httpx.AsyncClient() as client:
        return await client.get("https://example.com")


async def bad_client_only_other_params():
    # ruleid: httpx-client-no-timeout
    async with httpx.AsyncClient(headers={"X-Custom": "value"}) as client:
        return await client.get("https://example.com")


async def ok_client_with_timeout():
    # ok: timeout is specified
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.get("https://example.com")


async def ok_client_with_timeout_object():
    # ok: using httpx.Timeout object
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        return await client.get("https://example.com")


async def ok_client_with_none_timeout():
    # ok: explicit None is an intentional choice (no timeout)
    async with httpx.AsyncClient(timeout=None) as client:
        return await client.get("https://internal-service")
