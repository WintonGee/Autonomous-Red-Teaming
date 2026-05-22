from src.memory.dedup import ExactDeduplicator, content_hash, normalize
from src.memory.store import MemoryStore


def test_normalization_collapses_whitespace_and_case():
    assert content_hash("Hello   World") == content_hash("hello world")
    assert normalize("  A\tB\nC ") == "a b c"


def test_second_identical_content_is_duplicate():
    with MemoryStore(":memory:") as store:
        dd = ExactDeduplicator(store)
        first = dd.check_and_register("GET /admin 200", scope="episodic")
        second = dd.check_and_register("get   /admin    200", scope="episodic")
        assert first.is_duplicate is False
        assert second.is_duplicate is True
        assert second.hit_count == 2


def test_same_content_distinct_scopes_not_duplicate():
    with MemoryStore(":memory:") as store:
        dd = ExactDeduplicator(store)
        assert dd.check_and_register("x", scope="episodic").is_duplicate is False
        assert dd.check_and_register("x", scope="semantic").is_duplicate is False


def test_add_event_deduplicate_skips_duplicate():
    with MemoryStore(":memory:") as store:
        id1 = store.add_event(engagement_id="e1", authorization_id="a1",
                              event_type="tool_output", content="GET / 200", deduplicate=True)
        id2 = store.add_event(engagement_id="e1", authorization_id="a1",
                              event_type="tool_output", content="get   /   200", deduplicate=True)
        assert id1 == id2                       # duplicate returns the original id
        assert len(store.get_events("e1")) == 1  # no second row written


def test_add_event_dedup_is_per_engagement():
    with MemoryStore(":memory:") as store:
        store.add_event(engagement_id="e1", authorization_id="a1",
                        event_type="note", content="same", deduplicate=True)
        store.add_event(engagement_id="e2", authorization_id="a1",
                        event_type="note", content="same", deduplicate=True)
        # Identical content across engagements is NOT cross-collapsed.
        assert len(store.get_events("e1")) == 1
        assert len(store.get_events("e2")) == 1
