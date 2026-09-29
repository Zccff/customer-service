from scripts.ch10 import build_corpus


async def test_synthetic_source_never_reads_question_pool(monkeypatch):
    async def forbidden():
        raise AssertionError("private pool must not be read")
    monkeypatch.setattr(build_corpus.repository, "list_pool_texts", forbidden)
    assert await build_corpus.source_pool(synthetic_only=True) == []


async def test_default_source_preserves_existing_pool_behavior(monkeypatch):
    async def rows():
        return [{"question_id": 1, "text": "example"}]
    monkeypatch.setattr(build_corpus.repository, "list_pool_texts", rows)
    assert await build_corpus.source_pool(synthetic_only=False) == await rows()
