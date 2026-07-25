import math

from google import genai
from google.genai import types

from .config import get_settings

_client: genai.Client | None = None


def _l2_normalize(vec: list[float]) -> list[float]:
    # gemini-embedding-001 does NOT normalize when output_dimensionality < 3072
    # (only gemini-embedding-2 does), so we unit-length the 768-dim vectors here.
    # Cosine ranking is scale-invariant either way, but unit vectors keep the
    # similarity floor interpretable and let cosine and dot product agree.
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0.0 else [x / norm for x in vec]


def _client_() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    settings = get_settings()
    resp = _client_().models.embed_content(
        model=settings.embedding_model,
        contents=texts,
        # gemini-embedding-001 defaults to 3072 dims; pin it to our schema's
        # VECTOR size so stored and queried vectors are always the same length.
        config=types.EmbedContentConfig(
            task_type=task_type, output_dimensionality=settings.embedding_dims
        ),
    )
    return [_l2_normalize(e.values) for e in resp.embeddings]


# Documents and questions are embedded with different task types on purpose.
# A chunk ("here is some information") and a question ("find information about
# X") are grammatically different shapes; telling the model which role each
# text plays lets it pull a question and its answer closer together in vector
# space than a single symmetric embedding would. It improves recall for free.
def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    return _embed([text], "RETRIEVAL_QUERY")[0]
