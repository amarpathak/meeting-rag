from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://mi:mi@db:5432/meeting_intel"

    gemini_api_key: str = ""

    embedding_model: str = "gemini-embedding-001"
    embedding_dims: int = 768
    # Pinned versions, not the `-latest` alias. The alias resolved to a different
    # model mid-build, and free-tier quota is per project *per model*: a silent
    # shift moves you to a different daily bucket and makes eval runs taken
    # either side of it incomparable.
    #
    # Ordered fallback chain. Free tier allows 20 generate calls per day per
    # model, so one model alone is a hard stop after 20 requests; falling through
    # to the next turns that into degraded service instead of an outage. Ordered
    # best-first — later entries are cheaper and weaker, which is the right
    # trade when the alternative is no answer at all.
    answer_models: str = (
        "gemini-2.5-flash,gemini-2.0-flash,gemini-3.5-flash,"
        "gemini-2.5-flash-lite,gemini-2.0-flash-lite"
    )

    @property
    def answer_model_chain(self) -> list[str]:
        return [m.strip() for m in self.answer_models.split(",") if m.strip()]

    @property
    def answer_model(self) -> str:
        """The preferred model — what we try first and report in /health."""
        return self.answer_model_chain[0]

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
