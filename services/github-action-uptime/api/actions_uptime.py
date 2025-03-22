from fastapi import Request
import requests

UP_STATUSES = ["skipped", "cancelled", "success"]

UPTIME_KUMA_URL = "http://uptime-kuma.uptime-kuma.svc.cluster.local:3001"
UPTIME_KUMA_URL = "http://host.docker.internal:30333"

async def uptime(request: Request) -> None:
    gh_payload = await request.json()
    assert isinstance(gh_payload, dict)
    assert "workflow_run" in gh_payload
    workflow_run = gh_payload["workflow_run"]
    if workflow_run["status"] != "completed":
        return
    if workflow_run["name"] != "Deploy Homelab":
        return  
    url = f"{UPTIME_KUMA_URL}/api/push/6jsi0iFnCb"
    if workflow_run["conclusion"] not in UP_STATUSES:
        message = f"Workflow {workflow_run['name']} failed - {workflow_run['url']}"
        requests.get(url, params={  
            "status": "down",
            "message": message})   
    else:
        message = f"Workflow {workflow_run['name']} succeeded - {workflow_run['url']}"
        requests.get(url, params={
            "status": "up",
            "message": message})
