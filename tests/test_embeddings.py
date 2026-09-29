from app.core import embeddings


class _FakeEmb:
    def __init__(self, vec):
        self.embedding = vec


class _FakeResp:
    def __init__(self, vecs):
        self.data = [_FakeEmb(v) for v in vecs]


class _FakeEmbeddings:
    def __init__(self):
        self.calls = []

    async def create(self, model, input):
        self.calls.append((model, list(input)))
        return _FakeResp([[float(i), 0.0, 1.0] for i, _ in enumerate(input)])


class _FakeClient:
    def __init__(self):
        self.embeddings = _FakeEmbeddings()


async def test_embed_texts_passes_model_and_input(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "embed_model", "test-embedding-model")
    fake = _FakeClient()
    monkeypatch.setattr(embeddings, "_client", lambda: fake)
    out = await embeddings.embed_texts(["a", "b"])
    assert out == [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]]
    assert fake.embeddings.calls == [("test-embedding-model", ["a", "b"])]


async def test_embed_query_returns_single_vector(monkeypatch):
    monkeypatch.setattr(embeddings, "_client", lambda: _FakeClient())
    v = await embeddings.embed_query("邮费")
    assert v == [0.0, 0.0, 1.0]


async def test_embed_large_input_respects_provider_limit_and_order(monkeypatch):
    fake = _FakeClient()
    async def create(model, input):
        assert len(input) <= 10
        fake.embeddings.calls.append(list(input))
        return _FakeResp([[float(text)] for text in input])
    fake.embeddings.create = create
    monkeypatch.setattr(embeddings, "_client", lambda: fake)
    assert await embeddings.embed_texts([str(i) for i in range(23)]) == [[float(i)] for i in range(23)]
    assert list(map(len, fake.embeddings.calls)) == [10, 10, 3]


async def test_embed_empty_input_does_not_call_provider(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(embeddings, "_client", lambda: fake)
    assert await embeddings.embed_texts([]) == []
    assert fake.embeddings.calls == []


async def test_embed_incomplete_response_is_rejected(monkeypatch):
    import pytest
    fake = _FakeClient()
    async def create(model, input):
        return _FakeResp([[1.0]])
    fake.embeddings.create = create
    monkeypatch.setattr(embeddings, "_client", lambda: fake)
    with pytest.raises(ValueError, match="count"):
        await embeddings.embed_texts(["a", "b"])
