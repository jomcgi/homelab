from fastapi import Request
import requests
from settings import GITHUB_UPTIME_SETTINGS

# UPTIME_KUMA_URL = "http://uptime-kuma.uptime-kuma.svc.cluster.local:3001"

async def uptime(request: Request) -> None:
    gh_payload = await request.json()
    assert isinstance(gh_payload, dict)
    assert "workflow_run" in gh_payload
    workflow_run = gh_payload["workflow_run"]
    if workflow_run["status"] != "completed":
        return
    if workflow_run["name"] != "Deploy Homelab":
        return
    kuma_endpoint = GITHUB_UPTIME_SETTINGS.workflow_mapping.get(workflow_run["name"])
    if kuma_endpoint is None:
        return
    url = f"{GITHUB_UPTIME_SETTINGS.uptime_kuma_url}/api/push/{kuma_endpoint}"
    if workflow_run["conclusion"] not in GITHUB_UPTIME_SETTINGS.up_statuses:
        message = f"Workflow {workflow_run['name']} failed - {workflow_run['url']}"
        requests.get(url, params={  
            "status": "down",
            "message": message})   
    else:
        message = f"Workflow {workflow_run['name']} succeeded - {workflow_run['url']}"
        requests.get(url, params={
            "status": "up",
            "message": message})
