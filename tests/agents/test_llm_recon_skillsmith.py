"""LLM recon + skill generation, exercised with an injected transport (no API key).

Proves the non-deterministic path end-to-end: a Claude tool-use response becomes a
SiteProfile, and a Claude skill proposal becomes a validated, runnable SkillSpec.
"""
from src.agents.llm.client import ClaudeClient
from src.agents.llm.reasoners import ClaudeRecon, ClaudeSkillGenerator
from src.agents.recon import RuleBasedRecon, SiteProfile
from src.agents.skillsmith import RuleBasedSkillGenerator, generate_skills
from src.skills.spec import SpecSkill
from src.tools.http_client import HttpResponse

ALLOWED = {"reconnaissance", "web-misconfiguration-checks", "safe-validation"}


class _Usage:
    input_tokens = 1
    output_tokens = 1


def _client(name, inp):
    class _B:
        type = "tool_use"
        def __init__(self):
            self.name = name
            self.input = inp

    class _R:
        def __init__(self):
            self.content = [_B()]
            self.usage = _Usage()

    return ClaudeClient(create_message=lambda **kw: _R())


def _err_client():
    def boom(**kw):
        raise RuntimeError("boom")
    return ClaudeClient(create_message=boom)


def _obs():
    return [{"path": "/", "status": 200, "headers": {"server": "x"}, "body_head": "OWASP Juice Shop"}]


# ---- recon ----
def test_claude_recon_builds_profile():
    c = _client("describe_site", {
        "summary": "Angular SPA", "tech": ["Angular", "Express"],
        "notable": [{"path": "/", "note": "wildcard CORS"}],
        "gaps": [{"category": "open-redirect", "hint": "redirect param", "path": "/redirect"}],
    })
    profile = ClaudeRecon(c, RuleBasedRecon()).understand("http://localhost:3001", _obs())
    assert "Angular" in profile.tech
    assert any(g["category"] == "open-redirect" for g in profile.gaps)
    assert profile.observations[0]["notable"] == ["wildcard CORS"]


def test_claude_recon_falls_back_on_error():
    profile = ClaudeRecon(_err_client(), RuleBasedRecon()).understand("http://localhost:3001", _obs())
    assert isinstance(profile, SiteProfile)  # deterministic fallback produced a profile


# ---- skill generation ----
def test_claude_proposal_becomes_runnable_skill():
    proposal = {
        "category": "cookie-security", "action_type": "web-misconfiguration-checks",
        "risk_level": 1, "severity": "low", "name": "Cookie flags", "title": "Cookie missing HttpOnly",
        "tags": ["cookies"], "probes": [{"path": "/login"}],
        "detect": {"mode": "all", "conditions": [
            {"check": "header_present", "header": "set-cookie"},
            {"check": "header_lacks", "header": "set-cookie", "substring": "HttpOnly"}]},
    }
    c = _client("propose_skills", {"proposals": [proposal]})
    profile = SiteProfile(target_url="http://localhost:3001", summary="x")
    specs = generate_skills(ClaudeSkillGenerator(c, RuleBasedSkillGenerator()), profile,
                            allowed_testing=ALLOWED)
    assert len(specs) == 1
    # The LLM-authored skill actually runs and fires.
    resp = HttpResponse(200, {"set-cookie": "sid=abc; Path=/"}, "u", body="")
    obs = SpecSkill(specs[0]).run(type("H", (), {"get": lambda self, u: resp})(), "http://localhost:3001")
    assert obs["finding"]["category"] == "cookie-security"


def test_claude_overpermissive_proposal_is_rejected_by_coercion():
    # The trust boundary drops a risk-3 proposal even though the LLM returned it.
    bad = {"category": "rce", "action_type": "exploitation", "risk_level": 3, "severity": "high",
           "probes": [{"path": "/x"}], "detect": {"mode": "any", "conditions": [
               {"check": "status_equals", "value": 500}]}}
    c = _client("propose_skills", {"proposals": [bad]})
    specs = generate_skills(ClaudeSkillGenerator(c, RuleBasedSkillGenerator()),
                            SiteProfile(target_url="u", summary="x"), allowed_testing=ALLOWED)
    assert specs == []


def test_skill_generator_falls_back_on_error():
    profile = SiteProfile(target_url="u", summary="x",
                          gaps=[{"category": "crawler-policy-disclosure", "hint": "h", "path": "/robots.txt"}])
    out = ClaudeSkillGenerator(_err_client(), RuleBasedSkillGenerator()).propose(profile, [])
    assert any(p["category"] == "crawler-policy-disclosure" for p in out)  # heuristic fallback fired
