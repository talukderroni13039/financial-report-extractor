from fastapi import APIRouter

from src.domains.earnings_reports.routers.api_endpoints import router as earnings_reports_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(earnings_reports_router)
