from src.risk import RiskEngine


def test_max_allowed_is_min_of_limit_and_ceiling():
    assert RiskEngine(project_ceiling=1).max_allowed("high") == 1   # ceiling caps it
    assert RiskEngine(project_ceiling=3).max_allowed("low") == 1    # limit caps it
    assert RiskEngine(project_ceiling=3).max_allowed("medium") == 2


def test_within_enforces_ceiling_and_prohibited():
    engine = RiskEngine(project_ceiling=2)
    assert engine.within(2, 2) is True
    assert engine.within(3, 2) is False     # above ceiling
    assert engine.within(4, 4) is False     # prohibited is never allowed
    assert engine.within(-1, 2) is False    # nonsense level
