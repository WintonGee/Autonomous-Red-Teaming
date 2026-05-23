from src.skills.dedup import dedupe_specs
from src.skills.spec import SkillSpec, SpecSkill, coerce_or_reject, spec_signature
from src.tools.http_client import HttpResponse

ALLOWED = {"reconnaissance", "web-misconfiguration-checks", "safe-validation"}


def _proposal(**over):
    base = {
        "category": "crawler-policy-disclosure",
        "action_type": "reconnaissance",
        "risk_level": 1,
        "severity": "low",
        "probes": [{"path": "/robots.txt"}],
        "detect": {"mode": "all", "conditions": [
            {"check": "status_equals", "value": 200},
            {"check": "body_contains", "substring": "Disallow"},
        ]},
        "title": "robots.txt discloses paths",
        "tags": ["recon", "robots"],
    }
    base.update(over)
    return base


def _http(resp):
    class _H:
        def get(self, url):
            return resp
    return _H()


# ---- coerce_or_reject (the trust boundary) ----
def test_valid_proposal_coerces_with_deterministic_id():
    spec = coerce_or_reject(_proposal(), allowed_testing=ALLOWED)
    assert spec is not None
    assert spec.id.startswith("web.generated.crawler_policy_disclosure.")
    # deterministic: same capability -> same id
    assert coerce_or_reject(_proposal(), allowed_testing=ALLOWED).id == spec.id


def test_rejects_risk_above_two():
    assert coerce_or_reject(_proposal(risk_level=3), allowed_testing=ALLOWED) is None


def test_rejects_unauthorized_action_type():
    assert coerce_or_reject(_proposal(action_type="exploitation"), allowed_testing=ALLOWED) is None


def test_rejects_unsafe_probe_paths():
    for bad in [{"path": "http://evil/x"}, {"path": "/../etc/passwd"}, {"path": "nope"}]:
        assert coerce_or_reject(_proposal(probes=[bad]), allowed_testing=ALLOWED) is None


def test_rejects_bad_regex_and_unknown_check():
    bad_re = _proposal(detect={"mode": "any", "conditions": [{"check": "body_matches", "pattern": "("}]})
    assert coerce_or_reject(bad_re, allowed_testing=ALLOWED) is None
    bad_check = _proposal(detect={"mode": "any", "conditions": [{"check": "exfiltrate"}]})
    assert coerce_or_reject(bad_check, allowed_testing=ALLOWED) is None


def test_rejects_empty_probes_or_conditions():
    assert coerce_or_reject(_proposal(probes=[]), allowed_testing=ALLOWED) is None
    assert coerce_or_reject(_proposal(detect={"mode": "any", "conditions": []}), allowed_testing=ALLOWED) is None


# ---- SpecSkill interpreter ----
def test_specskill_fires_on_match_with_suspected_confidence():
    spec = coerce_or_reject(_proposal(), allowed_testing=ALLOWED)
    resp = HttpResponse(200, {"content-type": "text/plain"}, "u", body="User-agent: *\nDisallow: /ftp")
    obs = SpecSkill(spec).run(_http(resp), "http://localhost:3001")
    assert obs["finding"]["confidence"] == "suspected"
    assert obs["finding"]["category"] == "crawler-policy-disclosure"
    assert obs["matched"][0]["path"] == "/robots.txt"


def test_specskill_no_finding_when_detect_fails():
    spec = coerce_or_reject(_proposal(), allowed_testing=ALLOWED)
    resp = HttpResponse(200, {}, "u", body="nothing relevant here")
    obs = SpecSkill(spec).run(_http(resp), "http://localhost:3001")
    assert "finding" not in obs


# ---- dedupe ----
def test_signature_is_order_insensitive():
    a = coerce_or_reject(_proposal(probes=[{"path": "/a"}, {"path": "/b"}]), allowed_testing=ALLOWED)
    b = coerce_or_reject(_proposal(probes=[{"path": "/b"}, {"path": "/a"}]), allowed_testing=ALLOWED)
    assert spec_signature(a) == spec_signature(b)


def test_dedupe_drops_structural_duplicate_and_keeps_unique():
    existing = coerce_or_reject(_proposal(), allowed_testing=ALLOWED)
    dup = coerce_or_reject(_proposal(title="different prose, same capability"), allowed_testing=ALLOWED)
    fresh = coerce_or_reject(_proposal(category="cookie-security", probes=[{"path": "/login"}],
                                       detect={"mode": "any", "conditions": [
                                           {"check": "header_present", "header": "set-cookie"}]}),
                             allowed_testing=ALLOWED)
    out = dedupe_specs([dup, fresh], existing_specs=[existing])
    ids = {s.id for s in out}
    assert existing.id not in ids       # structural dup dropped
    assert fresh.id in ids              # genuinely new kept


def test_dedupe_respects_reuse_before_create_against_trusted_skills():
    cand = coerce_or_reject(_proposal(), allowed_testing=ALLOWED)
    trusted_card = {"id": "web.x", "category": cand.category,
                    "action_type": cand.action_type, "tags": cand.tags}
    out = dedupe_specs([cand], existing_skill_cards=[trusted_card])
    assert out == []  # capability already covered by a trusted skill
