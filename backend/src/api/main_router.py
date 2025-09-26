from fastapi import APIRouter
from src.api.v1.router import v1_router

main_router = APIRouter(
    prefix='/api',
)
main_router.include_router(v1_router)

