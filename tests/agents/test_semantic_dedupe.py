"""Semantic dedupe layer (ClaudeSpecDeduper), exercised with an injected transport.

Proves the 6th dedupe layer drops a functional duplicate the structural layers
miss — e.g. an LLM re-deriving an existing check under a different category.
"""
from src.agents.llm.client import ClaudeClient
from src.agents.llm.reasoners import ClaudeSpecDeduper
from src.agents.recon import SiteProfile
from src.agents.skillsmith import RuleBasedSkillGenerator, generate_skills
from src.skills.spec import coerce_or_reject

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


def _spec(category, header):
    return coerce_or_reject({
        "category": category, "action_type": "web-misconfiguration-checks", "risk_level": 1,
        "severity": "low", "probes": [{"path": "/"}],
        "detect": {"mode": "any", "conditions": [{"check": "header_absent", "header": header}]},
    }, allowed_testing=ALLOWED)


def test_semantic_deduper_drops_flagged_candidate():
    deduper = ClaudeSpecDeduper(_client("flag_redundant", {"duplicate_indices": [0]}))
    candidates = [_spec("security-headers", "content-security-policy"),
                  _spec("open-redirect", "location")]
    redundant = deduper.redundant(candidates, [{"id": "web.missing_security_headers",
                                                "name": "Missing Security Headers", "category": "web-misconfiguration"}])
    assert redundant == [0]


def test_semantic_deduper_ignores_out_of_range_indices():
    deduper = ClaudeSpecDeduper(_client("flag_redundant", {"duplicate_indices": [0, 99]}))
    assert deduper.redundant([_spec("x", "a")], []) == [0]


def test_semantic_deduper_fails_open_on_error():
    deduper = ClaudeSpecDeduper(_err_client())
    assert deduper.redundant([_spec("x", "a")], []) == []


def test_generate_skills_applies_semantic_layer_and_audits_it():
    profile = SiteProfile(
        target_url="u", summary="x",
        gaps=[{"category": "crawler-policy-disclosure", "hint": "h", "path": "/robots.txt"}],
    )
    deduper = ClaudeSpecDeduper(_client("flag_redundant", {"duplicate_indices": [0]}))
    audit: dict = {}
    out = generate_skills(RuleBasedSkillGenerator(), profile, allowed_testing=ALLOWED,
                          semantic_deduper=deduper, audit=audit)
    assert out == []                          # the one heuristic proposal was flagged redundant
    assert audit["dropped_semantic"] == 1
