from src.skills.library import SkillLibrary


def test_composed_card_merges_code_and_knowledge():
    lib = SkillLibrary.load()
    card = lib.get("web.missing_security_headers")
    # mechanical fields come from the code skill...
    assert card["risk_level"] == 1
    assert card["action_type"] == "web-misconfiguration-checks"
    # ...knowledge fields come from the card on disk
    assert "purpose" in card and card["purpose"]
    assert card["references"] and "url" in card["references"][0]
    assert "verified_at" in card["references"][0]


def test_every_shipped_skill_has_a_knowledge_card():
    lib = SkillLibrary.load()
    assert lib.missing_knowledge() == []


def test_gap_detection():
    lib = SkillLibrary.load()
    # an existing capability is not a gap; an unknown one is
    assert lib.gaps(["web-misconfiguration"]) == []
    assert "sql-injection" in lib.gaps(["sql-injection"])


def test_categories_listed():
    lib = SkillLibrary.load()
    cats = lib.categories()
    assert "web-misconfiguration" in cats
    assert "broken-access-control" in cats


def test_find_duplicate_of_catches_draft_colliding_with_active():
    lib = SkillLibrary.load()
    # A would-be draft with the same capability signature as a live skill.
    colliding = {
        "id": "draft.headers",
        "category": "web-misconfiguration",
        "action_type": "web-misconfiguration-checks",
        "tags": ["headers", "http", "browser-security", "misconfiguration"],
    }
    assert lib.find_duplicate_of(colliding) == "web.missing_security_headers"
    # A genuinely new capability collides with nothing.
    assert lib.find_duplicate_of({"id": "draft.sqli", "category": "sql-injection",
                                  "action_type": "active", "tags": ["sqli"]}) is None


def test_load_raises_on_missing_dir():
    import pytest
    with pytest.raises(FileNotFoundError):
        SkillLibrary.load(root="/no/such/skills/dir")
