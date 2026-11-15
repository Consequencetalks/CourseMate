import sys

from app.clients import ConfigError
from app.clients.embedding import embed_texts
from app.clients.llm import complete
from app.config import settings


def _missing_settings() -> list[str]:
    return [
        name
        for name, value in (
            ("DASHSCOPE_API_KEY", settings.dashscope_api_key),
            ("DASHSCOPE_BASE_URL", settings.dashscope_base_url),
            ("DEEPSEEK_API_KEY", settings.deepseek_api_key),
            ("DEEPSEEK_BASE_URL", settings.deepseek_base_url),
        )
        if not value
    ]


def _public_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for secret in (settings.dashscope_api_key, settings.deepseek_api_key):
        if secret:
            text = text.replace(secret, "***")
    return text


def main() -> int:
    missing = _missing_settings()
    if missing:
        print("Configuration error: Missing " + ", ".join(missing), file=sys.stderr)
        return 1
    try:
        vectors = embed_texts(["CourseMate"])
        print(f"Embedding dimension: {len(vectors[0])}")
        reply = complete(
            "Reply with one short sentence: CourseMate is ready.",
            max_tokens=64,
        )
        print(f"DeepSeek: {reply}")
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"API error: {_public_error(exc)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
