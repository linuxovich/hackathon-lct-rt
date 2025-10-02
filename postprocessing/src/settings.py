from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class EnvBaseSettings(BaseSettings):
    class Config:
        env_file = BASE_DIR / ".env"
        extra = "ignore"


class LLMSettings(EnvBaseSettings):
    model: str = Field(default="infidelis/GigaChat-20B-A3B-instruct-v1.5:q4_K_M")
    base_url: str = Field(default="http://localhost:8888")

    class Config:
        env_prefix = "LLM_"


class Settings(EnvBaseSettings):
    llm: LLMSettings = Field(default=LLMSettings())


settings = Settings()