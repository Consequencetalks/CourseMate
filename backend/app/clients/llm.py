from collections.abc import Iterator

from openai import OpenAI

from app.clients import ConfigError
from app.config import settings


def _client(timeout: float = 60) -> OpenAI:
    missing = [
        name
        for name, value in (
            ("DEEPSEEK_API_KEY", settings.deepseek_api_key),
            ("DEEPSEEK_BASE_URL", settings.deepseek_base_url),
        )
        if not value
    ]
    if missing:
        raise ConfigError("Missing " + ", ".join(missing))
    return OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        timeout=timeout,
        max_retries=0,
    )


def complete(prompt: str, max_tokens: int = 1024, timeout: float = 60) -> str:
    if timeout <= 0:
        raise TimeoutError("The model request timed out.")
    response = _client(timeout).chat.completions.create(
        model=settings.deepseek_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError("DeepSeek returned an empty reply")
    return content.strip()


def stream_reply(messages: list[dict[str, str]], timeout: float) -> Iterator[str]:
    if timeout <= 0:
        raise TimeoutError("Chat timed out.")
    stream = _client(timeout).chat.completions.create(
        model=settings.deepseek_model,
        messages=messages,
        temperature=0,
        stream=True,
        extra_body={"thinking": {"type": "disabled"}},
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        text = chunk.choices[0].delta.content
        if text:
            yield text
