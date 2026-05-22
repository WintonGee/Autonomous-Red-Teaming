from src.agents.contracts import (
    EngagementState,
    ExecutionResult,
    ProposedAction,
    SkillInfo,
    Verdict,
)
from src.agents.llm.client import ClaudeClient
from src.agents.llm.reasoners import ClaudeEvaluator, ClaudeLearner, ClaudePlanner
from src.agents.reasoners import RuleBasedEvaluator, RuleBasedLearner, RuleBasedPlanner


class _Usage:
    input_tokens = 1
    output_tokens = 1


def _client(name, inp):
    class _B:
        def __init__(self):
            self.type = "tool_use"
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


def _state():
    return EngagementState(authorization_id="a", goal="assess", target_url="http://localhost:3001",
                           available_skills=[SkillInfo("web.x", "X", "cat", 1, "recon")], max_risk=2)


def _result(observations, ok=True):
    action = ProposedAction(skill_id="web.x", target_url="http://localhost:3001",
                            action_type="recon", risk_level=2, rationale="")
    return ExecutionResult(action, ok=ok, observations=observations)


# ---- planner ----
def test_planner_uses_llm_choice():
    c = _client("choose_skill", {"skill_id": "web.x", "rationale": "best fit"})
    action = ClaudePlanner(c, RuleBasedPlanner()).propose(_state())
    assert action.skill_id == "web.x"
    assert "[claude]" in action.rationale


def test_planner_rejects_skill_not_on_menu():
    c = _client("choose_skill", {"skill_id": "injected-evil", "rationale": "x"})
    action = ClaudePlanner(c, RuleBasedPlanner()).propose(_state())
    assert action.skill_id == "web.x"  # fell back to a real eligible skill


def test_planner_falls_back_on_error():
    action = ClaudePlanner(_err_client(), RuleBasedPlanner()).propose(_state())
    assert action.skill_id == "web.x"


# ---- evaluator ----
def test_evaluator_adds_finding_with_resolved_evidence():
    obs = {"status_code": 500, "body_snippet": "Stack trace: NPE at Server.java:42", "finding": None}
    c = _client("report_findings", {"rationale": "stack trace leak", "findings": [
        {"title": "Stack trace exposure", "category": "info-disclosure",
         "severity": "medium", "evidence_pointer": "body_snippet"}]})
    v = ClaudeEvaluator(c, RuleBasedEvaluator()).evaluate(_result(obs))
    assert len(v.extra_findings) == 1
    ef = v.extra_findings[0]
    assert ef["source"] == "llm-evaluator"
    assert ef["evidence"]["pointer"] == "body_snippet"
    assert "Stack trace" in ef["evidence"]["value"]
    assert v.has_signal is True


def test_evaluator_drops_unresolvable_pointer():
    obs = {"status_code": 200, "body_snippet": "fine"}
    c = _client("report_findings", {"rationale": "x", "findings": [
        {"title": "hallucinated", "category": "x", "severity": "high",
         "evidence_pointer": "no_such_key"}]})
    v = ClaudeEvaluator(c, RuleBasedEvaluator()).evaluate(_result(obs))
    assert v.extra_findings == []


def test_evaluator_caps_findings_at_three():
    obs = {"a": "one", "b": "two"}
    findings = [{"title": f"f{i}", "category": "c", "severity": "low", "evidence_pointer": "a"}
                for i in range(6)]
    c = _client("report_findings", {"rationale": "x", "findings": findings})
    v = ClaudeEvaluator(c, RuleBasedEvaluator()).evaluate(_result(obs))
    assert len(v.extra_findings) == 3


def test_evaluator_falls_back_on_error():
    v = ClaudeEvaluator(_err_client(), RuleBasedEvaluator()).evaluate(_result({"a": "1"}))
    assert v.extra_findings == []


# ---- learner ----
def _verdict(category):
    return Verdict(action=ProposedAction("web.x", "u", "recon", 2, ""), has_signal=True,
                   confidence="confirmed", finding={"title": "f", "category": category})


def test_learner_proposes_new_skill_for_gap():
    existing = [SkillInfo("web.x", "X", "web-misconfiguration", 1, "checks")]
    c = _client("propose_skills", {"proposals": [
        {"title": "Detect SQLi", "category": "sql-injection", "rationale": "gap"}]})
    out = ClaudeLearner(c, RuleBasedLearner()).propose_skills([_verdict("sql-injection")], existing)
    assert any(p.category == "sql-injection" for p in out)


def test_learner_reuses_existing_category():
    existing = [SkillInfo("web.x", "X", "web-misconfiguration", 1, "checks")]
    c = _client("propose_skills", {"proposals": [
        {"title": "dup", "category": "web-misconfiguration", "rationale": "x"}]})
    out = ClaudeLearner(c, RuleBasedLearner()).propose_skills([_verdict("web-misconfiguration")], existing)
    assert out == []  # nothing new: the category already exists
