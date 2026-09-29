"""Check configured upstreams without displaying credentials or response bodies."""
import asyncio

from app.core import embeddings, rerank
from app.core.llm import get_chat_model


async def main():
    async def check(name, call):
        try:
            result = await asyncio.wait_for(call(), timeout=90)
            print(name, "OK", result, flush=True)
        except Exception as exc:
            print(name, "FAILED", type(exc).__name__,
                  "status=", getattr(exc, "status_code", getattr(getattr(exc, "response", None), "status_code", None)), flush=True)

    async def chat():
        result = await get_chat_model().ainvoke("请只回复：连接成功")
        return bool(result.content)

    async def embed():
        return {"dimensions": len(await embeddings.embed_query("退货运费"))}

    async def rank():
        return await rerank.rerank("退货运费", ["质量问题退货运费由商家承担", "会员生日有礼物"], top_n=1)

    await asyncio.gather(check("CHAT", chat), check("EMBED", embed), check("RERANK", rank))


if __name__ == "__main__":
    asyncio.run(main())
