from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """项目统一配置，优先读取项目根目录 .env。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Local Knowledge Base"
    app_version: str = "1.0.0"
    debug: bool = False

    deepseek_api_key: str
    deepseek_model: str = "deepseek-chat"
    deepseek_api_url: str = "https://api.deepseek.com/chat/completions"
    deepseek_timeout: int = 60

    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"
    embedding_local_files_only: bool = True

    data_dir: Path = PROJECT_ROOT / "data"
    documents_dir: Path = PROJECT_ROOT / "data" / "documents"
    database_path: Path = PROJECT_ROOT / "data" / "local_kb.db"
    chroma_path: Path = PROJECT_ROOT / "data" / "chroma"
    chroma_collection_name: str = "knowledge_base"

    min_similarity: float = 0.60
    top_k: int = 3
    chunk_size: int = 200
    chunk_overlap: int = 40
    agent_max_tool_calls: int = 5
    workflow_max_supplement_attempts: int = 3
    workflow_max_summary_retries: int = 1
    workflow_max_steps: int = 20
    short_term_memory_max_messages: int = 20

    log_level: str = Field(default="INFO", validation_alias="APP_LOG_LEVEL")
    log_format: str = Field(
        default="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        validation_alias="APP_LOG_FORMAT",
    )


settings = Settings()
