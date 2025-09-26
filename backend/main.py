from src.api.main_router import main_router

from fastapi import FastAPI

application = FastAPI()
application.include_router(main_router)


