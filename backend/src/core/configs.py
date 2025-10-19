import os
from pathlib import Path
from typing import Optional, Literal

from pydantic_settings import BaseSettings
from pydantic import Field, FilePath


BASE_DIR = Path(__file__).resolve().parent.parent

env_name = os.getenv("ENV", "dev")
env_file = BASE_DIR / f".env.{env_name}"


class EnvBaseSettings(BaseSettings):
    class Config:
        env_file = env_file
        extra = "ignore"


class DirsSettings(EnvBaseSettings):
    data: Path = Path("./var/data").resolve()
    assets: Path = Path("./var/data").resolve() / "assets"
    store: Path = Path("./var/data").resolve() / "store"

    class Config: ## pyright: ignore
        env_prefix = "DIR_FOR_"

class QueueSettings(EnvBaseSettings):
    # AMQP URL для RabbitMQ (vhost по умолчанию — "/": это %2F в URL)
    amqp_url: str = "amqp://guest:guest@rabbit:5672/%2F"

    class Config:
        env_prefix = "QUEUE_"

class MlSettings(EnvBaseSettings):
    url: str = "http://ml-pipeline:8080"
    training_url: str = "http://ml-training:8080"
    callback_path_ocr: str = "/api/v1/pipeline/callback_ocr"

class Configs(EnvBaseSettings):
    dirs: DirsSettings = DirsSettings()
    allowed_exts: set = {".jpg", ".jpeg", ".png", ".pdf"}
    debug_mode: bool = True
    tag: Literal["dev", "prod", "etc"] = Field(default="dev")
    queue: QueueSettings = QueueSettings()
    ml_pipeline: MlSettings = MlSettings()
    backend_base_url: str = "http://backend:8000"

configs = Configs()

