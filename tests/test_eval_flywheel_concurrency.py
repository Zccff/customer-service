import asyncio
from scripts import eval_flywheel


async def test_generation_limits_concurrent_model_requests(monkeypatch):
    active = peak = 0
    async def fake_try(factory, label):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return None
    monkeypatch.setattr(eval_flywheel, "_try", fake_try)
    await asyncio.gather(*(eval_flywheel._gen_faith({"id":str(i)}, [], None, None) for i in range(14)))
    assert peak <= 5
    assert peak > 1
