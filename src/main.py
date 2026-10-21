import os

from dotenv import load_dotenv

# Load env BEFORE importing anything else from src.
# load_dotenv does not override vars that are already set (e.g. by Docker --env-file).
APP_ENV = os.getenv("APP_ENV", "dev")
load_dotenv(f".env.{APP_ENV}")

import logging  # noqa: E402
import sys  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from src.api_router import api_router  # noqa: E402
from src.core.exception_handlers import global_exception_handler  # noqa: E402
from src.core.exceptions import AppError  # noqa: E402
from src.core.health import router as health_router  # noqa: E402
from src.core.logging_config import configure_logging  # noqa: E402
from src.core.middleware import RequestContextMiddleware  # noqa: E402

logger = logging.getLogger(__name__)


def _cli_option(name: str, default: str) -> str:
    """Value of a uvicorn CLI option (e.g. --port 8001 or --port=8001), for display only."""
    for index, arg in enumerate(sys.argv):
        if arg == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        if arg.startswith(f"{name}="):
            return arg.split("=", 1)[1]
    return default


def _base_url() -> str:
    host = _cli_option("--host", "127.0.0.1")
    if host in ("0.0.0.0", "::"):  # noqa: S104 - display only: bound to all interfaces
        host = "localhost"
    return f"http://{host}:{_cli_option('--port', '8000')}"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Application started",
        extra={"environment": os.getenv("APP_ENV", "dev"), "docs_url": f"{_base_url()}/docs"},
    )
    yield


def create_app() -> FastAPI:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    environment = os.getenv("APP_ENV", "dev")

    app = FastAPI(
        title=f"Financial Report Extractor API [{environment}]",
        version="0.1.0",
        description=(
            "Extract revenue, guidance and risks from earnings call transcripts.\n\n"
            f"**Environment:** `{environment}`"
        ),
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)

    # One handler function for every error type, so every error uses the ErrorResponse envelope.
    for exc_type in (AppError, RequestValidationError, StarletteHTTPException, Exception):
        app.add_exception_handler(exc_type, global_exception_handler)

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
