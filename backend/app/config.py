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
    skills_root: Path = Path("./skills")
    work_root: Path = Path("./data/work")
    sandbox_url: str = "http://localhost:8000"
    sandbox_timeout: int = 180
    github_token: str = ""
    makaseta_password: str = ""
    # Providers allowed to read confidential 資料室 (comma separated), e.g. models running in your own cloud account.
    confidential_providers: str = "bedrock"

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
    # How many tasks one agent works on at once when the manager starts backlog tasks.
    max_active_tasks_per_agent: int = 1
    # After each review the assignee reflects and keeps what it learned in its 業務メモ.
    agent_reflection: bool = True
    # USD per web search (Anthropic web search is billed per search on top of tokens).
    web_search_price_usd: float = 0.01
    embedding_model_profile: str = "embed-main"


@lru_cache
def get_settings() -> Settings:
    return Settings()
