from pydantic_settings import BaseSettings


class GithubWebhookHandlerSettings(BaseSettings):
    """Settings for the Uptime service"""

    uptime_port: int = 9090
    workflow_mapping: dict[str, str] = {
        "Deploy Homelab": "6jsi0iFnCb",
    }
    uptime_kuma_url: str = "http://localhost:30333"
    otel_github_receiver_url: str = "http://localhost:30319/events"
    up_statuses: list[str] = ["skipped", "cancelled", "success"]
    
HANDLER_SETTINGS = GithubWebhookHandlerSettings()