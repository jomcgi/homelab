# Tests for unsafe-json-field-access rule.
import httpx


async def bad_direct_access_after_raise_for_status():
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("https://api.example.com/data")
        resp.raise_for_status()
        # ruleid: unsafe-json-field-access
        value = resp.json()["key"]
        return value


async def bad_direct_access_inline():
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("https://api.example.com/data")
        resp.raise_for_status()
        # ruleid: unsafe-json-field-access
        return resp.json()["result"]


async def bad_direct_access_requests_style(session):
    resp = session.get("https://api.example.com/data")
    resp.raise_for_status()
    # ruleid: unsafe-json-field-access
    token = resp.json()["access_token"]
    return token


async def ok_access_with_try_except():
    # ok: wrapped in try/except handles KeyError
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("https://api.example.com/data")
        resp.raise_for_status()
        try:
            value = resp.json()["key"]
        except (KeyError, ValueError) as e:
            raise RuntimeError("unexpected response shape") from e
        return value


async def ok_access_with_get():
    # ok: .get() returns None instead of raising KeyError
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("https://api.example.com/data")
        resp.raise_for_status()
        data = resp.json()
        value = data.get("key")
        return value


async def ok_access_in_try_block():
    # ok: the access is inside a try block
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("https://api.example.com/data")
        try:
            resp.raise_for_status()
            value = resp.json()["key"]
        except Exception as e:
            raise RuntimeError("request failed") from e
        return value
