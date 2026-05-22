from src.risk import RiskEngine


def test_authorized_risk_limit_is_honored_directly():
    # A properly-authorized target's level is honored, NOT clamped to the ceiling.
    assert RiskEngine(project_ceiling=1).max_allowed("high") == 3
    assert RiskEngine(project_ceiling=1).max_allowed("medium") == 2
    assert RiskEngine(project_ceiling=1).max_allowed("low") == 1


def test_malformed_authorization_falls_back_to_ceiling():
    # Missing/unknown risk_limit -> conservative project ceiling, not wide open.
    assert RiskEngine(project_ceiling=1).max_allowed("nonsense") == 1
    assert RiskEngine(project_ceiling=0).max_allowed("") == 0


def test_within_enforces_ceiling_and_prohibited():
    engine = RiskEngine()
    assert engine.within(2, 2) is True
    assert engine.within(3, 2) is False     # above the allowed maximum
    assert engine.within(4, 4) is False     # prohibited is never allowed
    assert engine.within(-1, 2) is False    # nonsense level
