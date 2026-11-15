from openai import OpenAI

from app.clients import ConfigError
from app.config import settings


def _client() -> OpenAI:
    missing = [
        name
        for name, value in (
            ("DASHSCOPE_API_KEY", settings.dashscope_api_key),
            ("DASHSCOPE_BASE_URL", settings.dashscope_base_url),
        )
        if not value
    ]
    if missing:
        raise ConfigError("Missing " + ", ".join(missing))
    return OpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        timeout=60,
        max_retries=0,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    response = _client().embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    vectors = [item.embedding for item in response.data]
    expected = settings.embedding_dimensions
    if len(vectors) != len(texts) or any(len(vector) != expected for vector in vectors):
        raise RuntimeError(f"Expected {len(texts)} embeddings of dimension {expected}")
    return vectors
