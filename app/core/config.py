from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    timezone: str = "Africa/Cairo"

    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/schoolrag"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: str = "/data/storage"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24
    cors_origins: str = "*"

    # ---- provider keys (a role can override with its own *_API_KEY) ----
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # ---- every role picks its own provider + model: swap any of them from .env ----
    # LLM: answers      (anthropic | openai  -- "openai" works with any OpenAI-compatible server via *_BASE_URL)
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-5-5"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    # Condense: rewrites follow-up questions. Unset provider => reuse the LLM provider/model.
    condense_provider: str | None = None
    condense_model: str = "claude-haiku-5-5"
    condense_api_key: str | None = None
    condense_base_url: str | None = None
    # VLM: reads page images (anthropic | openai)
    vlm_provider: str = "anthropic"
    vlm_model: str = "claude-sonnet-5-5"
    vlm_api_key: str | None = None
    vlm_base_url: str | None = None
    # Embeddings (bge_m3 = local dense+sparse | openai = any OpenAI-compatible embeddings API, dense only)
    embed_provider: str = "bge_m3"
    embed_model: str = "BAAI/bge-m3"
    embed_dim: int = 1024
    embed_api_key: str | None = None
    embed_base_url: str | None = None
    # Reranker (bge | none)
    rerank_provider: str = "bge"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_min_score: float = 0.05
    # Vector store (qdrant)
    vectorstore_provider: str = "qdrant"
    qdrant_url: str = "http://localhost:6333"
    collection_prefix: str = "textbooks"
    # OCR fallback (tesseract | none)
    ocr_provider: str = "tesseract"
    ocr_languages: str = "ara+eng+fra"

    # ---- extraction ----
    extraction_mode: str = "auto"  # auto | vlm | native
    vlm_concurrency: int = 4
    render_long_edge: int = 1900
    vlm_max_tokens: int = 8000
    max_upload_mb: int = 300

    # ---- chunking / retrieval ----
    chunk_target_chars: int = 1500
    chunk_max_chars: int = 2400
    top_k_candidates: int = 30
    top_k_final: int = 6
    max_context_chars: int = 14000
    history_messages: int = 8
    answer_max_tokens: int = 1800

    # ---- limits ----
    default_daily_requests: int = 60
    default_daily_tokens: int = 150_000
    rate_limit_per_minute: int = 12
    login_attempts_per_5min: int = 10
    max_question_chars: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
