import pytest

from src.memory.context import SALIENT, PinnedContextMissing, WorkingMemory


def test_render_without_pins_fails_closed():
    wm = WorkingMemory(token_budget=100)
    wm.add("some observation", salience=SALIENT)
    with pytest.raises(PinnedContextMissing):
        wm.render()


def test_pin_after_add_is_rejected():
    # Pinning mid-engagement would mutate the cacheable preamble — disallowed.
    wm = WorkingMemory(token_budget=100)
    wm.add("an observation", salience=SALIENT)
    with pytest.raises(RuntimeError):
        wm.pin("authorization_id: lab")


def test_pins_survive_compaction_and_render():
    wm = WorkingMemory(token_budget=80, recent_keep=2)
    wm.pin("authorization_id: local-juice-shop")
    wm.pin("scope: http://localhost:3000")
    for i in range(30):
        wm.add(f"noisy step {i} " * 3, salience=SALIENT)

    blocks = wm.render()
    pinned_block = next(b for b in blocks if b["region"] == "pinned")
    assert "local-juice-shop" in pinned_block["text"]
    assert "http://localhost:3000" in pinned_block["text"]
    assert pinned_block["cacheable"] is True
