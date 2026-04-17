# Tests for httpx-cf-auth-must-disable-redirects rule.
# When CF tokens expire, the server returns 302 to the login page;
# httpx silently follows it, returning HTML instead of JSON.
import httpx


def bad_client_cf_auth_follows_redirects(url: str, token: str):
    # ruleid: httpx-cf-auth-must-disable-redirects
    client = httpx.Client(
        base_url=url, cookies={"CF_Authorization": token}, timeout=30.0
    )
    return client


def ok_client_cf_auth_no_redirects(url: str, token: str):
    # ok: follow_redirects=False prevents silent redirect to CF login page
    client = httpx.Client(
        base_url=url,
        cookies={"CF_Authorization": token},
        follow_redirects=False,
        timeout=30.0,
    )
    return client


async def ok_async_client_cf_auth_no_redirects(token: str):
    # ok: AsyncClient also safe when follow_redirects=False
    client = httpx.AsyncClient(
        cookies={"CF_Authorization": token}, follow_redirects=False
    )
    return client
