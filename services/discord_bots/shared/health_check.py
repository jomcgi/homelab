import threading
from collections.abc import Iterable
from typing import NamedTuple

import uvicorn
from fastapi import FastAPI, Response
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.discord_bots.shared.health_protocol import Healthable


class HealthServiceConfig(BaseSettings):
    port: int = 8080
    route: str = "/health"

    model_config = SettingsConfigDict(env_prefix="HEALTH_SERVICE_")


class HealthResponse(BaseModel):
    OK: bool = True
    utils_health: dict[str, bool] | None = None


def http_service(
    config: HealthServiceConfig, health_utils: Iterable[Healthable] | None = None
):
    app = FastAPI()

    @app.get(config.route, status_code=200, response_model=HealthResponse)
    async def get_health(response: Response):  # type: ignore
        healthy_responses: dict[str, bool] = {}
        if health_utils:
            for health_util in health_utils:
                health_status = health_util.is_healthy()
                healthy_responses[health_util.__class__.__name__] = health_status

            if not all(healthy_responses.values()):
                response.status_code = 503
                return HealthResponse(OK=False, utils_health=healthy_responses)

            return HealthResponse(utils_health=healthy_responses)

        return HealthResponse()

    return app


class HealthServer(NamedTuple):
    server: uvicorn.Server
    thread: threading.Thread


def run_http_service(
    health_utils: Iterable[Healthable] | None = None,
) -> HealthServer:
    """Runs the http service using uvicorn. Passing a list of Healthable
    classes you can control the lifetime of the service based on the
    availability of your dependencies.

    Args:
        health_utils (Iterable[Healthable] | None, optional): Utilities that implement the is_healthy -> bool.
        Defaults to None.

    Returns:
        HealthServer: Thread & Server objects that can be used to stop the service.
    """
    config = HealthServiceConfig()
    app = http_service(config, health_utils)

    uvicorn_config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=config.port,
        access_log=False,
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)

    server_thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    server_thread.start()

    return HealthServer(uvicorn_server, server_thread)


def stop_server(health_server: HealthServer):
    """Stops the server."""
    health_server.server.should_exit = True
    health_server.thread.join()
