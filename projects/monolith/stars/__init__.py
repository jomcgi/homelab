"""Stars domain — best stargazing locations in Scotland for the next 72 hours.

Refresh-on-schedule pattern: a registered job hits MET Norway, scores each
seed location, and writes one ``stars.refresh_runs`` row per refresh. The read
endpoint serves the most recent successful row, so failed refreshes never
break the read path — the last good payload keeps serving until the next
success.
"""

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from stars.router import router

    app.include_router(router)


def on_startup_jobs(session) -> None:
    from shared.scheduler import register_job
    from stars.service import refresh_handler

    # MET Norway updates hourly; refresh slightly more often so we don't drift
    # if a refresh fails and the next one is delayed by ttl_secs.
    register_job(
        session,
        name="stars.refresh",
        interval_secs=3600,
        handler=refresh_handler,
        ttl_secs=900,
    )
