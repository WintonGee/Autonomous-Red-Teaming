import pytest

from src.memory.store import MemoryStore


def test_retrieval_scoped_to_authorization():
    with MemoryStore(":memory:") as store:
        # A global skill (no authorization) and two target-specific findings.
        store.add_semantic_item(kind="skill", title="missing security headers", external_id="web.headers")
        store.add_semantic_item(kind="finding", title="finding A", authorization_id="auth-A", content={"x": 1})
        store.add_semantic_item(kind="finding", title="finding B", authorization_id="auth-B", content={"x": 2})

        titles = {r["title"] for r in store.retrieve_semantic(authorization_id="auth-A")}
        assert "finding A" in titles                    # own finding visible
        assert "missing security headers" in titles     # global skill visible
        assert "finding B" not in titles                # other target's finding isolated


def test_global_skill_excluded_when_include_global_false():
    with MemoryStore(":memory:") as store:
        store.add_semantic_item(kind="skill", title="generic skill", external_id="web.headers")
        rows = store.retrieve_semantic(authorization_id="auth-A", include_global=False)
        assert rows == []


def test_finding_requires_authorization_id():
    with MemoryStore(":memory:") as store:
        with pytest.raises(ValueError):
            store.add_semantic_item(kind="finding", title="x", content={})
