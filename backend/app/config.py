from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+psycopg://makaseta:makaseta@localhost:5432/makaseta"
    data_dir: Path = Path("./data")
    static_dir: Path = Path("./static")
    models_config: Path = Path("./config/models.yaml")
    library_root: Path = Path("./library")
    library_host_path: str = "./library"
    library_scan_interval: int = 30

    aws_dir: Path = Path.home() / ".aws"
    aws_profile: str = "default"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    deepseek_api_key: str = ""

    default_model_profile: str = "claude-main"
    max_concurrent_runs: int = 3
    monthly_budget_usd: float = 50.0
    max_steps_per_run: int = 40
    embedding_model_profile: str = "embed-main"


@lru_cache
def get_settings() -> Settings:
    return Settings()
