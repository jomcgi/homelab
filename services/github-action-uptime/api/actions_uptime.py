from fastapi import Request
import requests

WORKFLOW_MAPPING = {
    "Opentelemetry Collector": "6jsi0iFnCb",
}

UP_STATUSES = ["skipped", "cancelled", "success"]

UPTIME_KUMA_URL = "http://uptime-kuma.uptime-kuma.svc.cluster.local:3001"

async def uptime(request: Request) -> None:
    gh_payload = await request.json()
    assert "workflow_run" in gh_payload
    workflow_run = gh_payload["workflow_run"]
    if workflow_run["status"] != "completed":
        return
    if workflow_run["name"] not in WORKFLOW_MAPPING:
        return  
    url = f"{UPTIME_KUMA_URL}/api/push/{WORKFLOW_MAPPING[workflow_run['name']]}"
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
