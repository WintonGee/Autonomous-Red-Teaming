from src.agents.recon import RuleBasedRecon, gather
from src.tools.http_client import HttpClient, fake_juice_shop_fetch


def _http():
    return HttpClient(allowed_urls={"http://localhost:3001"}, fetch=fake_juice_shop_fetch)


def test_gather_fetches_the_safe_recon_set():
    obs = gather(_http(), "http://localhost:3001")
    assert {o["path"] for o in obs} == {"/", "/robots.txt"}


def test_understand_surfaces_server_header_tech_generically():
    # Works on any target, not just Juice Shop: whatever the Server header
    # advertises shows up as detected tech (AltoroMutual is Apache-Coyote/Tomcat).
    obs = [{"path": "/", "status": 200, "headers": {"server": "Apache-Coyote/1.1"}, "body_head": ""}]
    profile = RuleBasedRecon().understand("https://demo.testfire.net", obs)
    assert any("Apache-Coyote" in t for t in profile.tech)


def test_understand_detects_tech_security_notes_and_gap():
    profile = RuleBasedRecon().understand("http://localhost:3001", gather(_http(), "http://localhost:3001"))
    assert "OWASP Juice Shop" in profile.tech
    assert any(g["category"] == "crawler-policy-disclosure" for g in profile.gaps)

    notable = [n for o in profile.observations for n in o["notable"]]
    assert "wildcard CORS" in notable
    assert "no Content-Security-Policy" in notable
    assert "robots.txt discloses paths" in notable
