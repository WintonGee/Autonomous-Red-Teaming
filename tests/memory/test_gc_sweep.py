from datetime import datetime, timedelta, timezone

from src.memory.gc import run_gc
from src.memory.store import MemoryStore


def test_expired_ephemeral_evicted_salient_kept():
    with MemoryStore(":memory:") as store:
        old_ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        store.conn.execute(
            "INSERT INTO episodic_events "
            "(engagement_id, authorization_id, ts, event_type, salience, content, content_hash, token_cost) "
            "VALUES (?,?,?,?,?,?,?,0)",
            ("e1", "a1", old_ts, "tool_output", "ephemeral", "junk", "h1"),
        )
        store.conn.execute(
            "INSERT INTO episodic_events "
            "(engagement_id, authorization_id, ts, event_type, salience, content, content_hash, token_cost) "
            "VALUES (?,?,?,?,?,?,?,0)",
            ("e1", "a1", old_ts, "decision", "salient", "important", "h2"),
        )
        store.conn.commit()

        report = run_gc(store, ephemeral_ttl=timedelta(hours=24))
        assert report.expired_ephemeral == 1

        remaining = store.get_events("e1")
        assert len(remaining) == 1
        assert remaining[0]["salience"] == "salient"


def test_exact_duplicates_collapsed():
    with MemoryStore(":memory:") as store:
        for _ in range(3):
            store.add_event(
                engagement_id="e1",
                authorization_id="a1",
                event_type="observation",
                content="same observation",
                salience="salient",
            )
        report = run_gc(store)
        assert report.duplicates_collapsed == 2
        assert len(store.get_events("e1")) == 1
