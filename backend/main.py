from src.api.main_router import main_router

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

origins = ["*"]

application = FastAPI()
application.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    )


application.include_router(main_router)

@application.get("/__routes__")
def __routes__():
    return [{"path": r.path, "methods": list(getattr(r, "methods", []))} for r in application.router.routes]


