from src.skills.library import SkillLibrary
from src.skills.research import propose_skill_card


def test_reuses_existing_skill_instead_of_drafting(tmp_path):
    lib = SkillLibrary.load()
    # Same capability signature as the shipped exposed-sensitive-paths skill.
    result = propose_skill_card(
        capability="Find exposed files",
        category="broken-access-control",
        action_type="reconnaissance",
        risk_level=2,
        tags=["access-control", "information-disclosure", "recon", "files"],
        library=lib,
        drafts_dir=str(tmp_path),
    )
    assert result["status"] == "reuse"
    assert result["existing"] == "web.exposed_sensitive_paths"
    assert list(tmp_path.iterdir()) == []  # nothing drafted


def test_drafts_new_capability_as_non_runnable_pending_review(tmp_path):
    lib = SkillLibrary.load()
    result = propose_skill_card(
        capability="Detect SQL injection in login",
        category="sql-injection",
        action_type="active-validation",
        risk_level=3,
        tags=["sqli", "auth"],
        library=lib,
        drafts_dir=str(tmp_path),
    )
    assert result["status"] == "draft"
    card = result["card"]
    assert card["status"] == "pending_review"
    assert card["implementation"] is None      # cannot run
    assert (tmp_path / f"{card['id']}.json").exists()


def test_library_loader_refuses_drafts():
    # Drafts live under skills/_drafts/ which the loader skips entirely.
    lib = SkillLibrary.load()
    assert all(not c["id"].startswith("draft.") for c in lib.all())
