import os

from dotenv import load_dotenv

# Load env BEFORE importing anything else from src.
# load_dotenv does not override vars that are already set (e.g. by Docker --env-file).
APP_ENV = os.getenv("APP_ENV", "dev")
load_dotenv(f".env.{APP_ENV}")

from fastapi import FastAPI  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from src.api_router import api_router  # noqa: E402
from src.core.exception_handlers import global_exception_handler  # noqa: E402
from src.core.exceptions import AppError  # noqa: E402
from src.core.health import router as health_router  # noqa: E402
from src.core.logging_config import configure_logging  # noqa: E402
from src.core.middleware import RequestContextMiddleware  # noqa: E402


def create_app() -> FastAPI:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))

    app = FastAPI(
        title="Financial Report Extractor API",
        version="0.1.0",
        description="Extract revenue, guidance and risks from earnings call transcripts.",
    )
    app.add_middleware(RequestContextMiddleware)

    # One handler function for every error type, so every error uses the ErrorResponse envelope.
    for exc_type in (AppError, RequestValidationError, StarletteHTTPException, Exception):
        app.add_exception_handler(exc_type, global_exception_handler)

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
