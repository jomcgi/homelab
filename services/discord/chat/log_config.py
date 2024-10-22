import logging
import structlog


def configure_structlog():
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(),
            structlog.processors.CallsiteParameterAdder(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.add_log_level,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    )
