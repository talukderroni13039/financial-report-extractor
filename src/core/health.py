import os

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.core.schemas import ApiResponse, ResponseMeta

router = APIRouter(tags=["health"])


class HealthResult(BaseModel):
    status: str
    environment: str


@router.get("/health", response_model=ApiResponse[HealthResult])
async def health(request: Request) -> ApiResponse[HealthResult]:
    return ApiResponse(
        data=HealthResult(status="ok", environment=os.getenv("APP_ENV", "dev")),
        meta=ResponseMeta.from_request(request),
    )
