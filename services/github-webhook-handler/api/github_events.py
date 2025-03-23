from fastapi import Request
from settings import HANDLER_SETTINGS
import asyncio
import httpx
import structlog

logger = structlog.get_logger(__name__)

async def uptime_kuma_success(
    workflow_run: dict[str, str], url: str
) -> None:
    message = f"Workflow {workflow_run['name']} succeeded - {workflow_run['url']}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:  # Set 5-second timeout
            await client.get(url, params={
                "status": "up",
                "message": message})
            logger.info("Successfully sent success status to Uptime Kuma", url=url)
    except httpx.ConnectTimeout:
        logger.error("Connection timeout when sending success to Uptime Kuma", url=url)
    except Exception as e:
        logger.error("Failed to send success to Uptime Kuma", url=url, error=str(e))
        
async def uptime_kuma_failure(
    workflow_run: dict[str, str], url: str
) -> None:
    message = f"Workflow {workflow_run['name']} failed - {workflow_run['url']}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:  # Set 5-second timeout
            await client.get(url, params={
                "status": "down",
                "message": message})
            logger.info("Successfully sent failure status to Uptime Kuma", url=url)
    except httpx.ConnectTimeout:
        logger.error("Connection timeout when sending failure to Uptime Kuma", url=url)
    except Exception as e:
        logger.error("Failed to send failure to Uptime Kuma", url=url, error=str(e))


async def uptime_kuma_push_monitor(payload: dict) -> None:
    try:
        workflow_run = payload["workflow_run"]
    except KeyError:
        logger.debug("No workflow_run in payload, skipping Uptime Kuma notification")
        return
    
    kuma_endpoint = HANDLER_SETTINGS.workflow_mapping.get(workflow_run["name"], None)
    if kuma_endpoint is None:
        logger.info(f"No mapping for workflow {workflow_run['name']}")
        return
    
    if workflow_run["status"] != "completed":
        logger.debug(f"Workflow {workflow_run['name']} not completed, skipping")
        return
    
    url = f"{HANDLER_SETTINGS.uptime_kuma_url}/api/push/{kuma_endpoint}"
    logger.info(f"Sending status to Uptime Kuma", 
                workflow=workflow_run["name"], 
                conclusion=workflow_run["conclusion"], 
                url=url)
    
    if workflow_run["conclusion"] not in HANDLER_SETTINGS.up_statuses:
        await uptime_kuma_failure(workflow_run, url)
    else:
        await uptime_kuma_success(workflow_run, url)
        

async def otel_collector_githubreceiver(payload: dict, request: Request) -> None:
    headers = dict(request.headers)
    headers.pop('content-length', None)
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:  # Set 5-second timeout
            await client.post(
                HANDLER_SETTINGS.otel_github_receiver_url,
                json=payload,
                headers=headers,
                cookies=request.cookies,
            )
            logger.info("Successfully sent payload to OpenTelemetry collector")
    except httpx.ConnectTimeout:
        logger.error("Connection timeout when sending to OpenTelemetry collector")
    except Exception as e:
        logger.error("Failed to post to OpenTelemetry collector", error=str(e))
    

async def handle_events(request: Request) -> None:
    payload = await request.json()
    logger.info("Received GitHub webhook event")
    
    uptime_kuma_push = uptime_kuma_push_monitor(payload)
    otel_collector_post = otel_collector_githubreceiver(payload, request)
    
    # Execute both tasks and continue even if one fails
    results = await asyncio.gather(
        uptime_kuma_push, 
        otel_collector_post, 
        return_exceptions=True
    )
    
    # Log any exceptions that were returned
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            service_name = "uptime_kuma_push" if i == 0 else "otel_collector_post"
            logger.error(f"Error in {service_name}", error=str(result))