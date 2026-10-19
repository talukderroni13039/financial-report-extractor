import os

from dotenv import load_dotenv

# Load env BEFORE importing anything else from src.
# load_dotenv does not override vars that are already set (e.g. by Docker --env-file).
APP_ENV = os.getenv("APP_ENV", "dev")
load_dotenv(f".env.{APP_ENV}")

from fastapi import FastAPI  # noqa: E402

from src.core.health import router as health_router  # noqa: E402


def create_app() -> FastAPI:
    app = FastAPI(
        title="Financial Report Extractor API",
        version="0.1.0",
        description="Extract revenue, guidance and risks from earnings call transcripts.",
    )
    app.include_router(health_router)
    return app


app = create_app()
