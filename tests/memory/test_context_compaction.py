from src.memory.context import EPHEMERAL, SALIENT, WorkingMemory


def test_compaction_drops_ephemeral_keeps_salient():
    wm = WorkingMemory(token_budget=40, recent_keep=10)
    wm.pin("authorization_id: lab")
    wm.add("salient decision one", salience=SALIENT)
    wm.add("BIG EPHEMERAL JUNK " * 10, salience=EPHEMERAL)
    wm.add("salient decision two", salience=SALIENT)
    wm.add("BIG EPHEMERAL JUNK " * 10, salience=EPHEMERAL)
    wm.compact()

    assert all(it.salience != EPHEMERAL for it in wm.items)
    contents = [it.content for it in wm.items]
    assert "salient decision one" in contents
    assert "salient decision two" in contents


def test_ephemeral_auto_clears_without_budget_pressure():
    # Huge budget => compaction never fires. Ephemeral must still self-clear.
    wm = WorkingMemory(token_budget=10_000, recent_keep=10, ephemeral_ttl_turns=1)
    wm.pin("authorization_id: lab")
    wm.add("RAW TOOL DUMP", salience=EPHEMERAL)
    assert any(it.salience == EPHEMERAL for it in wm.items)  # visible this turn
    wm.add("a salient decision", salience=SALIENT)
    wm.add("another decision", salience=SALIENT)
    assert all(it.salience != EPHEMERAL for it in wm.items)  # gone despite room
    contents = [it.content for it in wm.items]
    assert "a salient decision" in contents and "another decision" in contents


def test_compaction_keeps_recent_and_summarizes_old():
    wm = WorkingMemory(token_budget=220, recent_keep=3)
    wm.pin("authorization_id: x")
    for i in range(20):
        wm.add(f"salient step number {i} with some descriptive text", salience=SALIENT)

    assert wm.total_tokens() <= wm.token_budget       # budget respected
    assert wm.rolling_summary                          # older items folded in
    assert len(wm.items) < 10                          # bounded recent window
    assert wm.pinned == ["authorization_id: x"]        # pinned fact survived
