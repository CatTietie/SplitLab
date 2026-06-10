from fastapi import APIRouter

from app.api.experiments import router as experiments_router
from app.api.layers import router as layers_router
from app.api.sdk import router as sdk_router
from app.api.stats import router as stats_router

api_router = APIRouter()
api_router.include_router(experiments_router)
api_router.include_router(layers_router)
api_router.include_router(sdk_router)
api_router.include_router(stats_router)
