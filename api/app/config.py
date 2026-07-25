from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://mi:mi@db:5432/meeting_intel"

    gemini_api_key: str = ""

    embedding_model: str = "gemini-embedding-001"
    embedding_dims: int = 768
    # 'latest' alias so the reviewer's run doesn't break when a pinned flash
    # version is retired (gemini-2.5-flash was already blocked for new keys).
    answer_model: str = "gemini-flash-latest"

    # Below this cosine similarity we refuse rather than let the model improvise
    # from weak context. 0.60 tuned against evals/ for gemini-embedding-001:
    # it clears every real answer (weakest 0.66) and refuses obvious off-topic
    # questions. Topic-adjacent misses that clear it are caught by the prompt.
    similarity_floor: float = 0.60
    top_k: int = 5

    # 200 gives ~5 topically-coherent chunks on a single ~9-min transcript;
    # 400 collapsed the whole meeting into 2 diluted chunks. Revisit against evals.
    chunk_target_tokens: int = 200
    chunk_overlap_turns: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
