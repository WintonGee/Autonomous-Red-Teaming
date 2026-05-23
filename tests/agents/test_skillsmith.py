from src.agents.recon import SiteProfile
from src.agents.skillsmith import (
    RuleBasedSkillGenerator,
    generate_skills,
    load_generated_specs,
    save_generated_spec,
)
from src.skills.spec import SpecSkill
from src.tools.http_client import HttpResponse

ALLOWED = {"reconnaissance", "web-misconfiguration-checks", "safe-validation"}


def _profile_with_gap():
    return SiteProfile(
        target_url="http://localhost:3001", summary="x",
        gaps=[{"category": "crawler-policy-disclosure", "hint": "robots", "path": "/robots.txt"}],
    )


def _http(resp):
    class _H:
        def get(self, url):
            return resp
    return _H()


def test_generator_produces_a_runnable_new_skill():
    specs = generate_skills(RuleBasedSkillGenerator(), _profile_with_gap(), allowed_testing=ALLOWED)
    assert len(specs) == 1
    # The generated skill is immediately executable and fires on a real robots.txt.
    resp = HttpResponse(200, {"content-type": "text/plain"}, "u", body="User-agent: *\nDisallow: /ftp")
    obs = SpecSkill(specs[0]).run(_http(resp), "http://localhost:3001")
    assert obs["finding"]["category"] == "crawler-policy-disclosure"
    assert obs["finding"]["confidence"] == "suspected"


def test_generator_dedupes_against_already_generated():
    gen = RuleBasedSkillGenerator()
    first = generate_skills(gen, _profile_with_gap(), allowed_testing=ALLOWED)
    again = generate_skills(gen, _profile_with_gap(), allowed_testing=ALLOWED, existing_specs=first)
    assert again == []


def test_generator_reuses_before_creating_when_trusted_skill_covers_it():
    specs = generate_skills(RuleBasedSkillGenerator(), _profile_with_gap(), allowed_testing=ALLOWED)
    card = {"id": "web.robots", "category": specs[0].category,
            "action_type": specs[0].action_type, "tags": specs[0].tags}
    out = generate_skills(RuleBasedSkillGenerator(), _profile_with_gap(),
                          allowed_testing=ALLOWED, existing_cards=[card])
    assert out == []


def test_save_and_load_round_trip(tmp_path):
    specs = generate_skills(RuleBasedSkillGenerator(), _profile_with_gap(), allowed_testing=ALLOWED)
    save_generated_spec(specs[0], directory=tmp_path)
    loaded = load_generated_specs(directory=tmp_path)
    assert [s.id for s in loaded] == [specs[0].id]
