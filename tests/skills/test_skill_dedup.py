from src.skills.dedup import capability_signature, duplicate_clusters, find_duplicate


def test_same_capability_signature_collides():
    a = {"id": "x", "category": "web-misconfiguration", "action_type": "checks", "tags": ["b", "a"]}
    b = {"id": "y", "category": "web-misconfiguration", "action_type": "checks", "tags": ["a", "b"]}
    assert capability_signature(a) == capability_signature(b)  # tag order doesn't matter


def test_find_duplicate_by_id_and_by_signature():
    existing = [{"id": "web.headers", "category": "web-misconfiguration", "action_type": "checks", "tags": ["http"]}]
    same_id = {"id": "web.headers", "category": "other", "action_type": "x", "tags": []}
    same_cap = {"id": "web.headers_v2", "category": "web-misconfiguration", "action_type": "checks", "tags": ["http"]}
    distinct = {"id": "web.sqli", "category": "sql-injection", "action_type": "active", "tags": ["db"]}

    assert find_duplicate(same_id, existing)["id"] == "web.headers"
    assert find_duplicate(same_cap, existing)["id"] == "web.headers"
    assert find_duplicate(distinct, existing) is None


def test_duplicate_clusters_report():
    cards = [
        {"id": "a", "category": "c", "action_type": "t", "tags": ["x"]},
        {"id": "b", "category": "c", "action_type": "t", "tags": ["x"]},
        {"id": "c", "category": "d", "action_type": "t", "tags": ["y"]},
    ]
    clusters = duplicate_clusters(cards)
    assert any(set(group) == {"a", "b"} for group in clusters)
