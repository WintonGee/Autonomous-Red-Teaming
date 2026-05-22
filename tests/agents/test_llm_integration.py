"""Orchestrator with the LLM brains active, driven by a fake Claude client.

No network, no API key. Verifies the LLM is wired end-to-end, the audit trail is
durable, and the deterministic gates still hold with an LLM in the loop.
"""
from src.agents.llm.client import ClaudeClient
from src.orchestrator import build_orchestrator


class _Usage:
    input_tokens = 7
    output_tokens = 3


def _fake_llm():
    """Returns plausible structured output for whichever tool is forced."""
    def create(**kw):
        tool_name = kw["tool_choice"]["name"]
        if tool_name == "choose_skill":
            enum = kw["tools"][0]["input_schema"]["properties"]["skill_id"]["enum"]
            inp = {"skill_id": enum[0], "rationale": "llm pick"}
        elif tool_name == "report_findings":
            inp = {"rationale": "llm review", "findings": []}
        elif tool_name == "propose_skills":
            inp = {"proposals": []}
        else:
            inp = {}

        class _B:
            def __init__(self):
                self.type = "tool_use"
                self.name = tool_name
                self.input = inp

        class _R:
            def __init__(self):
                self.content = [_B()]
                self.usage = _Usage()

        return _R()

    return ClaudeClient(create_message=create)


def test_engagement_with_llm_active_writes_audit_and_keeps_gates():
    orch = build_orchestrator(dry_run=True, llm=True, llm_client=_fake_llm())
    report = orch.run_engagement("local-juice-shop", "assess")

    assert report.llm_active is True
    # Deterministic skill findings still produced (gates + skills unaffected).
    assert len(report.findings) >= 1
    assert all(o["ran"] for o in report.skill_outcomes)
    # Durable audit trail of external LLM calls (no raw payload).
    audit = orch.store.conn.execute(
        "SELECT content FROM episodic_events WHERE event_type='llm_call'"
    ).fetchall()
    assert len(audit) >= 1
    assert "agent_role" in audit[0]["content"]


def test_no_llm_when_client_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    orch = build_orchestrator(dry_run=True, llm=True)  # real ClaudeClient, no key
    report = orch.run_engagement("local-juice-shop", "assess")
    assert report.llm_active is False           # gracefully deterministic
    assert len(report.findings) >= 1            # still works
