from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://mi:mi@db:5432/meeting_intel"

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536
    answer_model: str = "claude-sonnet-4-5"

    # Below this cosine similarity we refuse to answer rather than let the
    # model improvise from weak context. Tuned by hand against evals/.
    similarity_floor: float = 0.35
    top_k: int = 5

    # 200 gives ~5 topically-coherent chunks on a single ~9-min transcript;
    # 400 collapsed the whole meeting into 2 diluted chunks. Revisit against evals.
    chunk_target_tokens: int = 200
    chunk_overlap_turns: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
