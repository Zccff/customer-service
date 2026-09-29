from app.config import settings
from app.core import rerank


async def test_dashscope_request_and_response(monkeypatch):
    monkeypatch.setattr(settings, "rerank_provider", "dashscope")
    monkeypatch.setattr(settings, "rerank_base_url", "https://workspace.example.com/")
    monkeypatch.setattr(settings, "rerank_model", "gte-rerank-v2")

    async def fake_post(url, json, headers, timeout):
        assert url == "https://workspace.example.com/api/v1/services/rerank/text-rerank/text-rerank"
        assert json == {"model": "gte-rerank-v2",
                        "input": {"query": "运费", "documents": ["a", "b"]},
                        "parameters": {"top_n": 1, "return_documents": False}}

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"output": {"results": [
                    {"index": 0, "relevance_score": 0.2},
                    {"index": 1, "relevance_score": 0.9},
                ]}}

        return Response()

    monkeypatch.setattr(rerank, "_post", fake_post)
    assert await rerank.rerank("运费", ["a", "b"], top_n=1) == [(1, 0.9)]
