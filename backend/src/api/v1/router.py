from fastapi import APIRouter
from src.api.v1.endpoints.files import files_router
from src.api.v1.endpoints.groups import groups_router
from src.api.v1.endpoints.pipeline_callback import router as pipeline_router

v1_router = APIRouter(
    prefix='/v1',
)

v1_router.include_router(files_router)
v1_router.include_router(groups_router)
v1_router.include_router(pipeline_router)
