import math

from google.genai import types

from .config import get_settings
from .llm import client


def _l2_normalize(vec: list[float]) -> list[float]:
    # gemini-embedding-001 does NOT normalize when output_dimensionality < 3072,
    # so we unit-length the 768-dim vectors here. Cosine ranking is scale-invariant
    # either way, but unit vectors keep the similarity floor interpretable and let
    # cosine and dot product agree.
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0.0 else [x / norm for x in vec]


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    settings = get_settings()
    resp = client().models.embed_content(
        model=settings.embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type, output_dimensionality=settings.embedding_dims
        ),
    )
    return [_l2_normalize(e.values) for e in resp.embeddings]


# Documents and queries are embedded with different task types on purpose: it
# pulls a question and its answer closer together in vector space (better recall).
def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    return _embed([text], "RETRIEVAL_QUERY")[0]
