from openai import AsyncOpenAI

from app.config import settings

_CLIENT: AsyncOpenAI | None = None


def _client() -> AsyncOpenAI:
    """直连嵌入上游(硅基流动的 bge-m3,OpenAI 兼容)。
    进程内单例:复用同一 httpx 连接池,避免每次 embed 新建客户端累积连接/fd。"""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = AsyncOpenAI(base_url=settings.embed_base_url, api_key=settings.embed_api_key)
    return _CLIENT


async def embed_texts(texts: list[str]) -> list[list[float]]:
    # The configured DashScope embedding endpoint accepts at most 10 texts.
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 10):
        batch = texts[start:start + 10]
        resp = await _client().embeddings.create(model=settings.embed_model, input=batch)
        if len(resp.data) != len(batch):
            raise ValueError("Embedding response count does not match input count")
        vectors.extend(d.embedding for d in resp.data)
    return vectors


async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text]))[0]
