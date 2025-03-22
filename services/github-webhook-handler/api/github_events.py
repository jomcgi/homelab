from fastapi import Request
from settings import HANDLER_SETTINGS
import asyncio
import httpx

async def uptime_kuma_success(
    workflow_run: dict[str, str], url: str
) -> None:
    message = f"Workflow {workflow_run['name']} succeeded - {workflow_run['url']}"
    async with httpx.AsyncClient() as client:
        await client.get(url, params={
            "status": "up",
            "message": message})
        
async def uptime_kuma_failure(
    workflow_run: dict[str, str], url: str
) -> None:
    message = f"Workflow {workflow_run['name']} failed - {workflow_run['url']}"
    async with httpx.AsyncClient() as client:
        await client.get(url, params={
            "status": "down",
            "message": message})    


async def uptime_kuma_push_monitor(request: Request) -> None:
    gh_payload = await request.json()
    workflow_run = gh_payload["workflow_run"]
    kuma_endpoint = HANDLER_SETTINGS.workflow_mapping.get(workflow_run["name"], None)
    if kuma_endpoint is None:
        print(f"No mapping for {workflow_run['name']}")
        return
    if workflow_run["status"] != "completed":
        return
    url = f"{HANDLER_SETTINGS.uptime_kuma_url}/api/push/{kuma_endpoint}"
    if workflow_run["conclusion"] not in HANDLER_SETTINGS.up_statuses:
        await uptime_kuma_failure(workflow_run, url)
    else:
        await uptime_kuma_success(workflow_run, url)
        

async def otel_collector_githubreceiver(request: Request) -> None:
    payload = await request.json()
    headers = dict(request.headers)
    headers.pop('content-length', None)
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                HANDLER_SETTINGS.otel_github_receiver_url,
                json=payload,
                headers=headers,
                cookies=request.cookies,
            )
        except Exception as e:
            print("Failed to post to otel collector")
            print(e)
    

async def handle_events(request: Request) -> None:
    uptime_kuma_push = uptime_kuma_push_monitor(request)
    otel_collector_post = otel_collector_githubreceiver(request)
    await asyncio.gather(uptime_kuma_push, otel_collector_post)

