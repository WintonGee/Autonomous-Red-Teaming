import pytest

from src.agents.llm.client import ClaudeClient, LlmError


class _Usage:
    input_tokens = 11
    output_tokens = 4


class _ToolBlock:
    def __init__(self, name, inp):
        self.type = "tool_use"
        self.name = name
        self.input = inp


class _Resp:
    def __init__(self, name, inp):
        self.content = [_ToolBlock(name, inp)]
        self.usage = _Usage()


def _client(name, inp):
    return ClaudeClient(create_message=lambda **kw: _Resp(name, inp))


def test_structured_returns_tool_input_and_records_audit():
    c = _client("choose", {"x": 1})
    assert c.available() is True
    out = c.structured(system="s", user="u", tool={"name": "choose"}, tool_name="choose",
                       audit_meta={"agent_role": "planner", "chars_sent": 3, "redacted_secrets": 2})
    assert out == {"x": 1}

    audit = c.drain_audit()
    assert len(audit) == 1
    assert audit[0]["agent_role"] == "planner"
    assert audit[0]["redacted_secrets"] == 2
    assert audit[0]["input_tokens"] == 11
    assert c.drain_audit() == []  # drained


def test_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = ClaudeClient()  # no injected transport, no key
    assert c.available() is False
    with pytest.raises(LlmError):
        c.structured(system="s", user="u", tool={"name": "t"}, tool_name="t")


def test_raises_when_no_tool_block():
    class _Empty:
        content = []
        usage = None
    c = ClaudeClient(create_message=lambda **kw: _Empty())
    with pytest.raises(LlmError):
        c.structured(system="s", user="u", tool={"name": "t"}, tool_name="t")


def test_wraps_sdk_errors_and_audits_failure():
    def boom(**kw):
        raise RuntimeError("network down")
    c = ClaudeClient(create_message=boom)
    with pytest.raises(LlmError):
        c.structured(system="s", user="u", tool={"name": "t"}, tool_name="t",
                     audit_meta={"agent_role": "evaluator"})
    audit = c.drain_audit()
    assert len(audit) == 1
    assert "error" in audit[0]  # failure is visible, not silent
    assert audit[0]["agent_role"] == "evaluator"
